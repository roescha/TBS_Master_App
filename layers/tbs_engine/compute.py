import pandas as pd
from tbs_engine.types import GRACE_BUFFER_ATR_PCT, GateResult
from tbs_engine.helpers import _assess_floor_state, _deep_reclaim_scan, _evaluate_floor_failure_context

__all__ = ['_compute_morphology', '_compute_vol_confirmation', '_compute_window_binding', '_compute_floor_state', '_compute_early_capital_rr', '_evaluate_precheck']
# ======================================================================
# RFT-003 Phase 4: Inline Block Extractions from run_tbs_engine
# 6 named functions extracted per spec §III.4 (F4).
# Each receives ctx (RunContext) and returns void or a result tuple.
# ======================================================================


def _compute_morphology(ctx):
    """Compute Modifiers A/B/C/D, conviction state, and active_mods list.

    Writes ctx.prev_high, ctx.conviction_state.
    Returns (mod_d_state, active_mods) for downstream _populate_base_metrics.

    RFT-003 Finding F4a | Spec §III.4
    """
    last = ctx.last
    state = ctx.state
    cfg = ctx.cfg
    df = ctx.df
    atr_dist = ctx.atr_dist
    ext_limit = ctx.ext_limit
    _is_c3 = ctx._is_c3

    total_range = last['high'] - last['low']
    real_body   = abs(last['close'] - last['open'])
    # Profile A last = df.iloc[-2], so "previous bar" is one further back.
    prev_high   = df['high'].iloc[-cfg.prev_bar_offset]
    prev_low    = df['low'].iloc[-cfg.prev_bar_offset]

    # [MANDATE: BAR-CLOSE CADENCE] For Profile A, vol_sma_9 must reference the
    # last COMPLETED bar (iloc[-2]). Using iloc[-1] includes the live opening-stub
    # bar -- its partial volume deflates the SMA, making Modifiers B and D
    # marginally easier to trigger than the mandate intends.
    # The climax filter applies the same discipline (passes df.iloc[:-1]).
    _vol_sma9_ref = df['vol_sma_9'].iloc[cfg.iq]

    # Modifier A: Structural Rejection Bar
    mod_a = (
            (total_range > (0.5 * state.atr_raw)) and
            (last['low']   < last['ANCHOR']) and
            (last['close'] > last['ANCHOR']) and
            ((min(last['open'], last['close']) - last['low']) > (0.6 * total_range))
    )

    # Modifier B: Momentum Ignition Bar
    mod_b = (
            (last['close'] > prev_high) and
            (real_body > (0.7 * total_range)) and
            (last['volume'] > _vol_sma9_ref)
    )

    # Modifier C: Compression Bar
    mod_c = (
            (last['high'] < prev_high) and
            (last['low']  > prev_low) and
            (abs(last['close'] - last['ANCHOR']) <= (0.5 * state.atr_raw))
    )

    # Modifier D: Institutional Churn (Early Warning Exit)
    # EXTENDED condition uses the same state-dependent ext_limit as Gate 5
    # [MANDATE: DOC 2 SEC VII / SEC VIII] -- single source of truth for EXTENDED definition.
    mod_d_vol   = last['volume'] > (1.5 * _vol_sma9_ref)
    mod_d_body  = (real_body < (0.25 * total_range)) if total_range > 0 else False
    mod_d_state = (
        "ACTIVE (Inst. Churn)" if (atr_dist > ext_limit) and mod_d_vol and mod_d_body
        else "CLEAR (No Churn)"
    )
    # [CONVEXITY] Modifier D annotation for C-3 (Redesign Proposal §6.2 / Execution Map §VI)
    # C-3 positions have open-ended reward; institutional churn at extended levels is
    # expected volatility, not a structural exit signal. The flag is surfaced for operator
    # awareness but does not mandate action.
    if _is_c3 and mod_d_state.startswith("ACTIVE"):
        mod_d_state = "INFORMATIONAL (Inst. Churn -- C-3: no action mandated)"

    # Conviction state for Convexity sizing multiplier
    conviction_state = (
        "LOW (Range < 1.2 ATR)"  if total_range < (1.2 * state.atr_raw)
        else "HIGH (Range > 1.2 ATR)"
    )

    active_mods = []
    if mod_a: active_mods.append("A (Rejection)")
    if mod_b: active_mods.append("B (Ignition)")
    if mod_c: active_mods.append("C (Compression)")

    # --- Progressive ctx update: morphology ---
    ctx.prev_high = prev_high
    ctx.conviction_state = conviction_state

    return mod_d_state, active_mods


def _compute_vol_confirmation(ctx):
    """Compute Volume Trend Confirmation Ratio over focus window.

    Sets ctx.vol_confirm_ratio and ctx.vol_confirm_state directly.

    RFT-003 Finding F4b | Spec §III.4
    """
    cfg = ctx.cfg
    df = ctx.df

    # ======================================================================
    # VOLUME TREND CONFIRMATION RATIO  [MANDATE: DOC 2 SEC 4.2.2]
    #
    # Measures institutional participation alignment over the 10-bar Focus
    # Window. Counts above-average-volume bars on up-closes vs down-closes.
    #   > 0.7  : STRONG INSTITUTIONAL -- accumulation dominates
    #   0.4-0.7: MIXED               -- no clear institutional commitment
    #   < 0.4  : DISTRIBUTION WARNING -- selling despite rising price
    #
    # Profile A uses iloc[-12:-2] (bar-close cadence); B/C use iloc[-11:-1].
    # Stateless: single pass over existing columns, no persistent state.
    # ======================================================================
    _vw_slice = df.iloc[cfg.resistance_slice_start:cfg.resistance_slice_end]
    _up_vol   = int((((_vw_slice['close'] > _vw_slice['open']) &
                      (_vw_slice['volume'] > _vw_slice['vol_sma_9']))).sum())
    _dn_vol   = int((((_vw_slice['close'] < _vw_slice['open']) &
                      (_vw_slice['volume'] > _vw_slice['vol_sma_9']))).sum())
    _vol_total = _up_vol + _dn_vol
    vol_confirm_ratio = round(_up_vol / max(_vol_total, 1), 2)
    vol_confirm_state = (
        "STRONG INSTITUTIONAL" if vol_confirm_ratio > 0.7 else
        "DISTRIBUTION WARNING" if vol_confirm_ratio < 0.4 else
        "MIXED"
    )

    # --- Progressive ctx update: volume confirmation ---
    ctx.vol_confirm_ratio = vol_confirm_ratio
    ctx.vol_confirm_state = vol_confirm_state


def _compute_window_binding(ctx):
    """Compute Execution Window: breakout/pullback flags, window count.

    Mutates ctx.df by adding Prev_10_High, Prev_10_Low, Is_Breakout,
    Is_Pullback, _Is_ADX_Cross columns.  Sets ctx.window_count and
    ctx.window_limit on context.  Returns _window_reset_event.

    RFT-003 Finding F4c | Spec §III.4
    """
    df = ctx.df
    p_code = ctx.p_code
    cfg = ctx.cfg
    adx_col = ctx.adx_col

    # ======================================================================
    # EXECUTION WINDOW BINDING  [MANDATE: DOC 2 SEC III]
    #
    # Is_Breakout : close strictly above the preceding 10-bar high.
    # Is_Pullback : PURELY POSITIONAL -- Price in [Floor, Floor + 0.5 ATR].
    #   No morphological criteria. Modifier A/C assess bar quality separately.
    # Window count : bars since the most recent structural event (either type).
    # ======================================================================

    df['Prev_10_High'] = df['high'].shift(1).rolling(window=10).max()
    df['Prev_10_Low']  = df['low'].shift(1).rolling(window=10).min()

    df['Is_Breakout'] = df['close'] > df['Prev_10_High']

    # [PE-CAL-1 FIX §6.1] Profile B pullback zone widened: upper bound uses
    # EMA 21 + 0.5 ATR instead of ANCHOR (SMA 50) + 0.5 ATR. In a real trend,
    # EMA 21 is the natural pullback anchor -- the 0.5 ATR zone from SMA 50 is
    # too narrow for a separated MA stack. Profile A/C retain ANCHOR-based zone.
    _pb_upper = (df['EMA_21'] + (0.5 * df['ATRr_14'])) if p_code == "B" else (df['ANCHOR'] + (0.5 * df['ATRr_14']))
    df['Is_Pullback'] = (
            (df['close'] <= _pb_upper) &
            (df['close'] >= df['ANCHOR'])
    )

    if p_code == "A":
        df.loc[df.index[-1], 'Is_Breakout'] = False
        df.loc[df.index[-1], 'Is_Pullback'] = False

    # [PE-CAL-1 FIX §6.3] ADX threshold cross resets window for Profile B.
    # When ADX crosses above 20 (RESOLVING activation), the directional regime
    # is new -- the setup is not stale. Window freshness is measured from
    # regime change, not from the last price event.
    df['_Is_ADX_Cross'] = (df[adx_col] > 20) & (df[adx_col].shift(1) <= 20)

    # Window limits per profile  [MANDATE: DOC 2 SEC III]
    # A=4 hourly bars (VWAP resets daily -- natural staleness protection)
    # B=5 daily bars  (SMA 50 pullbacks develop over 3-7 days)
    # C=4 weekly bars [PE-CAL-1 §6.5: widened from 2 to ~1 month]
    window_limit  = cfg.window_limit
    window_tail   = window_limit + 10  # lookback buffer -- always larger than the limit

    # [PE-CAL-1 §6.3] Include ADX cross as window event for Profile B
    recent_series = (df['Is_Breakout'] | df['Is_Pullback'] | (df['_Is_ADX_Cross'] if p_code == "B" else False))
    recent_events = (recent_series.iloc[:-1].tail(window_tail) if p_code == "A" else recent_series.tail(window_tail)).astype(bool).to_list()
    window_count  = recent_events[::-1].index(True) if any(recent_events) else 99  # 99 = sentinel: no valid window found

    # [PE-CAL-1] Identify what type of event reset the window for operator transparency.
    # Looks at the specific bar that triggered the reset and checks which flag was true.
    _window_reset_event = "NONE"
    if window_count != 99:
        _reset_series = recent_series.iloc[:-1].tail(window_tail) if p_code == "A" else recent_series.tail(window_tail)
        _reset_idx = _reset_series.index[-1 - window_count]  # index of the resetting bar
        _events = []
        if df.loc[_reset_idx, 'Is_Pullback']:
            _events.append("PULLBACK")
        if df.loc[_reset_idx, 'Is_Breakout']:
            _events.append("BREAKOUT")
        if p_code == "B" and df.loc[_reset_idx, '_Is_ADX_Cross']:
            _events.append("ADX_CROSS_20")
        _window_reset_event = " + ".join(_events) if _events else "UNKNOWN"

    # --- Progressive ctx update: window binding ---
    ctx.window_count = window_count
    ctx.window_limit = window_limit

    return _window_reset_event


def _compute_floor_state(ctx, _ff_threshold):
    """Violated state detection and 3-bar reclaim recovery tracking.

    Calls _assess_floor_state and _deep_reclaim_scan (F1).
    Mutates ctx.state directly (consec_below, is_violated, is_reclaim,
    is_floor_failure, _reclaim_run).

    RFT-003 Finding F4d | Spec §III.4
    """
    state = ctx.state
    cfg = ctx.cfg
    df = ctx.df
    i0 = cfg.iq  # evaluated bar index (Profile A uses last completed bar)

    # ======================================================================
    # VIOLATED STATE DETECTION  [MANDATE: DOC 2 SEC 4.1 / SEC VI.3]
    #
    # Doc 2 P026: Floor Violation = 1 to 3 consecutive bar closes BELOW the
    #             Structural Floor.
    # Doc 2 P075: Reclaim Trigger = (1) Previous 1-3 bars below floor;
    #             (2) CURRENT bar closes ABOVE floor.
    #
    # Counting algorithm extracted to _assess_floor_state() helper (RFT-002 Phase 3).
    # ======================================================================

    _atr_val = float(df['ATRr_14'].iloc[i0]) if not pd.isna(df['ATRr_14'].iloc[i0]) else 0
    _floor = _assess_floor_state(df, i0, _atr_val, _ff_threshold)
    state.consec_below     = _floor.consec_below
    state.is_violated      = _floor.is_violated
    state.is_reclaim       = _floor.is_reclaim
    state.is_floor_failure = _floor.is_floor_failure

    # Grace buffer recomputed for recovery tracking block below (same ATR, same formula).
    grace = GRACE_BUFFER_ATR_PCT * _atr_val if _atr_val > 0 else 0
    current_above_floor = _floor.current_above_floor

    # ======================================================================
    # FLOOR FAILURE RECOVERY TRACKING  [3-BAR RECLAIM MANDATE]
    #
    # After a floor failure (threshold+ bars below), structural recovery requires
    # 3 consecutive closes above floor to reset the exit signal. This creates
    # symmetric conviction with the §X exit counter (3 bars to trigger exit,
    # 3 bars to confirm reclaim). Precedent: Floor Trader System requires
    # "price above both SMAs for at least three consecutive bars" to confirm
    # trend reclaim.
    #
    # Problem solved: the simple backward counter "forgets" a floor failure
    # after 2 reclaim bars (the below-floor bars shift out of the lookback
    # window). This deeper scan detects recent failures and re-asserts
    # is_floor_failure until 3 consecutive reclaim bars are confirmed.
    # ======================================================================
    state._reclaim_run = 0  # Tracks consecutive above-floor bars for PE-25 messaging
    if current_above_floor:
        if state.is_floor_failure:
            # Original counter detected floor failure (4+ prior bars below).
            # Current bar is the FIRST reclaim bar.
            state._reclaim_run = 1
        elif not state.is_violated:
            _drs = _deep_reclaim_scan(df, i0, _atr_val, _ff_threshold)
            state._reclaim_run = _drs.reclaim_run

            if _drs.is_recent_failure:
                state.is_floor_failure = True
                state.is_reclaim = False
                state.consec_below = _drs.hist_below
            # _reclaim_run >= 3: floor failure fully resolved, no re-assertion


def _compute_early_capital_rr(ctx, exit_signal):
    """CEG-002 early Capital R:R computation + PE-31 diagnostic guard.

    Computes cons_high_raw (profit target numerator) and early Capital R:R.
    Applies suppression guards. Saves and nulls PE-31 resistance/R:R notes.
    Sets ctx.cons_high_raw.

    Returns (_p1_resistance_note, _p1_reward_risk_note) for downstream
    consumption by _identify_trigger.

    RFT-003 Finding F4e | Spec §III.4
    """
    p_code = ctx.p_code
    last = ctx.last
    metrics = ctx.metrics
    state = ctx.state
    price_scaler = ctx.price_scaler
    resistance_raw = ctx.resistance_raw
    hard_stop_raw = ctx.hard_stop_raw
    df = ctx.df
    cfg = ctx.cfg

    # ==================================================================
    # [CEG-002] EARLY PROFIT TARGET EXTRACTION
    #
    # cons_high_raw is the profit target numerator for Capital R:R.
    # Previously computed inside the Profile A Expectancy pre-check,
    # which is unreachable on pre-gate HALT paths. Extract here so
    # Capital_Reward_Risk can be computed before any gate fires.
    #
    # Profile A: 10-bar daily high from context chart, fallback to weekly-equivalent (PE-41).
    # Profile B: uses resistance_raw (already available), not cons_high_raw.
    # Profile C: no profit targets.
    # ==================================================================
    cons_high_raw = None
    _profit_target_source = None

    # Access df_ctx from raw_metrics stashed on ctx (needed for Profile A profit target)
    df_ctx = ctx._df_ctx

    if p_code == "A":
        if df_ctx is not None and len(df_ctx) >= 11:
            cons_high_raw = df_ctx['high'].iloc[-11:-1].max()
            if cons_high_raw < last['close']:
                # [PE-41] Escalate to weekly-equivalent ceiling (daily 50-bar high)
                # instead of falling back to hourly resistance.  Daily 50-bar window
                # (~10 weeks) is mathematically equivalent to weekly 10-bar high.
                # See PE-41 spec §5.1.
                if len(df_ctx) >= 51:
                    cons_high_raw = df_ctx['high'].iloc[-51:-1].max()
                else:
                    cons_high_raw = df_ctx['high'].max()  # reduced window — defensive
                _profit_target_source = "WEEKLY_RESISTANCE (price above daily range)"
            else:
                _profit_target_source = "DAILY_CTX"
        else:
            cons_high_raw = df['high'].iloc[-12:-2].max()
            _profit_target_source = "FALLBACK_HOURLY (context data unavailable)"
        metrics["Cons_High"] = round(cons_high_raw / price_scaler, 2)
        metrics["Profit_Target_Source"] = _profit_target_source

    # --- Progressive ctx update: profit target ---
    ctx.cons_high_raw = cons_high_raw

    # ==================================================================
    # [CEG-002] EARLY CAPITAL R:R COMPUTATION
    #
    # Surfaces Capital_Reward_Risk and Capital_RR_Label on ALL paths,
    # including pre-gate HALT paths where CEG-001 is unreachable.
    # CEG-001 gate logic is unchanged — it overwrites these values
    # when reached (Profile A gate, Profile B transparency).
    #
    # Suppression guards (per Operator design decisions):
    #   - Exit_Signal = EXIT: suppress (consistent with PE-7)
    #   - Price below floor (floor failure/violation): suppress (misleading)
    #   - Profile C: not applicable (no profit targets)
    #   - No positive reward or risk: null (structurally non-computable)
    # ==================================================================
    _early_capital_target = None
    if p_code == "A" and cons_high_raw is not None:
        _early_capital_target = cons_high_raw
    elif p_code == "B":
        _early_capital_target = resistance_raw
        # [PE-41 §5.2.1] Weekly ceiling escalation for C-1/C-2 when price
        # above daily ceiling.  C-3 bypasses the expectancy gate entirely.
        if (not ctx._is_c3
                and resistance_raw <= last['close']
                and df_ctx is not None):
            _wk_n = len(df_ctx)
            _weekly_ceiling = (df_ctx['high'].iloc[-11:-1].max()
                               if _wk_n >= 11
                               else df_ctx['high'].max())
            if _weekly_ceiling > last['close']:
                _early_capital_target = _weekly_ceiling

    _early_capital_risk = last['close'] - hard_stop_raw

    # Suppression guards
    _suppress_capital_rr = (
            exit_signal == "EXIT"
            or state.is_floor_failure
            or state.is_violated
            or _early_capital_target is None
            or _early_capital_target <= last['close']
            or _early_capital_risk <= 0
    )

    if _suppress_capital_rr:
        metrics["Capital_Reward_Risk"] = None
        metrics["Capital_RR_Label"] = None
    else:
        _early_crr = (_early_capital_target - last['close']) / _early_capital_risk
        metrics["Capital_Reward_Risk"] = round(_early_crr, 2)
        if _early_crr < 1.0:
            metrics["Capital_RR_Label"] = "INSUFFICIENT"
        elif _early_crr < 1.5:
            metrics["Capital_RR_Label"] = "NARROW"
        else:
            metrics["Capital_RR_Label"] = "HEALTHY"

    # ==================================================================
    # [PE-31] PRE-GATE HALT DIAGNOSTIC GUARD
    #
    # Phase 1 writes Resistance_Note and Reward_Risk_Note with generic
    # defaults that assume Phase 4 will contextualise them. On any
    # pre-gate HALT path (CRG-1, CRG-2, Floor Failure, MID-RANGE, etc.),
    # these strings are misleading or factually wrong.
    #
    # Save Phase 1 values to local variables and null them in metrics.
    # Phase 4 restore block will re-populate if the engine reaches it.
    # This covers ALL current and future pre-gate HALT paths automatically.
    # ==================================================================
    _p1_resistance_note  = metrics.get("Resistance_Note")
    _p1_reward_risk_note = metrics.get("Reward_Risk_Note")
    metrics["Resistance_Note"]  = None
    metrics["Reward_Risk_Note"] = None

    return _p1_resistance_note, _p1_reward_risk_note


def _evaluate_precheck(ctx, _ff_threshold):
    """Floor violation pre-check + Profile A expectancy pre-check.

    Returns GateResult if any pre-check fires, None otherwise.
    Also sets ctx.risk_a and ctx.reward_a on the context for downstream gate use.

    Side effects:
        - Writes Exit_Signal, Exit_Triggers, Exit_Reason,
          Floor_Failure_Reclaim to ctx.metrics (on floor failure paths).
        - Writes Reward_Risk, Reward_Risk_Note, Profit_Target to
          ctx.metrics (on Profile A expectancy paths).
        - Mutates ctx.state._reclaim_run (on deep scan paths).

    WARNING: The Profile A expectancy pre-check has deeply nested branching
    (floor-exact → PE-CAL-2 → standard). Copied exactly per spec mandate.
    Do not restructure, simplify, or reformat the nesting.

    RFT-003 Finding F4f | Spec §III.4
    DIAG-001 Phase 2A: Returns refactored from (status, diagnostic) to GateResult.
    """
    state = ctx.state
    cfg = ctx.cfg
    df = ctx.df
    last = ctx.last
    p_code = ctx.p_code
    metrics = ctx.metrics
    price_scaler = ctx.price_scaler
    hard_stop_raw = ctx.hard_stop_raw
    cons_high_raw = ctx.cons_high_raw
    exit_signal = ctx.exit_signal

    gate_result = None

    # --- Initialize variables that are conditionally set by profile ---
    # risk_a and reward_a are computed only for Profile A in the Expectancy
    # Pre-Check below. Default to None so downstream gate calls
    # (_gate_expectancy, _gate_capital_expectancy) can safely receive them
    # for all profiles — the gates check p_code before accessing these.
    risk_a   = None
    reward_a = None

    # --- FLOOR WARNING PRE-CHECK ---
    # Must run BEFORE the Expectancy gate (which computes risk_a = price - VWAP
    # and fires a confusing "floor integrity failure" when price < VWAP).
    # Any broken-floor state is caught here with the correct diagnostic.
    # [R-1 FIX] Pre-check now uses Profile A's i0=-2 offset to evaluate the same
    # bar window as the main check. Previously used df.iloc[-1 - offset] which was
    # shifted by 1 bar for Profile A, causing potential disagreement on floor state.
    if gate_result is None and state.atr_raw > 0:
        _precheck_i0 = cfg.iq  # [R-1] Match main check's i0
        floor_dist_pre = (df['close'].iloc[_precheck_i0] - df['ANCHOR'].iloc[_precheck_i0]) / state.atr_raw
        _pre_floor = _assess_floor_state(df, _precheck_i0, state.atr_raw, _ff_threshold, include_current_bar=False)
        consec_pre               = _pre_floor.consec_below
        _precheck_current_above  = _pre_floor.current_above_floor
        is_floor_failure_pre     = _pre_floor.is_floor_failure
        is_violated_pre          = _pre_floor.is_violated
        is_reclaim_pre           = _pre_floor.is_reclaim
        # Grace buffer recomputed for deep scan block below (same ATR, same formula).
        grace_pre = GRACE_BUFFER_ATR_PCT * state.atr_raw if state.atr_raw > 0 else 0
        if is_floor_failure_pre:
            # --- FFD-001: Composite check for BREACH vs FAILURE ---
            _ffd_breach, _ffd_label, _ffd_conds = _evaluate_floor_failure_context(
                state, ctx._df_ctx, p_code
            )
            metrics["Floor_Failure_Context"] = _ffd_label
            _pre_reclaim = 1 if _precheck_current_above else 0

            if _ffd_breach:
                # FLOOR BREACH → WAIT / WARNING (PE-28 graduation: early deterioration)
                # [PE-38] Preserve-and-merge guard: do not downgrade an existing EXIT.
                _existing_exit = metrics.get("Exit_Signal")
                _existing_triggers = metrics.get("Exit_Triggers", [])
                if isinstance(_existing_triggers, str):
                    _existing_triggers = []
                if _existing_exit == "EXIT":
                    _trigger_label = "Floor_Breach"
                    if _trigger_label not in _existing_triggers:
                        _existing_triggers.append(_trigger_label)
                    metrics["Exit_Triggers"] = _existing_triggers
                else:
                    metrics["Exit_Signal"] = "WARNING"
                    metrics["Exit_Triggers"] = ["Floor_Breach"]
                    metrics["Exit_Reason"] = (
                        f"FLOOR BREACH: {consec_pre}/{_ff_threshold} consecutive bars below floor "
                        f"(threshold reached, higher-frame intact). Monitor for 3-bar reclaim."
                    )
                metrics["Floor_Failure_Reclaim"] = f"{_pre_reclaim}/3"
                _diag = (
                    f"WAIT (reason: FLOOR BREACH). FLOOR BREACH: {consec_pre}/{_ff_threshold} consecutive bars "
                    f"below Floor (threshold reached, higher-frame intact). "
                    f"Monitor for 3-bar reclaim."
                )
                gate_result = GateResult(
                    verdict="INVALID",
                    reason="FLOOR BREACH",
                    mandate="Monitor for 3-bar reclaim.",
                    context=f"FLOOR BREACH: {consec_pre}/{_ff_threshold} consecutive bars below Floor (threshold reached, higher-frame intact).",
                    legacy_diagnostic=_diag,
                )
            else:
                # FLOOR FAILURE → REJECT / EXIT (existing behaviour)
                # [PE-38] Preserve-and-merge guard: do not downgrade an existing EXIT.
                _existing_exit = metrics.get("Exit_Signal")
                _existing_triggers = metrics.get("Exit_Triggers", [])
                if isinstance(_existing_triggers, str):
                    _existing_triggers = []
                _detail = f" Structural break ({_ffd_conds[0]})." if _ffd_conds else " Structural break."
                if _existing_exit == "EXIT":
                    _trigger_label = "Floor_Failure_Override"
                    if _trigger_label not in _existing_triggers:
                        _existing_triggers.append(_trigger_label)
                    metrics["Exit_Triggers"] = _existing_triggers
                else:
                    metrics["Exit_Signal"] = "EXIT"
                    metrics["Exit_Triggers"] = ["Floor_Failure_Override"]
                    metrics["Exit_Reason"] = (
                        f"FLOOR FAILURE OVERRIDE: {consec_pre}/{_ff_threshold} consecutive bars below floor "
                        f"(threshold reached, higher-frame broken).{_detail} "
                        f"Reclaim progress: {_pre_reclaim}/3 bars above floor. "
                        f"3 consecutive closes above floor required to reset structural break."
                    )
                metrics["Floor_Failure_Reclaim"] = f"{_pre_reclaim}/3"
                _diag = (
                    f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE{' RECOVERY' if _pre_reclaim > 0 else ''}: "
                    f"{consec_pre}/{_ff_threshold} consecutive bars below Floor "
                    f"(threshold reached, higher-frame broken).{_detail}"
                    + (f" Reclaim {_pre_reclaim}/3 -- need {3 - _pre_reclaim} more close(s) above floor."
                       if _pre_reclaim > 0 else "")
                )
                gate_result = GateResult(
                    verdict="INVALID",
                    reason="FLOOR FAILURE",
                    mandate="Asset disqualified. Structural breakdown confirmed.",
                    context=f"FLOOR FAILURE{' RECOVERY' if _pre_reclaim > 0 else ''}: {consec_pre}/{_ff_threshold} consecutive bars below Floor (threshold reached, higher-frame broken).{_detail}",
                    legacy_diagnostic=_diag,
                )

        # [3-BAR RECLAIM MANDATE -- PRE-CHECK DEEP SCAN]
        # After 2 reclaim bars, the simple backward counter no longer detects
        # the floor failure (below-floor bars shifted out of lookback window).
        # Scan deeper to find recent failure behind the reclaim streak.
        # Algorithm extracted to _deep_reclaim_scan() helper (RFT-003 F1).
        if gate_result is None and not is_floor_failure_pre and _precheck_current_above and not is_violated_pre:
            _drs_pre = _deep_reclaim_scan(df, _precheck_i0, state.atr_raw, _ff_threshold)
            if _drs_pre.is_recent_failure:
                # --- FFD-001: Composite check for BREACH vs FAILURE ---
                _ffd_breach, _ffd_label, _ffd_conds = _evaluate_floor_failure_context(
                    state, ctx._df_ctx, p_code
                )
                metrics["Floor_Failure_Context"] = _ffd_label

                if _ffd_breach:
                    # FLOOR BREACH → WAIT / WARNING
                    # [PE-38] Preserve-and-merge guard: do not downgrade an existing EXIT.
                    _existing_exit = metrics.get("Exit_Signal")
                    _existing_triggers = metrics.get("Exit_Triggers", [])
                    if isinstance(_existing_triggers, str):
                        _existing_triggers = []
                    if _existing_exit == "EXIT":
                        _trigger_label = "Floor_Breach"
                        if _trigger_label not in _existing_triggers:
                            _existing_triggers.append(_trigger_label)
                        metrics["Exit_Triggers"] = _existing_triggers
                    else:
                        metrics["Exit_Signal"] = "WARNING"
                        metrics["Exit_Triggers"] = ["Floor_Breach"]
                        metrics["Exit_Reason"] = (
                            f"FLOOR BREACH: {_drs_pre.hist_below}/{_ff_threshold} consecutive bars below floor "
                            f"(threshold reached, higher-frame intact). Monitor for 3-bar reclaim."
                        )
                    metrics["Floor_Failure_Reclaim"] = f"{_drs_pre.reclaim_run}/3"
                    state._reclaim_run = _drs_pre.reclaim_run
                    _diag = (
                        f"WAIT (reason: FLOOR BREACH). FLOOR BREACH RECOVERY: {_drs_pre.hist_below}/{_ff_threshold} consecutive bars below Floor "
                        f"(threshold reached, higher-frame intact). "
                        f"Reclaim {_drs_pre.reclaim_run}/3 -- need {3 - _drs_pre.reclaim_run} more close(s) above floor."
                    )
                    gate_result = GateResult(
                        verdict="INVALID",
                        reason="FLOOR BREACH",
                        mandate=f"Monitor for 3-bar reclaim. Need {3 - _drs_pre.reclaim_run} more close(s) above floor.",
                        context=f"FLOOR BREACH RECOVERY: {_drs_pre.hist_below}/{_ff_threshold} consecutive bars below Floor (threshold reached, higher-frame intact). Reclaim {_drs_pre.reclaim_run}/3.",
                        legacy_diagnostic=_diag,
                    )
                else:
                    # FLOOR FAILURE → REJECT / EXIT (existing behaviour)
                    # [PE-38] Preserve-and-merge guard: do not downgrade an existing EXIT.
                    _existing_exit = metrics.get("Exit_Signal")
                    _existing_triggers = metrics.get("Exit_Triggers", [])
                    if isinstance(_existing_triggers, str):
                        _existing_triggers = []
                    _detail = f" Structural break ({_ffd_conds[0]})." if _ffd_conds else ""
                    if _existing_exit == "EXIT":
                        _trigger_label = "Floor_Failure_Override"
                        if _trigger_label not in _existing_triggers:
                            _existing_triggers.append(_trigger_label)
                        metrics["Exit_Triggers"] = _existing_triggers
                    else:
                        metrics["Exit_Signal"] = "EXIT"
                        metrics["Exit_Triggers"] = ["Floor_Failure_Override"]
                        metrics["Exit_Reason"] = (
                            f"FLOOR FAILURE OVERRIDE: {_drs_pre.hist_below}/{_ff_threshold} consecutive bars below floor "
                            f"(threshold reached, higher-frame broken).{_detail} "
                            f"Reclaim progress: {_drs_pre.reclaim_run}/3 bars above floor. "
                            f"3 consecutive closes above floor required to reset structural break."
                        )
                    metrics["Floor_Failure_Reclaim"] = f"{_drs_pre.reclaim_run}/3"
                    state._reclaim_run = _drs_pre.reclaim_run
                    _diag = (
                        f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE RECOVERY: {_drs_pre.hist_below}/{_ff_threshold} consecutive bars below Floor "
                        f"(threshold reached, higher-frame broken).{_detail} "
                        f"Reclaim {_drs_pre.reclaim_run}/3 -- need {3 - _drs_pre.reclaim_run} more close(s) above floor."
                    )
                    gate_result = GateResult(
                        verdict="INVALID",
                        reason="FLOOR FAILURE",
                        mandate="Asset disqualified. Structural breakdown confirmed.",
                        context=f"FLOOR FAILURE RECOVERY: {_drs_pre.hist_below}/{_ff_threshold} consecutive bars below Floor (threshold reached, higher-frame broken).{_detail}",
                        legacy_diagnostic=_diag,
                    )

        if gate_result is None:
            if is_violated_pre and not is_reclaim_pre:
                _diag = (f"WAIT (reason: FLOOR WARNING ACTIVE). FLOOR WARNING ACTIVE: {consec_pre}/{_ff_threshold} consecutive bars below Floor ({round(last['ANCHOR'] / price_scaler, 2)}). "
                                     f"Current bar has NOT reclaimed (Close {round(last['close'] / price_scaler, 2)} < Floor). "
                                     f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above floor.")
                gate_result = GateResult(
                    verdict="INVALID",
                    reason="FLOOR WARNING ACTIVE",
                    mandate="HARD WAIT. Entry only valid on confirmed reclaim close above floor.",
                    context=f"FLOOR WARNING ACTIVE: {consec_pre}/{_ff_threshold} consecutive bars below Floor ({round(last['ANCHOR'] / price_scaler, 2)}). Current bar has NOT reclaimed.",
                    legacy_diagnostic=_diag,
                )
            elif floor_dist_pre < -0.15 and not is_violated_pre:
                _diag = f"WAIT (reason: FLOOR WARNING). FLOOR WARNING: {consec_pre}/{_ff_threshold} consecutive bars below Floor (threshold not reached). Price {abs(floor_dist_pre):.2f} ATR below Floor."
                gate_result = GateResult(
                    verdict="INVALID",
                    reason="FLOOR WARNING",
                    mandate="WAIT. Price below floor, threshold not reached.",
                    context=f"FLOOR WARNING: {consec_pre}/{_ff_threshold} consecutive bars below Floor (threshold not reached). Price {abs(floor_dist_pre):.2f} ATR below Floor.",
                    legacy_diagnostic=_diag,
                )

    # ======================================================================
    # PROFILE A: EXPECTANCY GATE  [MANDATE: DOC 2 SEC 4.3 / P032 / P038]
    # Mandatory 1:2 reward-to-risk gate for ALL Profile A PASS verdicts.
    # Applied here -- BEFORE Phase 4 -- so it covers Pullback, Breakout,
    # AND Reclaim paths equally. No Profile A trade bypasses this gate.
    #
    #   Reward = Consolidation High - Current Price
    #   Risk   = Current Price - Structural Floor
    #   Gate   = Reward >= 2.0 x Risk
    # ======================================================================

    if gate_result is None and p_code == "A":
        # cons_high_raw, Cons_High, and Profit_Target_Source already
        # computed in the CEG-002 early extraction block.
        reward_a       = (cons_high_raw - last['close'])
        risk_a         = (last['close'] - last['ANCHOR'])   # Doc 2 P032: risk = distance to Structural Floor
        # Grace buffer: price within 0.15 ATR below floor is floor-hugging, not a breach.
        # Clamp risk_a to 0 in this zone (treated as floor-exact entry).
        _exp_grace = GRACE_BUFFER_ATR_PCT * state.atr_raw if not pd.isna(state.atr_raw) and state.atr_raw > 0 else 0
        if pd.isna(risk_a):
            _diag = "REJECT (reason: DATA INTEGRITY). Invalid Reward/Risk: risk_a is NaN."
            gate_result = GateResult(
                verdict="INVALID",
                reason="DATA INTEGRITY",
                mandate="Invalid Reward/Risk computation. risk_a is NaN.",
                context="Invalid Reward/Risk: risk_a is NaN.",
                legacy_diagnostic=_diag,
            )
        elif risk_a < -_exp_grace:
            # Price is materially below VWAP floor -- genuine integrity failure.
            _diag = (f"WAIT (reason: FLOOR WARNING ACTIVE). FLOOR WARNING ACTIVE: {state.consec_below}/{_ff_threshold} consecutive bars below Floor. Price {round(last['close'] / price_scaler, 2)} is {abs(risk_a / state.atr_raw):.2f} ATR below floor ({round(last['ANCHOR'] / price_scaler, 2)}). Mandate: HARD WAIT.")
            gate_result = GateResult(
                verdict="INVALID",
                reason="FLOOR WARNING ACTIVE",
                mandate="HARD WAIT. Price materially below floor.",
                context=f"FLOOR WARNING ACTIVE: {state.consec_below}/{_ff_threshold} consecutive bars below Floor. Price {round(last['close'] / price_scaler, 2)} is {abs(risk_a / state.atr_raw):.2f} ATR below floor ({round(last['ANCHOR'] / price_scaler, 2)}).",
                legacy_diagnostic=_diag,
            )
        else:
            if risk_a < 0:
                # Within grace buffer -- treat as floor-exact entry (risk -> 0).
                risk_a = 0
            if risk_a == 0:
                # [PE-CAL-2] Price is exactly AT VWAP floor -- structurally optimal
                # pullback entry, but floor-based R:R is undefined (denominator = 0).
                # Substitute hard stop as risk denominator, same as floor-proximity.
                if reward_a <= 0:
                    _diag = "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: no upside reward from VWAP floor position."
                    gate_result = GateResult(
                        verdict="INVALID",
                        reason="DATA INTEGRITY",
                        mandate="No upside reward from VWAP floor position.",
                        context="Invalid Expectancy: no upside reward from VWAP floor position.",
                        legacy_diagnostic=_diag,
                    )
                else:
                    risk_a_hardstop = last['close'] - hard_stop_raw
                    if risk_a_hardstop <= 0:
                        _diag = "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: hard stop above current price at floor-exact entry."
                        gate_result = GateResult(
                            verdict="INVALID",
                            reason="DATA INTEGRITY",
                            mandate="Hard stop above current price at floor-exact entry.",
                            context="Invalid Expectancy: hard stop above current price at floor-exact entry.",
                            legacy_diagnostic=_diag,
                        )
                    else:
                        rr_hardstop = reward_a / risk_a_hardstop
                        rr_threshold = 1.2  # PE-CAL-3: Profile A C-1 reliability adjustment
                        metrics["Expectancy_Threshold"] = rr_threshold
                        metrics["Expectancy_Threshold_Note"] = "PE-CAL-3: Floor Proximity threshold 1.2 (Profile A C-1 reliability adjustment)"
                        if rr_hardstop < rr_threshold:
                            metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                            metrics["Reward_Risk_Note"] = (
                                f"FLOOR_EXACT: price at VWAP; floor-based R:R undefined. "
                                f"Hard-stop R:R = {round(rr_hardstop, 2)}:1 -- fails PE-CAL-3 minimum ({rr_threshold}:1)."
                            )
                            _diag = (
                                f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY FAILED (FLOOR EXACT): R:R {round(rr_hardstop, 2)}:1 < PE-CAL-3 threshold {rr_threshold} "
                                f"(reward {round(reward_a / price_scaler, 2)} / hard-stop risk {round(risk_a_hardstop / price_scaler, 2)}). "
                                f"Await wider reward ceiling or deeper pullback."
                            )
                            gate_result = GateResult(
                                verdict="INVALID",
                                reason="EXPECTANCY FAILED",
                                mandate="Await wider reward ceiling or deeper pullback.",
                                context=f"EXPECTANCY FAILED (FLOOR EXACT): R:R {round(rr_hardstop, 2)}:1 < PE-CAL-3 threshold {rr_threshold} (reward {round(reward_a / price_scaler, 2)} / hard-stop risk {round(risk_a_hardstop / price_scaler, 2)}).",
                                legacy_diagnostic=_diag,
                            )
                        else:
                            metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                            metrics["Reward_Risk_Note"] = (
                                f"FLOOR_EXACT: price at VWAP; R:R computed against hard stop "
                                f"({round(hard_stop_raw / price_scaler, 2)}). Displayed R:R reflects actual capital at risk."
                            )
                            metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)
            elif risk_a < (0.20 * state.atr_raw):
                # [PE-CAL-2] Risk denominator is near-zero (< 20% of ATR) -- the floor-based
                # R:R is degenerate (small price movements swing R:R by 10+ points).
                # Substitute the hard stop as the risk denominator.
                risk_a_hardstop = last['close'] - hard_stop_raw
                if risk_a_hardstop <= 0:
                    _diag = "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: hard stop above current price in floor-proximity zone."
                    gate_result = GateResult(
                        verdict="INVALID",
                        reason="DATA INTEGRITY",
                        mandate="Hard stop above current price in floor-proximity zone.",
                        context="Invalid Expectancy: hard stop above current price in floor-proximity zone.",
                        legacy_diagnostic=_diag,
                    )
                else:
                    rr_hardstop = reward_a / risk_a_hardstop
                    rr_threshold = 1.2  # PE-CAL-3: Profile A C-1 reliability adjustment
                    metrics["Expectancy_Threshold"] = rr_threshold
                    metrics["Expectancy_Threshold_Note"] = "PE-CAL-3: Floor Proximity threshold 1.2 (Profile A C-1 reliability adjustment)"
                    if rr_hardstop < rr_threshold:
                        metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                        metrics["Reward_Risk_Note"] = (
                            f"FLOOR_PROXIMITY: floor-based risk ({round(risk_a / price_scaler, 3)}) < 20% ATR -- "
                            f"substituted hard stop risk ({round(risk_a_hardstop / price_scaler, 2)}). "
                            f"Hard-stop R:R = {round(rr_hardstop, 2)}:1 -- fails PE-CAL-3 minimum ({rr_threshold}:1)."
                        )
                        _diag = (
                            f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY FAILED (FLOOR PROXIMITY): R:R {round(rr_hardstop, 2)}:1 < PE-CAL-3 threshold {rr_threshold} "
                            f"(reward {round(reward_a / price_scaler, 2)} / hard-stop risk {round(risk_a_hardstop / price_scaler, 2)}). "
                            f"Floor-based R:R is degenerate (risk < 20% ATR). Await wider reward ceiling or deeper pullback."
                        )
                        gate_result = GateResult(
                            verdict="INVALID",
                            reason="EXPECTANCY FAILED",
                            mandate="Await wider reward ceiling or deeper pullback.",
                            context=f"EXPECTANCY FAILED (FLOOR PROXIMITY): R:R {round(rr_hardstop, 2)}:1 < PE-CAL-3 threshold {rr_threshold} (reward {round(reward_a / price_scaler, 2)} / hard-stop risk {round(risk_a_hardstop / price_scaler, 2)}). Floor-based R:R is degenerate (risk < 20% ATR).",
                            legacy_diagnostic=_diag,
                        )
                    else:
                        # Hard-stop R:R passes -- entry is valid with realistic R:R displayed.
                        metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                        metrics["Reward_Risk_Note"] = (
                            f"FLOOR_PROXIMITY: floor-based risk ({round(risk_a / price_scaler, 3)}) < 20% ATR -- "
                            f"R:R computed against hard stop ({round(hard_stop_raw / price_scaler, 2)}). "
                            f"Displayed R:R reflects actual capital at risk, not floor distance."
                        )
                        metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)
            else:
                metrics["Reward_Risk"]      = round(reward_a / risk_a, 2)
                metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)
                metrics["Expectancy_Threshold"] = 2.0
                metrics["Expectancy_Threshold_Note"] = None

    # [PE-7 PROFILE A GUARD] Ensure Profile A's Expectancy Gate doesn't overwrite
    # a scrubbed R:R if an EXIT signal is active (e.g. strict 3-bar VWAP counter).
    # The relocated PE-7 block fires before Pre-Check but also before the Expectancy
    # Gate. If Profile A passes Pre-Check but has EXIT from VWAP, the Expectancy Gate
    # would re-populate R:R -- this guard catches that edge case.
    if p_code == "A" and exit_signal == "EXIT":
        metrics["Reward_Risk"] = None
        metrics["Profit_Target"] = None

    # --- Progressive ctx update: expectancy ---
    ctx.risk_a = risk_a
    ctx.reward_a = reward_a

    return gate_result
