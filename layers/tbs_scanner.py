################################################################################
#                   TBS v8.5 BATCH SCANNER (Layer 4)                           #
#         Objective: High-Volume Technical Candidate Discovery                  #
#         Mandate: Engine-only by design. Scanner runs Step 6 (Technical        #
#                  Engine) exclusively. Steps 1-5 (macro, fundamentals,         #
#                  sympathy, asset gates) are the Orchestrator's domain —       #
#                  the operator runs candidates individually through the        #
#                  full pipeline after scanner identifies PASS tickers.         #
#                                                                               #
#         Bug fixes: SC-1 (version), SC-2 (moat/roic/pivot args),             #
#                    SC-3 (None fallback), SC-4 (profile aliases)              #
#         v8.3.1:   SC-5 (honor --mode flag; was accepted but ignored),        #
#                    SC-6 (pass all v8.3.1 override args to orchestrator),      #
#                    SC-8 (--engine-only: skip Steps 1-5, fast scan mode)       #
#         v8.4:     CVX-SC-1 (Watchlist metadata parsing: inline + companion)  #
#                    CVX-SC-2 (Pre-flight admissibility gate)                   #
#                    CVX-SC-3 (--require-classification flag)                   #
#                    CVX-SC-4 (Convexity passthrough to orchestrator)           #
#                    CVX-SC-5 (Summary table enrichment with Conv. column)      #
#                    CVX-SC-6 (Companion .meta.json loading)                    #
#                    CVX-SC-7 (classifications.json fallback loading)           #
#         v8.4.1:   SC-10 (Scanner is now ALWAYS engine-only. The --engine-only#
#                    flag and fundamental override CLI flags removed.           #
#                    Rationale: scanner identifies Step 6 PASS candidates;     #
#                    operator then runs each through orchestrator individually  #
#                    for full pipeline + LIVE sign-offs. Running Steps 1-5 in  #
#                    the scanner was redundant — macro is identical per batch,  #
#                    fundamentals are identical per ticker, and the operator    #
#                    re-runs the full pipeline anyway. Engine-only saves API   #
#                    budget and eliminates the redundant path.)                 #
#         v8.5:     SC-11 (REWRITE: Remove orchestrator dependency entirely.   #
#                    Scanner now calls run_tbs_engine() directly from           #
#                    ibkr_purity_engine.py. Eliminates bypass_macro crash       #
#                    bug, double IB connection, and orchestrator coupling.)     #
#                                                                               #
#         Spec:     Scanner_Classification_Integration_Spec_v2.docx            #
#         Upstream: Role & Convexity Classification Prompt v2                  #
#         Downstream: TBS Convexity Redesign Proposal v2                       #
################################################################################

import argparse
import json
import time
import os
from ibkr_purity_engine import run_tbs_engine


# ==============================================================================
# ADMISSIBILITY RULES (Scanner_Classification_Integration_Spec_v2 §3.2)
# Derived from Classification Prompt v2 admissibility mapping:
#   C-1: A=ideal,          B=ideal,      C=ideal
#   C-2: A=restricted,     B=ideal,      C=ideal
#   C-3: A=not_permitted,  B=restricted, C=not_permitted
#   C-4: A=not_permitted,  B=not_permitted, C=not_permitted
# Gate: "not_permitted" = REJECT. "ideal"/"restricted" = PASS.
# ==============================================================================

# Default admissibility when only convexity class is known (no companion file)
DEFAULT_ADMISSIBILITY = {
    "C1": {"A": "ideal",          "B": "ideal",      "C": "ideal"},
    "C2": {"A": "restricted",     "B": "ideal",      "C": "ideal"},
    "C3": {"A": "not_permitted",  "B": "restricted",  "C": "not_permitted"},
    "C4": {"A": "not_permitted",  "B": "not_permitted", "C": "not_permitted"},
}

# Profile name → internal code mapping
PROFILE_MAP = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
PROFILE_NAMES = {"A": "SWING", "B": "TREND", "C": "WEALTH"}


def _resolve_project_root():
    """Return the project root directory (parent of scripts/)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


def load_classifications_json():
    """
    [CVX-SC-7] Load the simple classifications.json from project root.
    Format: {"TICKER": "C1|C2|C3"} per Convexity Redesign Proposal §6.4.
    Returns dict or empty dict if file not found.
    """
    project_root = _resolve_project_root()
    filepath = os.path.join(project_root, "docs\\classifications.json")
    if not os.path.exists(filepath):
        print(f"[WARN] [CVX] Failed to find classifications.json")
        return {}
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        # Normalize keys to uppercase
        return {k.upper(): v.upper() for k, v in data.items()}
    except (json.JSONDecodeError, Exception) as e:
        print(f"[WARN] [CVX] Failed to parse classifications.json: {e}")
        return {}


def load_companion_metadata(watchlist_filename):
    """
    [CVX-SC-6] Load companion .meta.json for a watchlist file.
    Convention: tech.meta.json companions tech.txt (Scanner Spec §3.1.2).
    The companion file takes precedence over classifications.json (Scanner Spec §3.1.3).

    Returns dict keyed by uppercase ticker:
      {"AAPL": {"convexity": "C2", "role": "B", "admissibility": {...}}, ...}
    Returns empty dict if no companion found.
    """
    project_root = _resolve_project_root()
    watchlist_dir = os.path.join(project_root, "watchlists")

    # Derive companion filename: tech.txt -> tech.meta.json
    base_name = os.path.splitext(watchlist_filename)[0]
    meta_filepath = os.path.join(watchlist_dir, f"{base_name}.meta.json")

    if not os.path.exists(meta_filepath):
        return {}

    try:
        with open(meta_filepath, 'r') as f:
            data = json.load(f)
        # Normalize keys to uppercase
        return {k.upper(): v for k, v in data.items()}
    except (json.JSONDecodeError, Exception) as e:
        print(f"[WARN] [CVX] Failed to parse {base_name}.meta.json: {e}")
        return {}


def parse_watchlist_line(line):
    """
    [CVX-SC-1] Parse a single watchlist line supporting both legacy and extended formats.

    Supported formats (Scanner Spec §3.1.1):
      AAPL                   → ticker only, no classification
      AAPL:C2:B              → ticker, convexity C2, role B
      NVDA:C3:C              → ticker, convexity C3, role C
      BT.A.L:C2:B:8.0        → ticker, convexity C2, role B, WACC override 8.0
      BT.A.L:8.0             → legacy format: ticker, WACC override (no classification)

    Returns dict: {
        "ticker": str,
        "wacc": float or None,
        "convexity": str or None  (e.g. "C2"),
        "role": str or None       (e.g. "B"),
    }
    """
    parts = line.strip().upper().split(":")
    result = {"ticker": None, "wacc": None, "convexity": None, "role": None}

    if not parts or not parts[0]:
        return result

    # Valid convexity codes for detection
    VALID_CVX = {"C1", "C2", "C3", "C4"}
    # Valid role codes
    VALID_ROLES = {"A", "B", "C", "D", "E"}

    # Multi-segment tickers (e.g. BT.A.L) don't contain C1/C2/C3/C4 as segments,
    # so we can safely detect the format by checking the second segment.

    result["ticker"] = parts[0]

    if len(parts) == 1:
        # Plain ticker: AAPL
        return result

    if len(parts) == 2:
        # Two segments: either TICKER:WACC (legacy) or ambiguous.
        # If second segment is a valid convexity code, treat as TICKER:CVX
        if parts[1] in VALID_CVX:
            result["convexity"] = parts[1]
        else:
            # Legacy WACC format: BT.A.L:8.0 or AAPL:9.2
            try:
                result["wacc"] = float(parts[1])
            except ValueError:
                # Not a number, not a convexity code -- ignore
                print(f"[WARN] [CVX] Unrecognised segment '{parts[1]}' for {parts[0]}. Ignoring.")
        return result

    if len(parts) >= 3:
        # Three+ segments: TICKER:CVX:ROLE or TICKER:CVX:ROLE:WACC
        if parts[1] in VALID_CVX:
            result["convexity"] = parts[1]
            if parts[2] in VALID_ROLES:
                result["role"] = parts[2]
            else:
                # Might be WACC in position 2 if role is omitted
                try:
                    result["wacc"] = float(parts[2])
                except ValueError:
                    print(f"[WARN] [CVX] Unrecognised role/WACC '{parts[2]}' for {parts[0]}.")

            # Fourth segment = WACC override
            if len(parts) >= 4 and result["wacc"] is None:
                try:
                    result["wacc"] = float(parts[3])
                except ValueError:
                    print(f"[WARN] [CVX] Invalid WACC '{parts[3]}' for {parts[0]}. Defaulting to None.")
        else:
            # Doesn't match extended format -- treat as legacy multi-segment ticker
            # (e.g. a ticker with dots that produces multiple segments)
            # Reconstruct ticker and try WACC from last segment
            try:
                result["wacc"] = float(parts[-1])
                result["ticker"] = ":".join(parts[:-1])
            except ValueError:
                result["ticker"] = ":".join(parts)

    return result


def get_admissibility(convexity, profile_code, companion_entry=None):
    """
    [CVX-SC-2] Check admissibility for a ticker given its convexity class and profile.

    Priority:
      1. Companion metadata admissibility (per-profile, from .meta.json)
      2. Default admissibility (derived from convexity class rules)

    Returns: "ideal", "restricted", or "not_permitted"
    """
    # Profile code → companion key mapping
    profile_to_key = {"A": "PROFILE_A", "B": "PROFILE_B", "C": "PROFILE_C"}
    profile_key = profile_to_key.get(profile_code, "PROFILE_B")

    # 1. Companion metadata takes precedence
    if companion_entry and "admissibility" in companion_entry:
        adm = companion_entry["admissibility"]
        if profile_key in adm:
            return adm[profile_key]

    # 2. Default admissibility from convexity class
    if convexity and convexity.upper() in DEFAULT_ADMISSIBILITY:
        return DEFAULT_ADMISSIBILITY[convexity.upper()].get(profile_code, "ideal")

    # 3. No classification → treat as ideal (C-1 default)
    return "ideal"


def load_tickers_from_file(filename):
    """
    Utility to extract tickers from the 'watchlists' directory.
    Mandate: Search within the dedicated sub-folder for research inputs.

    [CVX-SC-1] Extended to return raw lines (not just ticker strings) for
    downstream metadata parsing. Returns list of stripped uppercase lines.
    """
    project_root = _resolve_project_root()
    watchlist_dir = os.path.join(project_root, "watchlists")
    filepath = os.path.join(watchlist_dir, filename)

    if not os.path.exists(filepath):
        print(f"[ERR] [FILE ERROR] Watchlist '{filename}' not found in '{watchlist_dir}/'.")
        if os.path.exists(watchlist_dir):
            available = os.listdir(watchlist_dir)
            print(f"   Available: {available}")
        return []

    with open(filepath, 'r') as f:
        # Return raw lines (uppercase, stripped) -- metadata parsing happens later
        return [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]


def run_tbs_scanner(ticker_list, profile="TREND", mode="INFO",
                    require_classification=False,
                    watchlist_filename=None):
    """
    [SC-10] Engine-Only Batch Scanner: identifies technical PASS candidates.

    Processes multiple tickers through the Technical Engine (Step 6 only).
    Steps 1-5 (macro, fundamentals, sympathy, asset gates) are NOT run here —
    the operator runs each candidate individually through the orchestrator
    for the full pipeline + LIVE sign-offs after scanner identifies PASS tickers.

    Summary table displays ONLY tickers where [STEP 6] TECHNICAL PASS was confirmed,
    identified by the |S6:PASS| tag written by the engine return value.

    [CVX-SC-1] Watchlist metadata parsing (inline TICKER:CONVEXITY:ROLE format).
    [CVX-SC-2] Pre-flight admissibility gate before pipeline invocation.
    [CVX-SC-3] --require-classification flag: reject unclassified tickers.
    [CVX-SC-4] Convexity passthrough to engine.
    [CVX-SC-5] Summary table enrichment with Conv. column.
    [CVX-SC-6] Companion .meta.json loading.
    [CVX-SC-7] classifications.json fallback loading.
    [SC-10]    Always engine-only. Fundamental override flags removed.
    """
    profile_code = PROFILE_MAP.get(profile.upper(), "B")
    profile_display = f"{profile_code} ({PROFILE_NAMES.get(profile_code, 'UNKNOWN')})"

    _cvx_label = " | REQUIRE-CVX" if require_classification else ""
    print(f"\n{'#'*80}")
    print(f"               TBS v8.5 BATCH SCANNER: {len(ticker_list)} TICKERS")
    print(f"               PROFILE: {profile_display} | MODE: ENGINE-ONLY (Step 6){_cvx_label}")
    print(f"{'#'*80}\n")

    # [PRE-FLIGHT] Soft check for kaleido — verdicts are unaffected if missing.
    try:
        import kaleido  # noqa: F401
    except ImportError:
        print("[WARN] kaleido not installed — engine charts will not be generated. Verdicts unaffected.")

    # [NOTE] Chart directory creation removed in v8.5 (SC-11).
    # Engine creates its own chart directory internally.

    # =========================================================================
    # [CVX-SC-6] METADATA LOADING
    # Priority (Scanner Spec §3.1.3):
    #   1. Companion .meta.json (richest: includes role + per-profile admissibility)
    #   2. Inline TICKER:CVX:ROLE format in watchlist file
    #   3. classifications.json at project root (simple {"TICKER": "C1|C2|C3"})
    #   4. Unclassified → default to C-1 (or HALT if --require-classification)
    # =========================================================================
    companion_meta = {}
    if watchlist_filename:
        companion_meta = load_companion_metadata(watchlist_filename)
        if companion_meta:
            print(f"[CVX] Loaded companion metadata: {watchlist_filename.replace('.txt', '.meta.json')} ({len(companion_meta)} entries)")

    classifications = load_classifications_json()
    if classifications:
        print(f"[CVX] Loaded classifications.json: {len(classifications)} entries")

    start_time = time.time()
    scan_results = []    # (ticker, status, convexity_display)
    pre_rejected = []    # (ticker, reason, convexity_display) -- admissibility rejections
    failures = 0

    for item in ticker_list:
        # =================================================================
        # [CVX-SC-1] PARSE WATCHLIST LINE (inline metadata extraction)
        # =================================================================
        parsed = parse_watchlist_line(item)
        ticker = parsed["ticker"]
        wacc_val = parsed["wacc"]
        inline_convexity = parsed["convexity"]
        inline_role = parsed["role"]

        if not ticker:
            continue

        # =================================================================
        # [CVX-SC-6] RESOLVE CONVEXITY CLASS
        # Priority: companion .meta.json > inline > classifications.json > default
        # =================================================================
        convexity_class = None
        companion_entry = companion_meta.get(ticker)
        cvx_source = None

        if companion_entry and "convexity" in companion_entry:
            # Priority 1: Companion file (canonical per Scanner Spec §3.1.3)
            convexity_class = companion_entry["convexity"].upper()
            cvx_source = "companion"
        elif inline_convexity:
            # Priority 2: Inline format in watchlist
            convexity_class = inline_convexity
            cvx_source = "inline"
        elif ticker in classifications:
            # Priority 3: classifications.json
            convexity_class = classifications[ticker]
            cvx_source = "classifications.json"
        else:
            # Priority 4: Unclassified
            cvx_source = "default"

        # Display label for summary table
        cvx_display = convexity_class if convexity_class else "---"

        # =================================================================
        # [CVX-SC-3] CLASSIFICATION PRESENCE CHECK
        # =================================================================
        if convexity_class is None and require_classification:
            reason = f"CLASSIFICATION REQUIRED (--require-classification active)"
            print(f"[HALT] [CVX PRE-FLIGHT] {ticker}: {reason}")
            pre_rejected.append((ticker, f"HALT|S6:UNKN| {reason}", cvx_display))
            continue

        # Default unclassified tickers to C-1 behaviour
        if convexity_class is None:
            convexity_class = None  # Engine treats None as C-1 behaviour (backward compat)
            # cvx_display remains "---" to indicate no explicit classification

        # =================================================================
        # [CVX-SC-2] PROFILE ADMISSIBILITY CHECK
        # Gate fires BEFORE any API calls — saves IBKR/Yahoo rate limit budget.
        # "not_permitted" = REJECT. "ideal"/"restricted" = PASS.
        # =================================================================
        admissibility = get_admissibility(convexity_class, profile_code, companion_entry)

        if admissibility == "not_permitted":
            cvx_label = f"C-{convexity_class[1]}" if convexity_class else "UNKNOWN"
            profile_label = PROFILE_NAMES.get(profile_code, profile_code)
            reason = f"{cvx_label} NOT PERMITTED (Profile {profile_code} / {profile_label})"
            print(f"[HALT] [CVX PRE-FLIGHT] {ticker}: {reason}")
            pre_rejected.append((ticker, f"HALT|S6:UNKN| {reason}", cvx_display))
            continue

        if admissibility == "restricted" and convexity_class:
            cvx_label = f"C-{convexity_class[1]}" if convexity_class else ""
            print(f"[INFO] [CVX] {ticker}: {cvx_label} RESTRICTED on Profile {profile_code} (proceeding)")

        # =================================================================
        # [SC-11] DIRECT ENGINE INVOCATION (v8.5)
        # Scanner calls run_tbs_engine() directly from ibkr_purity_engine.py.
        # No orchestrator dependency. Engine manages its own IB connection
        # and ETF auto-detection.
        # =================================================================
        try:
            print(f"[SCAN] ANALYZING: {ticker}" +
                  (f" [CVX: {convexity_class} via {cvx_source}]" if convexity_class else ""))

            status, diag, metrics = run_tbs_engine(
                ticker,
                profile=profile,
                is_etf=False,       # Engine auto-detects via reqContractDetails
                mode=mode,
                convexity_class=convexity_class
            )

            # Format return string using same tag convention as before
            # so summary table filtering (|S6:PASS|, |S6:HALT|) works unchanged.
            _ths_tag = ""
            _ths_val = metrics.get('Trend_Health_Score')
            if _ths_val is not None:
                _ths_label = metrics.get('THS_Label', '')
                _ths_tag = f"THS:{int(_ths_val)}({_ths_label}) "

            if status == "PASS":
                formatted = f"PASS|S6:PASS| {_ths_tag}{diag}"
            elif status == "HALT":
                formatted = f"HALT|S6:HALT| Step 6: {diag}"
            else:
                formatted = f"ERROR|S6:UNKN| Step 6: {diag}"

            scan_results.append((ticker, formatted, cvx_display))

        except Exception as e:
            err_msg = f"ERROR|S6:UNKN| {str(e)[:80]}"
            print(f"[ERR] [SCAN ERROR] {ticker}: {str(e)}")
            scan_results.append((ticker, err_msg, cvx_display))
            failures += 1

        # Pacing: Adhere to IBKR/Yahoo rate limits
        time.sleep(1.2)

    duration = time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time))

    # =========================================================================
    # [CVX-SC-5] SUMMARY TABLE (Enriched with Convexity Column)
    # [FILTER MANDATE] Only tickers carrying the |S6:PASS| tag appear as
    # candidates. This tag is formatted by the scanner from the engine's
    # PASS verdict (SC-11: direct engine invocation).
    #
    # [SC-7 FIX] Classification handles both bypass-mode and direct returns.
    # =========================================================================

    s6_pass  = [r for r in scan_results if "|S6:PASS|" in r[1] and r[1].startswith("PASS")]
    s6_halt  = [r for r in scan_results if "|S6:HALT|" in r[1]]
    errors   = [r for r in scan_results if r[1].startswith("ERROR")]

    total_processed = len(ticker_list)
    total_rejected = len(pre_rejected)

    print(f"\n{'='*80}")
    print(f"  [LOG] SCAN SUMMARY  --  {profile_display}  |  {total_processed} tickers  |  {duration}")
    if total_rejected > 0:
        print(f"  [CVX] PRE-FLIGHT REJECTED: {total_rejected}  |  PIPELINE ENTERED: {total_processed - total_rejected}")
    print(f"{'='*80}")

    # --- CANDIDATES: Step 6 cleared ---
    if s6_pass:
        print(f"\n  [OK] CANDIDATES ({len(s6_pass)})  --  Step 6 cleared. Proceed to Visual Audit:")
        for ticker, status, cvx in s6_pass:
            clean = status.replace("PASS|S6:PASS|", "").strip()
            print(f"     {ticker:<12} {cvx:<5}  {clean}")
    else:
        print(f"\n  [OK] CANDIDATES (0)  --  No tickers cleared the Technical Engine today.")

    # --- TECHNICAL HALTS: Step 6 blocked ---
    if s6_halt:
        print(f"\n  [ -- ] TECHNICAL HALTS ({len(s6_halt)})  --  Failed at Step 6:")
        for ticker, status, cvx in s6_halt:
            clean = status.replace("PASS|S6:HALT|", "").replace("HALT|S6:HALT| Step 6:", "").replace("HALT|S6:HALT|", "").strip()
            print(f"     {ticker:<12} {cvx:<5}  {clean}")

    # --- CVX PRE-FLIGHT REJECTIONS: Admissibility gate blocked ---
    if pre_rejected:
        print(f"\n  [ XX ] CVX REJECTED ({len(pre_rejected)})  --  Admissibility gate blocked (no API calls):")
        for ticker, reason, cvx in pre_rejected:
            clean = reason.replace("HALT|S6:UNKN|", "").strip()
            print(f"     {ticker:<12} {cvx:<5}  {clean}")

    # --- ERRORS: Data or connection failures ---
    if errors:
        print(f"\n  [ERR] ERRORS ({len(errors)})  --  Data or connection failures:")
        for ticker, status, cvx in errors:
            clean = status.replace("ERROR|S6:UNKN|", "").strip()
            print(f"     {ticker:<12} {cvx:<5}  {clean}")

    print(f"\n  Next: Run CANDIDATES individually through the orchestrator for full pipeline:")
    print(f"        python tbs_orchestrator.py --ticker XXXX --profile {PROFILE_NAMES.get(profile_code, 'TREND')} --mode INFO")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TBS v8.5 Batch Scanner (Engine-Direct, Convexity-Aware). "
                    "Calls ibkr_purity_engine.py directly for Step 6 Technical Engine. "
                    "For full pipeline, use tbs_orchestrator.py per candidate.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tickers", help="Comma-separated list: AAPL,MSFT,NVDA or AAPL:C2:B,NVDA:C3:C")
    group.add_argument("--watchlist", help="Filename inside 'watchlists' directory (e.g. tech.txt)")

    # [SC-4 FIX] Accept both named profiles and letter aliases
    parser.add_argument("--profile", default="TREND",
                        choices=["SWING", "TREND", "WEALTH", "A", "B", "C"],
                        help="Trade profile (A=SWING, B=TREND, C=WEALTH).")
    # [SC-5 FIX] Mode flag determines IBKR port routing
    parser.add_argument("--mode", default="INFO", choices=["INFO", "LIVE"],
                        help="INFO (paper port 4002) or LIVE (port 4001).")

    # [CVX-SC-3] Require classification: reject unclassified tickers
    parser.add_argument("--require-classification", action="store_true",
                        help="Reject tickers without convexity classification (default: unclassified → C-1).")

    args = parser.parse_args()

    # Input Selection Logic
    if args.watchlist:
        ticker_input = load_tickers_from_file(args.watchlist)
        watchlist_filename = args.watchlist
    else:
        # CLI --tickers: split by comma, each element may have inline metadata
        ticker_input = [t.strip() for t in args.tickers.split(",") if t.strip()]
        watchlist_filename = None

    if ticker_input:
        run_tbs_scanner(ticker_input, profile=args.profile.upper(), mode=args.mode,
                        require_classification=args.require_classification,
                        watchlist_filename=watchlist_filename)
    else:
        print("[HALT] No valid tickers provided. Check 'watchlists' directory.")
