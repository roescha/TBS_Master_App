#!/usr/bin/env python3
"""
TBS Phase 0 — Snapshot Baseline Capture
Amendment: RFT-001 | Phase: 0 (Snapshot Capture)
Spec: TBS_Engine_Refactoring_Testing_Spec_v1_1.docx §IV.3

PURPOSE:
  Run ibkr_purity_engine.py against 6 ticker configurations and save
  the complete output (status, diagnostic, metrics) as JSON baselines.
  These baselines are the pre-refactoring reference: every subsequent
  refactoring phase must produce identical output for all 6 snapshots.

PREREQUISITES:
  - IBKR Paper Trading connection active (TWS or Gateway)
  - ibkr_purity_engine.py in the same directory (or on PYTHONPATH)
  - classifications.json in the same directory (or working directory)
  - Python 3.10+, ib_insync, pandas, pandas_ta installed

USAGE:
  python capture_baselines.py                    # Run all 6 captures
  python capture_baselines.py --ticker AAPL      # Run single ticker
  python capture_baselines.py --output-dir ./my_snapshots  # Custom output

OUTPUT:
  snapshots/
  ├── GD_SWING_C2_baseline.json
  ├── AAPL_TREND_C2_baseline.json
  ├── TSLA_TREND_C3_baseline.json
  ├── SPY_SWING_ETF_baseline.json
  ├── COST_WEALTH_C1_baseline.json
  └── HALT_case_baseline.json       # Whichever ticker produces HALT
  └── capture_manifest.json         # Capture metadata and market state

NO ENGINE CODE IS MODIFIED BY THIS SCRIPT.
"""

import json
import os
import sys
import datetime
import argparse
import traceback

# ---------------------------------------------------------------------------
# Import the engine — must be in the same directory or on PYTHONPATH
# ---------------------------------------------------------------------------
try:
    from ibkr_purity_engine import run_tbs_engine
except ImportError:
    print("ERROR: Cannot import ibkr_purity_engine. Ensure the script is in")
    print("       the same directory or on PYTHONPATH.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Snapshot Ticker Configurations — from RFT-001 Spec §IV.3.1
# ---------------------------------------------------------------------------
SNAPSHOT_CONFIGS = [
    {
        "label":           "GD_SWING_C2",
        "ticker":          "GD",
        "profile":         "SWING",
        "is_etf":          False,
        "convexity_class": "C2",
        "reason":          "CEG-001 trigger event. Known Capital R:R = 0.37 case.",
        "expected_path":   "S-17 (CEG-001 HALT) or PASS depending on current price",
    },
    {
        "label":           "AAPL_TREND_C2",
        "ticker":          "AAPL",
        "profile":         "TREND",
        "is_etf":          False,
        "convexity_class": "C2",
        "reason":          "Standard TRENDING pullback baseline. Clean PASS candidate.",
        "expected_path":   "Variable — depends on current market state",
    },
    {
        "label":           "TSLA_TREND_C3",
        "ticker":          "TSLA",
        "profile":         "TREND",
        "is_etf":          False,
        "convexity_class": "C3",
        "reason":          "C-3 convexity protocol. EMA 8 EXIT escalation, Modifier D INFORMATIONAL.",
        "expected_path":   "Variable — C-3 specific output fields must be present",
    },
    {
        "label":           "SPY_SWING_ETF",
        "ticker":          "SPY",
        "profile":         "SWING",
        "is_etf":          True,
        "convexity_class": None,
        "reason":          "ETF Logic Lock. _entry_trending/_entry_resolving snapshot. CRG-1 coverage.",
        "expected_path":   "Variable — ETF-specific routing must be visible in metrics",
    },
    {
        "label":           "COST_WEALTH_C1",
        "ticker":          "COST",
        "profile":         "WEALTH",
        "is_etf":          False,
        "convexity_class": "C1",
        "reason":          "WEALTH profile. Weekly bars. SMA 200 floor. Floor Proximity gate coverage.",
        "expected_path":   "Variable — Profile C specific gates must evaluate",
    },
    # --- ADDITIONAL CAPTURES (added to find PASS/APPROACHING baselines) ---
    {
        "label":           "COST_TREND_C1",
        "ticker":          "COST",
        "profile":         "TREND",
        "is_etf":          False,
        "convexity_class": "C1",
        "reason":          "TREND/C1 baseline. Supplements WEALTH capture. Seeking PASS/APPROACHING coverage.",
        "expected_path":   "Variable — looking for PASS or APPROACHING to cover Layers 4+5",
    },
    {
        "label":           "CENX_TREND_C2",
        "ticker":          "CENX",
        "profile":         "TREND",
        "is_etf":          False,
        "convexity_class": "C2",
        "reason":          "TREND/C2 baseline. Seeking PASS/APPROACHING coverage.",
        "expected_path":   "Variable — looking for PASS or APPROACHING to cover Layers 4+5",
    },
    {
        "label":           "TGT_SWING_C2",
        "ticker":          "TGT",
        "profile":         "SWING",
        "is_etf":          False,
        "convexity_class": "C2",
        "reason":          "SWING/C2 baseline. Seeking PASS/APPROACHING coverage.",
        "expected_path":   "Variable — looking for PASS or APPROACHING to cover Layers 4+5",
    },
    {
        "label":           "XOM_TREND_C2",
        "ticker":          "XOM",
        "profile":         "TREND",
        "is_etf":          False,
        "convexity_class": "C2",
        "reason":          "TREND/C2 baseline. Seeking PASS/APPROACHING coverage.",
        "expected_path":   "Variable — looking for PASS or APPROACHING to cover Layers 4+5",
    },
]
# HALT coverage: confirmed from initial 5 captures (all HALT). PASS coverage sought from additions.


def sanitise_metrics(metrics: dict) -> dict:
    """
    Convert metrics dict to JSON-serialisable form.
    Handles: NaN, Infinity, numpy types, None.
    """
    import math

    clean = {}
    for k, v in metrics.items():
        if v is None:
            clean[k] = None
        elif isinstance(v, float):
            if math.isnan(v):
                clean[k] = "__NaN__"
            elif math.isinf(v):
                clean[k] = "__Inf__" if v > 0 else "__-Inf__"
            else:
                clean[k] = v
        elif isinstance(v, (int, bool, str)):
            clean[k] = v
        elif hasattr(v, 'item'):  # numpy scalar
            clean[k] = v.item()
        else:
            clean[k] = str(v)
    return clean


def capture_one(config: dict, output_dir: str) -> dict:
    """
    Run the engine for one ticker configuration and save the JSON baseline.
    Returns a manifest entry dict.
    """
    label = config["label"]
    print(f"\n{'='*60}")
    print(f"  CAPTURING: {label}")
    print(f"  Ticker: {config['ticker']} | Profile: {config['profile']} | "
          f"ETF: {config['is_etf']} | Convexity: {config['convexity_class']}")
    print(f"{'='*60}")

    manifest_entry = {
        "label":           label,
        "ticker":          config["ticker"],
        "profile":         config["profile"],
        "is_etf":          config["is_etf"],
        "convexity_class": config["convexity_class"],
        "reason":          config["reason"],
        "capture_time":    datetime.datetime.now().isoformat(),
        "success":         False,
        "status":          None,
        "diagnostic_prefix": None,
        "error":           None,
    }

    try:
        status, diagnostic, metrics = run_tbs_engine(
            ticker=config["ticker"],
            profile=config["profile"],
            is_etf=config["is_etf"],
            mode="LIVE",
            convexity_class=config["convexity_class"],
        )

        # Truncate diagnostic for manifest (full version in baseline file)
        diag_prefix = diagnostic[:120] if diagnostic else ""

        baseline = {
            "capture_metadata": {
                "label":           label,
                "ticker":          config["ticker"],
                "profile":         config["profile"],
                "is_etf":          config["is_etf"],
                "convexity_class": config["convexity_class"],
                "capture_time":    datetime.datetime.now().isoformat(),
                "reason":          config["reason"],
                "expected_path":   config.get("expected_path", ""),
                "spec_reference":  "RFT-001 §IV.3.1",
            },
            "output": {
                "status":     status,
                "diagnostic": diagnostic,
                "metrics":    sanitise_metrics(metrics),
            },
        }

        # Write baseline JSON
        filepath = os.path.join(output_dir, f"{label}_baseline.json")
        with open(filepath, "w") as f:
            json.dump(baseline, f, indent=2, default=str)

        manifest_entry["success"] = True
        manifest_entry["status"] = status
        manifest_entry["diagnostic_prefix"] = diag_prefix
        manifest_entry["output_file"] = filepath

        print(f"  STATUS: {status}")
        print(f"  DIAGNOSTIC: {diag_prefix}...")
        print(f"  METRICS KEYS: {len(metrics)}")
        print(f"  SAVED: {filepath}")

        # Flag if this is a HALT case (useful for the 6th snapshot requirement)
        if status == "HALT":
            manifest_entry["is_halt_case"] = True

    except Exception as e:
        manifest_entry["error"] = f"{type(e).__name__}: {str(e)}"
        print(f"  ERROR: {manifest_entry['error']}")
        traceback.print_exc()

    return manifest_entry


def main():
    parser = argparse.ArgumentParser(
        description="RFT-001 Phase 0: Capture engine output baselines"
    )
    parser.add_argument(
        "--output-dir", default="./snapshots",
        help="Directory for baseline JSON files (default: ./snapshots)"
    )
    parser.add_argument(
        "--ticker", default=None,
        help="Run single ticker only (by label, e.g. AAPL_TREND_C2)"
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Filter to single ticker if requested
    if args.ticker:
        configs = [c for c in SNAPSHOT_CONFIGS if c["label"] == args.ticker
                   or c["ticker"] == args.ticker]
        if not configs:
            print(f"ERROR: No config found for '{args.ticker}'.")
            print(f"Available: {[c['label'] for c in SNAPSHOT_CONFIGS]}")
            sys.exit(1)
    else:
        configs = SNAPSHOT_CONFIGS

    # Run all captures
    manifest_entries = []
    for config in configs:
        entry = capture_one(config, args.output_dir)
        manifest_entries.append(entry)

    # Check: do we have at least one HALT case?
    halt_cases = [e for e in manifest_entries if e.get("is_halt_case")]
    pass_cases = [e for e in manifest_entries if e.get("status") == "PASS"]
    non_halt_non_pass = [e for e in manifest_entries
                         if e.get("status") not in ("HALT", "PASS", None)]

    print(f"\n{'='*60}")
    print("  CAPTURE SUMMARY")
    print(f"{'='*60}")
    print(f"  Total captured:  {len(manifest_entries)}")
    print(f"  Successful:      {sum(1 for e in manifest_entries if e['success'])}")
    print(f"  Failed:          {sum(1 for e in manifest_entries if not e['success'])}")
    print(f"  HALT cases:      {len(halt_cases)}")
    print(f"  PASS cases:      {len(pass_cases)}")
    print()

    if not halt_cases and not args.ticker:
        print("  WARNING: No HALT case captured among the 5 tickers.")
        print("  The spec requires at least 1 HALT baseline (§IV.3.1).")
        print("  Review the outputs above and either:")
        print("    (a) One of the 5 tickers happened to HALT — check status fields")
        print("    (b) Run an additional ticker known to produce HALT currently")
        print("        e.g.: python capture_baselines.py --ticker MANUAL_HALT")
        print("        (add the ticker config to SNAPSHOT_CONFIGS first)")
        print()

    # Write manifest
    manifest = {
        "spec_reference":  "RFT-001 Phase 0 — TBS_Engine_Refactoring_Testing_Spec_v1_1.docx",
        "capture_date":    datetime.datetime.now().isoformat(),
        "python_version":  sys.version,
        "entries":         manifest_entries,
        "halt_case_found": len(halt_cases) > 0,
        "notes": (
            "Phase 0 captures engine OUTPUT (status, diagnostic, metrics) only. "
            "DataFrame CSV capture is deferred to the test harness (Phase 1+). "
            "JSON baselines are sufficient for snapshot regression verification."
        ),
    }
    manifest_path = os.path.join(args.output_dir, "capture_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    print(f"  MANIFEST: {manifest_path}")

    # Final status
    all_ok = all(e["success"] for e in manifest_entries)
    if all_ok:
        print("\n  ✅ All captures successful. Review outputs before confirming Phase 0.")
    else:
        print("\n  ❌ Some captures failed. Review errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
