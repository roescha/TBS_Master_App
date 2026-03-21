import os
import json
import pandas as pd
from tbs_engine.types import GRACE_BUFFER_ATR_PCT, MetricsResult, GateResult
from tbs_engine.helpers import _clamp, check_climax_history
from tbs_engine.charts import _build_focus_chart

from tbs_engine.transform import _transform_output, _flatten, _audit_key_coverage, _error_output

__all__ = ['_proximity_audit', '_assemble_output', '_populate_base_metrics',
           '_transform_output', '_flatten', '_audit_key_coverage', '_error_output']

# THS-001: Trend Health Score gate threshold (Spec Section III)
THS_GATE_THRESHOLD = 50





# [RFT-001 Phase 6A] _proximity_audit promoted from nested to top-level.
# All former closure variables now passed explicitly via keyword arguments.
def _proximity_audit(_prx_metrics, gate_result, ctx, mode):
    """Write 5 Proximity_* fields to metrics. EPX-001 post-verdict audit.

    DIAG-001 Phase 2B: Signature changed from (_prx_metrics, _prx_status,
    _prx_diag, ctx, mode) to (_prx_metrics, gate_result, ctx, mode).
    Reason extracted from gate_result.reason instead of string parsing.
    """

    # --- RunContext unpacking (RFT-003 F3) ---
    state = ctx.state
    p_code = ctx.p_code
    is_etf = ctx.is_etf
    last = ctx.last
    prev_high = ctx.prev_high
    resistance_raw = ctx.resistance_raw
    ext_limit = ctx.ext_limit
    atr_dist = ctx.atr_dist
    window_count = ctx.window_count
    window_limit = ctx.window_limit
    cons_high_raw = ctx.cons_high_raw
    hard_stop_raw = ctx.hard_stop_raw
    price_scaler = ctx.price_scaler
    prox_anchor = ctx.prox_anchor
    df = ctx.df
    structural_floor_raw = ctx.structural_floor_raw

    # --- Step 1: Eligibility (Section IV.2, Step 1) ---
    # DIAG-001 Phase 2B: Read verdict from GateResult instead of status string
    if gate_result is None or gate_result.verdict == "VALID":
        return
    if mode.upper() == "MONITOR":
        return  # DQ-5: suppress in Position Monitor mode
    if p_code == "C":
        return  # Profile C excluded (Section 1.1)

    # --- Step 2: Identify blocking gate (Section IV.2, Step 2) ---
    # DIAG-001 Phase 2B: Structured field read replaces string parsing
    _reason = gate_result.reason if gate_result else None
    if _reason is None:
        return

    # --- Step 3: Gate classification (Section II) ---
    _PROXIMITY_MAP = {
        "EXTENDED":                   "EXTENSION",
        "MID-RANGE (ADX < 20)":       "ADX_THRESHOLD_20",
        "NOT IN PULLBACK ZONE":       ("VWAP_PULLBACK" if p_code == "A"
                                       else "SMA50_PULLBACK"),
        "NO BREAKOUT":                "BREAKOUT_RESISTANCE",
        "PROFILE A RESOLVING BLOCK":  "ADX_THRESHOLD_25",
        "TREND QUALITY":              "THS_THRESHOLD",     # THS-001
    }

    _blocking_gate = _PROXIMITY_MAP.get(_reason)

    # RECLAIM_2_OF_3: floor failure with exactly 2 reclaim bars
    if _reason == "FLOOR FAILURE" and state._reclaim_run == 2:
        _blocking_gate = "RECLAIM_2_OF_3"

    if _blocking_gate is None:
        return  # structural gate — null defaults are correct

    # --- Step 4: Structural gate filter (Section IV.2, Step 3) ---
    # Forward-looking: would all structural gates pass if this one
    # proximity gate were hypothetically clear?

    # Floor integrity (skip for RECLAIM — that IS the floor scenario)
    if _blocking_gate != "RECLAIM_2_OF_3":
        if state.is_floor_failure or state.is_violated:
            return

    # DI Dominance
    _di_blocked = False
    if state.di_minus > state.di_plus:
        if p_code == "A" and state.ema_stacked:
            pass  # Profile A EMA exemption
        elif p_code == "B" and state._entry_trending and state.ma_stack_full:
            pass  # Profile B TRENDING exemption
        else:
            _di_blocked = True
    if _di_blocked:
        return

    # Gap Trap
    if ((last['open'] > (prev_high + (0.5 * state.atr_raw)))
            and (last['close'] < last['open'])):
        return

    # Window Expired
    if window_count > window_limit:
        return

    # MA Squeeze (structural — distinct from ADX < 20)
    if state.ma_squeeze:
        return

    # Volume Climax (evaluate from available data)
    _climax_df_ck = df.iloc[:-1] if p_code == "A" else df
    if (not pd.isna(_climax_df_ck['vol_sma_9'].iloc[-1])):
        _climax_ck, _ = check_climax_history(_climax_df_ck)
        if _climax_ck:
            return

    # Profile A Expectancy (structural — forward check)
    if p_code == "A" and _blocking_gate != "RECLAIM_2_OF_3":
        _pa_reward = ((cons_high_raw - last['close'])
                      if cons_high_raw is not None else 0)
        _pa_risk   = last['close'] - last['ANCHOR']
        _pa_grace  = GRACE_BUFFER_ATR_PCT * state.atr_raw if state.atr_raw > 0 else 0
        if _pa_risk < -_pa_grace:
            return  # floor violation
        _pa_risk = max(_pa_risk, 0)
        if _pa_risk == 0:
            pass  # floor-exact — PE-CAL-2 handles
        elif _pa_risk < (0.20 * state.atr_raw):
            _pa_hs_risk = last['close'] - hard_stop_raw
            if (_pa_hs_risk > 0 and _pa_reward > 0
                    and _pa_reward / _pa_hs_risk < 1.2):  # PE-CAL-3
                return
        else:
            if _pa_reward < (2.0 * _pa_risk):
                return
        # CEG-001 forward check
        if _pa_risk >= (0.20 * state.atr_raw):
            _pa_cap_r = ((cons_high_raw - last['close'])
                         if cons_high_raw else 0)
            _pa_cap_k = last['close'] - hard_stop_raw
            if (_pa_cap_k > 0 and _pa_cap_r > 0
                    and _pa_cap_r / _pa_cap_k < 1.0):
                return

    # --- Step 4b: State-qualification guard (EPX-001-OBS-2) ---
    if _blocking_gate in ("VWAP_PULLBACK", "SMA50_PULLBACK"):
        if not state._entry_trending:
            return
    elif _blocking_gate == "EXTENSION":
        if not (state._entry_trending or state._entry_resolving):
            return
    elif _blocking_gate == "BREAKOUT_RESISTANCE":
        if not state._entry_resolving:
            return

    # --- Step 5: Count proximity blockers (Section IV.2, Step 4) ---
    _pb_upper_ck = ((last['EMA_21'] + (0.5 * state.atr_raw)) if p_code == "B"
                    else (last['ANCHOR'] + (0.5 * state.atr_raw)))
    _at_pb_ck    = ((last['close'] >= last['ANCHOR'])
                    and (last['close'] <= _pb_upper_ck))
    _cvx_sup     = last['ANCHOR'] if is_etf else last['EMA_8']
    _at_bo_ck    = ((last['close'] > resistance_raw)
                    and (last['close'] > _cvx_sup))

    _blockers = []

    # ADX_THRESHOLD_20
    if state.adx_t < 20:
        _blockers.append("ADX_THRESHOLD_20")

    # ADX_THRESHOLD_25 (Profile A RESOLVING → needs TRENDING)
    if (p_code == "A" and state._entry_resolving and not state._entry_trending
            and not state.ma_squeeze and state.adx_t >= 20 and state.adx_t < 25):
        _blockers.append("ADX_THRESHOLD_25")

    # EXTENSION — account for breakout bar exemption
    _is_bo_bar_ck = ((last['close'] > resistance_raw)
                     if p_code == "B" else False)
    _eff_ext = (1.5 if (_is_bo_bar_ck and not state.is_trending
                        and state._entry_resolving) else ext_limit)
    if atr_dist > _eff_ext:
        _blockers.append("EXTENSION")

    # PULLBACK (TRENDING but above pullback zone, above floor)
    if (state._entry_trending and not _at_pb_ck
            and last['close'] >= last['ANCHOR']):
        _blockers.append(
            "VWAP_PULLBACK" if p_code == "A" else "SMA50_PULLBACK")

    # BREAKOUT_RESISTANCE (RESOLVING, below resistance, non-A)
    if (state._entry_resolving and not state._entry_trending
            and p_code != "A" and not _at_bo_ck):
        _blockers.append("BREAKOUT_RESISTANCE")

    # RECLAIM_2_OF_3
    if state.is_floor_failure and state._reclaim_run == 2:
        _blockers.append("RECLAIM_2_OF_3")

    # THS_THRESHOLD (THS-001: THS gate is sole blocker by definition)
    if _blocking_gate == "THS_THRESHOLD":
        _ths_ck = _prx_metrics.get('Trend_Health_Score', 0)
        if _ths_ck <= THS_GATE_THRESHOLD:
            _blockers.append("THS_THRESHOLD")

    # DQ-2: strict single-gate rule
    if len(_blockers) != 1:
        return
    if _blockers[0] != _blocking_gate:
        return  # sanity — identified blocker must match

    # --- Step 6: Distance computation (Section III + VII DQ-1) ---
    _dist      = None
    _target    = None
    _threshold = None
    _note_ctx  = ""

    if _blocking_gate == "VWAP_PULLBACK":
        _dist      = (last['close'] - _pb_upper_ck) / state.atr_raw
        _target    = round(_pb_upper_ck / price_scaler, 2)
        _threshold = 0.5
        _note_ctx  = (f"{_dist:.2f} ATR above pullback zone "
                      f"({_target}). "
                      f"One hourly pullback creates valid entry.")

    elif _blocking_gate == "SMA50_PULLBACK":
        _dist      = (last['close'] - _pb_upper_ck) / state.atr_raw
        _target    = round(_pb_upper_ck / price_scaler, 2)
        _threshold = 0.5
        _note_ctx  = (f"{_dist:.2f} ATR above pullback zone "
                      f"({_target}). "
                      f"One daily pullback creates valid entry.")

    elif _blocking_gate == "EXTENSION":
        _dist      = atr_dist - _eff_ext
        _target    = round(
            (prox_anchor + (_eff_ext * state.atr_raw)) / price_scaler, 2)
        _threshold = 0.3
        _tf_label  = "hourly" if p_code == "A" else "daily"
        _note_ctx  = (f"{_dist:.2f} ATR past extension limit "
                      f"({_eff_ext}). One {_tf_label} pullback "
                      f"into valid zone.")

    elif _blocking_gate == "BREAKOUT_RESISTANCE":
        _dist      = (resistance_raw - last['close']) / state.atr_raw
        _target    = round(resistance_raw / price_scaler, 2)
        _threshold = 0.3
        _note_ctx  = (f"{_dist:.2f} ATR below resistance ({_target}). "
                      f"One daily close above resistance triggers "
                      f"breakout.")

    elif _blocking_gate == "ADX_THRESHOLD_20":
        _dist      = 20.0 - state.adx_t
        _target    = 20.0
        _threshold = 1.5
        _note_ctx  = (f"{_dist:.2f} ADX points below 20 threshold. "
                      f"ADX acceleration could cross on next bar.")

    elif _blocking_gate == "ADX_THRESHOLD_25":
        _dist      = 25.0 - state.adx_t
        _target    = 25.0
        _threshold = 1.5
        _note_ctx  = (f"{_dist:.2f} ADX points below 25 "
                      f"(TRENDING transition). ADX acceleration "
                      f"could cross on next bar.")

    elif _blocking_gate == "RECLAIM_2_OF_3":
        # DQ-4: Heuristic guard
        if not (state.ma_stack_full and state.adx_t > 20
                and state.di_plus > state.di_minus):
            return
        _dist      = None  # bar-count based
        _target    = round(structural_floor_raw / price_scaler, 2)
        _threshold = None
        _note_ctx  = (f"1 bar remaining. Next close above floor "
                      f"({_target}) completes 3-bar reclaim.")

    elif _blocking_gate == "THS_THRESHOLD":
        # THS-001 Section V.3: Distance = deficit from gate threshold
        _ths_prx = _prx_metrics.get('Trend_Health_Score', 0)
        _dist      = THS_GATE_THRESHOLD - _ths_prx + 1
        _target    = THS_GATE_THRESHOLD + 1  # need THS > 50 (i.e. >= 51)
        _threshold = 10.0  # proximity range: upper CAUTION band
        # Identify dominant weakness (lowest sub-score component)
        _sub_scores = {
            "Floor_Buffer":  _prx_metrics.get('THS_Floor_Buffer', 0),
            "Dir_Momentum":  _prx_metrics.get('THS_Dir_Momentum', 0),
            "Trend_Age":     _prx_metrics.get('THS_Trend_Age', 0),
            "Structure":     _prx_metrics.get('THS_Structure', 0),
        }
        _lowest_component = min(_sub_scores, key=_sub_scores.get)
        _note_ctx  = (f"THS {round(_ths_prx)}/51 "
                      f"({round(_dist)} points below gate). "
                      f"Dominant weakness: {_lowest_component}.")

    else:
        return  # unhandled gate

    # Threshold check (skip for bar-count gates)
    if _dist is not None and _threshold is not None:
        if _dist < 0:
            return  # gate not actually blocking
        if _dist > _threshold:
            return  # beyond proximity range

    # --- Step 7: Write APPROACHING (Section V) ---
    _ths_val = _prx_metrics.get('Trend_Health_Score', 0)

    _prx_metrics["Proximity_Signal"]        = "APPROACHING"
    _prx_metrics["Proximity_Blocking_Gate"]  = _blocking_gate
    _prx_metrics["Proximity_Distance"]       = (round(_dist, 2)
                                                if _dist is not None
                                                else None)
    _prx_metrics["Proximity_Target"]         = _target
    _prx_metrics["Proximity_Note"]           = (
        f"APPROACHING: {_note_ctx} "
        f"All structural gates PASS. "
        f"THS: {round(_ths_val)}."
    )




# Consolidates post-evaluation metric population into a single-pass function.
# [Phase 7 NOTE] PE-7b, Bug #33, and ENG-001 remain in run_tbs_engine at their
# original positions (before gates). Option B (relocate to _assemble_output) was
# attempted but created a behavioral delta: ENG-001 reads Profit_Target before
# gates write to it. Moving ENG-001 post-gates changed RN_Target_Proximity from
# None to "CLEAR" on several paths. The ordering dependency is NOT resolved.
# THS computation and proximity audit are consolidated here.
def _assemble_output(ctx, gate_result, _prx_ctx, debug=False):
    """Layer 5: Assemble final output tuple after all gates and triggers.

    Receives the accumulated evaluation results and produces the final
    grouped dict. Owns THS computation, Focus Chart rendering, ENG-002
    Fibonacci Confluence, and proximity audit.

    DIAG-001 Phase 2A: Signature changed from (ctx, result_status,
    result_diagnostic, ...) to (ctx, gate_result, ...). Temporary bridge
    extracts (result_status, result_diagnostic) for the existing output
    pipeline. Removed in Phase 2B when action_summary replaces
    status + diagnostic.

    Note: Bug #33, PE-7b suppression, and ENG-001 remain in run_tbs_engine
    at their original pre-gate positions. ENG-001 reads Profit_Target before
    gates populate it — relocating to Layer 5 would change observed values.

    [RFT-002 Phase 2] Focus Chart and ENG-002 moved here from
    _identify_trigger() — presentation concerns with no ordering dependency
    on Layer 4 logic.

    Args:
        ctx: RunContext from run_tbs_engine.
        gate_result: GateResult from cascade/trigger chain.
        _prx_ctx: Context dict for _proximity_audit call (contains mode).
        debug: If True, include _debug group in output. Defaults to False.

    Returns:
        dict: Grouped output from _transform_output.
    """

    # --- RunContext unpacking (RFT-003 F3) ---
    metrics = ctx.metrics
    state = ctx.state
    cfg = ctx.cfg
    last = ctx.last
    df = ctx.df
    window_count = ctx.window_count
    _is_c3 = ctx._is_c3
    p_code = ctx.p_code
    is_etf = ctx.is_etf
    price_scaler = ctx.price_scaler
    profile = ctx.profile
    clean_ticker = ctx.clean_ticker
    adx_col = ctx.adx_col
    dmp_col = ctx.dmp_col
    dmn_col = ctx.dmn_col
    chart_dir = ctx.chart_dir
    resistance_raw = ctx.resistance_raw
    bars_per_day = ctx.bars_per_day

    # --- THS COMPUTATION [MODULE G] ---
    # Composite 0-100 metric from four sub-scores. Read-only — does not
    # alter any gate, exit, or verdict.
    # [RFT-001 Phase 6C] Moved from inline in run_tbs_engine to Layer 5.

    # Component 1: Floor Buffer (ATR distance price → structural floor)
    _fb_atr = (last['close'] - state.floor_raw) / state.atr_raw if state.atr_raw > 0 else 0
    _fb_max = cfg.fb_max
    _fb = _clamp(_fb_atr / _fb_max, 0, 1) * 100 if _fb_atr > 0 else 0

    # Component 2: Directional Momentum (ADX strength + DI spread)
    _adx_s = _clamp((state.adx_t - 15) / 30, 0, 1)
    _di_s  = _clamp((state.di_plus - state.di_minus) / 20, 0, 1)
    _dm    = (_adx_s * 0.6 + _di_s * 0.4) * 100

    # Component 3: Trend Age (bars since window reset — window_count IS the age)
    _ta_max  = cfg.ta_max
    _ta_bars = window_count if window_count != 99 else _ta_max
    _ta      = _clamp(1 - (_ta_bars / _ta_max), 0, 1) * 100

    # Component 4: Structure Quality (MA stack integrity + EMA separation)
    _stk = ((15 if last['close'] > last['EMA_8']  else 0)
            + (15 if last['EMA_8']  > last['EMA_21'] else 0)
            + (10 if last['EMA_21'] > last['SMA_50'] else 0)
            + (10 if ('SMA_200' in df.columns and not pd.isna(last['SMA_200'])
                      and last['SMA_50'] > last['SMA_200']) else 0))
    _ema_gap = abs(last['EMA_8'] - last['EMA_21']) / state.atr_raw if state.atr_raw > 0 else 0
    _sq = _stk + _clamp(_ema_gap / 1.0, 0, 1) * 50

    # Weighted composite — convexity-aware
    if _is_c3:
        _ths = _fb * 0.25 + _dm * 0.25 + _ta * 0.20 + _sq * 0.30
    else:
        _ths = _fb * 0.40 + _dm * 0.25 + _ta * 0.15 + _sq * 0.20

    metrics['Trend_Health_Score'] = round(_ths, 1)
    metrics['THS_Label'] = (
        'STRONG' if _ths >= 80 else 'HEALTHY' if _ths >= 60
        else 'ACCEPTABLE' if _ths >= 51
        else 'CAUTION' if _ths >= 40 else 'WEAK' if _ths >= 20 else 'CRITICAL')
    metrics['THS_Floor_Buffer']   = round(_fb, 1)
    metrics['THS_Dir_Momentum']   = round(_dm, 1)
    metrics['THS_Trend_Age']      = round(_ta, 1)
    metrics['THS_Structure']      = round(_sq, 1)
    metrics['Trend_Age_Bars']     = int(_ta_bars)

    # --- THS-001: TREND QUALITY GATE (Spec Section IV.2) ---
    # Post-verdict downgrade: if all gates passed (verdict VALID) but THS
    # is at or below threshold, downgrade to WAIT. THS is dynamic (improves
    # bar-to-bar), so WAIT is correct -- not INVALID.
    # gate_result is never None here (_identify_trigger always returns
    # a GateResult). "All prior gates passed" = verdict == "VALID".
    if gate_result.verdict == "VALID" and _ths <= THS_GATE_THRESHOLD:
        gate_result = GateResult(
            verdict="WAIT",
            reason="TREND QUALITY",
            mandate="WAIT. Trend quality below threshold.",
            context=(
                f"THS {round(_ths)} <= {THS_GATE_THRESHOLD}"
                f" ({metrics['THS_Label']}). "
                f"Sub-scores: FB={round(_fb)}, DM={round(_dm)}, "
                f"TA={round(_ta)}, SQ={round(_sq)}."
            ),
        )

    # ==================================================================
    # [FFD-001] Higher-Frame Context Enrichment — Profile C (monthly)
    # Written on ALL evaluations for Operator auditability (DQ-5).
    # Profile A/B enrichment fields are written in _gate_context_regime.
    # ==================================================================
    if p_code == "C":
        _df_ctx = ctx._df_ctx
        if (_df_ctx is not None and len(_df_ctx) >= 2
                and 'SMA_50' in _df_ctx.columns and 'SMA_200' in _df_ctx.columns
                and not pd.isna(_df_ctx['SMA_50'].iloc[-1])
                and not pd.isna(_df_ctx['SMA_200'].iloc[-1])):
            _ctx_last_c = _df_ctx.iloc[-1]
            _prior_sma50_c = _df_ctx['SMA_50'].iloc[-2]
            if not pd.isna(_prior_sma50_c):
                metrics["Context_Monthly_SMA50_Slope"] = round(float(_ctx_last_c['SMA_50'] - _prior_sma50_c) / price_scaler, 2)
            else:
                metrics["Context_Monthly_SMA50_Slope"] = None
            metrics["Context_Monthly_SMA50"]             = round(float(_ctx_last_c['SMA_50']) / price_scaler, 2)
            metrics["Context_Monthly_Golden_Cross"]      = bool(_ctx_last_c['SMA_50'] > _ctx_last_c['SMA_200'])
            metrics["Context_Monthly_Price_vs_SMA200"]   = round(float(_ctx_last_c['close'] - _ctx_last_c['SMA_200']) / price_scaler, 2)
            metrics["Context_Monthly_SMA200"]            = round(float(_ctx_last_c['SMA_200']) / price_scaler, 2)
        else:
            metrics["Context_Monthly_SMA50_Slope"]       = None
            metrics["Context_Monthly_SMA50"]             = None
            metrics["Context_Monthly_Golden_Cross"]      = None
            metrics["Context_Monthly_Price_vs_SMA200"]   = None
            metrics["Context_Monthly_SMA200"]            = None

    # [FFD-001] Floor_Failure_Context — null guard for non-floor-failure paths.
    # The field is written by _gate_floor_failure or _evaluate_precheck ONLY
    # when the consecutive-bar threshold is reached. Otherwise it stays None.
    if "Floor_Failure_Context" not in metrics:
        metrics["Floor_Failure_Context"] = None

    # [FFD-001-BR-1] Floor_Breach_Dist — null guard for non-floor-failure paths.
    if "Floor_Breach_Dist" not in metrics:
        metrics["Floor_Breach_Dist"] = None

    # ==================================================================
    # [RFT-002 Phase 2] Focus Chart and ENG-002 — moved from
    # _identify_trigger() (Layer 4). Presentation concerns with no
    # ordering dependency on Layer 4 logic.
    # DIAG-001 Phase 2B: Guard uses gate_result.verdict instead of result_status.
    # Focus chart path written to metrics only (not embedded in action_summary.context).
    # ==================================================================
    if gate_result.verdict == "VALID":
        # ======================================================================
        # PHASE 4B: FOCUS CHART -- generated ONLY after a confirmed VALID
        # [MANDATE: DOC 4 SEC VII]
        # A Focus chart failure must NOT block a valid VALID verdict.
        # ======================================================================
        focus_path = os.path.join(chart_dir, f"{clean_ticker}_focus.png")
        try:
            _build_focus_chart(
                df, p_code, profile, clean_ticker, price_scaler,
                adx_col, dmp_col, dmn_col, cfg=cfg  # PE-43: pass cfg for slice alignment
            ).write_image(focus_path)
            metrics["Focus_Chart_Path"] = focus_path
        except Exception as focus_err:
            metrics["Focus_Chart_Path"] = None
            metrics["Focus_Chart_Error"] = str(focus_err)

        # ======================================================================
        # ENG-002: FIBONACCI RETRACEMENT CONFLUENCE DIAGNOSTIC  [Amendment ENG-002]
        # Scope: Profile B (TREND), TRENDING state only. Not computed for
        # Profile A, Profile C, RESOLVING state, or ETFs.
        # NON-GATE: informational only. No verdict or gate impact.
        # [Phase 6 note: ENG-002 metrics writes stay with computation per spec §III.6]
        # Only runs on PASS paths (original behavior: HALT result-collection paths skipped this).
        # ======================================================================
        if p_code == "B" and state._entry_trending and not is_etf:
            _fib_window  = df.iloc[-11:-1]
            _fib_origin  = float(_fib_window['low'].min())
            _fib_peak    = float(_fib_window['high'].max())
            _fib_range   = _fib_peak - _fib_origin

            if _fib_range > 0:
                _fib_382_raw = _fib_peak - 0.382 * _fib_range
                _fib_500_raw = _fib_peak - 0.500 * _fib_range

                # Scale to display currency (pence → pounds for GBP)
                metrics["Fib_382_Level"] = round(_fib_382_raw / price_scaler, 2)
                metrics["Fib_500_Level"] = round(_fib_500_raw / price_scaler, 2)

                _current_price = last['close']
                _tol_382 = 0.003 * _fib_382_raw
                _tol_500 = 0.003 * _fib_500_raw

                if abs(_current_price - _fib_382_raw) <= _tol_382:
                    metrics["Fib_Confluence"] = "CONFLUENCE_382"
                elif abs(_current_price - _fib_500_raw) <= _tol_500:
                    metrics["Fib_Confluence"] = "CONFLUENCE_500"
                elif _fib_500_raw <= _current_price <= _fib_382_raw:
                    metrics["Fib_Confluence"] = "BETWEEN_FIBS"
                elif _current_price > _fib_382_raw:
                    metrics["Fib_Confluence"] = "ABOVE_FIBS"
                else:
                    metrics["Fib_Confluence"] = "BELOW_FIBS"
            else:
                # Degenerate range (Origin == Peak) -- cannot compute Fibonacci levels
                metrics["Fib_382_Level"]  = None
                metrics["Fib_500_Level"]  = None
                metrics["Fib_Confluence"] = None
        else:
            metrics["Fib_382_Level"]  = None
            metrics["Fib_500_Level"]  = None
            metrics["Fib_Confluence"] = None

        # ======================================================================
        # ENG-003: FIBONACCI RETRACEMENT CONFLUENCE DIAGNOSTIC  [Amendment ENG-003]
        # Scope: Profile A (SWING), VWAP floor state only. Not computed for
        # Profile B (ENG-002 covers), Profile C, RESOLVING state, or ETFs.
        # NON-GATE: informational only. No verdict or gate impact.
        # Rally leg: 3-session hourly lookback (bars_per_day * 3).
        # Tolerance: ±0.5% (wider than ENG-002 daily ±0.3% due to hourly noise).
        # ======================================================================
        if p_code == "A" and not is_etf:
            _fib_a_session_bars = int(bars_per_day * 3)
            _fib_a_min_bars = int(bars_per_day * 2)  # at least 2 sessions

            if len(df) > (_fib_a_session_bars + 1) and _fib_a_session_bars >= _fib_a_min_bars:
                _fib_a_window = df.iloc[-(_fib_a_session_bars + 1):-1]
                _fib_a_origin = float(_fib_a_window['low'].min())
                _fib_a_peak = float(_fib_a_window['high'].max())
                _fib_a_range = _fib_a_peak - _fib_a_origin

                if _fib_a_range >= (0.5 * state.atr_raw):
                    _fib_a_382_raw = _fib_a_peak - 0.382 * _fib_a_range
                    _fib_a_500_raw = _fib_a_peak - 0.500 * _fib_a_range

                    metrics["Fib_A_382_Level"] = round(_fib_a_382_raw / price_scaler, 2)
                    metrics["Fib_A_500_Level"] = round(_fib_a_500_raw / price_scaler, 2)

                    _current_price = last['close']
                    _tol_a_382 = 0.005 * _fib_a_382_raw
                    _tol_a_500 = 0.005 * _fib_a_500_raw

                    if abs(_current_price - _fib_a_382_raw) <= _tol_a_382:
                        metrics["Fib_A_Confluence"] = "CONFLUENCE_382"
                    elif abs(_current_price - _fib_a_500_raw) <= _tol_a_500:
                        metrics["Fib_A_Confluence"] = "CONFLUENCE_500"
                    elif _fib_a_500_raw <= _current_price <= _fib_a_382_raw:
                        metrics["Fib_A_Confluence"] = "BETWEEN_FIBS"
                    elif _current_price > _fib_a_382_raw:
                        metrics["Fib_A_Confluence"] = "ABOVE_FIBS"
                    else:
                        metrics["Fib_A_Confluence"] = "BELOW_FIBS"
                else:
                    # Range below 0.5 ATR — levels would be noise
                    metrics["Fib_A_382_Level"] = None
                    metrics["Fib_A_500_Level"] = None
                    metrics["Fib_A_Confluence"] = None
            else:
                # Insufficient bar history for 3-session lookback
                metrics["Fib_A_382_Level"] = None
                metrics["Fib_A_500_Level"] = None
                metrics["Fib_A_Confluence"] = None
        else:
            metrics["Fib_A_382_Level"] = None
            metrics["Fib_A_500_Level"] = None
            metrics["Fib_A_Confluence"] = None

        # ======================================================================
        # ENG-004: MEASURED MOVE PROJECTION  [Amendment ENG-004]
        # Scope: Profile A (SWING) + Profile B (TREND). Not computed for
        # Profile C, ETFs, or INVALID paths.
        # NON-GATE: informational only. No verdict or gate impact.
        # ======================================================================
        if p_code == "B" and state._entry_trending and not is_etf:
            _mm_b_window = df.iloc[-11:-1]
            _mm_b_origin = float(_mm_b_window['low'].min())
            _mm_b_peak   = float(_mm_b_window['high'].max())
            _mm_b_rally  = _mm_b_peak - _mm_b_origin

            if _mm_b_rally < 1.0 * state.atr_raw or _mm_b_rally == 0:
                metrics["MM_Target"]    = None
                metrics["MM_Rally_ATR"] = None
            else:
                metrics["MM_Target"]    = round((last['close'] + _mm_b_rally) / price_scaler, 2)
                metrics["MM_Rally_ATR"] = round(_mm_b_rally / state.atr_raw, 2)

        elif p_code == "A" and not is_etf:
            _mm_a_session_bars = int(bars_per_day * 3)
            _mm_a_min_bars     = int(bars_per_day * 2)

            if len(df) > (_mm_a_session_bars + 1) and _mm_a_session_bars >= _mm_a_min_bars:
                _mm_a_window = df.iloc[-(_mm_a_session_bars + 1):-1]
                _mm_a_origin = float(_mm_a_window['low'].min())
                _mm_a_peak   = float(_mm_a_window['high'].max())
                _mm_a_rally  = _mm_a_peak - _mm_a_origin

                if _mm_a_rally < 1.0 * state.atr_raw or _mm_a_rally == 0:
                    metrics["MM_Target"]    = None
                    metrics["MM_Rally_ATR"] = None
                else:
                    metrics["MM_Target"]    = round((last['close'] + _mm_a_rally) / price_scaler, 2)
                    metrics["MM_Rally_ATR"] = round(_mm_a_rally / state.atr_raw, 2)
            else:
                metrics["MM_Target"]    = None
                metrics["MM_Rally_ATR"] = None
        else:
            metrics["MM_Target"]    = None
            metrics["MM_Rally_ATR"] = None

    # --- PROXIMITY AUDIT ---
    # Called exactly once, after all metrics are populated.
    # DIAG-001 Phase 2B: New signature — reads gate_result.reason directly.
    # CRITICAL ORDERING: Must run BEFORE action_summary construction (DD-6 reads Proximity_Signal).
    _proximity_audit(metrics, gate_result, ctx, _prx_ctx['mode'])

    # --- OTL-001: Hydrate _debug keys from ctx/state ---
    # These values live on RunContext and StateBundle, not in the flat metrics
    # dict. Written here so _transform_output can map them into the _debug group.
    # Skipped when debug=False since the _debug group is omitted from output.
    if debug:
        metrics["actual_price"]        = ctx.actual_price
        metrics["adx_t"]               = state.adx_t
        metrics["adx_t1"]              = state.adx_t1
        metrics["adx_t2"]              = ctx.adx_t2
        metrics["adx_accel"]           = ctx.adx_accel
        metrics["adx_accel_state"]     = ctx.adx_accel_state
        metrics["di_plus"]             = state.di_plus
        metrics["di_minus"]            = state.di_minus
        metrics["atr_raw"]             = state.atr_raw
        metrics["hard_stop_raw"]       = ctx.hard_stop_raw
        metrics["resistance_raw"]      = ctx.resistance_raw
        metrics["structural_floor_raw"]= ctx.structural_floor_raw
        metrics["price_scaler"]        = ctx.price_scaler
        metrics["is_etf"]              = ctx.is_etf
        metrics["_is_lse_etf"]         = ctx._is_lse_etf
        metrics["_ssg_adjusted"]       = ctx._ssg_adjusted
        metrics["_ssg_original_raw"]   = ctx._ssg_original_raw
        metrics["_ssg_reason"]         = ctx._ssg_reason
        metrics["_early_return"]       = False  # reached _assemble_output → no early return
        metrics["ma_squeeze"]          = state.ma_squeeze
        metrics["clean_ticker"]        = ctx.clean_ticker
        metrics["currency"]            = ctx.currency
        metrics["bars_per_day"]        = ctx.bars_per_day
        metrics["window_count"]        = ctx.window_count
        metrics["adx_col"]             = ctx.adx_col
        metrics["dmp_col"]             = ctx.dmp_col
        metrics["dmn_col"]             = ctx.dmn_col
        metrics["vwap_col"]            = ctx.vwap_col

    # --- Entry_Reference: single reference price for the active entry protocol ---
    # BREAKOUT protocol → Resistance (the level price must break through)
    # All other protocols (PULLBACK, TRENDING, RESOLVING) → Structural_Floor
    if metrics.get("Engine_State", "").startswith("BREAKOUT"):
        metrics["Entry_Reference"] = metrics.get("Resistance")
    else:
        metrics["Entry_Reference"] = metrics.get("Structural_Floor")

    # --- VOL-001: Volume-at-Price Context ---
    metrics["Vol_PoC_Price"]        = ctx.vol_poc_price
    metrics["Vol_PoC_Distance_ATR"] = ctx.vol_poc_distance_atr
    metrics["Vol_PoC_Position"]     = ctx.vol_poc_position
    metrics["AVWAP_Price"]          = ctx.avwap_price
    metrics["AVWAP_Position"]       = ctx.avwap_position
    metrics["Volume_Context_Label"] = ctx.volume_context_label
    metrics["Vol_Histogram_Period"] = ctx.metrics.get("Vol_Histogram_Period", "")

    # ==================================================================
    # DIAG-001 Phase 2B: action_summary construction
    # Reads from gate_result fields and metrics already written upstream.
    # This is the LAST step before _transform_output.
    # ==================================================================
    _volume_context = metrics.get("Volume_Context_Label")

    if gate_result.verdict == "VALID":
        # --- DD-2: EXIT forces INVALID ---
        _exit_sig = metrics.get("Exit_Signal")
        if _exit_sig == "EXIT":
            # Override VALID → INVALID
            _exit_reason = metrics.get("Exit_Reason", "Unknown")
            action_summary = {
                "verdict": "INVALID",
                "reason": gate_result.reason,   # preserves original entry type as reason
                "approaching": False,
                "volume_context": _volume_context,  # VOL-001 v1.1: DD-7b
                "action": f"EXIT ACTIVE — entry suppressed. Exit via {_exit_reason} takes priority over entry signal.",
                "context": (f"All gates passed. Trigger met ({gate_result.reason}). "
                            f"Exit_Signal: EXIT ({_exit_reason}). Entry suppressed per DD-2."),
                "existing_position_exit_signal": True,
                "existing_position_exit_reason": _exit_reason,   # already computed in DD-2 block
            }
        else:
            # --- DD-5: exit_warning ---
            _exit_warning = (_exit_sig == "WARNING")
            _exit_warning_note = (
                "Expected on deep pullback — exit system detects price at entry zone level, not a quality concern."
                if _exit_warning else None
            )

            # --- DD-7: quality ---
            _quality = metrics.get("THS_Label")

            # --- DD-8: trigger_condition ---
            _floor = metrics.get("Structural_Floor")
            _resistance = metrics.get("Resistance")
            _pb_upper = metrics.get("Pullback_Zone_Upper")
            if gate_result.entry_type == "PULLBACK":
                _trigger_cond = f"Close within [{_floor} -- {_pb_upper}]"
            elif gate_result.entry_type == "BREAKOUT":
                _trigger_cond = f"Close above {_resistance}"
            elif gate_result.entry_type == "RECLAIM":
                _trigger_cond = f"Close above {_floor}"
            else:
                _trigger_cond = None

            # --- Reward string ---
            _rr_label = metrics.get("Capital_RR_Label")
            _rr_value = metrics.get("Capital_Reward_Risk")
            _reward = f"{_rr_label} [{_rr_value}]" if _rr_label and _rr_value is not None else "N/A"

            # --- DD-3 + DD-7c: entry_strategy (VALID only) ---
            _fib_382 = metrics.get("Fib_A_382_Level") if p_code == "A" else metrics.get("Fib_382_Level")
            _fib_500 = metrics.get("Fib_A_500_Level") if p_code == "A" else metrics.get("Fib_500_Level")
            _fib_conf = metrics.get("Fib_A_Confluence") if p_code == "A" else metrics.get("Fib_Confluence")

            _entry_strategy = {
                "entry_price":     metrics.get("Entry_Reference"),
                "stop_loss":       metrics.get("Hard_Stop"),
                "target":          metrics.get("Profit_Target"),
                "fib_382":         _fib_382,
                "fib_500":         _fib_500,
                "fib_confluence":  _fib_conf,
                "mm_target":       metrics.get("MM_Target"),
            }

            action_summary = {
                "verdict": "VALID",
                "reason": gate_result.reason,        # PULLBACK / BREAKOUT / RECLAIM
                "quality": _quality,                  # DD-7
                "volume_context": _volume_context,    # VOL-001 v1.1: DD-7b
                "reward": _reward,
                "exit_warning": _exit_warning,        # DD-5
                "exit_warning_note": _exit_warning_note,
                "trigger_rule": gate_result.trigger_rule,
                "trigger_condition": _trigger_cond,   # DD-8
                "entry_strategy": _entry_strategy,    # DD-3
                "state": gate_result.state,
                "action": gate_result.mandate,
                "context": gate_result.context,
            }

    elif gate_result.verdict == "INVALID":
        # --- DD-6: approaching ---
        _approaching = (metrics.get("Proximity_Signal") == "APPROACHING")

        # Reuse _exit_sig if already read (DD-2 path above); otherwise read now.
        # Note: _exit_sig is only in scope when gate_result.verdict == "VALID",
        # so we must read it fresh here for the INVALID branch.
        _exit_sig_inv = metrics.get("Exit_Signal")
        action_summary = {
            "verdict": "INVALID",
            "reason": gate_result.reason,
            "approaching": _approaching,     # DD-6
            "volume_context": _volume_context,  # VOL-001 v1.1: DD-7b
            "action": gate_result.mandate,
            "context": gate_result.context,
            "existing_position_exit_signal": (_exit_sig_inv == "EXIT"),
            "existing_position_exit_reason": metrics.get("Exit_Reason") if _exit_sig_inv == "EXIT" else None,
        }

    elif gate_result.verdict == "WAIT":
        # --- THS-001: WAIT path (TREND QUALITY gate) ---
        _approaching = (metrics.get("Proximity_Signal") == "APPROACHING")
        _exit_sig_wait = metrics.get("Exit_Signal")
        action_summary = {
            "verdict": "WAIT",
            "reason": gate_result.reason,
            "approaching": _approaching,
            "volume_context": _volume_context,  # VOL-001 v1.1: DD-7b
            "action": gate_result.mandate,
            "context": gate_result.context,
            "existing_position_exit_signal": (_exit_sig_wait == "EXIT"),
            "existing_position_exit_reason": metrics.get("Exit_Reason") if _exit_sig_wait == "EXIT" else None,
        }

    # ==================================================================
    # PE-42: Data Basis Transparency Note Construction
    # Spec §III.1: data_basis format by profile.
    # Reads component fields already written to metrics by data.py.
    # ==================================================================
    _pe42_bar_range    = metrics.get("Bar_Range")
    _pe42_snapshot_t   = metrics.get("Snapshot_Time")
    _pe42_tz           = metrics.get("_tz_label", "")
    _pe42_price_source = metrics.get("Price_Source", "BAR")

    if p_code == "A":
        # SWING analysis — includes completed bar range + live price info
        _bar_part = f"SWING analysis based on completed bar {_pe42_bar_range} {_pe42_tz}."
        if _pe42_price_source == "LIVE":
            metrics["Data_Basis"] = f"{_bar_part} Live price at {_pe42_snapshot_t} {_pe42_tz}."
        elif _pe42_price_source == "DAILY_CLOSE":
            metrics["Data_Basis"] = f"{_bar_part} Current price from daily close."
        else:  # UNAVAILABLE
            metrics["Data_Basis"] = f"{_bar_part} Live price unavailable (post-close)."
    else:
        # TREND / WEALTH — snapshot time only
        _profile_label = "TREND" if p_code == "B" else "WEALTH"
        metrics["Data_Basis"] = f"{_profile_label} analysis with data up to {_pe42_snapshot_t} {_pe42_tz}."

    # DIAG-001 Phase 2B: Pass action_summary to _transform_output (new signature)
    return _transform_output(action_summary, metrics, debug=debug)





def _populate_base_metrics(ctx, adv_20, _window_reset_event,
                           _ff_threshold, mod_d_state,
                           active_mods, convexity_class):
    """Populate base metrics payload and compute derived display values.

    Writes approximately 60 keys to the metrics dict covering price levels,
    indicator values, state labels, reward/risk computations, and suppression
    guards. Also computes derived variables needed by downstream blocks.

    Mutates:
        ctx.metrics: dict — approximately 60 keys written.
        ctx.state.floor_raw: set to last['ANCHOR'].

    [MANDATE: DOC 3 SEC 498 & DOC 8 SEC 466]

    Returns:
        MetricsResult namedtuple with derived values for downstream use.
    """

    # --- RunContext unpacking (RFT-003 F3) ---
    state = ctx.state
    p_code = ctx.p_code
    is_etf = ctx.is_etf
    _is_c3 = ctx._is_c3
    cfg = ctx.cfg
    df = ctx.df
    last = ctx.last
    actual_price = ctx.actual_price
    price_scaler = ctx.price_scaler
    hard_stop_raw = ctx.hard_stop_raw
    atr_dist = ctx.atr_dist
    ext_limit = ctx.ext_limit
    window_count = ctx.window_count
    window_limit = ctx.window_limit
    _ssg_adjusted = ctx._ssg_adjusted
    _ssg_reason = ctx._ssg_reason
    _ssg_original_raw = ctx._ssg_original_raw
    conviction_state = ctx.conviction_state
    adx_accel = ctx.adx_accel
    adx_accel_state = ctx.adx_accel_state
    vol_confirm_ratio = ctx.vol_confirm_ratio
    vol_confirm_state = ctx.vol_confirm_state
    resistance_raw = ctx.resistance_raw
    metrics = ctx.metrics

    state.floor_raw   = last['ANCHOR']
    floor_price = round(state.floor_raw / price_scaler, 2)
    hard_stop   = round(hard_stop_raw / price_scaler, 2)

    # Profile-specific derived metrics  [MANDATE: DOC 2 SEC 4.3]
    # [PE-26] Profit_Target_Synthetic for Profile B: Floor + 1.5 ATR.
    # A risk-calibrated intermediate profit objective for pullback entries.
    # Suppressed if price is already above it (target is behind current price).
    target_1_b  = round((state.floor_raw + (1.5 * state.atr_raw)) / price_scaler, 2) if p_code == "B" else None
    # [CONVEXITY] C-3 Synthetic target suppression (Redesign Proposal §6.2 / Execution Map §VI)
    # C-3 has open-ended reward. A fixed Floor + 1.5 ATR target would cap the right tail
    # and contradict the C-3 management regime. Suppress immediately.
    if _is_c3 and target_1_b is not None:
        target_1_b = None
        metrics["Profit_Target_Synthetic_Note"] = "SUPPRESSED: C-3 open-ended reward -- no synthetic target"
    elif target_1_b is not None and target_1_b <= actual_price:
        target_1_b = None
        metrics["Profit_Target_Synthetic_Note"] = "SUPPRESSED: price already above Floor + 1.5 ATR -- await pullback to floor"

    # Profile C Floor Proximity: % distance from the Weekly 200-SMA
    if p_code == "C":
        floor_prox_pct = round(
            abs(last['close'] - last['SMA_200']) / last['SMA_200'] * 100, 2
        )
    else:
        floor_prox_pct = None

    # Profile A floor is immutably VWAP -- Convexity Protocol is Profile B only.
    # p_code checks must come before is_resolving to prevent label contamination.
    anchor_label = (
        "VWAP (Baseline Floor)"              if p_code == "A" else
        "EMA 8 (Convexity Protocol)"         if (p_code == "B" and state.is_resolving and not state.is_trending and not is_etf) else
        "50-SMA (Baseline Floor)"            if p_code == "B" else
        "200-SMA (Baseline Floor)"
    )

    # Four distinct labels so the Operator is never misled:
    #   TRENDING   : ADX > 25 + full MA stack
    #   RESOLVING  : ADX > 20 + 3-bar slope
    #   MID-RANGE  : ADX < 20 OR MA squeeze  (true non-directional regime)
    #   AMBIGUOUS  : ADX > 20 but no protocol confirmed (MA stack broken /
    #                slope absent / ETF lock) -- different from MID-RANGE
    # [BUG #38 FIX] ETF Logic Lock forces is_trending/is_resolving to False,
    # causing the state chain to fall through to "AMBIGUOUS (MA STACK BROKEN)"
    # even when the MA stack is fully intact. Add explicit ETF states BEFORE the
    # AMBIGUOUS fallthrough so operators see the correct structural picture.
    engine_state = (
        "VIOLATED -- RECLAIM ACTIVE (STATE AMBIGUOUS)"  if (state.is_reclaim and not (state._entry_trending or state._entry_resolving)) else
        "VIOLATED -- RECLAIM ACTIVE"                    if state.is_reclaim   else
        "VIOLATED -- AWAITING RECLAIM"                  if state.is_violated  else
        "TRENDING"                                      if state.is_trending  else
        "RESOLVING"                                     if state.is_resolving else
        "MID-RANGE (ADX <20)"                           if state.adx_t < 20 else
        "MID-RANGE (MA SQUEEZE)"                          if state.ma_squeeze else
        "TRENDING (ETF -- BASELINE FLOOR ONLY)"         if (is_etf and state.ma_stack_full and state.adx_t > 20 and not state.ma_squeeze) else
        "RESOLVING (ETF -- BASELINE FLOOR ONLY)"        if (is_etf and state.adx_t >= 20) else
        "AMBIGUOUS (DOWNTREND -- ADX MEASURING BEARISH MOMENTUM)"  if state._resolving_is_bearish else
        "AMBIGUOUS (MA STACK BROKEN)"                   if state.adx_t >= 25 else
        "AMBIGUOUS (ADX >20, No Protocol)"
    )

    metrics["Price"]             = round(actual_price, 2)
    metrics["Structural_Floor"]  = floor_price
    # Suppress Hard_Stop when it is above current price -- this occurs when price
    # has broken below the floor and the stop (anchored to floor - 1.5 ATR) is
    # now stale above entry. In this state Exit_Signal is true and the stop is
    # irrelevant; showing it above price is actively misleading to the Operator.
    if hard_stop < actual_price:
        metrics["Hard_Stop"]     = hard_stop
    else:
        metrics["Hard_Stop"]     = None
        metrics["Hard_Stop_Note"] = "SUPPRESSED: stop above current price -- floor already broken, Exit_Signal active"
    # --- SSG-001 METRICS ---
    metrics["Original_Hard_Stop"]   = round(_ssg_original_raw / price_scaler, 2) if _ssg_adjusted else None
    metrics["Stop_Adjusted_Flag"]   = _ssg_adjusted
    metrics["Stop_Adjusted_Reason"] = _ssg_reason
    metrics["ADV_20"]            = float(adv_20)
    metrics["ATR_Dist"]          = round(atr_dist, 2)

    # [FFD-001-BR-1] Floor-relative distance on floor failure paths.
    # ATR_Dist uses the proximity anchor (EMA_21, VWAP, etc.) which can diverge
    # from the structural floor (SMA_50) on breach paths. Floor_Breach_Dist
    # provides the floor-relative measurement for downstream consumers.
    # Negative = below floor (breach). Null on non-floor-failure paths.
    if state.is_floor_failure:
        metrics["Floor_Breach_Dist"] = round((last['close'] - state.floor_raw) / state.atr_raw, 2)

    metrics["Extension_Limit"]   = ext_limit   # [R-9] Profile/state-dependent ATR ceiling
    # Surface evaluation-rule context when live bar has GENUINELY recovered above floor
    # but floor failure is still active on completed bars. Without this note,
    # ATR_Dist > 0 and Exit_Signal = true appear contradictory to the operator.
    # Guard: also require last['close'] > last['ANCHOR'] -- prevents spurious note
    # when ATR_Dist is positive due to an anchor mismatch (e.g. ETF Profile A was
    # previously computing prox_anchor from SMA_200 rather than VWAP, yielding a
    # false positive ATR_Dist even when price was below the VWAP floor).
    _live_bar_above_floor = last['close'] >= last['ANCHOR']
    if round(atr_dist, 2) > 0 and (state.is_violated or state.is_floor_failure) and _live_bar_above_floor:
        metrics["ATR_Dist_Note"] = (
            f"LIVE BAR RECOVERY: current bar above floor ({round(last['close'] / price_scaler, 2)} > "
            f"{round(last['ANCHOR'] / price_scaler, 2)}) but floor "
            f"{'failure' if state.is_floor_failure else 'warning'} based on "
            f"{state.consec_below}/{_ff_threshold} completed consecutive bars below. "
            f"Check Exit_Signal field for position management status."
        )
    # [BUG #39 FIX] ETF Profile B uses SMA_50 as proximity anchor (not EMA_21).
    # ETF Profile C uses SMA_200 (same as structural floor -- not EMA_21).
    # ETF cases must be evaluated BEFORE the generic p_code in ("B","C") branch
    # which previously caused ETF assets to display an incorrect anchor label.
    metrics["ATR_Dist_Anchor"]   = (
        "EMA_8"   if (p_code == "B" and state.is_resolving and not state.is_trending and not is_etf) else
        "SMA_50"  if (is_etf and p_code == "B") else   # ETF Profile B: SMA_50 anchor (immutable)
        "SMA_200" if (is_etf and p_code == "C") else   # ETF Profile C: SMA_200 anchor (same as floor)
        "SMA_200" if p_code == "C" else                 # [PE-CAL-1 §6.4] Profile C realigned to SMA_200
        "EMA_21"  if p_code == "B" else                 # Profile B TRENDING: EMA_21 anchor
        "VWAP"    if p_code == "A" else
        "SMA_200"
    )
    metrics["window_count"]      = int(window_count)
    metrics["Window_Limit"]      = window_limit   # [R-10] Profile-dependent: A=4, B=5, C=4 [PE-CAL-1]
    metrics["Window_Reset_Event"] = _window_reset_event  # [PE-CAL-1] What triggered the window: PULLBACK, BREAKOUT, ADX_CROSS_20
    metrics["Floor_Failure_Threshold"] = _ff_threshold  # [PE-29] Profile-dependent: A=8, B/C=4
    # [CONVEXITY] Write classification tag to metrics (Redesign Proposal §4.2 / Execution Map §VI)
    # When convexity_class is None (unclassified), no tag is written — backward compatible.
    if convexity_class is not None:
        metrics["Convexity_Class"] = convexity_class
    metrics["Anchor_Type"]       = "EMA_8" if (p_code == "B" and state.is_resolving and not state.is_trending and not is_etf) else "Standard"
    metrics["Anchor_Label"]      = anchor_label
    metrics["ADX"]               = round(state.adx_t, 2)
    metrics["DI_Plus"]           = round(state.di_plus, 2)
    metrics["DI_Minus"]          = round(state.di_minus, 2)
    metrics["Engine_State"]      = engine_state
    metrics["Conviction"]        = conviction_state
    metrics["Inst_Churn"]        = mod_d_state
    metrics["ADX_Accel"]         = adx_accel
    metrics["ADX_Accel_State"]   = adx_accel_state
    metrics["Vol_Confirm_Ratio"] = vol_confirm_ratio
    metrics["Vol_Confirm_State"] = vol_confirm_state
    metrics["Active_Modifiers"]  = ", ".join(active_mods) if active_mods else "None"
    resistance_display = round((df['high'].iloc[cfg.resistance_slice_start:cfg.resistance_slice_end].max()) / price_scaler, 2)
    # [BUG #42 FIX] When price is above the 10-bar resistance ceiling, the
    # resistance value is no longer a forward target -- it is a stale level
    # behind current price. Displaying it alongside a SUPPRESSED note creates
    # a direct contradiction in the payload (operator sees both the number and
    # the declaration that the number is suppressed). Null the value and set
    # a flag so the downstream R:R block can suppress RR_Target_Price and
    # Reward_Risk consistently (secondary inconsistency fix).
    _resistance_suppressed = resistance_display < actual_price
    if _resistance_suppressed:
        metrics["Resistance"]      = None
        # [PE-CAL-1] Context-aware messaging: when floor is broken, "await pullback"
        # is contradictory -- you can't pull back to a floor that's above you.
        if state.is_floor_failure or (last['close'] < state.floor_raw):
            metrics["Resistance_Note"] = "SUPPRESSED: price above 10-bar high but below structural floor -- resistance metric not meaningful in broken structure"
        else:
            metrics["Resistance_Note"] = "SUPPRESSED: price already above resistance -- no overhead reward ceiling; await pullback"
    else:
        metrics["Resistance"] = resistance_display
    metrics["EMA_8"]             = round(last['EMA_8']   / price_scaler, 2)
    metrics["EMA_21"]            = round(last['EMA_21']  / price_scaler, 2)
    # [BUG #44 FIX] GBP pence stocks (price_scaler=100) have ATR values in the
    # 1-5 pence range. Dividing by 100 and rounding to 2dp collapses the entire
    # value to 0.01 or 0.02 -- a single digit that loses all precision. The
    # operator then sees ATR=0.01 alongside ATR_Dist=-0.34 and concludes the
    # two figures are inconsistent, even though the underlying atr_raw is used
    # correctly and consistently throughout all internal computations (Hard_Stop,
    # ATR_Dist, grace buffer, extension limit). The fix is to display ATR with
    # 4dp for GBP stocks, producing e.g. 0.0133 instead of 0.01 -- enough
    # precision to verify ATR_Dist by mental arithmetic.
    _atr_display_dp = 4 if price_scaler == 100.0 else 2
    metrics["ATR"]               = round(state.atr_raw         / price_scaler, _atr_display_dp)
    # [PE-23 FIX] Guard SMA_200 against NaN. Profile A requests 3 months of hourly
    # bars (~410 bars), so SMA_200 usually has valid values. But for short-history
    # tickers (recently IPO'd, just above the 30-bar minimum), SMA_200 is entirely
    # NaN. round(NaN / price_scaler, 2) produces NaN, which causes json.dumps() to
    # emit a non-standard NaN literal that breaks strict JSON consumers downstream.
    if 'SMA_200' in df.columns and not pd.isna(last['SMA_200']):
        metrics["SMA_200"]       = round(last['SMA_200'] / price_scaler, 2)
    else:
        metrics["SMA_200"]       = None
    metrics["SMA_50"]            = round(last['SMA_50']  / price_scaler, 2)

    # Target_1 written after Exit Conditions block -- see line below exit_signal assignment.

    # Profile B Reward/Risk  [MANDATE: DOC 2 SEC 4.3 / audit parity with Profile A]
    # Reward = Resistance (10-bar consolidation high) - Price
    # Risk   = Price - Structural Floor (SMA_50)
    # Mirrors Profile A convention: risk measured to structural floor, not Hard_Stop.
    if p_code == "B":
        reward_b = resistance_raw - last['close']
        risk_b   = last['close']  - state.floor_raw
        # [CONVEXITY] C-3 Expectancy Gate bypass (Redesign Proposal §6.2 / Execution Map §VI)
        # C-3 has open-ended reward. Computing R:R against a fixed resistance level
        # treats the breakout as a range-bound trade, which contradicts the C-3 thesis.
        # Profit_Target is written as INFORMATIONAL (see Profit_Target_Role field).
        # Reward_Risk is suppressed — operator uses Risk_Per_Unit instead.
        if _is_c3:
            if _resistance_suppressed or (state.is_floor_failure or (last['close'] < state.floor_raw)):
                metrics["Profit_Target"]        = None
                metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                metrics["Reward_Risk"]           = None
                metrics["Reward_Risk_Note"]      = "BYPASSED: C-3 open-ended reward -- R:R against fixed resistance not meaningful"
            else:
                metrics["Profit_Target"]        = round(resistance_raw / price_scaler, 2)
                metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                metrics["Reward_Risk"]           = None
                metrics["Reward_Risk_Note"]      = (
                    f"BYPASSED: C-3 open-ended reward. Resistance ({round(resistance_raw / price_scaler, 2)}) "
                    f"is INFORMATIONAL only. Use Risk_Per_Unit for risk assessment."
                )
        # [BUG #42 FIX -- secondary] When resistance is suppressed (price above
        elif _resistance_suppressed:
            # [PE-41 §5.2.2] Weekly ceiling escalation for C-1/C-2 TRENDING.
            # When price exceeds the daily 10-bar high, attempt the weekly
            # 10-bar high from df_ctx (which IS weekly for Profile B).
            # Guards: C-1/C-2 only (C-3 handled above), TRENDING state,
            # floor not broken, valid risk denominator.
            _weekly_escalated = False
            if (not _is_c3 and state.is_trending
                    and not state.is_floor_failure
                    and last['close'] >= state.floor_raw
                    and not pd.isna(risk_b) and risk_b > 0):
                _df_ctx_b = ctx._df_ctx
                if _df_ctx_b is not None and len(_df_ctx_b) >= 11:
                    _weekly_ceiling_b = _df_ctx_b['high'].iloc[-11:-1].max()
                elif _df_ctx_b is not None:
                    _weekly_ceiling_b = _df_ctx_b['high'].max()
                else:
                    _weekly_ceiling_b = None
                if _weekly_ceiling_b is not None and _weekly_ceiling_b > last['close']:
                    _reward_b_esc = _weekly_ceiling_b - last['close']
                    metrics["Profit_Target"]        = round(_weekly_ceiling_b / price_scaler, 2)
                    metrics["Profit_Target_Source"]  = "WEEKLY_RESISTANCE (price above daily range)"
                    metrics["Reward_Risk"]           = round(_reward_b_esc / risk_b, 2)
                    _weekly_escalated = True
            if not _weekly_escalated:
                metrics["Profit_Target"]        = None
                metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                metrics["Reward_Risk"]           = None
                # [PE-CAL-1] Context-aware: distinguish "extended above resistance" from
                # "floor broken, resistance metric meaningless"
                if state.is_floor_failure or (last['close'] < state.floor_raw):
                    metrics["Reward_Risk_Note"] = (
                        f"UNDEFINED: structural floor broken (price {round(actual_price, 2)} below floor {floor_price}). "
                        f"10-bar high ({resistance_display}) is not a valid reward target in broken structure."
                    )
                else:
                    metrics["Reward_Risk_Note"] = (
                        f"UNDEFINED: price ({round(actual_price, 2)}) above resistance ceiling ({resistance_display}) -- "
                        f"no reward target available. Await pullback to floor ({floor_price}) before re-evaluating."
                    )
        elif pd.isna(risk_b) or risk_b < 0:
            # [PE-10 FIX] Null Profit_Target alongside Reward_Risk when price is
            # below the structural floor. A target price displayed next to a null R:R
            # with "UNDEFINED" note is a payload contradiction -- the target has no
            # meaning without a valid ratio. Resistance already carries the value for
            # informational purposes; Profit_Target is strictly an R:R output field.
            metrics["Profit_Target"]        = None
            metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
            metrics["Reward_Risk"]           = None
            metrics["Reward_Risk_Note"] = "UNDEFINED: price below structural floor"
        elif risk_b == 0:
            metrics["Profit_Target"]        = round(resistance_raw / price_scaler, 2)
            metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
            metrics["Reward_Risk"]           = 9999.0
            metrics["Reward_Risk_Note"] = "FLOOR_EXACT: price at SMA_50; risk denominator = 0; R:R treated as maximal"
        else:
            metrics["Profit_Target"]        = round(resistance_raw / price_scaler, 2)
            metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
            metrics["Reward_Risk"]           = round(reward_b / risk_b, 2)

    if floor_prox_pct is not None:
        metrics["Floor_Prox_Pct"] = float(floor_prox_pct)     # Profile C only

    # [PE-26] Profile C: no profit targets per Doc 2 §4.3. Explicit null fields
    # ensure the Operator always sees a consistent Profit_Target / Source pair.
    if p_code == "C":
        metrics["Profit_Target"]        = None
        metrics["Profit_Target_Source"]  = "None"

    # [CONVEXITY] Profit_Target_Role (Redesign Proposal §6.2 / Execution Map §VI)
    # Distinguishes prescriptive exits from informational levels.
    #   PRESCRIPTIVE (C-1/C-2): Operator treats profit target as a mechanical exit.
    #   INFORMATIONAL (C-3):    Operator sees the level but does not exit mechanically.
    # When convexity_class is None, field is omitted — backward compatible.
    if convexity_class is not None:
        metrics["Profit_Target_Role"] = "INFORMATIONAL" if _is_c3 else "PRESCRIPTIVE"

    # [CONVEXITY] Risk_Per_Unit (Redesign Proposal §6.2 / Execution Map §VI)
    # For C-3 RESOLVING entries, reward is structurally undefined (open-ended).
    # Risk_Per_Unit = (price − EMA 8) / ATR measures the operator's actual risk
    # exposure without requiring a bounded reward target.
    if _is_c3 and state.is_resolving and not state.is_trending and p_code == "B":
        _ema8_risk = last['close'] - last['EMA_8']
        if not pd.isna(_ema8_risk) and state.atr_raw > 0:
            metrics["Risk_Per_Unit"] = round(_ema8_risk / state.atr_raw, 2)

    if p_code == "A":
        vwap_col = [c for c in df.columns if 'VWAP' in c][0]
        metrics["VWAP"] = round(last[vwap_col] / price_scaler, 2)

    return MetricsResult(
        target_1_b=target_1_b,
        floor_price=floor_price,
        hard_stop=hard_stop,
        floor_prox_pct=floor_prox_pct,
        engine_state=engine_state,
        anchor_label=anchor_label,
        resistance_display=resistance_display,
        resistance_suppressed=_resistance_suppressed,
    )
