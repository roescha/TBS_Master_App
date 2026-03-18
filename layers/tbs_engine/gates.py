import pandas as pd
from tbs_engine.helpers import _evaluate_floor_failure_context
from tbs_engine.types import GateResult

__all__ = ['_gate_context_regime', '_gate_liquidity', '_gate_data_integrity', '_gate_floor_failure', '_gate_floor_violation', '_gate_floor_violation_active', '_gate_climax', '_gate_midrange', '_gate_directional', '_gate_modifier_e', '_gate_window', '_assess_tq_override', '_gate_extension', '_gate_floor_proximity_c', '_gate_expectancy', '_gate_capital_expectancy']
# ==============================================================================
# PHASE 1 — EXTRACTED GATE FUNCTIONS  [RFT-001]
# DIAG-001 Phase 2A — Returns refactored from (status, diagnostic) to GateResult.
#
# Each gate returns None if passed, or GateResult(...) if failed.
# Gate order matches Engine Execution Map v1.9 §II.
# These are structural extractions — zero logic changes from inline originals.
# ==============================================================================


def _gate_context_regime(p_code, df_ctx, price_scaler, metrics):
    """CRG-1 (Profile A) + CRG-2 (Profile B) — Context Regime Gate [Doc 2 Amendment].
    Returns None if passed, or (status, diagnostic) if failed."""

    if p_code == "A":
        if (df_ctx is not None
                and 'SMA_50' in df_ctx.columns and 'SMA_200' in df_ctx.columns
                and not pd.isna(df_ctx['SMA_50'].iloc[-1])
                and not pd.isna(df_ctx['SMA_200'].iloc[-1])):
            _ctx_last = df_ctx.iloc[-1]
            _crg_golden_cross    = bool(_ctx_last['SMA_50'] > _ctx_last['SMA_200'])
            _crg_price_vs_sma200 = round(float(_ctx_last['close'] - _ctx_last['SMA_200']) / price_scaler, 2)
            metrics["Context_Golden_Cross"]    = _crg_golden_cross
            metrics["Context_Price_vs_SMA200"] = _crg_price_vs_sma200
            # [ENG-005 FIX] Context_SMA200 was written raw (pence for LSE equities)
            # while all other Operator-facing price metrics divide by price_scaler.
            # Apply the same scaling so Context_SMA200 displays in GBP, matching
            # SMA_200 / Price / Floor / Stop etc. in the payload.
            metrics["Context_SMA200"]          = round(float(_ctx_last['SMA_200']) / price_scaler, 2)

            # [FFD-001] Higher-frame context enrichment — Profile A (daily)
            # Written on ALL evaluations for Operator auditability (DQ-5).
            if not pd.isna(_ctx_last['SMA_50']) and len(df_ctx) >= 2 and not pd.isna(df_ctx['SMA_50'].iloc[-2]):
                _daily_sma50_slope = round(float(_ctx_last['SMA_50'] - df_ctx['SMA_50'].iloc[-2]) / price_scaler, 2)
                metrics["Context_Daily_SMA50_Slope"] = _daily_sma50_slope
                metrics["Context_Daily_SMA50"]       = round(float(_ctx_last['SMA_50']) / price_scaler, 2)
            else:
                metrics["Context_Daily_SMA50_Slope"] = None
                metrics["Context_Daily_SMA50"]       = None

            _crg_failures = []
            if not _crg_golden_cross:
                _crg_failures.append("Daily Golden Cross absent")
            if _ctx_last['close'] <= _ctx_last['SMA_200']:
                _crg_failures.append("Price below Daily SMA 200")
            if _crg_failures:
                _diag = (
                    f"REJECT (reason: CONTEXT REGIME FAILED). CONTEXT REGIME FAILED (Profile A): {' + '.join(_crg_failures)}. "
                    f"Hourly execution requires daily structural uptrend. "
                    f"Mandate: asset disqualified until daily regime recovers."
                )
                return GateResult(
                    verdict="INVALID",
                    reason="CONTEXT REGIME FAILED",
                    mandate="Asset disqualified until daily regime recovers.",
                    context=f"CONTEXT REGIME FAILED (Profile A): {' + '.join(_crg_failures)}. Hourly execution requires daily structural uptrend.",
                    legacy_diagnostic=_diag,
                )
        else:
            # df_ctx unavailable or SMA columns NaN -- cannot verify regime
            metrics["Context_Golden_Cross"]    = None
            metrics["Context_Price_vs_SMA200"] = None
            metrics["Context_SMA200"]          = None
            metrics["Context_Daily_SMA50_Slope"] = None
            metrics["Context_Daily_SMA50"]       = None
            return GateResult(
                    verdict="INVALID",
                    reason="DATA INTEGRITY",
                    mandate="Cannot verify structural regime. Await sufficient daily data.",
                    context="CONTEXT REGIME: Insufficient daily data for SMA 200 computation.",
                    legacy_diagnostic=(
                        "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: Insufficient daily data for SMA 200 computation. "
                        "Cannot verify structural regime."
                    ),
                )

    if p_code == "B":
        if (df_ctx is not None
                and len(df_ctx) >= 2
                and 'SMA_50' in df_ctx.columns):
            current_weekly_sma50 = df_ctx['SMA_50'].iloc[-1]
            prior_weekly_sma50   = df_ctx['SMA_50'].iloc[-2]

            if pd.isna(current_weekly_sma50) or pd.isna(prior_weekly_sma50):
                metrics["Context_Weekly_SMA50_Slope"]  = None
                metrics["Context_Weekly_SMA50_Rising"] = None
                metrics["Context_Weekly_SMA50"]        = None
                metrics["Context_Weekly_Golden_Cross"]    = None
                metrics["Context_Weekly_Price_vs_SMA200"] = None
                return GateResult(
                    verdict="INVALID",
                    reason="DATA INTEGRITY",
                    mandate="Cannot verify structural regime. Await sufficient weekly data.",
                    context="CONTEXT REGIME: Insufficient weekly data for SMA 50 slope computation.",
                    legacy_diagnostic=(
                        "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: "
                        "Insufficient weekly data for SMA 50 slope computation. "
                        "Cannot verify structural regime."
                    ),
                )

            weekly_sma50_rising = bool(current_weekly_sma50 > prior_weekly_sma50)
            slope_value = round((current_weekly_sma50 - prior_weekly_sma50) / price_scaler, 2)

            metrics["Context_Weekly_SMA50_Slope"]  = slope_value
            metrics["Context_Weekly_SMA50_Rising"] = weekly_sma50_rising
            metrics["Context_Weekly_SMA50"]        = round(current_weekly_sma50 / price_scaler, 2)

            # [FFD-001] Higher-frame context enrichment — Profile B (weekly)
            # Written on ALL evaluations for Operator auditability (DQ-5).
            _ctx_last_b = df_ctx.iloc[-1]
            if 'SMA_200' in df_ctx.columns and not pd.isna(_ctx_last_b['SMA_200']):
                metrics["Context_Weekly_Golden_Cross"]    = bool(_ctx_last_b['SMA_50'] > _ctx_last_b['SMA_200'])
                metrics["Context_Weekly_Price_vs_SMA200"] = round(float(_ctx_last_b['close'] - _ctx_last_b['SMA_200']) / price_scaler, 2)
            else:
                metrics["Context_Weekly_Golden_Cross"]    = None
                metrics["Context_Weekly_Price_vs_SMA200"] = None

            if not weekly_sma50_rising:
                _diag = (
                    f"REJECT (reason: CONTEXT REGIME FAILED). CONTEXT REGIME FAILED "
                    f"(Profile B): Weekly SMA 50 declining (slope: {slope_value}). "
                    f"Intermediate-term trend not confirmed. Daily execution requires "
                    f"weekly structural improvement. Mandate: asset disqualified until "
                    f"weekly SMA 50 turns positive."
                )
                return GateResult(
                    verdict="INVALID",
                    reason="CONTEXT REGIME FAILED",
                    mandate="Asset disqualified until weekly SMA 50 turns positive.",
                    context=f"CONTEXT REGIME FAILED (Profile B): Weekly SMA 50 declining (slope: {slope_value}). Intermediate-term trend not confirmed.",
                    legacy_diagnostic=_diag,
                )
        else:
            # df_ctx unavailable or < 2 bars or SMA_50 column missing
            metrics["Context_Weekly_SMA50_Slope"]  = None
            metrics["Context_Weekly_SMA50_Rising"] = None
            metrics["Context_Weekly_SMA50"]        = None
            metrics["Context_Weekly_Golden_Cross"]    = None
            metrics["Context_Weekly_Price_vs_SMA200"] = None
            return GateResult(
                    verdict="INVALID",
                    reason="DATA INTEGRITY",
                    mandate="Cannot verify structural regime. Await sufficient weekly data.",
                    context="CONTEXT REGIME: Insufficient weekly data for SMA 50 computation.",
                    legacy_diagnostic=(
                        "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: "
                        "Insufficient weekly data for SMA 50 computation. "
                        "Cannot verify structural regime."
                    ),
                )

    return None  # Gate passed


def _gate_liquidity(adv_20, is_etf, _is_lse_etf):
    """Gate 0 — Liquidity Check [Doc 2 Sec.II / Doc 8 Sec.II-IV].
    Returns None if passed, or (status, diagnostic) if failed."""

    _adv_limit_early = 5_000_000 if _is_lse_etf else (50_000_000 if is_etf else 5_000_000)
    if not pd.isna(adv_20) and adv_20 < _adv_limit_early:
        _diag = f"REJECT (reason: LIQUIDITY FAILED). Liquidity Failed ({'ETF' if is_etf else 'EQUITY'}): ${adv_20/1e6:.1f}M (Req >${_adv_limit_early/1e6:.0f}M)"
        return GateResult(
            verdict="INVALID",
            reason="LIQUIDITY FAILED",
            mandate=f"Liquidity insufficient. Below ${_adv_limit_early/1e6:.0f}M threshold.",
            context=f"Liquidity Failed ({'ETF' if is_etf else 'EQUITY'}): ${adv_20/1e6:.1f}M (Req >${_adv_limit_early/1e6:.0f}M).",
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


def _gate_data_integrity(atr_raw):
    """Data Integrity Check (ATR NaN/0) [Doc 2 Sec 4.1].
    Returns None if passed, or (status, diagnostic) if failed."""

    if pd.isna(atr_raw) or atr_raw == 0:
        _diag = "REJECT (reason: DATA INTEGRITY). Invalid ATR for proximity math (ATR is NaN or 0)."
        return GateResult(
            verdict="INVALID",
            reason="DATA INTEGRITY",
            mandate="Invalid ATR. Cannot compute proximity or risk metrics.",
            context="Invalid ATR for proximity math (ATR is NaN or 0).",
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


# [FFD-001-BR-2] _evaluate_floor_failure_context moved to helpers.py.
# Imported above for use by _gate_floor_failure.


def _gate_floor_failure(consec_below, is_floor_failure, p_code,
                        state=None, df_ctx=None, metrics=None, _ff_threshold=4):
    """Gate 1 — Floor Failure [Doc 2 Sec 4.1] + FFD-001 BREACH/FAILURE bifurcation.

    When state and df_ctx are provided, evaluates composite conditions to
    distinguish FLOOR BREACH (WAIT/WARNING) from FLOOR FAILURE (REJECT/EXIT).
    Without state/df_ctx, falls back to original FLOOR FAILURE behaviour.

    Returns None if passed, or (status, diagnostic) if failed."""
    if is_floor_failure:
        # --- FFD-001: Composite check ---
        if state is not None and metrics is not None:
            is_breach, context_label, failing_conds = _evaluate_floor_failure_context(
                state, df_ctx, p_code
            )
            metrics["Floor_Failure_Context"] = context_label

            if is_breach:
                # FLOOR BREACH → WAIT / WARNING (PE-28 graduation: early deterioration)
                metrics["Exit_Signal"] = "WARNING"
                _bar_note = " (evaluated on last completed bar)" if p_code == "A" else ""
                _diag = (
                    f"WAIT (reason: FLOOR BREACH). FLOOR BREACH: {consec_below}/{_ff_threshold} consecutive bars "
                    f"below Floor (threshold reached, higher-frame intact). "
                    f"Monitor for 3-bar reclaim.{_bar_note}"
                )
                return GateResult(
                    verdict="INVALID",
                    reason="FLOOR BREACH",
                    mandate="Monitor for 3-bar reclaim.",
                    context=f"FLOOR BREACH: {consec_below}/{_ff_threshold} consecutive bars below Floor (threshold reached, higher-frame intact).{_bar_note}",
                    legacy_diagnostic=_diag,
                )
            else:
                # FLOOR FAILURE → REJECT / EXIT (unchanged behaviour)
                # Build diagnostic with failing condition detail
                _detail = ""
                if failing_conds:
                    _detail = f" Structural break ({failing_conds[0]})."
                else:
                    _detail = " Structural break."
                _bar_note = " (evaluated on last completed bar)" if p_code == "A" else ""
                _diag = (
                    f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE: {consec_below}/{_ff_threshold} consecutive bars "
                    f"below Floor (threshold reached, higher-frame broken).{_detail}{_bar_note}"
                )
                return GateResult(
                    verdict="INVALID",
                    reason="FLOOR FAILURE",
                    mandate="Asset disqualified. Structural breakdown confirmed.",
                    context=f"FLOOR FAILURE: {consec_below}/{_ff_threshold} consecutive bars below Floor (threshold reached, higher-frame broken).{_detail}{_bar_note}",
                    legacy_diagnostic=_diag,
                )

        # Fallback: no composite params (backward compatibility)
        _diag = (
            f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE: {consec_below}/{_ff_threshold} consecutive bars "
            f"below Floor (threshold reached, higher-frame broken). Structural break."
            + (" (evaluated on last completed bar)" if p_code == "A" else "")
        )
        return GateResult(
            verdict="INVALID",
            reason="FLOOR FAILURE",
            mandate="Asset disqualified. Structural breakdown confirmed.",
            context=f"FLOOR FAILURE: {consec_below}/{_ff_threshold} consecutive bars below Floor (threshold reached, higher-frame broken). Structural break." + (" (evaluated on last completed bar)" if p_code == "A" else ""),
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


def _gate_floor_violation(floor_dist, is_violated, p_code, consec_below=0, _ff_threshold=4):
    """Gate 1 — Floor Warning (floor_dist check) [Doc 2 Sec 4.1].
    Returns None if passed, or (status, diagnostic) if failed."""
    if floor_dist < -0.15 and not is_violated:
        _diag = (f"WAIT (reason: FLOOR WARNING). FLOOR WARNING: {consec_below}/{_ff_threshold} consecutive bars below Floor (threshold not reached). Price {abs(floor_dist):.2f} ATR below Floor. (evaluated on last completed bar)" if p_code == "A" else f"WAIT (reason: FLOOR WARNING). FLOOR WARNING: {consec_below}/{_ff_threshold} consecutive bars below Floor (threshold not reached). Price {abs(floor_dist):.2f} ATR below Floor.")
        _bar_note = " (evaluated on last completed bar)" if p_code == "A" else ""
        return GateResult(
            verdict="INVALID",
            reason="FLOOR WARNING",
            mandate="WAIT. Price below floor, threshold not reached.",
            context=f"FLOOR WARNING: {consec_below}/{_ff_threshold} consecutive bars below Floor (threshold not reached). Price {abs(floor_dist):.2f} ATR below Floor.{_bar_note}",
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


def _gate_floor_violation_active(is_violated, is_reclaim, consec_below, floor_price,
                                 last_close, price_scaler, metrics, _ff_threshold=4):
    """Gate 1.5 — Floor Warning Active (no reclaim) [Doc 2 Sec 4.1].
    Returns None if passed, or (status, diagnostic) if failed."""
    if is_violated and not is_reclaim:
        _diag = (
            f"WAIT (reason: FLOOR WARNING ACTIVE). FLOOR WARNING ACTIVE: {consec_below}/{_ff_threshold} consecutive bars below Floor ({floor_price}). "
            f"Current bar has NOT reclaimed (Close {round(last_close / price_scaler, 2)} < Floor {floor_price}). "
            f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above {floor_price}. "
            f"Note: Exit_Signal activates after 3 consecutive closes below floor ({consec_below}/3 bars)."
        )
        return GateResult(
            verdict="INVALID",
            reason="FLOOR WARNING ACTIVE",
            mandate=f"HARD WAIT. Entry only valid on confirmed reclaim close above {floor_price}.",
            context=f"FLOOR WARNING ACTIVE: {consec_below}/{_ff_threshold} consecutive bars below Floor ({floor_price}). Current bar has NOT reclaimed (Close {round(last_close / price_scaler, 2)} < Floor {floor_price}). Exit_Signal activates after 3 consecutive closes below floor ({consec_below}/3 bars).",
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


def _gate_climax(df, p_code, is_reclaim, check_climax_history_fn):
    """Gate 3 — Volume Climax [Doc 2 Sec.II / Doc 6 Sec.3.6].
    Returns None if passed, or (status, diagnostic) if failed."""

    climax_df = df.iloc[:-1] if p_code == "A" else df
    if pd.isna(climax_df['vol_sma_9'].iloc[-1]):
        _diag = "REJECT (reason: DATA INTEGRITY). Climax check failed: Volume SMA9 is NaN (insufficient volume history)."
        return GateResult(
            verdict="INVALID",
            reason="DATA INTEGRITY",
            mandate="Climax check failed. Insufficient volume history.",
            context="Volume SMA9 is NaN (insufficient volume history).",
            legacy_diagnostic=_diag,
        )
    climax, ago = check_climax_history_fn(climax_df)
    if climax and ago is None:
        ago = 0
    if p_code == "A" and climax:
        ago += 1
    if climax:
        if is_reclaim:
            # Reclaim voided: cannot re-enter during the 3-bar climax window
            _diag = f"WAIT (reason: VOLUME CLIMAX). CLIMAX PRECEDENCE: Reclaim voided by Climax {ago} bars ago."
            return GateResult(
                verdict="INVALID",
                reason="VOLUME CLIMAX",
                mandate="WAIT. Reclaim voided by climax window.",
                context=f"CLIMAX PRECEDENCE: Reclaim voided by Climax {ago} bars ago.",
                legacy_diagnostic=_diag,
            )
        _diag = f"WAIT (reason: VOLUME CLIMAX). CLIMAX BLOCK: Institutional selling {ago} bars ago."
        return GateResult(
            verdict="INVALID",
            reason="VOLUME CLIMAX",
            mandate="WAIT. Institutional selling detected within climax window.",
            context=f"CLIMAX BLOCK: Institutional selling {ago} bars ago.",
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


def _gate_midrange(adx_t, ma_squeeze, atr_dist, ext_limit):
    """Gate 4 — MID-RANGE Hard Wait [Doc 2 Sec 4.2].
    Returns None if passed, or (status, diagnostic) if failed."""
    # [PE-11] Extension Warning: when MID-RANGE fires but extension would ALSO
    # fail, annotate the diagnostic so the operator knows two independent blocks
    # are active.
    _ext_warning = (
        f" [NOTE: Also EXTENDED at {atr_dist:.2f} ATR (limit {ext_limit}) "
        f"-- two independent blocks active]"
    ) if atr_dist > ext_limit else ""

    if adx_t < 20:
        _diag = f"WAIT (reason: MID-RANGE (ADX < 20)). MID-RANGE BLOCK: ADX ({adx_t:.2f}) < 20. HARD WAIT.{_ext_warning}"
        return GateResult(
            verdict="INVALID",
            reason="MID-RANGE (ADX < 20)",
            mandate="HARD WAIT. ADX below 20 threshold.",
            context=f"MID-RANGE BLOCK: ADX ({adx_t:.2f}) < 20.{_ext_warning}",
            legacy_diagnostic=_diag,
        )
    if ma_squeeze:
        _diag = f"WAIT (reason: MID-RANGE (MA SQUEEZE)). MID-RANGE BLOCK: EMA 8/21 Squeeze 3+ bars. HARD WAIT.{_ext_warning}"
        return GateResult(
            verdict="INVALID",
            reason="MID-RANGE (MA SQUEEZE)",
            mandate="HARD WAIT. EMA 8/21 squeeze active.",
            context=f"MID-RANGE BLOCK: EMA 8/21 Squeeze 3+ bars.{_ext_warning}",
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


def _gate_directional(di_plus, di_minus, p_code, ema_stacked, _entry_trending,
                      ma_stack_full, floor_prox_pct, adx_t, adx_t1):
    """Gate 4.1 — Directional Dominance [Doc 2 Sec VI].
    Returns None if passed, or (status, diagnostic) if failed."""

    if pd.isna(di_plus) or pd.isna(di_minus):
        _diag = "REJECT (reason: DATA INTEGRITY). Directional Dominance failed: DI values are NaN."
        return GateResult(
            verdict="INVALID",
            reason="DATA INTEGRITY",
            mandate="Directional Dominance check failed. DI values unavailable.",
            context="Directional Dominance failed: DI values are NaN.",
            legacy_diagnostic=_diag,
        )
    if di_minus > di_plus:
        if p_code == "A" and ema_stacked:
            pass  # Profile A exemption: EMA 8 > EMA 21 stack intact
        elif p_code == "B" and _entry_trending and ma_stack_full:
            pass  # Profile B TRENDING exemption: full MA stack overrides momentary
            # -DI dominance during pullback corrective phase  [DOC 2 SEC VI]
        elif p_code == "C" and floor_prox_pct is not None and floor_prox_pct <= 5.0 and (adx_t > adx_t1):
            pass  # [PE-CAL-1 §6.6] Profile C counter-cyclical exemption:
            # within 5% of SMA 200 + positive ADX slope. WEALTH entries at the
            # structural floor are inherently counter-cyclical. -DI dominance is
            # expected during the decline that brings price to the floor.
        else:
            _diag = f"WAIT (reason: DIRECTIONAL BLOCK). DIRECTIONAL BLOCK: -DI ({di_minus:.2f}) > +DI ({di_plus:.2f})"
            return GateResult(
                verdict="INVALID",
                reason="DIRECTIONAL BLOCK",
                mandate="WAIT. Bearish directional dominance active.",
                context=f"DIRECTIONAL BLOCK: -DI ({di_minus:.2f}) > +DI ({di_plus:.2f}).",
                legacy_diagnostic=_diag,
            )
    return None  # Gate passed


def _gate_modifier_e(last_open, prev_high, atr_raw, last_close):
    """Gate 4.2 — Modifier E Gap-Trap [Doc 2 Sec VII].
    Returns None if passed, or (status, diagnostic) if failed."""
    if (last_open > (prev_high + (0.5 * atr_raw))) and (last_close < last_open):
        _diag = "REJECT (reason: GAP TRAP). MODIFIER E BLOCK: Gap-Trap. Immediate HALT."
        return GateResult(
            verdict="INVALID",
            reason="GAP TRAP",
            mandate="Immediate HALT. Gap-Trap detected.",
            context="MODIFIER E BLOCK: Gap-Trap detected.",
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


def _gate_window(window_count, window_limit):
    """Gate 4.3 — Execution Window [Doc 2 Sec III].
    Returns None if passed, or (status, diagnostic) if failed."""
    if window_count > window_limit:
        wc_label = "NONE FOUND (sentinel)" if window_count == 99 else str(window_count)
        _diag = f"WAIT (reason: WINDOW EXPIRED). WINDOW EXPIRED: Window {wc_label} (Requires 0-{window_limit}). PLANNING ONLY."
        return GateResult(
            verdict="INVALID",
            reason="WINDOW EXPIRED",
            mandate="PLANNING ONLY. Execution window expired.",
            context=f"WINDOW EXPIRED: Window {wc_label} (Requires 0-{window_limit}).",
            legacy_diagnostic=_diag,
        )
    return None  # Gate passed


def _assess_tq_override(ctx, atr_dist):
    """Post-gate assessment: Trend Quality Override eligibility [Doc 2 Sec VIII.2].
    Writes Trend_Quality_Override dict to metrics. Does not return a value.
    Called only when extension gate has failed (atr_dist > effective limit)."""

    # --- RunContext unpacking (RFT-003 F3) ---
    p_code = ctx.p_code
    is_etf = ctx.is_etf
    is_trending = ctx.state.is_trending
    adx_accel_state = ctx.adx_accel_state
    adx_accel = ctx.adx_accel
    vol_confirm_state = ctx.vol_confirm_state
    vol_confirm_ratio = ctx.vol_confirm_ratio
    exit_signal = ctx.exit_signal
    structural_floor_raw = ctx.structural_floor_raw
    atr_raw = ctx.state.atr_raw
    price_scaler = ctx.price_scaler
    resistance_raw = ctx.resistance_raw
    resistance_display = ctx.resistance_display
    _resistance_suppressed = ctx._resistance_suppressed
    ext_limit = ctx.ext_limit
    last = ctx.last
    metrics = ctx.metrics

    # ==================================================================
    # TREND QUALITY OVERRIDE ASSESSMENT  [MANDATE: DOC 2 SEC VIII.2]
    #
    # The extension gate HALT is maintained. This block evaluates whether
    # the Operator may exercise discretionary override under mandatory
    # risk-reduction constraints. The engine verdict remains HALT; the
    # override is an Operator-layer decision (Doc 4 §I).
    #
    # Eligibility (ALL must be true):
    #   1. Engine State = TRENDING (full MA stack, not RESOLVING)
    #   2. ADX_Accel = ACCELERATING (trend gaining momentum)
    #   3. Vol_Confirm = STRONG INSTITUTIONAL (ratio > 0.7)
    #   4. Extension <= profile ceiling (B: 2.0 ATR, C: 1.0 ATR)
    #   5. No Exit_Signal active  [PE-28]
    #   6. Resistance not suppressed + Override R:R >= 0.5  [PE-13 REVISED]
    #
    # Override is structurally ineligible for:
    #   - Profile A (hourly timeframe -- override would only save ~1 bar)
    #   - ETF (TRENDING suppressed by Logic Lock -- condition 1
    #             structurally impossible).
    #
    # Override terms (non-negotiable):
    #   - 50% unit sizing
    #   - Tightened stop: Floor - 1.0 ATR (vs standard 1.5 ATR)
    #   - Resistance (10-bar high) is mandatory exit (no open-ended runner)
    # ==================================================================

    _override_ceiling = {
        "B": 2.0,    # 1.0 ATR override window above 1.0 base
        "C": 2.0,    # 1.0 ATR override window above 1.0 base [PE-CAL-1 §6.4: realigned from 1.0]
    }
    _ceil = _override_ceiling.get(p_code)

    if _ceil is not None and not is_etf:
        _ov_trending     = is_trending
        _ov_accel        = adx_accel_state == "ACCELERATING"
        _ov_vol          = vol_confirm_state == "STRONG INSTITUTIONAL"
        _ov_within_ceil  = atr_dist <= _ceil
        _ov_no_exit      = (exit_signal == False)  # [PE-28] Any active signal (WARNING or EXIT) blocks override

        _tight_stop_raw  = structural_floor_raw - (1.0 * atr_raw)
        _tight_stop      = round(_tight_stop_raw / price_scaler, 2)

        # [PE-13 REVISED] Override target = Resistance (10-bar consolidation high).
        # The original Floor + 1.5 ATR formula is structurally incompatible with
        # extended entries: in any established TRENDING state, the EMA_21-SMA_50 gap
        # exceeds 0.5 ATR, making Floor + 1.5 ATR < Price a mathematical certainty.
        #
        # Resistance is the correct target because:
        #   (a) It's a real structural level (10-bar high), not a synthetic computation
        #   (b) If price is already above it (suppressed), no forward target exists
        #       and the override is naturally ineligible
        #   (c) The R:R against the tightened stop enforces positive expectancy
        #
        # Condition 6: Resistance must exist (not suppressed) AND override R:R >= 0.5.
        # The 0.5 minimum (1:2 risk-adjusted) reflects the inferior entry quality:
        # a standard entry near the floor demands 1:1 or better; an override entry
        # at an extended price accepts lower reward per unit risk but must still show
        # meaningful positive expectancy.
        _ov_has_target   = not _resistance_suppressed
        if _ov_has_target:
            _ov_target   = resistance_display
            _ov_reward   = resistance_raw - last['close']
            _ov_risk     = last['close'] - _tight_stop_raw
            _ov_rr       = round(_ov_reward / _ov_risk, 2) if _ov_risk > 0 else 0
            _ov_rr_pass  = _ov_rr >= 0.5
        else:
            _ov_target   = None
            _ov_rr       = None
            _ov_rr_pass  = False

        _ov_eligible     = all([_ov_trending, _ov_accel, _ov_vol,
                                _ov_within_ceil, _ov_no_exit,
                                _ov_has_target, _ov_rr_pass])

        if _ov_eligible:
            metrics["Trend_Quality_Override"] = {
                "Eligible": True,
                "Conditions_Met": (
                    f"TRENDING + ACCELERATING (ADX_Accel {adx_accel}) + "
                    f"STRONG_VOL ({vol_confirm_ratio}) + "
                    f"Extension {atr_dist:.2f} <= {_ceil} ceiling + "
                    f"Override R:R {_ov_rr} >= 0.5 (Target {_ov_target})"
                ),
                "Override_Terms": (
                    f"50% unit | Stop: {_tight_stop} (Floor - 1.0 ATR) | "
                    f"Target: {_ov_target} (Resistance -- mandatory exit)"
                ),
                "Tight_Stop": _tight_stop,
                "Override_Target": _ov_target,
                "Override_RR": _ov_rr,
                "Note": (
                    "OPERATOR DISCRETION: All 6 conditions met. Override permitted "
                    "under reduced sizing and tightened risk. This is NOT a standard PASS."
                )
            }
        else:
            # Build rejection reason(s)
            _ov_fails = []
            if not _ov_trending:    _ov_fails.append("Engine State not TRENDING (MA stack incomplete)")
            if not _ov_accel:       _ov_fails.append(f"ADX not ACCELERATING ({adx_accel_state})")
            if not _ov_vol:         _ov_fails.append(f"Volume not STRONG INSTITUTIONAL ({vol_confirm_state})")
            if not _ov_within_ceil: _ov_fails.append(f"Extension {atr_dist:.2f} exceeds {_ceil} ATR ceiling")
            if not _ov_no_exit:     _ov_fails.append("Exit_Signal active")
            if not _ov_has_target:  _ov_fails.append(
                "Resistance suppressed (price above 10-bar high) -- no forward target"
            )
            if _ov_has_target and not _ov_rr_pass: _ov_fails.append(
                f"Override R:R {_ov_rr} < 0.5 minimum (Target {_ov_target}, "
                f"Stop {_tight_stop}) -- insufficient reward for extended entry"
            )
            metrics["Trend_Quality_Override"] = {
                "Eligible": False,
                "Reason": "; ".join(_ov_fails),
                "Note": "Extension rejection is protective. Do not chase."
            }
    else:
        # Profile A or ETF: override structurally ineligible
        _inelig_reason = (
            "Profile A (hourly timeframe -- no prolonged opportunity cost)"
            if p_code == "A" else
            "ETF (TRENDING state suppressed by Logic Lock)"
            if is_etf else
            "Unknown profile"
        )
        metrics["Trend_Quality_Override"] = {
            "Eligible": False,
            "Reason": f"Override ineligible: {_inelig_reason}",
            "Note": "Extension rejection is protective. Do not chase."
        }


def _gate_extension(ctx, atr_dist, ext_limit):
    """Gate 5 — Extension [Doc 2 Sec VIII].
    Returns None if passed, or (status, diagnostic) if failed."""

    # --- RunContext unpacking (RFT-003 F3) ---
    p_code = ctx.p_code
    is_etf = ctx.is_etf
    is_trending = ctx.state.is_trending
    is_resolving = ctx.state.is_resolving
    _entry_trending = ctx.state._entry_trending
    _entry_resolving = ctx.state._entry_resolving
    last = ctx.last
    resistance_raw = ctx.resistance_raw
    resistance_display = ctx.resistance_display
    _resistance_suppressed = ctx._resistance_suppressed
    floor_prox_pct = ctx.floor_prox_pct
    metrics = ctx.metrics

    # [PE-CAL-1 FIX §6.2] Breakout Extension Exemption
    _is_breakout_bar = (last['close'] > resistance_raw) if p_code == "B" else False
    _effective_ext = 1.5 if (_is_breakout_bar and not is_trending and _entry_resolving) else ext_limit
    if atr_dist > _effective_ext and not (p_code == "B" and not is_etf and not (is_trending or is_resolving)):
        # Gate 5.5 -- Profile C Floor Proximity Audit  [Doc 2 Sec 4.3]
        # [CLN-005] Delegates to _gate_floor_proximity_c — single source of truth
        # for the 15.0% threshold. Previously duplicated inline.
        _floor_prox_result = _gate_floor_proximity_c(p_code, last, floor_prox_pct)
        if _floor_prox_result is not None:
            return _floor_prox_result

        # TQ Override — delegated to _assess_tq_override()  [RFT-002 Phase 1]
        _assess_tq_override(ctx, atr_dist)

        _diag = f"WAIT (reason: EXTENDED). EXTENDED: {atr_dist:.2f} ATR above limit ({_effective_ext})"
        return GateResult(
            verdict="INVALID",
            reason="EXTENDED",
            mandate="WAIT. Price extended beyond ATR limit.",
            context=f"EXTENDED: {atr_dist:.2f} ATR above limit ({_effective_ext}).",
            legacy_diagnostic=_diag,
        )

    return None  # Gate passed


def _gate_floor_proximity_c(p_code, last, floor_prox_pct):
    """Gate 5.5 — Profile C Floor Proximity Audit [Doc 2 Sec 4.3].
    Returns None if passed, or GateResult if failed."""

    if p_code == "C":
        if pd.isna(last['SMA_200']) or last['SMA_200'] == 0:
            _diag = "REJECT (reason: DATA INTEGRITY). Invalid SMA_200 for Floor Proximity Audit."
            return GateResult(
                verdict="INVALID",
                reason="DATA INTEGRITY",
                mandate="Floor Proximity Audit failed. SMA 200 unavailable.",
                context="Invalid SMA_200 for Floor Proximity Audit.",
                legacy_diagnostic=_diag,
            )
        if floor_prox_pct > 15.0:
            _diag = f"REJECT (reason: FLOOR PROXIMITY FAILED). FLOOR PROXIMITY FAILED (Profile C): {floor_prox_pct:.2f}% > 15.0%."
            return GateResult(
                verdict="INVALID",
                reason="FLOOR PROXIMITY FAILED",
                mandate="Asset disqualified. Floor proximity exceeds 15% threshold.",
                context=f"FLOOR PROXIMITY FAILED (Profile C): {floor_prox_pct:.2f}% > 15.0%.",
                legacy_diagnostic=_diag,
            )
    return None  # Gate passed


def _gate_expectancy(p_code, risk_a, reward_a, cons_high_raw, last_close,
                     floor_price, price_scaler):
    """Gate 5.6 — Expectancy Gate (Profile A) [Doc 2 Sec 4.3 / P032 / P038].
    Returns None if passed, or (status, diagnostic) if failed."""
    if p_code == "A":
        if risk_a == 0:
            pass  # Floor-exact entry: R:R already validated by PE-CAL-2. Gate passes.
        elif reward_a < (2.0 * risk_a):
            if reward_a <= 0:
                reason = (
                    f"Price {round(last_close / price_scaler, 2)} has already exceeded "
                    f"Consolidation High {cons_high_raw / price_scaler:.2f} -- no reward remaining. "
                    f"Mandate: WAIT for pullback to VWAP ({floor_price}) before re-evaluating."
                )
            else:
                reason = (
                    f"Reward {reward_a / price_scaler:.2f} < 2x Risk {risk_a / price_scaler:.2f}. "
                    f"Consolidation High {cons_high_raw / price_scaler:.2f} too close to entry. "
                    f"Mandate: WAIT for pullback to VWAP ({floor_price})."
                )
            _diag = f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY GATE FAILED (Profile A): {reason}"
            return GateResult(
                verdict="INVALID",
                reason="EXPECTANCY FAILED",
                mandate=f"WAIT for pullback to VWAP ({floor_price}).",
                context=f"EXPECTANCY GATE FAILED (Profile A): {reason}",
                legacy_diagnostic=_diag,
            )
    return None  # Gate passed


def _gate_capital_expectancy(p_code, risk_a, cons_high_raw, last_close,
                             hard_stop_raw, resistance_raw, atr_raw,
                             price_scaler, metrics):
    """CEG-001 — Capital Expectancy Gate [Spec Section 2.1].
    Returns None if passed, or (status, diagnostic) if failed."""
    _capital_rr = None
    _reward_label = None

    if p_code == "A" and risk_a >= (0.20 * atr_raw):
        _capital_reward = cons_high_raw - last_close
        _capital_risk   = last_close - hard_stop_raw
        if _capital_risk > 0 and _capital_reward > 0:
            _capital_rr = _capital_reward / _capital_risk
            metrics["Capital_Reward_Risk"] = round(_capital_rr, 2)
            if _capital_rr < 1.0:
                _diag = (
                    f"REJECT (reason: CAPITAL EXPECTANCY FAILED). CAPITAL EXPECTANCY FAILED: Capital R:R {round(_capital_rr, 2)} "
                    f"-- reward ${round(_capital_reward / price_scaler, 2)} vs. "
                    f"stop risk ${round(_capital_risk / price_scaler, 2)}. Minimum: 1.0."
                )
                return GateResult(
                    verdict="INVALID",
                    reason="CAPITAL EXPECTANCY FAILED",
                    mandate="Capital R:R below 1.0 minimum. Insufficient reward for stop risk.",
                    context=f"CAPITAL EXPECTANCY FAILED: Capital R:R {round(_capital_rr, 2)} -- reward ${round(_capital_reward / price_scaler, 2)} vs. stop risk ${round(_capital_risk / price_scaler, 2)}. Minimum: 1.0.",
                    legacy_diagnostic=_diag,
                )
            elif _capital_rr < 1.5:
                _reward_label = "NARROW"
            else:
                _reward_label = "HEALTHY"
            metrics["Capital_RR_Label"] = _reward_label
        elif _capital_risk > 0:
            # Reward <= 0: no upside remaining (already handled by Gate 5.6 in most
            # cases, but write metric for completeness)
            _capital_rr = 0.0
            metrics["Capital_Reward_Risk"] = 0.0
            metrics["Capital_RR_Label"] = None
        else:
            # capital_risk <= 0: stop above price (floor broken state)
            metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = None
    elif p_code == "A":
        # PE-CAL-2 handled this case (risk_a < 20% ATR).
        # Capital R:R is still computable for dashboard visibility.
        _capital_reward = cons_high_raw - last_close
        _capital_risk   = last_close - hard_stop_raw
        if _capital_risk > 0 and _capital_reward > 0:
            _capital_rr = _capital_reward / _capital_risk
            metrics["Capital_Reward_Risk"] = round(_capital_rr, 2)
            if _capital_rr < 1.5:
                _reward_label = "NARROW"
            else:
                _reward_label = "HEALTHY"
            metrics["Capital_RR_Label"] = _reward_label
        else:
            metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = None
    elif p_code == "B":
        # Profile B: compute Capital_Reward_Risk for transparency, no gate.
        # [PE-39] EXIT guard: reinforce PE-7 suppression when EXIT active.
        if metrics.get("Exit_Signal") != "EXIT":
            _capital_reward_b = resistance_raw - last_close
            _capital_risk_b   = last_close - hard_stop_raw
            if _capital_risk_b > 0 and _capital_reward_b > 0:
                _capital_rr_b = _capital_reward_b / _capital_risk_b
                metrics["Capital_Reward_Risk"] = round(_capital_rr_b, 2)
                _capital_rr = _capital_rr_b  # for diagnostic label
                if _capital_rr_b < 1.0:
                    _reward_label = "INSUFFICIENT"
                elif _capital_rr_b < 1.5:
                    _reward_label = "NARROW"
                else:
                    _reward_label = "HEALTHY"
            else:
                metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = _reward_label  # CEG-002: write label on Profile B
        else:
            # EXIT active — reinforce PE-7 suppression
            metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = None
    else:
        # Profile C: not applicable
        metrics["Capital_Reward_Risk"] = None
        metrics["Capital_RR_Label"] = None

    return None  # Gate passed
