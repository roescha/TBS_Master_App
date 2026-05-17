import pandas as pd
from tbs_engine.helpers import _evaluate_floor_failure_context
from tbs_engine.types import GateResult

__all__ = ['_gate_context_regime', '_gate_liquidity', '_gate_data_integrity', '_gate_floor_failure', '_gate_floor_violation', '_gate_floor_violation_active', '_gate_climax', '_gate_midrange', '_gate_directional', '_gate_modifier_e', '_gate_window', '_assess_tq_override', '_gate_extension', '_gate_floor_proximity_c', '_gate_expectancy', '_gate_capital_expectancy', '_select_recovery_target', '_gate_recovery_r1', '_gate_recovery_r3', '_gate_recovery_r4', '_gate_recovery_r5', '_gate_volatility_regime']
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

            # [FA-001] Context frame EMA 8/21 extraction -- Profile A (daily)
            if 'EMA_8' in df_ctx.columns and 'EMA_21' in df_ctx.columns:
                _ctx_ema8 = _ctx_last.get('EMA_8')
                _ctx_ema21 = _ctx_last.get('EMA_21')
                if _ctx_ema8 is not None and not pd.isna(_ctx_ema8):
                    metrics["Context_EMA_8"] = round(float(_ctx_ema8) / price_scaler, 2)
                else:
                    metrics["Context_EMA_8"] = None
                if _ctx_ema21 is not None and not pd.isna(_ctx_ema21):
                    metrics["Context_EMA_21"] = round(float(_ctx_ema21) / price_scaler, 2)
                else:
                    metrics["Context_EMA_21"] = None
                if metrics["Context_EMA_8"] is not None and metrics["Context_EMA_21"] is not None:
                    metrics["Context_EMA_Stacked"] = bool(_ctx_ema8 > _ctx_ema21)
                    if _ctx_ema8 > _ctx_ema21:
                        metrics["Context_EMA_Bias"] = "BULLISH"
                        metrics["Context_EMA_Bias_Desc"] = "Daily EMA 8 above Daily EMA 21"
                    elif _ctx_ema8 < _ctx_ema21:
                        metrics["Context_EMA_Bias"] = "BEARISH"
                        metrics["Context_EMA_Bias_Desc"] = "Daily EMA 8 below Daily EMA 21"
                    else:
                        metrics["Context_EMA_Bias"] = "NEUTRAL"
                        metrics["Context_EMA_Bias_Desc"] = "Daily EMA 8 equal to Daily EMA 21"
                else:
                    metrics["Context_EMA_Stacked"] = None
                    metrics["Context_EMA_Bias"] = None
                    metrics["Context_EMA_Bias_Desc"] = None
            else:
                metrics["Context_EMA_8"] = None
                metrics["Context_EMA_21"] = None
                metrics["Context_EMA_Stacked"] = None
                metrics["Context_EMA_Bias"] = None
                metrics["Context_EMA_Bias_Desc"] = None

            # [EMA50-001] Context frame EMA 50 extraction -- Profile A (daily).
            # Parallel to SMA 50 slope extraction above (lines 38-44).
            # Strictly informational; not a gate input.
            if 'EMA_50' in df_ctx.columns and not pd.isna(_ctx_last['EMA_50']) and len(df_ctx) >= 2 and not pd.isna(df_ctx['EMA_50'].iloc[-2]):
                metrics["Context_Daily_EMA_50_Slope"] = round(float(_ctx_last['EMA_50'] - df_ctx['EMA_50'].iloc[-2]) / price_scaler, 2)
                metrics["Context_Daily_EMA_50"]       = round(float(_ctx_last['EMA_50']) / price_scaler, 2)
            else:
                metrics["Context_Daily_EMA_50_Slope"] = None
                metrics["Context_Daily_EMA_50"]       = None

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
            metrics["Context_EMA_8"]             = None
            metrics["Context_EMA_21"]            = None
            metrics["Context_EMA_Stacked"]       = None
            metrics["Context_EMA_Bias"]          = None
            metrics["Context_EMA_Bias_Desc"]     = None
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
                metrics["Context_Weekly_SMA200"]          = None     # [WKC-002]
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
            # [WKC-002 hotfix] Wrap with float() for parity with Profile A daily
            # and Profile C monthly extraction patterns. Without float(), the
            # numpy.float64 from pandas Series propagates through arithmetic and
            # comparisons, producing numpy.bool which crashes json.dumps.
            slope_value = round(float(current_weekly_sma50 - prior_weekly_sma50) / price_scaler, 2)

            metrics["Context_Weekly_SMA50_Slope"]  = slope_value
            metrics["Context_Weekly_SMA50_Rising"] = weekly_sma50_rising
            metrics["Context_Weekly_SMA50"]        = round(float(current_weekly_sma50) / price_scaler, 2)

            # [FFD-001] Higher-frame context enrichment — Profile B (weekly)
            # Written on ALL evaluations for Operator auditability (DQ-5).
            _ctx_last_b = df_ctx.iloc[-1]
            if 'SMA_200' in df_ctx.columns and not pd.isna(_ctx_last_b['SMA_200']):
                metrics["Context_Weekly_Golden_Cross"]    = bool(_ctx_last_b['SMA_50'] > _ctx_last_b['SMA_200'])
                metrics["Context_Weekly_Price_vs_SMA200"] = round(float(_ctx_last_b['close'] - _ctx_last_b['SMA_200']) / price_scaler, 2)
                # [WKC-002] Weekly SMA 200 absolute value -- parity with Context_SMA200 (Profile A) and Context_Monthly_SMA200 (Profile C).
                # Required input for Profile B higher_frame stage classification.
                metrics["Context_Weekly_SMA200"]          = round(float(_ctx_last_b['SMA_200']) / price_scaler, 2)
            else:
                metrics["Context_Weekly_Golden_Cross"]    = None
                metrics["Context_Weekly_Price_vs_SMA200"] = None
                metrics["Context_Weekly_SMA200"]          = None

            # [FA-001] Context frame EMA 8/21 extraction -- Profile B (weekly)
            if 'EMA_8' in df_ctx.columns and 'EMA_21' in df_ctx.columns:
                _ctx_ema8_b = _ctx_last_b.get('EMA_8')
                _ctx_ema21_b = _ctx_last_b.get('EMA_21')
                if _ctx_ema8_b is not None and not pd.isna(_ctx_ema8_b):
                    metrics["Context_EMA_8"] = round(float(_ctx_ema8_b) / price_scaler, 2)
                else:
                    metrics["Context_EMA_8"] = None
                if _ctx_ema21_b is not None and not pd.isna(_ctx_ema21_b):
                    metrics["Context_EMA_21"] = round(float(_ctx_ema21_b) / price_scaler, 2)
                else:
                    metrics["Context_EMA_21"] = None
                if metrics["Context_EMA_8"] is not None and metrics["Context_EMA_21"] is not None:
                    metrics["Context_EMA_Stacked"] = bool(_ctx_ema8_b > _ctx_ema21_b)
                    if _ctx_ema8_b > _ctx_ema21_b:
                        metrics["Context_EMA_Bias"] = "BULLISH"
                        metrics["Context_EMA_Bias_Desc"] = "Weekly EMA 8 above Weekly EMA 21"
                    elif _ctx_ema8_b < _ctx_ema21_b:
                        metrics["Context_EMA_Bias"] = "BEARISH"
                        metrics["Context_EMA_Bias_Desc"] = "Weekly EMA 8 below Weekly EMA 21"
                    else:
                        metrics["Context_EMA_Bias"] = "NEUTRAL"
                        metrics["Context_EMA_Bias_Desc"] = "Weekly EMA 8 equal to Weekly EMA 21"
                else:
                    metrics["Context_EMA_Stacked"] = None
                    metrics["Context_EMA_Bias"] = None
                    metrics["Context_EMA_Bias_Desc"] = None
            else:
                metrics["Context_EMA_8"] = None
                metrics["Context_EMA_21"] = None
                metrics["Context_EMA_Stacked"] = None
                metrics["Context_EMA_Bias"] = None
                metrics["Context_EMA_Bias_Desc"] = None

            # [EMA50-001] Context frame EMA 50 extraction -- Profile B (weekly).
            # Parallel to weekly SMA 50 slope extraction above.
            # Strictly informational; not a gate input.
            if 'EMA_50' in df_ctx.columns and not pd.isna(_ctx_last_b['EMA_50']) and len(df_ctx) >= 2 and not pd.isna(df_ctx['EMA_50'].iloc[-2]):
                metrics["Context_Weekly_EMA_50_Slope"] = round(float(_ctx_last_b['EMA_50'] - df_ctx['EMA_50'].iloc[-2]) / price_scaler, 2)
                metrics["Context_Weekly_EMA_50"]       = round(float(_ctx_last_b['EMA_50']) / price_scaler, 2)
            else:
                metrics["Context_Weekly_EMA_50_Slope"] = None
                metrics["Context_Weekly_EMA_50"]       = None

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
            metrics["Context_Weekly_SMA200"]          = None     # [WKC-002]
            metrics["Context_EMA_8"]                 = None
            metrics["Context_EMA_21"]                = None
            metrics["Context_EMA_Stacked"]           = None
            metrics["Context_EMA_Bias"]              = None
            metrics["Context_EMA_Bias_Desc"]         = None
            # [EMA50-001] None-fallback for Profile B EMA 50 keys
            metrics["Context_Weekly_EMA_50_Slope"]   = None
            metrics["Context_Weekly_EMA_50"]         = None
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
                        state=None, df_ctx=None, metrics=None, _ff_threshold=4,
                        price_scaler=1.0):
    """Gate 1 — Floor Failure [Doc 2 Sec 4.1] + FFD-001 BREACH/FAILURE bifurcation.

    When state and df_ctx are provided, evaluates composite conditions to
    distinguish FLOOR BREACH (WAIT/WARNING) from FLOOR FAILURE (REJECT/EXIT).
    Without state/df_ctx, falls back to original FLOOR FAILURE behaviour.

    Returns None if passed, or (status, diagnostic) if failed."""
    if is_floor_failure:
        # --- FFD-001: Composite check ---
        if state is not None and metrics is not None:
            is_breach, context_label, failing_conds = _evaluate_floor_failure_context(
                state, df_ctx, p_code, price_scaler=price_scaler
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
            f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above {floor_price}."
        )
        return GateResult(
            verdict="INVALID",
            reason="FLOOR WARNING ACTIVE",
            mandate=f"HARD WAIT. Entry only valid on confirmed reclaim close above {floor_price}.",
            context=f"FLOOR WARNING ACTIVE: {consec_below}/{_ff_threshold} consecutive bars below Floor ({floor_price}). Current bar has NOT reclaimed (Close {round(last_close / price_scaler, 2)} < Floor {floor_price}).",
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
    #   3. Vol_Confirm = STRONG ACCUMULATION (ratio > 0.7)
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
        _ov_vol          = vol_confirm_state == "STRONG ACCUMULATION"
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
                "eligible": True,
                "conditions_met": (
                    f"TRENDING + ACCELERATING (ADX_Accel {adx_accel}) + "
                    f"STRONG_VOL ({vol_confirm_ratio}) + "
                    f"Extension {atr_dist:.2f} <= {_ceil} ceiling + "
                    f"Override R:R {_ov_rr} >= 0.5 (Target {_ov_target})"
                ),
                "override_terms": (
                    f"50% unit | Stop: {_tight_stop} (Floor - 1.0 ATR) | "
                    f"Target: {_ov_target} (Resistance -- mandatory exit)"
                ),
                "tight_stop": _tight_stop,
                "override_target": _ov_target,
                "override_rr": _ov_rr,
                "note": (
                    "OPERATOR DISCRETION: All 6 conditions met. Override permitted "
                    "under reduced sizing and tightened risk. This is NOT a standard PASS."
                )
            }
        else:
            # Build rejection reason(s)
            _ov_fails = []
            if not _ov_trending:    _ov_fails.append("Engine State not TRENDING (MA stack incomplete)")
            if not _ov_accel:       _ov_fails.append(f"ADX not ACCELERATING ({adx_accel_state})")
            if not _ov_vol:         _ov_fails.append(f"Volume not STRONG ACCUMULATION ({vol_confirm_state})")
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
                "eligible": False,
                "reason": "; ".join(_ov_fails),
                "note": "Extension rejection is protective. Do not chase."
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
            "eligible": False,
            "reason": f"Override ineligible: {_inelig_reason}",
            "note": "Extension rejection is protective. Do not chase."
        }


def _gate_extension(ctx, atr_dist, ext_limit, daily_ext_dist=None):
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
    _is_breakout_bar = (last['close'] > resistance_raw) if p_code in ("A", "B") else False
    _effective_ext = 1.5 if (_is_breakout_bar and not is_trending and (_entry_resolving or getattr(ctx, '_sbo_prestate', False))) else ext_limit
    # BKOUT-001 FIX (GAP-1): Surface effective extension limit when exemption active
    if _effective_ext != ext_limit:
        metrics["Extension_Limit_Effective"] = _effective_ext
        metrics["Extension_Exemption_Note"] = (
            f"Breakout Extension Exemption (PE-CAL-1 Sec 6.2): "
            f"limit widened from {ext_limit} to {_effective_ext} ATR on RESOLVING breakout bar"
        )
    # AVWAP-001 DQ-4: Intraday extension gate RETIRED for Profile A.
    # PA-001 daily extension gate (below) is the sole overextension check.
    # Belt-and-suspenders: ext_limit_trending/resolving set to 99.0 in _build_config
    # guarantees atr_dist > _effective_ext is never True, but we also skip explicitly.
    if p_code == "A":
        pass  # Skip intraday extension check entirely for Profile A
    elif atr_dist > _effective_ext and not (p_code == "B" and not is_etf and not (is_trending or is_resolving)):
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

    # PA-001: Daily extension check (Profile A only)
    if p_code == "A" and daily_ext_dist is not None:
        if daily_ext_dist > 3.0:
            # EXHAUSTION — hard REJECT
            metrics['Daily_Extension_Distance'] = round(daily_ext_dist, 2)
            metrics['Daily_Extension_Label'] = 'EXHAUSTION'
            _d_rsi = metrics.get("Daily_RSI")
            _rsi_cond = "OVERBOUGHT" if (_d_rsi or 0) > 70 else ("OVERSOLD" if (_d_rsi or 50) < 30 else "NEUTRAL")
            return GateResult(
                verdict="INVALID",
                reason="DAILY EXTENSION",
                legacy_diagnostic="REJECT: Daily extension {:.1f}x ATR (> 3.0x EXHAUSTION)".format(daily_ext_dist),
                mandate="REJECT. Daily extension exceeds 3.0x ATR exhaustion threshold.",
                context={
                    "daily_ext_atr": round(daily_ext_dist, 2),
                    "threshold_atr": 3.0,
                    "daily_rsi": round(_d_rsi, 2) if _d_rsi is not None else None,
                    "rsi_condition": _rsi_cond if _d_rsi is not None else None,
                },
            )
        elif daily_ext_dist > 2.0:
            # CAUTION — advisory, write to metrics but do NOT block
            metrics['Daily_Extension_Distance'] = round(daily_ext_dist, 2)
            metrics['Daily_Extension_Label'] = 'CAUTION'
        else:
            metrics['Daily_Extension_Distance'] = round(daily_ext_dist, 2)
            metrics['Daily_Extension_Label'] = 'NORMAL'

    # PA-001 DQ-11: Profile B medium-term overextension (% from SMA 50)
    if p_code == "B":
        _sma50_raw = ctx.structural_floor_raw  # SMA 50 for Profile B
        if _sma50_raw and _sma50_raw > 0:
            _pct_above_sma50 = ((last['close'] - _sma50_raw) / _sma50_raw) * 100

            if _pct_above_sma50 > 25.0:
                # EXHAUSTION — hard REJECT
                metrics['MediumTerm_Extension_Pct'] = round(_pct_above_sma50, 2)
                metrics['MediumTerm_Extension_Label'] = 'EXHAUSTION'
                return GateResult(
                    verdict="INVALID",
                    reason="MEDIUM-TERM OVEREXTENSION",
                    legacy_diagnostic="REJECT: {:.1f}% above SMA 50 (> 25% EXHAUSTION)".format(_pct_above_sma50),
                    mandate="REJECT. Price exceeds 25% above SMA 50 medium-term exhaustion threshold.",
                    context={
                        "pct_above_sma50": round(_pct_above_sma50, 2),
                        "threshold_pct": 25.0,
                        "sma50_price": round(_sma50_raw / ctx.price_scaler, 2),
                    },
                )
            elif _pct_above_sma50 > 15.0:
                # CAUTION — advisory, write to metrics but do NOT block
                metrics['MediumTerm_Extension_Pct'] = round(_pct_above_sma50, 2)
                metrics['MediumTerm_Extension_Label'] = 'CAUTION'
            else:
                metrics['MediumTerm_Extension_Pct'] = round(_pct_above_sma50, 2)
                metrics['MediumTerm_Extension_Label'] = 'NORMAL'

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
                    f"Mandate: WAIT for pullback to entry zone ({floor_price}) before re-evaluating."
                )
            else:
                reason = (
                    f"Reward {reward_a / price_scaler:.2f} < 2x Risk {risk_a / price_scaler:.2f}. "
                    f"Consolidation High {cons_high_raw / price_scaler:.2f} too close to entry. "
                    f"Mandate: WAIT for pullback to entry zone ({floor_price})."
                )
            _diag = f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY GATE FAILED (Profile A): {reason}"
            return GateResult(
                verdict="INVALID",
                reason="EXPECTANCY FAILED",
                mandate=f"WAIT for pullback to entry zone ({floor_price}).",
                context=f"EXPECTANCY GATE FAILED (Profile A): {reason}",
                legacy_diagnostic=_diag,
            )
    return None  # Gate passed


def _gate_capital_expectancy(p_code, risk_a, cons_high_raw, last_close,
                             hard_stop_raw, resistance_raw, atr_raw,
                             price_scaler, metrics, _is_c3=False, ctx=None):
    """CEG-001 / CEG-003 -- Capital Expectancy Gate [Spec Section 2.1].
    CEG-003: Profile B C-1/C-2 enforcement (REJECT on Capital R:R < 1.0).
    C-3 bypasses gate entirely (informational only).
    Returns None if passed, or GateResult if failed."""
    _capital_rr = None
    _reward_label = None

    if p_code == "A" and risk_a >= (0.20 * atr_raw):
        # PA-001: Use daily hard stop as risk denominator for Profile A
        # [BRK-001]: When breakout model active, use catastrophic stop
        # (new support − BRK_CATASTROPHIC_MULTIPLIER × ATR) instead of
        # daily hard stop.  Spec §4.3.
        if ctx is not None and getattr(ctx, '_breakout_model_active', False) is True:
            _pa001_hard_stop = ctx._brk_catastrophic_stop_raw
        else:
            _pa001_hard_stop = ctx.daily_hard_stop if (ctx is not None and ctx.daily_hard_stop > 0) else hard_stop_raw
        _capital_reward = cons_high_raw - last_close
        _capital_risk   = last_close - _pa001_hard_stop
        if _capital_risk > 0 and _capital_reward > 0:
            _capital_rr = _capital_reward / _capital_risk
            metrics["Capital_Reward_Risk"] = round(_capital_rr, 2)
            if _capital_rr < 1.0:
                _reward_label = "INSUFFICIENT"
            elif _capital_rr < 1.5:
                _reward_label = "NARROW"
            else:
                _reward_label = "HEALTHY"
            metrics["Capital_RR_Label"] = _reward_label
            # PA-001: Advisory only — do NOT return GateResult for Profile A
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
        # PA-001: Use daily hard stop as risk denominator
        # [BRK-001]: When breakout model active, use catastrophic stop
        if ctx is not None and getattr(ctx, '_breakout_model_active', False) is True:
            _pa001_hard_stop = ctx._brk_catastrophic_stop_raw
        else:
            _pa001_hard_stop = ctx.daily_hard_stop if (ctx is not None and ctx.daily_hard_stop > 0) else hard_stop_raw
        _capital_reward = cons_high_raw - last_close
        _capital_risk   = last_close - _pa001_hard_stop
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
        # Profile B: Capital Expectancy computation + CEG-003 enforcement.
        # [FRR-001] Fundamental R:R gate (C-1/C-2) when analyst data available.
        # [PE-39] EXIT guard: reinforce PE-7 suppression when EXIT active.
        if metrics.get("Exit_Signal") != "EXIT":
            # --- FRR-001: Fundamental R:R gate (priority 1) ---
            _fund_rr = metrics.get("Fundamental_RR")
            _has_fund = getattr(ctx, '_has_fundamental_data', False) if ctx else False

            if _has_fund and _fund_rr is not None and not _is_c3:
                # C-1/C-2: enforce fundamental R:R >= 2.0
                if _fund_rr < 2.0:
                    _fund_target = metrics.get("Fundamental_Target")
                    _fund_floor = metrics.get("Fundamental_Floor")
                    _diag = (
                        f"REJECT (reason: FUNDAMENTAL EXPECTANCY FAILED). "
                        f"FUNDAMENTAL EXPECTANCY FAILED: Fundamental R:R "
                        f"{_fund_rr} "
                        f"-- analyst median target ${_fund_target} "
                        f"vs. analyst low ${_fund_floor}. "
                        f"Minimum: 2.0."
                    )
                    return GateResult(
                        verdict="INVALID",
                        reason="FUNDAMENTAL EXPECTANCY FAILED",
                        mandate="Fundamental R:R below 2.0 minimum. "
                                "Analyst consensus does not support entry.",
                        context=(
                            f"FUNDAMENTAL EXPECTANCY FAILED: Fundamental R:R "
                            f"{_fund_rr} "
                            f"-- analyst median target ${_fund_target} "
                            f"vs. analyst low ${_fund_floor}. "
                            f"Minimum: 2.0."
                        ),
                        legacy_diagnostic=_diag,
                    )

            # --- Technical R:R (informational when fundamental active, gate when not) ---
            _capital_reward_b = resistance_raw - last_close
            _capital_risk_b   = last_close - hard_stop_raw
            if _capital_risk_b > 0 and _capital_reward_b > 0:
                _capital_rr_b = _capital_reward_b / _capital_risk_b
                metrics["Capital_Reward_Risk"] = round(_capital_rr_b, 2)

                if not _is_c3 and not _has_fund and _capital_rr_b < 1.0:
                    # [CEG-003] Profile B enforcement (C-1/C-2 only, technical fallback)
                    _diag = (
                        f"REJECT (reason: CAPITAL EXPECTANCY FAILED). "
                        f"CAPITAL EXPECTANCY FAILED: Capital R:R "
                        f"{round(_capital_rr_b, 2)} "
                        f"-- reward ${round(_capital_reward_b / price_scaler, 2)} "
                        f"vs. stop risk "
                        f"${round(_capital_risk_b / price_scaler, 2)}. "
                        f"Minimum: 1.0."
                    )
                    return GateResult(
                        verdict="INVALID",
                        reason="CAPITAL EXPECTANCY FAILED",
                        mandate="Capital R:R below 1.0 minimum. "
                                "Insufficient reward for stop risk.",
                        context=(
                            f"CAPITAL EXPECTANCY FAILED: Capital R:R "
                            f"{round(_capital_rr_b, 2)} "
                            f"-- reward ${round(_capital_reward_b / price_scaler, 2)} "
                            f"vs. stop risk "
                            f"${round(_capital_risk_b / price_scaler, 2)}. "
                            f"Minimum: 1.0."
                        ),
                        legacy_diagnostic=_diag,
                    )

                # Gate passed -- write label
                _capital_rr = _capital_rr_b
                if _capital_rr_b < 1.0:
                    _reward_label = "INSUFFICIENT"   # C-3 only reaches here
                elif _capital_rr_b < 1.5:
                    _reward_label = "NARROW"
                else:
                    _reward_label = "HEALTHY"
            elif _capital_reward_b <= 0 and _capital_risk_b > 0:
                # BKOUT-001 FIX (GAP-2): Negative reward -- price above resistance.
                # Attempt weekly ceiling escalation (same mechanism as output.py GAP-3).
                _weekly_target_ceg = None
                _df_ctx_ceg = ctx._df_ctx if hasattr(ctx, '_df_ctx') else None
                if _df_ctx_ceg is not None and len(_df_ctx_ceg) >= 11:
                    _weekly_ceiling_ceg = _df_ctx_ceg['high'].iloc[-11:-1].max()
                elif _df_ctx_ceg is not None:
                    _weekly_ceiling_ceg = _df_ctx_ceg['high'].max()
                else:
                    _weekly_ceiling_ceg = None

                if _weekly_ceiling_ceg is not None and _weekly_ceiling_ceg > last_close:
                    _weekly_reward_ceg = _weekly_ceiling_ceg - last_close
                    _capital_rr_b_esc = _weekly_reward_ceg / _capital_risk_b
                    metrics["Capital_Reward_Risk"] = round(_capital_rr_b_esc, 2)

                    if not _is_c3 and not _has_fund and _capital_rr_b_esc < 1.0:
                        # CEG-003 enforcement against weekly target (technical fallback)
                        _diag = (
                            f"REJECT (reason: CAPITAL EXPECTANCY FAILED). "
                            f"CAPITAL EXPECTANCY FAILED (weekly target): Capital R:R "
                            f"{round(_capital_rr_b_esc, 2)} "
                            f"-- weekly reward ${round(_weekly_reward_ceg / price_scaler, 2)} "
                            f"vs. stop risk "
                            f"${round(_capital_risk_b / price_scaler, 2)}. "
                            f"Minimum: 1.0."
                        )
                        return GateResult(
                            verdict="INVALID",
                            reason="CAPITAL EXPECTANCY FAILED",
                            mandate="Capital R:R below 1.0 minimum (weekly target). "
                                    "Insufficient reward for stop risk.",
                            context=_diag.replace("REJECT (reason: CAPITAL EXPECTANCY FAILED). ", ""),
                            legacy_diagnostic=_diag,
                        )

                    # Gate passed with weekly target
                    _capital_rr = _capital_rr_b_esc
                    if _capital_rr_b_esc < 1.0:
                        _reward_label = "INSUFFICIENT"  # C-3 only
                    elif _capital_rr_b_esc < 1.5:
                        _reward_label = "NARROW"
                    else:
                        _reward_label = "HEALTHY"
                else:
                    # No weekly target available -- no forward ceiling
                    metrics["Capital_Reward_Risk"] = None
                    if not _is_c3 and not _has_fund:
                        # C1/C2: REJECT -- no forward target means unbounded risk
                        _diag = (
                            f"REJECT (reason: NO FORWARD TARGET). "
                            f"Price ({round(last_close / price_scaler, 2)}) above daily resistance "
                            f"({round(resistance_raw / price_scaler, 2)}) and no weekly ceiling available. "
                            f"C1/C2 requires a defined reward target for capital R:R validation."
                        )
                        return GateResult(
                            verdict="INVALID",
                            reason="NO FORWARD TARGET",
                            mandate="No reward target available. Await pullback or state upgrade.",
                            context=_diag.replace("REJECT (reason: NO FORWARD TARGET). ", ""),
                            legacy_diagnostic=_diag,
                        )
                    # C-3: informational only, no enforcement
                    _reward_label = None
            else:
                # capital_risk <= 0: stop above price (floor broken state)
                metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = _reward_label
        else:
            # EXIT active -- reinforce PE-7 suppression
            metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = None
    else:
        # Profile C: not applicable
        metrics["Capital_Reward_Risk"] = None
        metrics["Capital_RR_Label"] = None

    return None  # Gate passed


# ==============================================================================
# REC-001 PHASE 2B — RECOVERY GATE SEQUENCE
# Spec §4.2 (R-Gates), §5.1 (Target Selection), §7.1-7.2 (Regime/CRG bypass)
# ==============================================================================


def _select_recovery_target(current_price, df_ctx, df, p_code, cfg):
    """Select nearest overhead MA as recovery target.

    Target hierarchy (Spec §5.1): SMA 50 → Daily EMA 21 → SMA 200.
    Nearest overhead MA wins.  Returns (target_price, source_label) or (None, None).

    For Profile A: all MAs sourced from df_ctx (daily frame).
    For Profile B: all MAs sourced from df (daily = primary frame).

    REC-001 Phase 2B | Spec §5.1–5.3
    """
    candidates = []

    if p_code == "A":
        # Profile A — daily-frame MAs from df_ctx
        if df_ctx is not None and len(df_ctx) > 0:
            ctx_last = df_ctx.iloc[-1]
            if 'SMA_50' in df_ctx.columns and not pd.isna(ctx_last.get('SMA_50')):
                sma50 = float(ctx_last['SMA_50'])
                if sma50 > current_price:
                    candidates.append((sma50, 'SMA_50'))
            if 'EMA_21' in df_ctx.columns and not pd.isna(ctx_last.get('EMA_21')):
                ema21 = float(ctx_last['EMA_21'])
                if ema21 > current_price:
                    candidates.append((ema21, 'DAILY_EMA_21'))
            if 'SMA_200' in df_ctx.columns and not pd.isna(ctx_last.get('SMA_200')):
                sma200 = float(ctx_last['SMA_200'])
                if sma200 > current_price:
                    candidates.append((sma200, 'SMA_200'))
    else:
        # Profile B — daily-frame MAs from primary df
        eval_idx = len(df) + cfg.iq
        if 'SMA_50' in df.columns and not pd.isna(df['SMA_50'].iloc[eval_idx]):
            sma50 = float(df['SMA_50'].iloc[eval_idx])
            if sma50 > current_price:
                candidates.append((sma50, 'SMA_50'))
        if 'EMA_21' in df.columns and not pd.isna(df['EMA_21'].iloc[eval_idx]):
            ema21 = float(df['EMA_21'].iloc[eval_idx])
            if ema21 > current_price:
                candidates.append((ema21, 'DAILY_EMA_21'))
        if 'SMA_200' in df.columns and not pd.isna(df['SMA_200'].iloc[eval_idx]):
            sma200 = float(df['SMA_200'].iloc[eval_idx])
            if sma200 > current_price:
                candidates.append((sma200, 'SMA_200'))

    if not candidates:
        return None, None

    # Nearest overhead MA wins
    candidates.sort(key=lambda x: x[0])
    return candidates[0]


def _gate_recovery_r1(base_result):
    """R-Gate 1 + R-Gate 2: Base Confirmation + EMA Cross Freshness.

    Pass: All 5 DQ-1 criteria AND EMA 8/21 cross fresh.
    Spec §4.2 R-1, R-2 (combined in implementation per spec note).

    REC-001 Phase 2B | Spec §4.2
    """
    if not base_result['base_confirmed']:
        criteria = base_result['criteria']
        failing = [k for k, v in criteria.items() if not v]
        return GateResult(
            verdict="INVALID",
            reason="BASE NOT CONFIRMED",
            mandate="Recovery base incomplete. Monitor for base completion.",
            context=(f"Recovery base incomplete: {', '.join(failing)}. "
                     f"base_bar_count={base_result['base_bar_count']}, "
                     f"swing_low={base_result['swing_low_price']}, "
                     f"atr_contraction_ratio={base_result['atr_contraction_ratio']}, "
                     f"retest_confirmed={base_result['retest_confirmed']}, "
                     f"ema_cross_bar_index={base_result['ema_cross_bar_index']} vs "
                     f"swing_low_bar_index={base_result['swing_low_bar_index']}"),
        )

    if not base_result['ema_cross_fresh']:
        ecbi = base_result['ema_cross_bar_index']
        slbi = base_result['swing_low_bar_index']
        if ecbi is None:
            _detail = (f"No EMA 8/21 bullish cross detected since swing low at bar {slbi}. "
                       f"Momentum shift not yet confirmed.")
        else:
            _detail = (f"EMA 8/21 cross at bar {ecbi} predates swing low at bar {slbi}. "
                       f"Possible prior failed recovery.")
        return GateResult(
            verdict="INVALID",
            reason="EMA CROSS STALE",
            mandate="EMA 8/21 cross predates swing low. Monitor for fresh cross.",
            context=_detail,
        )

    return None  # PASS


def _gate_recovery_r3(base_result, di_plus_current, di_minus_current):
    """R-Gate 3: DI Spread Narrowing.

    Pass: (di_spread_current < di_spread_at_swing_low) OR (+DI > -DI).
    Handles NaN di_spread_at_swing_low (DI warmup window edge case).

    REC-001 Phase 2B | Spec §4.2 R-3, DQ-4
    """
    di_spread_current = base_result['di_spread_current']
    di_spread_at_sl = base_result['di_spread_at_swing_low']

    # Phase 2A edge case: DI warmup window → di_spread_at_swing_low is NaN
    if pd.isna(di_spread_at_sl):
        if di_plus_current > di_minus_current:
            return None  # PASS: +DI dominant (alternative condition)
        return GateResult(
            verdict="INVALID",
            reason="DI SPREAD NOT NARROWING",
            mandate="Directional balance not improved. DI data at swing low unavailable (warmup).",
            context=(f"DI spread at swing low: NaN (warmup window). "
                     f"+DI ({di_plus_current:.2f}) <= -DI ({di_minus_current:.2f}). "
                     f"Cannot confirm narrowing."),
        )

    # Normal case
    if di_spread_current < di_spread_at_sl or di_plus_current > di_minus_current:
        return None  # PASS

    return GateResult(
        verdict="INVALID",
        reason="DI SPREAD NOT NARROWING",
        mandate="Directional balance has not improved since base formation.",
        context=(f"DI spread {di_spread_current} vs {di_spread_at_sl}. "
                 f"Directional balance has not improved since base formation."),
    )


def _gate_recovery_r4(current_price, swing_low_price, recovery_target,
                       recovery_target_source):
    """R-Gate 4: Capital Expectancy (R:R >= 1.5).

    Uses recovery-specific risk/reward: reward = target - price,
    risk = price - swing_low (hard stop). Threshold: 1.5.

    REC-001 Phase 2B | Spec §4.2 R-4, §5.2
    """
    # §5.3 Edge case: no overhead MA
    if recovery_target is None:
        return GateResult(
            verdict="INVALID",
            reason="NO RECOVERY TARGET",
            mandate="No overhead MA found. Recovery target cannot be established.",
            context=("No overhead MA found. Price above SMA 50, Daily EMA 21, "
                     "and SMA 200. Recovery target cannot be established."),
        )

    reward = recovery_target - current_price
    risk = current_price - swing_low_price

    if risk <= 0:
        return GateResult(
            verdict="INVALID",
            reason="CAPITAL EXPECTANCY FAILED",
            mandate="Invalid risk: price at or below swing low.",
            context=(f"Risk <= 0: price {current_price:.4f} <= "
                     f"swing_low {swing_low_price:.4f}."),
        )

    rr = round(reward / risk, 2)

    if rr >= 1.5:
        return None  # PASS

    return GateResult(
        verdict="INVALID",
        reason="CAPITAL EXPECTANCY FAILED",
        mandate=f"Recovery R:R {rr} below 1.5 threshold.",
        context=(f"Recovery R:R {rr} below 1.5 threshold. "
                 f"Target: {recovery_target:.4f} ({recovery_target_source}), "
                 f"Stop: {swing_low_price:.4f}."),
    )


def _gate_recovery_r5(vol_confirm_state):
    """R-Gate 5: Volume Distribution Check.

    Pass: Vol_Confirm_Ratio NOT in DISTRIBUTION WARNING state.

    REC-001 Phase 2B | Spec §4.2 R-5
    """
    if vol_confirm_state == "DISTRIBUTION WARNING":
        return GateResult(
            verdict="INVALID",
            reason="DISTRIBUTION WARNING",
            mandate="Institutional selling pressure incompatible with recovery entry.",
            context=("Vol_Confirm_Ratio in DISTRIBUTION WARNING state. "
                     "Institutional selling pressure incompatible with recovery entry."),
        )
    return None  # PASS


# ==============================================================================
# IVR-001: IMPLIED VOLATILITY / HISTORICAL VOLATILITY REGIME CONTEXT
# Engine-native advisory gate. Returns PASS unconditionally.
# Spec: IVR001_Volatility_Regime_Context_Spec_v1_0
# ==============================================================================

# Tuneable constants (Spec §3.4)
IVR_COMPLACENT_THRESHOLD = 0.8
IVR_ELEVATED_THRESHOLD = 1.2
IVR_EXTREME_THRESHOLD = 1.5

# Regime descriptions (Spec §3.3 — surfaced in output desc field)
_IVR_REGIME_DESC = {
    "COMPLACENT": (
        "Options market pricing LESS risk than the stock has been delivering. "
        "Rare condition (~15% of observations historically). The market is "
        "underestimating actual price movement."
    ),
    "ALIGNED": (
        "Options market and recent price action agree on volatility magnitude. "
        "IV exceeds HV by a normal insurance premium (2-4 percentage points is "
        "typical -- IV exceeds HV approximately 85% of the time historically). "
        "The current price regime is orderly. No additional volatility risk signal. "
        "Defer to structural assessment from the engine gates."
    ),
    "ELEVATED": (
        "Options market pricing moderately more risk than recent price action justifies."
    ),
    "EXTREME": (
        "Options market pricing significantly more risk than the stock has been delivering. "
        "Strong signal in all contexts. Historically mean-reverting -- extreme readings "
        "normalise within days, aligning with Profile A swing trade horizons (2-5 day holds)."
    ),
    "UNAVAILABLE": (
        "Implied volatility data not available. Possible causes: non-optionable stock, "
        "newly listed ticker, illiquid options chain, or IBKR tick 106 not populated "
        "(can occur after hours on otherwise-liquid options chains). Volatility regime "
        "context cannot be computed."
    ),
}

# Context interpretation matrix (Spec §4 — 5 contexts × 4 regimes = 20 labels)
_IVR_INTERPRETATION = {
    # §4.1 At Extension (CAUTION or EXHAUSTION)
    ("EXTENSION", "COMPLACENT"): {
        "label": "CONTINUATION SUPPORT",
        "desc": (
            "Options market pricing less risk than realised despite elevated price distance "
            "from anchor. The move is not generating fear in the options market. Supports "
            "continuation of the trend -- the extension may be sustainable, especially if "
            "driven by a structural catalyst (index inclusion, sector rotation, earnings beat)."
        ),
    },
    ("EXTENSION", "ALIGNED"): {
        "label": "ORDERLY EXTENSION",
        "desc": (
            "Options market and price action agree on volatility magnitude at the extended "
            "level. The extension is acknowledged but not feared. Normal insurance premium. "
            "Defer to the engine extension gate assessment."
        ),
    },
    ("EXTENSION", "ELEVATED"): {
        "label": "REVERSAL RISK AT EXTENSION",
        "desc": (
            "Options market pricing moderately more risk than realised at an already-extended "
            "level. Early warning: the options market may be seeing reversal risk that the "
            "chart does not yet show. Smart money may be accumulating protective positions. "
            "Exercise additional caution on new entries."
        ),
    },
    ("EXTENSION", "EXTREME"): {
        "label": "DANGER AT EXTENSION",
        "desc": (
            "Options market pricing significantly more risk than realised at an extended level. "
            "Strong warning: smart money is likely hedging against a reversal. The combination "
            "of structural overextension (engine) and fear-level volatility premium (options) "
            "is the highest-risk configuration. Avoid new entries. If already holding, consider "
            "tightening stops."
        ),
    },
    # §4.2 At Pullback (PULLBACK trigger, near structural floor)
    ("PULLBACK", "COMPLACENT"): {
        "label": "CALM PULLBACK",
        "desc": (
            "Options market pricing less risk than realised near the structural floor. The "
            "pullback is orderly with no panic. No capitulation signal. Standard mean-reversion "
            "entry conditions -- the setup relies on structural floor integrity, not on "
            "contrarian fear."
        ),
    },
    ("PULLBACK", "ALIGNED"): {
        "label": "NORMAL CONDITIONS",
        "desc": (
            "Options market and price action agree on volatility magnitude at the pullback "
            "level. Normal conditions. No additional signal from the options market. Defer to "
            "structural assessment (floor integrity, THS, R:R)."
        ),
    },
    ("PULLBACK", "ELEVATED"): {
        "label": "CAPITULATION SUPPORT",
        "desc": (
            "Options market pricing moderately more risk than realised near the structural "
            "floor. Contrarian-supportive: elevated fear at structural support often marks "
            "capitulation. Research shows high VRP environments historically favour equity "
            "exposure because the market prices more pessimism than typically materialises. "
            "Higher-quality pullback entry than ALIGNED."
        ),
    },
    ("PULLBACK", "EXTREME"): {
        "label": "STRONG CAPITULATION",
        "desc": (
            "Options market pricing significantly more risk than realised near the structural "
            "floor. Extreme fear at support -- highest-asymmetry entry if the floor holds. "
            "The market is pricing a structural breakdown that may not materialise. VRP "
            "compression alone generates positive return as IV normalises over the swing hold "
            "period. Strongest contrarian signal available from the options market."
        ),
    },
    # §4.3 At Breakout (BREAKOUT / SWING_BREAKOUT trigger)
    ("BREAKOUT", "COMPLACENT"): {
        "label": "HIGH QUALITY BREAKOUT",
        "desc": (
            "Options market pricing less risk than realised at the breakout level. Dealers "
            "are not positioned for this move. As the breakout progresses, dealers must hedge "
            "by buying the underlying, creating mechanical follow-through buying pressure. "
            "This is the highest-quality breakout confirmation from the options market -- "
            "the move is catching participants off guard."
        ),
    },
    ("BREAKOUT", "ALIGNED"): {
        "label": "ORDERLY BREAKOUT",
        "desc": (
            "Options market and price action agree on volatility magnitude at the breakout. "
            "The move is not surprising the options market. Neutral signal -- defer to volume "
            "confirmation and structural assessment."
        ),
    },
    ("BREAKOUT", "ELEVATED"): {
        "label": "PARTIALLY PRICED IN",
        "desc": (
            "Options market pricing moderately more risk than realised. The breakout may "
            "already be anticipated by options traders. Follow-through could be limited as "
            "hedging demand was front-loaded. Not disqualifying but the entry has less "
            "mechanical tailwind than ALIGNED or COMPLACENT."
        ),
    },
    ("BREAKOUT", "EXTREME"): {
        "label": "HEAVILY PRICED IN",
        "desc": (
            "Options market pricing significantly more risk than realised at the breakout. "
            "The move is heavily anticipated -- options traders are already positioned for "
            "large movement. Mechanical follow-through from dealer hedging is likely exhausted. "
            "Caution: the breakout event itself may be the catalyst that triggers IV "
            "normalisation (the classic post-event volatility crush), which removes the tailwind."
        ),
    },
    # §4.4 At Recovery (REC-001 base formation)
    ("RECOVERY", "COMPLACENT"): {
        "label": "ORDERLY BASE",
        "desc": (
            "Options market pricing less risk than realised during base formation. The market "
            "views the basing action as orderly, not distressed. Low-uncertainty recovery -- "
            "standard base quality assessment applies."
        ),
    },
    ("RECOVERY", "ALIGNED"): {
        "label": "STANDARD REGIME",
        "desc": (
            "Options market and price action agree on volatility magnitude during recovery. "
            "Normal conditions for base formation. Defer to recovery gate assessment (base bar "
            "count, ATR contraction, recovery R:R)."
        ),
    },
    ("RECOVERY", "ELEVATED"): {
        "label": "ELEVATED ASYMMETRY",
        "desc": (
            "Options market pricing moderately more risk than realised during base formation. "
            "Higher risk but higher asymmetry -- if the base holds and the recovery triggers, "
            "the VRP compression contributes to positive return as IV normalises. The elevated "
            "uncertainty makes the base test more meaningful."
        ),
    },
    ("RECOVERY", "EXTREME"): {
        "label": "MAXIMUM ASYMMETRY",
        "desc": (
            "Options market pricing significantly more risk than realised during base formation. "
            "Maximum-asymmetry recovery if the base holds. The market is uncertain about the "
            "bottom -- fear is extreme. If the base proves valid, the VRP normalisation alone "
            "generates meaningful return over the recovery hold period. Highest-conviction "
            "recovery signal from the options market, contingent on structural base integrity."
        ),
    },
    # §4.5 Default (TRENDING state, no special context)
    ("DEFAULT", "COMPLACENT"): {
        "label": "LOW VOLATILITY PREMIUM",
        "desc": (
            "Options market pricing less risk than realised in a trending environment. The "
            "trend is not generating hedging demand. Suggests orderly, well-accepted trend "
            "with potential for surprise moves if conditions change."
        ),
    },
    ("DEFAULT", "ALIGNED"): {
        "label": "STANDARD REGIME",
        "desc": (
            "Options market and price action agree on volatility magnitude. Normal trending "
            "conditions. No additional options market signal. Defer entirely to structural "
            "engine assessment."
        ),
    },
    ("DEFAULT", "ELEVATED"): {
        "label": "ELEVATED UNCERTAINTY",
        "desc": (
            "Options market pricing moderately more risk than the trend has been delivering. "
            "The options market sees potential disruption that is not yet visible in price "
            "action. Advisory awareness -- monitor for catalysts (earnings, macro events, "
            "sector rotation)."
        ),
    },
    ("DEFAULT", "EXTREME"): {
        "label": "EXTREME UNCERTAINTY",
        "desc": (
            "Options market pricing significantly more risk than the trend has been delivering. "
            "Strong divergence between orderly price trend and fearful options positioning. "
            "Potential regime change ahead. Exercise caution on new entries and consider "
            "tightening stops on existing positions."
        ),
    },
}


def _gate_volatility_regime(ctx):
    """IVR-001 — IV/HV Volatility Regime Context [Advisory Gate].

    Reads IV_Current and HV_30D from ctx.metrics. Computes ratio, classifies
    into regime band, determines context interpretation from engine state and
    trigger. Writes all metrics. Returns PASS unconditionally.

    Tier 3 parallel execution — runs on both VALID and INVALID paths.
    This gate NEVER returns HALT or REJECT.

    Spec: IVR001_Volatility_Regime_Context_Spec_v1_0 §3-5
    """
    metrics = ctx.metrics
    iv = metrics.get("IV_Current")
    hv = metrics.get("HV_30D")

    # Guard: if either is None or HV is 0, write UNAVAILABLE
    if iv is None or hv is None or hv == 0:
        metrics["IV_HV_Ratio"] = None
        metrics["Volatility_Regime"] = "UNAVAILABLE"
        metrics["Volatility_Interpretation"] = None
        metrics["Volatility_Regime_Desc"] = _IVR_REGIME_DESC["UNAVAILABLE"]
        metrics["Volatility_Interpretation_Desc"] = None
        metrics["Volatility_Caution_Factor"] = None
        return None  # PASS unconditionally

    # Compute ratio
    ratio = round(iv / hv, 4)

    # Classify regime band (Spec §3.3, boundary rules §3.4)
    if ratio < IVR_COMPLACENT_THRESHOLD:
        regime = "COMPLACENT"
    elif ratio < IVR_ELEVATED_THRESHOLD:
        regime = "ALIGNED"
    elif ratio < IVR_EXTREME_THRESHOLD:
        regime = "ELEVATED"
    else:
        regime = "EXTREME"

    # Determine context (Spec §4): read engine state + trigger
    trigger = metrics.get("Trigger", "")
    ext_condition = metrics.get("Daily_Extension_Label") or metrics.get("Extension_Condition")
    recovery_active = (getattr(ctx, '_recovery_base_result', None) is not None)

    if recovery_active:
        context_key = "RECOVERY"
    elif ext_condition in ("CAUTION", "EXHAUSTION"):
        context_key = "EXTENSION"
    elif trigger == "PULLBACK":
        context_key = "PULLBACK"
    elif trigger in ("BREAKOUT", "SWING_BREAKOUT"):
        context_key = "BREAKOUT"
    else:
        context_key = "DEFAULT"

    # Look up interpretation from matrix
    interp = _IVR_INTERPRETATION.get((context_key, regime), {})
    interp_label = interp.get("label", "STANDARD REGIME")
    interp_desc = interp.get("desc", "")

    # Caution factor (Spec §5.2, §6.2): non-null when ELEVATED or EXTREME
    caution_factor = None
    if regime in ("ELEVATED", "EXTREME"):
        _summary = interp_desc.split(". ")[0] + "." if interp_desc else ""
        caution_factor = (
            f"VOLATILITY REGIME: {regime} -- {interp_label}. {_summary}"
        )

    # Write all metrics
    metrics["IV_HV_Ratio"] = ratio
    metrics["Volatility_Regime"] = regime
    metrics["Volatility_Interpretation"] = interp_label
    metrics["Volatility_Regime_Desc"] = _IVR_REGIME_DESC.get(regime, "")
    metrics["Volatility_Interpretation_Desc"] = interp_desc
    metrics["Volatility_Caution_Factor"] = caution_factor

    return None  # PASS unconditionally

