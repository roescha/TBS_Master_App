import math
import pandas as pd
from tbs_engine.types import FloorState, _DeepReclaimResult, GRACE_BUFFER_ATR_PCT

__all__ = ['_clamp', '_check_round_number_proximity', '_assess_floor_state', '_deep_reclaim_scan', 'check_climax_history', '_evaluate_floor_failure_context']
# ==============================================================================
# ENG-001: ROUND NUMBER PROXIMITY HELPER  [Amendment ENG-001]
# Evaluates whether a price level falls within ±0.5% of the nearest round
# number. Two-tier increment: $5 for prices < $50, $10 for prices >= $50.
# Returns: 'NEAR_ROUND_ABOVE', 'NEAR_ROUND_BELOW', or 'CLEAR'.
# NON-GATE: informational only. Must not affect any verdict or gate threshold.
# ==============================================================================


def _clamp(v, lo, hi):
    """Clamp value v to the range [lo, hi]. Promoted to module level in Phase 6."""
    return max(lo, min(hi, v))

def _check_round_number_proximity(price):
    """
    Returns 'NEAR_ROUND_ABOVE', 'NEAR_ROUND_BELOW', or 'CLEAR'.
    Increment: $5 for price < $50, $10 for price >= $50.
    Proximity threshold: ±0.5% of the round number.
    """
    if price is None or price <= 0:
        return "CLEAR"
    increment = 5.0 if price < 50.0 else 10.0
    nearest_below = math.floor(price / increment) * increment
    nearest_above = nearest_below + increment
    # Check proximity to nearest_below (round number is below current price)
    if nearest_below > 0 and abs(price - nearest_below) / nearest_below <= 0.005:
        return "NEAR_ROUND_ABOVE"   # level sits above the round number (round number is a floor below)
    # Check proximity to nearest_above (round number is above current price)
    if abs(price - nearest_above) / nearest_above <= 0.005:
        return "NEAR_ROUND_BELOW"   # level sits below the round number (round number is a ceiling above)
    return "CLEAR"

# ==============================================================================
# FLOOR STATE ASSESSMENT HELPER  [MANDATE: DOC 2 SEC 4.1 / SEC VI.3]
# ==============================================================================


def _assess_floor_state(df, i0, atr_raw, ff_threshold, include_current_bar=True):
    """Compute floor violation state from bar data.

    Counts consecutive closes below the structural floor (ANCHOR column)
    using a GRACE_BUFFER_ATR_PCT ATR grace buffer. Evaluates against the
    profile-dependent floor failure threshold.

    [MANDATE: DOC 2 SEC 4.1 / SEC VI.3]

    Args:
        df: DataFrame with 'close' and 'ANCHOR' columns.
        i0: Index of the evaluated bar (cfg.iq offset).
        atr_raw: ATR value for grace buffer computation.
        ff_threshold: Profile-dependent floor failure threshold
                      (A=8, B/C=4, from cfg.ff_threshold).
        include_current_bar: If True (default, Site 1 behavior), includes the
                      current bar in the consecutive count when it is below
                      floor (scan from offset 0). If False (Site 2 behavior),
                      always scans prior bars only (offset 1+) regardless of
                      current bar position. The two original sites used
                      different scan strategies; this parameter preserves both.

    Returns:
        FloorState namedtuple with violation assessment.
    """
    current_above_floor = df['close'].iloc[i0] >= df['ANCHOR'].iloc[i0]

    # Grace buffer: a bar must close more than 0.15 ATR below the floor to count
    # as a "below" bar. This prevents micro-wicks and hairline breaches from
    # triggering violated/failure states on stocks hugging their floor.
    grace = GRACE_BUFFER_ATR_PCT * atr_raw if atr_raw > 0 else 0

    ff_lookback = ff_threshold + 1  # scan depth: threshold + 1 for boundary detection

    if include_current_bar and not current_above_floor:
        # Site 1 mode: current bar is below floor. Count the current streak including it.
        consec_below = 0
        for offset in range(0, ff_lookback):
            bar_dist = df['ANCHOR'].iloc[i0 - offset] - df['close'].iloc[i0 - offset]
            if bar_dist > grace:
                consec_below += 1
            else:
                break
        is_violated      = (1 <= consec_below <= (ff_threshold - 1))    # Waiting for Reclaim
        is_reclaim       = False                                        # Current bar not above floor
        is_floor_failure = (consec_below >= ff_threshold)               # Structural failure
    else:
        # Current bar reclaimed (or include_current_bar=False).
        # Count consecutive below-floor bars among PRIOR bars only.
        consec_below = 0
        for offset in range(1, ff_lookback):
            bar_dist = df['ANCHOR'].iloc[i0 - offset] - df['close'].iloc[i0 - offset]
            if bar_dist > grace:
                consec_below += 1
            else:
                break  # Streak broken -- stop counting

        if include_current_bar:
            # Site 1 mode, current bar above floor: branch-based flag computation.
            is_violated      = False                                        # Current bar is healthy
            is_reclaim       = (1 <= consec_below <= (ff_threshold - 1))    # Prior bars below but under threshold = Reclaim
            is_floor_failure = (consec_below >= ff_threshold)               # Structural failure
        else:
            # Site 2 mode: non-branching flag computation (original Pre-Check logic).
            is_violated      = (1 <= consec_below <= (ff_threshold - 1))
            is_reclaim       = is_violated and current_above_floor
            is_floor_failure = (consec_below >= ff_threshold)

    return FloorState(consec_below, is_violated, is_reclaim, is_floor_failure, current_above_floor)



# ==============================================================================
# DEEP RECLAIM SCAN HELPER  [RFT-003 F1 | Spec §III.1]
#
# Extracts the duplicated 3-bar reclaim deep scan algorithm into a shared
# function. Both the main violated state detection (Block A) and the floor
# violation pre-check (Block B) call this helper instead of inlining the scan.
# The helper owns only the scan algorithm; callers own what to do with results.
# ==============================================================================

def _deep_reclaim_scan(df, i0, atr_raw, ff_threshold):
    """Scan for recent floor failure behind reclaim bars.

    Counts consecutive above-floor bars backward from i0, then checks
    for floor failure (ff_threshold+ below-floor bars) behind the
    reclaim streak. Used by both the main violated state detection
    and the floor violation pre-check.

    Returns namedtuple (reclaim_run, hist_below, is_recent_failure):
        reclaim_run: int — consecutive above-floor bars from i0 backward.
        hist_below: int — consecutive below-floor bars behind the reclaim streak.
        is_recent_failure: bool — True if hist_below >= ff_threshold
                                  AND reclaim_run <= 2 (insufficient recovery).

    RFT-003 Finding F1 | Spec §III.1
    """
    grace = GRACE_BUFFER_ATR_PCT * atr_raw if atr_raw > 0 else 0
    ff_lookback = ff_threshold + 1

    # Count consecutive above-floor bars backward from i0
    reclaim_run = 0
    for _r_off in range(0, ff_threshold + 4):
        if df['close'].iloc[i0 - _r_off] >= df['ANCHOR'].iloc[i0 - _r_off]:
            reclaim_run += 1
        else:
            break

    # If only 1–2 reclaim bars, check for floor failure behind them
    hist_below = 0
    if 1 <= reclaim_run <= 2:
        for _h_off in range(reclaim_run, reclaim_run + ff_lookback):
            _h_dist = df['ANCHOR'].iloc[i0 - _h_off] - df['close'].iloc[i0 - _h_off]
            if _h_dist > grace:
                hist_below += 1
            else:
                break

    is_recent_failure = (hist_below >= ff_threshold) and (1 <= reclaim_run <= 2)

    return _DeepReclaimResult(reclaim_run, hist_below, is_recent_failure)




# ==============================================================================
# CLIMAX LOCKOUT HELPER  [MANDATE: DOC 2 SEC II]
# ==============================================================================

def check_climax_history(df):
    """
    Verifies the mandatory 3-bar block following a Volume Climax.
    Triggered: Volume > 2x SMA9 AND bar closes negative.
    Penalty:   Hard Block for 3 subsequent bars.
    """
    if df is None or len(df) < 4:
        return False, None
    required_cols = {"volume", "vol_sma_9", "close", "open"}
    if not required_cols.issubset(set(df.columns)):
        return False, None
    for i in range(1, 4):

        try:
            vol    = df['volume'].iloc[-i]
            sma9   = df['vol_sma_9'].iloc[-i]
            if pd.isna(sma9) or sma9 == 0:
                continue
            is_neg = df['close'].iloc[-i] < df['open'].iloc[-i]
            if vol > (2 * sma9) and is_neg:
                return True, i
        except (IndexError, KeyError):
            continue
    return False, 0


def _evaluate_floor_failure_context(state, df_ctx, p_code, price_scaler=1.0):
    """FFD-001: Evaluate higher-frame composite conditions at floor failure threshold.

    When the consecutive-bar floor failure threshold is reached, evaluates three
    conditions using higher-frame data. If all three pass → FLOOR BREACH
    (consolidation). If any fails → FLOOR FAILURE (structural breakdown).

    Condition 3 (non-directional-bearish regime) uses PRIMARY frame ADX/DI from
    state.adx_t, state.di_plus, state.di_minus — NOT from df_ctx.

    [FFD-001-BR-2] Extracted from gates.py to helpers.py so it can be called
    unconditionally in main.py (Layer 3) when state.is_floor_failure is True,
    regardless of whether the gate cascade reaches _gate_floor_failure.

    Args:
        state: StateBundle with adx_t, di_plus, di_minus from primary frame.
        df_ctx: Higher-frame context DataFrame (weekly for B, daily for A, monthly for C).
        p_code: Profile code ("A", "B", "C").

    Returns:
        tuple: (is_breach: bool, context_label: str, failing_conditions: list)
    """
    failing_conditions = []

    # --- Guard: df_ctx unavailable ---
    if df_ctx is None or len(df_ctx) < 2:
        failing_conditions.append("higher-frame data unavailable")
        return (False, f"STRUCTURAL_BREAKDOWN ({', '.join(failing_conditions)})", failing_conditions)

    _ctx_last = df_ctx.iloc[-1]

    # --- Determine column availability ---
    _has_sma50 = 'SMA_50' in df_ctx.columns and not pd.isna(_ctx_last['SMA_50'])
    _has_sma200 = 'SMA_200' in df_ctx.columns and not pd.isna(_ctx_last['SMA_200'])

    if not _has_sma50 or not _has_sma200:
        failing_conditions.append("higher-frame SMA data insufficient")
        return (False, f"STRUCTURAL_BREAKDOWN ({', '.join(failing_conditions)})", failing_conditions)

    # --- Profile-mapped frame labels (for diagnostic strings) ---
    _hf_label = {"A": "daily", "B": "weekly", "C": "monthly"}.get(p_code, "context")

    # --- Condition 1: Golden Cross (higher-frame SMA 50 > SMA 200) ---
    golden_cross = bool(_ctx_last['SMA_50'] > _ctx_last['SMA_200'])
    if not golden_cross:
        failing_conditions.append(f"{_hf_label} Golden Cross absent: SMA 50 {_ctx_last['SMA_50'] / price_scaler:.2f} <= SMA 200 {_ctx_last['SMA_200'] / price_scaler:.2f}")

    # --- Condition 2: Price above higher-frame SMA 200 ---
    price_above_sma200 = bool(_ctx_last['close'] > _ctx_last['SMA_200'])
    if not price_above_sma200:
        failing_conditions.append(f"price below {_hf_label} SMA 200: {_ctx_last['close'] / price_scaler:.2f} <= {_ctx_last['SMA_200'] / price_scaler:.2f}")

    # --- Condition 3: Primary-frame non-directional-bearish regime ---
    # ADX < 20 (MID-RANGE, no directional trend) OR (ADX >= 20 AND +DI >= -DI)
    adx = state.adx_t
    di_p = state.di_plus
    di_m = state.di_minus
    non_dir_bearish = (adx < 20) or (adx >= 20 and di_p >= di_m)
    if not non_dir_bearish:
        failing_conditions.append(f"bearish DI regime: -DI {di_m:.2f} > +DI {di_p:.2f}")

    # --- Composite result ---
    if not failing_conditions:
        return (True, "CONSOLIDATION", [])
    else:
        return (False, f"STRUCTURAL_BREAKDOWN ({', '.join(failing_conditions)})", failing_conditions)
