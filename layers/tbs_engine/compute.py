import numpy as np
import pandas as pd
from tbs_engine.types import GRACE_BUFFER_ATR_PCT, GateResult
from tbs_engine.helpers import _assess_floor_state, _deep_reclaim_scan, _evaluate_floor_failure_context

__all__ = ['_compute_morphology', '_compute_vol_confirmation', '_compute_volume_at_price', '_compute_window_binding', '_compute_floor_state', '_compute_early_capital_rr', '_evaluate_precheck', '_compute_recovery_base', '_compute_consolidation_quality', '_detect_breakout_model', '_compute_mm_target_early']

# ======================================================================
# BRK-001: Breakout Entry Architecture Constants
# Post-breakout stop buffer and catastrophic multiplier.
# Calibration candidates — review after 3–6 months live data.
# ======================================================================
BRK_STOP_BUFFER_ATR = 1.0        # ATR multiplier for tight stop below new support (R:R computation, thesis invalidation)
BRK_CATASTROPHIC_MULTIPLIER = 1.5  # ATR multiplier for catastrophic stop below new support (position sizing, gap protection)

# SBO volume threshold (mirrored from trigger.py for breakout detection)
_BRK_SBO_VOLUME_THRESHOLD = 1.5


def _compute_mm_target_early(ctx):
    """BRK-001: Compute Measured Move target early for breakout R:R.

    Extracts the ENG-004 measured move computation so it is available
    before the gate cascade.  The same computation runs again in
    output.py for the final output; this early version provides the
    raw (unscaled) value for R:R arithmetic.

    Returns MM_Target in RAW price units, or None if not computable.
    """
    df = ctx.df
    p_code = ctx.p_code
    state = ctx.state
    bars_per_day = ctx.bars_per_day
    last = ctx.last
    is_etf = ctx.is_etf

    if is_etf:
        return None

    if df is None:
        return None

    if p_code == "B" and state._entry_trending:
        _window = df.iloc[-11:-1]
        _origin = float(_window['low'].min())
        _peak = float(_window['high'].max())
        _rally = _peak - _origin
        if _rally < 1.0 * state.atr_raw or _rally == 0:
            return None
        return last['close'] + _rally  # raw price units

    elif p_code == "A":
        _session_bars = int(bars_per_day * 3)
        _min_bars = int(bars_per_day * 2)
        if len(df) > (_session_bars + 1) and _session_bars >= _min_bars:
            _window = df.iloc[-(_session_bars + 1):-1]
            _origin = float(_window['low'].min())
            _peak = float(_window['high'].max())
            _rally = _peak - _origin
            if _rally < 1.0 * state.atr_raw or _rally == 0:
                return None
            return last['close'] + _rally  # raw price units

    return None


def _detect_breakout_model(ctx, _window_reset_event):
    """BRK-001: Detect whether the breakout evaluation model should activate.

    The breakout model activates when the CURRENT entry opportunity is a
    breakout — either a fresh breakout on the current bar or a historical
    breakout still within the execution window.

    Two detection paths:
      (A) Fresh breakout: close > resistance, DI+>DI-, volume confirmed.
      (B) Stale breakout: execution window shows recent BREAKOUT event,
          window still open, price has NOT pulled back to the entry zone.

    Sets ctx._breakout_model_active, ctx._brk_new_support_raw,
    ctx._brk_mm_target_raw, ctx._brk_tight_stop_raw, ctx._brk_catastrophic_stop_raw.

    Spec §4.7: Trigger binding — flip only on BREAKOUT/SWING_BREAKOUT.
    """
    p_code = ctx.p_code
    last = ctx.last
    state = ctx.state
    resistance_raw = ctx.resistance_raw

    # Default: breakout model inactive
    ctx._breakout_model_active = False
    ctx._brk_new_support_raw = None
    ctx._brk_mm_target_raw = None
    ctx._brk_tight_stop_raw = None
    ctx._brk_catastrophic_stop_raw = None
    # BRK-001-GAP-2: Thesis invalidation defaults (see guard below)
    ctx._breakout_thesis_failed = False
    ctx._brk_failed_new_support = None

    # C-3 bypasses expectancy gate entirely — no breakout model needed
    if ctx._is_c3:
        return

    # Profiles A and B only
    if p_code not in ("A", "B"):
        return

    # ---- Path A: Fresh breakout on current bar ----
    _at_breakout = (
        last['close'] > resistance_raw and
        state.di_plus > state.di_minus
    )
    _fresh = False
    if _at_breakout:
        _vol_sma = last.get('vol_sma_20', 0)
        _rvol = (float(last['volume']) / float(_vol_sma)) if _vol_sma and _vol_sma > 0 else 0.0
        _fresh = _rvol >= _BRK_SBO_VOLUME_THRESHOLD

    # ---- Path B: Stale breakout within execution window ----
    _stale = False
    if not _fresh:
        _wre = _window_reset_event or ""
        _in_window = (ctx.window_count < ctx.window_limit)
        _is_breakout_event = ("BREAKOUT" in _wre)
        # Price NOT in pullback zone — proxy: above ANCHOR + 1 ATR
        # (if price pulled back to floor, pullback model applies per §4.7)
        _not_pulled_back = (last['close'] > (last['ANCHOR'] + state.atr_raw))
        _stale = _in_window and _is_breakout_event and _not_pulled_back

    if not (_fresh or _stale):
        return

    # ------------------------------------------------------------------
    # BRK-001-GAP-2: Thesis validation — bar close must be at or above
    # new support (old resistance).  If close < resistance_raw, the
    # breakout thesis is invalidated: old resistance never converted to
    # new support.  Fall back to standard pullback model.
    #
    # Path A (fresh) already requires close > resistance_raw (line 106),
    # so this guard only fires on Path B (stale breakout with price
    # retracement below the new support level).
    #
    # DQ-1: Bar close comparison only (no intrabar sensitivity).
    # DQ-3: SBO monitor unchanged — breakout event recording is separate
    #        from thesis evaluation.
    # Note: see also _compute_early_capital_rr() tight-stop-breach
    # deactivation — these are complementary, not redundant. This guard
    # catches close < new_support; the other catches close < tight_stop
    # (= new_support − 1.0 ATR).
    # ------------------------------------------------------------------
    if last['close'] < resistance_raw:
        ctx._breakout_thesis_failed = True
        ctx._brk_failed_new_support = resistance_raw
        return  # _breakout_model_active remains False (line 90 default)

    # ---- Compute post-breakout levels ----
    _new_support_raw = resistance_raw  # old resistance = new support
    _atr = state.atr_raw
    _tight_stop_raw = _new_support_raw - BRK_STOP_BUFFER_ATR * _atr
    _catastrophic_stop_raw = _new_support_raw - BRK_CATASTROPHIC_MULTIPLIER * _atr

    # Measured move target (early computation)
    _mm_target_raw = _compute_mm_target_early(ctx)

    # ---- Activate breakout model ----
    ctx._breakout_model_active = True
    ctx._brk_new_support_raw = _new_support_raw
    ctx._brk_mm_target_raw = _mm_target_raw
    ctx._brk_tight_stop_raw = _tight_stop_raw
    ctx._brk_catastrophic_stop_raw = _catastrophic_stop_raw
    ctx._brk_fresh = _fresh  # for downstream diagnostics


# ======================================================================
# RFT-003 Phase 4: Inline Block Extractions from run_tbs_engine
# 6 named functions extracted per spec §III.4 (F4).
# Each receives ctx (RunContext) and returns void or a result tuple.
# ======================================================================


def _compute_morphology(ctx):
    """Compute Modifiers A/B/C/D and active_mods list.

    Writes ctx.prev_high.
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
    # "Previous bar" is one before the evaluated bar: iloc[-cfg.prev_bar_offset].
    prev_high   = df['high'].iloc[-cfg.prev_bar_offset]
    prev_low    = df['low'].iloc[-cfg.prev_bar_offset]

    # [MANDATE: BAR-CLOSE CADENCE] vol_sma_9 must reference the evaluated bar
    # (cfg.iq). For Profile A hourly data, iloc[-1] IS a completed bar (IBKR
    # never returns in-progress hourly bars). PE-43 corrected iq from -2 to -1.
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

    active_mods = []
    if mod_a: active_mods.append("A (Rejection)")
    if mod_b: active_mods.append("B (Ignition)")
    if mod_c: active_mods.append("C (Compression)")

    # --- Progressive ctx update: morphology ---
    ctx.prev_high = prev_high

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
    #   > 0.7  : STRONG ACCUMULATION  -- accumulation dominates
    #   0.4-0.7: MIXED                -- no clear commitment
    #   < 0.4  : DISTRIBUTION WARNING -- selling despite rising price
    #
    # All profiles use cfg.resistance_slice_start:cfg.resistance_slice_end (10-bar window).
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
        "STRONG ACCUMULATION" if vol_confirm_ratio > 0.7 else
        "DISTRIBUTION WARNING" if vol_confirm_ratio < 0.4 else
        "MIXED"
    )

    # --- Progressive ctx update: volume confirmation ---
    ctx.vol_confirm_ratio = vol_confirm_ratio
    ctx.vol_confirm_state = vol_confirm_state


def _compute_volume_at_price(ctx):
    """Compute Volume-at-Price context: PoC from histogram + AVWAP from bars.

    Sets ctx.vol_poc_price, ctx.vol_poc_distance_atr, ctx.vol_poc_position,
    ctx.avwap_price, ctx.avwap_position, ctx.volume_context_label.

    All internal arithmetic uses raw (unscaled) price units to match
    df columns, atr_raw, and IBKR histogram prices. Output prices
    are display-scaled (divided by price_scaler) for operator consumption.

    VOL-001 Spec Section V.2.  BUG FIX: VOL-001-BUG-1 (GBP pence scaling).
    """
    cfg = ctx.cfg
    df = ctx.df
    atr_raw = ctx.state.atr_raw
    price_scaler = ctx.price_scaler
    # actual_price is display-scaled (e.g. pounds). Convert back to raw
    # (e.g. pence) so all arithmetic is in the same unit space as df/atr/histogram.
    actual_price_raw = ctx.actual_price * price_scaler

    # ---- POINT OF CONTROL (from histogram) ----
    histogram_data = ctx.metrics.get("_histogram_data")
    poc_price_raw = None
    poc_distance_atr = None
    poc_position = "UNAVAILABLE"

    if histogram_data and len(histogram_data) >= 3:
        # HistogramData entries have .price and .count attributes
        poc_entry = max(histogram_data, key=lambda h: h.count)
        poc_price_raw = float(poc_entry.price)

        if atr_raw > 0:
            poc_distance_atr = round((actual_price_raw - poc_price_raw) / atr_raw, 2)
            if poc_distance_atr > 0.25:
                poc_position = "ABOVE_POC"
            elif poc_distance_atr < -0.25:
                poc_position = "BELOW_POC"
            else:
                poc_position = "AT_POC"
        else:
            poc_distance_atr = 0.0
            poc_position = "AT_POC"

    # ---- ANCHORED VWAP (from bar data) ----
    _vw_slice = df.iloc[cfg.resistance_slice_start:cfg.resistance_slice_end]
    avwap_price_raw = None
    avwap_position = "AT_AVWAP"  # defensive default

    if 'average' in _vw_slice.columns:
        _vol_sum = _vw_slice['volume'].sum()
        if _vol_sum > 0:
            avwap_price_raw = float(
                (_vw_slice['average'] * _vw_slice['volume']).sum() / _vol_sum
            )
        else:
            # Zero volume across entire window -- use simple mean of close
            avwap_price_raw = float(_vw_slice['close'].mean())
    else:
        # Fallback: typical price if 'average' column missing
        _tp = (_vw_slice['high'] + _vw_slice['low'] + _vw_slice['close']) / 3
        _vol_sum = _vw_slice['volume'].sum()
        if _vol_sum > 0:
            avwap_price_raw = float((_tp * _vw_slice['volume']).sum() / _vol_sum)
        else:
            avwap_price_raw = float(_tp.mean())

    if avwap_price_raw is not None and atr_raw > 0:
        _avwap_dist = (actual_price_raw - avwap_price_raw) / atr_raw
        if _avwap_dist > 0.25:
            avwap_position = "ABOVE"
        elif _avwap_dist < -0.25:
            avwap_position = "BELOW"
        else:
            avwap_position = "AT_AVWAP"
    else:
        _avwap_dist = None

    # ---- VOLUME CONTEXT LABEL (synthesis matrix) ----
    vol_state = ctx.vol_confirm_state
    _at_or_above_poc = poc_position in ("AT_POC", "ABOVE_POC")
    _above_avwap = avwap_position in ("ABOVE", "AT_AVWAP")

    if vol_state == "STRONG ACCUMULATION":
        volume_context_label = "ACCUMULATION DOMINANT"
    elif vol_state == "DISTRIBUTION WARNING":
        if poc_position == "UNAVAILABLE":
            volume_context_label = "DISTRIBUTION ZONE"  # fallback
        elif _at_or_above_poc and _above_avwap:
            volume_context_label = "SUPPORTED ZONE"
        elif _at_or_above_poc and not _above_avwap:
            volume_context_label = "CONTESTED ZONE"
        else:
            volume_context_label = "DISTRIBUTION ZONE"
    elif vol_state == "MIXED":
        if poc_position == "UNAVAILABLE":
            volume_context_label = "NEUTRAL"  # fallback
        elif _at_or_above_poc and _above_avwap:
            volume_context_label = "NEUTRAL -- BUILDING"
        else:
            volume_context_label = "NEUTRAL"
    else:
        volume_context_label = "NEUTRAL"  # defensive

    # ---- VOL-003: AVWAP Distance ATR (surfaced from local to ctx) ----
    _avwap_distance_atr = round(_avwap_dist, 2) if _avwap_dist is not None else None

    # ---- VOL-003: Confluence bias/confidence computation ----
    # Ratio bias
    _ratio_bias = (
        "BULLISH" if vol_state in ("STRONG ACCUMULATION", "ACCUMULATION DOMINANT") else
        "BEARISH" if vol_state == "DISTRIBUTION WARNING" else
        "NEUTRAL"
    )
    # PoC bias
    _poc_bias = (
        "BULLISH" if poc_position == "ABOVE_POC" else
        "BEARISH" if poc_position == "BELOW_POC" else
        "NEUTRAL"
    )
    # AVWAP bias
    _avwap_bias = (
        "BULLISH" if avwap_position == "ABOVE" else
        "BEARISH" if avwap_position == "BELOW" else
        "NEUTRAL"
    )
    # Confidence + net bias (majority vote)
    _bias_votes = [_ratio_bias, _poc_bias, _avwap_bias]
    _bull_count = _bias_votes.count("BULLISH")
    _bear_count = _bias_votes.count("BEARISH")
    if _bull_count == 3 or _bear_count == 3:
        _vol_confidence = "ALIGNED"
    elif _bull_count >= 2 or _bear_count >= 2:
        _vol_confidence = "SPLIT"
    else:
        _vol_confidence = "MIXED"
    _vol_net_bias = (
        "BULLISH" if _bull_count >= 2 else
        "BEARISH" if _bear_count >= 2 else
        "NEUTRAL"
    )
    _vol_bias_detail = f"Ratio {_ratio_bias} + PoC {_poc_bias} + AVWAP {_avwap_bias}"

    # ---- Write to ctx (display-scaled prices) ----
    ctx.vol_poc_price = round(poc_price_raw / price_scaler, 4) if poc_price_raw is not None else None
    ctx.vol_poc_distance_atr = poc_distance_atr
    ctx.vol_poc_position = poc_position
    ctx.avwap_price = round(avwap_price_raw / price_scaler, 4) if avwap_price_raw is not None else None
    ctx.avwap_position = avwap_position
    ctx.avwap_distance_atr = _avwap_distance_atr
    ctx.volume_context_label = volume_context_label
    ctx.vol_bias = _vol_net_bias
    ctx.vol_confidence = _vol_confidence
    ctx.vol_bias_detail = _vol_bias_detail


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
            _tier1_ceiling = df_ctx['high'].iloc[-11:-1].max()
            cons_high_raw = _tier1_ceiling
            # [DSP-003] Preserve the daily Tier 1 value BEFORE any escalation
            # (PE-41 weekly, RWD-001 blue-sky) or downstream BRK-001 MM override.
            # Consumed by transform.py DQ-9 DAILY_HIGH row so the row label
            # ("10-bar daily high from context chart") matches its value on all
            # Profile A paths. Emitted once, here; no subsequent writes.
            metrics["Daily_Cons_High_Pre_Override"] = round(_tier1_ceiling / price_scaler, 2)
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

                # ============================================================
                # [RWD-001] Blue-Sky Tier 3: ATR Projection + MM_Target override
                #
                # When PE-41 Tier 2 has fired AND the escalated ceiling is
                # compressed (< 1.5 ATR headroom), replace the ceiling with
                # an ATR-based projection from the structural floor.  If the
                # ENG-004 measured-move target exceeds the ATR projection,
                # MM_Target wins (RWD-001 §4.1.1).  BRK-001-GAP-3a moved this
                # comparison here from output.py so that Reward_Risk (written
                # below at lines 1194/1270/1277) consumes the final ceiling.
                # ============================================================
                # BRK-001-GAP-3b (S126): source daily ATR from RunContext per RWD-001 §3.2 / §4.1.1.
                # state.atr_raw is primary-frame ATR (hourly on Profile A); ctx.daily_atr is
                # populated in main.py:170 from raw_metrics['Daily_ATR'].
                _atr_daily = ctx.daily_atr
                _tier2_ceiling = cons_high_raw
                _bs_headroom = (_tier2_ceiling - last['close'])
                _is_blue_sky = _bs_headroom < 1.5 * _atr_daily

                if _is_blue_sky and _atr_daily > 0:
                    _floor_raw = last['ANCHOR']
                    _atr_target = _floor_raw + 3.0 * _atr_daily
                    cons_high_raw = _atr_target
                    _profit_target_source = "ATR_PROJECTION (blue sky)"
                    # [BRK-001-GAP-3a] RWD-001 §4.1.1 MM-vs-ATR override.
                    # ctx.mm_target_raw is populated in main.py between
                    # _detect_breakout_model and this call (see types.py
                    # RunContext.mm_target_raw).  Strict > ensures TC-GAP3A-05
                    # boundary behaviour (tie goes to ATR).  getattr fallback
                    # to None keeps minimal-fixture unit tests working — when
                    # no MM_Target is provided, the ATR projection stands.
                    _mm_target_raw = getattr(ctx, 'mm_target_raw', None)
                    if _mm_target_raw is not None and _mm_target_raw > cons_high_raw:
                        cons_high_raw = _mm_target_raw
                        _profit_target_source = "MEASURED_MOVE (blue sky)"
                    # Intermediate state for output.py Blue_Sky_* field population
                    metrics['_rwd001_blue_sky'] = True
                    metrics['_rwd001_atr_target_raw'] = _atr_target
                    metrics['_rwd001_headroom_ratio'] = (
                        _bs_headroom / _atr_daily if _atr_daily > 0 else None
                    )
                else:
                    metrics['_rwd001_blue_sky'] = False
            else:
                _profit_target_source = "DAILY_CTX"
                metrics['_rwd001_blue_sky'] = False
        else:
            cons_high_raw = df['high'].iloc[cfg.resistance_slice_start:cfg.resistance_slice_end].max()
            _profit_target_source = "FALLBACK_HOURLY (context data unavailable)"
            metrics['_rwd001_blue_sky'] = False
            # [DSP-003] No df_ctx available — no daily Tier 1 to preserve.
            # transform.py falls back to Resistance on None; the degraded-path
            # label/value mismatch is scoped to this defensive branch only.
            metrics["Daily_Cons_High_Pre_Override"] = None
        metrics["Cons_High"] = round(cons_high_raw / price_scaler, 2)
        metrics["Profit_Target_Source"] = _profit_target_source

    # --- Progressive ctx update: profit target ---
    ctx.cons_high_raw = cons_high_raw

    # ==================================================================
    # [BRK-001] BREAKOUT MODEL: PROFIT TARGET OVERRIDE
    #
    # When breakout model is active, override cons_high_raw with the
    # measured move target (ENG-004 MM_Target).  This ensures all
    # downstream R:R computations use the post-breakout target.
    #
    # Fallback: if MM_Target is null, retain the PE-41 escalation chain
    # as target (spec §8.1).  Stop model still uses post-breakout new
    # support regardless of target source.
    # ==================================================================
    if getattr(ctx, '_breakout_model_active', False) is True and ctx._brk_mm_target_raw is not None:
        cons_high_raw = ctx._brk_mm_target_raw
        ctx.cons_high_raw = cons_high_raw
        # [BUGR-006-LABEL-2 / ODQ-2(a)] Standardized BRK-001 label vocabulary across both profiles
        _profit_target_source = "MEASURED_MOVE (BRK-001 post-breakout target)"
        if p_code == "A":
            metrics["Cons_High"] = round(cons_high_raw / price_scaler, 2)
            metrics["Profit_Target_Source"] = _profit_target_source
    elif getattr(ctx, '_breakout_model_active', False) is True and ctx._brk_mm_target_raw is None:
        # MM_Target null — fallback per §8.1.  cons_high_raw retains
        # PE-41 escalation chain value.  Log fallback note.
        if _profit_target_source:
            _profit_target_source = _profit_target_source + " (BRK-001 fallback -- measured move unavailable)"
            if p_code == "A":
                metrics["Profit_Target_Source"] = _profit_target_source

    # ======================================================================
    # [BUGR-006 v2.0] PROFILE B BREAKOUT R:R OVERRIDE
    #
    # Writes metrics["Reward_Risk"], metrics["Reward_Risk_Note"],
    # metrics["Profit_Target"], metrics["Profit_Target_Source"] on Profile
    # B BREAKOUT paths. Runs AFTER _detect_breakout_model (main.py:334)
    # per call-order contract documented in spec §4.6. Overwrites the stale
    # values written by _populate_base_metrics (output.py:2153-2237, called
    # at main.py:254 — pre-detection pullback fallback).
    #
    # Spec: BUGR-006 v2.0 §4.3; BRK-001 §4.4, §8.1.
    # ======================================================================
    if p_code == "B" and getattr(ctx, '_breakout_model_active', False) is True:
        _brk_tight = ctx._brk_tight_stop_raw
        _brk_risk = last['close'] - _brk_tight

        # Target selection: MM first (already applied to cons_high_raw at
        # L733-746), then PE-41 weekly ceiling, then RWD-001 ATR projection.
        _brk_target = ctx._brk_mm_target_raw
        _target_source = "MEASURED_MOVE (BRK-001 post-breakout target)"
        _fallback_note = None

        if _brk_target is None:
            # §8.1 fallback 1: weekly 10-bar high from df_ctx
            _df_ctx_b = ctx._df_ctx
            if _df_ctx_b is not None and len(_df_ctx_b) >= 11:
                _wk_ceiling = _df_ctx_b['high'].iloc[-11:-1].max()
                if _wk_ceiling > last['close']:
                    _brk_target = _wk_ceiling
                    _target_source = "WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)"
                    _fallback_note = "MM target unavailable; using weekly 10-bar high"

        if _brk_target is None:
            # §8.1 fallback 2: RWD-001 ATR projection = ANCHOR + 3.0 × daily_atr.
            # Profile B: state.atr_raw IS daily ATR (BRK-001-GAP-3b comment at
            # compute.py:866-869); precedent formula at compute.py:876-877.
            _atr_daily_b = state.atr_raw
            if _atr_daily_b is not None and _atr_daily_b > 0:
                _brk_target = last['ANCHOR'] + 3.0 * _atr_daily_b
                _target_source = "ATR_PROJECTION (BRK-001 §8.1 MM-null fallback)"
                _fallback_note = "MM + weekly unavailable; using RWD-001 ATR projection"

        if _brk_target is not None and _brk_risk > 0:
            _brk_reward = _brk_target - last['close']
            if _brk_reward > 0:
                metrics["Profit_Target"] = round(_brk_target / price_scaler, 2)
                metrics["Profit_Target_Source"] = _target_source
                metrics["Reward_Risk"] = round(_brk_reward / _brk_risk, 2)
                metrics["Expectancy_Threshold"] = 2.0
                metrics["Reward_Risk_Note"] = (
                    f"BREAKOUT MODEL (BRK-001 §4.4): risk = entry - tight stop "
                    f"({round(last['close']/price_scaler, 2)} - {round(_brk_tight/price_scaler, 2)}); "
                    f"reward = target - entry ({round(_brk_target/price_scaler, 2)} - {round(last['close']/price_scaler, 2)})."
                    + (f" Fallback: {_fallback_note}." if _fallback_note else "")
                )
            else:
                # Target at or below entry — no upside
                metrics["Profit_Target"] = None
                metrics["Profit_Target_Source"] = _target_source
                metrics["Reward_Risk"] = None
                metrics["Reward_Risk_Note"] = (
                    "BREAKOUT MODEL: target at or below entry — no upside reward available."
                )
        elif _brk_risk <= 0:
            # Price at or below tight stop — thesis under stress; downstream floor gates handle.
            metrics["Profit_Target"] = None
            metrics["Profit_Target_Source"] = "MEASURED_MOVE (BRK-001 post-breakout target)"
            metrics["Reward_Risk"] = None
            metrics["Reward_Risk_Note"] = (
                "BREAKOUT MODEL: price at or below tight stop; risk denominator ≤ 0. "
                "Downstream floor gates will handle."
            )
        else:
            # _brk_target is None and all fallbacks exhausted (§8.1 terminal case)
            metrics["Profit_Target"] = None
            metrics["Profit_Target_Source"] = "BRK-001 post-breakout (fallbacks exhausted)"
            metrics["Reward_Risk"] = None
            metrics["Reward_Risk_Note"] = (
                "BREAKOUT MODEL: MM target + weekly ceiling + ATR projection all unavailable. "
                "R:R suppressed per §8.1 fallback exhaustion."
            )

    # ==================================================================
    # [FRR-001] FUNDAMENTAL R:R COMPUTATION (Profile B only)
    #
    # When analyst consensus targets are available, compute fundamental
    # reward-risk ratio.  Stores results in metrics for gate enforcement
    # (gates.py) and output (output.py).
    #
    # Priority hierarchy (spec §4.2):
    #   1. Fundamental R:R (analyst data)  → ANALYST_CONSENSUS / INFORMATIONAL
    #   2. Blue-sky ATR projection         → ATR_PROJECTION / PRESCRIPTIVE
    #   3. Weekly-escalated tech R:R       → WEEKLY_RESISTANCE / PRESCRIPTIVE
    #   4. Base technical R:R              → RESISTANCE / PRESCRIPTIVE
    # ==================================================================
    _has_fundamental_data = False
    _has_analyst_levels_data = False  # [DSP-002] NEW

    if p_code == "B":
        _atm = getattr(ctx, '_analyst_target_median', None)
        _atl = getattr(ctx, '_analyst_target_low', None)
        _ath_val = getattr(ctx, '_analyst_target_high', None)
        _acnt = getattr(ctx, '_analyst_count', None)

        # =========================================================
        # [DSP-002] Two-flag decoupling. Compute both flags BEFORE
        # any metric writes (ANALYST-002 / ANALYST-003 ordering
        # discipline — flag must be set before read).
        # =========================================================
        _has_fundamental_data = (                       # existing — UNCHANGED
            _atm is not None
            and _atl is not None
            and _atl < last['close']                     # R:R-denominator validity
            and _atm > _atl
        )

        _has_analyst_levels_data = (                     # [DSP-002 §4.1] NEW
            _atm is not None
            and _atl is not None
            and _atm > _atl
            and _atm > last['close']                     # Upside-validity
        )

        # =========================================================
        # [DSP-002] BLOCK A — Analyst-level metric writes
        # Gated on _has_analyst_levels_data (NEW). Writes the four
        # analyst-level metrics that drive transform.py surfacing:
        #   - analyst_levels JSON block at transform.py:~L1158
        #   - ANALYST_CONSENSUS hierarchy append at transform.py:~L1791-1800
        # =========================================================
        if _has_analyst_levels_data:
            metrics["Fundamental_Target"] = round(_atm, 2)
            metrics["Fundamental_Floor"] = round(_atl, 2)
            metrics["Fundamental_Target_High"] = round(_ath_val, 2) if _ath_val else None
            metrics["Fundamental_Analyst_Count"] = _acnt

        # =========================================================
        # [DSP-002] BLOCK B — R:R metric writes + Profit Target demotion
        # Gated on _has_fundamental_data (existing — UNCHANGED scope).
        # Writes the three R:R metrics consumed by gates.py:~L922-924
        # FRR-001 enforcement and output.py:~L2264 FRR-001 RESTORATION.
        # Profit_Target_Source / Profit_Target_Role demotion preserved
        # per DSP-001 §4.4 "do not touch" (compute-layer audit-trail
        # semantics retained for downstream consumers).
        # =========================================================
        if _has_fundamental_data:
            _fund_reward = _atm - last['close']
            _fund_risk = last['close'] - _atl

            if _fund_risk > 0:
                _fund_rr = round(_fund_reward / _fund_risk, 2)
            else:
                _fund_rr = None  # Degenerate -- suppress

            metrics["Fundamental_RR"] = _fund_rr

            # Label
            if _fund_rr is not None:
                if _fund_rr >= 3.0:
                    metrics["Fundamental_RR_Label"] = "STRONG"
                elif _fund_rr >= 2.0:
                    metrics["Fundamental_RR_Label"] = "MODERATE"
                else:
                    metrics["Fundamental_RR_Label"] = "INSUFFICIENT"
            else:
                metrics["Fundamental_RR_Label"] = None

            # Coverage + dispersion advisory
            _frr_notes = []
            if _acnt is not None and _acnt < 3:
                _frr_notes.append(
                    "Low analyst coverage (%d analyst%s) -- consensus may not be representative."
                    % (_acnt, "s" if _acnt != 1 else "")
                )
            if _ath_val and _atl and _atl > 0:
                _dispersion = _ath_val / _atl
                if _dispersion > 3.0:
                    _frr_notes.append(
                        "High analyst dispersion (high/low ratio %.1fx) -- consensus reliability reduced."
                        % _dispersion
                    )
            metrics["Fundamental_RR_Note"] = " ".join(_frr_notes) if _frr_notes else None

            # Profit target demotion: technical target becomes INFORMATIONAL
            if not getattr(ctx, "_breakout_model_active", False):  # [BUGR-006-LABEL-1] BRK-precedence guard
                metrics["Profit_Target_Source"] = "ANALYST_CONSENSUS"
            metrics["Profit_Target_Role"] = "INFORMATIONAL"

    # Store flags for gates.py + blue-sky guard (existing) and for diagnostic parity (new)
    ctx._has_fundamental_data = _has_fundamental_data
    ctx._has_analyst_levels_data = _has_analyst_levels_data  # [DSP-002] NEW

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

                # ============================================================
                # [FRR-001 / RWD-001] Blue-Sky Tier 3 extension to Profile B
                #
                # Only fires when fundamental data is NOT available (technical
                # fallback chain) AND the weekly ceiling is above price but
                # compressed (< 1.5 ATR headroom).  When fundamental data IS
                # available, the fundamental R:R provides the reward ceiling
                # and blue-sky is skipped.
                # ============================================================
                if not _has_fundamental_data:
                    # BRK-001-GAP-3b (S126): Profile B — state.atr_raw IS the
                    # 14-period daily ATR because Profile B's primary frame is
                    # daily (contrast Profile A at line ~670, which must source
                    # from ctx.daily_atr per BRK-001-GAP-3b).
                    _atr_daily_b = state.atr_raw
                    _tier2_ceiling_b = _early_capital_target
                    _bs_headroom_b = (_tier2_ceiling_b - last['close'])
                    _is_blue_sky_b = _bs_headroom_b < 1.5 * _atr_daily_b

                    if _is_blue_sky_b and _atr_daily_b > 0:
                        _floor_raw_b = last['ANCHOR']
                        _atr_target_b = _floor_raw_b + 3.0 * _atr_daily_b
                        _early_capital_target = _atr_target_b
                        metrics['_rwd001_blue_sky'] = True
                        metrics['_rwd001_atr_target_raw'] = _atr_target_b
                        metrics['_rwd001_headroom_ratio'] = (
                            _bs_headroom_b / _atr_daily_b if _atr_daily_b > 0 else None
                        )
                        if not getattr(ctx, "_breakout_model_active", False):  # [BUGR-006-LABEL-1] BRK-precedence guard
                            metrics["Profit_Target_Source"] = "ATR_PROJECTION (blue sky)"
                    else:
                        metrics['_rwd001_blue_sky'] = False
                else:
                    metrics['_rwd001_blue_sky'] = False
            else:
                if not _has_fundamental_data:
                    metrics['_rwd001_blue_sky'] = False
        else:
            if not _has_fundamental_data:
                metrics['_rwd001_blue_sky'] = False

    # PA-001: Profile A uses daily hard stop as risk denominator
    if p_code == "A" and hasattr(ctx, 'daily_hard_stop') and ctx.daily_hard_stop > 0:
        _early_capital_risk = last['close'] - ctx.daily_hard_stop
    else:
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
                state, ctx._df_ctx, p_code, price_scaler=ctx.price_scaler
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
                    state, ctx._df_ctx, p_code, price_scaler=ctx.price_scaler
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

        # ==============================================================
        # [BRK-001] BREAKOUT MODEL: R:R OVERRIDE
        #
        # When breakout model is active, risk and reward use post-breakout
        # reference points:
        #   risk_a  = entry_price − tight_stop (new support − buffer)
        #   reward_a = target (measured move or fallback) − entry_price
        #
        # The standard pullback R:R (price − floor) / (ceiling − price)
        # is skipped.  Gate logic is unchanged — same 2:1 threshold.
        # Spec §4.4.
        # ==============================================================
        if getattr(ctx, '_breakout_model_active', False) is True:
            _brk_tight = ctx._brk_tight_stop_raw
            reward_a = (cons_high_raw - last['close'])
            risk_a   = (last['close'] - _brk_tight)

            # Breakout risk should be positive (price above tight stop).
            # If negative, breakout thesis is failing — let standard
            # floor gate catch it.
            if risk_a > 0 and reward_a > 0:
                metrics["Reward_Risk"]      = round(reward_a / risk_a, 2)
                metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)
                metrics["Expectancy_Threshold"] = 2.0
                metrics["Expectancy_Threshold_Note"] = None
                metrics["Reward_Risk_Note"] = (
                    f"BREAKOUT MODEL: risk = entry ({round(last['close'] / price_scaler, 2)}) "
                    f"- tight stop ({round(_brk_tight / price_scaler, 2)}). "
                    f"reward = target ({round(cons_high_raw / price_scaler, 2)}) "
                    f"- entry ({round(last['close'] / price_scaler, 2)})."
                )
            elif reward_a <= 0:
                # No upside — target below entry.  Fall through to standard
                # validation (will fail naturally).
                reward_a = (cons_high_raw - last['close'])
                risk_a   = (last['close'] - last['ANCHOR'])
            else:
                # risk_a <= 0: price below tight stop.  Breakout thesis failing.
                # Let standard floor checks handle.
                reward_a = (cons_high_raw - last['close'])
                risk_a   = (last['close'] - last['ANCHOR'])
                ctx._breakout_model_active = False  # deactivate — thesis invalid
        else:
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
                    # PA-001: PE-CAL-3 exempted for Profile A — daily protective
                    # anchor eliminates the VWAP convergence problem.
                    # Floor-exact entry is structurally optimal; write metrics and pass.
                    metrics["Reward_Risk"]      = None
                    metrics["Reward_Risk_Note"] = (
                        "FLOOR_EXACT: price at entry anchor; floor-based R:R undefined. "
                        "PA-001 daily protective anchor provides swing-frame coverage."
                    )
                    metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)
            elif risk_a < (0.20 * state.atr_raw):
                # [PE-CAL-2] Risk denominator is near-zero (< 20% of ATR).
                # PA-001: PE-CAL-3 exempted for Profile A — skip hard-stop substitution.
                # Standard R:R computation proceeds with the small but non-zero risk_a.
                metrics["Reward_Risk"]      = round(reward_a / risk_a, 2)
                metrics["Reward_Risk_Note"] = (
                    f"FLOOR_PROXIMITY: floor-based risk ({round(risk_a / price_scaler, 3)}) < 20% ATR. "
                    f"PA-001: PE-CAL-3 substitution exempted; daily anchor provides protective coverage."
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


# ======================================================================
# REC-001 Phase 2A: Base Detection Algorithm
# Spec §3.1–3.5 | Standalone — consumed by Phase 2B recovery gates
# ======================================================================


def _compute_recovery_base(ctx):
    """Detect swing low, evaluate base window, and return base confirmation result.

    Reads from existing df indicator columns (EMA_8, EMA_21, ATRr_14, DI columns,
    volume, OHLCV). Does not recompute any indicator that already exists.

    Returns a dict consumed by Phase 2B recovery gate sequence.

    REC-001 Phase 2A | Spec §3.1–3.5
    """
    df = ctx.df
    cfg = ctx.cfg
    p_code = ctx.p_code
    eval_idx = len(df) + cfg.iq  # absolute iloc index of evaluated bar (cfg.iq is -1)

    # --- Profile branching (Spec §3.5) ---
    min_base_bars = 5 if p_code == "A" else 3
    # time_stop_limit stored for Phase 2C consumption — NOT used in Phase 2A
    time_stop_limit = 25 if p_code == "A" else 12

    # ------------------------------------------------------------------
    # §3.1 — Swing Low Detection
    # The swing low bar is the bar with the lowest low within the lookback
    # window (the entire primary data window up to the evaluated bar).
    # ------------------------------------------------------------------
    lows = df['low'].iloc[:eval_idx + 1]
    swing_low_iloc = int(lows.idxmin()) if isinstance(lows.index, pd.RangeIndex) else int(lows.values.argmin())
    # Handle datetime index: argmin gives positional index
    swing_low_iloc = int(lows.values.argmin())
    swing_low_price = float(df['low'].iloc[swing_low_iloc])

    # ------------------------------------------------------------------
    # §3.2 — Base Window Definition
    # Base window: [swing_low_iloc, eval_idx] inclusive.
    # ------------------------------------------------------------------
    base_bar_count = eval_idx - swing_low_iloc  # bars SINCE swing low (not including swing low itself)

    # ------------------------------------------------------------------
    # §3.3 — Base Confirmation Criteria (DQ-1): all 5 must pass
    # ------------------------------------------------------------------

    # Criterion 1: Minimum bar count (§3.3 C1)
    crit_min_bars = base_bar_count >= min_base_bars

    # Criterion 2: No new lower low in base window (§3.3 C2)
    # "For every bar i in [swing_low_bar_index + 1, current_bar]: df.iloc[i].low >= swing_low_price"
    if base_bar_count > 0:
        window_lows = df['low'].iloc[swing_low_iloc + 1: eval_idx + 1]
        crit_no_lower_low = bool((window_lows >= swing_low_price).all())
    else:
        crit_no_lower_low = False  # swing low IS the current bar — no base yet

    # Criterion 3: ATR Contraction (§3.3 C3)
    # ATR_base_window = mean true range over base window bars
    # ATR_prior_10 = mean true range over 10 bars immediately preceding swing low
    # atr_contraction_ratio = ATR_base_window / ATR_prior_10. Pass: <= 1.0
    def _mean_true_range(start_iloc, end_iloc):
        """Compute mean true range over df.iloc[start_iloc:end_iloc+1]."""
        if end_iloc <= start_iloc:
            return float('nan')
        sl = df.iloc[start_iloc:end_iloc + 1]
        highs = sl['high'].values
        low_vals = sl['low'].values
        closes_prev = df['close'].iloc[start_iloc - 1:end_iloc].values if start_iloc > 0 else None
        if closes_prev is not None and len(closes_prev) == len(highs):
            tr = [max(h - l, abs(h - cp), abs(l - cp))
                  for h, l, cp in zip(highs, low_vals, closes_prev)]
        else:
            # Fallback: no prior close available for first bar(s)
            tr = [h - l for h, l in zip(highs, low_vals)]
        return sum(tr) / len(tr) if tr else float('nan')

    prior_10_start = max(0, swing_low_iloc - 10)
    prior_10_end = swing_low_iloc - 1
    atr_prior_10 = _mean_true_range(prior_10_start, prior_10_end)

    if base_bar_count > 0:
        atr_base_window = _mean_true_range(swing_low_iloc, eval_idx)
    else:
        atr_base_window = float('nan')

    if atr_prior_10 > 0 and not pd.isna(atr_prior_10) and not pd.isna(atr_base_window):
        atr_contraction_ratio = round(atr_base_window / atr_prior_10, 4)
        crit_atr_contracting = bool(atr_contraction_ratio <= 1.0)
    else:
        atr_contraction_ratio = float('nan')
        crit_atr_contracting = False  # insufficient data — cannot confirm

    # Criterion 4: Retest on Lower Volume (§3.3 C4)
    # Bar whose low is within 0.5 * ATR_14 of swing_low_price AND volume < swing_low_bar volume
    atr_14_current = float(df['ATRr_14'].iloc[eval_idx])
    swing_low_volume = float(df['volume'].iloc[swing_low_iloc])
    retest_confirmed = False
    if base_bar_count > 0:
        for i in range(swing_low_iloc + 1, eval_idx + 1):
            bar_low = float(df['low'].iloc[i])
            bar_vol = float(df['volume'].iloc[i])
            if abs(bar_low - swing_low_price) <= 0.5 * atr_14_current and bar_vol < swing_low_volume:
                retest_confirmed = True
                break

    # Criterion 5: No DISTRIBUTION WARNING (§3.3 C5)
    # "vol_confirm_state != 'DISTRIBUTION WARNING' at current evaluation bar"
    crit_vol_clean = ctx.vol_confirm_state != "DISTRIBUTION WARNING"

    # --- Composite base confirmation ---
    base_confirmed = all([
        crit_min_bars, crit_no_lower_low, crit_atr_contracting,
        retest_confirmed, crit_vol_clean
    ])

    # ------------------------------------------------------------------
    # §3.4 — EMA 8/21 Cross Freshness (DQ-2)
    # Most recent bar where EMA_8 crosses above EMA_21 (bullish cross).
    # Cross bar must be >= swing_low_bar_index.
    # ------------------------------------------------------------------
    ema8 = df['EMA_8'].iloc[:eval_idx + 1]
    ema21 = df['EMA_21'].iloc[:eval_idx + 1]
    ema_cross_bar_index = None
    # Scan backward from eval bar for most recent bullish cross
    for i in range(eval_idx, 0, -1):
        if float(ema8.iloc[i]) > float(ema21.iloc[i]) and float(ema8.iloc[i - 1]) <= float(ema21.iloc[i - 1]):
            ema_cross_bar_index = i
            break

    ema_cross_fresh = (ema_cross_bar_index is not None and ema_cross_bar_index >= swing_low_iloc)

    # ------------------------------------------------------------------
    # DI spread values (consumed by Phase 2B R-Gate 3)
    # ------------------------------------------------------------------
    dmp_col = ctx.dmp_col
    dmn_col = ctx.dmn_col
    di_plus_current = float(df[dmp_col].iloc[eval_idx])
    di_minus_current = float(df[dmn_col].iloc[eval_idx])
    di_plus_at_sl = float(df[dmp_col].iloc[swing_low_iloc])
    di_minus_at_sl = float(df[dmn_col].iloc[swing_low_iloc])
    di_spread_current = abs(di_plus_current - di_minus_current)
    di_spread_at_swing_low = abs(di_plus_at_sl - di_minus_at_sl)

    # ------------------------------------------------------------------
    # Return structure — consumed by Phase 2B recovery gates
    # ------------------------------------------------------------------
    return {
        "swing_low_price": swing_low_price,
        "swing_low_bar_index": swing_low_iloc,
        "base_bar_count": base_bar_count,
        "base_confirmed": base_confirmed,
        "criteria": {
            "min_bars": crit_min_bars,
            "no_lower_low": crit_no_lower_low,
            "atr_contracting": crit_atr_contracting,
            "retest_confirmed": retest_confirmed,
            "vol_clean": crit_vol_clean,
        },
        "atr_contraction_ratio": atr_contraction_ratio,
        "retest_confirmed": retest_confirmed,
        "ema_cross_bar_index": ema_cross_bar_index,
        "ema_cross_fresh": ema_cross_fresh,
        "di_spread_current": round(di_spread_current, 2),
        "di_spread_at_swing_low": round(di_spread_at_swing_low, 2),
        # Phase 2C consumption — stored but not implemented here
        "time_stop_limit": time_stop_limit,
        "min_base_bars": min_base_bars,
    }


# ======================================================================
# CQS-001: Consolidation Quality Score
# Pre-breakout setup quality assessment for SWING_BREAKOUT and BREAKOUT
# triggers. Scores range contraction, volume contraction, and VCP proxy
# (pullback depth shallowing) over a profile-adaptive consolidation window.
#
# Pure backward-lookback computation — no gate logic, no output formatting.
# Called from main.py on VALID breakout paths only, after verdict
# determination and before output assembly.
# ======================================================================

# --- CQS-001 Constants (Spec §9) ---
CQS_ATR_GATE_RATIO = 0.50        # ATR qualifying gate threshold
CQS_WINDOW_A = 50                # Profile A consolidation window (hourly bars)
CQS_WINDOW_B = 30                # Profile B consolidation window (daily bars)
CQS_ATR_LONG_WINDOW = 50         # Long-window ATR period for ATR-ratio comparison
CQS_TERMINAL_BARS = 5            # Final bars for terminal volume ratio
CQS_RC_WEIGHT = 0.40             # Range Contraction component weight
CQS_VC_WEIGHT = 0.35             # Volume Contraction component weight
CQS_VCP_WEIGHT = 0.25            # VCP Proxy component weight
CQS_HIGH_THRESHOLD = 70          # Composite score threshold for HIGH label
CQS_MODERATE_THRESHOLD = 40      # Composite score threshold for MODERATE label


def _compute_consolidation_quality(df, resistance_raw, atr_raw, vol_sma_20, p_code):
    """CQS-001: Consolidation Quality Score computation.

    Assesses breakout setup quality by scoring three research-validated
    components: range contraction, volume contraction, and VCP proxy
    (pullback depth shallowing) over a profile-adaptive lookback window.

    Args:
        df: Primary dataframe (hourly for Profile A, daily for Profile B).
            The current (breakout) bar is the last row — the window
            excludes it, assessing only the consolidation preceding the
            breakout event.
        resistance_raw: 10-bar resistance ceiling (raw price units).
        atr_raw: Current 14-period ATR (raw price units).
        vol_sma_20: 20-period volume SMA (already computed in engine).
        p_code: Profile code ('A' or 'B').

    Returns:
        dict with ATR gate result, three component scores, composite
        score, composite label, and diagnostic fields. All values null
        when insufficient data or non-applicable.

    CQS-001 Spec §4–§6 | Follows _compute_exit_signals / _compute_early_capital_rr pattern.
    """
    # --- Null result template (returned on skip / insufficient data) ---
    _null = {
        "CQS_Composite_Score": None,
        "CQS_Composite_Label": None,
        "CQS_ATR_Gate_Passed": None,
        "CQS_ATR_Ratio": None,
        "CQS_Range_Contraction_Score": None,
        "CQS_Volume_Contraction_Score": None,
        "CQS_VCP_Score": None,
        "CQS_VCP_Swing_Lows_Found": None,
        "CQS_Volume_Terminal_Ratio": None,
    }

    # --- Window selection (Spec §4.2) ---
    window_size = CQS_WINDOW_A if p_code == "A" else CQS_WINDOW_B

    # Insufficient data guard: need at least 10 bars before breakout bar
    # df has breakout bar as last row; window excludes it
    if len(df) < 11:  # 10 consolidation bars + 1 breakout bar
        return _null

    # Extract consolidation window (excludes breakout bar = last row)
    avail = len(df) - 1  # bars available before breakout
    actual_window = min(window_size, avail)
    if actual_window < 10:
        return _null

    # Consolidation window: df.iloc[-(actual_window+1):-1]
    w_start = -(actual_window + 1)
    w_end = -1
    window_df = df.iloc[w_start:w_end]

    # --- §4.1 ATR Qualifying Gate ---
    # Compute long-window ATR average (SMA of ATR over CQS_ATR_LONG_WINDOW bars)
    if 'atr' in df.columns:
        _atr_col = 'atr'
    elif 'ATR' in df.columns:
        _atr_col = 'ATR'
    elif 'atr_raw' in df.columns:
        _atr_col = 'atr_raw'
    else:
        # Fallback: use atr_raw parameter directly
        _atr_col = None

    if _atr_col is not None:
        # Use ATR column from df for long-window average
        _atr_series = df[_atr_col].iloc[w_start:w_end]
        _long_window_atr_avg = _atr_series.mean()
    else:
        # No ATR column — use provided atr_raw as current, estimate long-window
        # from price ranges (conservative fallback)
        _long_window_atr_avg = atr_raw  # self-referential → gate always passes

    # Avoid division by zero
    if _long_window_atr_avg is None or _long_window_atr_avg <= 0:
        return _null

    atr_ratio = round(float(atr_raw / _long_window_atr_avg), 4)

    if atr_ratio > CQS_ATR_GATE_RATIO:
        # ATR gate fails: consolidation not genuine
        return {
            "CQS_Composite_Score": 0,
            "CQS_Composite_Label": "LOW",
            "CQS_ATR_Gate_Passed": False,
            "CQS_ATR_Ratio": atr_ratio,
            "CQS_Range_Contraction_Score": 0,
            "CQS_Volume_Contraction_Score": 0,
            "CQS_VCP_Score": 0,
            "CQS_VCP_Swing_Lows_Found": None,
            "CQS_Volume_Terminal_Ratio": None,
        }

    # ATR gate passed — compute components
    atr_gate_passed = True

    # === Component 1: Range Contraction (RC, 40%) — Spec §4.3 ===
    half = actual_window // 2
    early_half = window_df.iloc[:half]
    late_half = window_df.iloc[half:]

    early_avg_range = float((early_half['high'] - early_half['low']).mean())
    late_avg_range = float((late_half['high'] - late_half['low']).mean())

    if early_avg_range > 0:
        rc_ratio = late_avg_range / early_avg_range
    else:
        rc_ratio = 1.0  # no range → no contraction signal

    # Scoring: rc_ratio ≤ 0.50 → 100, rc_ratio ≥ 1.00 → 0, linear between
    rc_score = int(round(max(0, min(100, (1.0 - rc_ratio) / 0.5 * 100))))

    # === Component 2: Volume Contraction (VC, 35%) — Spec §4.4 ===

    # Sub-Component A: Volume Trend Slope (§4.4.1)
    vol_series = window_df['volume'].values.astype(float)
    mean_volume = float(np.mean(vol_series))
    if mean_volume > 0 and len(vol_series) >= 2:
        x = np.arange(len(vol_series), dtype=float)
        # Linear regression: slope via least squares
        slope = float(np.polyfit(x, vol_series, 1)[0])
        slope_pct = slope / mean_volume * 100.0
    else:
        slope_pct = 0.0

    # Scoring: slope_pct ≤ -3.0 → 100, slope_pct ≥ 0.0 → 0, linear between
    slope_score = int(round(max(0, min(100, (0.0 - slope_pct) / 3.0 * 100))))

    # Sub-Component B: Terminal Volume Ratio (§4.4.2)
    terminal_bars = window_df.iloc[-CQS_TERMINAL_BARS:]
    terminal_avg_vol = float(terminal_bars['volume'].mean())

    if vol_sma_20 is not None and vol_sma_20 > 0:
        terminal_ratio = round(float(terminal_avg_vol / vol_sma_20), 4)
    else:
        terminal_ratio = 1.0  # no reference → no contraction signal

    # Scoring: ratio ≤ 0.50 → 100, ratio ≥ 1.00 → 0, linear between
    terminal_score = int(round(max(0, min(100, (1.0 - terminal_ratio) / 0.5 * 100))))

    # VC composite: 50/50
    vc_score = int(round(0.50 * slope_score + 0.50 * terminal_score))

    # === Component 3: VCP Proxy (25%) — Spec §4.5 ===

    # Swing low detection: 3-bar pivot
    lows = window_df['low'].values.astype(float)
    swing_lows = []  # list of (index_in_window, low_value)
    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            swing_lows.append((i, lows[i]))

    swing_lows_found = len(swing_lows)

    # Depth computation: depth from resistance ceiling in ATR units
    if swing_lows_found >= 2 and atr_raw > 0:
        depths = [(resistance_raw - sl_val) / atr_raw for _, sl_val in swing_lows]

        # Check monotonically decreasing (later dips shallower)
        monotonic_decreasing = all(depths[j] > depths[j + 1] for j in range(len(depths) - 1))
        last_lt_first = depths[-1] < depths[0]

        if swing_lows_found >= 3 and monotonic_decreasing:
            vcp_score = 100
        elif swing_lows_found == 2 and monotonic_decreasing:
            vcp_score = 75
        elif last_lt_first:
            # 2+ swing lows, last depth < first depth (improving but non-monotonic)
            vcp_score = 40
        else:
            # Depths increasing
            vcp_score = 0
    else:
        # Fewer than 2 swing lows or zero ATR
        vcp_score = 0

    # === Composite Score and Labels — Spec §4.6 ===
    composite = int(round(
        rc_score * CQS_RC_WEIGHT +
        vc_score * CQS_VC_WEIGHT +
        vcp_score * CQS_VCP_WEIGHT
    ))
    composite = max(0, min(100, composite))

    if composite >= CQS_HIGH_THRESHOLD:
        label = "HIGH"
    elif composite >= CQS_MODERATE_THRESHOLD:
        label = "MODERATE"
    else:
        label = "LOW"

    return {
        "CQS_Composite_Score": composite,
        "CQS_Composite_Label": label,
        "CQS_ATR_Gate_Passed": atr_gate_passed,
        "CQS_ATR_Ratio": atr_ratio,
        "CQS_Range_Contraction_Score": rc_score,
        "CQS_Volume_Contraction_Score": vc_score,
        "CQS_VCP_Score": vcp_score,
        "CQS_VCP_Swing_Lows_Found": swing_lows_found,
        "CQS_Volume_Terminal_Ratio": terminal_ratio,
    }
