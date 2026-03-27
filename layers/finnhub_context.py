#!/usr/bin/env python3
"""
finnhub_context.py -- CT-001.5 Finnhub Fallback Provider (Session B)

CT-001 context enrichment via Finnhub deterministic fallback.
Session B: Full metric computation for CT-001.1 (EPS + Revenue revision),
CT-001.2 (Valuation ratios), and CT-001.4 (Margin trajectory).
Preserves Session A infrastructure (API key check, rate limiter, timeout,
sector median cache reader/writer).

Location: Project root, alongside yahoo_fundamentals.py, ibkr_asset_gates.py.

ASCII-only encoding -- no Unicode characters. Operator runs on Windows cp1252.
"""

import os
import json
import time
import datetime
import argparse
import concurrent.futures

# Session B: Import finnhub-python with graceful fallback
try:
    import finnhub
    _FH_AVAILABLE = True
except ImportError:
    _FH_AVAILABLE = False

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except Exception as _yf_import_err:
    _YF_AVAILABLE = False
    print("[FINNHUB CONTEXT] WARNING: yfinance import failed: %s" % str(_yf_import_err))


# =============================================================================
# CONFIGURATION
# =============================================================================

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY")

FINNHUB_TIMEOUT = 30  # seconds per individual API call

STALENESS_DAYS = 90

CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs", "sector_median_pe.json"
)

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLE": "Energy",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}


# =============================================================================
# RATE LIMITER
# =============================================================================

_last_call_time = 0


def _rate_limit():
    """Enforce minimum 1-second spacing between Finnhub API calls.

    Finnhub free tier allows 60 calls/minute. This simple limiter
    ensures at least 1s between consecutive calls. Session A validates
    the mechanism; Session B uses it for actual API calls.
    """
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_call_time = time.time()


# =============================================================================
# TIMED CALL HELPER (Session B)
# =============================================================================

def _timed_call(fn, *args, timeout=FINNHUB_TIMEOUT, **kwargs):
    """Execute fn(*args, **kwargs) with a hard timeout. Returns None on timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return None
        except Exception:
            return None


# =============================================================================
# FINNHUB FETCH FUNCTIONS (Session B)
# =============================================================================

def _fetch_eps_revision(client, ticker):
    """Fetch EPS revision data from Finnhub company_eps_estimates.

    Returns dict with EPS_Revision_Direction, EPS_Revision_Pct, or UNAVAILABLE.
    """
    result = {
        "EPS_Revision_Direction": "UNAVAILABLE",
        "EPS_Revision_Pct": None,
        "EPS_Revision_Source": "UNAVAILABLE",
    }
    try:
        _rate_limit()
        raw = _timed_call(client.company_eps_estimates, ticker, freq='quarterly')
        if raw is None or not isinstance(raw, dict):
            return result
        data = raw.get("data") or raw.get("estimates") or []
        if isinstance(raw, list):
            data = raw
        if not data:
            # Try direct list format
            if isinstance(raw, list):
                data = raw
            else:
                return result

        # Find the nearest future quarter with at least 2 estimate snapshots
        import math
        today_str = datetime.date.today().isoformat()
        best_period = None
        for entry in data:
            period = entry.get("period", "")
            if period >= today_str:
                best_period = entry
                break
        if best_period is None and data:
            best_period = data[0]  # fallback to first available

        if best_period is None:
            return result

        # Finnhub eps_estimates: look for epsAvg (current) and compare snapshots
        eps_avg = best_period.get("epsAvg")
        # Some Finnhub responses have revision data in different structures
        # Try to find a 30-day-ago comparison
        eps_ago = None

        # Check if there's a prior estimate snapshot in the data for the same period
        target_period = best_period.get("period", "")
        estimates_for_period = [e for e in data if e.get("period") == target_period]
        if len(estimates_for_period) >= 2:
            eps_avg = estimates_for_period[0].get("epsAvg")
            eps_ago = estimates_for_period[1].get("epsAvg")

        if eps_avg is not None and eps_ago is not None and abs(eps_ago) > 0:
            if not (isinstance(eps_avg, float) and math.isnan(eps_avg)):
                if not (isinstance(eps_ago, float) and math.isnan(eps_ago)):
                    pct = ((eps_avg - eps_ago) / abs(eps_ago)) * 100.0
                    pct = round(pct, 1)
                    if pct > 3.0:
                        direction = "REVISING UP"
                    elif pct < -3.0:
                        direction = "REVISING DOWN"
                    else:
                        direction = "STABLE"
                    result["EPS_Revision_Direction"] = direction
                    result["EPS_Revision_Pct"] = pct
                    result["EPS_Revision_Source"] = "FINNHUB"
    except Exception as e:
        print("[FINNHUB CONTEXT] EPS revision fetch error: %s" % str(e))
    return result


def _fetch_revenue_revision(client, ticker):
    """Fetch revenue revision data from Finnhub company_revenue_estimates.

    This is the ONLY source for revenue revision -- Yahoo has no revenue trend data.
    Returns dict with Revenue_Revision_Direction, Revenue_Revision_Pct, or UNAVAILABLE.
    """
    result = {
        "Revenue_Revision_Direction": "UNAVAILABLE",
        "Revenue_Revision_Pct": None,
        "Revenue_Revision_Source": "UNAVAILABLE",
    }
    try:
        _rate_limit()
        raw = _timed_call(client.company_revenue_estimates, ticker, freq='quarterly')
        if raw is None:
            return result
        data = raw.get("data") or raw.get("estimates") or []
        if isinstance(raw, list):
            data = raw
        if not data:
            return result

        import math
        today_str = datetime.date.today().isoformat()
        best_period = None
        for entry in data:
            period = entry.get("period", "")
            if period >= today_str:
                best_period = entry
                break
        if best_period is None and data:
            best_period = data[0]

        if best_period is None:
            return result

        rev_avg = best_period.get("revenueAvg")
        rev_ago = None

        target_period = best_period.get("period", "")
        estimates_for_period = [e for e in data if e.get("period") == target_period]
        if len(estimates_for_period) >= 2:
            rev_avg = estimates_for_period[0].get("revenueAvg")
            rev_ago = estimates_for_period[1].get("revenueAvg")

        if rev_avg is not None and rev_ago is not None and abs(rev_ago) > 0:
            if not (isinstance(rev_avg, float) and math.isnan(rev_avg)):
                if not (isinstance(rev_ago, float) and math.isnan(rev_ago)):
                    pct = ((rev_avg - rev_ago) / abs(rev_ago)) * 100.0
                    pct = round(pct, 1)
                    if pct > 3.0:
                        direction = "REVISING UP"
                    elif pct < -3.0:
                        direction = "REVISING DOWN"
                    else:
                        direction = "STABLE"
                    result["Revenue_Revision_Direction"] = direction
                    result["Revenue_Revision_Pct"] = pct
                    result["Revenue_Revision_Source"] = "FINNHUB"
    except Exception as e:
        print("[FINNHUB CONTEXT] Revenue revision fetch error: %s" % str(e))
    return result


def _fetch_valuation(client, ticker):
    """Fetch valuation ratios from Finnhub company_basic_financials.

    Returns dict with Forward_PE, PEG_Ratio, PS_Ratio (fallback values).
    """
    result = {
        "Forward_PE": None,
        "PEG_Ratio": None,
        "PS_Ratio": None,
        "Forward_PE_Source": "UNAVAILABLE",
        "PEG_Ratio_Source": "UNAVAILABLE",
        "PS_Ratio_Source": "UNAVAILABLE",
    }
    try:
        _rate_limit()
        raw = _timed_call(client.company_basic_financials, ticker, 'all')
        if raw is None or not isinstance(raw, dict):
            return result
        m = raw.get("metric", {})
        if not m:
            return result

        # Forward P/E proxy
        fpe = m.get("peBasicExclExtraTTM") or m.get("peExclExtraTTM") or m.get("peTTM")
        if fpe is not None:
            result["Forward_PE"] = round(float(fpe), 2)
            result["Forward_PE_Source"] = "FINNHUB"

        # PEG ratio
        peg = m.get("pegAnnual") or m.get("pegTTM")
        if peg is not None:
            result["PEG_Ratio"] = round(float(peg), 2)
            result["PEG_Ratio_Source"] = "FINNHUB"

        # P/S ratio
        ps = m.get("psAnnual") or m.get("psTTM")
        if ps is not None:
            result["PS_Ratio"] = round(float(ps), 2)
            result["PS_Ratio_Source"] = "FINNHUB"

    except Exception as e:
        print("[FINNHUB CONTEXT] Valuation fetch error: %s" % str(e))
    return result


def _fetch_margin_trajectory(client, ticker):
    """Fetch margin trajectory from Finnhub financials_reported (income statement).

    Returns dict with Gross_Margin_Trend, Operating_Margin_Trend, Margin_Note.
    """
    result = {
        "Gross_Margin_Trend": "UNAVAILABLE",
        "Gross_Margin_Delta_pp": None,
        "Operating_Margin_Trend": "UNAVAILABLE",
        "Operating_Margin_Delta_pp": None,
        "Margin_Note": None,
        "Gross_Margin_Source": "UNAVAILABLE",
        "Operating_Margin_Source": "UNAVAILABLE",
    }
    try:
        _rate_limit()
        raw = _timed_call(client.financials_reported, symbol=ticker, freq='quarterly')
        if raw is None or not isinstance(raw, dict):
            return result
        data = raw.get("data", [])
        if not data or len(data) < 2:
            return result

        # Sort by date descending -- each entry has a 'period' date
        try:
            data_sorted = sorted(data, key=lambda x: x.get("period", ""), reverse=True)
        except Exception:
            data_sorted = data

        if len(data_sorted) < 4:
            return result

        def _extract_financials(entry):
            """Extract gross profit, revenue, operating income from a Finnhub financials entry."""
            report = entry.get("report", {})
            ic = report.get("ic", []) if isinstance(report, dict) else []
            vals = {}
            for item in ic:
                concept = (item.get("concept", "") or "").lower()
                value = item.get("value")
                if "grossprofit" in concept.replace(" ", "").replace("_", ""):
                    vals["gross_profit"] = value
                elif "revenue" in concept and "total" in concept:
                    vals["revenue"] = value
                elif concept in ("revenue", "revenues", "salesrevenuenet"):
                    if "revenue" not in vals:
                        vals["revenue"] = value
                elif "operatingincome" in concept.replace(" ", "").replace("_", ""):
                    vals["operating_income"] = value
            return vals

        q0 = _extract_financials(data_sorted[0])
        # Use index 4 for YoY if available, else last available
        qy_idx = 4 if len(data_sorted) >= 5 else len(data_sorted) - 1
        qy = _extract_financials(data_sorted[qy_idx])

        # Gross margin
        if (q0.get("gross_profit") is not None and q0.get("revenue") is not None
                and qy.get("gross_profit") is not None and qy.get("revenue") is not None
                and float(q0["revenue"]) != 0 and float(qy["revenue"]) != 0):
            gm_q0 = float(q0["gross_profit"]) / float(q0["revenue"]) * 100.0
            gm_qy = float(qy["gross_profit"]) / float(qy["revenue"]) * 100.0
            delta = round(gm_q0 - gm_qy, 1)
            if abs(delta) > 100.0:
                pass  # Extreme base-period distortion -- leave as UNAVAILABLE
            else:
                result["Gross_Margin_Delta_pp"] = delta
                if delta > 1.5:
                    result["Gross_Margin_Trend"] = "EXPANDING"
                elif delta < -1.5:
                    result["Gross_Margin_Trend"] = "COMPRESSING"
                else:
                    result["Gross_Margin_Trend"] = "STABLE"
                result["Gross_Margin_Source"] = "FINNHUB"

        # Operating margin
        if (q0.get("operating_income") is not None and q0.get("revenue") is not None
                and qy.get("operating_income") is not None and qy.get("revenue") is not None
                and float(q0["revenue"]) != 0 and float(qy["revenue"]) != 0):
            om_q0 = float(q0["operating_income"]) / float(q0["revenue"]) * 100.0
            om_qy = float(qy["operating_income"]) / float(qy["revenue"]) * 100.0
            delta = round(om_q0 - om_qy, 1)
            if abs(delta) > 100.0:
                pass  # Extreme base-period distortion -- leave as UNAVAILABLE
            else:
                result["Operating_Margin_Delta_pp"] = delta
                if delta > 1.5:
                    result["Operating_Margin_Trend"] = "EXPANDING"
                elif delta < -1.5:
                    result["Operating_Margin_Trend"] = "COMPRESSING"
                else:
                    result["Operating_Margin_Trend"] = "STABLE"
                result["Operating_Margin_Source"] = "FINNHUB"

        # Margin note
        _notes = []
        if result["Gross_Margin_Trend"] == "COMPRESSING" and result["Gross_Margin_Delta_pp"] is not None:
            _notes.append("Gross margin compressing (%.1fpp YoY)" % result["Gross_Margin_Delta_pp"])
        if result["Operating_Margin_Trend"] == "COMPRESSING" and result["Operating_Margin_Delta_pp"] is not None:
            _notes.append("Operating margin compressing (%.1fpp YoY)" % result["Operating_Margin_Delta_pp"])
        if _notes:
            result["Margin_Note"] = " | ".join(_notes) + " -- growth may not translate to earnings."

    except Exception as e:
        print("[FINNHUB CONTEXT] Margin trajectory fetch error: %s" % str(e))
    return result

def _read_cache():
    """Read docs/sector_median_pe.json and return the parsed dict.

    Returns:
        dict: Cache contents keyed by sector ETF ticker (e.g. 'XLK').
              Returns empty dict if file not found or parse error.
    """
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"[FINNHUB CONTEXT] WARNING: Cache file read error: {e}")
        return {}


def _write_cache(cache_data):
    """Write cache dict to docs/sector_median_pe.json atomically.

    Writes to a .tmp file first, then replaces the original via
    os.replace() to avoid partial writes on crash.

    Args:
        cache_data: dict to serialize as JSON.

    Returns:
        bool: True if write succeeded, False otherwise.
    """
    tmp_path = CACHE_FILE + ".tmp"
    try:
        cache_dir = os.path.dirname(CACHE_FILE)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=4)
        os.replace(tmp_path, CACHE_FILE)
        return True
    except (IOError, OSError) as e:
        print(f"[FINNHUB CONTEXT] WARNING: Cache file write error: {e}")
        # Clean up tmp file if it exists
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False


def _is_any_entry_stale(cache):
    """Check if any cache entry has an updated date older than STALENESS_DAYS.

    Args:
        cache: dict from _read_cache().

    Returns:
        bool: True if any entry is stale or has missing/unparseable date.
    """
    if not cache:
        return True
    today = datetime.date.today()
    for etf_key, entry in cache.items():
        updated_str = entry.get("updated", "")
        if not updated_str:
            return True
        try:
            updated_date = datetime.date.fromisoformat(updated_str)
            if (today - updated_date).days > STALENESS_DAYS:
                return True
        except (ValueError, TypeError):
            return True
    return False


def _refresh_all_sectors():
    """Refresh all 11 sector ETF entries by fetching forwardPe from Yahoo Finance.

    Fetches yfinance info['forwardPe'] for each sector ETF. On success,
    updates the entry. On failure for a specific ETF, preserves the stale
    value (if any) and logs a warning.

    Returns:
        dict: Refreshed cache dict. May contain a mix of fresh and stale entries.
              Returns empty dict if yfinance is not available.
    """
    if not _YF_AVAILABLE:
        print("[FINNHUB CONTEXT] WARNING: yfinance not available -- cannot refresh sector median cache.")
        return {}

    today_str = datetime.date.today().isoformat()
    # Start from existing cache to preserve stale values on partial failure
    existing_cache = _read_cache()
    refreshed = {}

    for etf_ticker, sector_name in SECTOR_ETFS.items():
        try:
            ticker_obj = yf.Ticker(etf_ticker)
            info = ticker_obj.info or {}
            # Sector ETFs lack forwardPe (no forward earnings estimates).
            # Use trailingPE as the sector median proxy.
            pe_value = info.get("forwardPe") or info.get("trailingPE")
            pe_source = "forwardPe" if info.get("forwardPe") else "trailingPE"
            if pe_value is not None and pe_value > 0:
                refreshed[etf_ticker] = {
                    "median_pe": round(float(pe_value), 1),
                    "sector": sector_name,
                    "updated": today_str,
                }
                print("[FINNHUB CONTEXT] Refreshed %s (%s): %s = %.1f" % (etf_ticker, sector_name, pe_source, pe_value))
            else:
                # Yahoo returned None for both PE keys -- keep stale value
                if etf_ticker in existing_cache:
                    refreshed[etf_ticker] = existing_cache[etf_ticker]
                    print("[FINNHUB CONTEXT] WARNING: Yahoo returned None for %s PE -- keeping stale value." % etf_ticker)
                else:
                    # No stale value to fall back on
                    refreshed[etf_ticker] = {
                        "median_pe": None,
                        "sector": sector_name,
                        "updated": "",
                    }
                    print("[FINNHUB CONTEXT] WARNING: Yahoo returned None for %s PE -- no stale value available." % etf_ticker)
        except Exception as e:
            # Preserve stale value on error
            if etf_ticker in existing_cache:
                refreshed[etf_ticker] = existing_cache[etf_ticker]
                print("[FINNHUB CONTEXT] WARNING: Error fetching %s: %s -- keeping stale value." % (etf_ticker, e))
            else:
                refreshed[etf_ticker] = {
                    "median_pe": None,
                    "sector": sector_name,
                    "updated": "",
                }
                print("[FINNHUB CONTEXT] WARNING: Error fetching %s: %s -- no stale value available." % (etf_ticker, e))

    return refreshed


def _check_and_refresh_cache(cache):
    """Check staleness and refresh cache if any entry is older than 90 days.

    If any entry is stale, triggers a full refresh of ALL 11 entries via
    Yahoo Finance. Writes refreshed data atomically.

    Args:
        cache: dict from _read_cache(). May be empty.

    Returns:
        dict: The cache dict to use (refreshed or original).
    """
    if not _is_any_entry_stale(cache):
        return cache

    print("[FINNHUB CONTEXT] Cache staleness detected (> %d days) -- triggering full refresh." % STALENESS_DAYS)
    refreshed = _refresh_all_sectors()

    if refreshed:
        if _write_cache(refreshed):
            print("[FINNHUB CONTEXT] Cache file refreshed successfully.")
            return refreshed
        else:
            print("[FINNHUB CONTEXT] WARNING: Cache refresh computed but file write failed.")
            # Return refreshed data even if write failed -- usable this run
            return refreshed
    else:
        print("[FINNHUB CONTEXT] WARNING: Cache refresh returned empty -- using existing data.")
        return cache


def _get_sector_median_pe(cache, sector_etf):
    """Look up sector median P/E from the cache for a given sector ETF ticker.

    Args:
        cache: dict from _read_cache() or _check_and_refresh_cache().
        sector_etf: Sector ETF ticker string (e.g. 'XLK').

    Returns:
        tuple: (median_pe_value, is_stale, sector_name)
            - median_pe_value: float or None
            - is_stale: bool -- True if entry is older than STALENESS_DAYS
            - sector_name: str or None
    """
    if not sector_etf or sector_etf not in cache:
        return None, False, None

    entry = cache[sector_etf]
    median_pe = entry.get("median_pe")
    sector_name = entry.get("sector")
    updated_str = entry.get("updated", "")

    is_stale = False
    if updated_str:
        try:
            updated_date = datetime.date.fromisoformat(updated_str)
            if (datetime.date.today() - updated_date).days > STALENESS_DAYS:
                is_stale = True
        except (ValueError, TypeError):
            is_stale = True
    else:
        is_stale = True

    return median_pe, is_stale, sector_name


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def run_finnhub_context(ticker, sector_etf, profile, is_etf):
    """CT-001 context enrichment via Finnhub fallback.

    Session B: Implements actual metric computation for CT-001.1/1.2/1.4.
    Each metric is fetched independently -- one timeout does not block others.

    Args:
        ticker: Asset ticker (e.g., 'AAPL')
        sector_etf: Sector ETF ticker from sympathy audit (e.g., 'XLK')
        profile: 'A', 'B', or 'C'
        is_etf: True if asset is an ETF

    Returns:
        dict with CT-001 metric fields. Values are computed from Finnhub
        where possible, or UNAVAILABLE on any failure.
    """
    # Initialise all fields as UNAVAILABLE
    result = {
        # --- CT-001.1: Earnings Revision ---
        "EPS_Revision_Direction": "UNAVAILABLE",
        "EPS_Revision_Pct": None,
        "Revenue_Revision_Direction": "UNAVAILABLE",
        "Revenue_Revision_Pct": None,
        "EPS_Revision_Source": "UNAVAILABLE",
        "Revenue_Revision_Source": "UNAVAILABLE",
        # --- CT-001.2: Valuation ---
        "Forward_PE": None,
        "PEG_Ratio": None,
        "PS_Ratio": None,
        "Valuation_Label": "UNAVAILABLE",
        "Sector_Median_PE": None,
        "Sector_Median_PE_Stale": False,
        "Forward_PE_Source": "UNAVAILABLE",
        "PEG_Ratio_Source": "UNAVAILABLE",
        "PS_Ratio_Source": "UNAVAILABLE",
        "Valuation_Label_Source": "UNAVAILABLE",
        # --- CT-001.4: Margin Trajectory ---
        "Gross_Margin_Trend": "UNAVAILABLE",
        "Gross_Margin_Delta_pp": None,
        "Operating_Margin_Trend": "UNAVAILABLE",
        "Operating_Margin_Delta_pp": None,
        "Margin_Note": None,
        "Gross_Margin_Source": "UNAVAILABLE",
        "Operating_Margin_Source": "UNAVAILABLE",
        # --- Diagnostics ---
        "finnhub_diagnostic": "",
    }

    # --- API Key Check ---
    _fh_api_available = False
    if not FINNHUB_API_KEY:
        result["finnhub_diagnostic"] = "Finnhub API key not configured"
    elif not _FH_AVAILABLE:
        result["finnhub_diagnostic"] = "finnhub-python not installed"
    else:
        _fh_api_available = True

    # --- ETF Skip ---
    if is_etf:
        result["finnhub_diagnostic"] = "ETF -- context enrichment skipped"
        return result

    # --- Sector Median Cache Read ---
    try:
        cache = _read_cache()

        # If cache is empty (file missing), attempt auto-creation
        if not cache:
            print("[FINNHUB CONTEXT] Cache file not found -- attempting auto-creation via Yahoo Finance.")
            cache = _refresh_all_sectors()
            if cache:
                _write_cache(cache)
            else:
                if result["finnhub_diagnostic"]:
                    result["finnhub_diagnostic"] += " | "
                result["finnhub_diagnostic"] += "sector median cache file not found and auto-refresh failed"
                return result

        # Check staleness and refresh if needed
        cache = _check_and_refresh_cache(cache)

        # Look up sector median P/E for the given sector ETF
        median_pe, is_stale, sector_name = _get_sector_median_pe(cache, sector_etf)
        if median_pe is not None:
            result["Sector_Median_PE"] = median_pe
            result["Sector_Median_PE_Stale"] = is_stale

    except Exception as e:
        print("[FINNHUB CONTEXT] WARNING: Cache processing error: %s" % str(e))
        if result["finnhub_diagnostic"]:
            result["finnhub_diagnostic"] += " | "
        result["finnhub_diagnostic"] += "cache processing error: %s" % str(e)

    # --- Finnhub API Calls (Session B) ---
    if _fh_api_available:
        client = finnhub.Client(api_key=FINNHUB_API_KEY)
        _diag_parts = []

        # CT-001.1: EPS Revision
        try:
            eps_data = _fetch_eps_revision(client, ticker)
            if eps_data.get("EPS_Revision_Source") == "FINNHUB":
                result["EPS_Revision_Direction"] = eps_data["EPS_Revision_Direction"]
                result["EPS_Revision_Pct"] = eps_data["EPS_Revision_Pct"]
                result["EPS_Revision_Source"] = "FINNHUB"
            else:
                _diag_parts.append("EPS revision: no data")
        except Exception as e:
            _diag_parts.append("EPS revision error: %s" % str(e))

        # CT-001.1: Revenue Revision (Finnhub ONLY source)
        try:
            rev_data = _fetch_revenue_revision(client, ticker)
            if rev_data.get("Revenue_Revision_Source") == "FINNHUB":
                result["Revenue_Revision_Direction"] = rev_data["Revenue_Revision_Direction"]
                result["Revenue_Revision_Pct"] = rev_data["Revenue_Revision_Pct"]
                result["Revenue_Revision_Source"] = "FINNHUB"
            else:
                _diag_parts.append("Revenue revision: no data")
        except Exception as e:
            _diag_parts.append("Revenue revision error: %s" % str(e))

        # CT-001.2: Valuation (fallback for Yahoo None)
        try:
            val_data = _fetch_valuation(client, ticker)
            for _vkey in ("Forward_PE", "PEG_Ratio", "PS_Ratio"):
                _src_key = _vkey + "_Source"
                if val_data.get(_src_key) == "FINNHUB" and val_data.get(_vkey) is not None:
                    result[_vkey] = val_data[_vkey]
                    result[_src_key] = "FINNHUB"
        except Exception as e:
            _diag_parts.append("Valuation error: %s" % str(e))

        # CT-001.4: Margin Trajectory (fallback for Yahoo None)
        try:
            margin_data = _fetch_margin_trajectory(client, ticker)
            for _mkey in ("Gross_Margin_Trend", "Operating_Margin_Trend"):
                _src_key = _mkey.replace("_Trend", "_Source")
                if margin_data.get(_src_key) == "FINNHUB" and margin_data.get(_mkey) != "UNAVAILABLE":
                    result[_mkey] = margin_data[_mkey]
                    result[_src_key] = "FINNHUB"
                    # Copy delta too
                    _delta_key = _mkey.replace("_Trend", "_Delta_pp")
                    result[_delta_key] = margin_data.get(_delta_key)
            if margin_data.get("Margin_Note"):
                result["Margin_Note"] = margin_data["Margin_Note"]
        except Exception as e:
            _diag_parts.append("Margin trajectory error: %s" % str(e))

        if _diag_parts:
            if result["finnhub_diagnostic"]:
                result["finnhub_diagnostic"] += " | "
            result["finnhub_diagnostic"] += "; ".join(_diag_parts)
        else:
            if not result["finnhub_diagnostic"]:
                result["finnhub_diagnostic"] = "Finnhub metrics computed"

    return result


# =============================================================================
# CLI ENTRY POINT (standalone testing)
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CT-001.5 Finnhub Context Enrichment (Session B)"
    )
    parser.add_argument("--ticker", required=True, help="Asset ticker (e.g. AAPL)")
    parser.add_argument("--sector-etf", default="", help="Sector ETF ticker (e.g. XLK)")
    parser.add_argument("--profile", default="B", choices=["A", "B", "C"],
                        help="Trading profile (default: B)")
    parser.add_argument("--is-etf", action="store_true", help="Flag if asset is an ETF")

    args = parser.parse_args()

    print("=" * 60)
    print("CT-001.5 Finnhub Context -- Session B")
    print("=" * 60)
    print(f"Ticker:     {args.ticker}")
    print(f"Sector ETF: {args.sector_etf or '(none)'}")
    print(f"Profile:    {args.profile}")
    print(f"Is ETF:     {args.is_etf}")
    print("-" * 60)

    results = run_finnhub_context(
        ticker=args.ticker,
        sector_etf=args.sector_etf,
        profile=args.profile,
        is_etf=args.is_etf,
    )

    print("\n--- Results ---")
    for k, v in results.items():
        print(f"  {k}: {v}")

    print("\n--- API Key Status ---")
    if FINNHUB_API_KEY:
        print("  FINNHUB_API_KEY: SET (value masked)")
    else:
        print("  FINNHUB_API_KEY: NOT SET")

    print("\n--- Rate Limiter Test ---")
    t0 = time.time()
    _rate_limit()
    t1 = time.time()
    _rate_limit()
    t2 = time.time()
    print(f"  Call 1 -> Call 2 elapsed: {t2 - t1:.3f}s (expected >= 1.0s)")
