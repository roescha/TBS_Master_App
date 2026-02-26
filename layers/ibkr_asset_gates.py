import json
import os
import argparse
import math
from ib_insync import IB, Contract, util, Stock
from datetime import datetime, timedelta
import asyncio
import time

# TBS ASSET GATES (Step 4 - Asset Permission) v8.3
# Standalone pre-gate for the 8-Step Pipeline [DOC 5 SEC 3.2 / DOC 7 STEP 4]
#
# Per-ticker checks:
#   1. IV Guard: If Implied Volatility > Historical Volatility -> LIMIT ORDERS ONLY
#   2. Dividend Lockout: If Ex-Dividend date is within 24 hours -> BLOCKED
#
# Usage:
#   ibkr_asset_gates.py --ticker TNK
#   ibkr_asset_gates.py --ticker TNK --profile SWING
#   ibkr_asset_gates.py --ticker TNK --mode LIVE


# ==============================================================================
# MAIN FUNCTION
# ==============================================================================

def run_asset_gates(ticker, profile="SWING", mode="INFO"):
    """
    Per-ticker asset permission checks per Doc 5 Sec 3.2.

    Checks:
      1. IV Guard -- compares Implied Vol vs Historical Vol from IBKR market data.
         If IV > HV: mandate LIMIT ORDERS ONLY to avoid slippage.
      2. Dividend Lockout -- checks if ex-dividend date is within 24 hours.
         If yes: new entry is BLOCKED.

    Args:
        ticker: Asset ticker (e.g. TNK, MSFT, GLEN.L)
        profile: SWING (A), TREND (B), WEALTH (C) -- reported in output
        mode: INFO (paper port 4002) or LIVE (port 4001)

    Returns: (status, diagnostic, metrics) tuple
        status:     "PASS" | "LIMIT_ONLY" | "BLOCKED" | "ERROR"
        diagnostic: Human-readable explanation
        metrics:    Dict with full audit trail
    """

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    unique_client_id = 50 + (os.getpid() % 100)  # Offset from other scripts
    port = 4002 if mode.upper() == "INFO" else 4001

    ib = IB()
    metrics = {}

    # --- PROFILE VALIDATION ---
    VALID_PROFILES = {"SWING", "TREND", "WEALTH", "A", "B", "C"}
    if profile.upper() not in VALID_PROFILES:
        return "ERROR", f"INVALID PROFILE: '{profile}'.", {}

    p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    p_code = p_mapping[profile.upper()]

    # --- TICKER ROUTING ---
    clean_ticker = ticker.upper()
    exchange, currency, p_exchange = "SMART", "USD", ""
    routing_map = {
        '.L':  {'exchange': 'SMART', 'currency': 'GBP', 'primary': 'LSE'},
        '.TO': {'exchange': 'SMART', 'currency': 'CAD', 'primary': 'TSE'},
        '.DE': {'exchange': 'IBIS',  'currency': 'EUR', 'primary': 'IBIS'},
        '.AS': {'exchange': 'AEB',   'currency': 'EUR', 'primary': 'AEB'},
        '.PA': {'exchange': 'SBF',   'currency': 'EUR', 'primary': 'SBF'},
    }
    for suffix, route in routing_map.items():
        if clean_ticker.endswith(suffix):
            clean_ticker = clean_ticker.replace(suffix, '')
            exchange, currency, p_exchange = route['exchange'], route['currency'], route['primary']
            break

    try:
        ib.connect('127.0.0.1', port, clientId=unique_client_id)

        # --- CONTRACT RESOLUTION ---
        contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)
        details = ib.reqContractDetails(contract)

        if not details:
            return "ERROR", f"No contract details found for '{clean_ticker}'.", metrics

        meta = details[0]
        contract = meta.contract
        long_name = getattr(meta, 'longName', '') or ''

        metrics["Ticker"] = clean_ticker
        metrics["Long_Name"] = long_name
        metrics["Profile"] = f"{profile.upper()} ({p_code})"

        # =================================================================
        # SWITCH TO DELAYED MARKET DATA (paper accounts)
        # Paper accounts without real-time subscriptions get Error 10089.
        # reqMarketDataType(4) = DELAYED_FROZEN (delayed + last available)
        # Live accounts with subscriptions auto-receive real-time regardless,
        # but we explicitly request type 1 (REALTIME) for clarity.
        # This must be called BEFORE any reqMktData calls.
        # =================================================================
        if mode.upper() == "LIVE":
            ib.reqMarketDataType(1)  # REALTIME (live account has subscriptions)
        else:
            ib.reqMarketDataType(4)  # DELAYED_FROZEN (paper/info fallback)

        # =================================================================
        # GATE 1: IV GUARD [Doc 5 Sec 3.2]
        # "If IBKR Right Panel shows IV% > Historical Volatility,
        #  the Operator is mandated to use LIMIT ORDERS ONLY"
        #
        # Strategy:
        #   PRIMARY: Delayed market data ticks 106 (IV) + 104 (HV)
        #   FALLBACK: Compute HV from daily historical bars (30-day
        #             annualized std dev of log returns x sqrt(252))
        #             IV still from delayed ticks if available.
        # =================================================================

        # --- PRIMARY: Delayed market data for IV and HV ---
        ib.reqMktData(contract, genericTickList="106,104", snapshot=False)

        iv_value = None
        hv_value = None
        max_wait = 8  # seconds
        poll_interval = 0.5
        elapsed = 0

        while elapsed < max_wait:
            ib.sleep(poll_interval)
            elapsed += poll_interval
            ticker_data = ib.ticker(contract)
            if ticker_data is not None:
                # Delayed ticks appear as same attributes on the Ticker object
                iv_raw = getattr(ticker_data, 'impliedVolatility', None)
                hv_raw = getattr(ticker_data, 'histVolatility', None)

                if iv_raw is not None and iv_raw > 0:
                    iv_value = iv_raw
                if hv_raw is not None and hv_raw > 0:
                    hv_value = hv_raw

                if iv_value is not None and hv_value is not None:
                    break

        ib.cancelMktData(contract)

        iv_source = "DELAYED_TICK"
        hv_source = "DELAYED_TICK"

        # --- FALLBACK: Compute HV from historical bars if tick unavailable ---
        if hv_value is None:
            try:
                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr='3 M',
                    barSizeSetting='1 day',
                    whatToShow='TRADES',
                    useRTH=True,
                    formatDate=1
                )
                if bars and len(bars) >= 20:
                    closes = [b.close for b in bars]
                    # Log returns
                    log_returns = []
                    for i in range(1, len(closes)):
                        if closes[i-1] > 0 and closes[i] > 0:
                            log_returns.append(math.log(closes[i] / closes[i-1]))

                    if len(log_returns) >= 15:
                        # Use last 30 trading days (or all available)
                        window = log_returns[-30:]
                        mean_r = sum(window) / len(window)
                        variance = sum((r - mean_r) ** 2 for r in window) / (len(window) - 1)
                        daily_vol = math.sqrt(variance)
                        hv_value = daily_vol * math.sqrt(252)  # Annualize
                        hv_source = "COMPUTED_30D"
                        metrics["HV_Computation"] = (
                            f"Computed from {len(window)} daily log returns "
                            f"(annualized: daily_vol {round(daily_vol*100,2)}% x sqrt(252))"
                        )
            except Exception as hv_err:
                metrics["HV_Fallback_Error"] = str(hv_err)

        # --- Format results ---
        iv_guard_active = False
        if iv_value is not None:
            iv_pct = round(iv_value * 100, 2)
            metrics["Implied_Volatility"] = iv_pct
            metrics["IV_Source"] = iv_source
        else:
            iv_pct = None
            metrics["Implied_Volatility"] = "UNAVAILABLE"

        if hv_value is not None:
            hv_pct = round(hv_value * 100, 2)
            metrics["Historical_Volatility"] = hv_pct
            metrics["HV_Source"] = hv_source
        else:
            hv_pct = None
            metrics["Historical_Volatility"] = "UNAVAILABLE"

        if iv_pct is not None and hv_pct is not None:
            iv_guard_active = iv_pct > hv_pct
            metrics["IV_Guard"] = iv_guard_active
            metrics["IV_HV_Spread"] = round(iv_pct - hv_pct, 2)
            if iv_guard_active:
                metrics["IV_Guard_Action"] = "LIMIT ORDERS ONLY (IV > HV)"
            else:
                metrics["IV_Guard_Action"] = "MARKET or LIMIT (IV <= HV)"
        elif iv_pct is not None and hv_pct is None:
            metrics["IV_Guard"] = "UNKNOWN"
            metrics["IV_Guard_Action"] = "CAUTION: HV unavailable -- consider LIMIT orders"
        elif iv_pct is None and hv_pct is not None:
            # IV unavailable but HV computed -- conservative: mandate LIMIT
            iv_guard_active = True  # Conservative default when IV unknown
            metrics["IV_Guard"] = True
            metrics["IV_Guard_Action"] = (
                "LIMIT ORDERS ONLY (IV unavailable, conservative default). "
                f"HV = {hv_pct}% ({hv_source})"
            )
        else:
            iv_guard_active = True  # Conservative default
            metrics["IV_Guard"] = True
            metrics["IV_Guard_Action"] = (
                "LIMIT ORDERS ONLY (IV/HV both unavailable, conservative default)"
            )

        # =================================================================
        # GATE 2: DIVIDEND LOCKOUT [Doc 5 Sec 3.2]
        # "If the Ex-Dividend date is within 24 hours, new entry is
        #  strictly BLOCKED to avoid dividend capture volatility"
        #
        # Strategy:
        #   PRIMARY: Delayed market data generic tick 456 (dividends)
        #   FALLBACK: reqFundamentalData "ReportSnapshot" XML parsing
        # =================================================================

        div_lockout = False

        # --- PRIMARY: Delayed tick 456 for dividend schedule ---
        ib.reqMktData(contract, genericTickList="456", snapshot=False)

        div_wait = 6
        div_elapsed = 0
        div_string = None

        while div_elapsed < div_wait:
            ib.sleep(poll_interval)
            div_elapsed += poll_interval
            ticker_data = ib.ticker(contract)
            if ticker_data is not None:
                div_raw = getattr(ticker_data, 'dividends', None)
                if div_raw is not None:
                    div_string = div_raw
                    break

        ib.cancelMktData(contract)

        div_parsed = False
        if div_string is not None:
            try:
                future_date = getattr(div_string, 'futureDate', None)
                future_amount = getattr(div_string, 'futureAmount', None)
                past_date = getattr(div_string, 'pastDate', None)
                past_amount = getattr(div_string, 'pastAmount', None)

                metrics["Dividend_Data_Available"] = True
                metrics["Dividend_Source"] = "DELAYED_TICK_456"

                if past_date:
                    metrics["Last_Ex_Dividend_Date"] = str(past_date)
                if past_amount is not None and past_amount > 0:
                    metrics["Last_Dividend_Amount"] = round(float(past_amount), 4)

                if future_date:
                    metrics["Next_Ex_Dividend_Date"] = str(future_date)
                    if future_amount is not None and future_amount > 0:
                        metrics["Next_Dividend_Amount"] = round(float(future_amount), 4)

                    try:
                        if isinstance(future_date, str):
                            ex_dt = datetime.strptime(future_date, "%Y-%m-%d")
                        else:
                            ex_dt = datetime.combine(future_date, datetime.min.time())
                        now = datetime.now()
                        hours_to_ex = (ex_dt - now).total_seconds() / 3600
                        metrics["Hours_to_Ex_Dividend"] = round(hours_to_ex, 1)

                        if 0 <= hours_to_ex <= 24:
                            div_lockout = True
                        elif hours_to_ex < 0:
                            metrics["Dividend_Note"] = "Next ex-date has passed; awaiting updated schedule"
                    except Exception as parse_err:
                        metrics["Dividend_Parse_Error"] = str(parse_err)
                else:
                    metrics["Next_Ex_Dividend_Date"] = "NONE_SCHEDULED"

                div_parsed = True
            except Exception as div_err:
                metrics["Dividend_Tick_Error"] = str(div_err)

        # --- FALLBACK: reqFundamentalData ReportSnapshot XML ---
        if not div_parsed:
            try:
                xml_data = ib.reqFundamentalData(contract, reportType='ReportSnapshot')
                if xml_data:
                    # Parse XML for dividend info
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(xml_data)

                    # Look for DividendData or similar elements
                    # ReportSnapshot XML structure varies, but commonly has:
                    # <Ratio FieldName="TTMDIVSHR"> for trailing 12m div/share
                    # <ForecastData> sections may have ex-date info
                    metrics["Dividend_Source"] = "FUNDAMENTAL_XML"

                    # Extract trailing dividend per share as indicator
                    for ratio in root.iter('Ratio'):
                        field = ratio.get('FieldName', '')
                        if field == 'TTMDIVSHR':
                            ttm_div = ratio.text
                            if ttm_div and float(ttm_div) > 0:
                                metrics["TTM_Dividend_Per_Share"] = round(float(ttm_div), 4)
                                metrics["Dividend_Data_Available"] = True
                                metrics["Dividend_Note"] = (
                                    "Ex-date not available from XML. "
                                    "TTM dividend data confirms this is a dividend-paying stock. "
                                    "CHECK IBKR GUI or financial calendar for upcoming ex-date."
                                )
                            break

                    if "TTM_Dividend_Per_Share" not in metrics:
                        metrics["Dividend_Data_Available"] = False
                        metrics["Dividend_Note"] = (
                            "No dividend data in fundamental snapshot. "
                            "Likely non-dividend stock or data unavailable."
                        )
                    div_parsed = True
                else:
                    metrics["Dividend_Data_Available"] = False
                    metrics["Dividend_Note"] = "No fundamental data returned by IBKR"
            except Exception as fund_err:
                metrics["Dividend_Data_Available"] = False
                metrics["Dividend_Fundamental_Error"] = str(fund_err)
                metrics["Dividend_Note"] = (
                    "Dividend data unavailable from both delayed ticks and fundamentals. "
                    "CHECK IBKR GUI or financial calendar manually."
                )

        metrics["Dividend_Lockout"] = div_lockout
        if div_lockout:
            metrics["Dividend_Lockout_Action"] = (
                f"BLOCKED: Ex-dividend date ({metrics.get('Next_Ex_Dividend_Date','N/A')}) "
                f"is within 24 hours ({metrics.get('Hours_to_Ex_Dividend','N/A')}h). "
                f"New entry strictly prohibited per Doc 5 Sec 3.2."
            )

        # =================================================================
        # FINAL VERDICT
        # =================================================================

        # Dividend lockout is the hardest gate -- BLOCKED overrides everything
        if div_lockout:
            metrics["Verdict"] = "BLOCKED"
            return (
                "BLOCKED",
                f"ASSET GATES BLOCKED: '{clean_ticker}' ex-dividend date "
                f"({metrics.get('Next_Ex_Dividend_Date','N/A')}) is within 24 hours. "
                f"New entry strictly BLOCKED per Doc 5 Sec 3.2.",
                metrics
            )

        # IV Guard mandates order type but doesn't block
        if iv_guard_active:
            if iv_pct is not None and hv_pct is not None:
                iv_msg = (
                    f"IV ({iv_pct}%) > HV ({hv_pct}%). "
                    f"Spread: +{metrics.get('IV_HV_Spread',0)}%. "
                )
            elif iv_pct is None and hv_pct is not None:
                iv_msg = (
                    f"IV unavailable (delayed ticks not returned). "
                    f"HV computed at {hv_pct}% ({hv_source}). "
                    f"Conservative default: treat as IV > HV. "
                )
            else:
                iv_msg = (
                    f"IV/HV both unavailable from delayed data. "
                    f"Conservative default: treat as IV > HV. "
                )
            metrics["Verdict"] = "LIMIT_ONLY"
            return (
                "LIMIT_ONLY",
                f"ASSET GATES LIMIT_ONLY: '{clean_ticker}' -- {iv_msg}"
                f"LIMIT ORDERS ONLY mandated per Doc 5 Sec 3.2. "
                f"Dividend lockout: clear.",
                metrics
            )

        # All clear
        metrics["Verdict"] = "PASS"
        order_note = ""
        if iv_pct is not None and hv_pct is not None:
            order_note = f" IV ({iv_pct}%) <= HV ({hv_pct}%) -- MARKET or LIMIT orders permitted."
        else:
            order_note = " IV/HV data incomplete -- recommend LIMIT orders as precaution."

        return (
            "PASS",
            f"ASSET GATES PASS: '{clean_ticker}' cleared all per-ticker gates.{order_note} "
            f"Dividend lockout: clear.",
            metrics
        )

    except Exception as e:
        import traceback
        return "ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", metrics
    finally:
        if ib.isConnected():
            ib.disconnect()


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TBS Asset Gates (Step 4) - IV Guard + Dividend Lockout per Doc 5 Sec 3.2"
    )
    parser.add_argument("--ticker", required=True,
                        help="Asset ticker (e.g. TNK, MSFT, GLEN.L)")
    parser.add_argument("--profile", default="SWING",
                        help="Trade profile: SWING (A), TREND (B), WEALTH (C)")
    parser.add_argument("--mode", default="INFO",
                        help="INFO (paper/read-only port 4002) or LIVE (port 4001)")
    args = parser.parse_args()

    VALID_PROFILES = {"SWING", "TREND", "WEALTH", "A", "B", "C"}
    if args.profile.upper() not in VALID_PROFILES:
        print(json.dumps({
            "status": "ERROR",
            "diagnostic": f"INVALID PROFILE: '{args.profile}'. "
                          f"Valid: SWING (A), TREND (B), WEALTH (C).",
            "metrics": {}
        }, indent=4))
        import sys
        sys.exit(1)

    status, diag, metrics = run_asset_gates(args.ticker, args.profile, args.mode)
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))
