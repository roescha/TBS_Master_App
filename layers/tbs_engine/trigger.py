__all__ = ['_identify_trigger']




# [RFT-001 Phase 7] Layer 4: Trigger Identification
# Extracts the Priority 1-4 trigger chain and PASS-only enrichment (PE-30)
# into a top-level function per spec §III.6.
# [RFT-002 Phase 2] Focus Chart and ENG-002 moved to _assemble_output().
# Receives gate cascade result and determines final (status, diagnostic).
def _identify_trigger(ctx, result_status, result_diagnostic,
                      _capital_rr, _reward_label,
                      _p1_resistance_note, _p1_reward_risk_note):
    """Layer 4: Identify trigger type from state and gate cascade result.

    Wraps the Priority 1-4 trigger chain (RECLAIM, TRENDING/PULLBACK,
    RESOLVING/BREAKOUT, AMBIGUOUS) and PASS-only PE-30 enrichment.

    If result_status is already set by the gate cascade (HALT), the
    trigger chain is skipped and the existing result passes through.

    [RFT-002 Phase 2] Focus Chart rendering and ENG-002 Fibonacci
    Confluence moved to _assemble_output() (Layer 5) — presentation
    concerns that have no ordering dependency on Layer 4 logic.

    Args:
        ctx: RunContext from run_tbs_engine.
        result_status: Gate cascade result ("HALT" or None).
        result_diagnostic: Gate cascade diagnostic (str or None).
        _capital_rr: Capital Reward/Risk ratio.
        _reward_label: Capital R:R label string.
        _p1_resistance_note: Phase 1 Resistance_Note for PE-31 restore.
        _p1_reward_risk_note: Phase 1 Reward_Risk_Note for PE-31 restore.

    Returns:
        tuple: (status, diagnostic) — "PASS" or "HALT" with diagnostic string.
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
    conviction_state = ctx.conviction_state
    price_scaler = ctx.price_scaler
    _resistance_suppressed = ctx._resistance_suppressed

    # Current-bar position flags (independent of window-reset columns)
    # [PE-CAL-1 FIX §6.1] Pullback zone upper bound uses cfg.pb_upper_col.
    # Floor (ANCHOR) remains the lower bound. Profile B widens the zone to
    # encompass the natural pullback channel between SMA 50 and EMA 21.
    _pb_upper_cur = last[cfg.pb_upper_col] + (0.5 * state.atr_raw)
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
    if result_status is None:
        if metrics.get("Resistance_Note") is None:
            metrics["Resistance_Note"] = _p1_resistance_note
        if metrics.get("Reward_Risk_Note") is None:
            metrics["Reward_Risk_Note"] = _p1_reward_risk_note

    # ---- PRIORITY 1: RECLAIM PROTOCOL  [Doc 2 Sec VI.3] ----
    if result_status is None and state.is_reclaim:
        # State quality gate: reclaim is only a valid re-entry signal if the
        # underlying directional state is confirmed (TRENDING or RESOLVING).
        if not (state._entry_trending or state._entry_resolving):
            result_status = "HALT"
            result_diagnostic = (f"WAIT (reason: RECLAIM WITHOUT REGIME). RECLAIM DETECTED but state AMBIGUOUS: ADX {state.adx_t:.1f} -- MA stack incomplete "
                                 f"and no confirmed 3-bar ADX slope. Floor reclaimed ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                                 f"but directional regime not active. Mandate: HARD WAIT. "
                                 f"Monitor for state upgrade (RESOLVING or TRENDING) before re-entry.")
        else:
            result_status = "PASS"
            _reclaim_state = "TRENDING" if state._entry_trending else "RESOLVING"
            _reclaim_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            result_diagnostic = (
                f"PRE-APPROVED (entry: RECLAIM | state: {_reclaim_state} | "
                f"reward: {_reclaim_reward} | trigger: BAR CLOSE ONLY). "
                f"Current bar closed above Floor ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                f"after {state.consec_below} prior bar(s) below Floor. "
                f"ADX: {state.adx_t:.1f}. "
                f"Entry: execute at THIS bar's close. "
                f"If close missed: next bar must ALSO close above {floor_price} before entry is valid. "
                f"Stop: {hard_stop}. {chart_ref}"
            )

    # ---- PRIORITY 2: TRENDING STATE -- Standard/Pullback Protocol  [Doc 2 Sec VI.1] ----
    if result_status is None and state._entry_trending:
        if at_pullback_zone:
            result_status = "PASS"
            _pb_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            result_diagnostic = (
                f"PRE-APPROVED (entry: PULLBACK | state: TRENDING | "
                f"reward: {_pb_reward} | trigger: BAR CLOSE ONLY). "
                f"Price {round(last['close'] / price_scaler, 2)} within pullback zone "
                f"[{floor_price} -- {round(_pb_upper_cur / price_scaler, 2)}]. "
                f"ADX: {state.adx_t:.1f}. "
                f"Entry: execute at THIS bar's close. "
                f"If close missed: next bar must ALSO close within pullback zone before entry is valid. "
                f"Stop: {hard_stop}. {chart_ref}"
            )
        else:
            result_status = "HALT"
            result_diagnostic = (f"WAIT (reason: NOT IN PULLBACK ZONE). TRENDING (ADX {state.adx_t:.1f}) -- price not in pullback zone. "
                                 f"Mandate: WAIT for Pullback Zone entry at [{floor_price} -- {round(_pb_upper_cur / price_scaler, 2)}].")

    # ---- PRIORITY 3: RESOLVING STATE -- Convexity/Breakout Protocol  [Doc 2 Sec VI.2] ----
    if result_status is None and state._entry_resolving:
        # [GENUINE PROFILE LOGIC] Profile A Convexity Protocol block.
        # Profile A requires TRENDING state; RESOLVING is not sufficient.
        # This is a genuine behavioural difference, not a parameter selection.
        if p_code == "A":
            result_status = "HALT"
            result_diagnostic = (f"WAIT (reason: PROFILE A RESOLVING BLOCK). CONVEXITY PROTOCOL BLOCKED (Profile A): "
                                 f"Profile A requires TRENDING state for pullback entry. "
                                 f"Current: RESOLVING (ADX {state.adx_t:.1f} -- below 25 threshold). "
                                 f"Mandate: WAIT for ADX > 25 and TRENDING state to enable pullback entry path. "
                                 f"Floor: {floor_price}.")
        elif at_breakout:
            result_status = "PASS"
            sizing  = "Full Unit" if conviction_state.startswith("HIGH") else "50% Unit (Low Conviction)"
            _bo_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            result_diagnostic = (
                f"PRE-APPROVED (entry: BREAKOUT | state: RESOLVING | "
                f"reward: {_bo_reward} | trigger: INTRADAY). "
                f"Price {round(last['close'] / price_scaler, 2)} closed above resistance "
                f"{round(resistance_raw / price_scaler, 2)}. "
                f"ADX: {state.adx_t:.1f}. Sizing: {sizing}. "
                f"Entry: INTRADAY permitted -- may enter while breakout bar is still forming. "
                f"{'Floor Support' if is_etf else 'Convex Support'}: price must remain above "
                f"{'baseline floor' if is_etf else 'EMA 8'} ({round(_convex_support_level / price_scaler, 2)}). "
                f"Stop: {hard_stop}. {chart_ref}"
            )
        else:
            reason = (
                "No breakout above resistance"  if not df['Is_Breakout'].iloc[-1]
                else ("Floor Support failed: Price below baseline floor" if is_etf
                      else "Convex Support failed: Price below EMA 8")
            )
            result_status = "HALT"
            result_diagnostic = (f"WAIT (reason: NO BREAKOUT). RESOLVING (ADX {state.adx_t:.1f}) -- {reason} at "
                                 f"{round(resistance_raw / price_scaler, 2)}. "
                                 f"Mandate: WAIT for Consolidation Range violation.")

    # ---- PRIORITY 4: AMBIGUOUS (ADX 20-25, MA stack incomplete) ----
    if result_status is None:
        result_status = "HALT"
        result_diagnostic = (f"WAIT (reason: AMBIGUOUS STATE). ENGINE STATE AMBIGUOUS: ADX {state.adx_t:.1f} > 20 but TRENDING not confirmed "
                             f"(MA stack incomplete or ADX < 25). Mandate: HARD WAIT.")

    # ==================================================================
    # PASS-ONLY SECTION: PE-30
    # [RFT-002 Phase 2] Focus Chart and ENG-002 moved to Layer 5.
    # Only PE-30 remains — it modifies Resistance_Note which is read
    # by the trigger diagnostic.
    # ==================================================================

    if result_status == "PASS":
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

    return result_status, result_diagnostic
