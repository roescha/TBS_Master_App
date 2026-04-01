"""
ai_institutional_context.py -- FLOW-001 + MOD-M Institutional Context
Sub-Phase 2B: Post-engine informational overlay. Zero engine impact.

Queries Gemini 2.5 Flash with Google Search grounding for:
  - FLOW-001: Dark pool activity, block trades, sweeps, 13F changes (5-day)
  - MOD-M:   SEC Form 4 insider transactions (30-day, equities only)

Public interface:
  get_institutional_context(ticker, company_name, is_etf=False) -> dict

CLI:
  python ai_institutional_context.py AAPL --company "Apple Inc."
  python ai_institutional_context.py SPY  --company "SPDR S&P 500 ETF" --etf
  python ai_institutional_context.py AAPL --company "Apple Inc." --raw
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

def _build_prompt(ticker: str, company_name: str, is_etf: bool = False) -> str:
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
        etf_note = "\nThis asset is an ETF. Do NOT search for insider activity. Return only flow_activity."

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
{section2}
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
  }}{("," + schema_insider) if not is_etf else ""}
}}

CRITICAL: Return ONLY the raw JSON object. No markdown, no preamble, no commentary."""

    return prompt


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


# ---------------------------------------------------------------------------
# Field Mapping to Output Schema (Flow_* and Insider_* prefixed fields)
# ---------------------------------------------------------------------------

def _map_to_output(flow: dict, insider: dict, is_etf: bool,
                   flow_status: str = "AVAILABLE",
                   insider_status: str = "AVAILABLE",
                   diagnostic: str = "") -> dict:
    """Map parsed Gemini response to orchestrator-compatible output dict."""
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

    if diagnostic:
        result["Institutional_Diagnostic"] = diagnostic

    return result


# ---------------------------------------------------------------------------
# Main Public Interface
# ---------------------------------------------------------------------------

def get_institutional_context(ticker: str, company_name: str,
                              is_etf: bool = False) -> dict:
    """
    Query Gemini Search grounding for institutional flow + insider activity.
    Returns dict with all Flow_* and Insider_* prefixed fields.
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
        prompt = _build_prompt(ticker, company_name, is_etf)

        response = client.models.generate_content(
            model='gemini-2.5-flash',
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

        return _map_to_output(
            flow, insider, is_etf,
            flow_status=flow_status,
            insider_status=insider_status,
            diagnostic=flow_diag
        )

    except json.JSONDecodeError as je:
        return _map_to_output(
            {}, {}, is_etf,
            flow_status="UNAVAILABLE",
            insider_status="UNAVAILABLE" if not is_etf else "N/A",
            diagnostic="JSON parse error: %s" % str(je)[:80]
        )
    except Exception as e:
        return _map_to_output(
            {}, {}, is_etf,
            flow_status="UNAVAILABLE",
            insider_status="UNAVAILABLE" if not is_etf else "N/A",
            diagnostic="Exception: %s" % str(e)[:80]
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
        description="FLOW-001 + MOD-M: Institutional Context (Post-Engine Overlay)"
    )
    parser.add_argument("ticker", type=str, help="Stock ticker symbol")
    parser.add_argument("--company", type=str, required=True,
                        help="Full company name for Gemini search context")
    parser.add_argument("--etf", action="store_true", default=False,
                        help="ETF mode: skip MOD-M insider activity")
    parser.add_argument("--raw", action="store_true", default=False,
                        help="Output raw JSON (orchestrator-compatible)")

    args = parser.parse_args()

    ctx = get_institutional_context(
        ticker=args.ticker.upper(),
        company_name=args.company,
        is_etf=args.etf
    )

    if args.raw:
        print(json.dumps(ctx, indent=2, default=str))
    else:
        print("\n   FLOW-001 + MOD-M | %s | %s%s" % (
            args.ticker.upper(), args.company,
            " [ETF]" if args.etf else ""
        ))
        _print_dashboard(ctx, args.ticker.upper(), args.etf)
