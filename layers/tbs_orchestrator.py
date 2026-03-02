import argparse
import sys
import os
import asyncio
from ai_event_radar import run_risk_radar
from ai_fundamental_retriever import run_retriever_with_timeout
from ai_vision_auditor import run_vision_audit
from ib_insync import IB, Stock, Contract

# -----------------------------
# TBS MASTER ORCHESTRATOR (Layer 3) v8.3.2
# Pipeline Execution, Governor Sizing, Bracket Order Routing
#
# Bug fixes: O-1 (sentinel profile passthrough), O-2 (shared IB connection),
#            O-4 (window mandate), O-5 (moat/roic/pivot args), O-6 (contract routing),
#            SC-5 (profile normalization SWING/TREND/WEALTH -> A/B/C),
#            SC-6 (ERROR status from engine/fundamentals treated as PASS),
#            SC-9 (dashboard gated on step6_passed)
#
# v8.3.1:   O-7  (Wire Layer 1.5a ibkr_sympathy_audit -- was manual prompt_operator only)
#            O-8  (Wire Layer 1.5b ibkr_asset_gates -- was completely absent)
#            O-9  (Passthrough v8.3.1 CLI args: --tnx, --de, --fcf-yield, --rev, --eps,
#                   --sector-etf, --etf to downstream scripts)
#            O-10 (IV Guard from asset gates propagates to order_type in Step 8)
#            O-11 (Sympathy + Asset Gates run in BOTH INFO and LIVE modes per Doc 8 Layer 1.5)
#            O-12 (Dashboard surfaces sympathy verdict, sector ETF, IV/HV, dividend status)
#
# v8.3.2:   O-13 (DEFENSIVE regime hard-blocks Profile B/C per Doc 5 Sec II -- "No new long-term adds")
#            O-14 (Dashboard uses engine Profit_Target/Reward_Risk instead of recomputing from raw fields)
#            O-15 (Dashboard surfaces Engine_State, Exit_Signal, Exit_VWAP_Counter from PE-28)
#            O-16 (Position Monitor mode: --entry-price + --shares enables collect-all pipeline.
#                   Three-state model: EXIT / NO ACTION / FIT FOR ADD.
#                   EXIT and NO ACTION display dashboard and return.
#                   FIT FOR ADD falls through to Steps 7-8 for add sizing and execution.
#                   All entry-blocking conditions also block adds (_no_adds invariant).)
#            O-17 (--capital flag: optional portfolio net worth override for sizing, bypasses IBKR account query)
#            O-18 (INFO mode sizing preview: when --capital provided, Steps 7 runs in INFO mode with PREVIEW label)
#            O-19 (Auto-extract TNX yield from sentinel_details for fundamentals FCF Yield comparison; CLI --tnx overrides)
#            O-20 (Pass orchestrator IB connection to sympathy_audit and asset_gates; avoids clientId collision)
#            O-21 (Move Step 3 Visual after Step 6 Engine -- operator sees engine results before chart verification)
#            O-22 (Interactive MOAT prompt for WEALTH profile in LIVE mode when --moat not provided)
#            O-23 (Retry loop for Step 5: prompts operator for missing fundamentals data inline instead of pipeline kill)
#            O-24 (Engine-only fast path: skip Steps 1-5, run only Step 6 for scanner batch mode)
#
# v8.4.0:   O-25 (Convexity classification passthrough: --convexity CLI arg + convexity_class parameter.
#                   Scanner Spec §3.3: accept convexity_class, forward to run_tbs_engine().)
#            O-26 (classifications.json fallback: load from project root when convexity_class not passed.
#                   Redesign Proposal §6.3: enables standalone orchestrator usage with classification.)
#            O-27 (Admissibility gate: C-3 rejected on Profile A/C, C-4 rejected on all profiles.
#                   Scanner Spec §3.2: fires before IBKR connection to save API budget.)
#            O-28 (Convexity_Class surfaced in execution dashboard and position monitor dashboard.
#                   Redesign Proposal §6.3: operator sees classification + management regime.)
# -----------------------------

# TBS Layer Imports
from ibkr_sentinel import run_tbs_sentinel
from yahoo_fundamentals import run_v8_clean_audit
from ibkr_sympathy_audit import run_sympathy_audit       # [O-7] Layer 1.5a
from ibkr_asset_gates import run_asset_gates              # [O-8] Layer 1.5b
from ibkr_purity_engine import run_tbs_engine

from ib_insync import LimitOrder, MarketOrder, StopOrder


def execute_bracket_order(ib, contract, action, quantity, order_type, entry_price, hard_stop_price, target_price=None):
    """
    Constructs and submits a strict TBS Bracket Order via ib_insync.
    Maps exactly to the v8.2 Hard Stop and Target logic.
    """
    action = action.upper()
    reverse_action = "SELL" if action == "BUY" else "BUY"
    orders_to_submit = []

    if order_type == "LIMIT":
        parent = LimitOrder(action, quantity, entry_price)
    else:
        parent = MarketOrder(action, quantity)
    parent.orderId = ib.client.getReqId()
    parent.transmit = False
    orders_to_submit.append(parent)

    stop_order = StopOrder(reverse_action, quantity, hard_stop_price)
    stop_order.parentId = parent.orderId
    stop_order.transmit = True if target_price in [None, "OPEN-ENDED", "N/A"] else False
    orders_to_submit.append(stop_order)

    if target_price not in [None, "OPEN-ENDED", "N/A"]:
        target_order = LimitOrder(reverse_action, quantity, float(target_price))
        target_order.parentId = parent.orderId
        target_order.transmit = True
        orders_to_submit.append(target_order)

    trades = []
    # for order in orders_to_submit:
    #     trade = ib.placeOrder(contract, order)
    #     trades.append(trade)
    return trades


def prompt_operator(step_num, question):
    """Strict human sign-off for qualitative execution gates (LIVE mode only)."""
    while True:
        ans = input(f"   [STEP {step_num}] {question} (Y/N): ").strip().upper()
        if ans in ['Y', 'N']:
            return ans == 'Y'
        print("   [!] Invalid input. Enter Y or N.")


def verify_chart_engine():
    """Diagnostic to ensure Kaleido is installed for chart export."""
    try:
        import kaleido
    except ImportError:
        print("[FATAL] Static image engine 'kaleido' not found.")
        print("   Action Required: Run 'pip install --upgrade \"kaleido>=1.0.0\"' in your terminal.")
        return False
    return True


def get_asset_type(ib, ticker):
    """
    [MANDATE: DOC 8 SEC 23] High-Fidelity Asset Identification.
    Returns (is_etf: bool, contract: Stock) for reuse in bracket orders.
    """
    clean_ticker = ticker.upper()
    exchange, currency, p_exchange = 'SMART', 'USD', ""
    routing_map = {
        '.L': {'exch': 'SMART', 'curr': 'GBP', 'prim': 'LSE'},
        '.TO': {'exch': 'SMART', 'curr': 'CAD', 'prim': 'TSE'},
        '.DE': {'exch': 'IBIS', 'curr': 'EUR', 'prim': 'IBIS'},
        '.AS': {'exch': 'AEB', 'curr': 'EUR', 'prim': 'AEB'},
        '.PA': {'exch': 'SBF', 'curr': 'EUR', 'prim': 'SBF'}
    }
    for suffix, route in routing_map.items():
        if clean_ticker.endswith(suffix):
            clean_ticker = clean_ticker.replace(suffix, '')
            exchange, currency, p_exchange = route['exch'], route['curr'], route['prim']
            break

    contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)
    try:
        details = ib.reqContractDetails(contract)
        if details:
            meta = details[0].longName.upper()
            etf_keywords = ['ETF', 'FUND', 'VANGUARD', 'ISHARES', 'UCITS',
                            'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES']
            if any(key in meta for key in etf_keywords):
                return True, contract
    except Exception:
        pass
    return False, contract

def retrieve_and_confirm(ticker, metric_name):
    """
    Executes the AI Network Search with 120s timeout and mandates Operator confirmation.
    """
    print(f"   [ANALYST] Initiating 120s Network Search for {metric_name}...")

    # Run the async retriever synchronously from the orchestrator
    result = asyncio.run(run_retriever_with_timeout(ticker, metric_name, timeout=120.0))
    data = result.get("data", {})

    val = data.get("value")
    source = data.get("source")

    if val is None or source == "TIMEOUT":
        print(f"   [FAIL] AI Retrieval failed or timed out. Reason: {data.get('error', 'Unknown')}")
        return None

    print(f"   [ANALYST RESULT] Found {metric_name}: {val}")
    print(f"   [SOURCE] {source}")

    # [MANDATE: OPERATOR CONFIRMATION]
    confirm = input("   Accept this value? (Y to accept / N to reject and SKIP): ").strip().upper()
    if confirm == 'Y':
        return val
    return None

def execute_v8_pipeline(ticker, profile="TREND", mode="INFO", bypass_macro=False,
                        wacc=None, moat=None, roic_override=None, pivot_confirmed=False,
                        # [O-9] v8.3.1 passthrough args
                        tnx=None, de_override=None, fcf_yield_override=None,
                        rev_override=None, eps_override=None,
                        sector_etf_override=None, is_etf_flag=False,
                        # [O-16] Position Monitor args
                        entry_price_override=None, shares=None,
                        # [O-17] Capital override
                        capital_override=None,
                        # [O-24] Engine-only mode: skip Steps 1-5, run Step 6 only
                        engine_only=False,
                        # [O-25] Convexity classification passthrough (Scanner Spec §3.3)
                        convexity_class=None):

    # [SC-5 FIX] Normalize profile aliases to internal codes (A/B/C).
    profile_map = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    profile = profile_map.get(profile.upper(), "B")

    # ===================================================================
    # [O-26] CONVEXITY CLASSIFICATION RESOLUTION (Redesign Proposal §6.3)
    # If convexity_class not passed by scanner, attempt classifications.json
    # lookup. This enables standalone orchestrator usage with classification.
    # ===================================================================
    if convexity_class is None:
        try:
            import json as _json
            _script_dir = os.path.dirname(os.path.abspath(__file__))
            _project_root = os.path.dirname(_script_dir)
            _cvx_path = os.path.join(_project_root, "docs\\Classifications.json")
            if os.path.exists(_cvx_path):
                with open(_cvx_path, 'r') as _f:
                    _cvx_data = _json.load(_f)
                _cvx_lookup = _cvx_data.get(ticker.upper()) or _cvx_data.get(ticker)
                if _cvx_lookup:
                    convexity_class = _cvx_lookup.upper()
                    print(f"[CVX] Classification loaded from classifications.json: {convexity_class}")
        except Exception:
            pass  # Silent -- classifications.json is optional

    # [O-27] ADMISSIBILITY GATE (Scanner Spec §3.2 / Classification Prompt v2)
    # Fires before any IBKR connection to save API budget on rejected tickers.
    # C-3 → NOT PERMITTED on Profile A (SWING) and Profile C (WEALTH).
    # C-4 → NOT PERMITTED on all profiles.
    _CVX_ADMISSIBILITY = {
        "C3": {"A": False, "B": True, "C": False},
        "C4": {"A": False, "B": False, "C": False},
    }
    if convexity_class and convexity_class.upper() in _CVX_ADMISSIBILITY:
        _adm = _CVX_ADMISSIBILITY[convexity_class.upper()]
        if not _adm.get(profile, True):
            _pnames = {"A": "SWING", "B": "TREND", "C": "WEALTH"}
            _reason = f"{convexity_class.upper()} NOT PERMITTED (Profile {profile} / {_pnames.get(profile, profile)})"
            print(f"[HALT] [CVX ADMISSIBILITY] {ticker}: {_reason}")
            return f"HALT|S6:UNKN| {_reason}"

    _cvx_display = f" | CVX: {convexity_class}" if convexity_class else ""

    port = 4001 if mode == "LIVE" else 4002
    ib = IB()
    active_bypass = (mode == "INFO" and bypass_macro)

    # [O-16] Position Monitor Mode: when entry_price and shares are provided,
    # the pipeline switches from entry-gating (fail-fast) to position monitoring
    # (collect-all). Every step runs to completion and verdicts accumulate.
    position_monitor = (entry_price_override is not None and shares is not None)

    profile_names = {"A": "SWING", "B": "TREND", "C": "WEALTH"}
    profile_display = f"{profile} ({profile_names.get(profile, 'UNKNOWN')})"
    _mode_label = f"MONITOR (${entry_price_override} x {shares})" if position_monitor else mode
    print(f"\n{'='*80}\nTBS v8.3.2 MASTER ORCHESTRATOR: {ticker} | {profile_display} | MODE: {_mode_label}{_cvx_display}")
    if active_bypass: print("[WARN] BYPASS ACTIVE: Observing full pipeline despite Logic Halts.")
    if position_monitor: print(f"[MONITOR] Position Monitor active: Entry ${entry_price_override} x {shares} shares")
    print(f"{'='*80}")

    try:
        ib.connect('127.0.0.1', port, clientId=100)
        ib.reqMarketDataType(1)
        step6_passed = False

        # ==================================================================
        # [O-24] ENGINE-ONLY FAST PATH
        # Skips Steps 1-5, runs only the Technical Engine (Step 6).
        # Used by scanner for high-volume candidate discovery where only
        # price action / technical alignment matters. Returns same format
        # string (PASS|S6:PASS| or HALT|S6:HALT|) for scanner compatibility.
        # ==================================================================
        if engine_only:
            is_etf, resolved_contract = get_asset_type(ib, ticker)
            if is_etf_flag:
                is_etf = True
            print(f"[SCAN] [AUTO-ID] {'ETF/Index' if is_etf else 'Equity'} | ENGINE-ONLY mode")
            status, diag, metrics = run_tbs_engine(ticker, profile=profile, is_etf=is_etf, mode=mode,
                                                   convexity_class=convexity_class)
            ib.disconnect()
            # [Module G] Extract THS for scanner CANDIDATES display
            _ths_tag = ""
            _ths_val = metrics.get('Trend_Health_Score')
            if _ths_val is not None:
                _ths_tag = f"THS:{int(_ths_val)} "
            if status == "PASS":
                return f"PASS|S6:PASS| {_ths_tag}{diag}"
            elif status == "HALT":
                return f"HALT|S6:HALT| Step 6: {diag}"
            else:
                return f"ERROR|S6:UNKN| Step 6: {diag}"

        # [O-16] Verdict collector for position monitor mode.
        # In entry mode, a HALT returns immediately. In monitor mode, verdicts
        # are logged and the pipeline continues to collect the full picture.
        _verdicts = {}   # step_name -> (status, detail)
        _threats = []    # list of threat strings for position dashboard
        _no_adds = False # earnings/event prohibits adding to position

        # ==================================================================
        # STEP 1: SYSTEMIC PERMISSION (The Sentinel) [Doc 5 / Doc 7 Step 1]
        # ==================================================================
        regime, verdict, reason, storm_watch_active, sentinel_details = run_tbs_sentinel(
            ib_connection=ib, port=port, profile=profile
        )

        _verdicts["Sentinel"] = (verdict, regime)

        # [O-19] Auto-extract TNX yield from sentinel for fundamentals passthrough.
        # Priority: CLI --tnx override > sentinel-computed tnx_close_daily
        # IBKR TNX index reports yield as price (e.g. 39.62 = 3.962%). Divide by 10.
        if tnx is None and sentinel_details and sentinel_details.get("tnx_close_daily") is not None:
            tnx = round(sentinel_details["tnx_close_daily"] / 10.0, 2)
            print(f"[AUTO] TNX yield auto-extracted from Sentinel: {tnx:.2f}%")

        if verdict in ["HALT", "FORCE HARVEST"] and not active_bypass:
            if position_monitor:
                # [O-16] Log threat and continue -- regime is EXIT-relevant for held positions
                print(f"[WARN] Step 1: {reason} (Regime: {regime}) -- continuing for position analysis")
                _threats.append(f"Regime {regime}: {reason}")
                _no_adds = True
            else:
                print(f"[HALT] Step 1: {reason} (Regime: {regime})")
                if verdict == "FORCE HARVEST" or "RESTRICTED" in regime:
                    print(f"\n{'!'*30} [MANDATE: LIQUIDATION WATERFALL] {'!'*30}")
                    print("   Regime mandates a 50% CASH FLOOR. Harvest capital in this order:")
                    print("   1. TIER 1 (TERMINAL): Immediate exit of all BROKEN/TERMINATED or WEAK/VULNERABLE [Doc 3].")
                    print("   2. TIER 2 (NON-CORE): Harvest ALL Profile A. Harvest Profile B closest to 50-SMA [Doc 3].")
                    print("   3. TIER 3 (EFFICIENCY): Liquidate Profile C in Structural Floor Violation [Doc 3].")
                    print(f"{'!'*80}\n")
                return "HALT|S6:HALT| Step 1: " + regime

        if verdict != "PASS" and active_bypass:
            print(f"[WARN] [MACRO HALT BYPASSED] Step 1 reported {verdict}.")
        else:
            print(f"[PASS] [STEP 1] SENTINEL PASS: {regime}")

        # [O-13] DEFENSIVE REGIME PROFILE GATE [Doc 5 Sec II]
        if "DEFENSIVE" in regime and profile in ("B", "C") and not active_bypass:
            if position_monitor:
                _threats.append(f"DEFENSIVE regime: Profile {profile} long-term adds prohibited")
                _no_adds = True
                print(f"[WARN] Step 1: DEFENSIVE regime -- Profile {profile} adds blocked (position held)")
            else:
                print(f"[HALT] Step 1: DEFENSIVE regime blocks Profile {profile} entries.")
                print(f"   [MANDATE: Doc 5 Sec II] 'No new long-term adds; focus on Profile A/Scalps.'")
                print(f"   Profile B (TREND) and C (WEALTH) entries are NOT permitted in DEFENSIVE regime.")
                return f"HALT|S6:HALT| Step 1: DEFENSIVE blocks Profile {profile} (long-term adds prohibited)"

        # AUTO-ID: Deterministic Asset Classification
        is_etf, resolved_contract = get_asset_type(ib, ticker)
        if is_etf_flag:
            is_etf = True
        print(f"[SCAN] [AUTO-ID] Asset identified as: {'ETF/Index' if is_etf else 'Standard Equity'}")

        # ==================================================================
        # STEP 2: PORTFOLIO PERMISSION (The Governor) [Doc 3 / Doc 7 Step 2]
        # Bypassed in INFO mode per Doc 7 Pre-Flight.
        # [O-16] Bypassed in Position Monitor -- you already own the position.
        # ==================================================================
        if position_monitor:
            print("[SKIP] [STEP 2] BYPASSED: Position Monitor (position already held)")
        elif mode == "LIVE":
            if not prompt_operator(2, "Portfolio: Heat < 5% & Slots Open? [Doc 3]"):
                print("[HALT] Step 2 failure."); return "HALT|S6:HALT| Step 2: Portfolio Capacity"
        else:
            print("[SKIP] [STEP 2] BYPASSED: INFO Mode Active")

        # ==================================================================
        # STEP 3: VISUAL PROOF SUBMISSION [Doc 4 / Doc 7 Step 3]
        # [O-21] DEFERRED to after Step 6. The operator cannot verify "engine
        # state matches charts" until the engine has produced results. Visual
        # verification is now the final human gate before sizing/execution.
        # ==================================================================

        # ==================================================================
        # STEP 4: ASSET PERMISSION [Doc 5 Sec 3 / Doc 7 Step 4]
        # ==================================================================

        event_aware, system_overheat = False, False
        iv_guard_limit_only = False    # [O-10] Propagated to order_type

        # --- 4a & 4d: AI Risk Radar (Integrity Shocks & Event-Aware) ---
        print(f"[....] [STEP 4a/4d] Executing AI Risk Radar (Integrity & Binary Events)...")
        # Execute the async AI Radar from the sync Orchestrator
        radar_results = asyncio.run(run_risk_radar(ticker))

        # Check for Integrity Shocks (Step 4a)
        if radar_results.get("integrity_shock_detected", False):
            # Extract the specific failure details from the radar payload
            shock_details = []
            for cat in ["security_geo", "operational_env", "integrity_legal", "financial_shock"]:
                if radar_results.get(cat, {}).get("status") != "PASS":
                    shock_details.append(f"{cat.upper()}: {radar_results.get(cat, {}).get('details', 'Unknown')}")

            detail_str = " | ".join(shock_details) if shock_details else "Unspecified structural threat"

            if position_monitor:
                _threats.append(f"INTEGRITY SHOCK: {detail_str}")
                _no_adds = True
                print(f"[WARN] Step 4a: Integrity Shock -- {detail_str}")
            elif mode == "LIVE" and not active_bypass:
                print(f"[HALT] Step 4a: Integrity Shock detected: {detail_str}")
                return f"HALT|S6:HALT| Step 4a: Integrity Shock ({detail_str})"
            else:
                print(f"[WARN] Step 4a: Integrity Shock detected (INFO/BYPASS): {detail_str}")
        else:
            print("[PASS] [STEP 4a] INTEGRITY SHOCKS CLEAR.")

        # --- 4b: SYMPATHY AUDIT [Doc 5 Sec 3.1 / Doc 8 Layer 1.5a] ---
        print(f"[....] [STEP 4b] Executing Sympathy Audit...")
        symp_status, symp_diag, symp_metrics = run_sympathy_audit(
            ticker, profile=profile,
            sector_etf_override=sector_etf_override,
            mode=mode,
            ib_connection=None
        )

        _verdicts["Sympathy"] = (symp_status, symp_diag)

        if symp_status == "HALT":
            print(f"[HALT] Step 4b (Sympathy): {symp_diag}")
            if position_monitor:
                _threats.append(f"Sympathy HALT: sector floor violated -- {symp_diag}")
                _no_adds = True
            elif not active_bypass:
                return f"HALT|S6:HALT| Step 4b: {symp_diag[:60]}"
        elif symp_status == "ERROR":
            print(f"[ERROR] Step 4b (Sympathy): {symp_diag}")
            if position_monitor:
                _threats.append(f"Sympathy ERROR: {symp_diag}")
                _no_adds = True
            elif not active_bypass:
                return f"ERROR|S6:UNKN| Step 4b: {symp_diag[:60]}"
        elif symp_status == "SKIPPED":
            print(f"[WARN] [STEP 4b] SYMPATHY SKIPPED: {symp_diag}")
        elif symp_status == "EXEMPT":
            print(f"[PASS] [STEP 4b] SYMPATHY EXEMPT: {symp_diag}")
        else:
            print(f"[PASS] [STEP 4b] SYMPATHY PASS: {symp_diag}")

        # --- 4c: ASSET GATES [Doc 5 Sec 3.2 / Doc 8 Layer 1.5b] ---
        print(f"[....] [STEP 4c] Executing Asset Gates (IV Guard + Dividend Lockout)...")
        ag_status, ag_diag, ag_metrics = run_asset_gates(
            ticker, profile=profile, mode=mode,
            ib_connection=None
        )

        _verdicts["Asset_Gates"] = (ag_status, ag_diag)

        if ag_status == "BLOCKED":
            print(f"[HALT] Step 4c (Asset Gates): {ag_diag}")
            if position_monitor:
                _threats.append(f"Dividend Lockout: ex-date imminent -- NO ADDS")
                _no_adds = True
            else:
                return f"HALT|S6:HALT| Step 4c: DIVIDEND LOCKOUT"
        elif ag_status == "ERROR":
            print(f"[ERROR] Step 4c (Asset Gates): {ag_diag}")
            if position_monitor:
                _threats.append(f"Asset Gates ERROR: {ag_diag}")
                _no_adds = True
                iv_guard_limit_only = True
            elif mode == "LIVE" and not active_bypass:
                return f"ERROR|S6:UNKN| Step 4c: {ag_diag[:60]}"
            else:
                print(f"[WARN] Step 4c: Asset Gates error, defaulting to LIMIT orders.")
                iv_guard_limit_only = True
        elif ag_status == "LIMIT_ONLY":
            print(f"[PASS] [STEP 4c] ASSET GATES: LIMIT_ONLY -- {ag_diag}")
            iv_guard_limit_only = True
        else:
            print(f"[PASS] [STEP 4c] ASSET GATES PASS: {ag_diag}")

        # --- 4d/4e: Event-Aware + Overheat ---
        # Automate Event-Aware (Earnings) using Radar output
        event_aware = radar_results.get("event_aware_triggered", False)

        if event_aware:
            print("[WARN] [STEP 4d] EVENT-AWARE TRIGGERED: Earnings within 10 days (Target or Super 7).")
            if position_monitor:
                _no_adds = True
                _threats.append("Earnings within 10 days: NO ADDS to position")
                print("[WARN] Step 4d: Earnings proximity -- NO ADDS mandate for held position")
        else:
            print("[PASS] [STEP 4d] EVENT-AWARE: No imminent binary events.")

        # System Overheat remains a strictly manual human-in-the-loop gate
        if mode == "LIVE":
            system_overheat = prompt_operator("4e", "System: >= 3 consecutive realized losses?")
        else:
            system_overheat = False
            print("[SKIP] [STEP 4e] BYPASSED Overheat check: INFO Mode Active")

        # ==================================================================
        # STEP 5: CLEAN TRADE AUDIT [Doc 6 / Doc 7 Step 5]
        # ==================================================================

        # [O-22] Interactive MOAT prompt for WEALTH profile when not provided via CLI.
        # Doc 6 Sec 3.1: WEALTH requires Morningstar Moat rating (Wide or Narrow).
        # Rather than halting with "provide --moat", prompt the operator in LIVE mode.
        if profile == "C" and moat is None and mode == "LIVE" and not is_etf:
            moat_input = input("   [STEP 5 PRE-GATE] WEALTH Moat Rating (WIDE/NARROW/SKIP): ").strip().upper()
            if moat_input in ("WIDE", "NARROW"):
                moat = moat_input
                print(f"[INFO] Moat set to: {moat}")
            elif moat_input == "SKIP":
                print("[WARN] Moat skipped -- fundamentals will HALT on missing moat.")
            else:
                print(f"[WARN] Invalid moat '{moat_input}' -- fundamentals will HALT on missing moat.")

        # [O-23] Retry loop: when fundamentals HALTs on missing Analyst-retrievable data,
        # prompt the operator inline and retry rather than killing the pipeline.
        # Max 5 retries handles cascading missing fields (e.g. Rev → ROIC → D/E → FCF → WACC).
        # Only prompts in LIVE mode; INFO mode halts immediately per Doc 7 Pre-Flight.
        _MAX_FUND_RETRIES = 5

        for _fund_attempt in range(_MAX_FUND_RETRIES + 1):
            print(f"[....] [STEP 5] Executing Clean Trade Audit{' (retry)' if _fund_attempt > 0 else ''}...")
            audit_status, audit_diag, audit_metrics = run_v8_clean_audit(
                ticker, profile=profile, is_etf=is_etf, wacc=wacc,
                moat=moat, roic_override=roic_override, pivot_confirmed=pivot_confirmed,
                tnx=tnx, de_override=de_override, fcf_yield_override=fcf_yield_override,
                rev_override=rev_override, eps_override=eps_override
            )

            # Check if this is a retrievable HALT that can be resolved by operator input
            _retrievable = audit_status in ("HALT (ANALYST RETRIEVE)", "HALT (MISSING DATA)", "HALT (PIVOT UNCONFIRMED)")

            if _retrievable and mode == "LIVE" and _fund_attempt < _MAX_FUND_RETRIES:
                print(f"[HALT] Step 5 (Fundamentals): {audit_diag}")
                print(f"[O-23 AI UPGRADE] Missing data detected. Delegating to Master Analyst for network retrieval.")

                _diag_upper = audit_diag.upper()
                _resolved = False

                if "MISSING DATA: REV=" in _diag_upper or ("REV=" in _diag_upper and "MASKED" in _diag_upper):
                    if rev_override is None:
                        val = retrieve_and_confirm(ticker, "Revenue Growth %")
                        if val is not None: rev_override = float(val); _resolved = True
                    if eps_override is None:
                        val = retrieve_and_confirm(ticker, "EPS Growth %")
                        if val is not None: eps_override = float(val); _resolved = True

                elif "MISSING ROIC" in _diag_upper or "ROIC IS MISSING" in _diag_upper:
                    val = retrieve_and_confirm(ticker, "ROIC %")
                    if val is not None: roic_override = float(val); _resolved = True

                elif "DEBT-TO-EQUITY" in _diag_upper:
                    val = retrieve_and_confirm(ticker, "Debt-to-Equity %")
                    if val is not None: de_override = float(val); _resolved = True

                elif "FCF YIELD" in _diag_upper:
                    val = retrieve_and_confirm(ticker, "FCF Yield %")
                    if val is not None: fcf_yield_override = float(val); _resolved = True

                elif "WACC DATA IS MISSING" in _diag_upper:
                    val = retrieve_and_confirm(ticker, "WACC %")
                    if val is not None: wacc = float(val); _resolved = True

                elif "MOAT" in _diag_upper:
                    val = retrieve_and_confirm(ticker, "Moat Rating")
                    if val in ("WIDE", "NARROW", "NONE"):
                        moat = val; _resolved = True

                # Pivot remains manual as it is strictly qualitative based on earnings calls
                elif "PIVOT NOT CONFIRMED" in _diag_upper:
                    _val = input("   Pivot confirmed manually via earnings calls? (Y/N): ").strip().upper()
                    if _val == "Y":
                        pivot_confirmed = True; _resolved = True

                if _resolved:
                    continue  # Retry Step 5 with the AI-retrieved overrides
                else:
                    break     # AI failed or Operator rejected -- fall through to HALT handling

            else:
                break  # Not retrievable, or INFO mode, or max retries -- proceed to verdict handling

        _verdicts["Fundamentals"] = (audit_status, audit_diag)

        if "HALT" in audit_status:
            print(f"[HALT] Step 5 (Fundamentals): {audit_diag}")
            if position_monitor:
                _threats.append(f"Fundamental HALT: {audit_status} -- {audit_diag}")
                _no_adds = True
            elif not active_bypass:
                return f"HALT|S6:HALT| Step 5: {audit_status}"
        elif audit_status == "WEAKENED":
            print(f"[HALT] Step 5: Asset state is WEAKENED. IMMEDIATE LOCKOUT on new capital adds.")
            if position_monitor:
                _threats.append("Fundamentals WEAKENED: capital lockout -- evaluate EXIT")
                _no_adds = True
            elif not active_bypass:
                return "HALT|S6:HALT| Step 5: WEAKENED (Capital Lockout)"
        elif audit_status.startswith("ERROR"):
            print(f"[ERROR] Step 5 (Fundamentals): {audit_diag}")
            if position_monitor:
                _threats.append(f"Fundamental ERROR: {audit_diag}")
                _no_adds = True
            else:
                return f"ERROR|S6:UNKN| Step 5: {audit_diag[:50]}"
        else:
            print(f"[PASS] [STEP 5] FUNDAMENTAL PASS: {audit_diag}")

        # ==================================================================
        # STEP 6: TECHNICAL ENGINE [Doc 2 / Doc 7 Step 6]
        # [O-16] Always runs in position monitor mode -- Exit_Signal,
        # Engine_State, ATR_Dist are the core position management metrics.
        # ==================================================================
        print(f"[....] [STEP 6] Executing Technical Engine...")
        status, diag, metrics = run_tbs_engine(ticker, profile=profile, is_etf=is_etf, mode=mode,
                                               convexity_class=convexity_class)

        _verdicts["Engine"] = (status, diag)

        if status == "HALT":
            print(f"[HALT] Step 6 (Technical): {diag}")
            if position_monitor:
                _threats.append(f"Engine HALT: {diag}")
                _no_adds = True
            elif not active_bypass:
                return "HALT|S6:HALT| Step 6: " + diag[:50]
        elif status == "ERROR":
            print(f"[ERROR] Step 6 (Technical): {diag}")
            if position_monitor:
                _threats.append(f"Engine ERROR: {diag}")
                _no_adds = True
            else:
                return f"ERROR|S6:UNKN| Step 6: {diag[:50]}"
        else:
            print(f"[PASS] [STEP 6] TECHNICAL PASS: {diag}")
            step6_passed = True

        # ==================================================================
        # STEP 3: VISUAL PROOF SUBMISSION [Doc 4 / Doc 7 Step 3]
        # [O-21] Deferred from original position (between Steps 2 and 4) to
        # after Step 6. The operator now has engine results (Engine_State,
        # Exit_Signal, floors, targets) and can meaningfully verify that
        # charts match the engine's assessment before proceeding.
        # ==================================================================
        if mode == "LIVE":
            print(f"[....] [STEP 3] Executing AI Vision Auditor for Triple-View Mandate...")

            # Execute the async AI Vision Auditor synchronously, passing engine metrics
            vision_results = asyncio.run(run_vision_audit(ticker, profile, metrics))

            vision_verdict = vision_results.get("verdict", "ERROR")
            vision_reasoning = vision_results.get("reasoning", "No reasoning provided.")

            if vision_verdict == "PASS":
                print(f"   [ANALYST RESULT] Vision Audit PASS: {vision_reasoning}")

                # [MANDATE: THE OPERATOR HUMAN VETO - DOC 4 SEC I]
                _engine_ctx = metrics.get('Engine_State', '') if step6_passed else 'ENGINE DID NOT PASS'
                _visual_q = f"Operator VETO Gate: Analyst passed visual audit. Do you confirm engine state ({_engine_ctx}) matches charts? [Doc 4]"

                if not prompt_operator(3, _visual_q):
                    if position_monitor:
                        _threats.append("Visual verification VETOED by Operator")
                        print("[WARN] Step 3: Visual verification vetoed -- flagged for position analysis")
                    else:
                        print("[HALT] Step 3 failure: Operator Veto."); return "HALT|S6:HALT| Step 3: Operator Veto"
            else:
                # The AI Vision Auditor detected a failure (e.g., ADX < 25 or masked legend)
                print(f"   [HALT] AI Vision Auditor: {vision_reasoning}")
                if position_monitor:
                    _threats.append(f"AI Vision HALT: {vision_reasoning}")
                    print("[WARN] Step 3: AI Vision failed -- flagged for position analysis")
                else:
                    print(f"[HALT] Step 3 failure: AI Vision HALT."); return f"HALT|S6:HALT| Step 3: AI Vision Halt"
        else:
            print("[SKIP] [STEP 3] BYPASSED: INFO Mode Active")

        # ==================================================================
        # [O-16] POSITION MONITOR BRANCH
        # Three-state model after Step 6 completes:
        #   EXIT:        Exit_Signal active (WARNING or EXIT) → dashboard, return
        #   NO ACTION:   _no_adds=True, Exit_Signal=false → hold, no adds, return
        #   FIT FOR ADD: _no_adds=False, Exit_Signal=false → dashboard, fall through to Steps 7-8
        # ==================================================================
        if position_monitor:
            current_price = metrics.get('Price', 0)
            stop_price = metrics.get('Hard_Stop', 0)
            structural_floor = metrics.get('Structural_Floor', 0)
            atr = metrics.get('ATR', 1.0) or 1.0

            # --- Position P&L Metrics ---
            pl_per_share = round(current_price - entry_price_override, 4)
            unrealized_pl = round(pl_per_share * shares, 2)
            pl_pct = round((pl_per_share / entry_price_override) * 100, 2) if entry_price_override else 0
            risk_from_entry = round(entry_price_override - stop_price, 4) if stop_price else 0
            r_multiple = round(pl_per_share / risk_from_entry, 2) if risk_from_entry > 0 else 0
            dist_to_stop = round(current_price - stop_price, 4) if stop_price else 0
            dist_to_stop_atr = round(dist_to_stop / atr, 2) if atr > 0 else 0
            stop_risk_remaining = round(dist_to_stop * shares, 2) if stop_price else 0

            # --- Collect engine-level threats ---
            _exit_sig = metrics.get('Exit_Signal', False)
            _exit_triggers = metrics.get('Exit_Triggers', 'None')
            _exit_vwap = metrics.get('Exit_VWAP_Counter', '')
            _engine_state = metrics.get('Engine_State', 'N/A')
            _vol_confirm = metrics.get('Vol_Confirm_State', '')
            _di_plus = metrics.get('DI_Plus', 0)
            _di_minus = metrics.get('DI_Minus', 0)

            if _exit_sig == "EXIT":
                _threats.append(f"Exit_Signal = EXIT: {_exit_triggers}")
            elif _exit_sig == "WARNING":
                _threats.append(f"Exit_Signal = WARNING: {_exit_triggers}")

            if _exit_vwap and profile == "A":
                try:
                    vwap_count = int(str(_exit_vwap).split("/")[0])
                    if vwap_count >= 2:
                        _threats.append(f"Exit_VWAP_Counter = {_exit_vwap} (approaching EXIT)")
                except (ValueError, IndexError):
                    pass

            if "DISTRIBUTION" in str(_vol_confirm):
                _threats.append(f"Vol_Confirm: {_vol_confirm} (institutional selling)")

            if _di_minus > _di_plus:
                _threats.append(f"DI: Bearish dominance (-DI {_di_minus} > +DI {_di_plus})")

            if dist_to_stop_atr < 0.5 and dist_to_stop > 0:
                _threats.append(f"Distance to stop: {dist_to_stop_atr} ATR (critically tight)")

            if "AMBIGUOUS" in str(_engine_state) or "DOWNTREND" in str(_engine_state):
                _threats.append(f"Engine_State: {_engine_state}")

            if storm_watch_active:
                _threats.append("Storm Watch active (VIX >= 25)")

            # --- Three-State Determination ---
            # The two axes are independent:
            #   Exit_Signal (position structural health) → driven by PE-28 engine
            #   _no_adds (environment fitness) → driven by Steps 1-6 pipeline verdicts
            _has_exit_signal = (_exit_sig in ("WARNING", "EXIT"))

            if _has_exit_signal:
                recommendation = "EXIT"
                rationale = f"Exit_Signal = {_exit_sig}. Position structural health deteriorating. Evaluate immediate exit or reduction."
            elif _no_adds:
                recommendation = "NO ACTION"
                rationale = "Position structure intact but environment blocks new capital. Hold current position, do not add."
            else:
                recommendation = "FIT FOR ADD"
                rationale = "All pipeline steps clear and no exit signals active. Position eligible for add sizing."

            # --- Sympathy/Asset Gates summary ---
            symp_summary = symp_metrics.get("Sympathy_Status", "N/A")
            symp_etf = symp_metrics.get("Sector_ETF", "N/A")
            symp_margin = symp_metrics.get("Sympathy_Margin_Pct", "N/A")
            iv_guard_display = ag_metrics.get("IV_Guard_Action", "N/A")

            # --- Position Monitor Dashboard ---
            _exit_display = "CLEAR" if _exit_sig == False else str(_exit_sig)
            if _exit_vwap and profile == "A":
                _exit_display += f" (VWAP: {_exit_vwap})"
            _pl_sign = "+" if unrealized_pl >= 0 else ""

            print(f"\n{'='*80}")
            print(f"***  POSITION MONITOR: {ticker} | {profile_display} | ENTRY: ${entry_price_override} x {shares} shares  ***")
            print(f"{'='*80}")
            print(f"   REGIME:       {regime}")
            print(f"   ENGINE STATE: {_engine_state}")
            # [O-28] Surface Convexity_Class in position monitor dashboard
            if convexity_class:
                _cvx_role = metrics.get('Profit_Target_Role', 'PRESCRIPTIVE')
                print(f"   CONVEXITY:    C-{convexity_class[1]} ({_cvx_role})")
            print(f"   EXIT SIGNAL:  {_exit_display}")
            if _exit_triggers and _exit_triggers != "None":
                print(f"   EXIT TRIGGERS:{_exit_triggers}")
            print(f"   SYMPATHY:     {symp_summary} (Sector: {symp_etf}, Margin: {symp_margin}%)")
            print(f"   IV GUARD:     {iv_guard_display}")
            print(f"")
            # --- TREND HEALTH [Module G] ---
            _ths_score = metrics.get('Trend_Health_Score')
            if _ths_score is not None:
                _ths_label = metrics.get('THS_Label', '')
                _ths_warn  = " [!]" if _ths_score < 40 else ""
                print(f"   --- TREND HEALTH ---")
                print(f"   TREND HEALTH: {_ths_score} / 100 ({_ths_label}){_ths_warn}")
                print(f"   │ Floor Buffer:   {metrics.get('THS_Floor_Buffer', '-')}")
                print(f"   │ Dir. Momentum:  {metrics.get('THS_Dir_Momentum', '-')}")
                print(f"   │ Trend Age:      {metrics.get('THS_Trend_Age', '-')}  (Day {metrics.get('Trend_Age_Bars', '?')})")
                print(f"   │ Structure:      {metrics.get('THS_Structure', '-')}")
                print(f"")
            print(f"   --- POSITION METRICS ---")
            print(f"   CURRENT PRICE: ${current_price}")
            print(f"   ENTRY PRICE:   ${entry_price_override}")
            print(f"   UNREALIZED PL: {_pl_sign}${unrealized_pl} ({_pl_sign}{pl_pct}%)")
            print(f"   R-MULTIPLE:    {r_multiple}R")
            print(f"   STRUCT FLOOR:  ${structural_floor}")
            print(f"   HARD STOP:     ${stop_price}")
            print(f"   DIST TO STOP:  ${dist_to_stop} ({dist_to_stop_atr} ATR)")
            print(f"   STOP RISK:     ${stop_risk_remaining}")
            print(f"")
            print(f"   --- PIPELINE VERDICTS ---")
            for step_name, (v_status, v_detail) in _verdicts.items():
                _v_label = "PASS" if v_status in ("PASS", "EXEMPT") else v_status
                print(f"   {step_name.upper():14s}: {_v_label} ({v_detail[:50]})")
            print(f"")
            if _threats:
                print(f"   --- THREAT SUMMARY ---")
                for t in _threats:
                    print(f"   [!] {t}")
                print(f"")
            print(f"   RECOMMENDATION: {recommendation}")
            print(f"   Rationale: {rationale}")
            print(f"{'='*80}\n")

            # --- EXIT and NO ACTION terminate here ---
            if recommendation == "EXIT":
                return f"MONITOR|EXIT| {regime} | PL: {_pl_sign}${unrealized_pl} ({_pl_sign}{pl_pct}%) | R: {r_multiple}R"
            if recommendation == "NO ACTION":
                return f"MONITOR|NO_ACTION| {regime} | PL: {_pl_sign}${unrealized_pl} ({_pl_sign}{pl_pct}%) | R: {r_multiple}R"

            # --- FIT FOR ADD: fall through to Steps 7-8 for add sizing ---
            print(f"[....] [STEP 7-8] FIT FOR ADD confirmed. Proceeding to add sizing...")

        # [SC-9 FIX] Dashboard only for Step-6-cleared candidates.
        if not step6_passed:
            if mode == "INFO":
                return f"PASS|S6:HALT| {regime} | Entry: ${metrics.get('Price', 0)} | Stop: ${metrics.get('Hard_Stop', 0)}"
            else:
                return "HALT|S6:HALT| Step 6: Technical Engine did not clear."

        # ==================================================================
        # STEP 7 & 8: SIZING & FINAL AUTH [Doc 3 / Doc 7 Steps 7-8]
        # ==================================================================
        multiplier = 1.0
        mod_log = []

        if "DEFENSIVE" in regime:
            multiplier *= 0.5; mod_log.append("Defensive Regime (0.5x)")
        if event_aware:
            multiplier *= 0.5; mod_log.append("Event-Aware <10d (0.5x)")
        if "TURNAROUND" in audit_status:
            multiplier *= 0.5; mod_log.append("Turnaround Patch (0.5x)")
        if storm_watch_active:
            multiplier *= 0.5; mod_log.append("Storm Watch VIX >= 25 (0.5x)")
        if system_overheat:
            multiplier *= 0.5; mod_log.append("System Overheat: Recent Streak (0.5x)")
        if "LOW" in metrics.get("Conviction", ""):
            multiplier *= 0.5; mod_log.append("Low-Conviction Range (0.5x)")
        if "ACTIVE" in metrics.get("Inst_Churn", ""):
            multiplier *= 0.5; mod_log.append("Inst. Churn/Modifier D (0.5x)")

        sizing_msg = f"{multiplier * 100}%" if mode == "LIVE" else (f"{multiplier * 100}% (PREVIEW)" if capital_override else "BYPASSED (INFO MODE)")

        # --- EXECUTION METRICS SYNC ---
        entry_price = metrics.get('Price', 0)
        stop_price = metrics.get('Hard_Stop', 0)
        structural_floor = metrics.get('Structural_Floor', 0)
        window_val = metrics.get('window_count', 'N/A')
        floor_type = metrics.get('Anchor_Type', 'Standard')

        # [O-10] Order type: IV Guard overrides default
        if iv_guard_limit_only:
            order_type = "LIMIT"
        elif "WEAKENED" in audit_status or "TERMINATED" in audit_status:
            order_type = "MARKET"
        else:
            order_type = "LIMIT"

        risk_per_share = round(entry_price - stop_price, 2) if stop_price else 0
        target_price = "N/A"
        dynamic_label, dynamic_val = "INFO", "N/A"

        # [O-14] Use engine-computed Profit_Target and Reward_Risk directly.
        # The engine already accounts for suppression, floor proximity sentinels,
        # context chart targets, and PE-28 graduated exit states. Recomputing
        # from raw Resistance/EMA produces numbers that disagree with engine output.
        engine_target = metrics.get('Profit_Target')
        engine_rr = metrics.get('Reward_Risk')

        if profile == "A":
            if engine_rr is not None and engine_target is not None:
                dynamic_label = "EXPECTANCY"
                if engine_rr == 9999.0:
                    dynamic_val = "FLOOR_EXACT (R:R maximal)"
                else:
                    dynamic_val = f"{engine_rr}:1"
                target_price = engine_target
                # Surface target source for operator context
                target_src = metrics.get('Profit_Target_Source', '')
                if target_src:
                    dynamic_val += f" ({target_src})"
            else:
                dynamic_label, dynamic_val = "EXPECTANCY", "SUPPRESSED (Exit_Signal or price > resistance)"
        elif profile == "B":
            ema8 = metrics.get('EMA_8', entry_price)
            atr = metrics.get('ATR', 1.0)
            extension = round((entry_price - ema8) / atr, 2) if atr > 0 else 0
            dynamic_label, dynamic_val = "EXTENSION", f"{extension} ATR"
            # [O-14] Use engine's Profit_Target (10-bar Resistance) as primary target.
            # Fall back to Profit_Target_Synthetic (Floor + 1.5 ATR) if Resistance suppressed.
            if engine_target is not None:
                target_price = engine_target
            elif metrics.get('Profit_Target_Synthetic') is not None:
                target_price = metrics.get('Profit_Target_Synthetic')
            else:
                target_price = "SUPPRESSED"
        elif profile == "C":
            sma200 = metrics.get('SMA_200', entry_price)
            proximity = round(abs(entry_price - sma200) / sma200 * 100, 2) if sma200 > 0 else 0
            dynamic_label, dynamic_val = "PROXIMITY", f"{proximity}% (200-SMA)"
            target_price = "OPEN-ENDED"

        # --- FINAL EXECUTION DASHBOARD [DOC 7] ---
        window_limits = {"A": "0-4", "B": "0-5", "C": "0-2"}

        # [O-12] Sympathy + Asset Gates summary
        symp_summary = symp_metrics.get("Sympathy_Status", "N/A")
        symp_etf = symp_metrics.get("Sector_ETF", "N/A")
        symp_margin = symp_metrics.get("Sympathy_Margin_Pct", "N/A")
        iv_guard_display = ag_metrics.get("IV_Guard_Action", "N/A")
        div_status = "CLEAR" if not ag_metrics.get("Dividend_Lockout", False) else "BLOCKED"

        print(f"\n{'='*80}")
        if position_monitor:
            print(f"***  ADD SIZING: {ticker} | Existing: ${entry_price_override} x {shares} shares  ***")
        else:
            print(f"***  FINAL STRATEGY ALIGNMENT: {ticker} ***")
        print(f"{'='*80}")
        print(f"   REGIME:       {regime}")
        print(f"   ENGINE STATE: {metrics.get('Engine_State', 'N/A')}")
        # [O-28] Surface Convexity_Class in operator dashboard
        if convexity_class:
            _cvx_role = metrics.get('Profit_Target_Role', 'PRESCRIPTIVE')
            print(f"   CONVEXITY:    C-{convexity_class[1]} ({_cvx_role})")
        print(f"   WINDOW:       Window {window_val} (Mandate: {window_limits.get(profile, '0-5')})")
        print(f"   FLOOR TYPE:   {floor_type}")
        # [O-15] Surface PE-28 graduated Exit_Signal prominently
        _exit_sig = metrics.get('Exit_Signal', False)
        _exit_display = "CLEAR" if _exit_sig == False else str(_exit_sig)
        _exit_vwap = metrics.get('Exit_VWAP_Counter', '')
        if _exit_vwap and profile == "A":
            _exit_display += f" (VWAP: {_exit_vwap})"
        print(f"   EXIT SIGNAL:  {_exit_display}")
        print(f"   SYMPATHY:     {symp_summary} (Sector: {symp_etf}, Margin: {symp_margin}%)")
        print(f"   IV GUARD:     {iv_guard_display}")
        print(f"   DIVIDEND:     {div_status}")
        _action_label = f"ADD {order_type} ORDER" if position_monitor else f"EXECUTE {order_type} ORDER"
        print(f"   ACTION:       {_action_label}")
        print(f"   SIZING:       {sizing_msg} of Base Unit")
        if mod_log: print(f"   MODIFIERS:    {', '.join(mod_log)}")
        print(f"   {dynamic_label.ljust(13)}: {dynamic_val}")
        print(f"   ENTRY PRICE:  ${entry_price}")
        print(f"   STRUCT FLOOR: ${structural_floor}")
        print(f"   HARD STOP:    ${stop_price} (Floor - 1.5 ATR)")
        print(f"   TARGET:       ${target_price}")
        print(f"   RISK/SHARE:   ${risk_per_share}")
        print(f"{'='*80}\n")

        if mode == "INFO" and capital_override is None:
            _info_prefix = "MONITOR|FIT_FOR_ADD" if position_monitor else "PASS|S6:PASS"
            return f"{_info_prefix}| {regime} | W{window_val} | Entry: ${entry_price} | Stop: ${stop_price}"

        # ==================================================================
        # STEP 7: SIZING [Doc 3 / Doc 7 Step 7]
        # [O-18] Runs in LIVE mode always, and in INFO mode when --capital provided.
        # ==================================================================

        # [O-17] Capital source priority: CLI override > IBKR account > fallback
        if capital_override is not None:
            total_net_worth = capital_override
            print(f"   [CAPITAL] Using CLI override: ${total_net_worth:,.2f}")
        elif mode == "LIVE":
            try:
                account_summary = ib.accountSummary()
                net_worth_item = next((item for item in account_summary if item.tag == 'NetLiquidation'), None)
                total_net_worth = float(net_worth_item.value) if net_worth_item else 10000.0
            except Exception:
                total_net_worth = 10000.0
        else:
            total_net_worth = 10000.0  # Should not reach here, but safe fallback

        risk_pct = 0.0025 if profile == "A" else 0.005
        base_units = (total_net_worth * risk_pct) / risk_per_share if risk_per_share > 0 else 0
        final_units = int(base_units * multiplier)

        total_capital_outlay = final_units * entry_price
        max_cash_cap = total_net_worth * 0.25

        if profile == "B" and total_capital_outlay > (total_net_worth * 0.01):
            final_units = int((total_net_worth * 0.01) / entry_price)
        elif total_capital_outlay > max_cash_cap:
            final_units = int(max_cash_cap / entry_price)

        open_risk_heat = final_units * risk_per_share

        if open_risk_heat < 50:
            print(f"[HALT] UTILITY HALT: Open Risk (${open_risk_heat:.2f}) < $50.")
            return "HALT|S6:PASS| Step 7: Utility Gate (Heat < 50)"

        _sizing_label = "ADD SIZING" if position_monitor else "FINAL SIZING"
        _sizing_mode = "(PREVIEW)" if mode == "INFO" else ""
        print(f"   {_sizing_label} {_sizing_mode}: {final_units} Units (Capital: ${final_units * entry_price:.2f} | Risk: ${open_risk_heat:.2f})")

        if position_monitor:
            _new_total = shares + final_units
            _avg_cost = round(((entry_price_override * shares) + (entry_price * final_units)) / _new_total, 4)
            _new_risk = round(_new_total * risk_per_share, 2)
            print(f"   EXISTING:     {shares} shares @ ${entry_price_override}")
            print(f"   AFTER ADD:    {_new_total} shares @ ${_avg_cost} avg cost")
            print(f"   COMBINED RISK:${_new_risk}")

        # INFO mode with --capital: sizing preview complete, return
        if mode == "INFO":
            _info_prefix = "MONITOR|FIT_FOR_ADD" if position_monitor else "PASS|S6:PASS"
            return f"{_info_prefix}| {regime} | W{window_val} | Entry: ${entry_price} | Stop: ${stop_price} | Units: {final_units}"

        # ==================================================================
        # STEP 8: THE AUTOMATED BRACKET ROUTER (LIVE only)
        # ==================================================================
        if mode == "LIVE":
            _exec_label = f"AUTHORIZE ADD of {final_units} units to existing {shares}-share position" if position_monitor else f"AUTHORIZE LIVE EXECUTION of {final_units} units"
            if prompt_operator(8, f"{_exec_label}?"):
                print(f"[EXEC] [TRANSMITTING] Routing Bracket Order to IBKR...")
                contract = resolved_contract

                # # Fire the deterministic bracket order
                # trades = execute_bracket_order(
                #     ib=ib, contract=contract, action="BUY",
                #     quantity=final_units, order_type=order_type,
                #     entry_price=entry_price, hard_stop_price=stop_price,
                #     target_price=target_price if target_price not in ["OPEN-ENDED", "N/A"] else None
                # )
                # print("[PASS] [EXECUTED] Bracket Order Transmitted successfully.")
                # for t in trades:
                #     print(f"   -> Order ID: {t.order.orderId} | Status: {t.orderStatus.status}")
            else:
                print("[HALT] Operator Vetoed Execution at Final Gate.")
                return "HALT|S6:PASS| Step 8: Operator Veto"

    except Exception as e:
        print(f"[ERROR] Orchestrator Failure: {str(e)}")
        return f"ERROR|S6:UNKN| {str(e)[:60]}"
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    if not verify_chart_engine():
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="TBS v8.3.2 Master Orchestrator -- Full 8-Step Pipeline"
    )
    # Core args
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--profile", default="TREND",
                        choices=["SWING", "TREND", "WEALTH", "A", "B", "C"],
                        help="Trade profile (A=SWING, B=TREND, C=WEALTH).")
    parser.add_argument("--mode", default="INFO", choices=["INFO", "LIVE"])
    parser.add_argument("--bypass_macro", action="store_true")
    parser.add_argument("--etf", action="store_true",
                        help="Advisory ETF flag (engine auto-detects; this forces True).")

    # Fundamental overrides (Doc 6 / Doc 8 Sec V)
    parser.add_argument("--wacc", type=float, default=None,
                        help="WACC override for Turnaround Patch.")
    parser.add_argument("--moat", type=str, default=None,
                        help="Moat rating for WEALTH (Wide or Narrow).")
    parser.add_argument("--roic", type=float, default=None,
                        help="Manual ROIC percent override (Analyst-retrieved).")
    parser.add_argument("--rev", type=float, default=None,
                        help="Manual Revenue Growth percent override. Example: --rev 6.8")
    parser.add_argument("--eps", type=float, default=None,
                        help="Manual EPS Growth percent override. Example: --eps 8.5")
    parser.add_argument("--de", type=float, default=None,
                        help="Manual Debt-to-Equity percent override. Example: --de 139.8")
    parser.add_argument("--fcf-yield", type=float, default=None,
                        help="Manual FCF Yield percent override. Example: --fcf-yield 3.5")
    parser.add_argument("--tnx", type=float, default=None,
                        help="Current 10-Year Treasury Yield for FCF comparison.")
    parser.add_argument("--pivot-confirmed", action="store_true",
                        help="Confirm guidance revisions for Turnaround Patch.")

    # Sympathy override (Doc 5 Sec 3.1 / Doc 8 Layer 1.5a)
    parser.add_argument("--sector-etf", default=None,
                        help="Manual sector ETF override for Sympathy Audit (e.g. XLE, XLK).")

    # [O-16] Position Monitor flags
    parser.add_argument("--entry-price", type=float, default=None,
                        help="Original entry price for position monitoring (enables MONITOR mode).")
    parser.add_argument("--shares", type=int, default=None,
                        help="Number of shares held (required with --entry-price for MONITOR mode).")

    # [O-17] Capital override
    parser.add_argument("--capital", type=float, default=None,
                        help="Total portfolio net worth override for sizing (bypasses IBKR account query).")

    # [O-25] Convexity classification (Redesign Proposal §6.3 / Scanner Spec §3.3)
    parser.add_argument("--convexity", type=str, default=None,
                        choices=["C1", "C2", "C3"],
                        help="Convexity class override (C1/C2/C3). Overrides classifications.json.")

    args = parser.parse_args()

    # [O-16] Validate position monitor flags are paired
    _ep = getattr(args, 'entry_price', None)
    _sh = args.shares
    if (_ep is not None) != (_sh is not None):
        parser.error("--entry-price and --shares must be provided together for Position Monitor mode.")

    execute_v8_pipeline(
        args.ticker.upper(), args.profile.upper(), args.mode.upper(),
        bypass_macro=args.bypass_macro, wacc=args.wacc,
        moat=args.moat, roic_override=args.roic, pivot_confirmed=args.pivot_confirmed,
        tnx=args.tnx, de_override=args.de,
        fcf_yield_override=getattr(args, 'fcf_yield', None),
        rev_override=args.rev, eps_override=args.eps,
        sector_etf_override=args.sector_etf, is_etf_flag=args.etf,
        entry_price_override=getattr(args, 'entry_price', None),
        shares=args.shares,
        capital_override=args.capital,
        convexity_class=args.convexity
    )
