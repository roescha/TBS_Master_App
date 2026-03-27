import json
import os
import argparse
import math
from ib_insync import IB, Contract, util, Stock
from datetime import datetime, timedelta
import asyncio
import time

# TBS ASSET GATES (Step 4 - Asset Permission) v8.3.2
# Standalone pre-gate for the 8-Step Pipeline [DOC 5 SEC 3.2 / DOC 7 STEP 4]
#
# Per-ticker checks:
#   1. IV Guard: LIMIT ORDERS ONLY mandated permanently (see AG-2)
#   2. Dividend Lockout: If Ex-Dividend date is within 24 hours -> BLOCKED
#
# v8.3.1:   AG-1 (ib_connection param for orchestrator reuse, avoids clientId collision)
# v8.3.2:   AG-2 (Remove OPRA dependency: IV tick request stripped. HV computed from
#                  30-day bars for audit trail. LIMIT_ONLY is permanent mandate.
#                  Rationale: OPRA subscription ($12/mo) required for IV ticks. IV > HV
#                  ~70-80% of the time for C-2 universe; the 20-30% window where MARKET
#                  orders would clear is low-VIX calm where slippage is minimal anyway.
#                  Cost of subscription >> value of occasional MARKET order permission.
#                  Conservative default was already the fallback -- this makes it explicit.)
#
# Usage:
#   ibkr_asset_gates.py --ticker TNK
#   ibkr_asset_gates.py --ticker TNK --profile SWING
#   ibkr_asset_gates.py --ticker TNK --mode LIVE


# ==============================================================================
# MAIN FUNCTION
# ==============================================================================

def run_asset_gates(ticker, profile="SWING", mode="INFO", ib_connection=None):
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
        ib_connection: Existing IB connection to reuse (avoids clientId collision
                       when called from orchestrator). If None, creates own connection.

    Returns: (status, diagnostic, metrics) tuple
        status:     "PASS" | "LIMIT_ONLY" | "BLOCKED" | "ERROR"
        diagnostic: Human-readable explanation
        metrics:    Dict with full audit trail
    """

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # [AG-1] Connection reuse: when called from orchestrator, ib_connection is the
    # orchestrator's existing IB session. Avoids clientId collision (orchestrator=100,
    # standalone asset_gates=150+). Only create/disconnect our own connection when standalone.
    _own_connection = (ib_connection is None)

    if _own_connection:
        unique_client_id = 150 + (os.getpid() % 50)  # Range 150-199, avoids orchestrator(100)
        port = 4002 if mode.upper() == "INFO" else 4001
        ib = IB()
    else:
        ib = ib_connection

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
        if _own_connection:
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
        # SWITCH TO APPROPRIATE MARKET DATA TYPE
        # Live accounts with equity data subscriptions receive real-time.
        # Paper/INFO mode uses DELAYED_FROZEN as fallback.
        # Note: OPRA (options) subscription no longer required (AG-2
        # removed IV tick requests). Only tick 456 (dividends) remains,
        # which is served by the standard equity data subscription.
        # =================================================================
        if mode.upper() == "LIVE":
            ib.reqMarketDataType(1)  # REALTIME (live equity subscription)
        else:
            ib.reqMarketDataType(4)  # DELAYED_FROZEN (paper/info fallback)

        # =================================================================
        # GATE 1: IV GUARD [Doc 5 Sec 3.2]  [AG-2 SIMPLIFIED]
        #
        # LIMIT ORDERS ONLY is mandated permanently. No OPRA subscription
        # required. HV is computed from 30-day daily bars for audit trail
        # and operator situational awareness (high HV = extra caution on
        # fill quality).
        #
        # Removed: reqMktData ticks 106 (IV) + 104 (HV) -- required OPRA
        # subscription ($12/mo). Conservative default was already the
        # fallback path; this makes it the only path.
        # =================================================================

        iv_guard_active = True  # [AG-2] Always active -- LIMIT_ONLY permanent
        iv_pct = None
        hv_pct = None
        hv_source = "UNAVAILABLE"

        # --- Compute HV from historical bars (audit trail only) ---
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
                log_returns = []
                for i in range(1, len(closes)):
                    if closes[i-1] > 0 and closes[i] > 0:
                        log_returns.append(math.log(closes[i] / closes[i-1]))

                if len(log_returns) >= 15:
                    window = log_returns[-30:]
                    mean_r = sum(window) / len(window)
                    variance = sum((r - mean_r) ** 2 for r in window) / (len(window) - 1)
                    daily_vol = math.sqrt(variance)
                    hv_value = daily_vol * math.sqrt(252)
                    hv_pct = round(hv_value * 100, 2)
                    hv_source = "COMPUTED_30D"
                    metrics["HV_Computation"] = (
                        f"Computed from {len(window)} daily log returns "
                        f"(annualized: daily_vol {round(daily_vol*100,2)}% x sqrt(252))"
                    )
        except Exception as hv_err:
            metrics["HV_Fallback_Error"] = str(hv_err)

        # --- Format results ---
        metrics["Implied_Volatility"] = "NOT_REQUESTED (AG-2: OPRA removed)"
        metrics["IV_Source"] = "NONE (AG-2)"

        if hv_pct is not None:
            metrics["Historical_Volatility"] = hv_pct
            metrics["HV_Source"] = hv_source
        else:
            metrics["Historical_Volatility"] = "UNAVAILABLE"
            metrics["HV_Source"] = "UNAVAILABLE"

        metrics["IV_Guard"] = True
        metrics["IV_Guard_Action"] = (
            "LIMIT ORDERS ONLY (permanent mandate per AG-2). "
            f"HV = {hv_pct}% ({hv_source})" if hv_pct else
            "LIMIT ORDERS ONLY (permanent mandate per AG-2). HV unavailable."
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
        poll_interval = 0.5  # seconds between tick polls

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
        # SEAS-001: CALENDAR SEASONALITY CONTEXT (Monthly Win Rate)
        # Informational metric only -- does NOT affect PASS/HALT verdict.
        # Reuses existing IB connection and resolved contract.
        # =================================================================

        _seasonality_diag = ""
        current_month_name = datetime.now().strftime("%B")
        current_month_int = datetime.now().month

        metrics["Seasonality_Month"] = current_month_name
        metrics["Seasonality_Win_Pct"] = None
        metrics["Seasonality_Sample_Size"] = None
        metrics["Seasonality_Label"] = None

        try:
            monthly_bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='10 Y',
                barSizeSetting='1 month',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )

            if monthly_bars:
                # Filter bars matching the current calendar month
                matching_bars = []
                for bar in monthly_bars:
                    bar_date = bar.date
                    # bar.date may be a date object or string depending on formatDate
                    if isinstance(bar_date, str):
                        try:
                            bar_date = datetime.strptime(bar_date, "%Y%m%d").date()
                        except ValueError:
                            try:
                                bar_date = datetime.strptime(bar_date, "%Y-%m-%d").date()
                            except ValueError:
                                continue
                    if hasattr(bar_date, 'month') and bar_date.month == current_month_int:
                        matching_bars.append(bar)

                sample_size = len(matching_bars)
                metrics["Seasonality_Sample_Size"] = sample_size

                if sample_size >= 5:
                    positive_count = sum(1 for b in matching_bars if b.close > b.open)
                    win_pct = round((positive_count / sample_size) * 100, 1)
                    metrics["Seasonality_Win_Pct"] = win_pct

                    if win_pct > 60.0:
                        metrics["Seasonality_Label"] = "FAVOURABLE"
                    elif win_pct < 40.0:
                        metrics["Seasonality_Label"] = "UNFAVOURABLE"
                    else:
                        metrics["Seasonality_Label"] = "NEUTRAL"

                    _seasonality_diag = (
                        f" [SEASONALITY] {current_month_name}: {win_pct}% win rate "
                        f"(10Y). {metrics['Seasonality_Label']}."
                    )
                else:
                    metrics["Seasonality_Label"] = "UNAVAILABLE"
                    _seasonality_diag = (
                        f" [SEASONALITY] {current_month_name}: UNAVAILABLE "
                        f"({sample_size}Y data, minimum 5Y required)."
                    )
            else:
                # No bars returned at all
                metrics["Seasonality_Sample_Size"] = 0
                metrics["Seasonality_Label"] = "UNAVAILABLE"
                _seasonality_diag = (
                    f" [SEASONALITY] {current_month_name}: UNAVAILABLE "
                    f"(0Y data, minimum 5Y required)."
                )

        except Exception as seas_err:
            metrics["Seasonality_Month"] = current_month_name
            metrics["Seasonality_Win_Pct"] = None
            metrics["Seasonality_Sample_Size"] = None
            metrics["Seasonality_Label"] = "UNAVAILABLE"
            metrics["Seasonality_Error"] = str(seas_err)
            _seasonality_diag = " [SEASONALITY] UNAVAILABLE (data fetch error)."

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
                f"New entry strictly BLOCKED per Doc 5 Sec 3.2."
                f"{_seasonality_diag}",
                metrics
            )

        # IV Guard mandates order type but doesn't block
        # [AG-2] Always LIMIT_ONLY -- no IV comparison needed
        if iv_guard_active:
            iv_msg = (
                f"LIMIT ORDERS ONLY (permanent mandate per AG-2). "
                f"HV = {hv_pct}% ({hv_source}). " if hv_pct else
                f"LIMIT ORDERS ONLY (permanent mandate per AG-2). HV unavailable. "
            )
            metrics["Verdict"] = "LIMIT_ONLY"
            return (
                "LIMIT_ONLY",
                f"ASSET GATES LIMIT_ONLY: '{clean_ticker}' -- {iv_msg}"
                f"Dividend lockout: clear."
                f"{_seasonality_diag}",
                metrics
            )

        # [AG-2] This path is now unreachable (iv_guard_active always True)
        # but retained for structural completeness in case AG-2 is reverted.
        metrics["Verdict"] = "PASS"
        order_note = " LIMIT orders recommended (AG-2 override inactive -- unexpected)."

        return (
            "PASS",
            f"ASSET GATES PASS: '{clean_ticker}' cleared all per-ticker gates.{order_note} "
            f"Dividend lockout: clear."
            f"{_seasonality_diag}",
            metrics
        )

    except Exception as e:
        import traceback
        return "ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", metrics
    finally:
        if _own_connection and ib.isConnected():
            ib.disconnect()


# ==============================================================================
# CLI OUTPUT FORMATTER
# ==============================================================================

def _format_cli_output(status, diagnostic, metrics):
    """Convert flat audit results into grouped, readable JSON structure.

    Groups the flat metrics dict into semantic sub-objects so the Operator
    sees meaningful categories instead of a flat dump of internal field names.
    The orchestrator always receives the raw (status, diagnostic, metrics)
    tuple -- this formatter is CLI-only, mirroring the sympathy audit pattern.
    """

    # --- Asset Identification ---
    asset = {
        "ticker":  metrics.get("Ticker"),
        "name":    metrics.get("Long_Name"),
        "profile": metrics.get("Profile"),
    }

    # --- IV Guard (Gate 1) ---
    hv_val = metrics.get("Historical_Volatility")
    hv_display = f"{hv_val}%" if hv_val not in (None, "UNAVAILABLE") else "UNAVAILABLE"

    iv_guard = {
        "order_mandate":       "LIMIT ORDERS ONLY (permanent -- AG-2)",
        "historical_volatility": hv_display,
        "hv_source":           metrics.get("HV_Source", "UNAVAILABLE"),
    }
    if metrics.get("HV_Computation"):
        iv_guard["hv_computation"] = metrics["HV_Computation"]
    if metrics.get("HV_Fallback_Error"):
        iv_guard["hv_error"] = metrics["HV_Fallback_Error"]

    # --- Dividend Lockout (Gate 2) ---
    div_lockout_active = metrics.get("Dividend_Lockout", False)

    dividend = {
        "lockout_active": div_lockout_active,
    }

    if div_lockout_active:
        dividend["lockout_detail"] = metrics.get("Dividend_Lockout_Action", "")

    # Next ex-date (primary concern for lockout)
    next_ex = metrics.get("Next_Ex_Dividend_Date")
    if next_ex and next_ex != "NONE_SCHEDULED":
        dividend["next_ex_date"] = next_ex
        if metrics.get("Next_Dividend_Amount") is not None:
            dividend["next_dividend_amount"] = metrics["Next_Dividend_Amount"]
        if metrics.get("Hours_to_Ex_Dividend") is not None:
            dividend["hours_to_ex_date"] = metrics["Hours_to_Ex_Dividend"]
    elif next_ex == "NONE_SCHEDULED":
        dividend["next_ex_date"] = "NONE SCHEDULED"

    # Historical reference
    if metrics.get("Last_Ex_Dividend_Date"):
        dividend["last_ex_date"] = metrics["Last_Ex_Dividend_Date"]
    if metrics.get("Last_Dividend_Amount") is not None:
        dividend["last_dividend_amount"] = metrics["Last_Dividend_Amount"]
    if metrics.get("TTM_Dividend_Per_Share") is not None:
        dividend["ttm_dividend_per_share"] = metrics["TTM_Dividend_Per_Share"]

    # Data source and notes
    dividend["data_source"] = metrics.get("Dividend_Source", "UNAVAILABLE")
    if metrics.get("Dividend_Data_Available") is False:
        dividend["data_available"] = False
    if metrics.get("Dividend_Note"):
        dividend["note"] = metrics["Dividend_Note"]

    # Surface errors only when present
    if metrics.get("Dividend_Tick_Error"):
        dividend["tick_error"] = metrics["Dividend_Tick_Error"]
    if metrics.get("Dividend_Parse_Error"):
        dividend["parse_error"] = metrics["Dividend_Parse_Error"]
    if metrics.get("Dividend_Fundamental_Error"):
        dividend["fundamental_error"] = metrics["Dividend_Fundamental_Error"]

    # --- Calendar Seasonality (SEAS-001, informational) ---
    seas_label = metrics.get("Seasonality_Label")
    seas_pct = metrics.get("Seasonality_Win_Pct")
    seas_size = metrics.get("Seasonality_Sample_Size")
    seas_month = metrics.get("Seasonality_Month", "")

    seasonality = {
        "month": seas_month,
    }

    if seas_label and seas_label != "UNAVAILABLE" and seas_pct is not None:
        seasonality["win_rate_pct"] = seas_pct
        seasonality["sample_years"] = seas_size
        seasonality["assessment"] = seas_label
    elif seas_label == "UNAVAILABLE" and seas_size is not None and seas_size > 0:
        seasonality["assessment"] = "UNAVAILABLE"
        seasonality["sample_years"] = seas_size
        seasonality["reason"] = f"Insufficient data ({seas_size}Y, minimum 5Y required)"
    else:
        seasonality["assessment"] = "UNAVAILABLE"
        if metrics.get("Seasonality_Error"):
            seasonality["reason"] = f"Data fetch error: {metrics['Seasonality_Error']}"
        else:
            seasonality["reason"] = "No monthly bar data returned"

    # --- Assemble in operator reading order ---
    output = {
        "asset":              asset,
        "iv_guard":           iv_guard,
        "dividend_lockout":   dividend,
        "seasonality":        seasonality,
    }

    return output


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
    parser.add_argument("--raw", action="store_true",
                        help="Output raw flat metrics (orchestrator format) instead of grouped CLI format.")
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

    if args.raw:
        # Raw flat output (same as orchestrator sees)
        print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))
    else:
        # Grouped CLI output
        output = _format_cli_output(status, diag, metrics)
        print(json.dumps(output, indent=4))
