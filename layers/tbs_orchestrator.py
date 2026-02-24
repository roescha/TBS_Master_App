import argparse
import sys
from ib_insync import IB, Stock, Contract

# -----------------------------
# TBS MASTER ORCHESTRATOR (Layer 3) v8.3
# Pipeline Execution, Governor Sizing, Bracket Order Routing
# Bug fixes: O-1 (sentinel profile passthrough), O-2 (shared IB connection),
#            O-4 (window mandate), O-5 (moat/roic/pivot args), O-6 (contract routing),
#            SC-5 (profile normalization SWING/TREND/WEALTH -> A/B/C),
#            SC-6 (ERROR status from engine/fundamentals treated as PASS),
#            SC-9 (dashboard gated on step6_passed)
# -----------------------------

# TBS Layer Imports
from ibkr_sentinel import run_tbs_sentinel
from yahoo_fundamentals import run_v8_clean_audit
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

    # ==========================================
    # LEG 1: THE PARENT ENTRY ORDER
    # ==========================================
    if order_type == "LIMIT":
        parent = LimitOrder(action, quantity, entry_price)
    else:
        # Defaults to MARKET if Reclaim/Exiting or IV is favorable
        parent = MarketOrder(action, quantity)

    parent.orderId = ib.client.getReqId()
    # Parent transmit must be False because children need to be attached first
    parent.transmit = False
    orders_to_submit.append(parent)

    # ==========================================
    # LEG 2: THE MATHEMATICAL HARD STOP
    # ==========================================
    # This locks in the Structural Floor - (1.5 * ATR) calculation
    stop_order = StopOrder(reverse_action, quantity, hard_stop_price)
    stop_order.parentId = parent.orderId

    # If there is no profit target (e.g., Profile C), the Stop is the final leg
    stop_order.transmit = True if target_price in [None, "OPEN-ENDED", "N/A"] else False
    orders_to_submit.append(stop_order)

    # ==========================================
    # LEG 3: THE EXPECTANCY TARGET (Optional)
    # ==========================================
    if target_price not in [None, "OPEN-ENDED", "N/A"]:
        target_order = LimitOrder(reverse_action, quantity, float(target_price))
        target_order.parentId = parent.orderId
        target_order.transmit = True # Final leg transmits the entire bracket
        orders_to_submit.append(target_order)

    # ==========================================
    # EXECUTION
    # ==========================================
    trades = []
    # for order in orders_to_submit:
    #     trade = ib.placeOrder(contract, order)
    #    trades.append(trade)

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
        # FIX: Updated to align with Plotly's modern serialization requirements
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

    # LAYER 1: DETERMINISTIC SUFFIX CHECK (The Fail-Safe)
    # REMOVED: Deterministic .L suffix check to prevent Equity misidentification

    # LAYER 2: IBKR METADATA AUDIT
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
            # If the name contains these keywords, it is an ETF.
            # [MANDATE: DOC 8] Expanded Keywords to catch SPDR (SS), Invesco, and Schwab
            etf_keywords = ['ETF', 'FUND', 'VANGUARD', 'ISHARES', 'UCITS', 'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES']
            if any(key in meta for key in etf_keywords):
                return True, contract
    except Exception:
        pass

    return False, contract


def execute_v8_pipeline(ticker, profile="TREND", mode="INFO", bypass_macro=False, wacc=None, moat=None, roic_override=None, pivot_confirmed=False):
    # [SC-5 FIX] Normalize profile aliases to internal codes (A/B/C).
    # All downstream logic (dashboard, window_limits, risk_pct, sizing caps)
    # compares against A/B/C. Without this, named profiles silently fall through.
    profile_map = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    profile = profile_map.get(profile.upper(), "B")  # Default B if unrecognized

    port = 4001 if mode == "LIVE" else 4002
    ib = IB()
    active_bypass = (mode == "INFO" and bypass_macro)

    profile_names = {"A": "SWING", "B": "TREND", "C": "WEALTH"}
    profile_display = f"{profile} ({profile_names.get(profile, 'UNKNOWN')})"
    print(f"\n{'='*80}\nTBS v8.3 MASTER ORCHESTRATOR: {ticker} | {profile_display} | MODE: {mode}")
    if active_bypass: print("[WARN] BYPASS ACTIVE: Observing full pipeline despite Logic Halts.")
    print(f"{'='*80}")

    try:
        ib.connect('127.0.0.1', port, clientId=100)

        # [MANDATE: SCANNER FILTER] Tracks whether Step 6 Technical Engine issued a PASS.
        # Used by tbs_scanner.py to include only Step-6-cleared tickers in the summary table.
        step6_passed = False

        # --- [MANDATE: DOC 5 SEC 134 & DOC 3 SEC 88] SYSTEMIC PERMISSION ---
        # [O-1 FIX] Pass profile for correct confirmation timeframe (A=hourly, B=daily, C=weekly)
        regime, verdict, reason, storm_watch_active, sentinel_details = run_tbs_sentinel(
            ib_connection=ib, port=port, profile=profile
        )

        # [MANDATE: DOC 3 SEC 92] LIQUIDATION WATERFALL TRIGGER
        # If macro regime requires capital harvesting, output the deterministic ladder
        if verdict in ["HALT", "FORCE HARVEST"] and not active_bypass:
            print(f"[HALT] Step 1: {reason} (Regime: {regime})")

            if verdict == "FORCE HARVEST" or "RESTRICTED" in regime:
                print(f"\n{'!'*30} [MANDATE: LIQUIDATION WATERFALL] {'!'*30}")
                print("   Regime mandates a 50% CASH FLOOR. Harvest capital in this order:")
                print("   1. TIER 1 (TERMINAL): Immediate exit of all assets in BROKEN/TERMINATED or WEAK/VULNERABLE states [Doc 3].")
                print("   2. TIER 2 (NON-CORE): Harvest ALL Profile A (Swing). Harvest Profile B (Trend) closest to Daily 50-SMA [Doc 3].")
                print("   3. TIER 3 (EFFICIENCY): Liquidate Profile C assets currently in Structural Floor Violation [Doc 3].")
                print(f"{'!'*80}\n")
            return "HALT|S6:HALT| Step 1: " + regime

        if verdict != "PASS" and active_bypass:
            print(f"[WARN] [MACRO HALT BYPASSED] Step 1 reported {verdict}.")
        else:
            print(f"[PASS] [STEP 1] SENTINEL PASS: {regime}")

        # AUTO-ID: Deterministic Asset Classification
        # [O-6 FIX] Unpack resolved contract for reuse in bracket orders
        is_etf, resolved_contract = get_asset_type(ib, ticker)
        print(f"[SCAN] [AUTO-ID] Asset identified as: {'ETF/Index' if is_etf else 'Standard Equity'}")

        # STEPS 2-4: OPERATOR GATES (LIVE MODE ONLY)
        event_aware, system_overheat = False, False
        if mode == "LIVE":
            if not prompt_operator(2, "Portfolio: Heat < 5% & Slots Open? [Doc 3]"):
                print("[HALT] Step 2 failure."); return "HALT|S6:HALT| Step 2: Portfolio Capacity"
            if not prompt_operator(3, "Visual: Triple-View Mandate verified? [Doc 4]"):
                print("[HALT] Step 3 failure."); return "HALT|S6:HALT| Step 3: Triple-View Not Verified"

            # [MANDATE: DOC 5 SEC 3.2] SYMPATHY AUDIT
            if not prompt_operator(4, "Sympathy: Sector ETF closing above its Structural Floor?"):
                print("[HALT] Step 4: Sympathy Audit FAILED."); return "HALT|S6:HALT| Step 4: Sympathy Audit"

            if not prompt_operator("4.1", "Radar: Integrity Shocks clear? [Doc 5]"):
                print("[HALT] Step 4.1 failure."); return "HALT|S6:HALT| Step 4.1: Integrity Shock"

            event_aware = prompt_operator("4.2", "Event: Earnings/Dividend within 10 days?")
            # [MANDATE: DOC 7 STEP 7] Overheat Switch
            system_overheat = prompt_operator("4.3", "System: >= 3 consecutive realized losses?")
        else:
            print("[SKIP] [STEPS 2-4] BYPASSED: INFO Mode Active")

        # STEP 5: CLEAN TRADE AUDIT (Fundamental SSoT)
        print(f"[....] [STEP 5] Executing Clean Trade Audit...")
        # [O-5 FIX] Pass moat/roic/pivot for WEALTH and Turnaround Patch paths
        audit_status, audit_diag, audit_metrics = run_v8_clean_audit(
            ticker, profile=profile, is_etf=is_etf, wacc=wacc,
            moat=moat, roic_override=roic_override, pivot_confirmed=pivot_confirmed
        )

        if "HALT" in audit_status:
            print(f"[HALT] Step 5 (Fundamentals): {audit_diag}")
            if not active_bypass: return f"HALT|S6:HALT| Step 5: {audit_status}"
        elif audit_status == "WEAKENED":
            print(f"[HALT] Step 5: Asset state is WEAKENED. IMMEDIATE LOCKOUT on new capital adds.")
            if not active_bypass: return "HALT|S6:HALT| Step 5: WEAKENED (Capital Lockout)"
        elif audit_status.startswith("ERROR"):
            # [SC-6b FIX] Fundamentals returned ERROR — never treat as PASS.
            print(f"[ERROR] Step 5 (Fundamentals): {audit_diag}")
            return f"ERROR|S6:UNKN| Step 5: {audit_diag[:50]}"
        else:
            print(f"[PASS] [STEP 5] FUNDAMENTAL PASS: {audit_diag}")

        # STEP 6: TECHNICAL ENGINE (Liquidity/Volume SSoT)
        print(f"[....] [STEP 6] Executing Technical Engine...")
        # [O-2 NOTE] Engine currently manages its own IBKR connection internally.
        # Future enhancement: add ib_connection parameter to run_tbs_engine for session reuse.
        status, diag, metrics = run_tbs_engine(ticker, profile=profile, is_etf=is_etf, mode=mode)

        if status == "HALT":
            print(f"[HALT] Step 6 (Technical): {diag}")
            if not active_bypass: return "HALT|S6:HALT| Step 6: " + diag[:50]
        elif status == "ERROR":
            # [SC-6 FIX] Engine returned ERROR (e.g. no data, contract not found).
            # Never treat as PASS. Always halt — bypass mode cannot override missing data.
            print(f"[ERROR] Step 6 (Technical): {diag}")
            return f"ERROR|S6:UNKN| Step 6: {diag[:50]}"
        else:
            print(f"[PASS] [STEP 6] TECHNICAL PASS: {diag}")
            step6_passed = True  # [SCANNER FILTER MANDATE] Step 6 cleared


        # [SC-9 FIX] If Step 6 did not PASS, return immediately.
        # Dashboard is only meaningful for candidates that cleared the Technical Engine.
        # Halted tickers already have their diagnostic in the [HALT] print line above.
        if not step6_passed:
            if mode == "INFO":
                return f"PASS|S6:HALT| {regime} | Entry: ${metrics.get('Price', 0)} | Stop: ${metrics.get('Hard_Stop', 0)}"
            else:
                return "HALT|S6:HALT| Step 6: Technical Engine did not clear."

        # ==========================================
        # STEP 7 & 8: SIZING & FINAL AUTH [Doc 3 / Doc 7]
        # ==========================================
        multiplier = 1.0
        mod_log = []

        # 1. Macro Regime Multipliers [Doc 5]
        if "DEFENSIVE" in regime:
            multiplier *= 0.5
            mod_log.append("Defensive Regime (0.5x)")

        # 2. Event-Aware Multipliers [Doc 3 Sec 519]
        if event_aware:
            multiplier *= 0.5
            mod_log.append("Event-Aware <10d (0.5x)")

        # 3. Quality/DNA Multipliers [Doc 6 Sec 421]
        if "TURNAROUND" in audit_status:
            multiplier *= 0.5
            mod_log.append("Turnaround Patch (0.5x)")

        # 4. Volatility Multipliers [Doc 5 SEC 2.2]
        if storm_watch_active:
            multiplier *= 0.5
            mod_log.append("Storm Watch VIX >= 25 (0.5x)")

        # 5. Overheat Switch [Doc 7 Step 7]
        if system_overheat:
            multiplier *= 0.5
            mod_log.append("System Overheat: Recent Streak (0.5x)")

        # 5. Engine Conviction & Churn [Doc 2 Sec 316, 353]
        if "LOW" in metrics.get("Conviction", ""):
            multiplier *= 0.5
            mod_log.append("Low-Conviction Range (0.5x)")
        if "ACTIVE" in metrics.get("Inst_Churn", ""):
            multiplier *= 0.5
            mod_log.append("Inst. Churn/Modifier D (0.5x)")

        # Final sizing string for display
        sizing_msg = f"{multiplier * 100}%" if mode == "LIVE" else "BYPASSED (INFO MODE)"

        # --- [MANDATE: DOC 8 LAYER 2] EXECUTION METRICS SYNC ---
        # Extracting the Mechanical Hard Stop for automated bracket orders
        entry_price = metrics.get('Price', 0)
        stop_price = metrics.get('Hard_Stop', 0)
        structural_floor = metrics.get('Structural_Floor', 0)
        window_val = metrics.get('window_count', 'N/A')
        floor_type = metrics.get('Anchor_Type', 'Standard')

        # [MANDATE: DOC 3 SEC 90] Dynamic Order Type
        order_type = "MARKET" if "WEAKENED" in audit_status or "TERMINATED" in audit_status else "LIMIT"

        # --- [SECTION 4.3 MANDATES: EXPECTANCY, EXTENSION & PROXIMITY] --- #
        risk_per_share = round(entry_price - stop_price, 2)
        target_price = "N/A"
        dynamic_label, dynamic_val = "INFO", "N/A"

        if profile == "A":
            # SWING: 1:2 RR to Consolidation High [Doc 2 Sec 279]
            resistance = metrics.get('Resistance', entry_price)
            reward = resistance - entry_price
            expectancy = round(reward / risk_per_share, 2) if risk_per_share > 0 else 0
            dynamic_label, dynamic_val = "EXPECTANCY", f"{expectancy}:1"
            target_price = round(resistance, 2)

        elif profile == "B":
            # TREND: Extension Audit (Price vs EMA 8) [Doc 2 Sec 281]
            ema8 = metrics.get('EMA_8', entry_price)
            atr = metrics.get('ATR', 1.0)
            extension = round((entry_price - ema8) / atr, 2) if atr > 0 else 0
            dynamic_label, dynamic_val = "EXTENSION", f"{extension} ATR"
            target_price = round(entry_price + (atr * 1.5), 2) # Target 1 fixed @ +1.5 ATR

        elif profile == "C":
            # WEALTH: Floor Proximity Audit [Doc 2 Sec 284]
            sma200 = metrics.get('SMA_200', entry_price)
            proximity = round(abs(entry_price - sma200) / sma200 * 100, 2) if sma200 > 0 else 0
            dynamic_label, dynamic_val = "PROXIMITY", f"{proximity}% (200-SMA)"
            target_price = "OPEN-ENDED"

        # --- FINAL EXECUTION DASHBOARD [DOC 7] ---
        # [O-4 FIX] Profile-dependent window limits per Doc 2 Sec III
        window_limits = {"A": "0-4", "B": "0-5", "C": "0-2"}
        print(f"\n{'='*80}\n***  FINAL STRATEGY ALIGNMENT: {ticker} ***\n{'='*80}")
        print(f"   REGIME:      {regime}")
        print(f"   WINDOW:      Window {window_val} (Mandate: {window_limits.get(profile, '0-5')})")
        print(f"   FLOOR TYPE:  {floor_type}")
        print(f"   ACTION:      EXECUTE {order_type} ORDER")
        print(f"   SIZING:      {sizing_msg} of Base Unit")
        if mod_log: print(f"   MODIFIERS:   {', '.join(mod_log)}")
        print(f"   {dynamic_label.ljust(12)}: {dynamic_val}")
        print(f"   ENTRY PRICE: ${entry_price}")
        print(f"   STRUCT. FLOOR: ${structural_floor}")
        print(f"   HARD STOP:   ${stop_price} (Anchor - 1.5 ATR)")
        print(f"   TARGET:      ${target_price}")
        print(f"   RISK/SHARE:  ${risk_per_share}")
        print(f"{'='*80}\n")

        print(f"{'='*80}\n")

        # [MANDATE: SCANNER FILTER] Return tagged result for INFO mode.
        # step6_passed is guaranteed True here (halted tickers returned early via SC-9).
        if mode == "INFO":
            return f"PASS|S6:PASS| {regime} | W{window_val} | Entry: ${entry_price} | Stop: ${stop_price}"

        # ==========================================
        # STEP 8: THE AUTOMATED BRACKET ROUTER
        # ==========================================
        if mode == "LIVE":
            # 1. Retrieve Total Net Worth from the connected IBKR silo
            try:
                account_summary = ib.accountSummary()
                net_worth_item = next((item for item in account_summary if item.tag == 'NetLiquidation'), None)
                total_net_worth = float(net_worth_item.value) if net_worth_item else 10000.0
            except Exception:
                total_net_worth = 10000.0 # Fallback Silo Liquidity

            # 2. Calculate Base Unit per Profile Mandate
            risk_pct = 0.0025 if profile == "A" else 0.005 # 0.25% for A, 0.5% for B/C

            if risk_per_share > 0:
                base_units = (total_net_worth * risk_pct) / risk_per_share
            else:
                base_units = 0

            # Apply cumulative multipliers
            final_units = int(base_units * multiplier)

            # --- [MANDATE: DOC 3 SEC 217 & 230] CAPITAL SAFETY CAPS ---
            # Calculate total capital required for this trade
            total_capital_outlay = final_units * entry_price

            # Individual Cash Cap: Max 25% of Silo Liquidity
            max_cash_cap = total_net_worth * 0.25

            # Profile B Unit 1 Safety Cap: Max 1.0% of Account Equity
            if profile == "B" and total_capital_outlay > (total_net_worth * 0.01):
                final_units = int((total_net_worth * 0.01) / entry_price)
            elif total_capital_outlay > max_cash_cap:
                final_units = int(max_cash_cap / entry_price)

            open_risk_heat = final_units * risk_per_share

            # 3. Minimum Utility Gate
            if open_risk_heat < 50:
                print(f"[HALT] UTILITY HALT: Calculated Open Risk (${open_risk_heat:.2f}) < $50. Trade is not useful money.")
                return "HALT|S6:PASS| Step 7: Utility Gate (Heat < 50)"

            print(f"   FINAL SIZING: {final_units} Units (Total Capital: ${final_units * entry_price:.2f} | Open Risk: ${open_risk_heat:.2f})")

            # 4. Final Execution Gate
            if prompt_operator(8, f"AUTHORIZE LIVE EXECUTION of {final_units} units?"):
                print(f"[EXEC] [TRANSMITTING] Routing Bracket Order to IBKR...")

                # Fetch contract details (Assuming Long-Only per +DI > -DI preamble)
                # [O-6 FIX] Use resolved_contract from get_asset_type (correct exchange/currency)
                contract = resolved_contract

                # # Fire the deterministic bracket order
                # trades = execute_bracket_order(
                #     ib=ib,
                #     contract=contract,
                #     action="BUY",
                #     quantity=final_units,
                #     order_type=order_type,
                #     entry_price=entry_price,
                #     hard_stop_price=stop_price,
                #     target_price=target_price if target_price not in ["OPEN-ENDED", "N/A"] else None
                # )
                #
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

    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--profile", default="TREND",
                        choices=["SWING", "TREND", "WEALTH", "A", "B", "C"],
                        help="Trade profile (A=SWING, B=TREND, C=WEALTH).")
    parser.add_argument("--mode", default="INFO", choices=["INFO", "LIVE"])
    parser.add_argument("--bypass_macro", action="store_true")
    parser.add_argument("--wacc", type=float, default=None, help="WACC override for Turnaround Patch.")
    parser.add_argument("--moat", type=str, default=None, help="Moat rating for WEALTH (Wide or Narrow).")
    parser.add_argument("--roic", type=float, default=None, help="Manual ROIC percent override (Analyst-retrieved).")
    parser.add_argument("--pivot-confirmed", action="store_true", help="Confirm guidance revisions for Turnaround Patch.")
    args = parser.parse_args()

    execute_v8_pipeline(
        args.ticker.upper(), args.profile.upper(), args.mode.upper(),
        bypass_macro=args.bypass_macro, wacc=args.wacc,
        moat=args.moat, roic_override=args.roic, pivot_confirmed=args.pivot_confirmed
    )