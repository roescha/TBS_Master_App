#!/usr/bin/env python3
"""
tbs_engine_cli.py -- ENG-CLI-001: Engine CLI Wrapper

Lightweight CLI wrapper around the TBS purity engine.
Profile B: pre-fetches analyst consensus price targets (Yahoo -> Finnhub fallback).
All other profiles: pass-through to engine directly.

Usage:
    python tbs_engine_cli.py --ticker MSFT --profile TREND --mode LIVE --convexity=C2
    python tbs_engine_cli.py --ticker AAPL --profile SWING --mode LIVE --convexity=C1
    python tbs_engine_cli.py --ticker TSCO.L --profile TREND --mode LIVE --convexity=C2 --debug

ASCII-only encoding -- no Unicode characters. Operator runs on Windows cp1252.
"""

import argparse
import json
import sys

import yfinance as yf

from tbs_engine.main import run_tbs_engine
from finnhub_context import run_finnhub_analyst_targets

# =============================================================================
# PROFILE NORMALISATION
# =============================================================================

_PROFILE_MAP = {
    "A": ("SWING", "A"),
    "SWING": ("SWING", "A"),
    "B": ("TREND", "B"),
    "TREND": ("TREND", "B"),
    "C": ("WEALTH", "C"),
    "WEALTH": ("WEALTH", "C"),
}


# =============================================================================
# ANALYST TARGET FETCH (Profile B only)
# =============================================================================

def _fetch_analyst_targets(ticker):
    """Return (median, low, high, count) -- any may be None."""
    analyst_target_median = None
    analyst_target_low = None
    analyst_target_high = None
    analyst_count = None

    # --- Yahoo primary ---
    try:
        info = yf.Ticker(ticker).info
        analyst_target_median = info.get("targetMedianPrice")
        analyst_target_low = info.get("targetLowPrice")
        analyst_target_high = info.get("targetHighPrice")
        analyst_count = info.get("numberOfAnalystOpinions")
    except Exception as e:
        print("[FRR-001] Yahoo analyst target fetch failed: %s" % e)

    # --- Finnhub fallback (only for None fields) ---
    if any(v is None for v in [analyst_target_median, analyst_target_low,
                                analyst_target_high, analyst_count]):
        print("[FRR-001] Yahoo incomplete -- attempting Finnhub fallback...")
        try:
            _fh = run_finnhub_analyst_targets(ticker)
            if analyst_target_median is None and _fh.get("analyst_target_median") is not None:
                analyst_target_median = _fh["analyst_target_median"]
            if analyst_target_low is None and _fh.get("analyst_target_low") is not None:
                analyst_target_low = _fh["analyst_target_low"]
            if analyst_target_high is None and _fh.get("analyst_target_high") is not None:
                analyst_target_high = _fh["analyst_target_high"]
            if analyst_count is None and _fh.get("analyst_count") is not None:
                analyst_count = _fh["analyst_count"]
        except Exception as e:
            print("[FRR-001] Finnhub fallback failed: %s" % e)

    return analyst_target_median, analyst_target_low, analyst_target_high, analyst_count


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="TBS Engine CLI Wrapper (ENG-CLI-001)")
    parser.add_argument("--ticker",    required=True)
    parser.add_argument("--profile",   default="TREND")
    parser.add_argument("--mode",      default="INFO")
    parser.add_argument("--etf",       action="store_true")
    parser.add_argument("--convexity", default=None, choices=["C1", "C2", "C3"],
                        help="Convexity classification. Omit for unclassified assets.")
    parser.add_argument("--debug",     action="store_true",
                        help="Include _debug group with raw internal values in output.")
    args = parser.parse_args()

    # --- Normalise profile ---
    raw = args.profile.upper()
    if raw not in _PROFILE_MAP:
        print("ERROR: Unknown profile '%s'. Use SWING/A, TREND/B, or WEALTH/C." % args.profile,
              file=sys.stderr)
        sys.exit(1)
    profile, p_code = _PROFILE_MAP[raw]

    # --- Analyst targets (Profile B only) ---
    analyst_target_median = None
    analyst_target_low = None
    analyst_target_high = None
    analyst_count = None

    if p_code == "B":
        print("[FRR-001] Fetching analyst consensus targets...")
        analyst_target_median, analyst_target_low, analyst_target_high, analyst_count = \
            _fetch_analyst_targets(args.ticker)
        print("[FRR-001] Analyst targets: median=%s low=%s high=%s count=%s"
              % (analyst_target_median, analyst_target_low,
                 analyst_target_high, analyst_count))

    # --- Run engine ---
    result = run_tbs_engine(
        args.ticker, profile, args.etf, args.mode,
        convexity_class=args.convexity,
        debug=args.debug,
        analyst_target_median=analyst_target_median,
        analyst_target_low=analyst_target_low,
        analyst_target_high=analyst_target_high,
        analyst_count=analyst_count,
    )

    print(json.dumps(result, indent=4))


if __name__ == "__main__":
    main()
