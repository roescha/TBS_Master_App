################################################################################
#                   TBS v8.1 BATCH SCANNER (Layer 4)                           #
#         Objective: High-Volume Strategy Alignment & Candidate Discovery       #
################################################################################

import argparse
import time
import os
from tbs_orchestrator import execute_v8_pipeline

def load_tickers_from_file(filename):
    """
    Utility to extract tickers from the 'watchlists' directory.
    Mandate: Search within the dedicated sub-folder for research inputs.
    """
    # 1. Get the absolute path of the directory containing this script (scripts/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 2. Go up one level to target the project root
    project_root = os.path.dirname(script_dir)
    # 3. Explicitly define the charts directory at the root
    watchlist_dir = os.path.join(project_root, "watchlists")

    filepath = os.path.join(watchlist_dir, filename)

    if not os.path.exists(filepath):
        print(f"[ERR] [FILE ERROR] Watchlist '{filename}' not found in '{watchlist_dir}/'.")
        # List available files to help the Operator
        if os.path.exists(watchlist_dir):
            available = os.listdir(watchlist_dir)
            print(f"   Available: {available}")
        return []

    with open(filepath, 'r') as f:
        # Supports Ticker:WACC format for Turnaround research
        # Removes comments (#), whitespace, and empty lines
        return [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]

def run_tbs_scanner(ticker_list, profile="TREND"):
    """
    Processes multiple tickers through the finalized v8.1 Orchestrator.
    Mandate: Identify technical candidates while bypassing macro halts for INFO mode.
    Summary table displays ONLY tickers where [STEP 6] TECHNICAL PASS was confirmed,
    identified by the |S6:PASS| tag written by the Orchestrator return value.
    """
    print(f"\n{'#'*80}")
    print(f"               TBS v8.1 BATCH SCANNER: {len(ticker_list)} TICKERS")
    print(f"               PROFILE: {profile} | MODE: INFO (Research)")
    print(f"{'#'*80}\n")

    # [PRE-FLIGHT] Fail fast if chart engine (kaleido) is not installed.
    # Without this check, every ticker fails silently at the chart render step.
    from tbs_orchestrator import verify_chart_engine
    if not verify_chart_engine():
        print("[HALT] Chart engine unavailable. Install kaleido before scanning.")
        print("   Action Required: pip install --upgrade \"kaleido>=1.0.0\"")
        return

    # [MANDATE: ABSOLUTE PATHING] Ensure chart directory exists at Project Root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    chart_dir = os.path.join(project_root, "charts")
    if not os.path.exists(chart_dir):
        os.makedirs(chart_dir)

    start_time = time.time()

    # Per-ticker result collection: stores (ticker, return_string) for every asset.
    scan_results = []
    failures = 0

    for item in ticker_list:
        # Split ticker and optional WACC override (e.g. BT.A.L:8.0)
        if ":" in item:
            ticker, wacc_val = item.split(":", 1)
            try:
                wacc_val = float(wacc_val)
            except ValueError:
                print(f"[WARN] [INPUT ERROR] Invalid WACC for {ticker}. Defaulting to None.")
                wacc_val = None
        else:
            ticker, wacc_val = item, None

        if not ticker:
            continue

        try:
            print(f"[SCAN] ANALYZING: {ticker}")
            result = execute_v8_pipeline(
                ticker, profile=profile, mode="INFO", bypass_macro=True, wacc=wacc_val
            )
            # Normalise None returns to a labelled string
            status = result if result else "PASS|S6:PASS| (Pipeline Complete)"
            scan_results.append((ticker, status))

        except Exception as e:
            err_msg = f"ERROR|S6:UNKN| {str(e)[:60]}"
            print(f"[ERR] [SCAN ERROR] {ticker}: {str(e)}")
            scan_results.append((ticker, err_msg))
            failures += 1

        # Pacing: Adhere to IBKR/Yahoo rate limits
        time.sleep(1.2)

    duration = time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time))

    # =========================================================================
    # SUMMARY TABLE
    # [FILTER MANDATE] Only tickers carrying the |S6:PASS| tag appear as
    # candidates. This tag is written by the Orchestrator only when the
    # Technical Engine (Step 6) explicitly returns a PASS verdict.
    # =========================================================================

    s6_pass  = [r for r in scan_results if "|S6:PASS|" in r[1] and r[1].startswith("PASS")]
    s6_halt  = [r for r in scan_results if "|S6:HALT|" in r[1] and "Step 6" in r[1]]
    pre_halt = [r for r in scan_results if "|S6:HALT|" in r[1] and "Step 6" not in r[1]]
    errors   = [r for r in scan_results if r[1].startswith("ERROR")]

    print(f"\n{'='*80}")
    print(f"  [LOG] SCAN SUMMARY  --  {profile}  |  {len(ticker_list)} tickers  |  {duration}")
    print(f"{'='*80}")

    # --- CANDIDATES: Step 6 cleared ---
    if s6_pass:
        print(f"\n  [OK] CANDIDATES ({len(s6_pass)})  --  Step 6 cleared. Proceed to Visual Audit:")
        for ticker, status in s6_pass:
            clean = status.replace("PASS|S6:PASS|", "").strip()
            print(f"     {ticker:<12}  {clean}")
    else:
        print(f"\n  [OK] CANDIDATES (0)  --  No tickers cleared the Technical Engine today.")

    # --- TECHNICAL HALTS: Step 6 blocked (tally + tickers only) ---
    if s6_halt:
        print(f"\n  [ -- ] TECHNICAL HALTS ({len(s6_halt)})  --  Failed at Step 6 (not listed in detail):")
        print(f"     Tickers: {', '.join(t for t, _ in s6_halt)}")

    # --- EARLY HALTS: Blocked before Step 6 (macro/fundamental) ---
    if pre_halt:
        print(f"\n  [ ~~ ] EARLY HALTS ({len(pre_halt)})  --  Blocked before Step 6 (monitor for rotation):")
        for ticker, status in pre_halt:
            clean = status.replace("HALT|S6:HALT|", "").strip()
            print(f"     {ticker:<12}  {clean}")

    # --- ERRORS: Data or connection failures ---
    if errors:
        print(f"\n  [ERR] ERRORS ({len(errors)})  --  Data or connection failures:")
        for ticker, status in errors:
            clean = status.replace("ERROR|S6:UNKN|", "").strip()
            print(f"     {ticker:<12}  {clean}")

    print(f"\n  Action: Visually audit charts for CANDIDATES in the /charts directory.")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TBS v8.1 Batch Scanner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tickers", help="Comma-separated list: AAPL,MSFT,NVDA")
    group.add_argument("--watchlist", help="Filename inside 'watchlists' directory (e.g. tech.txt)")

    parser.add_argument("--profile", default="TREND", choices=["SWING", "TREND", "WEALTH"])

    args = parser.parse_args()

    # Input Selection Logic
    if args.watchlist:
        ticker_input = load_tickers_from_file(args.watchlist)
    else:
        ticker_input = [t.strip() for t in args.tickers.split(",") if t.strip()]

    if ticker_input:
        run_tbs_scanner(ticker_input, args.profile.upper())
    else:
        print("[HALT] No valid tickers provided. Check 'watchlists' directory.")