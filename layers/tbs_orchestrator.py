import argparse
import sys
from ib_insync import IB, Stock, Contract

# -----------------------------
# TBS MASTER ORCHESTRATOR (Layer 3) v8.3.1
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


def execute_v8_pipeline(ticker, profile="TREND", mode="INFO", bypass_macro=False,
                        wacc=None, moat=None, roic_override=None, pivot_confirmed=False,
                        # [O-9] v8.3.1 passthrough args
                        tnx=None, de_override=None, fcf_yield_override=None,
                        rev_override=None, eps_override=None,
                        sector_etf_override=None, is_etf_flag=False):

    # [SC-5 FIX] Normalize profile aliases to internal codes (A/B/C).
    profile_map = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    profile = profile_map.get(profile.upper(), "B")

    port = 4001 if mode == "LIVE" else 4002
    ib = IB()
    active_bypass = (mode == "INFO" and bypass_macro)

    profile_names = {"A": "SWING", "B": "TREND", "C": "WEALTH"}
    profile_display = f"{profile} ({profile_names.get(profile, 'UNKNOWN')})"
    print(f"\n{'='*80}\nTBS v8.3.1 MASTER ORCHESTRATOR: {ticker} | {profile_display} | MODE: {mode}")
    if active_bypass: print("[WARN] BYPASS ACTIVE: Observing full pipeline despite Logic Halts.")
    print(f"{'='*80}")

    try:
        ib.connect('127.0.0.1', port, clientId=100)
        ib.reqMarketDataType(1)
        step6_passed = False

        # ==================================================================
        # STEP 1: SYSTEMIC PERMISSION (The Sentinel) [Doc 5 / Doc 7 Step 1]
        # ==================================================================
        regime, verdict, reason, storm_watch_active, sentinel_details = run_tbs_sentinel(
            ib_connection=ib, port=port, profile=profile
        )

        if verdict in ["HALT", "FORCE HARVEST"] and not active_bypass:
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

        # AUTO-ID: Deterministic Asset Classification
        is_etf, resolved_contract = get_asset_type(ib, ticker)
        if is_etf_flag:
            is_etf = True
        print(f"[SCAN] [AUTO-ID] Asset identified as: {'ETF/Index' if is_etf else 'Standard Equity'}")

        # ==================================================================
        # STEP 2: PORTFOLIO PERMISSION (The Governor) [Doc 3 / Doc 7 Step 2]
        # Bypassed in INFO mode per Doc 7 Pre-Flight.
        # ==================================================================
        if mode == "LIVE":
            if not prompt_operator(2, "Portfolio: Heat < 5% & Slots Open? [Doc 3]"):
                print("[HALT] Step 2 failure."); return "HALT|S6:HALT| Step 2: Portfolio Capacity"
        else:
            print("[SKIP] [STEP 2] BYPASSED: INFO Mode Active")

        # ==================================================================
        # STEP 3: VISUAL PROOF SUBMISSION [Doc 4 / Doc 7 Step 3]
        # ==================================================================
        if mode == "LIVE":
            if not prompt_operator(3, "Visual: Triple-View Mandate verified? [Doc 4]"):
                print("[HALT] Step 3 failure."); return "HALT|S6:HALT| Step 3: Triple-View Not Verified"
        else:
            print("[SKIP] [STEP 3] BYPASSED: INFO Mode Active")

        # ==================================================================
        # STEP 4: ASSET PERMISSION [Doc 5 Sec 3 / Doc 7 Step 4]
        #
        #   4a: Integrity Shocks (qualitative — LIVE only)
        #   4b: Sympathy Audit (automated — BOTH modes)   [O-7]
        #   4c: Asset Gates: IV + Dividend (auto — BOTH)   [O-8]
        #   4d: Event-Aware / Earnings (qualitative — LIVE)
        #   4e: Overheat Switch (qualitative — LIVE)
        # ==================================================================

        event_aware, system_overheat = False, False
        iv_guard_limit_only = False    # [O-10] Propagated to order_type

        # --- 4a: Integrity Shocks (LIVE only — non-quantifiable) ---
        if mode == "LIVE":
            if not prompt_operator("4a", "Radar: Integrity Shocks clear? [Doc 5 Sec 3.3]"):
                print("[HALT] Step 4a: Integrity Shock detected.")
                return "HALT|S6:HALT| Step 4a: Integrity Shock"

        # --- 4b: SYMPATHY AUDIT [Doc 5 Sec 3.1 / Doc 8 Layer 1.5a] ---
        # [O-7 FIX] Replaces previous manual prompt_operator() with automated
        # ibkr_sympathy_audit.py. Runs in BOTH modes per Doc 8 Layer 1.5.
        print(f"[....] [STEP 4b] Executing Sympathy Audit...")
        symp_status, symp_diag, symp_metrics = run_sympathy_audit(
            ticker, profile=profile,
            sector_etf_override=sector_etf_override,
            mode=mode
        )

        if symp_status == "HALT":
            print(f"[HALT] Step 4b (Sympathy): {symp_diag}")
            if not active_bypass:
                return f"HALT|S6:HALT| Step 4b: {symp_diag[:60]}"
        elif symp_status == "ERROR":
            print(f"[ERROR] Step 4b (Sympathy): {symp_diag}")
            if not active_bypass:
                return f"ERROR|S6:UNKN| Step 4b: {symp_diag[:60]}"
        elif symp_status == "SKIPPED":
            print(f"[WARN] [STEP 4b] SYMPATHY SKIPPED: {symp_diag}")
        elif symp_status == "EXEMPT":
            print(f"[PASS] [STEP 4b] SYMPATHY EXEMPT: {symp_diag}")
        else:
            print(f"[PASS] [STEP 4b] SYMPATHY PASS: {symp_diag}")

        # --- 4c: ASSET GATES [Doc 5 Sec 3.2 / Doc 8 Layer 1.5b] ---
        # [O-8 FIX] Wires automated ibkr_asset_gates.py. IV Guard result
        # propagates to order_type; Dividend Lockout = hard HALT.
        print(f"[....] [STEP 4c] Executing Asset Gates (IV Guard + Dividend Lockout)...")
        ag_status, ag_diag, ag_metrics = run_asset_gates(
            ticker, profile=profile, mode=mode
        )

        if ag_status == "BLOCKED":
            print(f"[HALT] Step 4c (Asset Gates): {ag_diag}")
            return f"HALT|S6:HALT| Step 4c: DIVIDEND LOCKOUT"
        elif ag_status == "ERROR":
            print(f"[ERROR] Step 4c (Asset Gates): {ag_diag}")
            if mode == "LIVE" and not active_bypass:
                return f"ERROR|S6:UNKN| Step 4c: {ag_diag[:60]}"
            else:
                print(f"[WARN] Step 4c: Asset Gates error in INFO mode, defaulting to LIMIT orders.")
                iv_guard_limit_only = True
        elif ag_status == "LIMIT_ONLY":
            print(f"[PASS] [STEP 4c] ASSET GATES: LIMIT_ONLY -- {ag_diag}")
            iv_guard_limit_only = True
        else:
            print(f"[PASS] [STEP 4c] ASSET GATES PASS: {ag_diag}")

        # --- 4d/4e: Event-Aware + Overheat (LIVE only) ---
        if mode == "LIVE":
            event_aware = prompt_operator("4d", "Event: Earnings/Dividend within 10 days?")
            system_overheat = prompt_operator("4e", "System: >= 3 consecutive realized losses?")
        else:
            print("[SKIP] [STEPS 4d-4e] BYPASSED: INFO Mode Active")

        # ==================================================================
        # STEP 5: CLEAN TRADE AUDIT [Doc 6 / Doc 7 Step 5]
        # ==================================================================
        print(f"[....] [STEP 5] Executing Clean Trade Audit...")
        # [O-9 FIX] Pass all v8.3.1 override args
        audit_status, audit_diag, audit_metrics = run_v8_clean_audit(
            ticker, profile=profile, is_etf=is_etf, wacc=wacc,
            moat=moat, roic_override=roic_override, pivot_confirmed=pivot_confirmed,
            tnx=tnx, de_override=de_override, fcf_yield_override=fcf_yield_override,
            rev_override=rev_override, eps_override=eps_override
        )

        if "HALT" in audit_status:
            print(f"[HALT] Step 5 (Fundamentals): {audit_diag}")
            if not active_bypass: return f"HALT|S6:HALT| Step 5: {audit_status}"
        elif audit_status == "WEAKENED":
            print(f"[HALT] Step 5: Asset state is WEAKENED. IMMEDIATE LOCKOUT on new capital adds.")
            if not active_bypass: return "HALT|S6:HALT| Step 5: WEAKENED (Capital Lockout)"
        elif audit_status.startswith("ERROR"):
            print(f"[ERROR] Step 5 (Fundamentals): {audit_diag}")
            return f"ERROR|S6:UNKN| Step 5: {audit_diag[:50]}"
        else:
            print(f"[PASS] [STEP 5] FUNDAMENTAL PASS: {audit_diag}")

        # ==================================================================
        # STEP 6: TECHNICAL ENGINE [Doc 2 / Doc 7 Step 6]
        # ==================================================================
        print(f"[....] [STEP 6] Executing Technical Engine...")
        status, diag, metrics = run_tbs_engine(ticker, profile=profile, is_etf=is_etf, mode=mode)

        if status == "HALT":
            print(f"[HALT] Step 6 (Technical): {diag}")
            if not active_bypass: return "HALT|S6:HALT| Step 6: " + diag[:50]
        elif status == "ERROR":
            print(f"[ERROR] Step 6 (Technical): {diag}")
            return f"ERROR|S6:UNKN| Step 6: {diag[:50]}"
        else:
            print(f"[PASS] [STEP 6] TECHNICAL PASS: {diag}")
            step6_passed = True

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

        sizing_msg = f"{multiplier * 100}%" if mode == "LIVE" else "BYPASSED (INFO MODE)"

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

        if profile == "A":
            resistance = metrics.get('Resistance', entry_price)
            if resistance:
                reward = resistance - entry_price
                expectancy = round(reward / risk_per_share, 2) if risk_per_share > 0 else 0
                dynamic_label, dynamic_val = "EXPECTANCY", f"{expectancy}:1"
                target_price = round(resistance, 2)
            else:
                dynamic_label, dynamic_val = "EXPECTANCY", "SUPPRESSED (price > resistance)"
        elif profile == "B":
            ema8 = metrics.get('EMA_8', entry_price)
            atr = metrics.get('ATR', 1.0)
            extension = round((entry_price - ema8) / atr, 2) if atr > 0 else 0
            dynamic_label, dynamic_val = "EXTENSION", f"{extension} ATR"
            target_price = round(entry_price + (atr * 1.5), 2)
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

        print(f"\n{'='*80}\n***  FINAL STRATEGY ALIGNMENT: {ticker} ***\n{'='*80}")
        print(f"   REGIME:       {regime}")
        print(f"   WINDOW:       Window {window_val} (Mandate: {window_limits.get(profile, '0-5')})")
        print(f"   FLOOR TYPE:   {floor_type}")
        print(f"   SYMPATHY:     {symp_summary} (Sector: {symp_etf}, Margin: {symp_margin}%)")
        print(f"   IV GUARD:     {iv_guard_display}")
        print(f"   DIVIDEND:     {div_status}")
        print(f"   ACTION:       EXECUTE {order_type} ORDER")
        print(f"   SIZING:       {sizing_msg} of Base Unit")
        if mod_log: print(f"   MODIFIERS:    {', '.join(mod_log)}")
        print(f"   {dynamic_label.ljust(13)}: {dynamic_val}")
        print(f"   ENTRY PRICE:  ${entry_price}")
        print(f"   STRUCT FLOOR: ${structural_floor}")
        print(f"   HARD STOP:    ${stop_price} (Floor - 1.5 ATR)")
        print(f"   TARGET:       ${target_price}")
        print(f"   RISK/SHARE:   ${risk_per_share}")
        print(f"{'='*80}\n")

        if mode == "INFO":
            return f"PASS|S6:PASS| {regime} | W{window_val} | Entry: ${entry_price} | Stop: ${stop_price}"

        # ==================================================================
        # STEP 8: THE AUTOMATED BRACKET ROUTER (LIVE only)
        # ==================================================================
        if mode == "LIVE":
            try:
                account_summary = ib.accountSummary()
                net_worth_item = next((item for item in account_summary if item.tag == 'NetLiquidation'), None)
                total_net_worth = float(net_worth_item.value) if net_worth_item else 10000.0
            except Exception:
                total_net_worth = 10000.0

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

            print(f"   FINAL SIZING: {final_units} Units (Capital: ${final_units * entry_price:.2f} | Risk: ${open_risk_heat:.2f})")

            if prompt_operator(8, f"AUTHORIZE LIVE EXECUTION of {final_units} units?"):
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
        description="TBS v8.3.1 Master Orchestrator -- Full 8-Step Pipeline"
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

    args = parser.parse_args()

    execute_v8_pipeline(
        args.ticker.upper(), args.profile.upper(), args.mode.upper(),
        bypass_macro=args.bypass_macro, wacc=args.wacc,
        moat=args.moat, roic_override=args.roic, pivot_confirmed=args.pivot_confirmed,
        tnx=args.tnx, de_override=args.de,
        fcf_yield_override=getattr(args, 'fcf_yield', None),
        rev_override=args.rev, eps_override=args.eps,
        sector_etf_override=args.sector_etf, is_etf_flag=args.etf
    )
