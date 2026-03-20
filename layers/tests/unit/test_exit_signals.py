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
    i0 = -1  # PE-43: Profile A evaluated bar (was -2)
    for offset in range(0, 6):
        idx = len(df) + i0 - offset
        if idx >= 0:
            anchor_val = df['ANCHOR'].iloc[idx]
            df.iloc[idx, df.columns.get_loc('close')] = anchor_val + vwap_offset

    if low_breach:
        # Set close below the established hourly low (min of lows in [-11:-1])
        est_low = df['low'].iloc[-11:-1].min()  # PE-43: was -12:-2
        df.iloc[-1, df.columns.get_loc('close')] = est_low - 1.0  # PE-43: was -2

    return df


def _make_exit_df_b(n=60, base=100.0, below_sma50=False, below_ema8=False,
                    below_sma200=False, consec_below_ema8=0):
    """Build a minimal DataFrame for Profile B exit tests.

    Args:
        below_sma200: When True, set last bar close below SMA_200 - 2.0
            (same pattern as _make_exit_df_c).
        consec_below_ema8: Number of consecutive bars (counting back from the
            last bar) to place below EMA 8. When > 0, overrides the below_ema8
            single-bar flag. Sets close to EMA_8 - 0.5 for each qualifying bar.
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
    df['SMA_50'] = df['close'].rolling(50, min_periods=1).mean()
    df['EMA_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['SMA_200'] = df['close'].rolling(min(200, n - 1), min_periods=1).mean()
    df['ANCHOR'] = df['SMA_50']

    last_idx = -1  # Profile B evaluated bar

    if below_sma200:
        df.iloc[last_idx, df.columns.get_loc('close')] = df['SMA_200'].iloc[last_idx] - 2.0
    elif below_sma50:
        # Place close below SMA 50 but above SMA 200 (midpoint between the two)
        sma50_val = df['SMA_50'].iloc[last_idx]
        sma200_val = df['SMA_200'].iloc[last_idx]
        if sma50_val > sma200_val + 0.2:
            # Room exists between SMA 50 and SMA 200 — place close in the gap
            df.iloc[last_idx, df.columns.get_loc('close')] = (sma50_val + sma200_val) / 2
        else:
            # Tight gap — force SMA 200 lower to create separation, then place close
            df.iloc[last_idx, df.columns.get_loc('close')] = sma50_val - 0.5
            # Ensure still above SMA 200 by adjusting SMA 200 if needed
            if df['close'].iloc[last_idx] <= sma200_val:
                df.iloc[last_idx, df.columns.get_loc('SMA_200')] = df['close'].iloc[last_idx] - 1.0

    if consec_below_ema8 > 0:
        # Override below_ema8 flag: set N consecutive bars below their EMA 8
        for offset in range(consec_below_ema8):
            idx = len(df) - 1 - offset
            if idx >= 0:
                target = df['EMA_8'].iloc[idx] - 0.5
                # When below_sma50 is also requested, ensure close is below SMA 50 too
                if below_sma50:
                    sma50_val = df['SMA_50'].iloc[idx]
                    target = min(target, sma50_val - 0.5)
                    # But keep above SMA 200 unless below_sma200 is also set
                    if not below_sma200:
                        sma200_val = df['SMA_200'].iloc[idx]
                        if target <= sma200_val:
                            # Force SMA 200 lower to create room
                            df.iloc[idx, df.columns.get_loc('SMA_200')] = target - 1.0
                df.iloc[idx, df.columns.get_loc('close')] = target
        # Ensure above SMA_50 if not testing SMA 50 breach
        if not below_sma50 and not below_sma200:
            for offset in range(consec_below_ema8):
                idx = len(df) - 1 - offset
                if idx >= 0:
                    sma50_val = df['SMA_50'].iloc[idx]
                    if df['close'].iloc[idx] < sma50_val:
                        df.iloc[idx, df.columns.get_loc('close')] = sma50_val + 0.1
    elif below_ema8:
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


def _cfg_a():
    """PE-43: Profile A cfg mock with corrected iq=-1 slices."""
    return SimpleNamespace(
        iq=-1, resistance_slice_start=-11, resistance_slice_end=-1,
        prev_bar_offset=2, ff_threshold=8,
    )


def _cfg_b():
    """Profile B cfg mock."""
    return SimpleNamespace(
        iq=-1, resistance_slice_start=-11, resistance_slice_end=-1,
        prev_bar_offset=2, ff_threshold=4,
    )


def _cfg_c():
    """Profile C cfg mock."""
    return SimpleNamespace(
        iq=-1, resistance_slice_start=-11, resistance_slice_end=-1,
        prev_bar_offset=2, ff_threshold=4,
    )


# ===========================================================================
# _exit_profile_a — VWAP 3-bar counter, strict close, no grace buffer
# ===========================================================================

class TestExitProfileA:
    """Tests for _exit_profile_a (Profile A exit handler)."""

    def test_no_trigger_returns_false(self):
        """No exit trigger: close above VWAP and above hourly low → False."""
        df = _make_exit_df_a(vwap_offset=5.0, low_breach=False)
        state = _make_state()
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_a(state, df, last, -1, 1.0, metrics, _cfg_a())
        assert result is False
        assert metrics["Exit_Signal"] is False
        assert metrics["Exit_Triggers"] == "None"
        assert metrics["Exit_Reason"] == "None"

    def test_hourly_low_breach_returns_warning(self):
        """PE-28: Hourly low breach alone → WARNING."""
        df = _make_exit_df_a(vwap_offset=5.0, low_breach=True)
        state = _make_state()
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_a(state, df, last, -1, 1.0, metrics, _cfg_a())
        assert result == "WARNING"
        assert metrics["Exit_Signal"] == "WARNING"
        assert "Hourly_Low_Breach" in metrics["Exit_Triggers"]

    def test_vwap_3bar_returns_exit(self):
        """PE-28: VWAP 3-bar violation → EXIT (sustained structural deterioration)."""
        df = _make_exit_df_a(vwap_offset=-5.0, low_breach=False)
        state = _make_state()
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_a(state, df, last, -1, 1.0, metrics, _cfg_a())
        assert result == "EXIT"
        assert metrics["Exit_Signal"] == "EXIT"
        assert "VWAP_3Bar_Violation" in metrics["Exit_Triggers"]

    def test_both_triggers_returns_exit(self):
        """PE-28: Both triggers → EXIT."""
        df = _make_exit_df_a(vwap_offset=-5.0, low_breach=True)
        state = _make_state()
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_a(state, df, last, -1, 1.0, metrics, _cfg_a())
        assert result == "EXIT"
        assert "Hourly_Low_Breach" in metrics["Exit_Triggers"]
        assert "VWAP_3Bar_Violation" in metrics["Exit_Triggers"]

    def test_graduation_false_to_warning_to_exit(self):
        """PE-28 graduation sequence: False → WARNING → EXIT."""
        state = _make_state()

        # 1. No triggers → False
        df1 = _make_exit_df_a(vwap_offset=5.0, low_breach=False)
        m1 = {}
        r1 = _exit_profile_a(state, df1, df1.iloc[-1], -1, 1.0, m1, _cfg_a())
        assert r1 is False

        # 2. Hourly low breach only → WARNING
        df2 = _make_exit_df_a(vwap_offset=5.0, low_breach=True)
        m2 = {}
        r2 = _exit_profile_a(state, df2, df2.iloc[-1], -1, 1.0, m2, _cfg_a())
        assert r2 == "WARNING"

        # 3. VWAP 3-bar → EXIT
        df3 = _make_exit_df_a(vwap_offset=-5.0, low_breach=False)
        m3 = {}
        r3 = _exit_profile_a(state, df3, df3.iloc[-1], -1, 1.0, m3, _cfg_a())
        assert r3 == "EXIT"

    def test_vwap_counter_metric_written(self):
        """Exit_VWAP_Counter metric is written."""
        df = _make_exit_df_a(vwap_offset=-5.0)
        state = _make_state()
        metrics = {}
        _exit_profile_a(state, df, df.iloc[-1], -1, 1.0, metrics, _cfg_a())
        assert "Exit_VWAP_Counter" in metrics
        assert metrics["Exit_VWAP_Counter"] == "3/3"

    def test_established_hourly_low_metric(self):
        """Established_Hourly_Low metric is surfaced (PE-27)."""
        df = _make_exit_df_a(vwap_offset=5.0)
        state = _make_state()
        metrics = {}
        _exit_profile_a(state, df, df.iloc[-1], -1, 1.0, metrics, _cfg_a())
        assert "Established_Hourly_Low" in metrics

    def test_price_scaler_applied(self):
        """Established_Hourly_Low is divided by price_scaler."""
        df = _make_exit_df_a(vwap_offset=5.0)
        state = _make_state()
        m1 = {}
        _exit_profile_a(state, df, df.iloc[-1], -1, 1.0, m1, _cfg_a())
        m2 = {}
        _exit_profile_a(state, df, df.iloc[-1], -1, 100.0, m2, _cfg_a())
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
        """CVX-003: EMA 8 breach for C-3 with 2-bar counter → EXIT (thesis invalidation)."""
        df = _make_exit_df_b(consec_below_ema8=2)
        state = _make_state(is_resolving=True, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert "EMA_8_Counter_Exit" in metrics["Exit_Triggers"]

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
# TestExitProfileB_C3 — CVX-003 C-3 Three-Tier Exit Model (Scenarios 1–9)
# ===========================================================================

class TestExitProfileB_C3:
    """C-3 specific tests for the redesigned _exit_profile_b.

    All tests pass _is_c3=True. Covers state-independent EMA 8, graduated
    2-bar counter, SMA 50 downgrade, SMA 200 catastrophic backstop.
    """

    def test_scenario_1_c3_above_all_mas(self):
        """Scenario 1: C-3 above all MAs → False with Exit_EMA8_Counter='0/2'."""
        df = _make_exit_df_b()
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result is False
        assert metrics["Exit_Signal"] is False
        assert metrics["Exit_EMA8_Counter"] == "0/2"

    def test_scenario_2_c3_ema8_1bar_resolving(self):
        """Scenario 2: C-3 EMA 8 breach, 1 bar (RESOLVING) → WARNING, counter 1/2."""
        df = _make_exit_df_b(consec_below_ema8=1)
        state = _make_state(is_resolving=True, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "WARNING"
        assert metrics["Exit_EMA8_Counter"] == "1/2"
        assert "EMA_8_Counter_Warning" in metrics["Exit_Triggers"]

    def test_scenario_3_c3_ema8_2bar_resolving(self):
        """Scenario 3: C-3 EMA 8 breach, 2 bars (RESOLVING) → EXIT, counter 2/2."""
        df = _make_exit_df_b(consec_below_ema8=2)
        state = _make_state(is_resolving=True, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert metrics["Exit_EMA8_Counter"] == "2/2"
        assert "EMA_8_Counter_Exit" in metrics["Exit_Triggers"]
        assert "thesis invalidation" in metrics["Exit_Reason"]

    def test_scenario_4_c3_ema8_1bar_trending_blindspot_fix(self):
        """Scenario 4: C-3 EMA 8, 1 bar (TRENDING) → WARNING. Blindspot fix."""
        df = _make_exit_df_b(consec_below_ema8=1)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "WARNING"
        assert "EMA_8_Counter_Warning" in metrics["Exit_Triggers"]

    def test_scenario_5_c3_ema8_2bar_trending_blindspot_fix(self):
        """Scenario 5: C-3 EMA 8, 2 bars (TRENDING) → EXIT. State-independent + counter."""
        df = _make_exit_df_b(consec_below_ema8=2)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert "EMA_8_Counter_Exit" in metrics["Exit_Triggers"]

    def test_scenario_6_c3_sma50_downgraded(self):
        """Scenario 6: C-3 SMA 50 breach → WARNING (downgraded from EXIT)."""
        df = _make_exit_df_b(below_sma50=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "WARNING"
        assert "SMA_50_Downgrade" in metrics["Exit_Triggers"]
        assert "C-3 WARNING" in metrics["Exit_Reason"]

    def test_scenario_7_c3_sma200_catastrophic(self):
        """Scenario 7: C-3 SMA 200 breach → EXIT (catastrophic backstop)."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]
        assert "catastrophic backstop" in metrics["Exit_Reason"]

    def test_scenario_8_c3_sma50_plus_ema8_2bar(self):
        """Scenario 8: C-3 SMA 50 + EMA 8 (2 bars) → EXIT. EMA 8 counter wins (priority 2 > 3)."""
        df = _make_exit_df_b(below_sma50=True, consec_below_ema8=2)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "EXIT"
        # EMA 8 counter EXIT (priority 2) should fire before SMA 50 downgrade (priority 3)
        assert "EMA_8_Counter_Exit" in metrics["Exit_Triggers"]

    def test_scenario_9_c3_etf_logic_lock_bypass(self):
        """Scenario 9: C-3 ETF EMA 8 with is_resolving=False → EXIT. Logic Lock bypass."""
        df = _make_exit_df_b(consec_below_ema8=2)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert "EMA_8_Counter_Exit" in metrics["Exit_Triggers"]


# ===========================================================================
# TestExitProfileB_C1C2_Regression — Zero-Change Guarantee (Scenarios 10–13)
# ===========================================================================

class TestExitProfileB_C1C2_Regression:
    """Zero behavioral change regression tests. All tests pass _is_c3=False."""

    def test_scenario_10_c1c2_sma50_breach(self):
        """Scenario 10: C-1/C-2 SMA 50 breach → EXIT (unchanged)."""
        df = _make_exit_df_b(below_sma50=True)
        state = _make_state()
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert "SMA_50_Breach" in metrics["Exit_Triggers"]
        assert metrics["Exit_Reason"] == "Close below 50-SMA"

    def test_scenario_11_c1c2_ema8_breach_resolving(self):
        """Scenario 11: C-1/C-2 EMA 8 breach (RESOLVING) → WARNING (unchanged, no counter)."""
        df = _make_exit_df_b(below_ema8=True)
        state = _make_state(is_resolving=True, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        assert result == "WARNING"
        assert "EMA_8_Convexity_Breach" in metrics["Exit_Triggers"]
        assert "Exit_EMA8_Counter" not in metrics

    def test_scenario_12_c1c2_ema8_breach_trending(self):
        """Scenario 12: C-1/C-2 EMA 8 breach (TRENDING) → False (state gate active)."""
        df = _make_exit_df_b(below_ema8=True)
        state = _make_state(is_resolving=True, is_trending=True)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        # EMA 8 gate blocked by is_trending for C-1/C-2
        if last['close'] >= last['SMA_50']:
            assert result is False

    def test_scenario_13_c1c2_above_all_mas(self):
        """Scenario 13: C-1/C-2 above all MAs → False (unchanged)."""
        df = _make_exit_df_b()
        state = _make_state(is_resolving=True, is_trending=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics)
        assert result is False
        assert metrics["Exit_Signal"] is False
        assert "Exit_EMA8_Counter" not in metrics


# ===========================================================================
# TestComputeExitSignals_CVX003 — FFD-001 Interaction (Scenarios 14–18)
# ===========================================================================

class TestComputeExitSignals_CVX003:
    """FFD-001 interaction tests through the _compute_exit_signals dispatcher."""

    def test_scenario_14_c3_sma50_warning_no_floor_failure(self):
        """Scenario 14: C-3 SMA 50 WARNING, no floor failure → WARNING (override skipped)."""
        df = _make_exit_df_b(below_sma50=True)
        state = _make_state(is_floor_failure=False)
        metrics = {}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], True, None, -1, 1.0, metrics, _cfg_b()
        )
        assert result == "WARNING"
        assert metrics["Exit_Signal"] == "WARNING"

    def test_scenario_15_c3_sma50_warning_floor_fail_consolidation(self):
        """Scenario 15: C-3 SMA 50 WARNING + floor fail + CONSOLIDATION → WARNING (FLOOR BREACH)."""
        df = _make_exit_df_b(below_sma50=True)
        state = _make_state(is_floor_failure=True, consec_below=4, _reclaim_run=1)
        metrics = {"Floor_Failure_Context": "CONSOLIDATION"}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], True, None, -1, 1.0, metrics, _cfg_b()
        )
        assert result == "WARNING"
        assert metrics["Exit_Signal"] == "WARNING"
        assert "FLOOR BREACH" in metrics["Exit_Reason"]

    def test_scenario_16_c3_sma50_warning_floor_fail_structural(self):
        """Scenario 16: C-3 SMA 50 WARNING + floor fail + STRUCTURAL_BREAKDOWN → EXIT."""
        df = _make_exit_df_b(below_sma50=True)
        state = _make_state(is_floor_failure=True, consec_below=5, _reclaim_run=0)
        metrics = {"Floor_Failure_Context": "STRUCTURAL_BREAKDOWN"}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], True, None, -1, 1.0, metrics, _cfg_b()
        )
        assert result == "EXIT"
        assert metrics["Exit_Signal"] == "EXIT"
        assert "FLOOR FAILURE OVERRIDE" in metrics["Exit_Reason"]

    def test_scenario_17_c3_ema8_exit_floor_failure_skipped(self):
        """Scenario 17: C-3 EMA 8 EXIT + floor failure → EXIT (override skipped, already EXIT)."""
        df = _make_exit_df_b(consec_below_ema8=2)
        state = _make_state(is_floor_failure=True, consec_below=5, _reclaim_run=0)
        metrics = {"Floor_Failure_Context": "STRUCTURAL_BREAKDOWN"}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], True, None, -1, 1.0, metrics, _cfg_b()
        )
        assert result == "EXIT"
        # Override skipped because already EXIT — no Floor_Failure_Override trigger
        assert "Floor_Failure_Override" not in metrics.get("Exit_Triggers", [])

    def test_scenario_18_c3_sma200_exit_floor_failure_skipped(self):
        """Scenario 18: C-3 SMA 200 EXIT + floor failure → EXIT (override skipped, already EXIT)."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_floor_failure=True, consec_below=5, _reclaim_run=0)
        metrics = {"Floor_Failure_Context": "STRUCTURAL_BREAKDOWN"}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], True, None, -1, 1.0, metrics, _cfg_b()
        )
        assert result == "EXIT"
        assert "Floor_Failure_Override" not in metrics.get("Exit_Triggers", [])


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
            state, "A", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_a()
        )
        assert result is False

    def test_dispatches_to_profile_b(self):
        """Dispatcher routes Profile B correctly."""
        df = _make_exit_df_b()
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_b()
        )
        assert result is False

    def test_dispatches_to_profile_c(self):
        """Dispatcher routes Profile C correctly."""
        df = _make_exit_df_c()
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "C", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_c()
        )
        assert result is False

    def test_unknown_profile_returns_false(self):
        """Unknown profile code → False with 'None' triggers."""
        df = _make_exit_df_b()
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "Z", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_b()
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
            state, "A", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_a()
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
            state, "A", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_a()
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
            state, "A", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_a()
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
            state, "B", df, df.iloc[-1], False, target_1_b, -1, 1.0, metrics, _cfg_b()
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
            state, "B", df, df.iloc[-1], False, target_1_b, -1, 1.0, metrics, _cfg_b()
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
            state, "B", df, df.iloc[-1], False, target_1_b, -1, 1.0, metrics, _cfg_b()
        )
        assert result is False
        assert metrics.get("Profit_Target_Synthetic") == 150.0

    def test_pe7b_reward_risk_suppressed_on_exit(self):
        """PE-7b: Reward_Risk suppressed when exit_signal = EXIT."""
        df = _make_exit_df_b(below_sma50=True)  # EXIT
        state = _make_state()
        metrics = {"Reward_Risk": 1.5, "Profit_Target": 160.0}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_b()
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
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_b()
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
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_b()
        )
        assert result == "EXIT"
        assert "Reward_Risk_Note" not in metrics

    def test_pe25_floor_failure_profile_b(self):
        """PE-25: Floor failure override works for Profile B."""
        df = _make_exit_df_b()  # No trigger → False
        state = _make_state(is_floor_failure=True, consec_below=4, _reclaim_run=0)
        metrics = {}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_b()
        )
        assert result == "EXIT"
        assert "Floor_Failure_Override" in metrics["Exit_Triggers"]

    def test_pe25_floor_failure_profile_c(self):
        """PE-25: Floor failure override works for Profile C."""
        df = _make_exit_df_c()  # No trigger → False
        state = _make_state(is_floor_failure=True, consec_below=4, _reclaim_run=0)
        metrics = {}
        result = _compute_exit_signals(
            state, "C", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_c()
        )
        assert result == "EXIT"
        assert "Floor_Failure_Override" in metrics["Exit_Triggers"]

    def test_return_type_is_native(self):
        """All return types are native Python (not numpy.bool_)."""
        df = _make_exit_df_b()
        state = _make_state()
        metrics = {}
        result = _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics, _cfg_b()
        )
        assert type(result) in (bool, str)


# ===========================================================================
# Helper: build minimal weekly df_ctx for CVX-003-OBS-1 tests
# ===========================================================================

def _make_weekly_df_ctx(golden_cross=True, sma50_rising=True,
                        sma50_nan=False, sma200_nan=False):
    """Build a minimal weekly DataFrame for Priority 1 weekly context guard.

    Args:
        golden_cross: If True, weekly SMA 50 > SMA 200 (golden cross present).
        sma50_rising: If True, weekly SMA 50 current > prior (rising).
        sma50_nan: If True, set SMA 50 values to NaN.
        sma200_nan: If True, set SMA 200 values to NaN.
    """
    # Two rows minimum: prior week and current week
    sma200_val = 100.0
    if golden_cross:
        sma50_current = 120.0
    else:
        sma50_current = 90.0  # below SMA 200 → no golden cross

    if sma50_rising:
        sma50_prior = sma50_current - 1.30  # rising
    else:
        sma50_prior = sma50_current + 1.30  # falling

    df_ctx = pd.DataFrame({
        'close': [110.0, 112.0],
        'SMA_50': [sma50_prior, sma50_current],
        'SMA_200': [sma200_val, sma200_val],
    })

    if sma50_nan:
        df_ctx['SMA_50'] = float('nan')
    if sma200_nan:
        df_ctx['SMA_200'] = float('nan')

    return df_ctx


# ===========================================================================
# CVX-003-OBS-1: Weekly Context Cross-Check for Priority 1 (Tests 1–7)
# ===========================================================================

class TestCVX003_OBS1_WeeklyContextGuard:
    """Regression tests for CVX-003-OBS-1 Option B: Weekly context cross-check
    on the SMA 200 catastrophic backstop (Priority 1) in _exit_profile_b.
    """

    def test_obs1_priority1_fires_when_weekly_broken(self):
        """Test 1: Priority 1 fires when weekly structure is broken (no golden cross)."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        df_ctx = _make_weekly_df_ctx(golden_cross=False, sma50_rising=True)
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]
        assert metrics["Exit_Signal"] == "EXIT"

    def test_obs1_priority1_skipped_when_weekly_intact(self):
        """Test 2: Priority 1 skipped when weekly structure intact (GC + rising).
        Falls through to Priority 3 (SMA 50 WARNING) since close < SMA 200 implies
        close < SMA 50 in this fixture."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        df_ctx = _make_weekly_df_ctx(golden_cross=True, sma50_rising=True)
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        # Priority 1 skipped → should NOT be SMA_200_Catastrophic EXIT
        assert "SMA_200_Catastrophic" not in metrics.get("Exit_Triggers", [])
        # close < SMA 200 implies close < SMA 50 → Priority 3 SMA 50 downgrade
        assert result == "WARNING"
        assert "SMA_50_Downgrade" in metrics["Exit_Triggers"]

    def test_obs1_priority1_fires_when_df_ctx_none(self):
        """Test 3: Priority 1 fires when df_ctx is None (conservative fallback)."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=None)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]

    def test_obs1_priority1_fires_when_weekly_sma_nan(self):
        """Test 4: Priority 1 fires when weekly SMA data is NaN (conservative)."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        # SMA 50 is NaN → cannot determine weekly structure → conservative EXIT
        df_ctx = _make_weekly_df_ctx(sma50_nan=True)
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]

        # Also test SMA 200 NaN
        metrics2 = {}
        df_ctx2 = _make_weekly_df_ctx(sma200_nan=True)
        result2 = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics2, df_ctx=df_ctx2)
        assert result2 == "EXIT"
        assert "SMA_200_Catastrophic" in metrics2["Exit_Triggers"]

    def test_obs1_c1c2_unaffected(self):
        """Test 5: C-1/C-2 unaffected — Priority 1 block not entered (_is_c3=False).
        Weekly context guard does not alter C-1/C-2 behaviour."""
        df = _make_exit_df_b(below_sma50=True)
        state = _make_state()
        last = df.iloc[-1]
        # With df_ctx (should be ignored for C-1/C-2)
        df_ctx = _make_weekly_df_ctx(golden_cross=True, sma50_rising=True)
        metrics_with = {}
        result_with = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics_with, df_ctx=df_ctx)
        # Without df_ctx
        metrics_without = {}
        result_without = _exit_profile_b(state, df, last, False, None, -1, 1.0, metrics_without, df_ctx=None)
        # Both should produce identical results
        assert result_with == result_without
        assert metrics_with["Exit_Signal"] == metrics_without["Exit_Signal"]
        assert metrics_with["Exit_Triggers"] == metrics_without["Exit_Triggers"]

    def test_obs1_priority1_skipped_falls_to_priority2(self):
        """Test 6: Priority 1 skipped, falls correctly to Priority 2 (EMA 8 counter EXIT).
        Confirms elif chain works when Priority 1 is bypassed."""
        df = _make_exit_df_b(below_sma200=True, consec_below_ema8=2)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        df_ctx = _make_weekly_df_ctx(golden_cross=True, sma50_rising=True)
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        # Priority 1 skipped (weekly intact), Priority 2 fires (EMA 8 counter >= 2)
        assert result == "EXIT"
        assert "EMA_8_Counter_Exit" in metrics["Exit_Triggers"]
        assert "SMA_200_Catastrophic" not in metrics["Exit_Triggers"]

    def test_obs1_backward_compat_no_df_ctx_param(self):
        """Test 7: Backward compatibility — calling _exit_profile_b without df_ctx
        parameter (default None). Priority 1 fires unconditionally (same as pre-fix)."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        # Call WITHOUT df_ctx keyword — relies on default=None
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]
        assert metrics["Exit_Reason"] == "Close below 200-SMA -- C-3 catastrophic backstop"

    # ------------------------------------------------------------------
    # Gap-closing tests (P3, P4, P7, P8, P9c, P9d)
    # ------------------------------------------------------------------

    def test_obs1_priority1_fires_when_df_ctx_too_short(self):
        """P3: df_ctx with < 2 rows → conservative EXIT (cannot compute rising)."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        # Single-row df_ctx — not enough for prior-week comparison
        df_ctx = pd.DataFrame({
            'close': [110.0],
            'SMA_50': [120.0],
            'SMA_200': [100.0],
        })
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]

    def test_obs1_priority1_fires_when_df_ctx_missing_columns(self):
        """P4: df_ctx present but missing SMA columns → conservative EXIT."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        # df_ctx with enough rows but no SMA columns
        df_ctx = pd.DataFrame({
            'close': [110.0, 112.0],
            'volume': [1000000, 1100000],
        })
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]

    def test_obs1_priority1_fires_gc_true_rising_false(self):
        """P7: GC=True but SMA 50 declining → _weekly_intact=False → FIRES.
        Unit test complement to PG live verification."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        df_ctx = _make_weekly_df_ctx(golden_cross=True, sma50_rising=False)
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]

    def test_obs1_priority1_fires_gc_false_rising_false(self):
        """P8: GC=False AND SMA 50 declining → _weekly_intact=False → FIRES."""
        df = _make_exit_df_b(below_sma200=True)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        df_ctx = _make_weekly_df_ctx(golden_cross=False, sma50_rising=False)
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        assert result == "EXIT"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"]

    def test_obs1_skipped_falls_to_priority4_ema8_warning(self):
        """P9c: Weekly intact + EMA 8 counter=1 → Priority 1 skipped, Priority 4 WARNING."""
        df = _make_exit_df_b(below_sma200=True, consec_below_ema8=1)
        state = _make_state(is_trending=True, is_resolving=False)
        last = df.iloc[-1]
        metrics = {}
        df_ctx = _make_weekly_df_ctx(golden_cross=True, sma50_rising=True)
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        assert "SMA_200_Catastrophic" not in metrics.get("Exit_Triggers", [])
        # below_sma200 implies below SMA_50 → Priority 3 may fire before Priority 4.
        # Either way, Priority 1 is skipped.
        assert result in ("WARNING", "EXIT")
        assert result != "EXIT" or "EMA_8_Counter_Exit" in metrics["Exit_Triggers"]

    def test_obs1_skipped_falls_to_no_trigger(self):
        """P9d: Weekly intact + close below SMA 200 but above all other triggers → False.
        Requires close < SMA 200 but >= SMA 50 and >= EMA 8. Achievable by forcing
        SMA 200 above SMA 50 (inverted ordering, the PLTR pattern)."""
        df = _make_exit_df_b(below_sma200=False)  # start with normal df
        state = _make_state(is_trending=True, is_resolving=False)
        # Force inverted ordering: SMA 200 above close, but close above SMA 50 and EMA 8
        last_idx = -1
        sma50_val = df['SMA_50'].iloc[last_idx]
        ema8_val = df['EMA_8'].iloc[last_idx]
        # Place close above SMA 50 and EMA 8
        safe_close = max(sma50_val, ema8_val) + 1.0
        df.iloc[last_idx, df.columns.get_loc('close')] = safe_close
        # Force SMA 200 above close (inverted)
        df.iloc[last_idx, df.columns.get_loc('SMA_200')] = safe_close + 5.0
        last = df.iloc[last_idx]
        metrics = {}
        df_ctx = _make_weekly_df_ctx(golden_cross=True, sma50_rising=True)
        result = _exit_profile_b(state, df, last, True, None, -1, 1.0, metrics, df_ctx=df_ctx)
        # Priority 1 skipped (weekly intact), no other trigger fires
        assert "SMA_200_Catastrophic" not in metrics.get("Exit_Triggers", [])
        assert result is False
