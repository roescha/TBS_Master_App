"""
ai_institutional_context.py -- FLOW-001 + MOD-M + PMC-001 + GEX-001 Institutional Context
Sub-Phase 2B/2C: Post-engine informational overlay. Zero engine impact.

Queries Gemini 2.5 Pro with Google Search grounding for:
  - FLOW-001: Dark pool activity, block trades, sweeps, 13F changes (5-day)
  - MOD-M:   SEC Form 4 insider transactions (30-day, equities only)
  - PMC-001 Layer 2: Per-ticker overnight/pre-market context (all assets)
  - GEX-001: SPY gamma exposure flip level and regime (when current_spy_price provided)

Public interface:
  get_institutional_context(ticker, company_name, is_etf=False, current_spy_price=None) -> dict

CLI:
  python ai_institutional_context.py AAPL --company "Apple Inc."
  python ai_institutional_context.py SPY  --company "SPDR S&P 500 ETF" --etf --spy-price 510.50
  python ai_institutional_context.py AAPL --company "Apple Inc." --raw --spy-price 510.50
"""

import argparse
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client()

GEMINI_TIMEOUT = 30  # seconds, consistent with ai_event_radar.py


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

def _build_prompt(ticker: str, company_name: str, is_etf: bool = False,
                  msx_pass1: dict = None, current_spy_price: float = None) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    year = datetime.now().strftime("%Y")

    etf_note = ""
    section2 = ""
    schema_insider = ""

    if not is_etf:
        section2 = f"""
SECTION 2: INSIDER ACTIVITY (30-day lookback from {today})

Search SEC EDGAR Form 4 filings and financial news for insider
transactions (purchases and sales) by officers, directors, and
10%+ beneficial owners of {ticker} ({company_name}) within the
last 30 days.

Required search passes:
  Pass 1: "{company_name} insider buying Form 4 SEC {year}"
  Pass 2: "{company_name} insider selling stock sale {year}"

Report: number of distinct insiders buying, number selling,
approximate dollar values, and names/titles of notable filers.
Note any 10b5-1 pre-planned sales in the filing data.
A "cluster buy" = 3+ distinct insiders purchasing within the window.
"""
        schema_insider = """
  "insider_activity": {
    "buy_count_30d": <int>,
    "buy_total_value_30d": <float or null>,
    "buy_notable": "<string or null>",
    "sell_count_30d": <int>,
    "sell_total_value_30d": <float or null>,
    "sell_notable": "<string or null>",
    "bs_ratio_30d": <float 0.0-1.0 or null if zero transactions>,
    "cluster_buy": <bool>,
    "details": "<string or null>"
  }
"""
    else:
        etf_note = "\nThis asset is an ETF. Do NOT search for insider activity. Return only flow_activity and overnight_context."

    # [PMC-001] Section 3: Per-ticker overnight/pre-market context (all assets incl. ETFs)
    section3 = f"""
SECTION 3: OVERNIGHT / PRE-MARKET CONTEXT

Search for overnight and pre-market developments for
{ticker} ({company_name}) since the prior US market close.

Required search passes:
  Pass 1: "{ticker} pre-market price today {today}"
  Pass 2: "{ticker} after hours trading {today}"
  Pass 3: "{company_name} news overnight {today}"

Report: pre-market gap direction and percentage,
significant after-hours moves, and any breaking news
or analyst actions affecting the ticker overnight.

If no pre-market data or news is found, report null.
"""

    # [PMC-001] Schema extension for overnight_context (all assets)
    schema_overnight = """,
  "overnight_context": {
    "premarket_gap_pct": <float or null>,
    "premarket_gap_direction": "<UP | DOWN | FLAT | UNAVAILABLE>",
    "afterhours_notable": "<string or null>",
    "overnight_news": "<string or null>",
    "sector_commodity_note": "<string or null>",
    "catalyst_flag": <bool>
  }"""

    # [MSX-001] Section 4: Microstructure Synthesis conviction narrative
    section4 = ""
    schema_msx = ""
    if msx_pass1 and isinstance(msx_pass1, dict):
        _msx_regime = msx_pass1.get("MSX_Regime", "NEUTRAL")
        _msx_score = msx_pass1.get("MSX_Score")
        _msx_summary = msx_pass1.get("MSX_Component_Summary", {})
        _msx_support = msx_pass1.get("MSX_Support_Level")
        _msx_resist = msx_pass1.get("MSX_Resistance_Level")

        # Build component signal list for Gemini
        _comp_lines = []
        for _cname, _cdata in (_msx_summary or {}).items():
            _csig = _cdata.get("signal", "---") if isinstance(_cdata, dict) else "---"
            _cdet = _cdata.get("detail", "") if isinstance(_cdata, dict) else ""
            _comp_lines.append("  %s: %s (%s)" % (_cname, _csig, _cdet))
        _comp_block = "\n".join(_comp_lines) if _comp_lines else "  No components available."

        _levels_block = ""
        if _msx_support is not None:
            _levels_block += "  Support: $%.2f\n" % _msx_support
        if _msx_resist is not None:
            _levels_block += "  Resistance: $%.2f\n" % _msx_resist

        section4 = f"""
SECTION 4: MICROSTRUCTURE SYNTHESIS CONVICTION NOTE

Given the following microstructure component signals and regime label,
produce a 2-4 sentence plain-English note describing the microstructure
environment for {ticker}.

Do NOT use sizing language (full-size, half-size, reduce, increase).
Do NOT use verdict language (VALID, REJECT, PASS, HALT, PRE-APPROVED, WAIT).
Describe conditions only.

Regime label (rule-based): {_msx_regime}
Score: {_msx_score if _msx_score is not None else 'N/A'}

Component signals:
{_comp_block}

Key levels:
{_levels_block if _levels_block else '  Not available.'}
"""
        schema_msx = """,
  "msx_conviction_note": "<string: 2-4 sentence plain-English note describing microstructure environment>"
"""

    # [GEX-001] Section 5: SPY Gamma Flip Level (when current_spy_price provided)
    section5 = ""
    schema_gex = ""
    if current_spy_price is not None:
        section5 = f"""
SECTION 5: SPY GAMMA EXPOSURE FLIP LEVEL

Search for the current SPY / S&P 500 gamma flip level (also known as
"zero gamma level", "volatility trigger", "gamma exposure flip point",
"GEX flip"). This is the SPY price level where aggregate dealer gamma
exposure crosses from positive to negative.

Required search passes:
  Pass 1: "SPY gamma flip level today {today}"
  Pass 2: "SPY zero gamma level GEX {year}"
  Pass 3: "SpotGamma gamma flip {year}"
  Pass 4: "S&P 500 volatility trigger gamma exposure flip point {year}"

Report: the numerical SPY price level, the source of the data
(e.g., SpotGamma, Unusual Whales, financial news outlet), and the
date/time the level was reported if available.

If no reliable gamma flip level is found in search results, return
null for gamma_flip_level. Do NOT estimate or fabricate a level.
"""
        schema_gex = """,
  "gamma_flip": {{
    "gamma_flip_level": <float or null>,
    "source": "<string or null>",
    "reported_date": "<string or null>"
  }}"""

    prompt = f"""You are a financial data analyst. For {ticker} ({company_name}), search for the following data and return ONLY a JSON object with the structure specified below. No preamble, no markdown fences.{etf_note}

SECTION 1: INSTITUTIONAL FLOW ACTIVITY (5-day lookback from {today})

Search for dark pool activity, block trades, and unusual options
flow for {ticker} ({company_name}) over the last 5 trading days.

Required search passes:
  Pass 1: "{ticker} dark pool volume FINRA ATS {year}"
  Pass 2: "{ticker} block trades institutional {year}"
  Pass 3: "{ticker} unusual options sweep activity {year}"
  Pass 4: "{ticker} 13F filing institutional holdings {year}"

Report: dark pool % of total volume (and 20-day average if found),
net dark pool sentiment, block trades > $1M with direction,
bullish/bearish sweep counts and notable sweeps, and any
recent 13F position changes from institutional holders.

If data is not available for any sub-category, report UNAVAILABLE
for that sub-category. Do not fabricate data.
{section2}{section3}{section4}{section5}
Return JSON:
{{
  "flow_activity": {{
    "dark_pool_pct": <float or null>,
    "dark_pool_avg_pct": <float or null>,
    "dark_pool_sentiment": "<NET_BUYING | NET_SELLING | NEUTRAL | UNAVAILABLE>",
    "block_trades_count": <int>,
    "block_trades_notable": "<string or null>",
    "sweep_bullish_count": <int>,
    "sweep_bearish_count": <int>,
    "sweep_notable": "<string or null>",
    "whale_13f_changes": "<string or null>",
    "flow_label": "<STRONG INSTITUTIONAL BUYING | INSTITUTIONAL SELLING PRESSURE | MIXED FLOW | INSUFFICIENT DATA>",
    "details": "<string or null>"
  }}{("," + schema_insider) if not is_etf else ""}{schema_overnight}{schema_msx}{schema_gex}
}}

CRITICAL: Return ONLY the raw JSON object. No markdown, no preamble, no commentary."""

    return prompt


# ---------------------------------------------------------------------------
# Unicode-to-ASCII Sanitization (Windows cp1252 safety)
# ---------------------------------------------------------------------------

# Gemini Search grounding returns these Unicode chars in response text
_UNICODE_MAP = {
    "\u2013": "--",   # en-dash
    "\u2014": "--",   # em-dash
    "\u2018": "'",    # left single quote
    "\u2019": "'",    # right single quote
    "\u201c": '"',    # left double quote
    "\u201d": '"',    # right double quote
    "\u2026": "...",  # ellipsis
    "\u00a0": " ",    # non-breaking space
    "\u00b7": "-",    # middle dot
    "\u2022": "-",    # bullet
}


def _sanitize_ascii(obj):
    """Recursively replace common Unicode chars with ASCII equivalents."""
    if isinstance(obj, str):
        for uc, repl in _UNICODE_MAP.items():
            obj = obj.replace(uc, repl)
        # Fallback: replace any remaining non-ASCII with '?'
        obj = obj.encode("ascii", "replace").decode("ascii")
        return obj
    elif isinstance(obj, dict):
        return {k: _sanitize_ascii(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_ascii(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Belt-and-Suspenders Validation
# ---------------------------------------------------------------------------

def _validate_flow(flow: dict) -> dict:
    """Spec Section 3.4: Validate flow_label against component data."""
    label = flow.get("flow_label", "INSUFFICIENT DATA")

    dp_sent = flow.get("dark_pool_sentiment", "UNAVAILABLE")
    sweep_bull = flow.get("sweep_bullish_count") or 0
    sweep_bear = flow.get("sweep_bearish_count") or 0
    block_count = flow.get("block_trades_count") or 0
    block_notable = flow.get("block_trades_notable") or ""

    # Check if all sub-categories are unavailable/null
    all_unavail = (
        flow.get("dark_pool_pct") is None
        and dp_sent in ("UNAVAILABLE", None)
        and block_count == 0
        and sweep_bull == 0
        and sweep_bear == 0
        and flow.get("whale_13f_changes") in (None, "", "UNAVAILABLE")
    )
    if all_unavail:
        flow["flow_label"] = "INSUFFICIENT DATA"
        return flow

    # Count bullish conditions
    buy_conditions = 0
    if dp_sent == "NET_BUYING":
        buy_conditions += 1
    if sweep_bull > sweep_bear:
        buy_conditions += 1
    if block_count > 0 and "buy" in block_notable.lower():
        buy_conditions += 1

    # Count bearish conditions
    sell_conditions = 0
    if dp_sent == "NET_SELLING":
        sell_conditions += 1
    if sweep_bear > sweep_bull:
        sell_conditions += 1
    if block_count > 0 and "sell" in block_notable.lower():
        sell_conditions += 1

    # Override if label is inconsistent with components
    if label == "STRONG INSTITUTIONAL BUYING" and buy_conditions < 2:
        flow["flow_label"] = "MIXED FLOW"
    elif label == "INSTITUTIONAL SELLING PRESSURE" and sell_conditions < 2:
        flow["flow_label"] = "MIXED FLOW"

    return flow


def _validate_insider(insider: dict) -> dict:
    """Spec Section 4.4: Validate cluster_buy, ratio, and numeric fields."""
    buy_count = insider.get("buy_count_30d") or 0
    sell_count = insider.get("sell_count_30d") or 0

    # Enforce non-negative integers (safe conversion -- Gemini may return strings)
    try:
        buy_count = max(0, int(buy_count))
    except (ValueError, TypeError):
        buy_count = 0
    try:
        sell_count = max(0, int(sell_count))
    except (ValueError, TypeError):
        sell_count = 0
    insider["buy_count_30d"] = buy_count
    insider["sell_count_30d"] = sell_count

    # Enforce non-negative floats for values
    for vf in ("buy_total_value_30d", "sell_total_value_30d"):
        v = insider.get(vf)
        if v is not None:
            try:
                insider[vf] = max(0.0, float(v))
            except (ValueError, TypeError):
                insider[vf] = None

    # Cluster buy override
    expected_cluster = buy_count >= 3
    insider["cluster_buy"] = expected_cluster

    # Ratio recomputation
    total = buy_count + sell_count
    if total > 0:
        expected_ratio = round(buy_count / total, 2)
        reported_ratio = insider.get("bs_ratio_30d")
        try:
            if reported_ratio is None or abs(float(reported_ratio) - expected_ratio) > 0.01:
                insider["bs_ratio_30d"] = expected_ratio
        except (ValueError, TypeError):
            insider["bs_ratio_30d"] = expected_ratio
    else:
        insider["bs_ratio_30d"] = None

    return insider


def _validate_gex(gamma_flip_raw, source_raw, reported_date_raw,
                  current_spy_price: float) -> dict:
    """
    GEX-001 Belt-and-suspenders validation (Spec §7).
    Returns dict with all GEX_ prefixed fields.
    """
    # --- Validate gamma_flip_level is a plausible float ---
    try:
        level = float(gamma_flip_raw)
    except (ValueError, TypeError):
        return _gex_unavailable("non-numeric level")

    if level < 300.0 or level > 700.0:
        return _gex_unavailable("implausible level (%.2f)" % level)

    # --- Validate source attribution ---
    if not source_raw or not str(source_raw).strip():
        return _gex_unavailable("no source attribution")

    source = str(source_raw).strip()

    # --- Validate staleness (> 24h → UNAVAILABLE) ---
    reported_date_str = None
    if reported_date_raw and str(reported_date_raw).strip():
        reported_date_str = str(reported_date_raw).strip()
        try:
            from dateutil import parser as dateutil_parser
            reported_dt = dateutil_parser.parse(reported_date_str)
            # Make naive if needed for comparison
            now = datetime.now()
            if reported_dt.tzinfo is not None:
                from datetime import timezone
                now = datetime.now(timezone.utc)
            delta_hours = (now - reported_dt).total_seconds() / 3600.0
            if delta_hours > 24.0:
                return _gex_unavailable("stale (> 24h)")
        except Exception:
            # Unparseable date → proceed (staleness unknown, level still usable)
            pass

    # --- Compute regime ---
    regime = "POSITIVE" if current_spy_price >= level else "NEGATIVE"

    if regime == "NEGATIVE":
        note = "Negative gamma -- dealer hedging amplifies moves"
    else:
        note = "Positive gamma -- dealer hedging dampens moves"

    return {
        "GEX_Gamma_Flip": level,
        "GEX_Gamma_Regime": regime,
        "GEX_Regime_Note": note,
        "GEX_Source": source,
        "GEX_Reported_Date": reported_date_str,
        "GEX_Status": "AVAILABLE",
        "GEX_Diagnostic": None,
    }


def _gex_unavailable(diagnostic: str) -> dict:
    """Return GEX UNAVAILABLE payload with diagnostic."""
    return {
        "GEX_Gamma_Flip": None,
        "GEX_Gamma_Regime": "NEGATIVE",
        "GEX_Regime_Note": None,
        "GEX_Source": None,
        "GEX_Reported_Date": None,
        "GEX_Status": "UNAVAILABLE",
        "GEX_Diagnostic": diagnostic,
    }


# ---------------------------------------------------------------------------
# Field Mapping to Output Schema (Flow_*, Insider_*, and PMC_* prefixed fields)
# ---------------------------------------------------------------------------

def _map_to_output(flow: dict, insider: dict, is_etf: bool,
                   flow_status: str = "AVAILABLE",
                   insider_status: str = "AVAILABLE",
                   pmc: dict = None,
                   pmc_status: str = "UNAVAILABLE",
                   diagnostic: str = "",
                   msx_conviction_note: str = None,
                   gex_fields: dict = None) -> dict:
    """Map parsed Gemini response to orchestrator-compatible output dict."""
    if pmc is None:
        pmc = {}
    result = {
        "Flow_Dark_Pool_Pct": flow.get("dark_pool_pct"),
        "Flow_Dark_Pool_Avg_Pct": flow.get("dark_pool_avg_pct"),
        "Flow_Dark_Pool_Sentiment": flow.get("dark_pool_sentiment", "UNAVAILABLE"),
        "Flow_Block_Trades_Count": flow.get("block_trades_count") or 0,
        "Flow_Block_Trades_Notable": flow.get("block_trades_notable"),
        "Flow_Sweep_Bullish_Count": flow.get("sweep_bullish_count") or 0,
        "Flow_Sweep_Bearish_Count": flow.get("sweep_bearish_count") or 0,
        "Flow_Sweep_Notable": flow.get("sweep_notable"),
        "Flow_Whale_13F": flow.get("whale_13f_changes"),
        "Flow_Label": flow.get("flow_label", "INSUFFICIENT DATA"),
        "Flow_Details": flow.get("details"),
        "Flow_Status": flow_status,
    }

    if is_etf:
        result.update({
            "Insider_Buy_Count_30d": None,
            "Insider_Buy_Total_Value_30d": None,
            "Insider_Buy_Notable": None,
            "Insider_Sell_Count_30d": None,
            "Insider_Sell_Total_Value_30d": None,
            "Insider_Sell_Notable": None,
            "Insider_BS_Ratio_30d": None,
            "Insider_Cluster_Buy": None,
            "Insider_Details": None,
            "Insider_Status": "N/A",
        })
    else:
        result.update({
            "Insider_Buy_Count_30d": insider.get("buy_count_30d") or 0,
            "Insider_Buy_Total_Value_30d": insider.get("buy_total_value_30d"),
            "Insider_Buy_Notable": insider.get("buy_notable"),
            "Insider_Sell_Count_30d": insider.get("sell_count_30d") or 0,
            "Insider_Sell_Total_Value_30d": insider.get("sell_total_value_30d"),
            "Insider_Sell_Notable": insider.get("sell_notable"),
            "Insider_BS_Ratio_30d": insider.get("bs_ratio_30d"),
            "Insider_Cluster_Buy": insider.get("cluster_buy", False),
            "Insider_Details": insider.get("details"),
            "Insider_Status": insider_status,
        })

    # [PMC-001] Per-ticker overnight/pre-market context (Layer 2)
    _gap_pct_raw = pmc.get("premarket_gap_pct")
    try:
        _gap_pct = float(_gap_pct_raw) if _gap_pct_raw is not None else None
    except (ValueError, TypeError):
        _gap_pct = None
    _gap_dir = pmc.get("premarket_gap_direction") or "UNAVAILABLE"
    if isinstance(_gap_dir, str):
        _gap_dir = _gap_dir.strip().upper()
    if _gap_dir not in ("UP", "DOWN", "FLAT", "UNAVAILABLE"):
        _gap_dir = "UNAVAILABLE"

    # Catalyst flag validation: true requires non-empty overnight_news
    _catalyst = bool(pmc.get("catalyst_flag", False))
    _overnight_news = pmc.get("overnight_news")
    if _catalyst and (not _overnight_news or str(_overnight_news).strip() == ""):
        _catalyst = False

    result.update({
        "PMC_Gap_Pct": _gap_pct,
        "PMC_Gap_Direction": _gap_dir,
        "PMC_Afterhours_Notable": pmc.get("afterhours_notable"),
        "PMC_Overnight_News": _overnight_news,
        "PMC_Sector_Commodity_Note": pmc.get("sector_commodity_note"),
        "PMC_Catalyst_Flag": _catalyst,
        "PMC_Status": pmc_status,
    })

    # [MSX-001] Conviction note from Gemini Section 4
    if msx_conviction_note is not None:
        result["MSX_Gemini_Narrative"] = msx_conviction_note

    # [GEX-001] Gamma exposure fields
    if gex_fields and isinstance(gex_fields, dict):
        result.update(gex_fields)
    else:
        # Default: all GEX fields present but UNAVAILABLE
        result.update(_gex_unavailable("not requested"))

    if diagnostic:
        result["Institutional_Diagnostic"] = diagnostic

    return result


# ---------------------------------------------------------------------------
# Main Public Interface
# ---------------------------------------------------------------------------

def get_institutional_context(ticker: str, company_name: str,
                              is_etf: bool = False,
                              msx_pass1: dict = None,
                              current_spy_price: float = None) -> dict:
    """
    Query Gemini Search grounding for institutional flow + insider activity + overnight context.
    Returns dict with all Flow_*, Insider_*, and PMC_* prefixed fields.
    Pipeline-safe: never raises. Returns UNAVAILABLE on any failure.
    """
    # Guard: API key
    if not os.environ.get("GEMINI_API_KEY"):
        return _map_to_output(
            {}, {}, is_etf,
            flow_status="UNAVAILABLE",
            insider_status="UNAVAILABLE" if not is_etf else "N/A",
            diagnostic="GEMINI_API_KEY not set."
        )

    try:
        prompt = _build_prompt(ticker, company_name, is_etf, msx_pass1=msx_pass1,
                              current_spy_price=current_spy_price)

        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
            )
        )

        raw_text = response.text.strip()
        # Strip markdown fences if Gemini wraps response
        if raw_text.startswith('```json'):
            raw_text = raw_text.replace('```json', '').replace('```', '').strip()
        elif raw_text.startswith('```'):
            raw_text = raw_text.replace('```', '').strip()

        result = json.loads(raw_text)

        # Scrub Unicode chars from Gemini response (Windows cp1252 safety)
        result = _sanitize_ascii(result)

        # --- Parse flow_activity ---
        flow = result.get("flow_activity")
        if not flow or not isinstance(flow, dict):
            flow = {}
            flow_status = "UNAVAILABLE"
            flow_diag = "JSON parse error: flow_activity missing or malformed."
        else:
            flow = _validate_flow(flow)
            flow_status = "AVAILABLE"
            flow_diag = ""

        # --- Parse insider_activity ---
        if is_etf:
            insider = {}
            insider_status = "N/A"
        else:
            try:
                insider = result.get("insider_activity")
                if not insider or not isinstance(insider, dict):
                    insider = {}
                    insider_status = "UNAVAILABLE"
                    flow_diag = (flow_diag + " insider_activity missing or malformed.").strip()
                else:
                    insider = _validate_insider(insider)
                    insider_status = "AVAILABLE"
            except Exception as _ins_err:
                insider = {}
                insider_status = "UNAVAILABLE"
                flow_diag = (flow_diag + " insider validation error: %s" % str(_ins_err)[:60]).strip()

        # [PMC-001] --- Parse overnight_context (Layer 2) ---
        # Independent try/except per FLOW001-BUG-3 pattern:
        # PMC parse failure does NOT affect flow_status or insider_status.
        pmc = {}
        pmc_status = "UNAVAILABLE"
        try:
            _oc_raw = result.get("overnight_context")
            if _oc_raw and isinstance(_oc_raw, dict):
                pmc = _oc_raw
                pmc_status = "AVAILABLE"
            else:
                flow_diag = (flow_diag + " overnight_context missing or malformed.").strip()
        except Exception as _pmc_err:
            flow_diag = (flow_diag + " overnight_context parse error: %s" % str(_pmc_err)[:60]).strip()

        # [MSX-001] --- Parse msx_conviction_note (Section 4) ---
        # Independent try/except: Section 4 parse failure does NOT affect Sections 1-3.
        _msx_note = None
        try:
            _msx_raw = result.get("msx_conviction_note")
            if _msx_raw and isinstance(_msx_raw, str) and _msx_raw.strip():
                _msx_note = _sanitize_ascii(_msx_raw.strip())
        except Exception as _msx_err:
            flow_diag = (flow_diag + " msx_conviction_note parse error: %s" % str(_msx_err)[:60]).strip()

        # [GEX-001] --- Parse gamma_flip (Section 5) ---
        # Independent try/except: Section 5 parse failure does NOT affect Sections 1-4.
        _gex_fields = None
        try:
            if current_spy_price is not None:
                _gf_raw = result.get("gamma_flip")
                if _gf_raw and isinstance(_gf_raw, dict):
                    _gex_fields = _validate_gex(
                        gamma_flip_raw=_gf_raw.get("gamma_flip_level"),
                        source_raw=_gf_raw.get("source"),
                        reported_date_raw=_gf_raw.get("reported_date"),
                        current_spy_price=current_spy_price
                    )
                    _gex_fields = _sanitize_ascii(_gex_fields)
                else:
                    _gex_fields = _gex_unavailable("gamma_flip missing or malformed in Gemini response")
            else:
                _gex_fields = _gex_unavailable("current_spy_price not provided")
        except Exception as _gex_err:
            _gex_fields = _gex_unavailable("parse error: %s" % str(_gex_err)[:60])

        return _map_to_output(
            flow, insider, is_etf,
            flow_status=flow_status,
            insider_status=insider_status,
            pmc=pmc,
            pmc_status=pmc_status,
            diagnostic=flow_diag,
            msx_conviction_note=_msx_note,
            gex_fields=_gex_fields
        )

    except json.JSONDecodeError as je:
        return _map_to_output(
            {}, {}, is_etf,
            flow_status="UNAVAILABLE",
            insider_status="UNAVAILABLE" if not is_etf else "N/A",
            pmc={},
            pmc_status="UNAVAILABLE",
            diagnostic="JSON parse error: %s" % str(je)[:80],
            gex_fields=_gex_unavailable("Gemini JSON parse error")
        )
    except Exception as e:
        return _map_to_output(
            {}, {}, is_etf,
            flow_status="UNAVAILABLE",
            insider_status="UNAVAILABLE" if not is_etf else "N/A",
            pmc={},
            pmc_status="UNAVAILABLE",
            diagnostic="Exception: %s" % str(e)[:80],
            gex_fields=_gex_unavailable("Gemini call failed: %s" % str(e)[:40])
        )


# ---------------------------------------------------------------------------
# Dashboard Output Formatting (CLI)
# ---------------------------------------------------------------------------

def _print_dashboard(ctx: dict, ticker: str, is_etf: bool):
    """Print grouped INSTITUTIONAL CONTEXT dashboard section."""
    print("\n   ==================================================================")
    print("   INSTITUTIONAL CONTEXT")
    print("   ==================================================================")

    flow_status = ctx.get("Flow_Status", "UNAVAILABLE")
    insider_status = ctx.get("Insider_Status", "UNAVAILABLE")

    # Check if both sections are unavailable
    if flow_status == "UNAVAILABLE" and insider_status in ("UNAVAILABLE", "N/A"):
        diag = ctx.get("Institutional_Diagnostic", "Gemini Search error")
        print("   UNAVAILABLE (%s). Pipeline unaffected." % diag)
        return

    # --- FLOW ACTIVITY ---
    if flow_status == "AVAILABLE":
        print("   --- FLOW ACTIVITY (5-DAY) ---")

        dp_pct = ctx.get("Flow_Dark_Pool_Pct")
        dp_avg = ctx.get("Flow_Dark_Pool_Avg_Pct")
        dp_sent = ctx.get("Flow_Dark_Pool_Sentiment", "UNAVAILABLE")
        if dp_pct is not None:
            dp_line = "   Dark Pool:    %.1f%% of volume" % dp_pct
            if dp_avg is not None:
                dp_line += " (avg %.1f%%)" % dp_avg
            dp_line += " | %s" % dp_sent
            print(dp_line)
        else:
            print("   Dark Pool:    UNAVAILABLE")

        bt_count = ctx.get("Flow_Block_Trades_Count", 0)
        bt_notable = ctx.get("Flow_Block_Trades_Notable")
        if bt_count > 0:
            bt_line = "   Block Trades: %d trades > $1M" % bt_count
            if bt_notable:
                bt_line += " | %s" % bt_notable
            print(bt_line)
        else:
            print("   Block Trades: None reported")

        sw_bull = ctx.get("Flow_Sweep_Bullish_Count", 0)
        sw_bear = ctx.get("Flow_Sweep_Bearish_Count", 0)
        sw_notable = ctx.get("Flow_Sweep_Notable")
        if sw_bull > 0 or sw_bear > 0:
            sw_line = "   Sweeps:       %d bullish / %d bearish" % (sw_bull, sw_bear)
            if sw_notable:
                sw_line += " | %s" % sw_notable
            print(sw_line)
        else:
            print("   Sweeps:       None reported")

        whale = ctx.get("Flow_Whale_13F")
        if whale and whale != "UNAVAILABLE":
            print("   13F Changes:  %s" % whale)
        else:
            print("   13F Changes:  UNAVAILABLE")

        flow_label = ctx.get("Flow_Label", "INSUFFICIENT DATA")
        print("   FLOW SIGNAL:  %s" % flow_label)
        print("   SOURCE:       Gemini Search (FINRA ATS, SEC EDGAR, financial news)")
    else:
        print("   --- FLOW ACTIVITY: INSUFFICIENT DATA ---")
        print("   SOURCE:       Gemini Search (data not available for this ticker)")

    # --- INSIDER ACTIVITY (non-ETF only) ---
    if not is_etf:
        if insider_status == "AVAILABLE":
            buy_count = ctx.get("Insider_Buy_Count_30d", 0)
            sell_count = ctx.get("Insider_Sell_Count_30d", 0)

            if buy_count == 0 and sell_count == 0:
                print("   --- INSIDER ACTIVITY: No Form 4 filings in 30-day window. ---")
            else:
                print("   --- INSIDER ACTIVITY (30-DAY) ---")

                buy_val = ctx.get("Insider_Buy_Total_Value_30d")
                buy_notable = ctx.get("Insider_Buy_Notable")
                buy_line = "   BUYS:         %d insiders" % buy_count
                if buy_val is not None:
                    buy_line += " | $%s total" % _fmt_currency(buy_val)
                if buy_notable:
                    buy_line += " | %s" % buy_notable
                print(buy_line)

                sell_val = ctx.get("Insider_Sell_Total_Value_30d")
                sell_notable = ctx.get("Insider_Sell_Notable")
                sell_line = "   SELLS:        %d insiders" % sell_count
                if sell_val is not None:
                    sell_line += " | $%s total" % _fmt_currency(sell_val)
                if sell_notable:
                    sell_line += " | %s" % sell_notable
                print(sell_line)

                bs_ratio = ctx.get("Insider_BS_Ratio_30d")
                cluster = ctx.get("Insider_Cluster_Buy", False)
                ratio_str = "%.2f" % bs_ratio if bs_ratio is not None else "N/A"
                weight_label = "buy-weighted" if bs_ratio is not None and bs_ratio > 0.5 else ("sell-weighted" if bs_ratio is not None and bs_ratio < 0.5 else "neutral")
                cluster_str = "YES" if cluster else "NO"
                print("   RATIO:        %s (%s) | CLUSTER BUY: %s" % (ratio_str, weight_label, cluster_str))

                print("   SOURCE:       SEC EDGAR Form 4 via Gemini Search")
        elif insider_status == "UNAVAILABLE":
            diag = ctx.get("Institutional_Diagnostic", "Gemini Search error")
            print("   --- INSIDER ACTIVITY: UNAVAILABLE (%s) ---" % diag)

    # [PMC-001] --- PRE-MARKET CONTEXT sub-section (all assets) ---
    _pmc_status = ctx.get("PMC_Status", "UNAVAILABLE")
    if _pmc_status == "UNAVAILABLE":
        print("   --- PRE-MARKET CONTEXT: UNAVAILABLE (parse error) ---")
    elif _pmc_status == "AVAILABLE":
        _pmc_gap = ctx.get("PMC_Gap_Pct")
        _pmc_dir = ctx.get("PMC_Gap_Direction", "UNAVAILABLE")
        _pmc_ah = ctx.get("PMC_Afterhours_Notable")
        _pmc_news = ctx.get("PMC_Overnight_News")
        _pmc_sect = ctx.get("PMC_Sector_Commodity_Note")
        _pmc_cat = ctx.get("PMC_Catalyst_Flag", False)

        # Check if all data fields are null/empty
        _all_empty = (
            _pmc_gap is None
            and _pmc_dir in ("UNAVAILABLE", "FLAT")
            and not _pmc_ah
            and not _pmc_news
            and not _pmc_sect
            and not _pmc_cat
        )
        if _all_empty:
            print("   --- PRE-MARKET CONTEXT: No significant overnight activity. ---")
        else:
            print("   --- PRE-MARKET CONTEXT ---")
            # Gap line
            _cat_tag = " [CATALYST]" if _pmc_cat else ""
            if _pmc_gap is not None:
                print("   Gap:          %+.1f%% (%s)%s" % (_pmc_gap, _pmc_dir, _cat_tag))
            elif _cat_tag:
                print("   Gap:          %s%s" % (_pmc_dir, _cat_tag))
            # After-hours
            if _pmc_ah:
                print("   After-Hours:  %s" % _pmc_ah)
            # Overnight news
            if _pmc_news:
                print("   Overnight:    %s" % _pmc_news)
            # Sector commodity
            if _pmc_sect:
                print("   Sector:       %s" % _pmc_sect)

    # [GEX-001] --- GAMMA EXPOSURE sub-section ---
    _gex_status = ctx.get("GEX_Status", "UNAVAILABLE")
    if _gex_status == "AVAILABLE":
        _gex_flip = ctx.get("GEX_Gamma_Flip")
        _gex_regime = ctx.get("GEX_Gamma_Regime", "NEGATIVE")
        _gex_source = ctx.get("GEX_Source", "")
        _regime_label = "NEGATIVE GAMMA" if _gex_regime == "NEGATIVE" else "POSITIVE GAMMA"
        print("   GEX:          SPY Gamma Flip $%.2f | %s | Source: %s" % (
            _gex_flip, _regime_label, _gex_source))
    elif _gex_status == "UNAVAILABLE":
        _gex_diag = ctx.get("GEX_Diagnostic", "no reliable level found")
        print("   GEX:          UNAVAILABLE (%s)" % _gex_diag)


def _fmt_currency(val):
    """Format a dollar value for display (e.g., 2300000 -> 2.3M)."""
    if val is None:
        return "N/A"
    if val >= 1_000_000:
        return "%.1fM" % (val / 1_000_000)
    elif val >= 1_000:
        return "%sK" % int(val / 1_000)
    else:
        return "%d" % int(val)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FLOW-001 + MOD-M + PMC-001: Institutional Context (Post-Engine Overlay)"
    )
    parser.add_argument("ticker", type=str, help="Stock ticker symbol")
    parser.add_argument("--company", type=str, required=True,
                        help="Full company name for Gemini search context")
    parser.add_argument("--etf", action="store_true", default=False,
                        help="ETF mode: skip MOD-M insider activity")
    parser.add_argument("--raw", action="store_true", default=False,
                        help="Output raw JSON (orchestrator-compatible)")
    parser.add_argument("--spy-price", type=float, default=None,
                        help="Current SPY price for GEX-001 gamma flip regime computation")

    args = parser.parse_args()

    ctx = get_institutional_context(
        ticker=args.ticker.upper(),
        company_name=args.company,
        is_etf=args.etf,
        current_spy_price=args.spy_price
    )

    if args.raw:
        print(json.dumps(ctx, indent=2, default=str))
    else:
        print("\n   FLOW-001 + MOD-M + PMC-001 + GEX-001 | %s | %s%s" % (
            args.ticker.upper(), args.company,
            " [ETF]" if args.etf else ""
        ))
        _print_dashboard(ctx, args.ticker.upper(), args.etf)
