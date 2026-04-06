import os
import json
import argparse
import traceback
import pandas as pd
from tbs_engine.types import ProfileConfig, RunContext
from tbs_engine.helpers import _check_round_number_proximity, check_climax_history, _evaluate_floor_failure_context
from tbs_engine.charts import _build_primary_chart, _build_context_chart
from tbs_engine.gates import (
    _gate_context_regime, _gate_liquidity, _gate_data_integrity,
    _gate_floor_failure, _gate_floor_violation, _gate_floor_violation_active,
    _gate_climax, _gate_midrange, _gate_directional, _gate_modifier_e,
    _gate_window, _gate_extension, _gate_floor_proximity_c,
    _gate_expectancy, _gate_capital_expectancy,
)
from tbs_engine.data import _fetch_and_compute, _build_config, _classify_state
from tbs_engine.compute import (
    _compute_morphology, _compute_vol_confirmation, _compute_volume_at_price,
    _compute_window_binding,
    _compute_floor_state, _compute_early_capital_rr, _evaluate_precheck,
)
from tbs_engine.exit import _compute_exit_signals
from tbs_engine.trigger import _identify_trigger
from tbs_engine.output import _assemble_output, _populate_base_metrics, _proximity_audit, _error_output







def run_tbs_engine(ticker, profile="TREND", is_etf=False, mode="INFO",
                   exchange="SMART", currency="USD", convexity_class=None,
                   debug=False):

    # --- [CONVEXITY] Input validation (Redesign Proposal §4.1 / Execution Map §VI) ---
    _VALID_CONVEXITY = {None, "C1", "C2", "C3"}
    if convexity_class not in _VALID_CONVEXITY:
        return _error_output("ERROR", f"INVALID CONVEXITY CLASS: '{convexity_class}'. Valid: None, 'C1', 'C2', 'C3'.", debug=debug)
    _is_c3 = (convexity_class == "C3")

    # --- PROFILE MAPPING ---
    p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    p_code    = p_mapping.get(profile.upper())
    if p_code is None:
        return _error_output("ERROR", (f"INVALID PROFILE: '{profile}' not recognised. "
                         f"Valid: SWING (A), TREND (B), WEALTH (C)."), debug=debug)

    # --- [RFT-001 Phase 4] Build ProfileConfig ---
    cfg = _build_config(p_code)

    # --- [RFT-001 Phase 4] Layer 1: Data Fetch & Indicator Computation ---
    df, raw_metrics = _fetch_and_compute(
        ticker, p_code, cfg, profile, is_etf, mode, exchange, currency, convexity_class
    )

    # Handle early returns from data layer
    if df is None:
        _er = raw_metrics.get("_early_return")
        if _er:
            # DIAG-001 Phase 2B: Map data layer status to verdict
            _verdict = "ERROR" if _er[0] == "ERROR" else "INVALID"
            return _error_output(_verdict, _er[1], _er[2] if len(_er) > 2 else {}, debug=debug)
        return _error_output("ERROR", "Unknown data layer failure", debug=debug)

    # --- Unpack raw_metrics into local variables ---
    is_etf           = raw_metrics["is_etf"]
    _is_lse_etf      = raw_metrics["_is_lse_etf"]
    clean_ticker     = raw_metrics["clean_ticker"]
    currency         = raw_metrics["currency"]
    p_exchange       = raw_metrics.get("p_exchange", "")
    metrics          = raw_metrics["metrics"]
    adx_col          = raw_metrics["adx_col"]
    dmp_col          = raw_metrics["dmp_col"]
    dmn_col          = raw_metrics["dmn_col"]
    adx_accel        = raw_metrics["adx_accel"]
    adx_accel_state  = raw_metrics["adx_accel_state"]
    resistance_raw   = raw_metrics["resistance_raw"]
    price_scaler     = raw_metrics["price_scaler"]
    actual_price     = raw_metrics["actual_price"]
    structural_floor_raw = raw_metrics["structural_floor_raw"]
    hard_stop_raw    = raw_metrics["hard_stop_raw"]
    _ssg_adjusted    = raw_metrics["_ssg_adjusted"]
    _ssg_original_raw = raw_metrics["_ssg_original_raw"]
    _ssg_reason      = raw_metrics["_ssg_reason"]
    bars_per_day     = raw_metrics["bars_per_day"]
    vwap_col         = raw_metrics["vwap_col"]
    df_ctx           = raw_metrics["df_ctx"]

    # --- [RFT-001 Phase 5] Layer 2: State Classification ---
    state = _classify_state(df, p_code, is_etf, cfg, raw_metrics)

    try:
        script_dir   = os.path.dirname(os.path.abspath(__file__))
        # main.py lives in tbs_engine/ — go up two levels to reach project root
        project_root = os.path.dirname(os.path.dirname(script_dir))
        chart_dir    = os.path.join(project_root, "charts")
        if not os.path.exists(chart_dir):
            os.makedirs(chart_dir)

        # [MANDATE: CHART INTEGRITY] Purge all existing charts
        for suffix in ("_primary.png", "_context.png", "_focus.png"):
            try:
                os.remove(os.path.join(chart_dir, f"{clean_ticker}{suffix}"))
            except FileNotFoundError:
                pass

        # Re-derive last bar (same as _fetch_and_compute used)
        last = df.iloc[cfg.iq]

        # STRUCTURAL FLOOR MAPPING  [MANDATE: DOC 2 SEC 4.1]
        # Profile B Convexity override: RESOLVING + not TRENDING + ema_stacked → EMA_8.
        # ETF Profile B/C: baseline MA is immutable (ETF Logic Lock).
        if p_code == "B" and not is_etf:
            _convexity_eligible = state.is_resolving and not state.is_trending and state.ema_stacked
            if _convexity_eligible:
                df['ANCHOR'] = df['EMA_8']
                # Re-derive dependent values after ANCHOR override
                last = df.iloc[cfg.iq]
                structural_floor_raw = last['ANCHOR']
                hard_stop_raw = structural_floor_raw - (1.5 * state.atr_raw)

        # Re-read last row in case ANCHOR changed
        last = df.iloc[cfg.iq]

        # --- [RFT-003 F3] Construct RunContext ---
        # Required fields populated from Layer 1 + Layer 2 outputs.
        # Optional fields set progressively as run_tbs_engine computes them.
        ctx = RunContext(
            state=state, cfg=cfg, p_code=p_code, is_etf=is_etf, _is_c3=_is_c3,
            df=df, last=last, metrics=metrics,
            price_scaler=price_scaler, actual_price=actual_price,
            structural_floor_raw=structural_floor_raw, hard_stop_raw=hard_stop_raw,
            resistance_raw=resistance_raw,
        )
        # Static infrastructure fields (available from Layer 1 unpack)
        ctx.adx_accel = adx_accel
        ctx.adx_accel_state = adx_accel_state
        ctx._ssg_adjusted = _ssg_adjusted
        ctx._ssg_original_raw = _ssg_original_raw
        ctx._ssg_reason = _ssg_reason
        ctx.clean_ticker = clean_ticker
        ctx.adx_col = adx_col
        ctx.dmp_col = dmp_col
        ctx.dmn_col = dmn_col
        ctx.chart_dir = chart_dir
        ctx.profile = profile
        ctx._df_ctx = df_ctx
        ctx.bars_per_day = bars_per_day
        # OTL-001: debug auditability fields
        ctx._is_lse_etf = _is_lse_etf
        ctx.currency = currency
        ctx.vwap_col = vwap_col
        ctx.adx_t2 = raw_metrics.get("adx_t2", 0.0)

        # --- PROXIMITY ANCHOR  [MANDATE: DOC 2 SEC VIII] ---
        # A=VWAP, B=EMA_8(RESOLVING)/EMA_21(TRENDING), C=SMA_200, ETF=baseline MA
        if is_etf:
            if p_code == "A":
                prox_anchor = last[vwap_col]   # ETF Profile A: VWAP anchor (same as non-ETF)
            elif p_code == "B":
                prox_anchor = last['SMA_50']
            else:
                prox_anchor = last['SMA_200']  # Profile C ETF
        elif p_code == "A":
            prox_anchor = last[vwap_col]   # [MANDATE: DOC 2 SEC VIII] VWAP is the Profile A anchor
        elif p_code == "C":
            # [PE-CAL-1 FIX §6.4] Profile C anchor realigned to SMA 200.
            prox_anchor = last['SMA_200']
        else:
            # Profile B: TRENDING -> EMA_21 anchor | RESOLVING (only) -> EMA_8 anchor
            # Guard: if both flags are true, TRENDING wins and EMA_21 is used.
            prox_anchor = last['EMA_8'] if (state.is_resolving and not state.is_trending) else last['EMA_21']

        atr_dist = (last['close'] - prox_anchor) / state.atr_raw

        # EXTENSION LIMIT  [MANDATE: DOC 2 SEC VIII] -- state/profile dependent.
        # [RFT-001 Phase 4] Extension limit from cfg + state-dependent selection
        if is_etf:
            ext_limit = cfg.ext_limit_etf
        elif state.is_trending:
            ext_limit = cfg.ext_limit_trending
        else:
            ext_limit = cfg.ext_limit_resolving

        # --- [RFT-003 F3] Progressive ctx update: proximity/extension ---
        ctx.prox_anchor = prox_anchor
        ctx.atr_dist = atr_dist
        ctx.ext_limit = ext_limit

        # --- ADV  [MANDATE: DOC 2 SEC II] ---
        adv_20 = float((df['vol_sma_20'].iloc[-1] * actual_price) * bars_per_day)
        adv_20_shares = float(df['vol_sma_20'].iloc[-1] * bars_per_day)  # ADV-001: share volume

        # --- [RFT-003 F4a] Morphology computation ---
        mod_d_state, active_mods = _compute_morphology(ctx)

        # --- [RFT-003 F4b] Volume confirmation computation ---
        _compute_vol_confirmation(ctx)

        # --- [VOL-001] Volume-at-Price context computation ---
        _compute_volume_at_price(ctx)

        # --- [RFT-003 F4c] Window binding computation ---
        _window_reset_event = _compute_window_binding(ctx)

        # [PE-29] Floor failure threshold scaled by profile bar frequency.
        _ff_threshold = cfg.ff_threshold
        i0 = cfg.iq  # evaluated bar index (consumed by _compute_exit_signals)

        # --- [RFT-003 F4d] Floor state computation ---
        _compute_floor_state(ctx, _ff_threshold)

        # --- [FFD-001-BR-2] Unconditional Floor_Failure_Context classification ---
        # When is_floor_failure is True, classify the context (CONSOLIDATION or
        # STRUCTURAL_BREAKDOWN) immediately — before the gate cascade. This ensures
        # Floor_Failure_Context is populated even when an earlier gate (e.g. Context
        # Regime) issues a REJECT before _gate_floor_failure executes.
        # The gate cascade and precheck paths may overwrite this value if they
        # reach their own floor classification logic.
        if state.is_floor_failure:
            _, _ffc_label, _ = _evaluate_floor_failure_context(state, df_ctx, p_code)
            metrics["Floor_Failure_Context"] = _ffc_label

        # --- METRICS PAYLOAD — delegated to _populate_base_metrics() ---
        _mr = _populate_base_metrics(
            ctx, adv_20=adv_20, adv_20_shares=adv_20_shares,
            _window_reset_event=_window_reset_event,
            _ff_threshold=_ff_threshold, mod_d_state=mod_d_state,
            active_mods=active_mods, convexity_class=convexity_class,
        )
        target_1_b          = _mr.target_1_b
        floor_price         = _mr.floor_price
        hard_stop           = _mr.hard_stop
        floor_prox_pct      = _mr.floor_prox_pct
        resistance_display  = _mr.resistance_display
        _resistance_suppressed = _mr.resistance_suppressed

        # --- [RFT-003 F3] Progressive ctx update: metrics result ---
        ctx.floor_price = floor_price
        ctx.hard_stop = hard_stop
        ctx.floor_prox_pct = floor_prox_pct if floor_prox_pct is not None else 0.0
        ctx.resistance_display = resistance_display
        ctx._resistance_suppressed = _resistance_suppressed

        # SECTION X: EXIT CONDITION SIGNALS — delegated to _compute_exit_signals()
        exit_signal = _compute_exit_signals(
            state=state, p_code=p_code, df=df, last=last,
            _is_c3=_is_c3, target_1_b=target_1_b,
            i0=i0, price_scaler=price_scaler, metrics=metrics,
            cfg=cfg,  # PE-43: threaded for est_hourly_low slice
            df_ctx=df_ctx, _ff_threshold=_ff_threshold,
        )

        # --- [RFT-003 F3] Progressive ctx update: exit signal ---
        ctx.exit_signal = exit_signal

        # THS key pre-population (ordering preservation — _assemble_output overwrites)
        metrics['Trend_Health_Score'] = None
        metrics['THS_Label']         = None
        metrics['THS_Floor_Buffer']  = None
        metrics['THS_Dir_Momentum']  = None
        metrics['THS_Trend_Age']     = None
        metrics['THS_Structure']     = None
        metrics['Trend_Age_Bars']    = None

        # ENG-001: ROUND NUMBER PROXIMITY DIAGNOSTIC  [Amendment ENG-001]
        # NON-GATE: informational only. Must stay before gates (see RFT-001 Phase 7 note).
        _rn_target = metrics.get("Profit_Target")
        metrics["RN_Target_Proximity"] = (
            _check_round_number_proximity(_rn_target) if _rn_target is not None else None
        )
        _rn_stop = metrics.get("Hard_Stop")
        metrics["RN_Stop_Proximity"] = (
            _check_round_number_proximity(_rn_stop) if _rn_stop is not None else "CLEAR"
        )
        metrics["RN_Floor_Proximity"] = _check_round_number_proximity(
            metrics.get("Structural_Floor")
        )

        # Context data already fetched in _fetch_and_compute(). Unpack resolution/duration.
        ctx_res, ctx_dur = cfg.ctx_resolution, cfg.ctx_duration

        # PHASE 2: CHART RENDERING -- PRIMARY + CONTEXT [MANDATE: DOC 4 SEC II]

        primary_path = os.path.join(chart_dir, f"{clean_ticker}_primary.png")
        _build_primary_chart(
            df, p_code, profile, clean_ticker, adx_col, dmp_col, dmn_col
        ).write_image(primary_path)

        ctx_path = None
        if df_ctx is not None:
            ctx_path = os.path.join(chart_dir, f"{clean_ticker}_context.png")
            _build_context_chart(df_ctx, p_code, profile, clean_ticker).write_image(ctx_path)

        chart_ref = f"Primary: {primary_path}" + (f" | Context: {ctx_path}" if ctx_path else "")

        # --- [RFT-003 F3] Progressive ctx update: chart reference ---
        ctx.chart_ref = chart_ref

        # --- [RFT-003 F4e] Early capital R:R + PE-31 guard ---
        _p1_resistance_note, _p1_reward_risk_note = _compute_early_capital_rr(ctx, exit_signal)
        cons_high_raw = ctx.cons_high_raw

        # ======================================================================
        # EPX-001: ENTRY PROXIMITY SIGNAL — POST-VERDICT AUDIT
        # [Amendment EPX-001 v1.0]
        # [RFT-001 Phase 6A] _proximity_audit promoted to top-level function.
        # Build context dict for all proximity audit calls.
        # ======================================================================
        _prx_ctx = dict(
            state=state, mode=mode, p_code=p_code, is_etf=is_etf, last=last,
            prev_high=ctx.prev_high, resistance_raw=resistance_raw,
            ext_limit=ext_limit, atr_dist=atr_dist,
            window_count=ctx.window_count, window_limit=ctx.window_limit,
            cons_high_raw=cons_high_raw, hard_stop_raw=hard_stop_raw,
            price_scaler=price_scaler, prox_anchor=prox_anchor,
            df=df, structural_floor_raw=structural_floor_raw,
        )

        # --- [RFT-003 F3] Progressive ctx update: proximity context ---
        ctx._prx_ctx = _prx_ctx

        # [RFT-001 Phase 6B] Result-collection pattern: gate cascade
        # DIAG-001 Phase 2A: Refactored from (result_status, result_diagnostic) to GateResult `or` pattern
        gate_result = None  # None = all gates passed so far

        # --- TIER 0: CONTEXT & LIQUIDITY ---
        gate_result = gate_result or _gate_context_regime(p_code, df_ctx, price_scaler, metrics)
        gate_result = gate_result or _gate_liquidity(adv_20, is_etf, _is_lse_etf)

        # _evaluate_precheck: CANNOT use `or` — side-effects on ctx.risk_a/ctx.reward_a
        if gate_result is None:
            _pc = _evaluate_precheck(ctx, _ff_threshold)
            if _pc is not None:
                gate_result = _pc
        risk_a = ctx.risk_a       # read AFTER precheck regardless
        reward_a = ctx.reward_a   # read AFTER precheck regardless

        # PHASE 3: GATE EVALUATION  [MANDATE: DOC 2 SEC II, III, IV, VI, VII]

        # --- TIER 1: DATA QUALITY & FLOOR ---
        gate_result = gate_result or _gate_data_integrity(state.atr_raw)

        floor_dist = (last['close'] - last['ANCHOR']) / state.atr_raw

        gate_result = gate_result or _gate_floor_failure(state.consec_below, state.is_floor_failure, p_code,
                                                          state=state, df_ctx=df_ctx, metrics=metrics,
                                                          _ff_threshold=_ff_threshold)
        gate_result = gate_result or _gate_floor_violation(floor_dist, state.is_violated, p_code,
                                                            consec_below=state.consec_below, _ff_threshold=_ff_threshold)
        gate_result = gate_result or _gate_floor_violation_active(state.is_violated, state.is_reclaim, state.consec_below, floor_price,
                                                                   last['close'], price_scaler, metrics,
                                                                   _ff_threshold=_ff_threshold)
        gate_result = gate_result or _gate_climax(df, p_code, state.is_reclaim, check_climax_history)
        gate_result = gate_result or _gate_midrange(state.adx_t, state.ma_squeeze, atr_dist, ext_limit)

        # --- TIER 2: SIGNAL VALIDITY ---
        gate_result = gate_result or _gate_directional(state.di_plus, state.di_minus, p_code, state.ema_stacked, state._entry_trending,
                                                        state.ma_stack_full, floor_prox_pct, state.adx_t, state.adx_t1)
        gate_result = gate_result or _gate_modifier_e(last['open'], ctx.prev_high, state.atr_raw, last['close'])
        gate_result = gate_result or _gate_window(ctx.window_count, ctx.window_limit)

        # --- TIER 3: SAFETY CONSTRAINTS ---
        gate_result = gate_result or _gate_extension(ctx, atr_dist, ext_limit)
        gate_result = gate_result or _gate_floor_proximity_c(p_code, last, floor_prox_pct)
        gate_result = gate_result or _gate_expectancy(p_code, risk_a, reward_a, cons_high_raw, last['close'],
                                                       floor_price, price_scaler)

        # _gate_capital_expectancy: CANNOT use `or` — writes metrics even on pass
        if gate_result is None:
            _ceg_result = _gate_capital_expectancy(p_code, risk_a, cons_high_raw, last['close'],
                                                    hard_stop_raw, resistance_raw, state.atr_raw,
                                                    price_scaler, metrics, _is_c3=_is_c3, ctx=ctx)
            if _ceg_result is not None:
                gate_result = _ceg_result

        # Recover from metrics (written by _gate_capital_expectancy even on pass)
        _capital_rr = metrics.get("Capital_Reward_Risk")
        _reward_label = metrics.get("Capital_RR_Label")

        # PHASE 4: TRIGGER IDENTIFICATION
        gate_result = _identify_trigger(
            ctx, gate_result=gate_result,
            _capital_rr=_capital_rr, _reward_label=_reward_label,
            _p1_resistance_note=_p1_resistance_note,
            _p1_reward_risk_note=_p1_reward_risk_note,
        )

        # [RFT-001 Phase 6C] Layer 5 Output Assembly — single return point
        return _assemble_output(ctx, gate_result, _prx_ctx, debug=debug)

    except Exception as e:
        import traceback
        return _error_output("ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", debug=debug)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",     required=True)
    parser.add_argument("--profile",    default="TREND")
    parser.add_argument("--mode",       default="INFO")
    parser.add_argument("--etf",        action="store_true")
    parser.add_argument("--convexity",  default=None, choices=["C1", "C2", "C3"],
                        help="Convexity classification (from Classification Prompt). "
                             "Omit for unclassified assets (defaults to C-1 behaviour).")
    parser.add_argument("--debug",      action="store_true",
                        help="Include _debug group with raw internal values in output.")
    args = parser.parse_args()

    result = run_tbs_engine(
        args.ticker, args.profile, args.etf, args.mode,
        convexity_class=args.convexity, debug=args.debug
    )
    print(json.dumps(result, indent=4))
