#!/usr/bin/env python3
"""
finnhub_context.py -- CT-001.5 Finnhub Fallback Provider (Session A Skeleton)

CT-001 context enrichment via Finnhub deterministic fallback.
Session A scope: Infrastructure only (API key check, rate limiter, timeout,
sector median cache reader/writer). All CT-001.1/1.2/1.4 metrics return
UNAVAILABLE. Session B will implement actual metric computation.

Location: layers/finnhub_context.py (same directory as ibkr_asset_gates.py,
yahoo_fundamentals.py, etc.)

ASCII-only encoding -- no Unicode characters. Operator runs on Windows cp1252.
"""

import os
import json
import time
import datetime
import argparse

# NOTE: Do NOT import finnhub here. The finnhub-python import and
# FinnhubClient initialisation are Session B scope. Session A builds
# the infrastructure but makes no actual Finnhub API calls.
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
# SECTOR MEDIAN P/E CACHE FILE READER / WRITER
# =============================================================================

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

    Session A: Returns UNAVAILABLE for all CT-001.1/1.2/1.4 metrics.
    Session B will implement actual metric computation.

    The function still reads the sector median cache file to validate
    the cache reader infrastructure, and returns Sector_Median_PE from
    the cache if available.

    Args:
        ticker: Asset ticker (e.g., 'AAPL')
        sector_etf: Sector ETF ticker from sympathy audit (e.g., 'XLK')
        profile: 'A', 'B', or 'C'
        is_etf: True if asset is an ETF

    Returns:
        dict with CT-001 metric fields. All CT-001.1/1.2/1.4 fields are
        UNAVAILABLE in the Session A skeleton. Sector_Median_PE is
        populated from cache if available.
    """
    # Initialise all fields as UNAVAILABLE (Session A skeleton)
    result = {
        # --- CT-001.1: Earnings Revision (Session B) ---
        "EPS_Revision_Direction": "UNAVAILABLE",
        "EPS_Revision_Pct": None,
        "Revenue_Revision_Direction": "UNAVAILABLE",
        "Revenue_Revision_Pct": None,
        "EPS_Revision_Source": "NOT_IMPLEMENTED",
        "Revenue_Revision_Source": "NOT_IMPLEMENTED",
        # --- CT-001.2: Valuation (Session B) ---
        "Forward_PE": None,
        "PEG_Ratio": None,
        "PS_Ratio": None,
        "Valuation_Label": "UNAVAILABLE",
        "Sector_Median_PE": None,
        "Sector_Median_PE_Stale": False,
        "Forward_PE_Source": "NOT_IMPLEMENTED",
        "PEG_Ratio_Source": "NOT_IMPLEMENTED",
        "PS_Ratio_Source": "NOT_IMPLEMENTED",
        "Valuation_Label_Source": "NOT_IMPLEMENTED",
        # --- CT-001.4: Margin Trajectory (Session B) ---
        "Gross_Margin_Trend": "UNAVAILABLE",
        "Operating_Margin_Trend": "UNAVAILABLE",
        "Margin_Note": None,
        "Gross_Margin_Source": "NOT_IMPLEMENTED",
        "Operating_Margin_Source": "NOT_IMPLEMENTED",
        # --- Diagnostics ---
        "finnhub_diagnostic": "",
    }

    # --- API Key Check ---
    if not FINNHUB_API_KEY:
        result["finnhub_diagnostic"] = "Finnhub API key not configured"
        # Still proceed to cache read to validate infrastructure
    else:
        result["finnhub_diagnostic"] = "Finnhub skeleton -- all metrics UNAVAILABLE (Session A)"

    # --- ETF Skip ---
    if is_etf:
        result["finnhub_diagnostic"] = "ETF -- context enrichment skipped"
        return result

    # --- Sector Median Cache Read (validates infrastructure even in skeleton) ---
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
        print(f"[FINNHUB CONTEXT] WARNING: Cache processing error: {e}")
        if result["finnhub_diagnostic"]:
            result["finnhub_diagnostic"] += " | "
        result["finnhub_diagnostic"] += "cache processing error: %s" % str(e)

    return result


# =============================================================================
# CLI ENTRY POINT (standalone testing)
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CT-001.5 Finnhub Context Enrichment (Session A Skeleton)"
    )
    parser.add_argument("--ticker", required=True, help="Asset ticker (e.g. AAPL)")
    parser.add_argument("--sector-etf", default="", help="Sector ETF ticker (e.g. XLK)")
    parser.add_argument("--profile", default="B", choices=["A", "B", "C"],
                        help="Trading profile (default: B)")
    parser.add_argument("--is-etf", action="store_true", help="Flag if asset is an ETF")

    args = parser.parse_args()

    print("=" * 60)
    print("CT-001.5 Finnhub Context -- Session A Skeleton")
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
