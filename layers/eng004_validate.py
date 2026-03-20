"""ENG-004 Measured Move Projection -- Live Arithmetic Validation Script

PURPOSE:
  Runs the ENG-004 computation against real market data *bypassing* the
  gate_result.verdict == "VALID" guard so you can validate the arithmetic
  even when no ticker currently produces a VALID verdict.

USAGE:
  python eng004_validate.py --ticker=DVN --profile=TREND --convexity C2
  python eng004_validate.py --ticker=DVN --profile=SWING --convexity C2
  python eng004_validate.py --ticker=SPY --profile=TREND              # ETF exclusion test

  Add --mode=LIVE for live market data (default is INFO/delayed).

WHAT IT DOES:
  1. Fetches data via the normal engine data layer (IBKR connection required)
  2. Classifies state via _classify_state (same as production)
  3. Extracts the lookback window per the ENG-004 spec
  4. Runs the measured move formula and prints all intermediate values
  5. Shows what the engine would have written to metrics if verdict were VALID

DELETE THIS SCRIPT after validation. It is not part of the engine.
"""

import argparse
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tbs_engine.data import _fetch_and_compute, _build_config, _classify_state


def _sep(label):
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")


def _validate_eng004(ticker, profile, mode, exchange, currency, convexity_class):
    p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C",
                 "A": "A", "B": "B", "C": "C"}
    p_code = p_mapping.get(profile.upper())
    if p_code is None:
        print(f"ERROR: Invalid profile '{profile}'")
        return

    is_etf = False  # Will be overridden by data layer
    cfg = _build_config(p_code)

    _sep(f"FETCHING DATA: {ticker} / Profile {p_code} ({profile})")
    df, raw_metrics = _fetch_and_compute(
        ticker, p_code, cfg, profile, is_etf, mode,
        exchange, currency, convexity_class
    )

    if df is None:
        print("ERROR: Data fetch failed.")
        print(f"  Detail: {raw_metrics}")
        return

    # Unpack what we need
    is_etf       = raw_metrics["is_etf"]
    price_scaler = raw_metrics["price_scaler"]
    bars_per_day = raw_metrics["bars_per_day"]
    state        = _classify_state(df, p_code, is_etf, cfg, raw_metrics)
    last         = df.iloc[cfg.iq]

    _sep("CONTEXT")
    print(f"  Ticker:           {ticker}")
    print(f"  Profile:          {profile} (p_code={p_code})")
    print(f"  is_etf:           {is_etf}")
    print(f"  _entry_trending:  {state._entry_trending}")
    print(f"  _entry_resolving: {state._entry_resolving}")
    print(f"  price_scaler:     {price_scaler}")
    print(f"  bars_per_day:     {bars_per_day}")
    print(f"  ATR (raw):        {state.atr_raw:.4f}")
    print(f"  Last close:       {last['close']:.4f}")
    print(f"  DataFrame len:    {len(df)}")

    # ------------------------------------------------------------------
    # ENG-004 COMPUTATION (bypasses VALID gate for validation)
    # ------------------------------------------------------------------
    _sep("ENG-004 SCOPE CHECK")

    mm_target = None
    mm_rally_atr = None
    path_taken = None

    if p_code == "B" and state._entry_trending and not is_etf:
        path_taken = "Profile B (TREND, TRENDING, non-ETF)"
        print(f"  Path: {path_taken}")
        print(f"  Window: df.iloc[-11:-1] (10-bar daily Focus Window)")

        window = df.iloc[-11:-1]
        origin = float(window['low'].min())
        peak   = float(window['high'].max())
        rally  = peak - origin

        print(f"\n  --- Rally Leg ---")
        print(f"  Origin (window low.min):   {origin:.4f}")
        print(f"  Peak (window high.max):    {peak:.4f}")
        print(f"  Rally_Leg:                 {rally:.4f}")
        print(f"  ATR (raw):                 {state.atr_raw:.4f}")
        print(f"  Rally / ATR:               {rally / state.atr_raw:.4f}" if state.atr_raw else "  Rally / ATR: N/A")
        print(f"  1.0 * ATR threshold:       {1.0 * state.atr_raw:.4f}")

        if rally < 1.0 * state.atr_raw or rally == 0:
            print(f"\n  GUARD TRIGGERED: Rally_Leg ({rally:.4f}) < 1.0 * ATR ({state.atr_raw:.4f}) or == 0")
            print(f"  Result: MM_Target = None, MM_Rally_ATR = None")
        else:
            mm_target    = round((last['close'] + rally) / price_scaler, 2)
            mm_rally_atr = round(rally / state.atr_raw, 2)
            print(f"\n  GUARD PASSED: Rally_Leg ({rally:.4f}) >= 1.0 * ATR ({state.atr_raw:.4f})")
            print(f"\n  --- Formula ---")
            print(f"  MM_Target    = (close + Rally_Leg) / price_scaler")
            print(f"               = ({last['close']:.4f} + {rally:.4f}) / {price_scaler}")
            print(f"               = {mm_target}")
            print(f"  MM_Rally_ATR = Rally_Leg / ATR")
            print(f"               = {rally:.4f} / {state.atr_raw:.4f}")
            print(f"               = {mm_rally_atr}")

    elif p_code == "A" and not is_etf:
        path_taken = "Profile A (SWING, non-ETF)"
        session_bars = int(bars_per_day * 3)
        min_bars     = int(bars_per_day * 2)
        print(f"  Path: {path_taken}")
        print(f"  session_bars = int({bars_per_day} * 3) = {session_bars}")
        print(f"  min_bars     = int({bars_per_day} * 2) = {min_bars}")
        print(f"  Window: df.iloc[-({session_bars}+1):-1] ({session_bars}-bar hourly lookback)")

        if len(df) > (session_bars + 1) and session_bars >= min_bars:
            window = df.iloc[-(session_bars + 1):-1]
            origin = float(window['low'].min())
            peak   = float(window['high'].max())
            rally  = peak - origin

            print(f"\n  --- Rally Leg ---")
            print(f"  Origin (window low.min):   {origin:.4f}")
            print(f"  Peak (window high.max):    {peak:.4f}")
            print(f"  Rally_Leg:                 {rally:.4f}")
            print(f"  ATR (raw):                 {state.atr_raw:.4f}")
            print(f"  Rally / ATR:               {rally / state.atr_raw:.4f}" if state.atr_raw else "  Rally / ATR: N/A")
            print(f"  1.0 * ATR threshold:       {1.0 * state.atr_raw:.4f}")

            if rally < 1.0 * state.atr_raw or rally == 0:
                print(f"\n  GUARD TRIGGERED: Rally_Leg ({rally:.4f}) < 1.0 * ATR ({state.atr_raw:.4f}) or == 0")
                print(f"  Result: MM_Target = None, MM_Rally_ATR = None")
            else:
                mm_target    = round((last['close'] + rally) / price_scaler, 2)
                mm_rally_atr = round(rally / state.atr_raw, 2)
                print(f"\n  GUARD PASSED: Rally_Leg ({rally:.4f}) >= 1.0 * ATR ({state.atr_raw:.4f})")
                print(f"\n  --- Formula ---")
                print(f"  MM_Target    = (close + Rally_Leg) / price_scaler")
                print(f"               = ({last['close']:.4f} + {rally:.4f}) / {price_scaler}")
                print(f"               = {mm_target}")
                print(f"  MM_Rally_ATR = Rally_Leg / ATR")
                print(f"               = {rally:.4f} / {state.atr_raw:.4f}")
                print(f"               = {mm_rally_atr}")
        else:
            print(f"\n  GUARD TRIGGERED: Insufficient bars.")
            print(f"  len(df) = {len(df)}, need > {session_bars + 1}")
            print(f"  Result: MM_Target = None, MM_Rally_ATR = None")

    else:
        # Exclusion path
        reasons = []
        if p_code == "C":
            reasons.append("Profile C excluded")
        if is_etf:
            reasons.append("ETF excluded")
        if p_code == "B" and not state._entry_trending:
            reasons.append("Profile B but not TRENDING (_entry_trending=False)")
        path_taken = f"EXCLUDED ({'; '.join(reasons)})"
        print(f"  Path: {path_taken}")
        print(f"  Result: MM_Target = None, MM_Rally_ATR = None")

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    _sep("VALIDATION RESULT")
    print(f"  Path taken:    {path_taken}")
    print(f"  MM_Target:     {mm_target}")
    print(f"  MM_Rally_ATR:  {mm_rally_atr}")

    if mm_target is not None:
        # Cross-reference with other trade setup fields
        print(f"\n  --- Cross-Reference ---")
        resistance = raw_metrics["metrics"].get("Resistance")
        profit_tgt = raw_metrics["metrics"].get("Profit_Target")
        print(f"  Current Price:   {last['close'] / price_scaler:.2f}")
        if resistance is not None:
            print(f"  Resistance:      {resistance}")
        if profit_tgt is not None:
            print(f"  Profit_Target:   {profit_tgt}")
        print(f"  MM_Target:       {mm_target}")
        print(f"  (MM_Target {'above' if mm_target > (resistance or 0) else 'at/below'} resistance)")

    print(f"\n  NOTE: This computation ran OUTSIDE the verdict gate.")
    print(f"  In production, these values only appear when verdict == VALID.")
    print(f"  This script validates the arithmetic only.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ENG-004 Live Arithmetic Validation")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--profile", default="TREND")
    parser.add_argument("--mode", default="LIVE")
    parser.add_argument("--exchange", default="SMART")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--convexity", default=None)
    args = parser.parse_args()

    _validate_eng004(args.ticker, args.profile, args.mode,
                     args.exchange, args.currency, args.convexity)
