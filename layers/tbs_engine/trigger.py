from tbs_engine.types import GateResult

__all__ = ['_identify_trigger']

# SBO-001 Phase 1: Volume confirmation threshold for breakout validation
SBO_VOLUME_THRESHOLD = 1.5


def _detect_session_first_bar(df, iq):
    """AVWAP-001 DQ-9b: Detect first completed bar of a new session.

    Compares the evaluated bar's date to the previous bar's date.
    If different, this bar is the first completed bar of the new session.
    Returns True if session maturity waiver should apply.
    """
    if df is None:
        return False  # Can't determine without data — don't waive
    if iq < 1 and abs(iq) >= len(df):
        return True  # Not enough bars to compare — waive
    try:
        cur_date = df.index[iq].date() if hasattr(df.index[iq], 'date') else None
        prev_date = df.index[iq - 1].date() if hasattr(df.index[iq - 1], 'date') else None
    except (IndexError, AttributeError):
        return False  # Can't determine — don't waive
    if cur_date is None or prev_date is None:
        return False  # Can't determine — don't waive
    return cur_date != prev_date




# [RFT-001 Phase 7] Layer 4: Trigger Identification
# Extracts the Priority 1-4 trigger chain and PASS-only enrichment (PE-30)
# into a top-level function per spec §III.6.
# [RFT-002 Phase 2] Focus Chart and ENG-002 moved to _assemble_output().
# Receives gate cascade result and determines final (status, diagnostic).
def _identify_trigger(ctx, gate_result,
                      _capital_rr, _reward_label,
                      _p1_resistance_note, _p1_reward_risk_note):
    """Layer 4: Identify trigger type from state and gate cascade result.

    Wraps the Priority 1-4 trigger chain (RECLAIM, TRENDING/PULLBACK,
    RESOLVING/BREAKOUT, AMBIGUOUS) and PASS-only PE-30 enrichment.

    If gate_result is already set by the gate cascade, the trigger chain
    is skipped and the existing result passes through.

    DIAG-001 Phase 2A: Returns refactored from (status, diagnostic) to GateResult.

    Args:
        ctx: RunContext from run_tbs_engine.
        gate_result: Gate cascade result (GateResult or None).
        _capital_rr: Capital Reward/Risk ratio.
        _reward_label: Capital R:R label string.
        _p1_resistance_note: Phase 1 Resistance_Note for PE-31 restore.
        _p1_reward_risk_note: Phase 1 Reward_Risk_Note for PE-31 restore.

    Returns:
        GateResult: verdict="VALID" or "INVALID" with structured fields.
    """

    # --- RunContext unpacking (RFT-003 F3) ---
    state = ctx.state
    cfg = ctx.cfg
    p_code = ctx.p_code
    is_etf = ctx.is_etf
    metrics = ctx.metrics
    last = ctx.last
    df = ctx.df
    resistance_raw = ctx.resistance_raw
    resistance_display = ctx.resistance_display
    floor_price = ctx.floor_price
    hard_stop = ctx.hard_stop
    chart_ref = ctx.chart_ref
    price_scaler = ctx.price_scaler
    _resistance_suppressed = ctx._resistance_suppressed

    # Current-bar position flags (independent of window-reset columns)
    if p_code == "A":
        # AVWAP-001 DQ-2: Daily EMA 21 ± 0.5× daily ATR symmetric entry zone
        _daily_ema21 = ctx.daily_protective_anchor   # PA-001 infrastructure
        _daily_atr = ctx.daily_atr                    # PA-001 infrastructure
        if _daily_ema21 > 0 and _daily_atr > 0:
            _zone_lower = _daily_ema21 - (0.5 * _daily_atr)
            _zone_upper = _daily_ema21 + (0.5 * _daily_atr)
        else:
            # Fallback: use hourly ANCHOR zone if daily data unavailable
            _zone_lower = last['ANCHOR']
            _zone_upper = last['ANCHOR'] + (0.5 * state.atr_raw)
        at_pullback_zone = (
            (last['close'] >= _zone_lower) and
            (last['close'] <= _zone_upper)
        )
        metrics["Pullback_Zone_Lower"] = round(_zone_lower / price_scaler, 2)
        metrics["Pullback_Zone_Upper"] = round(_zone_upper / price_scaler, 2)
        metrics["Entry_Zone_Reference"] = "Daily EMA 21"
        metrics["Entry_Zone_Width_ATR"] = round(_daily_atr * 1.0 / price_scaler, 2) if _daily_atr > 0 else None
        # _pb_upper_cur needed by NOT IN PULLBACK ZONE diagnostic
        _pb_upper_cur = _zone_upper
    else:
        # Profile B/C: existing hourly-based pullback zone (unchanged)
        # [PE-CAL-1 FIX §6.1] Pullback zone upper bound uses cfg.pb_upper_col.
        # Floor (ANCHOR) remains the lower bound. Profile B widens the zone to
        # encompass the natural pullback channel between SMA 50 and EMA 21.
        _pb_upper_cur = last[cfg.pb_upper_col] + (0.5 * state.atr_raw)
        metrics["Pullback_Zone_Upper"] = round(_pb_upper_cur / price_scaler, 2)
        at_pullback_zone = (
            (last['close'] >= last['ANCHOR']) and
            (last['close'] <= _pb_upper_cur)
        )

    # [MANDATE: DOC 2 SEC VI.2] Convex Support: Price > EMA 8 required at breakout.
    # [PE-BUG-1 FIX] ETF Exemption: Convexity Protocol is bypassed (Doc 6 §3.4.1).
    # ETF breakout validates against baseline floor (ANCHOR) instead of EMA 8.
    _convex_support_level = last['ANCHOR'] if is_etf else last['EMA_8']
    at_breakout = (
            (last['close'] > resistance_raw) and
            (last['close'] > _convex_support_level)
    )

    # ==================================================================
    # [PE-31] RESTORE Phase 1 diagnostic strings for Phase 4.
    # ==================================================================
    if gate_result is None:
        if metrics.get("Resistance_Note") is None:
            metrics["Resistance_Note"] = _p1_resistance_note
        if metrics.get("Reward_Risk_Note") is None:
            metrics["Reward_Risk_Note"] = _p1_reward_risk_note

    # ---- PRIORITY 1: RECLAIM PROTOCOL  [Doc 2 Sec VI.3] ----
    if gate_result is None and state.is_reclaim:
        # State quality gate: reclaim is only a valid re-entry signal if the
        # underlying directional state is confirmed (TRENDING or RESOLVING).
        if not (state._entry_trending or state._entry_resolving):
            _diag = (f"WAIT (reason: RECLAIM WITHOUT REGIME). RECLAIM DETECTED but state AMBIGUOUS: ADX {state.adx_t:.1f} -- MA stack incomplete "
                                 f"and no confirmed 3-bar ADX slope. Floor reclaimed ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                                 f"but directional regime not active. Mandate: HARD WAIT. "
                                 f"Monitor for state upgrade (RESOLVING or TRENDING) before re-entry.")
            gate_result = GateResult(
                verdict="INVALID",
                reason="RECLAIM WITHOUT REGIME",
                mandate="HARD WAIT. Monitor for state upgrade (RESOLVING or TRENDING) before re-entry.",
                context=f"RECLAIM DETECTED but state AMBIGUOUS: ADX {state.adx_t:.1f} -- MA stack incomplete. Floor reclaimed ({round(last['close'] / price_scaler, 2)} > {floor_price}) but directional regime not active.",
                legacy_diagnostic=_diag,
            )
        else:
            _reclaim_state = "TRENDING" if state._entry_trending else "RESOLVING"
            _reclaim_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            _diag = (
                f"PRE-APPROVED (entry: RECLAIM | state: {_reclaim_state} | "
                f"reward: {_reclaim_reward} | trigger: BAR CLOSE ONLY). "
                f"Current bar closed above Floor ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                f"after {state.consec_below}/{cfg.ff_threshold} prior consecutive bars below Floor. "
                f"ADX: {state.adx_t:.1f}. "
                f"Entry: execute at THIS bar's close. "
                f"If close missed: next bar must ALSO close above {floor_price} before entry is valid. "
                f"Stop: {hard_stop}. {chart_ref}"
            )
            gate_result = GateResult(
                verdict="VALID",
                reason="RECLAIM",
                mandate=f"Execute at THIS bar's close. If close missed: next bar must ALSO close above {floor_price} before entry is valid. Stop: {hard_stop}.",
                context=f"Bar closed above Floor ({round(last['close'] / price_scaler, 2)} > {floor_price}) after {state.consec_below}/{cfg.ff_threshold} bars below. ADX: {state.adx_t:.1f}.",
                legacy_diagnostic=_diag,
                entry_type="RECLAIM",
                trigger_rule="BAR CLOSE ONLY",
                state=_reclaim_state,
            )

    # ---- PRIORITY 2: TRENDING STATE -- Standard/Pullback Protocol  [Doc 2 Sec VI.1] ----
    if gate_result is None and state._entry_trending:
        if at_pullback_zone:
            _pb_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            _diag = (
                f"PRE-APPROVED (entry: PULLBACK | state: TRENDING | "
                f"reward: {_pb_reward} | trigger: BAR CLOSE ONLY). "
                f"Price {round(last['close'] / price_scaler, 2)} within pullback zone "
                f"[{floor_price} -- {round(_pb_upper_cur / price_scaler, 2)}]. "
                f"ADX: {state.adx_t:.1f}. "
                f"Entry: execute at THIS bar's close. "
                f"If close missed: next bar must ALSO close within pullback zone before entry is valid. "
                f"Stop: {hard_stop}. {chart_ref}"
            )
            gate_result = GateResult(
                verdict="VALID",
                reason="PULLBACK",
                mandate=f"Execute at THIS bar's close. If close missed: next bar must ALSO close within pullback zone before entry is valid. Stop: {hard_stop}.",
                context=f"Price {round(last['close'] / price_scaler, 2)} in pullback zone [{floor_price} -- {round(_pb_upper_cur / price_scaler, 2)}]. ADX: {state.adx_t:.1f}.",
                legacy_diagnostic=_diag,
                entry_type="PULLBACK",
                trigger_rule="BAR CLOSE ONLY",
                state="TRENDING",
            )
        else:
            # ==============================================================
            # [BRK-001] TRENDING + BREAKOUT MODEL ACTIVE
            #
            # When a recent breakout event is within the execution window
            # and the breakout model was activated in compute.py, route to
            # SWING_BREAKOUT instead of rejecting as "NOT IN PULLBACK ZONE".
            #
            # This handles the case where a breakout fired during RESOLVING,
            # the state upgraded to TRENDING (breakout confirmed), and the
            # engine re-evaluates while the execution window is still open.
            # The post-breakout R:R was already computed with correct levels.
            # Spec §4.7.
            # ==============================================================
            if getattr(ctx, '_breakout_model_active', False) is True:
                _sbo_reward = (
                    f"{_reward_label} [{_capital_rr:.2f}]"
                    if _reward_label and _capital_rr is not None
                    else "N/A"
                )
                _brk_stop = round(ctx._brk_tight_stop_raw / price_scaler, 2) if ctx._brk_tight_stop_raw else hard_stop
                _diag = (
                    f"PRE-APPROVED (entry: SWING_BREAKOUT | state: TRENDING | "
                    f"reward: {_sbo_reward} | trigger: BAR CLOSE ONLY). "
                    f"Breakout model active (post-breakout evaluation). "
                    f"Price {round(last['close'] / price_scaler, 2)}, "
                    f"new support {round(resistance_raw / price_scaler, 2)} (old resistance). "
                    f"ADX: {state.adx_t:.1f}. "
                    f"Stop: {_brk_stop}. {chart_ref}"
                )
                gate_result = GateResult(
                    verdict="VALID",
                    reason="SWING_BREAKOUT",
                    mandate=f"Execute at THIS bar's close. Hold above new support {round(resistance_raw / price_scaler, 2)}. Stop: {_brk_stop}.",
                    context=f"Breakout model active. Price {round(last['close'] / price_scaler, 2)}, new support {round(resistance_raw / price_scaler, 2)}. ADX: {state.adx_t:.1f}.",
                    legacy_diagnostic=_diag,
                    entry_type="SWING_BREAKOUT",
                    trigger_rule="BAR CLOSE ONLY",
                    state="TRENDING",
                )
            else:
                _diag = (f"WAIT (reason: NOT IN PULLBACK ZONE). TRENDING (ADX {state.adx_t:.1f}) -- price not in pullback zone. "
                                     f"Mandate: WAIT for Pullback Zone entry at [{floor_price} -- {round(_pb_upper_cur / price_scaler, 2)}].")
                gate_result = GateResult(
                    verdict="INVALID",
                    reason="NOT IN PULLBACK ZONE",
                    mandate=f"WAIT for Pullback Zone entry at [{floor_price} -- {round(_pb_upper_cur / price_scaler, 2)}].",
                    context=f"TRENDING (ADX {state.adx_t:.1f}) -- price not in pullback zone.",
                    legacy_diagnostic=_diag,
                )

    # ---- PRIORITY 3: RESOLVING STATE -- Convexity/Breakout Protocol  [Doc 2 Sec VI.2] ----
    # SBO-001: Pre-state candidates (ADX 17-20, ctx._sbo_prestate=True) also
    # enter this block even though _entry_resolving is False.
    if gate_result is None and (state._entry_resolving or getattr(ctx, '_sbo_prestate', False) is True):
        # [GENUINE PROFILE LOGIC] Profile A Convexity Protocol block.
        # Profile A requires TRENDING state; RESOLVING is not sufficient.
        # This is a genuine behavioural difference, not a parameter selection.
        if p_code == "A":
            # SBO-001: Check breakout conditions before blocking
            _sbo_convex = last['ANCHOR'] if is_etf else last['EMA_8']

            _sbo_breakout = (
                last['close'] > resistance_raw and
                last['close'] > _sbo_convex
            )

            # Volume + DI checks only evaluated when price breakout is confirmed
            # (short-circuit avoids touching vol_sma_20/di_plus on non-breakout bars)
            if _sbo_breakout:
                _sbo_vol_sma = last.get('vol_sma_20', 0)
                _sbo_rvol = (float(last['volume']) / float(_sbo_vol_sma)) if _sbo_vol_sma and _sbo_vol_sma > 0 else 0.0
                _sbo_volume_ok = _sbo_rvol >= SBO_VOLUME_THRESHOLD
                _sbo_di_ok = state.di_plus > state.di_minus
            else:
                _sbo_volume_ok = False
                _sbo_di_ok = False
                _sbo_rvol = 0.0

            if _sbo_breakout and _sbo_volume_ok and _sbo_di_ok:
                # VALID: SWING_BREAKOUT
                _sbo_reward = (
                    f"{_reward_label} [{_capital_rr:.2f}]"
                    if _reward_label and _capital_rr is not None
                    else "N/A"
                )
                _diag = (
                    f"PRE-APPROVED (entry: SWING_BREAKOUT | state: RESOLVING | "
                    f"reward: {_sbo_reward} | trigger: BAR CLOSE ONLY). "
                    f"Price {round(last['close'] / price_scaler, 2)} closed above resistance "
                    f"{round(resistance_raw / price_scaler, 2)} with RVOL {_sbo_rvol:.2f}. "
                    f"ADX: {state.adx_t:.1f}. +DI: {state.di_plus:.1f} > -DI: {state.di_minus:.1f}. "
                    f"Entry: execute at THIS bar's close. "
                    f"Stop: {hard_stop}. {chart_ref}"
                )
                gate_result = GateResult(
                    verdict="VALID",
                    reason="SWING_BREAKOUT",
                    mandate=f"Execute at THIS bar's close. Stop: {hard_stop}.",
                    context=f"Price {round(last['close'] / price_scaler, 2)} above resistance {round(resistance_raw / price_scaler, 2)}. RVOL {_sbo_rvol:.2f}. ADX {state.adx_t:.1f}. +DI {state.di_plus:.1f} > -DI {state.di_minus:.1f}.",
                    legacy_diagnostic=_diag,
                    entry_type="SWING_BREAKOUT",
                    trigger_rule="BAR CLOSE ONLY",
                    state="RESOLVING",
                )
            else:
                # Existing PROFILE A RESOLVING BLOCK — amended diagnostic
                # [PE-45] Conditional RESOLVING cause (existing logic, unchanged)
                if state.adx_t < 25:
                    _resolving_cause = f"ADX {state.adx_t:.1f} -- below 25 threshold"
                else:
                    # ADX sufficient but MA stack broken — find the first broken link
                    try:
                        _c = round(last['close'] / price_scaler, 2)
                        _e8 = round(last['EMA_8'] / price_scaler, 2)
                        _e21 = round(last['EMA_21'] / price_scaler, 2)
                        _s50 = round(last['SMA_50'] / price_scaler, 2)
                        if last['close'] <= last['EMA_8']:
                            _break = f"Price {_c} <= EMA 8 {_e8}"
                        elif last['EMA_8'] <= last['EMA_21']:
                            _break = f"EMA 8 {_e8} <= EMA 21 {_e21}"
                        elif last['EMA_21'] <= last['SMA_50']:
                            _break = f"EMA 21 {_e21} <= SMA 50 {_s50}"
                        else:
                            _s200 = round(last['SMA_200'] / price_scaler, 2) if last.get('SMA_200') == last.get('SMA_200') else 'N/A'
                            if isinstance(_s200, float) and last['SMA_50'] <= last['SMA_200']:
                                _break = f"SMA 50 {_s50} <= SMA 200 {_s200}"
                            else:
                                _break = "MA stack incomplete"
                    except (KeyError, TypeError):
                        _break = "MA stack incomplete"
                    _resolving_cause = f"MA stack broken ({_break}) -- ADX {state.adx_t:.1f} sufficient but structure incomplete"
                _diag = (f"WAIT (reason: PROFILE A RESOLVING BLOCK). CONVEXITY PROTOCOL BLOCKED (Profile A): "
                                     f"Profile A requires TRENDING state for pullback entry. "
                                     f"Current: RESOLVING ({_resolving_cause}). "
                                     f"Mandate: WAIT for ADX > 25 and TRENDING state to enable pullback entry path. "
                                     f"Floor: {floor_price}.")
                gate_result = GateResult(
                    verdict="INVALID",
                    reason="PROFILE A RESOLVING BLOCK",
                    mandate=f"WAIT for ADX > 25 and TRENDING state to enable pullback entry path.",
                    context=f"CONVEXITY PROTOCOL BLOCKED (Profile A): RESOLVING ({_resolving_cause}). Floor: {floor_price}.",
                    legacy_diagnostic=_diag,
                )
        elif at_breakout:
            # SBO-001: Volume + directional confirmation on Profile B breakout
            _bo_vol_sma = last.get('vol_sma_20', 0)
            _bo_rvol = (float(last['volume']) / float(_bo_vol_sma)) if _bo_vol_sma and _bo_vol_sma > 0 else 0.0
            _bo_volume_ok = _bo_rvol >= SBO_VOLUME_THRESHOLD

            if not _bo_volume_ok:
                _diag = (f"WAIT (reason: NO BREAKOUT). RESOLVING (ADX {state.adx_t:.1f}) -- "
                         f"breakout detected but volume insufficient (RVOL {_bo_rvol:.2f} < {SBO_VOLUME_THRESHOLD}). "
                         f"Mandate: WAIT for volume-confirmed breakout.")
                gate_result = GateResult(
                    verdict="INVALID",
                    reason="NO BREAKOUT",
                    mandate="WAIT for volume-confirmed breakout.",
                    context=f"RESOLVING (ADX {state.adx_t:.1f}) -- breakout detected but RVOL {_bo_rvol:.2f} < {SBO_VOLUME_THRESHOLD}.",
                    legacy_diagnostic=_diag,
                )
            else:
                # DI check deferred until volume passes (avoids evaluating
                # di_plus/di_minus on non-volume-confirmed bars)
                _bo_di_ok = state.di_plus > state.di_minus
                if not _bo_di_ok:
                    _diag = (f"WAIT (reason: NO BREAKOUT). RESOLVING (ADX {state.adx_t:.1f}) -- "
                             f"breakout detected but -DI ({state.di_minus:.1f}) > +DI ({state.di_plus:.1f}). "
                             f"Mandate: WAIT for directional confirmation.")
                    gate_result = GateResult(
                        verdict="INVALID",
                        reason="NO BREAKOUT",
                        mandate="WAIT for directional confirmation.",
                        context=f"RESOLVING (ADX {state.adx_t:.1f}) -- breakout but -DI ({state.di_minus:.1f}) > +DI ({state.di_plus:.1f}).",
                        legacy_diagnostic=_diag,
                    )
                else:
                    # Existing VALID BREAKOUT path (volume + direction confirmed)
                    _bo_reward = (
                        f"{_reward_label} [{_capital_rr:.2f}]"
                        if _reward_label and _capital_rr is not None
                        else "N/A"
                    )
                    _diag = (
                        f"PRE-APPROVED (entry: BREAKOUT | state: RESOLVING | "
                        f"reward: {_bo_reward} | trigger: INTRADAY). "
                        f"Price {round(last['close'] / price_scaler, 2)} closed above resistance "
                        f"{round(resistance_raw / price_scaler, 2)}. "
                        f"ADX: {state.adx_t:.1f}. "
                        f"Entry: INTRADAY permitted -- may enter while breakout bar is still forming. "
                        f"{'Floor Support' if is_etf else 'Convex Support'}: price must remain above "
                        f"{'baseline floor' if is_etf else 'EMA 8'} ({round(_convex_support_level / price_scaler, 2)}). "
                        f"Stop: {hard_stop}. {chart_ref}"
                    )
                    gate_result = GateResult(
                        verdict="VALID",
                        reason="BREAKOUT",
                        mandate=f"INTRADAY permitted. {'Floor' if is_etf else 'Convex'} Support: price must remain above {round(_convex_support_level / price_scaler, 2)}. Stop: {hard_stop}.",
                        context=f"Price {round(last['close'] / price_scaler, 2)} closed above resistance {round(resistance_raw / price_scaler, 2)}. ADX: {state.adx_t:.1f}.",
                        legacy_diagnostic=_diag,
                        entry_type="BREAKOUT",
                        trigger_rule="INTRADAY",
                        state="RESOLVING",
                    )
        else:
            reason = (
                "No breakout above resistance"  if not df['Is_Breakout'].iloc[-1]
                else ("Floor Support failed: Price below baseline floor" if is_etf
                      else "Convex Support failed: Price below EMA 8")
            )
            _diag = (f"WAIT (reason: NO BREAKOUT). RESOLVING (ADX {state.adx_t:.1f}) -- {reason} at "
                                 f"{round(resistance_raw / price_scaler, 2)}. "
                                 f"Mandate: WAIT for Consolidation Range violation.")
            gate_result = GateResult(
                verdict="INVALID",
                reason="NO BREAKOUT",
                mandate="WAIT for Consolidation Range violation.",
                context=f"RESOLVING (ADX {state.adx_t:.1f}) -- {reason} at {round(resistance_raw / price_scaler, 2)}.",
                legacy_diagnostic=_diag,
            )

    # ---- PRIORITY 4: AMBIGUOUS (ADX 20-25, MA stack incomplete) ----
    if gate_result is None:
        _diag = (f"WAIT (reason: AMBIGUOUS STATE). ENGINE STATE AMBIGUOUS: ADX {state.adx_t:.1f} > 20 but TRENDING not confirmed "
                             f"(MA stack incomplete or ADX < 25). Mandate: HARD WAIT.")
        gate_result = GateResult(
            verdict="INVALID",
            reason="AMBIGUOUS STATE",
            mandate="HARD WAIT. ADX > 20 but TRENDING not confirmed.",
            context=f"ENGINE STATE AMBIGUOUS: ADX {state.adx_t:.1f} > 20 but TRENDING not confirmed (MA stack incomplete or ADX < 25).",
            legacy_diagnostic=_diag,
        )

    # ==================================================================
    # AVWAP-001 DQ-9: VWAP TRIGGER CONDITION (Profile A only)
    # Close above session VWAP required on all Profile A entry triggers.
    # Applied only when structural gates have already PASSED (verdict=VALID).
    # Session maturity waiver: first completed bar of session → waive.
    # ==================================================================
    if p_code == "A" and gate_result is not None and gate_result.verdict == "VALID":
        _session_vwap = last.get('SESSION_VWAP', None)
        _is_first_bar = _detect_session_first_bar(df, cfg.iq)

        if _session_vwap is not None and not _is_first_bar:
            if last['close'] <= _session_vwap:
                # Structural VALID but VWAP timing hold
                metrics["VWAP_Trigger_Status"] = "AWAITING_RECLAIM"
                metrics["VWAP_Trigger_Price"] = round(_session_vwap / price_scaler, 2)
                metrics["VWAP_Trigger_Confirmed"] = False
                # Note: verdict remains VALID — output.py (Phase 3) surfaces the timing hold.
                # The metric is written; output formatting is deferred to Phase 3.
            else:
                metrics["VWAP_Trigger_Status"] = "CONFIRMED"
                metrics["VWAP_Trigger_Price"] = round(_session_vwap / price_scaler, 2)
                metrics["VWAP_Trigger_Confirmed"] = True
        elif _is_first_bar:
            metrics["VWAP_Trigger_Status"] = "WAIVED"
            metrics["VWAP_Trigger_Note"] = "Session maturity waiver -- first completed bar of session"
            metrics["VWAP_Trigger_Confirmed"] = False
        else:
            metrics["VWAP_Trigger_Status"] = "UNAVAILABLE"
            metrics["VWAP_Trigger_Confirmed"] = False

    # ==================================================================
    # PASS-ONLY SECTION: PE-30
    # [RFT-002 Phase 2] Focus Chart and ENG-002 moved to Layer 5.
    # Only PE-30 remains — it modifies Resistance_Note which is read
    # by the trigger diagnostic.
    # ==================================================================

    if gate_result is not None and gate_result.verdict == "VALID":
        # ==================================================================
        # PE-30: Align Resistance_Note with BREAKOUT verdict
        # ==================================================================
        if _resistance_suppressed and at_breakout:
            metrics["Resistance_Note"] = (
                f"BROKEN: resistance ({resistance_display}) violated on breakout. "
                f"Now support reference. "
                f"{'Convex' if not is_etf else 'Floor'} Support: "
                f"{'EMA 8' if not is_etf else 'baseline floor'} "
                f"({round(_convex_support_level / price_scaler, 2)})."
            )

        # [RFT-002 Phase 2] Focus Chart and ENG-002 moved to _assemble_output()
        # (Layer 5) — presentation concerns with no ordering dependency on
        # Layer 4 logic. PE-30 remains here as it modifies a metric used by
        # the trigger diagnostic.

    return gate_result
