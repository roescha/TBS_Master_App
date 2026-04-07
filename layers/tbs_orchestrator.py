import argparse
import sys
import os
import asyncio
import nest_asyncio
import re
from ai_event_radar import run_risk_radar
from ai_fundamental_retriever import run_retriever_with_timeout
from ai_vision_auditor import run_vision_audit
from ib_insync import IB, Stock, Contract

# [O-29] Apply nest_asyncio to allow nested event loops.
nest_asyncio.apply()

# -----------------------------
# TBS MASTER ORCHESTRATOR (Layer 3) v8.6.0
# Unified Non-Blocking Pipeline (Amendment v0.2 + Addendum v0.3)
# GOV-002 Phase 1: Enforcement-to-Advisory Refactoring
# Pipeline Execution, Governor Sizing, Bracket Order Routing
# v8.6.0: GOV-002 Phase 1 (advisory model, caution factors, no enforcement)
# v8.5.2: SA-002 (pass asset_close_current + asset_close_20bar to sympathy audit)
# -----------------------------

# TBS Layer Imports
from ibkr_sentinel import run_tbs_sentinel
from yahoo_fundamentals import run_v8_clean_audit
from ibkr_sympathy_audit import run_sympathy_audit
from ibkr_asset_gates import run_asset_gates
from ibkr_purity_engine import run_tbs_engine
from tbs_engine.transform import _flatten
from finnhub_context import run_finnhub_context
from finnhub_context import run_finnhub_legacy_fallback
from finnhub_context import run_finnhub_analyst_targets
from ibkr_options_context import get_options_context
from ai_institutional_context import get_institutional_context

from ib_insync import LimitOrder, MarketOrder, StopOrder


def execute_bracket_order(ib, contract, action, quantity, order_type, entry_price, hard_stop_price, target_price=None):
    """
    Constructs and submits a strict TBS Bracket Order via ib_insync.
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
    long_name = ""
    try:
        details = ib.reqContractDetails(contract)
        if details:
            long_name = details[0].longName or ""
            meta = long_name.upper()
            etf_keywords = ['ETF', 'FUND', 'VANGUARD', 'ISHARES', 'UCITS',
                            'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES']
            if any(key in meta for key in etf_keywords):
                return True, contract, long_name
    except Exception:
        pass
    return False, contract, long_name

def retrieve_and_confirm(ticker, metric_name):
    """
    Executes the AI Network Search with 120s timeout.
    [FHB-001 DQ-4] Auto-accept: if Gemini returns a value, accept automatically.
    """
    print(f"   [ANALYST] Initiating 120s Network Search for {metric_name}...")

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(run_retriever_with_timeout(ticker, metric_name, timeout=120.0))
    data = result.get("data") or {}

    val = data.get("value")
    source = data.get("source")

    if val is None or source in ("TIMEOUT", "ERROR"):
        print(f"   [FAIL] AI Retrieval failed or timed out. Reason: {data.get('error', 'Unknown')}")
        return None

    print(f"   [ANALYST RESULT] Found {metric_name}: {val}")
    print(f"   [SOURCE] {source}")

    # [FHB-001 DQ-4] Auto-accept: remove Operator confirmation prompt.
    print(f"   [AUTO-ACCEPT] {metric_name}: {val} (source: {source})")
    return val

def execute_v8_pipeline(ticker, profile="TREND", mode="INFO",
                        wacc=None, moat=None, roic_override=None, pivot_confirmed=False,
                        tnx=None, de_override=None, fcf_yield_override=None,
                        rev_override=None, eps_override=None,
                        sector_etf_override=None, is_etf_flag=False,
                        entry_price_override=None, shares=None,
                        capital_override=None,
                        engine_only=False,
                        convexity_class=None,
                        position_status="CANDIDATE",
                        heat_confirmed=True, slots_available=True,
                        overheat=False,
                        skip_capacity_gate=False):

    # Normalize profile aliases to internal codes (A/B/C).
    profile_map = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    profile = profile_map.get(profile.upper(), "B")

    # CONVEXITY CLASSIFICATION RESOLUTION
    if convexity_class is None:
        try:
            import json as _json
            _script_dir = os.path.dirname(os.path.abspath(__file__))
            _project_root = os.path.dirname(_script_dir)
            _cvx_path = os.path.join(_project_root, "docs\\classifications.json")
            if os.path.exists(_cvx_path):
                with open(_cvx_path, 'r') as _f:
                    _cvx_data = _json.load(_f)
                _cvx_lookup = _cvx_data.get(ticker.upper()) or _cvx_data.get(ticker)
                if _cvx_lookup:
                    convexity_class = _cvx_lookup.upper()
                    print(f"[CVX] Classification loaded from classifications.json: {convexity_class}")
        except Exception:
            pass

            # ADMISSIBILITY GATE
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

    # POSITION STATUS RESOLUTION (Amendment v0.2, Change 5)
    if position_status == "CANDIDATE":
        entry_price_override = None
        shares = None
        position_monitor = False
    else:
        position_monitor = (entry_price_override is not None and shares is not None)

    profile_names = {"A": "SWING", "B": "TREND", "C": "WEALTH"}
    profile_display = f"{profile} ({profile_names.get(profile, 'UNKNOWN')})"
    _mode_label = f"MONITOR (${entry_price_override} x {shares})" if position_monitor else mode
    _pos_label = f" | STATUS: {position_status}" if position_status else ""
    print(f"\n{'='*80}\nTBS v8.6.0 MASTER ORCHESTRATOR: {ticker} | {profile_display} | MODE: {_mode_label}{_pos_label}{_cvx_display}")
    if position_monitor: print(f"[MONITOR] Position Monitor active: Entry ${entry_price_override} x {shares} shares")
    print(f"{'='*80}")

    try:
        ib.connect('127.0.0.1', port, clientId=100)
        ib.reqMarketDataType(1)
        step6_passed = False

        if engine_only:
            is_etf, resolved_contract, _ = get_asset_type(ib, ticker)
            if is_etf_flag:
                is_etf = True
            print(f"[SCAN] [AUTO-ID] {'ETF/Index' if is_etf else 'Equity'} | ENGINE-ONLY mode")
            engine_result = run_tbs_engine(ticker, profile=profile, is_etf=is_etf, mode=mode,
                                           convexity_class=convexity_class)
            ib.disconnect()
            action_summary = engine_result.get("action_summary", {})
            verdict = action_summary.get("verdict", "ERROR")
            _, _, metrics = _flatten(engine_result)

            _ths_tag = ""
            _ths_val = metrics.get('Trend_Health_Score')
            if _ths_val is not None:
                _ths_tag = f"THS:{int(_ths_val)} "

            _reason = action_summary.get("reason", "")
            _context = action_summary.get("context", "") or ""
            _display = f"{_reason}. {_context}".strip().rstrip(".")

            if verdict == "VALID":
                return f"PASS|S6:PASS| {_ths_tag}{_display}"
            elif verdict == "INVALID":
                return f"HALT|S6:HALT| Step 6: {_display}"
            else:
                return f"ERROR|S6:UNKN| Step 6: {_display}"

        _verdicts = {}
        _threats = []
        _advisories = []   # GOV-002: Each: {"source": str, "severity": str, "message": str}

        # [PMC-001] PRE-STEP 1: OVERNIGHT BRIEFING (Layer 1)
        # Runs on BOTH entry mode and position monitor mode.
        # Informational only -- failure does not block pipeline.
        _overnight_ctx = {}
        try:
            from ai_premarket_context import get_overnight_briefing
            print("[....] [PMC-001] Fetching overnight briefing...")
            _overnight_ctx = get_overnight_briefing()
            _ov_status = _overnight_ctx.get("Overnight_Status", "UNAVAILABLE")
            if _ov_status == "AVAILABLE":
                _ov_sent = _overnight_ctx.get("Overnight_Sentiment", "N/A")
                print(f"[PASS] [PMC-001] OVERNIGHT BRIEFING: {_ov_sent}")
            else:
                print("[WARN] [PMC-001] OVERNIGHT BRIEFING: UNAVAILABLE")
        except Exception as _ov_err:
            print(f"[WARN] [PMC-001] OVERNIGHT BRIEFING: error -- {str(_ov_err)[:60]}")

        _sentinel_tier = "INFORMATIONAL"

        # ==================================================================
        # STEP 1: SYSTEMIC PERMISSION (The Sentinel)
        # ==================================================================
        regime, verdict, reason, storm_watch_active, sentinel_details = run_tbs_sentinel(
            ib_connection=ib, port=port, profile=profile
        )

        _verdicts["Sentinel"] = (verdict, regime)

        # [Addendum v0.3, Change 14] Sentinel one-liner
        _vix_val = sentinel_details.get("vix_close", "N/A") if sentinel_details else "N/A"
        _tnx_raw = sentinel_details.get("tnx_close_daily") if sentinel_details else None
        _tnx_display = f"{round(_tnx_raw / 10.0, 2):.2f}%" if _tnx_raw is not None else "N/A"
        _sw_display = "ON" if storm_watch_active else "OFF"
        # [MOD-I] Breadth status for one-liner (SUPPRESSED/UNAVAILABLE omitted)
        _breadth = sentinel_details.get("breadth_status") if sentinel_details else None
        _breadth_disp = ""
        if _breadth == "DIVERGENCE":
            _breadth_disp = " | Breadth: DIVERGENCE [!]"
        elif _breadth == "CONFIRMING":
            _breadth_disp = " | Breadth: CONFIRMING"
        print(f"[STEP 1] Sentinel: {regime} | VIX: {_vix_val} | TNX: {_tnx_display} | Storm Watch: {_sw_display}{_breadth_disp}")

        # [MOD-I] Expanded breadth block
        if _breadth == "DIVERGENCE":
            _slope = sentinel_details.get("rsp_spy_slope_5d") or 0
            _ratio = sentinel_details.get("rsp_spy_ratio") or 0
            _sma = sentinel_details.get("rsp_spy_ratio_sma20") or 0
            print(f"   BREADTH: DIVERGENCE [!] RSP/SPY ratio declining (5d slope: {_slope:.4f}, ratio: {_ratio:.3f}, SMA20: {_sma:.3f})")
            print(f"   Equal-weight index underperforming cap-weight. Advance may be narrowing to mega-cap leadership.")
        elif _breadth == "CONFIRMING":
            _slope = sentinel_details.get("rsp_spy_slope_5d") or 0
            print(f"   BREADTH: CONFIRMING (RSP/SPY ratio stable, 5d slope: {_slope:+.4f})")

        if tnx is None and _tnx_raw is not None:
            tnx = round(_tnx_raw / 10.0, 2)
            print(f"[AUTO] TNX yield auto-extracted from Sentinel: {tnx:.2f}%")

        if "HIGH RISK" in regime or "BLACK" in regime:
            _sentinel_tier = "EMERGENCY"
        elif "RESTRICTED" in regime or "RED" in regime or "SHOCK" in regime or "GREY" in regime:
            _sentinel_tier = "CRITICAL"
        elif "AMBIGUOUS" in regime or "UNCONFIRMED" in regime:
            _sentinel_tier = "ADVISORY"

        if verdict in ["HALT", "FORCE HARVEST"]:
            print(f"[WARN] [STEP 1] SENTINEL: {reason}")
            print(f"   Regime: {regime} -- pipeline continues for full audit")
            _threats.append(f"Regime {regime}: {reason}")
            # GOV-002: advisory entry replaces _sentinel_blocked + _no_adds
            _adv_sev = "EMERGENCY" if verdict == "FORCE HARVEST" else "CRITICAL"
            _advisories.append({"source": "Sentinel", "severity": _adv_sev, "message": f"Regime {regime}: {reason}"})
        else:
            print(f"[PASS] [STEP 1] SENTINEL: {regime}")

        if "DEFENSIVE" in regime and profile in ("B", "C"):
            _threats.append(f"DEFENSIVE regime: Profile {profile} long-term adds carry elevated risk")
            _advisories.append({"source": "Sentinel", "severity": "ADVISORY", "message": f"DEFENSIVE regime -- Profile {profile} long-term adds carry elevated risk"})
            print(f"[WARN] [STEP 1] SENTINEL: DEFENSIVE regime -- Profile {profile} long-term adds carry elevated risk")

        # [MOD-I] Breadth divergence threats entry (candidate path -- DQ-2)
        if _breadth == "DIVERGENCE":
            _threats.append("BREADTH DIVERGENCE: RSP/SPY ratio declining -- advance may be narrowing")

        # AUTO-ID
        is_etf, resolved_contract, company_name = get_asset_type(ib, ticker)
        if is_etf_flag:
            is_etf = True
        _id_label = 'ETF/Index' if is_etf else 'Standard Equity'
        _name_label = f" ({company_name})" if company_name else ""
        print(f"[SCAN] [AUTO-ID] Asset identified as: {_id_label}{_name_label}")

        # ==================================================================
        # STEP 2: ASSET PERMISSION
        # ==================================================================

        event_aware, system_overheat = False, False
        iv_guard_limit_only = False

        # --- 4a & 4d: AI Risk Radar ---
        print(f"[....] [STEP 2a/2d] Executing AI Risk Radar...")
        loop = asyncio.get_event_loop()
        radar_results = loop.run_until_complete(run_risk_radar(ticker, company_name=company_name))

        if radar_results.get("threat_event_detected", False):
            shock_details = []
            for cat in ["security_geo_event", "operational_env_event", "integrity_legal_event", "financial_shock_event"]:
                if radar_results.get(cat, {}).get("status") != "PASS":
                    shock_details.append(f"{cat.upper()}: {radar_results.get(cat, {}).get('details', 'Unknown')}")

            detail_str = " | ".join(shock_details) if shock_details else "Unspecified structural threat"

            # [Amendment v0.2, Change 3] Integrity Shock capped at WARN.
            _threats.append(f"INTEGRITY SHOCK (WARN): {detail_str}")
            _advisories.append({"source": "Risk Radar", "severity": "CRITICAL", "message": f"Integrity Shock: {detail_str[:80]}"})
            _verdicts["Risk_Radar"] = ("WARN", f"Integrity Shock: {detail_str[:80]}")
            print(f"[WARN] [STEP 2a] RISK RADAR: Integrity Shock detected (capped at WARN)")
        else:
            print(f"[PASS] [STEP 2a] RISK RADAR: ALL CLEAR")
            _verdicts["Risk_Radar"] = ("PASS", "No integrity shocks detected")

        _radar_warns = []
        _radar_details = {}  # [Addendum v0.3, Change 9] Full details per category for sub-lines
        for _rcat in ["security_geo_event", "operational_env_event", "integrity_legal_event", "financial_shock_event"]:
            _rval = radar_results.get(_rcat, {})
            if isinstance(_rval, dict) and _rval.get("status") != "PASS":
                _rcat_detail = _rval.get('details', 'Unknown')
                _radar_warns.append(_rcat.upper())
                _radar_details[_rcat.upper()] = _rcat_detail
        if _radar_warns:
            radar_summary = f"{len(_radar_warns)} WARN"
        else:
            radar_summary = "ALL CLEAR (4/4 categories PASS)"

        # --- 4b: SECTOR SYMPATHY AUDIT ---
        print(f"[....] [STEP 2b] Executing Sector Sympathy Audit...")

        # [SA-002 DQ-4] Pre-fetch asset close prices for RS computation.
        # Uses existing IB connection -- lightweight fetch (same bar size as sector ETF).
        _asset_close_current = None
        _asset_close_20bar = None
        try:
            _sa002_tf_map = {"A": ("1 hour", "3 M"), "B": ("1 day", "1 Y"), "C": ("1 week", "5 Y")}
            _sa002_res, _sa002_dur = _sa002_tf_map[profile]
            _sa002_bars = ib.reqHistoricalData(
                resolved_contract, '', _sa002_dur, _sa002_res, 'TRADES', True
            )
            if _sa002_bars and len(_sa002_bars) >= 21:
                _sa002_df = __import__('ib_insync').util.df(_sa002_bars)
                _asset_close_current = float(_sa002_df['close'].iloc[-1])
                _asset_close_20bar = float(_sa002_df['close'].iloc[-21])
        except Exception:
            pass  # Non-fatal: RS fields will show UNAVAILABLE

        symp_status, symp_diag, symp_metrics = run_sympathy_audit(
            ticker, profile=profile,
            sector_etf_override=sector_etf_override,
            mode=mode,
            ib_connection=ib,
            asset_close_current=_asset_close_current,
            asset_close_20bar=_asset_close_20bar
        )

        _verdicts["Sector_Sympathy"] = (symp_status, symp_diag)

        if symp_status == "HALT":
            print(f"[HALT] [STEP 2b] SECTOR SYMPATHY: {symp_diag}")
            _threats.append(f"Sector Sympathy HALT: sector floor violated -- {symp_diag}")
            _advisories.append({"source": "Sector Sympathy", "severity": "ADVISORY", "message": f"Sector floor violated: {symp_diag}"})
        elif symp_status == "ERROR":
            print(f"[WARN] [STEP 2b] SECTOR SYMPATHY: ERROR -- {symp_diag}")
            _threats.append(f"Sector Sympathy ERROR: {symp_diag}")
            _advisories.append({"source": "Sector Sympathy", "severity": "ADVISORY", "message": f"Sector Sympathy ERROR: {symp_diag}"})
        elif symp_status == "SKIPPED":
            print(f"[WARN] [STEP 2b] SECTOR SYMPATHY: SKIPPED -- {symp_diag}")
        elif symp_status == "EXEMPT":
            print(f"[PASS] [STEP 2b] SECTOR SYMPATHY: EXEMPT -- {symp_diag}")
        else:
            print(f"[PASS] [STEP 2b] SECTOR SYMPATHY: {symp_diag}")

        # --- 4c: ASSET GATES ---
        print(f"[....] [STEP 2c] Executing Asset Gates...")
        ag_status, ag_diag, ag_metrics = run_asset_gates(
            ticker, profile=profile, mode=mode,
            ib_connection=ib
        )

        _verdicts["Asset_Gates"] = (ag_status, ag_diag)

        if ag_status == "BLOCKED":
            _threats.append(f"Dividend Lockout: ex-date imminent -- NO ADDS")
            _advisories.append({"source": "Asset Gates", "severity": "ADVISORY", "message": f"Dividend Lockout: ex-date imminent -- {ag_diag}"})
            _verdicts["Asset_Gates"] = ("HALT", f"DIVIDEND LOCKOUT: {ag_diag}")
            print(f"[HALT] [STEP 2c] ASSET GATES: DIVIDEND LOCKOUT -- {ag_diag}")
        elif ag_status == "ERROR":
            _threats.append(f"Asset Gates ERROR: {ag_diag}")
            _advisories.append({"source": "Asset Gates", "severity": "ADVISORY", "message": f"Asset Gates ERROR: {ag_diag}"})
            iv_guard_limit_only = True
            _verdicts["Asset_Gates"] = ("WARN", f"ERROR: {ag_diag}")
            print(f"[WARN] [STEP 2c] ASSET GATES: ERROR -- {ag_diag}")
        elif ag_status == "LIMIT_ONLY":
            iv_guard_limit_only = True
            print(f"[PASS] [STEP 2c] ASSET GATES: LIMIT_ONLY -- {ag_diag}")
        else:
            print(f"[PASS] [STEP 2c] ASSET GATES: {ag_diag}")

        # --- CT-001.5: Finnhub Context (Session B -- full metric computation) ---
        _fh_sector_etf = symp_metrics.get("Sector_ETF", "")
        _fh_results = run_finnhub_context(
            ticker, sector_etf=_fh_sector_etf,
            profile=profile, is_etf=is_etf,
        )

        # --- 4d/4e: Event-Aware + Overheat ---
        event_aware = radar_results.get("event_aware_triggered", False)

        _binary_evt = radar_results.get("earnings_buffer_event", {})
        _binary_details = _binary_evt.get("details", "") if isinstance(_binary_evt, dict) else str(_binary_evt)
        if not _binary_details or _binary_details in ("", "No details returned", "Verify manually."):
            _binary_details = f"Earnings within 10 days detected for {ticker.upper()} or Super 7 (radar returned no specifics — verify manually)"

        if event_aware:
            print(f"[WARN] [STEP 2d] EVENT-AWARE: {_binary_details}")
            if position_monitor:
                _advisories.append({"source": "Event-Aware", "severity": "ADVISORY", "message": f"Earnings within 10 days: {_binary_details[:60]}"})
                _threats.append(f"Earnings within 10 days: NO ADDS ({_binary_details})")
        else:
            print(f"[PASS] [STEP 2d] EVENT-AWARE: No imminent binary events")

        # [Addendum v0.3, Change 12] Overheat: CLI flag replaces prompt.
        system_overheat = overheat
        if system_overheat:
            print(f"[WARN] [STEP 2e] OVERHEAT: Active (operator-declared). Caution factor at Step 8.")

        # ==================================================================
        # STEP 3: CLEAN TRADE AUDIT
        # ==================================================================

        # [FHB-001 DQ-5] Pre-gate Moat prompt removed. Moat is provided via --moat CLI flag
        # or retrieved automatically via Gemini auto-accept in the retry loop.

        _MAX_FUND_RETRIES = 5

        for _fund_attempt in range(_MAX_FUND_RETRIES + 1):
            print(f"[....] [STEP 3] Executing Clean Trade Audit{' (retry)' if _fund_attempt > 0 else ''}...")
            audit_status, audit_diag, audit_metrics = run_v8_clean_audit(
                ticker, profile=profile, is_etf=is_etf, wacc=wacc,
                moat=moat, roic_override=roic_override, pivot_confirmed=pivot_confirmed,
                tnx=tnx, de_override=de_override, fcf_yield_override=fcf_yield_override,
                rev_override=rev_override, eps_override=eps_override
            )

            _retrievable = audit_status in ("HALT (ANALYST RETRIEVE)", "HALT (MISSING DATA)", "HALT (PIVOT UNCONFIRMED)")

            if _retrievable and _fund_attempt < _MAX_FUND_RETRIES:
                print(f"[HALT] Step 3 (Fundamentals): {audit_diag}")
                print(f"[O-23 AI UPGRADE] Missing data detected. Delegating to Master Analyst for network retrieval.")

                _diag_upper = audit_diag.upper()
                _resolved = False

                # [FHB-001] Finnhub-eligible metrics: try deterministic fallback before Gemini
                _FH_ELIGIBLE = {"Revenue Growth %", "EPS Growth %", "ROIC %", "Debt-to-Equity %", "FCF Yield %"}

                if "MISSING DATA: REV=" in _diag_upper or ("REV=" in _diag_upper and "MASKED" in _diag_upper):
                    if rev_override is None:
                        _fh_val = run_finnhub_legacy_fallback(ticker, "Revenue Growth %")
                        if _fh_val is not None:
                            rev_override = float(_fh_val); _resolved = True
                        else:
                            val = retrieve_and_confirm(ticker, "Revenue Growth %")
                            if val is not None: rev_override = float(val); _resolved = True
                    if eps_override is None:
                        _fh_val = run_finnhub_legacy_fallback(ticker, "EPS Growth %")
                        if _fh_val is not None:
                            eps_override = float(_fh_val); _resolved = True
                        else:
                            val = retrieve_and_confirm(ticker, "EPS Growth %")
                            if val is not None: eps_override = float(val); _resolved = True

                elif "MISSING ROIC" in _diag_upper or "ROIC IS MISSING" in _diag_upper:
                    _fh_val = run_finnhub_legacy_fallback(ticker, "ROIC %")
                    if _fh_val is not None:
                        roic_override = float(_fh_val); _resolved = True
                    else:
                        val = retrieve_and_confirm(ticker, "ROIC %")
                        if val is not None: roic_override = float(val); _resolved = True

                elif "DEBT-TO-EQUITY" in _diag_upper:
                    _fh_val = run_finnhub_legacy_fallback(ticker, "Debt-to-Equity %")
                    if _fh_val is not None:
                        de_override = float(_fh_val); _resolved = True
                    else:
                        val = retrieve_and_confirm(ticker, "Debt-to-Equity %")
                        if val is not None: de_override = float(val); _resolved = True

                elif "FCF YIELD" in _diag_upper:
                    _fh_val = run_finnhub_legacy_fallback(ticker, "FCF Yield %")
                    if _fh_val is not None:
                        fcf_yield_override = float(_fh_val); _resolved = True
                    else:
                        val = retrieve_and_confirm(ticker, "FCF Yield %")
                        if val is not None: fcf_yield_override = float(val); _resolved = True

                elif "WACC DATA IS MISSING" in _diag_upper:
                    # WACC is NOT Finnhub-eligible -- Gemini only
                    val = retrieve_and_confirm(ticker, "WACC %")
                    if val is not None: wacc = float(val); _resolved = True

                elif "MOAT" in _diag_upper:
                    # Moat is NOT Finnhub-eligible -- Gemini only
                    val = retrieve_and_confirm(ticker, "Moat Rating")
                    if val in ("WIDE", "NARROW"):
                        moat = val; _resolved = True
                    elif val == "NONE":
                        print(f"   [ANALYST] Moat rated NONE -- does not qualify for WEALTH profile. Fundamentals will HALT.")
                        break

                elif "PIVOT NOT CONFIRMED" in _diag_upper:
                    _val = input("   Pivot confirmed manually via earnings calls? (Y/N): ").strip().upper()
                    if _val == "Y":
                        pivot_confirmed = True; _resolved = True

                if _resolved:
                    continue
                else:
                    break

            else:
                break

        _verdicts["Fundamentals"] = (audit_status, audit_diag)

        if "HALT" in audit_status:
            print(f"[HALT] [STEP 3] FUNDAMENTALS: {audit_diag}")
            _threats.append(f"Fundamental HALT: {audit_status} -- {audit_diag}")
            _advisories.append({"source": "Fundamentals", "severity": "ADVISORY", "message": f"Fundamental HALT: {audit_status} -- {audit_diag[:60]}"})
        elif audit_status == "WEAKENED":
            print(f"[HALT] [STEP 3] FUNDAMENTALS: WEAKENED -- capital lockout")
            _threats.append("Fundamentals WEAKENED: capital lockout -- evaluate EXIT")
            _advisories.append({"source": "Fundamentals", "severity": "CRITICAL", "message": "WEAKENED -- capital lockout. Recommended: evaluate EXIT."})
        elif audit_status.startswith("ERROR"):
            print(f"[WARN] [STEP 3] FUNDAMENTALS: ERROR -- {audit_diag}")
            _threats.append(f"Fundamental ERROR: {audit_diag}")
            _advisories.append({"source": "Fundamentals", "severity": "ADVISORY", "message": f"Fundamental ERROR: {audit_diag[:60]}"})
        else:
            print(f"[PASS] [STEP 3] FUNDAMENTALS: {audit_diag}")

        # ==================================================================
        # CT-001 CONTEXT ENRICHMENT: Yahoo-Finnhub Merge (Session B)
        # ==================================================================
        # Build merged CT-001 metrics dict: prefer Yahoo, fallback to Finnhub.
        # Track which metrics came from Finnhub for SOURCE line.
        _ct_merged = {}
        _fh_sourced = []  # metric names that came from Finnhub

        # --- CT-001.1: EPS Revision ---
        # Yahoo primary
        _y_eps_dir = audit_metrics.get("EPS_Revision_Direction")
        _y_eps_pct = audit_metrics.get("EPS_Revision_Pct")
        if _y_eps_dir is not None:
            _ct_merged["EPS_Revision_Direction"] = _y_eps_dir
            _ct_merged["EPS_Revision_Pct"] = _y_eps_pct
        elif _fh_results.get("EPS_Revision_Direction") not in (None, "UNAVAILABLE"):
            _ct_merged["EPS_Revision_Direction"] = _fh_results["EPS_Revision_Direction"]
            _ct_merged["EPS_Revision_Pct"] = _fh_results.get("EPS_Revision_Pct")
            _fh_sourced.append("EPS revision")
        else:
            _ct_merged["EPS_Revision_Direction"] = "UNAVAILABLE"
            _ct_merged["EPS_Revision_Pct"] = None

        # --- CT-001.1: Revenue Revision (Finnhub ONLY -- no Yahoo source) ---
        _fh_rev_dir = _fh_results.get("Revenue_Revision_Direction")
        if _fh_rev_dir not in (None, "UNAVAILABLE"):
            _ct_merged["Revenue_Revision_Direction"] = _fh_rev_dir
            _ct_merged["Revenue_Revision_Pct"] = _fh_results.get("Revenue_Revision_Pct")
            _fh_sourced.append("Revenue revision")
        else:
            _ct_merged["Revenue_Revision_Direction"] = "UNAVAILABLE"
            _ct_merged["Revenue_Revision_Pct"] = None

        # --- CT-001.2: Valuation ratios ---
        for _vk in ("Forward_PE", "PEG_Ratio", "PS_Ratio"):
            _y_val = audit_metrics.get(_vk)
            if _y_val is not None:
                _ct_merged[_vk] = _y_val
            elif _fh_results.get(_vk) is not None:
                _ct_merged[_vk] = _fh_results[_vk]
                _fh_sourced.append(_vk)
            else:
                _ct_merged[_vk] = None

        # Sector Median PE from cache (via Finnhub module)
        _ct_merged["Sector_Median_PE"] = _fh_results.get("Sector_Median_PE")
        _ct_merged["Sector_Median_PE_Stale"] = _fh_results.get("Sector_Median_PE_Stale", False)

        # Valuation_Label: computed from Forward_PE vs Sector_Median_PE
        _fpe = _ct_merged.get("Forward_PE")
        _smed = _ct_merged.get("Sector_Median_PE")
        if _fpe is not None and _smed is not None and _smed > 0 and _fpe > 0:
            _val_ratio = _fpe / _smed
            if _val_ratio < 0.7:
                _ct_merged["Valuation_Label"] = "DISCOUNT"
            elif _val_ratio <= 1.3:
                _ct_merged["Valuation_Label"] = "FAIR"
            elif _val_ratio <= 2.0:
                _ct_merged["Valuation_Label"] = "PREMIUM"
            else:
                _ct_merged["Valuation_Label"] = "STRETCHED"
        elif _fpe is not None and _fpe <= 0:
            _ct_merged["Valuation_Label"] = "UNAVAILABLE (negative P/E)"
        else:
            _ct_merged["Valuation_Label"] = "UNAVAILABLE"

        # --- CT-001.4: Margin Trajectory ---
        for _mk in ("Gross_Margin_Trend", "Operating_Margin_Trend"):
            _y_mval = audit_metrics.get(_mk)
            _delta_key = _mk.replace("_Trend", "_Delta_pp")
            if _y_mval is not None:
                _ct_merged[_mk] = _y_mval
                _ct_merged[_delta_key] = audit_metrics.get(_delta_key)
            elif _fh_results.get(_mk) not in (None, "UNAVAILABLE"):
                _ct_merged[_mk] = _fh_results[_mk]
                _ct_merged[_delta_key] = _fh_results.get(_delta_key)
                _fh_sourced.append(_mk.replace("_Trend", "").replace("_", " ").strip().lower())
            else:
                _ct_merged[_mk] = "UNAVAILABLE"
                _ct_merged[_delta_key] = None

        _y_mnote = audit_metrics.get("Margin_Note")
        _fh_mnote = _fh_results.get("Margin_Note")
        _ct_merged["Margin_Note"] = _y_mnote if _y_mnote else _fh_mnote

        # --- SOURCE line construction ---
        _fh_diag = _fh_results.get("finnhub_diagnostic", "") or ""
        if "API key not configured" in _fh_diag:
            _ct_source_detail = "Finnhub fallback: API key not configured"
        elif "finnhub-python not installed" in _fh_diag:
            _ct_source_detail = "Finnhub fallback: finnhub-python not installed"
        elif _fh_sourced:
            _ct_source_detail = "Finnhub fallback: %s" % ", ".join(_fh_sourced)
        elif _fh_diag and "all metrics failed" in _fh_diag:
            _ct_source_detail = "Finnhub fallback: all metrics failed"
        else:
            _ct_source_detail = "Finnhub fallback: not activated"

        # Staleness warning for Valuation line
        _staleness_warn = ""
        if _ct_merged.get("Sector_Median_PE_Stale") and _smed is not None:
            # Compute days since update
            try:
                _cache_data = _fh_results  # Sector_Median_PE_Stale comes from cache check
                _staleness_warn = " | WARNING: sector median may be stale"
            except Exception:
                _staleness_warn = ""

        # ==================================================================
        # STEP 4: TECHNICAL ENGINE
        # ==================================================================

        # --- FRR-001: Analyst consensus target extraction + Finnhub fallback ---
        _analyst_target_median = audit_metrics.get("analyst_target_median")
        _analyst_target_low = audit_metrics.get("analyst_target_low")
        _analyst_target_high = audit_metrics.get("analyst_target_high")
        _analyst_count = audit_metrics.get("analyst_count")

        _any_null = (
            _analyst_target_median is None or _analyst_target_low is None
            or _analyst_target_high is None or _analyst_count is None
        )
        if _any_null and profile in ("B", "TREND"):
            print("[FRR-001] Analyst targets incomplete from Yahoo -- attempting Finnhub fallback...")
            try:
                _fh_at = run_finnhub_analyst_targets(ticker)
                if _analyst_target_median is None and _fh_at.get("analyst_target_median") is not None:
                    _analyst_target_median = _fh_at["analyst_target_median"]
                if _analyst_target_low is None and _fh_at.get("analyst_target_low") is not None:
                    _analyst_target_low = _fh_at["analyst_target_low"]
                if _analyst_target_high is None and _fh_at.get("analyst_target_high") is not None:
                    _analyst_target_high = _fh_at["analyst_target_high"]
                if _analyst_count is None and _fh_at.get("analyst_count") is not None:
                    _analyst_count = _fh_at["analyst_count"]
            except Exception as _fh_err:
                print("[FRR-001] Finnhub fallback failed: %s" % str(_fh_err))

        if profile in ("B", "TREND"):
            print("[FRR-001] Analyst targets: median=%s low=%s high=%s count=%s" % (
                _analyst_target_median, _analyst_target_low,
                _analyst_target_high, _analyst_count))

        print(f"[....] [STEP 4] Executing Technical Engine...")
        engine_result = run_tbs_engine(ticker, profile=profile, is_etf=is_etf, mode=mode,
                                       convexity_class=convexity_class,
                                       analyst_target_median=_analyst_target_median,
                                       analyst_target_low=_analyst_target_low,
                                       analyst_target_high=_analyst_target_high,
                                       analyst_count=_analyst_count)
        action_summary = engine_result.get("action_summary", {})
        verdict = action_summary.get("verdict", "ERROR")
        _, _, metrics = _flatten(engine_result)

        # Reconstruct display string from action_summary
        _reason = action_summary.get("reason", "")
        _as_context = action_summary.get("context", "") or ""
        diag = f"{_reason}. {_as_context}".strip().rstrip(".")

        # Map verdict to pipeline vocabulary for _verdicts dict
        # Note: _verdicts uses PASS/HALT for non-engine steps too, so we map back
        if verdict == "VALID":
            status = "PASS"
        elif verdict == "INVALID":
            status = "HALT"
        else:
            status = "ERROR"

        _verdicts["Tech_Engine"] = (status, diag)

        if verdict == "INVALID":
            print(f"[HALT] [STEP 4] TECHNICAL ENGINE: {diag}")
            _threats.append(f"Engine HALT: {diag}")
            _advisories.append({"source": "Tech Engine", "severity": "ADVISORY", "message": f"Engine HALT: {diag[:60]}"})
        elif verdict == "ERROR":
            print(f"[WARN] [STEP 4] TECHNICAL ENGINE: ERROR -- {diag}")
            _threats.append(f"Engine ERROR: {diag}")
            _advisories.append({"source": "Tech Engine", "severity": "ADVISORY", "message": f"Engine ERROR: {diag[:60]}"})
        else:
            print(f"[PASS] [STEP 4] TECHNICAL ENGINE: {diag}")
            step6_passed = True

        # ==================================================================
        # STEP 5: VISUAL PROOF SUBMISSION
        # ==================================================================
        print(f"[....] [STEP 5] Executing Chart Verification...")

        # [Amendment v0.2, Change 4] Strip exchange suffixes for chart filename matching.
        _vision_ticker = ticker.upper()
        for _suffix in ['.L', '.TO', '.DE', '.AS', '.PA']:
            if _vision_ticker.endswith(_suffix):
                _vision_ticker = _vision_ticker.replace(_suffix, '')
                break

        loop = asyncio.get_event_loop()
        vision_results = loop.run_until_complete(run_vision_audit(_vision_ticker, profile, metrics))

        vision_verdict = vision_results.get("verdict", "ERROR")
        vision_reasoning = vision_results.get("reasoning", "No reasoning provided.")

        _vision_climax = vision_results.get("volume_climax_detected", False)
        if _vision_climax:
            print(f"   [ANALYST WARNING] VOLUME CLIMAX visually detected -- 3-bar execution block per Doc 2 §II")
            if position_monitor:
                _threats.append("Volume Climax visually detected: 3-bar execution block (Doc 2 §II)")

        if vision_verdict == "PASS":
            print(f"[PASS] [STEP 5] CHART VERIFY: {vision_reasoning}")
            _verdicts["Chart_Verify"] = ("PASS", vision_reasoning[:80])

            if mode == "LIVE":
                _engine_ctx = metrics.get('Engine_State', '') if step6_passed else 'ENGINE DID NOT PASS'
                _visual_q = f"Confirm engine state ({_engine_ctx}) matches charts? [Doc 4]"

                if not prompt_operator(5, _visual_q):
                    _threats.append("Chart verification VETOED by Operator")
                    _verdicts["Chart_Verify"] = ("HALT", "Operator Veto")
                    _advisories.append({"source": "Chart Verify", "severity": "ADVISORY", "message": "Chart verification VETOED by Operator"})
                    print(f"[HALT] [STEP 5] CHART VERIFY: Operator Veto")
        else:
            print(f"[HALT] [STEP 5] CHART VERIFY: {vision_reasoning}")
            _threats.append(f"Chart Verify HALT: {vision_reasoning}")
            _verdicts["Chart_Verify"] = ("HALT", vision_reasoning[:80])
            _advisories.append({"source": "Chart Verify", "severity": "ADVISORY", "message": f"Chart Verify HALT: {vision_reasoning[:60]}"})

        # ==================================================================
        # STEP 6: CAPACITY GATE (moved from v8.5 Step 2)
        # [Addendum v0.3, Change 11] CLI flags replace operator prompt.
        # [v9.0, Phase 1] --skip-capacity-gate flag. Auto-applied in INFO mode.
        # ==================================================================
        if position_monitor:
            _verdicts["Capacity"] = ("N/A", "Position Monitor -- skipped")
        elif skip_capacity_gate or mode == "INFO":
            _verdicts["Capacity"] = ("SKIPPED", "--skip-capacity-gate applied (or INFO mode)")
            print(f"[SKIP] [STEP 6] CAPACITY: SKIPPED")
        elif not heat_confirmed:
            _advisories.append({"source": "Capacity", "severity": "ADVISORY", "message": "Portfolio heat > 5% (operator-declared)"})
            _threats.append("Capacity HALT: Operator declared heat > 5%")
            _verdicts["Capacity"] = ("HALT", "Operator declared heat > 5% (--heat-confirmed false)")
            print(f"[HALT] [STEP 6] CAPACITY: Operator declared heat > 5% (--heat-confirmed false)")
        elif not slots_available:
            _advisories.append({"source": "Capacity", "severity": "ADVISORY", "message": "No profile slots available (operator-declared)"})
            _threats.append("Capacity HALT: Operator declared no slots available")
            _verdicts["Capacity"] = ("HALT", "Operator declared no slots available (--slots-available false)")
            print(f"[HALT] [STEP 6] CAPACITY: Operator declared no slots available (--slots-available false)")
        else:
            _verdicts["Capacity"] = ("PASS", "Heat confirmed (CLI). Slots available")
            print(f"[PASS] [STEP 6] CAPACITY: Heat confirmed (CLI). Slots available.")

        # ==================================================================
        # POST-ENGINE: OPTIONS CONTEXT (Module K + OPEX-001)
        # Informational overlay -- zero engine interaction.
        # If this fails, pipeline continues with Options_Status = UNAVAILABLE.
        # ==================================================================
        _options_ctx = {}
        try:
            _opt_price = metrics.get('Price') or 0
            _opt_atr = metrics.get('ATR', 1.0) or 1.0
            if _opt_price > 0 and _opt_atr > 0:
                print(f"[....] [MOD-K] Fetching options context for {ticker}...")
                _options_ctx = get_options_context(
                    ticker, _opt_price, _opt_atr, mode=mode
                )
                _opt_status = _options_ctx.get("Options_Status", "UNAVAILABLE")
                if _opt_status == "AVAILABLE":
                    print(f"[PASS] [MOD-K] OPTIONS CONTEXT: AVAILABLE")
                else:
                    _opt_diag = _options_ctx.get("Options_Diagnostic", "")
                    print(f"[WARN] [MOD-K] OPTIONS CONTEXT: UNAVAILABLE -- {_opt_diag}")
            else:
                _options_ctx = {
                    "Options_Status": "UNAVAILABLE",
                    "Options_Diagnostic": "Price or ATR unavailable from engine.",
                    "OPEX_Flag": False, "OPEX_Tier": "NONE",
                    "OPEX_Advisory": "", "OPEX_Max_Pain_Note": "",
                    "OPEX_Afternoon_Flag": False,
                }
                print(f"[WARN] [MOD-K] OPTIONS CONTEXT: UNAVAILABLE -- Price/ATR not available from engine")
        except Exception as _opt_err:
            _options_ctx = {
                "Options_Status": "UNAVAILABLE",
                "Options_Diagnostic": "Exception: %s" % str(_opt_err)[:80],
                "OPEX_Flag": False, "OPEX_Tier": "NONE",
                "OPEX_Advisory": "", "OPEX_Max_Pain_Note": "",
                "OPEX_Afternoon_Flag": False,
            }
            print(f"[WARN] [MOD-K] OPTIONS CONTEXT: UNAVAILABLE -- {str(_opt_err)[:60]}")

        # ==================================================================
        # POST-ENGINE: INSTITUTIONAL CONTEXT (FLOW-001 + MOD-M)
        # Informational overlay -- zero engine interaction.
        # Candidate evaluation path ONLY (DQ Q2: not on PM path).
        # If this fails, pipeline continues with Flow_Status = UNAVAILABLE.
        # ==================================================================
        _inst_ctx = {}
        if not position_monitor:
            try:
                print(f"[....] [FLOW-001/MOD-M] Fetching institutional context for {ticker}...")
                _inst_ctx = get_institutional_context(
                    ticker, company_name, is_etf=is_etf
                )
                _flow_st = _inst_ctx.get("Flow_Status", "UNAVAILABLE")
                _ins_st = _inst_ctx.get("Insider_Status", "UNAVAILABLE")
                if _flow_st == "AVAILABLE":
                    print(f"[PASS] [FLOW-001] FLOW ACTIVITY: AVAILABLE -- {_inst_ctx.get('Flow_Label', 'N/A')}")
                else:
                    print(f"[WARN] [FLOW-001] FLOW ACTIVITY: UNAVAILABLE")
                if not is_etf:
                    if _ins_st == "AVAILABLE":
                        _cluster_tag = " [CLUSTER BUY]" if _inst_ctx.get("Insider_Cluster_Buy") else ""
                        print(f"[PASS] [MOD-M] INSIDER ACTIVITY: AVAILABLE{_cluster_tag}")
                    else:
                        print(f"[WARN] [MOD-M] INSIDER ACTIVITY: {_ins_st}")
                else:
                    print(f"[INFO] [MOD-M] INSIDER ACTIVITY: N/A (ETF)")
                # [PMC-001] Layer 2 status one-liner
                _pmc_st = _inst_ctx.get("PMC_Status", "UNAVAILABLE")
                if _pmc_st == "AVAILABLE":
                    _pmc_cat_tag = " [CATALYST]" if _inst_ctx.get("PMC_Catalyst_Flag") else ""
                    print(f"[PASS] [PMC-001] PRE-MARKET CONTEXT: AVAILABLE{_pmc_cat_tag}")
                else:
                    print(f"[WARN] [PMC-001] PRE-MARKET CONTEXT: UNAVAILABLE")
            except Exception as _inst_err:
                _inst_ctx = {
                    "Flow_Status": "UNAVAILABLE",
                    "Insider_Status": "UNAVAILABLE" if not is_etf else "N/A",
                    "Institutional_Diagnostic": "Exception: %s" % str(_inst_err)[:80],
                }
                print(f"[WARN] [FLOW-001/MOD-M] INSTITUTIONAL CONTEXT: UNAVAILABLE -- {str(_inst_err)[:60]}")

        # ==================================================================
        # POSITION MONITOR BRANCH
        # ==================================================================
        window_limits = {"A": "0-4", "B": "0-5", "C": "0-2"}

        if position_monitor:
            current_price = metrics.get('Price') or 0
            stop_price = metrics.get('Hard_Stop') or 0
            structural_floor = metrics.get('Structural_Floor') or 0
            atr = metrics.get('ATR', 1.0) or 1.0

            pl_per_share = round(current_price - entry_price_override, 4)
            unrealized_pl = round(pl_per_share * shares, 2)
            pl_pct = round((pl_per_share / entry_price_override) * 100, 2) if entry_price_override else 0
            risk_from_entry = round(entry_price_override - stop_price, 4) if stop_price else 0
            r_multiple = round(pl_per_share / risk_from_entry, 2) if risk_from_entry > 0 else 0
            dist_to_stop = round(current_price - stop_price, 4) if stop_price else 0
            dist_to_stop_atr = round(dist_to_stop / atr, 2) if atr > 0 else 0
            stop_risk_remaining = round(dist_to_stop * shares, 2) if stop_price else 0

            _exit_sig = metrics.get('Exit_Signal') or False
            _exit_triggers = metrics.get('Exit_Triggers') or 'None'
            _exit_vwap = metrics.get('Exit_VWAP_Counter') or ''
            _engine_state = metrics.get('Engine_State') or 'N/A'
            _vol_confirm = metrics.get('Vol_Confirm_State') or ''
            _di_plus = metrics.get('DI_Plus') or 0
            _di_minus = metrics.get('DI_Minus') or 0

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

            _has_exit_signal = (_exit_sig in ("WARNING", "EXIT"))

            if _has_exit_signal:
                recommendation = "EXIT"
                rationale = f"Exit_Signal = {_exit_sig}. Position structural health deteriorating. Evaluate immediate exit or reduction."
            elif any(a["severity"] in ("EMERGENCY", "CRITICAL") for a in _advisories):
                recommendation = "NO ACTION"
                rationale = "Position structure intact but environment carries elevated risk. Hold current position, do not add."
            else:
                recommendation = "FIT FOR ADD"
                rationale = "All pipeline steps clear and no exit signals active. Position eligible for add sizing."

            symp_summary = symp_metrics.get("Sympathy_Status", "N/A")
            symp_etf = symp_metrics.get("Sector_ETF", "N/A")
            symp_margin = symp_metrics.get("Sympathy_Margin_Pct", "N/A")
            iv_guard_display = ag_metrics.get("IV_Guard_Action", "N/A")

            _pl_sign = "+" if unrealized_pl >= 0 else ""

            # [PMC-001] OVERNIGHT BRIEFING rendering (Position Monitor path)
            if _overnight_ctx and _overnight_ctx.get("Overnight_Status") == "AVAILABLE":
                print("\n   ==================================================================")
                print("   OVERNIGHT BRIEFING (Pre-Session Context)")
                print("   ==================================================================")
                _ov_es_pct = _overnight_ctx.get("Overnight_ES_Change_Pct")
                _ov_nq_pct = _overnight_ctx.get("Overnight_NQ_Change_Pct")
                _ov_es_str = "%+.1f%%" % _ov_es_pct if _ov_es_pct is not None else _overnight_ctx.get("Overnight_ES_Direction", "N/A")
                _ov_nq_str = "%+.1f%%" % _ov_nq_pct if _ov_nq_pct is not None else _overnight_ctx.get("Overnight_NQ_Direction", "N/A")
                _ov_sent = _overnight_ctx.get("Overnight_Sentiment", "N/A")
                print("   Futures:      ES %s | NQ %s | Session bias: %s" % (_ov_es_str, _ov_nq_str, _ov_sent))
                _ov_nk = _overnight_ctx.get("Overnight_Nikkei_Pct")
                _ov_hs = _overnight_ctx.get("Overnight_HangSeng_Pct")
                _ov_sh = _overnight_ctx.get("Overnight_Shanghai_Pct")
                print("   Asia:         Nikkei %s | Hang Seng %s | Shanghai %s" % (
                    "%+.1f%%" % _ov_nk if _ov_nk is not None else "N/A",
                    "%+.1f%%" % _ov_hs if _ov_hs is not None else "N/A",
                    "%+.1f%%" % _ov_sh if _ov_sh is not None else "N/A"))
                _ov_stoxx = _overnight_ctx.get("Overnight_Stoxx600_Pct")
                _ov_dax = _overnight_ctx.get("Overnight_DAX_Pct")
                print("   Europe:       STOXX 600 %s | DAX %s" % (
                    "%+.1f%%" % _ov_stoxx if _ov_stoxx is not None else "N/A",
                    "%+.1f%%" % _ov_dax if _ov_dax is not None else "N/A"))
                _ov_oil = _overnight_ctx.get("Overnight_Oil_WTI_Pct")
                _ov_gold = _overnight_ctx.get("Overnight_Gold_Pct")
                print("   Commodities:  WTI %s | Gold %s" % (
                    "%+.1f%%" % _ov_oil if _ov_oil is not None else "N/A",
                    "%+.1f%%" % _ov_gold if _ov_gold is not None else "N/A"))
                _ov_vix_lvl = _overnight_ctx.get("Overnight_VIX_Level")
                _ov_vix_dir = _overnight_ctx.get("Overnight_VIX_Direction", "UNAVAILABLE")
                _ov_vix_chg = _overnight_ctx.get("Overnight_VIX_Change_Pct")
                if _ov_vix_lvl is not None:
                    _ov_vix_str = "%.1f" % _ov_vix_lvl
                    if _ov_vix_chg is not None:
                        _ov_vix_str += " (%s %+.1f%%)" % (_ov_vix_dir, _ov_vix_chg)
                    else:
                        _ov_vix_str += " (%s)" % _ov_vix_dir
                else:
                    _ov_vix_str = "UNAVAILABLE"
                print("   VIX Futures:  %s" % _ov_vix_str)
                _ov_hl = _overnight_ctx.get("Overnight_Headlines") or []
                if _ov_hl:
                    print("   Headlines:    %s" % _ov_hl[0])
                    for _h in _ov_hl[1:]:
                        print("                 %s" % _h)
                print("   SOURCE:       Gemini Search (financial news, futures data)")
            elif _overnight_ctx:
                _ov_diag = _overnight_ctx.get("Overnight_Diagnostic") or "Gemini Search error"
                print("\n   ==================================================================")
                print("   OVERNIGHT BRIEFING: UNAVAILABLE (%s)" % _ov_diag)
                print("   ==================================================================")

            # --- Verdict Summary (Position Monitor) ---
            print(f"\n{'='*80}")
            print(f"*** UNIFIED DASHBOARD: {ticker} | {profile_display} | {mode} | EXISTING ***")
            print(f"{'='*80}")
            print(f"\n   --- VERDICT SUMMARY ---")
            _step_labels_pm = {
                "Sentinel": "Step 1", "Risk_Radar": "Step 2a", "Sector_Sympathy": "Step 2b",
                "Asset_Gates": "Step 2c", "Fundamentals": "Step 3", "Tech_Engine": "Step 4",
                "Chart_Verify": "Step 5", "Capacity": "Step 6", "Sizing": "Step 7"
            }
            _step_order_pm = ["Sentinel", "Risk_Radar", "Sector_Sympathy", "Asset_Gates",
                              "Fundamentals", "Tech_Engine", "Chart_Verify", "Capacity", "Sizing"]
            for _sk in _step_order_pm:
                _sv = _verdicts.get(_sk)
                if _sv is not None:
                    _v_status, _v_detail = _sv
                    _v_label = _step_labels_pm.get(_sk, _sk)
                    _tag = ""
                    if _v_status in ("HALT", "ERROR"):
                        _tag = " [BLOCKED]"
                    elif _v_status == "WARN":
                        _tag = " [ADVISORY]"
                    print(f"   {_v_label:8s} {_sk:18s}: {_v_status}{_tag} -- {_v_detail[:60]}")

            # --- Strategy Alignment (Position Monitor) ---
            print(f"\n   --- STRATEGY ALIGNMENT ---")
            print(f"   POSITION:     EXISTING (Entry: ${entry_price_override} | {shares} shares)")
            if convexity_class:
                _cvx_role = metrics.get('Profit_Target_Role') or 'PRESCRIPTIVE'
                print(f"   CONVEXITY:    C-{convexity_class[1]} ({_cvx_role})")
            # [FRR-001] Fundamental R:R (Profile B, EXISTING path)
            _frr_val_e = metrics.get('Fundamental_RR')
            if _frr_val_e is not None:
                _frr_label_e = metrics.get('Fundamental_RR_Label')
                _frr_tgt_e = metrics.get('Fundamental_Target')
                _frr_flr_e = metrics.get('Fundamental_Floor')
                _frr_cnt_e = metrics.get('Fundamental_Analyst_Count')
                print(f"   FUNDAMENTAL R:R: {_frr_val_e} ({_frr_label_e}) | Target: ${_frr_tgt_e} Floor: ${_frr_flr_e} | {_frr_cnt_e} analysts")
                _frr_note_e = metrics.get('Fundamental_RR_Note')
                if _frr_note_e:
                    print(f"   ANALYST NOTE: {_frr_note_e}")

            if _sentinel_tier != "INFORMATIONAL":
                print(f"   MACRO REGIME: {regime} [{_sentinel_tier}]")
            else:
                print(f"   MACRO REGIME: {regime}")

            # GOV-002: Sector Rotation Map (non-GREEN regimes only)
            _rotation_map = sentinel_details.get("rotation_map", {})
            if _rotation_map and "BULLISH" not in regime and "DEFENSIVE" not in regime:
                print(f"\n   SECTOR ROTATION (20-bar vs SPY):")
                _sorted_sectors = sorted(
                    [(sym, data) for sym, data in _rotation_map.items() if "rs" in data],
                    key=lambda x: x[1].get("rs", 0),
                    reverse=True
                )
                for _sym, _data in _sorted_sectors:
                    _name = _data.get("name", _sym)
                    _chg = _data.get("change_20", 0)
                    _rs = _data.get("rs", 0)
                    _label = _data.get("label", "UNAVAILABLE")
                    _spread = _data.get("spread_mode", False)
                    _rs_display = f"{_rs:+.1f}pp" if _spread else f"RS {_rs:.2f}"
                    print(f"     {_sym:<6} {_name:<25} {_chg:+.1f}%  {_rs_display}  {_label}")
                _unavail = [(sym, data) for sym, data in _rotation_map.items() if "status" in data and data["status"] == "UNAVAILABLE"]
                for _sym, _data in _unavail:
                    print(f"     {_sym:<6} {_data.get('name', _sym):<25} UNAVAILABLE")
                _ticker_sector = symp_etf
                if _ticker_sector and _ticker_sector in _rotation_map:
                    _ts_data = _rotation_map[_ticker_sector]
                    _ts_label = _ts_data.get("label", _ts_data.get("status", "UNKNOWN"))
                    _ts_name = _ts_data.get("name", _ticker_sector)
                    print(f"     >> Ticker sector: {_ticker_sector} ({_ts_name}) -- {_ts_label}")

            print(f"   RISK RADAR:   {radar_summary}")
            if _radar_details:
                for _rcat_name, _rcat_detail in _radar_details.items():
                    print(f"      {_rcat_name}: {_rcat_detail[:80]}")

            print(f"   SECTOR SYMPATHY: {symp_summary} (Sector: {symp_etf}, Margin: {symp_margin}%)")
            print(f"   IV GUARD:     {iv_guard_display}")

            _div_lockout_pm = ag_metrics.get("Dividend_Lockout", False)
            _div_ex_date_pm = ag_metrics.get("Ex_Date", "")
            if _div_lockout_pm:
                print(f"   DIVIDEND LOCKOUT: BLOCKED (ex-date {_div_ex_date_pm} -- within 24h)")
            else:
                print(f"   DIVIDEND LOCKOUT: None (no ex-date within 24h)")

            # [SEAS-001] Calendar Seasonality Context
            _seas_label_pm = ag_metrics.get("Seasonality_Label")
            _seas_month_pm = ag_metrics.get("Seasonality_Month", "")
            _seas_pct_pm = ag_metrics.get("Seasonality_Win_Pct")
            _seas_size_pm = ag_metrics.get("Seasonality_Sample_Size")
            if _seas_label_pm and _seas_label_pm != "UNAVAILABLE" and _seas_pct_pm is not None:
                print(f"   SEASONALITY:  {_seas_month_pm} {_seas_pct_pm}% positive ({_seas_size_pm}Y) -- {_seas_label_pm}")
            else:
                print(f"   SEASONALITY:  UNAVAILABLE")

            # [MOD-K + OPEX-001] Options Context (post-engine informational overlay)
            _opt_st_pm = _options_ctx.get("Options_Status", "UNAVAILABLE")
            if _opt_st_pm == "AVAILABLE":
                print("   --- OPTIONS CONTEXT ---")
                _pw_pm = _options_ctx.get("Options_Put_Wall")
                _pw_oi_pm = _options_ctx.get("Options_Put_Wall_OI")
                _pw_dist_pm = _options_ctx.get("Options_Put_Wall_Distance")
                _pw_note_pm = _options_ctx.get("Options_Put_Wall_Note", "")
                _pw_line_pm = "   Put Wall:      $%.2f (OI: %s)" % (_pw_pm, "{:,}".format(_pw_oi_pm) if _pw_oi_pm else "N/A")
                if _pw_dist_pm is not None:
                    _pw_line_pm += "  |  Distance: %+.1f ATR" % _pw_dist_pm
                if _pw_note_pm:
                    _pw_line_pm += "  |  FLOOR REINFORCEMENT"
                print(_pw_line_pm)

                _cw_pm = _options_ctx.get("Options_Call_Wall")
                _cw_oi_pm = _options_ctx.get("Options_Call_Wall_OI")
                _cw_dist_pm = _options_ctx.get("Options_Call_Wall_Distance")
                _cw_note_pm = _options_ctx.get("Options_Call_Wall_Note", "")
                _cw_line_pm = "   Call Wall:     $%.2f (OI: %s)" % (_cw_pm, "{:,}".format(_cw_oi_pm) if _cw_oi_pm else "N/A")
                if _cw_dist_pm is not None:
                    _cw_line_pm += "  |  Distance: %+.1f ATR" % _cw_dist_pm
                if _cw_note_pm:
                    _cw_line_pm += "  |  CEILING PRESSURE"
                print(_cw_line_pm)

                _mp_pm = _options_ctx.get("Options_Max_Pain")
                _mp_dist_pm = _options_ctx.get("Options_Max_Pain_Distance")
                _mp_line_pm = "   Max Pain:      $%.2f" % _mp_pm if _mp_pm else "   Max Pain:      N/A"
                if _mp_dist_pm is not None:
                    _mp_line_pm += "               |  Distance: %+.1f ATR" % _mp_dist_pm
                print(_mp_line_pm)

                _pcr_pm = _options_ctx.get("Options_PCR")
                _pcr_lbl_pm = _options_ctx.get("Options_PCR_Label")
                if _pcr_pm is not None:
                    print("   PCR:           %.2f (%s)" % (_pcr_pm, _pcr_lbl_pm))
                else:
                    print("   PCR:           UNAVAILABLE")

                _exp_dt_pm = _options_ctx.get("Options_Expiry_Date", "N/A")
                _exp_dte_pm = _options_ctx.get("Options_Expiry_DTE", "N/A")
                print("   Expiry:        %s (%s trading days)" % (_exp_dt_pm, _exp_dte_pm))

                _opt_diag_pm = _options_ctx.get("Options_Diagnostic", "")
                if "Partial data" in _opt_diag_pm:
                    print("   WARNING:       %s" % _opt_diag_pm)

                # OPEX advisory (spec S4.5)
                if _options_ctx.get("OPEX_Flag"):
                    _opex_tier_map = {"QUARTERLY_WITCHING": "OPEX (Quarterly/Witching)", "MONTHLY": "OPEX (Monthly)", "WEEKLY": "OPEX (Weekly)"}
                    print("   --- OPEX ADVISORY ---")
                    print("   Tier:          %s" % _opex_tier_map.get(_options_ctx.get("OPEX_Tier", "NONE"), "NONE"))
                    _adv_pm = _options_ctx.get("OPEX_Advisory", "")
                    if _adv_pm:
                        print("   Advisory:      %s" % _adv_pm)
                    _mpn_pm = _options_ctx.get("OPEX_Max_Pain_Note", "")
                    if _mpn_pm:
                        print("   Max Pain:      %s" % _mpn_pm)
                    if _options_ctx.get("OPEX_Afternoon_Flag"):
                        print("   Afternoon:     Afternoon session -- increased pin risk. Consider delaying new entries.")

            elif _opt_st_pm == "UNAVAILABLE" and _options_ctx.get("Options_Diagnostic"):
                print("   --- OPTIONS CONTEXT ---")
                print("   Status:        UNAVAILABLE")
                print("   Diagnostic:    %s" % _options_ctx.get("Options_Diagnostic", ""))
                # OPEX calendar is independent of Module K (spec S7)
                if _options_ctx.get("OPEX_Flag"):
                    _opex_tier_map_u = {"QUARTERLY_WITCHING": "OPEX (Quarterly/Witching)", "MONTHLY": "OPEX (Monthly)", "WEEKLY": "OPEX (Weekly)"}
                    print("   --- OPEX ADVISORY ---")
                    print("   Tier:          %s" % _opex_tier_map_u.get(_options_ctx.get("OPEX_Tier", "NONE"), "NONE"))
                    _adv_u_pm = _options_ctx.get("OPEX_Advisory", "")
                    if _adv_u_pm:
                        print("   Advisory:      %s" % _adv_u_pm)

            # [CT-001] CONTEXT ENRICHMENT block (Session B -- replaces standalone SHORT INTEREST)
            if not is_etf:
                print("   --- CONTEXT ENRICHMENT ---")

                # EARNINGS REVISION (Profile A, B, C)
                _er_eps_dir = _ct_merged.get("EPS_Revision_Direction", "UNAVAILABLE")
                _er_eps_pct = _ct_merged.get("EPS_Revision_Pct")
                _er_rev_dir = _ct_merged.get("Revenue_Revision_Direction", "UNAVAILABLE")
                _er_rev_pct = _ct_merged.get("Revenue_Revision_Pct")
                if _er_eps_dir == "UNAVAILABLE" and _er_rev_dir == "UNAVAILABLE":
                    print("   EARNINGS REVISION: UNAVAILABLE (Yahoo + Finnhub returned None)")
                else:
                    _eps_part = _er_eps_dir
                    if _er_eps_pct is not None:
                        _eps_part = "%s (%+.1f%% / 30d)" % (_er_eps_dir, _er_eps_pct)
                    elif _er_eps_dir != "UNAVAILABLE":
                        _eps_part = _er_eps_dir
                    else:
                        _eps_part = "N/A"
                    _rev_part = _er_rev_dir
                    if _er_rev_pct is not None:
                        _rev_part = "%s (%+.1f%% / 30d)" % (_er_rev_dir, _er_rev_pct)
                    elif _er_rev_dir != "UNAVAILABLE":
                        _rev_part = _er_rev_dir
                    else:
                        _rev_part = "N/A"
                    print("   EARNINGS REVISION: EPS %s | Revenue %s" % (_eps_part, _rev_part))

                # VALUATION (Profile B, C only)
                if profile in ("B", "C"):
                    _v_fpe = _ct_merged.get("Forward_PE")
                    _v_peg = _ct_merged.get("PEG_Ratio")
                    _v_ps = _ct_merged.get("PS_Ratio")
                    _v_label = _ct_merged.get("Valuation_Label", "UNAVAILABLE")
                    _v_smed = _ct_merged.get("Sector_Median_PE")
                    _fpe_str = "%.1f" % _v_fpe if _v_fpe is not None else "N/A"
                    _peg_str = "%.1f" % _v_peg if _v_peg is not None else "N/A"
                    _ps_str = "%.1f" % _v_ps if _v_ps is not None else "N/A"
                    _label_str = _v_label
                    if not _v_label.startswith("UNAVAILABLE") and _v_smed is not None:
                        _label_str = "%s (vs sector median %.1f)" % (_v_label, _v_smed)
                    elif _v_label == "UNAVAILABLE" and _v_fpe is None:
                        _label_str = "UNAVAILABLE (no forward P/E)"
                    elif _v_label == "UNAVAILABLE" and _v_smed is None:
                        _label_str = "UNAVAILABLE (sector ETF not in cache)"
                    _val_line = "Forward P/E %s | PEG %s | P/S %s | %s" % (_fpe_str, _peg_str, _ps_str, _label_str)
                    if _staleness_warn:
                        _val_line += _staleness_warn
                    print("   VALUATION:    %s" % _val_line)

                # SHORT INTEREST (Profile A, B only)
                if profile in ("A", "B"):
                    _si_label_pm = ag_metrics.get("Short_Interest_Label")
                    _si_pct_pm = ag_metrics.get("Short_Interest_Pct")
                    _si_note_pm = ag_metrics.get("Short_Interest_Note")
                    if _si_label_pm and _si_label_pm != "UNAVAILABLE" and _si_pct_pm is not None:
                        _si_line_pm = "%.1f%% of float | %s" % (_si_pct_pm, _si_label_pm)
                        if _si_note_pm:
                            _si_line_pm += " -- %s" % _si_note_pm
                        print("   SHORT INTEREST: %s" % _si_line_pm)
                    else:
                        print("   SHORT INTEREST: UNAVAILABLE")

                # MARGIN TRAJECTORY (Profile B, C only)
                if profile in ("B", "C"):
                    _gm_trend = _ct_merged.get("Gross_Margin_Trend", "UNAVAILABLE")
                    _om_trend = _ct_merged.get("Operating_Margin_Trend", "UNAVAILABLE")
                    _gm_delta = _ct_merged.get("Gross_Margin_Delta_pp")
                    _om_delta = _ct_merged.get("Operating_Margin_Delta_pp")
                    if _gm_trend == "UNAVAILABLE" and _om_trend == "UNAVAILABLE":
                        print("   MARGIN TRAJECTORY: UNAVAILABLE")
                    else:
                        _gm_str = _gm_trend if _gm_trend else "UNAVAILABLE"
                        _om_str = _om_trend if _om_trend else "UNAVAILABLE"
                        _gm_delta_str = " (%+.1fpp YoY)" % _gm_delta if _gm_delta is not None else ""
                        _om_delta_str = " (%+.1fpp YoY)" % _om_delta if _om_delta is not None else ""
                        print("   MARGIN TRAJECTORY: Gross %s%s | Operating %s%s" % (_gm_str, _gm_delta_str, _om_str, _om_delta_str))

                # SOURCE line (always shown)
                print("   SOURCE:       Yahoo Finance (primary) | %s" % _ct_source_detail)

            if _vision_climax:
                print(f"   VOL CLIMAX:   DETECTED (3-bar execution block per Doc 2 §II)")

            # ENGINE STATUS (Three-State for EXISTING)
            if _has_exit_signal:
                _pm_determination = f"EXIT ({_exit_sig} -- {_exit_triggers})"
            elif any(a["severity"] in ("EMERGENCY", "CRITICAL") for a in _advisories):
                _pm_determination = "HOLD (advisory risk active -- no adds recommended)"
            else:
                _pm_determination = "FIT FOR ADD (all clear -- proceeds to sizing)"
            print(f"   ENGINE STATUS: {_pm_determination}")

            # ENGINE CONTEXT
            _pm_di_plus = metrics.get('DI_Plus') or 0
            _pm_di_minus = metrics.get('DI_Minus') or 0
            _pm_floor_label = "VWAP" if profile == "A" else ("Wk SMA 200" if profile == "C" else ("EMA 8" if "RESOLVING" in str(_engine_state).upper() and not is_etf else "SMA 50"))
            _pm_wlimit = window_limits.get(profile, '0-5')
            _pm_wmax = _pm_wlimit.split('-')[1] if '-' in str(_pm_wlimit) else '?'
            _pm_ctx = f"{_engine_state} | Win {metrics.get('window_count') or 'N/A'}/{_pm_wmax} | Floor: {_pm_floor_label} | DI: +{_pm_di_plus} vs -{_pm_di_minus}"
            if _exit_sig in ("WARNING", "EXIT"):
                _pm_ctx += f" | Exit: {_exit_sig} ({_exit_triggers})"
            print(f"   ENGINE CONTEXT: {_pm_ctx}")

            # --- Position Metrics ---
            print(f"\n   --- POSITION METRICS ---")
            print(f"   CURRENT PRICE: ${current_price}")
            print(f"   ENTRY PRICE:   ${entry_price_override}")
            print(f"   UNREALIZED PL: {_pl_sign}${unrealized_pl} ({_pl_sign}{pl_pct}%)")
            print(f"   R-MULTIPLE:    {r_multiple}R")
            print(f"   STRUCT FLOOR:  ${structural_floor} ({_pm_floor_label})")
            print(f"   HARD STOP:     ${stop_price} (Floor - 1.5 ATR)")
            print(f"   DIST TO STOP:  ${dist_to_stop} ({dist_to_stop_atr} ATR)")
            print(f"   STOP RISK:     ${stop_risk_remaining}")

            # --- Trend Health ---
            _ths_score = metrics.get('Trend_Health_Score')
            if _ths_score is not None:
                _ths_label = metrics.get('THS_Label', '')
                _ths_warn  = " [!]" if _ths_score < 40 else ""
                print(f"\n   --- TREND HEALTH ---")
                print(f"   TREND HEALTH: {_ths_score} / 100 ({_ths_label}){_ths_warn}")
                print(f"   │ Floor Buffer:   {metrics.get('THS_Floor_Buffer', '-')}")
                print(f"   │ Dir. Momentum:  {metrics.get('THS_Dir_Momentum', '-')}")
                print(f"   │ Trend Age:      {metrics.get('THS_Trend_Age', '-')}  (Day {metrics.get('Trend_Age_Bars', '?')})")
                print(f"   │ Structure:      {metrics.get('THS_Structure', '-')}")

            # --- Final Determination (Position Monitor) ---
            print(f"\n   --- FINAL DETERMINATION ---")
            if recommendation == "EXIT":
                print(f"   FINAL STATUS: EXIT --- Position structural health deteriorating")
            elif recommendation == "NO ACTION":
                print(f"   FINAL STATUS: HOLD --- Advisory risk active, no adds recommended")
            else:
                print(f"   FINAL STATUS: FIT FOR ADD --- Proceeds to sizing")
            print(f"{'='*80}\n")

            if recommendation == "EXIT":
                return f"MONITOR|EXIT| {regime} | PL: {_pl_sign}${unrealized_pl} ({_pl_sign}{pl_pct}%) | R: {r_multiple}R"
            if recommendation == "NO ACTION":
                return f"MONITOR|NO_ACTION| {regime} | PL: {_pl_sign}${unrealized_pl} ({_pl_sign}{pl_pct}%) | R: {r_multiple}R"

            print(f"[....] [STEP 7-8] FIT FOR ADD confirmed. Proceeding to add sizing...")

        if not step6_passed:
            # [Amendment v0.2] Pipeline continues regardless. Engine metrics may be partial.
            print("[WARN] Step 4 did not pass -- sizing will use available data where possible")

        # ==================================================================
        # STEP 7 & 8: SIZING & FINAL AUTH
        # ==================================================================
        multiplier = 1.0   # GOV-002: standard base unit, no automatic modifiers

        # Collect caution factors for display (advisory only, do not modify multiplier)
        caution_factors = []
        if "DEFENSIVE" in regime:
            caution_factors.append("DEFENSIVE regime -- Profile B/C long-term adds carry elevated risk")
        if event_aware:
            caution_factors.append(f"Earnings within buffer window ({_binary_details[:60]})")
        if "TURNAROUND" in audit_status:
            caution_factors.append("Turnaround Patch -- asset cleared via recovery criteria")
        if storm_watch_active:
            caution_factors.append("Storm Watch active (VIX >= 25)")
        if system_overheat:
            caution_factors.append("System Overheat: recent consecutive loss streak")
        if "LOW" in (metrics.get("Conviction") or ""):
            caution_factors.append("Low-Conviction Range")
        if "ACTIVE" in (metrics.get("Inst_Churn") or ""):
            caution_factors.append("C-1/C-2 convexity -- position approaching full allocation")

        entry_price = metrics.get('Price') or 0
        stop_price = metrics.get('Hard_Stop') or 0
        structural_floor = metrics.get('Structural_Floor') or 0
        window_val = metrics.get('window_count') or 'N/A'
        floor_type = metrics.get('Anchor_Type') or 'Standard'

        if iv_guard_limit_only:
            order_type = "LIMIT"
        elif "WEAKENED" in audit_status or "TERMINATED" in audit_status:
            order_type = "MARKET"
        else:
            order_type = "LIMIT"

        risk_per_share = round(entry_price - stop_price, 2) if stop_price else 0
        target_price = "N/A"
        dynamic_label, dynamic_val = "INFO", "N/A"

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
                target_src = metrics.get('Profit_Target_Source', '')
                if target_src:
                    dynamic_val += f" ({target_src})"
            else:
                dynamic_label, dynamic_val = "EXPECTANCY", "SUPPRESSED (Exit_Signal or price > resistance)"
        elif profile == "B":
            ema8 = metrics.get('EMA_8') or entry_price
            atr = metrics.get('ATR') or 1.0
            extension = round((entry_price - ema8) / atr, 2) if atr > 0 else 0
            dynamic_label, dynamic_val = "EXTENSION", f"{extension} ATR"
            if engine_target is not None:
                target_price = engine_target
            elif metrics.get('Profit_Target_Synthetic') is not None:
                target_price = metrics.get('Profit_Target_Synthetic')
            else:
                target_price = "SUPPRESSED"
        elif profile == "C":
            sma200 = metrics.get('SMA_200') or entry_price
            proximity = round(abs(entry_price - sma200) / sma200 * 100, 2) if sma200 > 0 else 0
            dynamic_label, dynamic_val = "PROXIMITY", f"{proximity}% (200-SMA)"
            target_price = "OPEN-ENDED"

        symp_summary = symp_metrics.get("Sympathy_Status", "N/A")
        symp_etf = symp_metrics.get("Sector_ETF", "N/A")
        symp_margin = symp_metrics.get("Sympathy_Margin_Pct", "N/A")
        iv_guard_display = ag_metrics.get("IV_Guard_Action", "N/A")

        # (Strategy alignment details are rendered in the Unified Dashboard below)

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
            _verdicts["Sizing"] = ("HALT", f"Utility Gate -- Open Risk ${open_risk_heat:.2f} < $50")
            print(f"[HALT] [STEP 7] SIZING: Utility Gate -- Open Risk (${open_risk_heat:.2f}) < $50 minimum")
        else:
            _verdicts["Sizing"] = ("PASS", f"{final_units} units, heat ${open_risk_heat:.2f}")

        _sizing_label = "ADD SIZING" if position_monitor else "FINAL SIZING"
        _sizing_mode = "(PREVIEW)" if mode == "INFO" else ""
        print(f"[STEP 7] SIZING RESULT: {final_units} Units (Capital: ${final_units * entry_price:.2f} | Risk: ${open_risk_heat:.2f})")

        if position_monitor:
            _new_total = shares + final_units
            _avg_cost = round(((entry_price_override * shares) + (entry_price * final_units)) / _new_total, 4)
            _new_risk = round(_new_total * risk_per_share, 2)
            print(f"   EXISTING:     {shares} shares @ ${entry_price_override}")
            print(f"   AFTER ADD:    {_new_total} shares @ ${_avg_cost} avg cost")
            print(f"   COMBINED RISK:${_new_risk}")

        # ==================================================================
        # UNIFIED FINAL DASHBOARD (Amendment v0.2)
        # ==================================================================

        # GOV-002: check only verdict statuses -- no _sentinel_blocked or _no_adds
        # CLEAN = fundamentals bypassed (Profile A). LIMIT_ONLY = IV guard (pass-equivalent).
        _pass_equivalent = ("PASS", "EXEMPT", "N/A", "SKIPPED", "CLEAN", "LIMIT_ONLY", None)
        _all_verdicts_pass = all(
            v[0] in _pass_equivalent
            for v in _verdicts.values() if v is not None
        )

        # Determine urgency tier
        _has_halt = any(v[0] == "HALT" for v in _verdicts.values() if v is not None)
        _has_warn = any(v[0] == "WARN" for v in _verdicts.values() if v is not None)

        if _sentinel_tier == "EMERGENCY":
            _urgency = "EMERGENCY"
        elif _sentinel_tier == "CRITICAL" or _has_halt:
            _urgency = "CRITICAL"
        elif _has_warn or _sentinel_tier == "ADVISORY":
            _urgency = "ADVISORY"
        else:
            _urgency = "INFORMATIONAL"

        # [PMC-001] OVERNIGHT BRIEFING rendering (Candidate path)
        if _overnight_ctx and _overnight_ctx.get("Overnight_Status") == "AVAILABLE":
            print("\n   ==================================================================")
            print("   OVERNIGHT BRIEFING (Pre-Session Context)")
            print("   ==================================================================")
            _ov_es_pct = _overnight_ctx.get("Overnight_ES_Change_Pct")
            _ov_nq_pct = _overnight_ctx.get("Overnight_NQ_Change_Pct")
            _ov_es_str = "%+.1f%%" % _ov_es_pct if _ov_es_pct is not None else _overnight_ctx.get("Overnight_ES_Direction", "N/A")
            _ov_nq_str = "%+.1f%%" % _ov_nq_pct if _ov_nq_pct is not None else _overnight_ctx.get("Overnight_NQ_Direction", "N/A")
            _ov_sent = _overnight_ctx.get("Overnight_Sentiment", "N/A")
            print("   Futures:      ES %s | NQ %s | Session bias: %s" % (_ov_es_str, _ov_nq_str, _ov_sent))
            _ov_nk = _overnight_ctx.get("Overnight_Nikkei_Pct")
            _ov_hs = _overnight_ctx.get("Overnight_HangSeng_Pct")
            _ov_sh = _overnight_ctx.get("Overnight_Shanghai_Pct")
            print("   Asia:         Nikkei %s | Hang Seng %s | Shanghai %s" % (
                "%+.1f%%" % _ov_nk if _ov_nk is not None else "N/A",
                "%+.1f%%" % _ov_hs if _ov_hs is not None else "N/A",
                "%+.1f%%" % _ov_sh if _ov_sh is not None else "N/A"))
            _ov_stoxx = _overnight_ctx.get("Overnight_Stoxx600_Pct")
            _ov_dax = _overnight_ctx.get("Overnight_DAX_Pct")
            print("   Europe:       STOXX 600 %s | DAX %s" % (
                "%+.1f%%" % _ov_stoxx if _ov_stoxx is not None else "N/A",
                "%+.1f%%" % _ov_dax if _ov_dax is not None else "N/A"))
            _ov_oil = _overnight_ctx.get("Overnight_Oil_WTI_Pct")
            _ov_gold = _overnight_ctx.get("Overnight_Gold_Pct")
            print("   Commodities:  WTI %s | Gold %s" % (
                "%+.1f%%" % _ov_oil if _ov_oil is not None else "N/A",
                "%+.1f%%" % _ov_gold if _ov_gold is not None else "N/A"))
            _ov_vix_lvl = _overnight_ctx.get("Overnight_VIX_Level")
            _ov_vix_dir = _overnight_ctx.get("Overnight_VIX_Direction", "UNAVAILABLE")
            _ov_vix_chg = _overnight_ctx.get("Overnight_VIX_Change_Pct")
            if _ov_vix_lvl is not None:
                _ov_vix_str = "%.1f" % _ov_vix_lvl
                if _ov_vix_chg is not None:
                    _ov_vix_str += " (%s %+.1f%%)" % (_ov_vix_dir, _ov_vix_chg)
                else:
                    _ov_vix_str += " (%s)" % _ov_vix_dir
            else:
                _ov_vix_str = "UNAVAILABLE"
            print("   VIX Futures:  %s" % _ov_vix_str)
            _ov_hl = _overnight_ctx.get("Overnight_Headlines") or []
            if _ov_hl:
                print("   Headlines:    %s" % _ov_hl[0])
                for _h in _ov_hl[1:]:
                    print("                 %s" % _h)
            print("   SOURCE:       Gemini Search (financial news, futures data)")
        elif _overnight_ctx:
            _ov_diag = _overnight_ctx.get("Overnight_Diagnostic") or "Gemini Search error"
            print("\n   ==================================================================")
            print("   OVERNIGHT BRIEFING: UNAVAILABLE (%s)" % _ov_diag)
            print("   ==================================================================")

        # --- Block 1: Urgency Indicator ---
        if _urgency == "EMERGENCY":
            print(f"\n{'='*80}\n[EMERGENCY] {regime} regime active. Harvest recommendation in position monitor mode.\n{'='*80}")
        elif _urgency == "CRITICAL":
            print(f"\n{'='*80}\n[CRITICAL] Non-PASS verdicts detected. Review all findings before proceeding.\n{'='*80}")

        # --- Block 2: Verdict Summary ---
        print(f"\n{'='*80}")
        print(f"*** UNIFIED DASHBOARD: {ticker} | {profile_display} | {mode} | {position_status} ***")
        print(f"{'='*80}")
        print(f"\n   --- VERDICT SUMMARY ---")
        _step_labels = {
            "Sentinel": "Step 1", "Risk_Radar": "Step 2a", "Sector_Sympathy": "Step 2b",
            "Asset_Gates": "Step 2c", "Fundamentals": "Step 3", "Tech_Engine": "Step 4",
            "Chart_Verify": "Step 5", "Capacity": "Step 6", "Sizing": "Step 7"
        }
        _step_order = ["Sentinel", "Risk_Radar", "Sector_Sympathy", "Asset_Gates",
                       "Fundamentals", "Tech_Engine", "Chart_Verify", "Capacity", "Sizing"]
        for _sk in _step_order:
            _sv = _verdicts.get(_sk)
            if _sv is not None:
                _v_status, _v_detail = _sv
                _v_label = _step_labels.get(_sk, _sk)
                _tag = ""
                if _v_status in ("HALT", "ERROR"):
                    _tag = " [BLOCKED]"
                elif _v_status == "WARN":
                    _tag = " [ADVISORY]"
                print(f"   {_v_label:8s} {_sk:18s}: {_v_status}{_tag} -- {_v_detail[:60]}")

        # --- Block 3: Strategy Alignment ---
        # [Addendum v0.3, Change 8] Order: POSITION, CONVEXITY → MACRO → gates → ENGINE last
        print(f"\n   --- STRATEGY ALIGNMENT ---")

        # POSITION (first)
        if position_monitor:
            print(f"   POSITION:     EXISTING (Entry: ${entry_price_override} | {shares} shares)")
        else:
            print(f"   POSITION:     {position_status}")

        # CONVEXITY
        if convexity_class:
            _cvx_role = metrics.get('Profit_Target_Role') or 'PRESCRIPTIVE'
            print(f"   CONVEXITY:    C-{convexity_class[1]} ({_cvx_role})")

        # [FRR-001] Fundamental R:R (Profile B only)
        _frr_val = metrics.get('Fundamental_RR')
        _frr_label = metrics.get('Fundamental_RR_Label')
        if _frr_val is not None:
            _frr_tgt = metrics.get('Fundamental_Target')
            _frr_flr = metrics.get('Fundamental_Floor')
            _frr_cnt = metrics.get('Fundamental_Analyst_Count')
            _frr_src = metrics.get('Profit_Target_Source', '')
            print(f"   FUNDAMENTAL R:R: {_frr_val} ({_frr_label}) | Target: ${_frr_tgt} Floor: ${_frr_flr} | {_frr_cnt} analysts | {_frr_src}")
            _frr_note = metrics.get('Fundamental_RR_Note')
            if _frr_note:
                print(f"   ANALYST NOTE: {_frr_note}")

        # [Change 7] MACRO REGIME: merged REGIME + SENTINEL tier
        if _sentinel_tier != "INFORMATIONAL":
            print(f"   MACRO REGIME: {regime} [{_sentinel_tier}]")
        else:
            print(f"   MACRO REGIME: {regime}")

        # GOV-002: Sector Rotation Map (non-GREEN regimes only)
        _rotation_map = sentinel_details.get("rotation_map", {})
        if _rotation_map and "BULLISH" not in regime and "DEFENSIVE" not in regime:
            print(f"\n   SECTOR ROTATION (20-bar vs SPY):")
            _sorted_sectors = sorted(
                [(sym, data) for sym, data in _rotation_map.items() if "rs" in data],
                key=lambda x: x[1].get("rs", 0),
                reverse=True
            )
            for _sym, _data in _sorted_sectors:
                _name = _data.get("name", _sym)
                _chg = _data.get("change_20", 0)
                _rs = _data.get("rs", 0)
                _label = _data.get("label", "UNAVAILABLE")
                _spread = _data.get("spread_mode", False)
                _rs_display = f"{_rs:+.1f}pp" if _spread else f"RS {_rs:.2f}"
                print(f"     {_sym:<6} {_name:<25} {_chg:+.1f}%  {_rs_display}  {_label}")
            _unavail = [(sym, data) for sym, data in _rotation_map.items() if "status" in data and data["status"] == "UNAVAILABLE"]
            for _sym, _data in _unavail:
                print(f"     {_sym:<6} {_data.get('name', _sym):<25} UNAVAILABLE")
            _ticker_sector = symp_etf
            if _ticker_sector and _ticker_sector in _rotation_map:
                _ts_data = _rotation_map[_ticker_sector]
                _ts_label = _ts_data.get("label", _ts_data.get("status", "UNKNOWN"))
                _ts_name = _ts_data.get("name", _ticker_sector)
                print(f"     >> Ticker sector: {_ticker_sector} ({_ts_name}) -- {_ts_label}")

        # [Change 9] RISK RADAR with sub-lines
        print(f"   RISK RADAR:   {radar_summary}")
        if _radar_details:
            for _rcat_name, _rcat_detail in _radar_details.items():
                print(f"      {_rcat_name}: {_rcat_detail[:80]}")

        # [Change 10] SECTOR SYMPATHY
        print(f"   SECTOR SYMPATHY: {symp_summary} (Sector: {symp_etf}, Margin: {symp_margin}%)")

        # IV GUARD
        print(f"   IV GUARD:     {iv_guard_display}")

        # [Change 6] DIVIDEND LOCKOUT
        _div_lockout = ag_metrics.get("Dividend_Lockout", False)
        _div_ex_date = ag_metrics.get("Ex_Date", "")
        if _div_lockout:
            print(f"   DIVIDEND LOCKOUT: BLOCKED (ex-date {_div_ex_date} -- within 24h)")
        else:
            print(f"   DIVIDEND LOCKOUT: None (no ex-date within 24h)")

        # [SEAS-001] Calendar Seasonality Context
        _seas_label = ag_metrics.get("Seasonality_Label")
        _seas_month = ag_metrics.get("Seasonality_Month", "")
        _seas_pct = ag_metrics.get("Seasonality_Win_Pct")
        _seas_size = ag_metrics.get("Seasonality_Sample_Size")
        if _seas_label and _seas_label != "UNAVAILABLE" and _seas_pct is not None:
            print(f"   SEASONALITY:  {_seas_month} {_seas_pct}% positive ({_seas_size}Y) -- {_seas_label}")
        else:
            print(f"   SEASONALITY:  UNAVAILABLE")

        # [MOD-K + OPEX-001] Options Context (post-engine informational overlay)
        _opt_st_c = _options_ctx.get("Options_Status", "UNAVAILABLE")
        if _opt_st_c == "AVAILABLE":
            print("   --- OPTIONS CONTEXT ---")
            _pw_c = _options_ctx.get("Options_Put_Wall")
            _pw_oi_c = _options_ctx.get("Options_Put_Wall_OI")
            _pw_dist_c = _options_ctx.get("Options_Put_Wall_Distance")
            _pw_note_c = _options_ctx.get("Options_Put_Wall_Note", "")
            _pw_line_c = "   Put Wall:      $%.2f (OI: %s)" % (_pw_c, "{:,}".format(_pw_oi_c) if _pw_oi_c else "N/A")
            if _pw_dist_c is not None:
                _pw_line_c += "  |  Distance: %+.1f ATR" % _pw_dist_c
            if _pw_note_c:
                _pw_line_c += "  |  FLOOR REINFORCEMENT"
            print(_pw_line_c)

            _cw_c = _options_ctx.get("Options_Call_Wall")
            _cw_oi_c = _options_ctx.get("Options_Call_Wall_OI")
            _cw_dist_c = _options_ctx.get("Options_Call_Wall_Distance")
            _cw_note_c = _options_ctx.get("Options_Call_Wall_Note", "")
            _cw_line_c = "   Call Wall:     $%.2f (OI: %s)" % (_cw_c, "{:,}".format(_cw_oi_c) if _cw_oi_c else "N/A")
            if _cw_dist_c is not None:
                _cw_line_c += "  |  Distance: %+.1f ATR" % _cw_dist_c
            if _cw_note_c:
                _cw_line_c += "  |  CEILING PRESSURE"
            print(_cw_line_c)

            _mp_c = _options_ctx.get("Options_Max_Pain")
            _mp_dist_c = _options_ctx.get("Options_Max_Pain_Distance")
            _mp_line_c = "   Max Pain:      $%.2f" % _mp_c if _mp_c else "   Max Pain:      N/A"
            if _mp_dist_c is not None:
                _mp_line_c += "               |  Distance: %+.1f ATR" % _mp_dist_c
            print(_mp_line_c)

            _pcr_c = _options_ctx.get("Options_PCR")
            _pcr_lbl_c = _options_ctx.get("Options_PCR_Label")
            if _pcr_c is not None:
                print("   PCR:           %.2f (%s)" % (_pcr_c, _pcr_lbl_c))
            else:
                print("   PCR:           UNAVAILABLE")

            _exp_dt_c = _options_ctx.get("Options_Expiry_Date", "N/A")
            _exp_dte_c = _options_ctx.get("Options_Expiry_DTE", "N/A")
            print("   Expiry:        %s (%s trading days)" % (_exp_dt_c, _exp_dte_c))

            _opt_diag_c = _options_ctx.get("Options_Diagnostic", "")
            if "Partial data" in _opt_diag_c:
                print("   WARNING:       %s" % _opt_diag_c)

            # OPEX advisory (spec S4.5)
            if _options_ctx.get("OPEX_Flag"):
                _opex_tier_map_c = {"QUARTERLY_WITCHING": "OPEX (Quarterly/Witching)", "MONTHLY": "OPEX (Monthly)", "WEEKLY": "OPEX (Weekly)"}
                print("   --- OPEX ADVISORY ---")
                print("   Tier:          %s" % _opex_tier_map_c.get(_options_ctx.get("OPEX_Tier", "NONE"), "NONE"))
                _adv_c = _options_ctx.get("OPEX_Advisory", "")
                if _adv_c:
                    print("   Advisory:      %s" % _adv_c)
                _mpn_c = _options_ctx.get("OPEX_Max_Pain_Note", "")
                if _mpn_c:
                    print("   Max Pain:      %s" % _mpn_c)
                if _options_ctx.get("OPEX_Afternoon_Flag"):
                    print("   Afternoon:     Afternoon session -- increased pin risk. Consider delaying new entries.")

        elif _opt_st_c == "UNAVAILABLE" and _options_ctx.get("Options_Diagnostic"):
            print("   --- OPTIONS CONTEXT ---")
            print("   Status:        UNAVAILABLE")
            print("   Diagnostic:    %s" % _options_ctx.get("Options_Diagnostic", ""))
            # OPEX calendar is independent of Module K (spec S7)
            if _options_ctx.get("OPEX_Flag"):
                _opex_tier_map_uc = {"QUARTERLY_WITCHING": "OPEX (Quarterly/Witching)", "MONTHLY": "OPEX (Monthly)", "WEEKLY": "OPEX (Weekly)"}
                print("   --- OPEX ADVISORY ---")
                print("   Tier:          %s" % _opex_tier_map_uc.get(_options_ctx.get("OPEX_Tier", "NONE"), "NONE"))
                _adv_uc = _options_ctx.get("OPEX_Advisory", "")
                if _adv_uc:
                    print("   Advisory:      %s" % _adv_uc)

        # [FLOW-001 + MOD-M] INSTITUTIONAL CONTEXT (post-engine informational overlay)
        # Candidate evaluation path only -- not rendered on PM path.
        if _inst_ctx:
            _ic_flow_st = _inst_ctx.get("Flow_Status", "UNAVAILABLE")
            _ic_ins_st = _inst_ctx.get("Insider_Status", "UNAVAILABLE")

            print("   --- INSTITUTIONAL CONTEXT ---")

            if _ic_flow_st == "UNAVAILABLE" and _ic_ins_st in ("UNAVAILABLE", "N/A"):
                _ic_diag = _inst_ctx.get("Institutional_Diagnostic", "Gemini Search error")
                print("   UNAVAILABLE (%s). Pipeline unaffected." % _ic_diag)
            else:
                # --- FLOW ACTIVITY sub-section (always) ---
                if _ic_flow_st == "AVAILABLE":
                    print("   --- FLOW ACTIVITY (5-DAY) ---")
                    _ic_dp = _inst_ctx.get("Flow_Dark_Pool_Pct")
                    _ic_dp_avg = _inst_ctx.get("Flow_Dark_Pool_Avg_Pct")
                    _ic_dp_sent = _inst_ctx.get("Flow_Dark_Pool_Sentiment", "UNAVAILABLE")
                    if _ic_dp is not None:
                        _ic_dp_line = "   Dark Pool:    %.1f%% of volume" % _ic_dp
                        if _ic_dp_avg is not None:
                            _ic_dp_line += " (avg %.1f%%)" % _ic_dp_avg
                        _ic_dp_line += " | %s" % _ic_dp_sent
                        print(_ic_dp_line)
                    else:
                        print("   Dark Pool:    UNAVAILABLE")

                    _ic_bt = _inst_ctx.get("Flow_Block_Trades_Count", 0)
                    _ic_bt_n = _inst_ctx.get("Flow_Block_Trades_Notable")
                    if _ic_bt > 0:
                        _ic_bt_line = "   Block Trades: %d trades > $1M" % _ic_bt
                        if _ic_bt_n:
                            _ic_bt_line += " | %s" % _ic_bt_n
                        print(_ic_bt_line)
                    else:
                        print("   Block Trades: None reported")

                    _ic_sb = _inst_ctx.get("Flow_Sweep_Bullish_Count", 0)
                    _ic_se = _inst_ctx.get("Flow_Sweep_Bearish_Count", 0)
                    _ic_sn = _inst_ctx.get("Flow_Sweep_Notable")
                    if _ic_sb > 0 or _ic_se > 0:
                        _ic_sw_line = "   Sweeps:       %d bullish / %d bearish" % (_ic_sb, _ic_se)
                        if _ic_sn:
                            _ic_sw_line += " | %s" % _ic_sn
                        print(_ic_sw_line)
                    else:
                        print("   Sweeps:       None reported")

                    _ic_wh = _inst_ctx.get("Flow_Whale_13F")
                    if _ic_wh and _ic_wh != "UNAVAILABLE":
                        print("   13F Changes:  %s" % _ic_wh)
                    else:
                        print("   13F Changes:  UNAVAILABLE")

                    print("   FLOW SIGNAL:  %s" % _inst_ctx.get("Flow_Label", "INSUFFICIENT DATA"))
                    print("   SOURCE:       Gemini Search (FINRA ATS, SEC EDGAR, financial news)")
                else:
                    print("   --- FLOW ACTIVITY: INSUFFICIENT DATA ---")
                    print("   SOURCE:       Gemini Search (data not available for this ticker)")

                # --- INSIDER ACTIVITY sub-section (non-ETF only) ---
                if not is_etf:
                    if _ic_ins_st == "AVAILABLE":
                        _ic_bc = _inst_ctx.get("Insider_Buy_Count_30d", 0)
                        _ic_sc = _inst_ctx.get("Insider_Sell_Count_30d", 0)
                        if _ic_bc == 0 and _ic_sc == 0:
                            print("   --- INSIDER ACTIVITY: No Form 4 filings in 30-day window. ---")
                        else:
                            print("   --- INSIDER ACTIVITY (30-DAY) ---")
                            _ic_bv = _inst_ctx.get("Insider_Buy_Total_Value_30d")
                            _ic_bn = _inst_ctx.get("Insider_Buy_Notable")
                            _ic_buy_line = "   BUYS:         %d insiders" % _ic_bc
                            if _ic_bv is not None:
                                if _ic_bv >= 1000000:
                                    _ic_buy_line += " | $%.1fM total" % (_ic_bv / 1000000)
                                elif _ic_bv >= 1000:
                                    _ic_buy_line += " | $%dK total" % int(_ic_bv / 1000)
                                else:
                                    _ic_buy_line += " | $%d total" % int(_ic_bv)
                            if _ic_bn:
                                _ic_buy_line += " | %s" % _ic_bn
                            print(_ic_buy_line)

                            _ic_sv = _inst_ctx.get("Insider_Sell_Total_Value_30d")
                            _ic_sn_ins = _inst_ctx.get("Insider_Sell_Notable")
                            _ic_sell_line = "   SELLS:        %d insiders" % _ic_sc
                            if _ic_sv is not None:
                                if _ic_sv >= 1000000:
                                    _ic_sell_line += " | $%.1fM total" % (_ic_sv / 1000000)
                                elif _ic_sv >= 1000:
                                    _ic_sell_line += " | $%dK total" % int(_ic_sv / 1000)
                                else:
                                    _ic_sell_line += " | $%d total" % int(_ic_sv)
                            if _ic_sn_ins:
                                _ic_sell_line += " | %s" % _ic_sn_ins
                            print(_ic_sell_line)

                            _ic_bsr = _inst_ctx.get("Insider_BS_Ratio_30d")
                            _ic_cl = _inst_ctx.get("Insider_Cluster_Buy", False)
                            _ic_r_str = "%.2f" % _ic_bsr if _ic_bsr is not None else "N/A"
                            _ic_wt = "buy-weighted" if _ic_bsr is not None and _ic_bsr > 0.5 else ("sell-weighted" if _ic_bsr is not None and _ic_bsr < 0.5 else "neutral")
                            _ic_cl_str = "YES" if _ic_cl else "NO"
                            print("   RATIO:        %s (%s) | CLUSTER BUY: %s" % (_ic_r_str, _ic_wt, _ic_cl_str))
                            print("   SOURCE:       SEC EDGAR Form 4 via Gemini Search")
                    elif _ic_ins_st == "UNAVAILABLE":
                        _ic_ins_diag = _inst_ctx.get("Institutional_Diagnostic", "Gemini Search error")
                        print("   --- INSIDER ACTIVITY: UNAVAILABLE (%s) ---" % _ic_ins_diag)

                # [PMC-001] --- PRE-MARKET CONTEXT sub-section (Layer 2, all assets) ---
                _ic_pmc_st = _inst_ctx.get("PMC_Status", "UNAVAILABLE")
                if _ic_pmc_st == "UNAVAILABLE":
                    print("   --- PRE-MARKET CONTEXT: UNAVAILABLE (parse error) ---")
                elif _ic_pmc_st == "AVAILABLE":
                    _ic_pmc_gap = _inst_ctx.get("PMC_Gap_Pct")
                    _ic_pmc_dir = _inst_ctx.get("PMC_Gap_Direction", "UNAVAILABLE")
                    _ic_pmc_ah = _inst_ctx.get("PMC_Afterhours_Notable")
                    _ic_pmc_news = _inst_ctx.get("PMC_Overnight_News")
                    _ic_pmc_sect = _inst_ctx.get("PMC_Sector_Commodity_Note")
                    _ic_pmc_cat = _inst_ctx.get("PMC_Catalyst_Flag", False)
                    _ic_pmc_all_empty = (
                        _ic_pmc_gap is None
                        and _ic_pmc_dir in ("UNAVAILABLE", "FLAT")
                        and not _ic_pmc_ah
                        and not _ic_pmc_news
                        and not _ic_pmc_sect
                        and not _ic_pmc_cat
                    )
                    if _ic_pmc_all_empty:
                        print("   --- PRE-MARKET CONTEXT: No significant overnight activity. ---")
                    else:
                        print("   --- PRE-MARKET CONTEXT ---")
                        _ic_cat_tag = " [CATALYST]" if _ic_pmc_cat else ""
                        if _ic_pmc_gap is not None:
                            print("   Gap:          %+.1f%% (%s)%s" % (_ic_pmc_gap, _ic_pmc_dir, _ic_cat_tag))
                        elif _ic_cat_tag:
                            print("   Gap:          %s%s" % (_ic_pmc_dir, _ic_cat_tag))
                        if _ic_pmc_ah:
                            print("   After-Hours:  %s" % _ic_pmc_ah)
                        if _ic_pmc_news:
                            print("   Overnight:    %s" % _ic_pmc_news)
                        if _ic_pmc_sect:
                            print("   Sector:       %s" % _ic_pmc_sect)

        # [CT-001] CONTEXT ENRICHMENT block (Session B -- replaces standalone SHORT INTEREST)
        if not is_etf:
            print("   --- CONTEXT ENRICHMENT ---")

            # EARNINGS REVISION (Profile A, B, C)
            _er_eps_dir_c = _ct_merged.get("EPS_Revision_Direction", "UNAVAILABLE")
            _er_eps_pct_c = _ct_merged.get("EPS_Revision_Pct")
            _er_rev_dir_c = _ct_merged.get("Revenue_Revision_Direction", "UNAVAILABLE")
            _er_rev_pct_c = _ct_merged.get("Revenue_Revision_Pct")
            if _er_eps_dir_c == "UNAVAILABLE" and _er_rev_dir_c == "UNAVAILABLE":
                print("   EARNINGS REVISION: UNAVAILABLE (Yahoo + Finnhub returned None)")
            else:
                _eps_part_c = _er_eps_dir_c
                if _er_eps_pct_c is not None:
                    _eps_part_c = "%s (%+.1f%% / 30d)" % (_er_eps_dir_c, _er_eps_pct_c)
                elif _er_eps_dir_c != "UNAVAILABLE":
                    _eps_part_c = _er_eps_dir_c
                else:
                    _eps_part_c = "N/A"
                _rev_part_c = _er_rev_dir_c
                if _er_rev_pct_c is not None:
                    _rev_part_c = "%s (%+.1f%% / 30d)" % (_er_rev_dir_c, _er_rev_pct_c)
                elif _er_rev_dir_c != "UNAVAILABLE":
                    _rev_part_c = _er_rev_dir_c
                else:
                    _rev_part_c = "N/A"
                print("   EARNINGS REVISION: EPS %s | Revenue %s" % (_eps_part_c, _rev_part_c))

            # VALUATION (Profile B, C only)
            if profile in ("B", "C"):
                _v_fpe_c = _ct_merged.get("Forward_PE")
                _v_peg_c = _ct_merged.get("PEG_Ratio")
                _v_ps_c = _ct_merged.get("PS_Ratio")
                _v_label_c = _ct_merged.get("Valuation_Label", "UNAVAILABLE")
                _v_smed_c = _ct_merged.get("Sector_Median_PE")
                _fpe_str_c = "%.1f" % _v_fpe_c if _v_fpe_c is not None else "N/A"
                _peg_str_c = "%.1f" % _v_peg_c if _v_peg_c is not None else "N/A"
                _ps_str_c = "%.1f" % _v_ps_c if _v_ps_c is not None else "N/A"
                _label_str_c = _v_label_c
                if not _v_label_c.startswith("UNAVAILABLE") and _v_smed_c is not None:
                    _label_str_c = "%s (vs sector median %.1f)" % (_v_label_c, _v_smed_c)
                elif _v_label_c == "UNAVAILABLE" and _v_fpe_c is None:
                    _label_str_c = "UNAVAILABLE (no forward P/E)"
                elif _v_label_c == "UNAVAILABLE" and _v_smed_c is None:
                    _label_str_c = "UNAVAILABLE (sector ETF not in cache)"
                _val_line_c = "Forward P/E %s | PEG %s | P/S %s | %s" % (_fpe_str_c, _peg_str_c, _ps_str_c, _label_str_c)
                if _staleness_warn:
                    _val_line_c += _staleness_warn
                print("   VALUATION:    %s" % _val_line_c)

            # SHORT INTEREST (Profile A, B only)
            if profile in ("A", "B"):
                _si_label = ag_metrics.get("Short_Interest_Label")
                _si_pct = ag_metrics.get("Short_Interest_Pct")
                _si_note = ag_metrics.get("Short_Interest_Note")
                if _si_label and _si_label != "UNAVAILABLE" and _si_pct is not None:
                    _si_line = "%.1f%% of float | %s" % (_si_pct, _si_label)
                    if _si_note:
                        _si_line += " -- %s" % _si_note
                    print("   SHORT INTEREST: %s" % _si_line)
                else:
                    print("   SHORT INTEREST: UNAVAILABLE")

            # MARGIN TRAJECTORY (Profile B, C only)
            if profile in ("B", "C"):
                _gm_trend_c = _ct_merged.get("Gross_Margin_Trend", "UNAVAILABLE")
                _om_trend_c = _ct_merged.get("Operating_Margin_Trend", "UNAVAILABLE")
                _gm_delta_c = _ct_merged.get("Gross_Margin_Delta_pp")
                _om_delta_c = _ct_merged.get("Operating_Margin_Delta_pp")
                if _gm_trend_c == "UNAVAILABLE" and _om_trend_c == "UNAVAILABLE":
                    print("   MARGIN TRAJECTORY: UNAVAILABLE")
                else:
                    _gm_str_c = _gm_trend_c if _gm_trend_c else "UNAVAILABLE"
                    _om_str_c = _om_trend_c if _om_trend_c else "UNAVAILABLE"
                    _gm_delta_str_c = " (%+.1fpp YoY)" % _gm_delta_c if _gm_delta_c is not None else ""
                    _om_delta_str_c = " (%+.1fpp YoY)" % _om_delta_c if _om_delta_c is not None else ""
                    print("   MARGIN TRAJECTORY: Gross %s%s | Operating %s%s" % (_gm_str_c, _gm_delta_str_c, _om_str_c, _om_delta_str_c))

            # SOURCE line (always shown)
            print("   SOURCE:       Yahoo Finance (primary) | %s" % _ct_source_detail)

        # Volume Climax
        if _vision_climax:
            print(f"   VOL CLIMAX:   DETECTED (3-bar execution block per Doc 2 §II)")

        # [Changes 1/2/10] ENGINE STATUS + ENGINE CONTEXT (last)
        _engine_state = metrics.get('Engine_State') or 'N/A'
        _engine_state_upper = str(_engine_state).upper()

        # Floor label resolution (Change 2)
        if profile == "A":
            _floor_label = "VWAP"
        elif profile == "C":
            _floor_label = "Wk SMA 200"
        elif profile == "B":
            if is_etf:
                _floor_label = "SMA 50"
            elif "RESOLVING" in _engine_state_upper:
                _floor_label = "EMA 8"
            else:
                _floor_label = "SMA 50"
        else:
            _floor_label = floor_type

        # ENGINE STATUS (Change 1, renamed per Change 10)
        _exit_sig_d = metrics.get('Exit_Signal') or False
        _exit_triggers_d = metrics.get('Exit_Triggers') or 'None'
        _window_limit = window_limits.get(profile, '0-5')
        _window_max = int(_window_limit.split('-')[1]) if '-' in str(_window_limit) else 5

        if position_status == "EXISTING" and position_monitor:
            if _exit_sig_d in ("WARNING", "EXIT"):
                _determination = f"EXIT ({_exit_sig_d} -- {_exit_triggers_d})"
            elif any(a["severity"] in ("EMERGENCY", "CRITICAL") for a in _advisories):
                _determination = "HOLD (advisory risk active -- no adds recommended)"
            else:
                _determination = "FIT FOR ADD (all clear -- proceeds to sizing)"
        else:
            if status == "PASS":
                try:
                    _wval = int(window_val) if window_val not in ('N/A', None) else 0
                except (ValueError, TypeError):
                    _wval = 0
                if _wval > _window_max:
                    _determination = "STALE (Window expired -- PLANNING ONLY)"
                else:
                    _state_desc = _engine_state if _engine_state != 'N/A' else 'confirmed'
                    _determination = f"SETUP VALID ({_state_desc})"
            elif "MID-RANGE" in _engine_state_upper or "MIDRANGE" in _engine_state_upper:
                _determination = "NO SETUP (MID-RANGE -- no directional regime active)"
            elif "AMBIGUOUS" in _engine_state_upper:
                _determination = f"NO SETUP (AMBIGUOUS -- {_engine_state})"
            else:
                _determination = f"CONDITIONAL ({diag[:60]})"

        print(f"   ENGINE STATUS: {_determination}")

        # ENGINE CONTEXT
        _di_plus = metrics.get('DI_Plus') or 0
        _di_minus = metrics.get('DI_Minus') or 0
        _ctx_state = _engine_state
        if is_etf and profile == "B":
            _ctx_state += " (ETF--BASELINE FLOOR ONLY)"
        _wlimit_num = _window_limit.split('-')[1] if '-' in str(_window_limit) else '?'
        _ctx_line = f"{_ctx_state} | Win {window_val}/{_wlimit_num} | Floor: {_floor_label} | DI: +{_di_plus} vs -{_di_minus}"
        # [Change 1] For EXISTING with exit, append exit info
        if position_status == "EXISTING" and position_monitor and _exit_sig_d in ("WARNING", "EXIT"):
            _ctx_line += f" | Exit: {_exit_sig_d} ({_exit_triggers_d})"
        print(f"   ENGINE CONTEXT: {_ctx_line}")

        # --- Block 4: Bracket Order Preview ---
        print(f"\n   --- BRACKET ORDER PREVIEW ---")
        if step6_passed and entry_price and stop_price:
            print(f"   ENTRY PRICE:  ${entry_price}")
            print(f"   STRUCT FLOOR: ${structural_floor}")
            print(f"   HARD STOP:    ${stop_price} (Floor - 1.5 ATR)")
            print(f"   TARGET:       ${target_price}")
            print(f"   RISK/SHARE:   ${risk_per_share}")
            print(f"   {dynamic_label.ljust(13)}: {dynamic_val}")
            _sizing_label = "ADD SIZING" if position_monitor else "SIZING"
            _sizing_mode_tag = "(PREVIEW)" if mode == "INFO" else ""
            print(f"   {_sizing_label} {_sizing_mode_tag}: {final_units} Units (Capital: ${final_units * entry_price:.2f} | Risk: ${open_risk_heat:.2f})")
            if caution_factors:
                print(f"   CAUTION FACTORS: {'; '.join(caution_factors)}")
        else:
            print(f"   N/A -- Engine did not produce valid entry/stop levels")

        # --- Block 5: Final Determination ---
        # [GOV-002] Single merged FINAL STATUS line
        _non_pass_count = sum(
            1 for v in _verdicts.values()
            if v is not None and v[0] not in _pass_equivalent
        )

        print(f"\n   --- FINAL DETERMINATION ---")
        if _all_verdicts_pass:
            print(f"   FINAL STATUS: PASS")
        else:
            print(f"   FINAL STATUS: NON-PASS ({_urgency} --- {_non_pass_count} non-PASS verdict{'s' if _non_pass_count != 1 else ''})")

        # Bottom banner for CRITICAL+
        if _urgency in ("CRITICAL", "EMERGENCY"):
            print(f"\n{'='*80}\n[{_urgency}] Pipeline completed for full audit. Advisory summary at Step 8.\n{'='*80}")

        print(f"\n{'='*80}\n")

        # ==================================================================
        # STEP 8: EXECUTION GATE (GOV-002: sole Operator decision point)
        # Consolidated advisory summary displayed before authorization.
        # ==================================================================

        # --- GOV-002: Advisory Summary ---
        if _advisories:
            print(f"   --- ADVISORY SUMMARY ({len(_advisories)} {'advisories' if len(_advisories) != 1 else 'advisory'}) ---")
            for _adv in _advisories:
                print(f"   [{_adv['severity']}] {_adv['source']}: {_adv['message']}")

        if caution_factors:
            print(f"   --- CAUTION FACTORS (sizing) ---")
            for _cf in caution_factors:
                print(f"   - {_cf}")

        # Standard size display
        print(f"   Standard size: {final_units} units @ ${entry_price:.2f}")

        if mode == "INFO":
            # INFO mode: display only, no execution option
            _info_prefix = "MONITOR|FIT_FOR_ADD" if position_monitor and _all_verdicts_pass else \
                "MONITOR|NO_ACTION" if position_monitor else \
                    f"{'PASS' if _all_verdicts_pass else 'NON_PASS'}|S6:{'PASS' if step6_passed else 'HALT'}"
            return f"{_info_prefix}| {regime} | Entry: ${entry_price} | Stop: ${stop_price}"

        # LIVE mode: Single severity-aware prompt (GOV-002 advisory model)
        if mode == "LIVE":
            _exec_units_label = f"ADD of {final_units} units to existing {shares}-share position" if position_monitor else f"LIVE execution of {final_units} units"

            if _all_verdicts_pass and not _advisories:
                # Clean prompt: no advisories
                _step8_q = f"AUTHORIZE {_exec_units_label}?"
            elif _urgency == "EMERGENCY":
                # EMERGENCY: harvest advisory active
                _step8_q = f"EMERGENCY advisory active ({regime}). Override and authorize {_exec_units_label}?"
            elif _advisories:
                # ADVISORY / CRITICAL: advisory count in wording
                _step8_q = f"{len(_advisories)} {'advisories' if len(_advisories) != 1 else 'advisory'} active. Override and authorize {_exec_units_label}?"
            else:
                _step8_q = f"AUTHORIZE {_exec_units_label}?"

            if prompt_operator(8, _step8_q):
                print(f"[EXEC] [TRANSMITTING] Routing Bracket Order to IBKR...")
                contract = resolved_contract
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
        description="TBS v8.6.0 Master Orchestrator -- GOV-002 Phase 1 Advisory Model"
    )

    parser.add_argument("--ticker", required=True)
    parser.add_argument("--profile", default="TREND",
                        choices=["SWING", "TREND", "WEALTH", "A", "B", "C"],
                        help="Trade profile (A=SWING, B=TREND, C=WEALTH).")
    parser.add_argument("--mode", default="INFO", choices=["INFO", "LIVE"])
    parser.add_argument("--etf", action="store_true",
                        help="Advisory ETF flag (engine auto-detects; this forces True).")
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
    parser.add_argument("--sector-etf", default=None,
                        help="Manual sector ETF override for Sector Sympathy Audit (e.g. XLE, XLK).")
    parser.add_argument("--entry-price", type=float, default=None,
                        help="Original entry price for position monitoring (enables MONITOR mode).")
    parser.add_argument("--shares", type=int, default=None,
                        help="Number of shares held (required with --entry-price for MONITOR mode).")
    parser.add_argument("--capital", type=float, default=None,
                        help="Total portfolio net worth override for sizing (bypasses IBKR account query).")
    parser.add_argument("--convexity", type=str, default=None,
                        choices=["C1", "C2", "C3"],
                        help="Convexity class override (C1/C2/C3). Overrides classifications.json.")
    parser.add_argument("--position-status", type=str, default="CANDIDATE",
                        choices=["CANDIDATE", "EXISTING"],
                        help="Position status: CANDIDATE (new analysis) or EXISTING (position monitoring).")
    parser.add_argument("--heat-confirmed", type=str, default="true",
                        choices=["true", "false"],
                        help="Operator confirms portfolio heat < 5%%. Pass 'false' if heat exceeds limit.")
    parser.add_argument("--slots-available", type=str, default="true",
                        choices=["true", "false"],
                        help="Operator confirms profile slots are open. Pass 'false' if slots full.")
    parser.add_argument("--overheat", action="store_true",
                        help="Operator declares >= 3 consecutive realised losses. Adds caution factor at Step 8.")
    parser.add_argument("--skip-capacity-gate", action="store_true",
                        help="Skip the Capacity Gate (Step 6). Outputs SKIPPED and pipeline continues. Auto-applied in INFO mode.")

    args = parser.parse_args()

    _pos_status = getattr(args, 'position_status', 'CANDIDATE')
    _ep = getattr(args, 'entry_price', None)
    _sh = args.shares

    # [Amendment v0.2, Change 5] CANDIDATE skips entry/shares entirely.
    # EXISTING requires both --entry-price and --shares.
    if _pos_status == "EXISTING":
        if (_ep is not None) != (_sh is not None):
            parser.error("--entry-price and --shares must be provided together when --position-status is EXISTING.")

    execute_v8_pipeline(
        args.ticker.upper(), args.profile.upper(), args.mode.upper(),
        wacc=args.wacc, moat=args.moat, roic_override=args.roic, pivot_confirmed=args.pivot_confirmed,
        tnx=args.tnx, de_override=args.de,
        fcf_yield_override=getattr(args, 'fcf_yield', None),
        rev_override=args.rev, eps_override=args.eps,
        sector_etf_override=args.sector_etf, is_etf_flag=args.etf,
        entry_price_override=getattr(args, 'entry_price', None),
        shares=args.shares,
        capital_override=args.capital,
        convexity_class=args.convexity,
        position_status=_pos_status,
        heat_confirmed=(getattr(args, 'heat_confirmed', 'true') == 'true'),
        slots_available=(getattr(args, 'slots_available', 'true') == 'true'),
        overheat=args.overheat,
        skip_capacity_gate=args.skip_capacity_gate
    )