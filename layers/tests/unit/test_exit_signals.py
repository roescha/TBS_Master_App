"""Unit tests for RFT-004 Phase 1: Exit signal decomposition.

Tests the three per-profile exit handlers and the _compute_exit_signals
dispatcher introduced in RFT-004 Phase 1:
    _exit_profile_a, _exit_profile_b, _exit_profile_c, _compute_exit_signals

Each per-profile function receives raw engine state and returns
False | "WARNING" | "EXIT". Tests use SimpleNamespace to construct
minimal state/df objects with only the fields each function reads.

Coverage per profile:
    - Primary exit trigger fires correctly
    - PE-28 graduation sequence: False → "WARNING" → "EXIT"
    - PE-25 floor failure override (exit forced to "EXIT" regardless of counter state)
    - PE-7b suppression interaction (Reward_Risk suppressed on EXIT)
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace

from ibkr_purity_engine import (
    _exit_profile_a,
    _exit_profile_b,
    _exit_profile_c,
    _compute_exit_signals,
)


# ---------------------------------------------------------------------------
# Helper: build minimal DataFrames for exit tests
# ---------------------------------------------------------------------------

def _make_exit_df_a(n=60, base=100.0, vwap_offset=0.0, low_breach=False):
    """Build a minimal DataFrame for Profile A exit tests.

    Args:
        vwap_offset: Offset added to close relative to ANCHOR.
            Positive = close above ANCHOR (no VWAP violation).
            Negative = close below ANCHOR (VWAP violation).
        low_breach: If True, set last close below the established hourly low.
    """
    rng = np.random.RandomState(42)
    closes = [base + 0.2 * i + rng.normal(0, 0.1) for i in range(n)]
    df = pd.DataFrame({
        'open':   [c - 0.1 for c in closes],
        'high':   [c + 1.0 for c in closes],
        'low':    [c - 1.0 for c in closes],
        'close':  closes,
        'volume': [500000] * n,
    })
    # ANCHOR (VWAP proxy)
    df['ANCHOR'] = df['close'].rolling(20, min_periods=1).mean()
    df['SMA_50'] = df['close'].rolling(50, min_periods=1).mean()
    df['EMA_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['SMA_200'] = df['close'].rolling(min(200, n - 1), min_periods=1).mean()

    # Apply vwap_offset to the last 6 bars (enough for the 5-bar counter)
    i0 = -2  # Profile A evaluated bar
    for offset in range(0, 6):
        idx = len(df) + i0 - offset
        if idx >= 0:
            anchor_val = df['ANCHOR'].iloc[idx]
            df.iloc[idx, df.columns.get_loc('close')] = anchor_val + vwap_offset

    if low_breach:
        # Set close below the established hourly low (min of lows in [-12:-2])
        est_low = df['low'].iloc[-12:-2].min()
        df.iloc[-2, df.columns.get_loc('close')] = est_low - 1.0

    return df


def _make_exit_df_b(n=60, base=100.0, below_sma50=False, below_ema8=False):
    """Build a minimal DataFrame for Profile B exit tests."""
    rng = np.random.RandomState(42)
    closes = [base + 0.2 * i + rng.normal(0, 0.1) for i in range(n)]
    df = pd.DataFrame({
        'open':   [c - 0.1 for c in closes],
        'high':   [c + 1.0 for c in closes],
        'low':    [c - 1.0 for c in closes],
        'close':  closes,
        'volume': [500000] * n,
    })
    df['SMA_50'] = df['close'].rolling(50, min_periods=1).mean()
    df['EMA_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['SMA_200'] = df['close'].rolling(min(200, n - 1), min_periods=1).mean()
    df['ANCHOR'] = df['SMA_50']

    last_idx = -1  # Profile B evaluated bar
    if below_sma50:
        df.iloc[last_idx, df.columns.get_loc('close')] = df['SMA_50'].iloc[last_idx] - 2.0
    if below_ema8:
        ema8_val = df['EMA_8'].iloc[last_idx]
        current_close = df['close'].iloc[last_idx]
        if current_close >= ema8_val:
            df.iloc[last_idx, df.columns.get_loc('close')] = ema8_val - 0.5
        # Ensure above SMA_50 if only testing EMA 8
        if not below_sma50:
            sma50_val = df['SMA_50'].iloc[last_idx]
            if df['close'].iloc[last_idx] < sma50_val:
                df.iloc[last_idx, df.columns.get_loc('close')] = sma50_val + 0.1

    return df


def _make_exit_df_c(n=60, base=100.0, below_sma200=False):
    """Build a minimal DataFrame for Profile C exit tests."""
    rng = np.random.RandomState(42)
    closes = [base + 0.2 * i + rng.normal(0, 0.1) for i in range(n)]
    df = pd.DataFrame({
        'open':   [c - 0.1 for c in closes],
        'high':   [c + 1.0 for c in closes],
        'low':    [c - 1.0 for c in closes],
        'close':  closes,
        'volume': [500000] * n,
    })
    df['SMA_50'] = df['close'].rolling(50, min_periods=1).mean()
    df['EMA_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['SMA_200'] = df['close'].rolling(min(200, n - 1), min_periods=1).mean()
    df['ANCHOR'] = df['SMA_50']

    if below_sma200:
        df.iloc[-1, df.columns.get_loc('close')] = df['SMA_200'].iloc[-1] - 2.0

    return df


def _make_state(**overrides):
    """Build a minimal StateBundle-like namespace for exit tests."""
    defaults = dict(
        is_floor_failure=False, consec_below=0, _reclaim_run=0,
        is_trending=True, is_resolving=False,
        atr_raw=2.0, floor_raw=100.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ===========================================================================
# _exit_profile_a — VWAP 3-bar counter, strict close, no grace buffer
# ===========================================================================

class TestExitProfileA:
    """Tests for _exit_profile_a (Profile A exit handler)."""

    def test_no_trigger_returns_false(self):
        """No exit trigger: close above VWAP and above hourly low → False."""
        df = _make_exit_df_a(vwap_offset=5.0, low_breach=False)
        state = _make_state()
        last = df.iloc[-2]
        metrics = {}
        result = _exit_profile_a(state, df, last, -2, 1.0, metrics)
        assert result is False
        assert metrics["Exit_Signal"] is False
        assert metrics["Exit_Triggers"] == "None"
        assert metrics["Exit_Reason"] == "None"

    def test_hourly_low_breach_returns_warning(self):
        """PE-28: Hourly low breach alone → WARNING."""
        df = _make_exit_df_a(vwap_offset=5.0, low_breach=True)
        state = _make_state()
        last = df.iloc[-2]
        metrics = {}
        result = _exit_profile_a(state, df, last, -2, 1.0, metrics)
        assert result == "WARNING"
        assert metrics["Exit_Signal"] == "WARNING"
        assert "Hourly_Low_Breach" in metrics["Exit_Triggers"]

    def test_vwap_3bar_returns_exit(self):
        """PE-28: VWAP 3-bar violation → EXIT (sustained structural deterioration)."""
        df = _make_exit_df_a(vwap_offset=-5.0, low_breach=False)
        state = _make_state()
        last = df.iloc[-2]
        metrics = {}
        result = _exit_profile_a(state, df, last, -2, 1.0, metrics)
        assert result == "EXIT"
        assert metrics["Exit_Signal"] == "EXIT"
        assert "VWAP_3Bar_Violation" in metrics["Exit_Triggers"]

    def test_both_triggers_returns_exit(self):
        """PE-28: Both triggers → EXIT."""
        df = _make_exit_df_a(vwap_offset=-5.0, low_breach=True)
        state = _make_state()
        last = df.iloc[-2]
        metrics = {}
        result = _exit_profile_a(state, df, last, -2, 1.0, metrics)
        assert result == "EXIT"
        assert "Hourly_Low_Breach" in metrics["Exit_Triggers"]
        assert "VWAP_3Bar_Violation" in metrics["Exit_Triggers"]

    def test_graduation_false_to_warning_to_exit(self):
        """PE-28 graduation sequence: False → WARNING → EXIT."""
        state = _make_state()

        # 1. No triggers → False
        df1 = _make_exit_df_a(vwap_offset=5.0, low_breach=False)
        m1 = {}
        r1 = _exit_profile_a(state, df1, df1.iloc[-2], -2, 1.0, m1)
        assert r1 is False

        # 2. Hourly low breach only → WARNING
        df2 = _make_exit_df_a(vwap_offset=5.0, low_breach=True)
        m2 = {}
        r2 = _exit_profile_a(state, df2, df2.iloc[-2], -2, 1.0, m2)
        assert r2 == "WARNING"

        # 3. VWAP 3-bar → EXIT
        df3 = _make_exit_df_a(vwap_offset=-5.0, low_breach=False)
        m3 = {}
        r3 = _exit_profile_a(state, df3, df3.iloc[-2], -2, 1.0, m3)
        assert r3 == "EXIT"

    def test_vwap_counter_metric_written(self):
        """Exit_VWAP_Counter metric is written."""
        df = _make_exit_df_a(vwap_offset=-5.0)
        state = _make_state()
        metrics = {}
        _exit_profile_a(state, df, df.iloc[-2], -2, 1.0, metrics)
        assert "Exit_VWAP_Counter" in metrics
        assert metrics["Exit_VWAP_Counter"] == "3/3"

    def test_established_hourly_low_metric(self):
        """Established_Hourly_Low metric is surfaced (PE-27)."""
        df = _make_exit_df_a(vwap_offset=5.0)
        state = _make_state()
        metrics = {}
        _exit_profile_a(state, df, df.iloc[-2], -2, 1.0, metrics)
        assert "Established_Hourly_Low" in metrics

    def test_price_scaler_applied(self):
        """Established_Hourly_Low is divided by price_scaler."""
        df = _make_exit_df_a(vwap_offset=5.0)
        state = _make_state()
        m1 = {}
        _exit_profile_a(state, df, df.iloc[-2], -2, 1.0, m1)
        m2 = {}
        _exit_profile_a(state, df, df.iloc[-2], -2, 100.0, m2)
        assert m1["Established_Hourly_Low"] != m2["Established_Hourly_Low"]


# ===========================================================================
# _exit_profile_b — SMA 50 standard + EMA 8 convexity (is_resolving gated)
# ===========================================================================

class TestExitProfileB:
    """Tests for _exit_profile_b (Profile B exit handler)."""

    def test_no_trigger_returns_false(self):
        """No exit trigger: close above SMA 50 and EMA 8 → False."""
        df = _make_exit_df_b()
        state = _make_state(is_resolving=True, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        assert result is False
        assert metrics["Exit_Signal"] is False
        assert metrics["Exit_Triggers"] == "None"

    def test_sma50_breach_returns_exit(self):
        """Close below SMA 50 → EXIT (structural floor break)."""
        df = _make_exit_df_b(below_sma50=True)
        state = _make_state()
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert "SMA_50_Breach" in metrics["Exit_Triggers"]
        assert metrics["Exit_Reason"] == "Close below 50-SMA"

    def test_ema8_breach_resolving_returns_warning(self):
        """EMA 8 breach with is_resolving (non-C3) → WARNING."""
        df = _make_exit_df_b(below_ema8=True)
        state = _make_state(is_resolving=True, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        assert result == "WARNING"
        assert "EMA_8_Convexity_Breach" in metrics["Exit_Triggers"]

    def test_ema8_breach_c3_returns_exit(self):
        """CVX-7: EMA 8 breach for C-3 → EXIT (thesis invalidation)."""
        df = _make_exit_df_b(below_ema8=True)
        state = _make_state(is_resolving=True, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert "C-3 EXIT" in metrics["Exit_Reason"]

    def test_ema8_not_gated_when_trending(self):
        """EMA 8 exit requires is_resolving and NOT is_trending."""
        df = _make_exit_df_b(below_ema8=True)
        # is_trending=True blocks the convexity exit gate
        state = _make_state(is_resolving=True, is_trending=True)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        # EMA 8 gate blocked by is_trending — only SMA 50 matters
        if last['close'] >= last['SMA_50']:
            assert result is False

    def test_ema8_not_gated_when_not_resolving(self):
        """EMA 8 exit requires is_resolving to be True."""
        df = _make_exit_df_b(below_ema8=True)
        state = _make_state(is_resolving=False, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        # EMA 8 gate blocked by !is_resolving
        if last['close'] >= last['SMA_50']:
            assert result is False

    def test_graduation_false_to_warning_to_exit(self):
        """PE-28 graduation: False → WARNING (EMA 8) → EXIT (SMA 50)."""
        # 1. No triggers → False
        df1 = _make_exit_df_b()
        state1 = _make_state(is_resolving=True, is_trending=False)
        m1 = {}
        r1 = _exit_profile_b(state1, df1, df1.iloc[-1], False, None, -1, 1.0, m1)
        assert r1 is False

        # 2. EMA 8 breach (non-C3) → WARNING
        df2 = _make_exit_df_b(below_ema8=True)
        state2 = _make_state(is_resolving=True, is_trending=False)
        m2 = {}
        r2 = _exit_profile_b(state2, df2, df2.iloc[-1], False, None, -1, 1.0, m2)
        assert r2 == "WARNING"

        # 3. SMA 50 breach → EXIT
        df3 = _make_exit_df_b(below_sma50=True)
        state3 = _make_state()
        m3 = {}
        r3 = _exit_profile_b(state3, df3, df3.iloc[-1], False, None, -1, 1.0, m3)
        assert r3 == "EXIT"


# ===========================================================================
# _exit_profile_c — SMA 200 weekly
# ===========================================================================

class TestExitProfileC:
    """Tests for _exit_profile_c (Profile C exit handler)."""

    def test_no_trigger_returns_false(self):
        """Close above SMA 200 → False."""
        df = _make_exit_df_c()
        state = _make_state()
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_c(state, df, last, -1, 1.0, metrics)
        assert result is False
        assert metrics["Exit_Signal"] is False

    def test_sma200_breach_returns_exit(self):
        """Close below SMA 200 → EXIT (single structural trigger)."""
        df = _make_exit_df_c(below_sma200=True)
        state = _make_state()
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_c(state, df, last, -1, 1.0, metrics)
        assert result == "EXIT"
        assert metrics["Exit_Signal"] == "EXIT"
        assert "SMA_200_Breach" in metrics["Exit_Triggers"]
        assert metrics["Exit_Reason"] == "Close below 200-SMA"

    def test_graduation_false_to_exit(self):
        """PE-28: Profile C has no WARNING — goes directly to EXIT."""
        state = _make_state()

        # 1. Above SMA 200 → False
        df1 = _make_exit_df_c()
        m1 = {}
        r1 = _exit_profile_c(state, df1, df1.iloc[-1], -1, 1.0, m1)
        assert r1 is False

        # 2. Below SMA 200 → EXIT (no intermediate WARNING)
        df2 = _make_exit_df_c(below_sma200=True)
        m2 = {}
        r2 = _exit_profile_c(state, df2, df2.iloc[-1], -1, 1.0, m2)
        assert r2 == "EXIT"


# ===========================================================================
# _compute_exit_signals dispatcher — PE-25, Bug #33, PE-7b
# ===========================================================================

class TestComputeExitSignalsDispatcher:
    """Tests for the _compute_exit_signals dispatcher (shared post-exit logic)."""

    def test_dispatches_to_profile_a(self):
        """Dispatcher routes Profile A correctly."""
        df = _make_exit_df_a(vwap_offset=5.0)
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "A", df, df.iloc[-2], False, None, -2, 1.0, metrics
        )
        assert result is False

    def test_dispatches_to_profile_b(self):
        """Dispatcher routes Profile B correctly."""
        df = _make_exit_df_b()
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert result is False

    def test_dispatches_to_profile_c(self):
        """Dispatcher routes Profile C correctly."""
        df = _make_exit_df_c()
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "C", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert result is False

    def test_unknown_profile_returns_false(self):
        """Unknown profile code → False with 'None' triggers."""
        df = _make_exit_df_b()
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "Z", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert result is False
        assert metrics["Exit_Signal"] is False

    def test_pe25_floor_failure_override_forces_exit(self):
        """PE-25: Floor failure overrides any profile result to EXIT."""
        # Profile A with no triggers (would be False)
        df = _make_exit_df_a(vwap_offset=5.0)
        state = _make_state(is_floor_failure=True, consec_below=5, _reclaim_run=1)
        metrics = {}
        result = _compute_exit_signals(
            state, "A", df, df.iloc[-2], False, None, -2, 1.0, metrics
        )
        assert result == "EXIT"
        assert metrics["Exit_Signal"] == "EXIT"
        assert "Floor_Failure_Override" in metrics["Exit_Triggers"]
        assert "FLOOR FAILURE OVERRIDE" in metrics["Exit_Reason"]
        assert metrics["Floor_Failure_Reclaim"] == "1/3"

    def test_pe25_does_not_override_when_already_exit(self):
        """PE-25: Floor failure does not double-override when already EXIT."""
        df = _make_exit_df_a(vwap_offset=-5.0)  # VWAP violation → EXIT
        state = _make_state(is_floor_failure=True, consec_below=5, _reclaim_run=0)
        metrics = {}
        result = _compute_exit_signals(
            state, "A", df, df.iloc[-2], False, None, -2, 1.0, metrics
        )
        assert result == "EXIT"
        # Floor_Failure_Override should NOT be appended (already EXIT)
        assert "Floor_Failure_Override" not in metrics["Exit_Triggers"]

    def test_pe25_overrides_warning_to_exit(self):
        """PE-25: Floor failure overrides WARNING → EXIT."""
        df = _make_exit_df_a(vwap_offset=5.0, low_breach=True)  # WARNING
        state = _make_state(is_floor_failure=True, consec_below=4, _reclaim_run=2)
        metrics = {}
        result = _compute_exit_signals(
            state, "A", df, df.iloc[-2], False, None, -2, 1.0, metrics
        )
        assert result == "EXIT"
        assert "Floor_Failure_Override" in metrics["Exit_Triggers"]
        assert metrics["Floor_Failure_Reclaim"] == "2/3"

    def test_bug33_profit_target_synthetic_suppressed_on_exit(self):
        """Bug #33: Profit_Target_Synthetic suppressed when exit_signal = EXIT."""
        df = _make_exit_df_b(below_sma50=True)  # EXIT
        state = _make_state()
        metrics = {}
        target_1_b = 150.0
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, target_1_b, -1, 1.0, metrics
        )
        assert result == "EXIT"
        assert "Profit_Target_Synthetic" not in metrics
        assert "SUPPRESSED" in metrics.get("Profit_Target_Synthetic_Note", "")

    def test_bug33_profit_target_synthetic_preserved_on_warning(self):
        """Bug #33: Profit_Target_Synthetic preserved on WARNING."""
        df = _make_exit_df_b(below_ema8=True)
        state = _make_state(is_resolving=True, is_trending=False)
        metrics = {}
        target_1_b = 150.0
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, target_1_b, -1, 1.0, metrics
        )
        assert result == "WARNING"
        assert metrics.get("Profit_Target_Synthetic") == 150.0

    def test_bug33_profit_target_synthetic_preserved_on_false(self):
        """Bug #33: Profit_Target_Synthetic written when no exit signal."""
        df = _make_exit_df_b()
        state = _make_state()
        metrics = {}
        target_1_b = 150.0
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, target_1_b, -1, 1.0, metrics
        )
        assert result is False
        assert metrics.get("Profit_Target_Synthetic") == 150.0

    def test_pe7b_reward_risk_suppressed_on_exit(self):
        """PE-7b: Reward_Risk suppressed when exit_signal = EXIT."""
        df = _make_exit_df_b(below_sma50=True)  # EXIT
        state = _make_state()
        metrics = {"Reward_Risk": 1.5, "Profit_Target": 160.0}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert result == "EXIT"
        assert metrics["Reward_Risk"] is None
        assert metrics["Profit_Target"] is None
        assert "SUPPRESSED" in metrics["Reward_Risk_Note"]

    def test_pe7b_reward_risk_preserved_on_warning(self):
        """PE-7b: Reward_Risk preserved on WARNING."""
        df = _make_exit_df_b(below_ema8=True)
        state = _make_state(is_resolving=True, is_trending=False)
        metrics = {"Reward_Risk": 1.5, "Profit_Target": 160.0}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert result == "WARNING"
        assert metrics["Reward_Risk"] == 1.5
        assert metrics["Profit_Target"] == 160.0

    def test_pe7b_no_suppression_when_reward_risk_absent(self):
        """PE-7b: No suppression when Reward_Risk is not in metrics."""
        df = _make_exit_df_b(below_sma50=True)  # EXIT
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert result == "EXIT"
        assert "Reward_Risk_Note" not in metrics

    def test_pe25_floor_failure_profile_b(self):
        """PE-25: Floor failure override works for Profile B."""
        df = _make_exit_df_b()  # No trigger → False
        state = _make_state(is_floor_failure=True, consec_below=4, _reclaim_run=0)
        metrics = {}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert result == "EXIT"
        assert "Floor_Failure_Override" in metrics["Exit_Triggers"]

    def test_pe25_floor_failure_profile_c(self):
        """PE-25: Floor failure override works for Profile C."""
        df = _make_exit_df_c()  # No trigger → False
        state = _make_state(is_floor_failure=True, consec_below=4, _reclaim_run=0)
        metrics = {}
        result = _compute_exit_signals(
            state, "C", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert result == "EXIT"
        assert "Floor_Failure_Override" in metrics["Exit_Triggers"]

    def test_return_type_is_native(self):
        """All return types are native Python (not numpy.bool_)."""
        df = _make_exit_df_b()
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics
        )
        assert type(result) in (bool, str)
