"""TBS Purity Engine — Re-export shim.

RFT-004 Phase 2: ibkr_purity_engine.py is now a full re-export shim.
All implementation lives in the tbs_engine/ package.

This shim re-exports ALL public and internal symbols so that existing
consumers (tbs_orchestrator.py, tbs_scanner.py) and the full test suite
continue to import from ibkr_purity_engine without modification.
"""

from tbs_engine.main import run_tbs_engine
from tbs_engine.types import *
from tbs_engine.helpers import *
from tbs_engine.gates import *
from tbs_engine.compute import *
from tbs_engine.exit import *
from tbs_engine.data import *
from tbs_engine.trigger import *
from tbs_engine.output import *

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",     required=True)
    parser.add_argument("--profile",    default="TREND")
    parser.add_argument("--mode",       default="INFO")
    parser.add_argument("--etf",        action="store_true")
    parser.add_argument("--convexity",  default=None, choices=["C1", "C2", "C3"],
                        help="Convexity classification (from Classification Prompt). "
                             "Omit for unclassified assets (defaults to C-1 behaviour).")
    args = parser.parse_args()

    status, diag, metrics = run_tbs_engine(
        args.ticker, args.profile, args.etf, args.mode,
        convexity_class=args.convexity
    )
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))
