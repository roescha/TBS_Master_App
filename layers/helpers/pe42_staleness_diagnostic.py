#!/usr/bin/env python3
"""
PE-42 Phase 1 Diagnostic -- IBKR reqHistoricalData Staleness Audit
=================================================================

PURPOSE:
  Diagnose stale bar behaviour on NASDAQ vs NYSE data farms after market close.
  Tests Option A (explicit endDateTime) and Option D (reqMktData snapshot)
  as potential fixes. Produces a structured report for Operator review.

WHEN TO RUN:
  After US market close (16:00 ET). Ideally run at multiple intervals:
    - close+5min  (16:05 ET)
    - close+15min (16:15 ET)
    - close+30min (16:30 ET)
    - close+60min (17:00 ET)
  Each run is timestamped. Compare across runs to determine the
  NASDAQ consolidation window.

USAGE:
  python pe42_staleness_diagnostic.py [--port 4002] [--profile B]

  --port    IBKR gateway port (default: 4002 = paper/INFO, 4001 = LIVE)
  --profile Which TBS profile to test (A=hourly, B=daily, C=weekly; default: B)
            Profile B (daily) is the primary concern -- end-of-day scans use daily bars.

REQUIREMENTS:
  - IBKR gateway running (TWS or IB Gateway)
  - ib_insync, pandas installed

OUTPUT:
  Prints structured diagnostic report to stdout.
  Save to file: python pe42_staleness_diagnostic.py > pe42_diag_$(date +%H%M).txt

ORIGIN: PE-42 (Bug Register), Session 52
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from ib_insync import IB, Stock, Contract, util

# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

# Test tickers: 3 NASDAQ, 3 NYSE, 1 LSE, 1 TSX (scope mapping)
TEST_TICKERS = {
    "NASDAQ": [
        {"ticker": "AAPL",  "exchange": "SMART", "currency": "USD", "primary": ""},
        {"ticker": "MSFT",  "exchange": "SMART", "currency": "USD", "primary": ""},
        {"ticker": "AMZN",  "exchange": "SMART", "currency": "USD", "primary": ""},
        {"ticker": "KLAC",  "exchange": "SMART", "currency": "USD", "primary": ""},  # PE-42 original evidence
        {"ticker": "APP",   "exchange": "SMART", "currency": "USD", "primary": ""},  # PE-42 original evidence
        {"ticker": "AMAT",  "exchange": "SMART", "currency": "USD", "primary": ""},  # PE-42 original evidence
    ],
    "NYSE": [
        {"ticker": "JPM",   "exchange": "SMART", "currency": "USD", "primary": ""},
        {"ticker": "XOM",   "exchange": "SMART", "currency": "USD", "primary": ""},
        {"ticker": "GS",    "exchange": "SMART", "currency": "USD", "primary": ""},
    ],
    "LSE": [
        {"ticker": "SHEL",  "exchange": "SMART", "currency": "GBP", "primary": "LSE"},
    ],
    "TSX": [
        {"ticker": "RY",    "exchange": "SMART", "currency": "CAD", "primary": "TSE"},
    ],
}

# Profile -> resolution/duration mapping (mirrors data.py::_build_config)
PROFILE_MAP = {
    "A": {"tf_res": "1 hour",  "tf_dur": "3 M",   "ctx_res": "1 day",   "ctx_dur": "12 M"},
    "B": {"tf_res": "1 day",   "tf_dur": "2 Y",   "ctx_res": "1 week",  "ctx_dur": "5 Y"},
    "C": {"tf_res": "1 week",  "tf_dur": "10 Y",  "ctx_res": "1 month", "ctx_dur": "20 Y"},
}


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def get_session_close_time(exchange_group: str) -> str:
    """Return expected session close time for the exchange group."""
    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)

    if exchange_group in ("NASDAQ", "NYSE"):
        close_time = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        return close_time.strftime("%Y-%m-%d %H:%M:%S ET")
    elif exchange_group == "LSE":
        london = ZoneInfo("Europe/London")
        now_london = datetime.now(london)
        close_time = now_london.replace(hour=16, minute=30, second=0, microsecond=0)
        return close_time.strftime("%Y-%m-%d %H:%M:%S UK")
    elif exchange_group == "TSX":
        close_time = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        return close_time.strftime("%Y-%m-%d %H:%M:%S ET")
    return "UNKNOWN"


def format_bar(bar_row, label: str) -> str:
    """Format a single bar's OHLCV for display."""
    if bar_row is None:
        return f"  {label}: NO DATA"
    return (
        f"  {label}: "
        f"Date={bar_row.name}  "
        f"O={bar_row.get('open', 'N/A'):.2f}  "
        f"H={bar_row.get('high', 'N/A'):.2f}  "
        f"L={bar_row.get('low', 'N/A'):.2f}  "
        f"C={bar_row.get('close', 'N/A'):.2f}  "
        f"V={int(bar_row.get('volume', 0)):,}"
    )


def fetch_bars(ib, contract, end_dt, duration, resolution):
    """Fetch historical bars and return as DataFrame or None."""
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_dt,
            durationStr=duration,
            barSizeSetting=resolution,
            whatToShow='TRADES',
            useRTH=True
        )
        if not bars:
            return None
        df = util.df(bars)
        df.set_index('date', inplace=True)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        print(f"    [ERROR] reqHistoricalData failed: {e}")
        return None


def fetch_mkt_snapshot(ib, contract, timeout=8):
    """
    Fetch a market data snapshot via reqMktData.
    Returns (last_price, close_price) or (None, None).
    """
    try:
        ib.reqMktData(contract, genericTickList="", snapshot=False, regulatorySnapshot=False)
        elapsed = 0
        interval = 0.5
        last_price = None
        close_price = None

        while elapsed < timeout:
            ib.sleep(interval)
            elapsed += interval
            ticker_data = ib.ticker(contract)
            if ticker_data is not None:
                # .last = last trade price; .close = previous official close
                lp = getattr(ticker_data, 'last', None)
                cp = getattr(ticker_data, 'close', None)
                if lp is not None and lp > 0:
                    last_price = float(lp)
                if cp is not None and cp > 0:
                    close_price = float(cp)
                if last_price is not None or close_price is not None:
                    break

        ib.cancelMktData(contract)
        return last_price, close_price
    except Exception as e:
        print(f"    [ERROR] reqMktData failed: {e}")
        return None, None


# ---------------------------------------------------------------------
# MAIN DIAGNOSTIC
# ---------------------------------------------------------------------

def run_diagnostic(port: int, profile: str):
    et = ZoneInfo("America/New_York")
    run_time = datetime.now(et)
    cfg = PROFILE_MAP[profile]

    print("=" * 80)
    print(f"PE-42 STALENESS DIAGNOSTIC -- Phase 1")
    print(f"=" * 80)
    print(f"Run Time:    {run_time.strftime('%Y-%m-%d %H:%M:%S ET')}")
    print(f"UTC Time:    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Profile:     {profile} ({cfg['tf_res']} primary, {cfg['ctx_res']} context)")
    print(f"Port:        {port}")
    print(f"Primary:     dur={cfg['tf_dur']} res={cfg['tf_res']}")
    print(f"Context:     dur={cfg['ctx_dur']} res={cfg['ctx_res']}")
    print()

    # --- Connect ---
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    unique_client_id = 200 + (os.getpid() % 50)  # Avoid collision with engine (25-124)
    ib = IB()

    try:
        ib.connect('127.0.0.1', port, clientId=unique_client_id)
        ib.reqMarketDataType(1)
    except Exception as e:
        print(f"[FATAL] Cannot connect to IBKR on port {port}: {e}")
        sys.exit(1)

    print(f"Connected (clientId={unique_client_id})")
    print()

    # --- Build explicit endDateTime for Option A test ---
    # Use current wall-clock time formatted for IBKR
    now_utc = datetime.now(timezone.utc)
    explicit_end_dt = now_utc.strftime("%Y%m%d %H:%M:%S") + " UTC"

    results = []

    for exchange_group, tickers in TEST_TICKERS.items():
        expected_close = get_session_close_time(exchange_group)

        for t in tickers:
            ticker = t["ticker"]
            contract = Stock(
                ticker, t["exchange"], t["currency"],
                primaryExchange=t["primary"]
            )

            # Qualify the contract
            try:
                details = ib.reqContractDetails(contract)
                if details:
                    contract = details[0].contract
                    actual_exchange = getattr(contract, 'primaryExchange', '') or 'UNKNOWN'
                else:
                    print(f"  [{ticker}] Contract qualification failed -- skipping")
                    continue
            except Exception as e:
                print(f"  [{ticker}] Contract error: {e} -- skipping")
                continue

            print(f"--- {ticker} ({exchange_group} -> {actual_exchange}) ---")

            result = {
                "ticker": ticker,
                "exchange_group": exchange_group,
                "actual_exchange": actual_exchange,
                "expected_close": expected_close,
            }

            # -- TEST 1: Standard fetch (endDateTime='') -- mirrors engine --
            print(f"  [Test 1] Standard fetch (endDateTime='')")
            df_standard = fetch_bars(ib, contract, '', cfg['tf_dur'], cfg['tf_res'])
            if df_standard is not None and len(df_standard) > 0:
                last_bar = df_standard.iloc[-1]
                result["std_last_date"] = str(df_standard.index[-1])
                result["std_close"] = float(last_bar['close'])
                result["std_bars"] = len(df_standard)
                print(format_bar(last_bar, "Last bar"))
            else:
                result["std_last_date"] = "NO DATA"
                result["std_close"] = None
                result["std_bars"] = 0
                print("  Last bar: NO DATA")

            # -- TEST 2: Option A (explicit endDateTime) --
            print(f"  [Test 2] Option A (endDateTime='{explicit_end_dt}')")
            df_explicit = fetch_bars(ib, contract, explicit_end_dt, cfg['tf_dur'], cfg['tf_res'])
            if df_explicit is not None and len(df_explicit) > 0:
                last_bar_e = df_explicit.iloc[-1]
                result["exp_last_date"] = str(df_explicit.index[-1])
                result["exp_close"] = float(last_bar_e['close'])
                result["exp_bars"] = len(df_explicit)
                print(format_bar(last_bar_e, "Last bar"))

                # Compare with standard
                if result["std_close"] is not None:
                    delta = result["exp_close"] - result["std_close"]
                    if abs(delta) > 0.01:
                        print(f"  *** PRICE DIFFERS: D={delta:+.2f} (Option A returned different close)")
                    else:
                        print(f"  Prices match (D={delta:+.4f})")
                    result["option_a_delta"] = delta
                else:
                    result["option_a_delta"] = None
            else:
                result["exp_last_date"] = "NO DATA"
                result["exp_close"] = None
                result["exp_bars"] = 0
                result["option_a_delta"] = None
                print("  Last bar: NO DATA")

            # -- TEST 3: Context frame standard fetch --
            print(f"  [Test 3] Context fetch (endDateTime='', {cfg['ctx_res']})")
            df_ctx = fetch_bars(ib, contract, '', cfg['ctx_dur'], cfg['ctx_res'])
            if df_ctx is not None and len(df_ctx) > 0:
                last_ctx = df_ctx.iloc[-1]
                result["ctx_last_date"] = str(df_ctx.index[-1])
                result["ctx_close"] = float(last_ctx['close'])
                print(format_bar(last_ctx, "Last bar"))
            else:
                result["ctx_last_date"] = "NO DATA"
                result["ctx_close"] = None
                print("  Last bar: NO DATA")

            # -- TEST 4: Option D (reqMktData snapshot) --
            print(f"  [Test 4] Option D (reqMktData snapshot)")
            mkt_last, mkt_close = fetch_mkt_snapshot(ib, contract)
            result["mkt_last"] = mkt_last
            result["mkt_close"] = mkt_close
            print(f"  last={mkt_last}  close={mkt_close}")

            if mkt_close is not None and result["std_close"] is not None:
                mkt_delta = mkt_close - result["std_close"]
                if abs(mkt_delta) > 0.01:
                    print(f"  *** VERIFICATION DIVERGENCE: historical bar close={result['std_close']:.2f}, "
                          f"mktData close={mkt_close:.2f}, D={mkt_delta:+.2f}")
                else:
                    print(f"  Consistent (D={mkt_delta:+.4f})")
                result["mkt_delta"] = mkt_delta
            else:
                result["mkt_delta"] = None

            results.append(result)
            print()

    # --- Disconnect ---
    if ib.isConnected():
        ib.disconnect()

    # -----------------------------------------------------------------
    # SUMMARY REPORT
    # -----------------------------------------------------------------
    print()
    print("=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)
    print()

    print(f"{'Ticker':<8} {'Exchange':<10} {'Std Close':>10} {'OptA Close':>11} {'OptA D':>8} "
          f"{'MktData':>10} {'MktD D':>8} {'Std Last Bar Date':<22} {'Status'}")
    print("-" * 110)

    stale_count = 0
    option_a_fixes = 0
    option_d_detects = 0

    for r in results:
        std_c = f"{r['std_close']:.2f}" if r['std_close'] else "N/A"
        exp_c = f"{r['exp_close']:.2f}" if r['exp_close'] else "N/A"
        opt_a_d = f"{r['option_a_delta']:+.2f}" if r.get('option_a_delta') is not None else "N/A"
        mkt_c = f"{r['mkt_close']:.2f}" if r.get('mkt_close') else "N/A"
        mkt_d = f"{r['mkt_delta']:+.2f}" if r.get('mkt_delta') is not None else "N/A"

        # Determine status
        is_stale = (r.get('mkt_delta') is not None and abs(r['mkt_delta']) > 0.10)
        option_a_fixed = (is_stale and r.get('option_a_delta') is not None
                          and abs(r['option_a_delta']) > 0.10)

        if is_stale:
            status = "STALE"
            stale_count += 1
            if option_a_fixed:
                status += " -> OptA FIXES"
                option_a_fixes += 1
        else:
            status = "OK"

        if r.get('mkt_delta') is not None and abs(r['mkt_delta']) > 0.10:
            option_d_detects += 1

        print(f"{r['ticker']:<8} {r['exchange_group']:<10} {std_c:>10} {exp_c:>11} {opt_a_d:>8} "
              f"{mkt_c:>10} {mkt_d:>8} {r['std_last_date']:<22} {status}")

    print()
    print("-" * 80)
    print(f"Stale tickers detected:     {stale_count}/{len(results)}")
    print(f"Option A resolves staleness: {option_a_fixes}/{stale_count if stale_count else 'N/A'}")
    print(f"Option D detects staleness:  {option_d_detects}/{len(results)}")
    print()

    # Decision guidance
    if stale_count == 0:
        print("RESULT: No staleness detected at this time.")
        print("  -> If market is closed, data farm may have already consolidated.")
        print("  -> Re-run earlier after close (close+5min) to catch the stale window.")
    elif option_a_fixes == stale_count:
        print("RESULT: OPTION A RESOLVES ALL STALE TICKERS.")
        print("  -> Proceed to Phase 2: apply explicit endDateTime to all 4 reqHistoricalData calls.")
    elif option_a_fixes > 0:
        print(f"RESULT: Option A partially resolves ({option_a_fixes}/{stale_count}).")
        print("  -> Investigate: some tickers may need additional delay or Option D verification.")
    else:
        print("RESULT: Option A does NOT resolve staleness.")
        print("  -> Option D (reqMktData verification) is the required fix path.")
        print("  -> Phase 2 should implement staleness detection (Option C) + reqMktData cross-check (Option D).")
    print()

    if option_d_detects > 0:
        print(f"Option D (reqMktData) successfully detected {option_d_detects} divergence(s).")
        print("  -> Option C+D guardrail is viable regardless of Option A outcome.")
    print()
    print(f"Run completed at {datetime.now(et).strftime('%H:%M:%S ET')}")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PE-42 Phase 1 Diagnostic -- IBKR Staleness Audit")
    parser.add_argument("--port", type=int, default=4002,
                        help="IBKR gateway port (4002=paper/INFO, 4001=LIVE)")
    parser.add_argument("--profile", type=str, default="B", choices=["A", "B", "C"],
                        help="TBS profile to test (A=hourly, B=daily, C=weekly)")
    args = parser.parse_args()
    run_diagnostic(args.port, args.profile)
