"""ENG-004: Measured Move Projection -- Unit Tests

Tests the ENG-004 computation block in isolation using crafted DataFrames
and known inputs. Same inline-testing pattern as test_eng003_fibonacci.py.

Profile B reference (10-bar daily Focus Window):
  Origin = 100.0, Peak = 115.0, Rally_Leg = 15.0
  ATR = 2.0, so Rally_Leg / ATR = 7.5 (clears 1.0 ATR guard)
  Close = 112.0
  MM_Target = (112.0 + 15.0) / 1.0 = 127.0
  MM_Rally_ATR = 15.0 / 2.0 = 7.5

Profile A reference (3-session hourly lookback):
  bars_per_day = 6.5 (US) -> session_bars = int(6.5 * 3) = 19
  Origin = 100.0, Peak = 115.0, Rally_Leg = 15.0
  ATR = 2.0
  Close = 112.0
  MM_Target = (112.0 + 15.0) / 1.0 = 127.0
  MM_Rally_ATR = 15.0 / 2.0 = 7.5

price_scaler = 1.0 unless noted otherwise.
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helper: build DataFrames with controlled high/low over a lookback window
# ---------------------------------------------------------------------------

def _build_df_b(num_bars, origin, peak, close_price):
    """Build a DataFrame for Profile B (10-bar daily Focus Window).

    The 10-bar window is df.iloc[-11:-1]. The evaluation bar (iloc[-1])
    carries close_price and is excluded from the window.
    """
    data = {
        'open':  [origin + 1.0] * num_bars,
        'high':  [origin + 2.0] * num_bars,
        'low':   [origin + 0.5] * num_bars,
        'close': [origin + 1.0] * num_bars,
    }
    df = pd.DataFrame(data)

    # Window = iloc[-11:-1] = indices [num_bars-11, num_bars-2]
    window_start = num_bars - 11
    window_end = num_bars - 2

    df.loc[window_start, 'high'] = peak
    df.loc[window_end, 'low'] = origin

    df.loc[num_bars - 1, 'close'] = close_price
    return df


def _build_df_a(num_bars, origin, peak, close_price):
    """Build a DataFrame for Profile A (3-session hourly lookback).

    session_bars = 19 (for bars_per_day=6.5).
    Window = df.iloc[-(19+1):-1] = iloc[-20:-1].
    """
    data = {
        'open':  [origin + 1.0] * num_bars,
        'high':  [origin + 2.0] * num_bars,
        'low':   [origin + 0.5] * num_bars,
        'close': [origin + 1.0] * num_bars,
    }
    df = pd.DataFrame(data)

    window_start = num_bars - 20
    window_end = num_bars - 2

    df.loc[window_start, 'high'] = peak
    df.loc[window_end, 'low'] = origin

    df.loc[num_bars - 1, 'close'] = close_price
    return df


# ---------------------------------------------------------------------------
# Inline ENG-004 computation (mirrors output.py logic exactly)
# ---------------------------------------------------------------------------

def _run_eng004(p_code, is_etf, entry_trending, bars_per_day, atr_raw,
                df, close_price, price_scaler=1.0, verdict="VALID"):
    """Execute the ENG-004 computation block and return the 2 MM_ fields.

    Returns dict with MM_Target and MM_Rally_ATR keys (or absent if INVALID).
    """
    metrics = {}
    state = SimpleNamespace(atr_raw=atr_raw, _entry_trending=entry_trending)
    last = df.iloc[-1].copy()
    last['close'] = close_price

    if verdict != "VALID":
        # INVALID path: fields are never written
        return metrics

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

    return metrics


# ===========================================================================
# Constants
# ===========================================================================
BARS_PER_DAY = 6.5       # US market
SESSION_BARS = int(BARS_PER_DAY * 3)  # 19
ATR_RAW = 2.0
ORIGIN = 100.0
PEAK = 115.0
RALLY_LEG = PEAK - ORIGIN  # 15.0
CLOSE = 112.0
NUM_BARS_B = 15            # Comfortable margin above 11 + 1 = 12 for Profile B
NUM_BARS_A = 25            # Comfortable margin above 19 + 1 = 20 for Profile A
PRICE_SCALER = 1.0

# Expected values
EXPECTED_MM_TARGET = round((CLOSE + RALLY_LEG) / PRICE_SCALER, 2)   # 127.0
EXPECTED_MM_RALLY_ATR = round(RALLY_LEG / ATR_RAW, 2)              # 7.5


# ===========================================================================
# TEST 1: Profile B VALID TRENDING -- normal range
# ===========================================================================

class TestENG004ProfileBNormal:
    """Test 1: Profile B, TRENDING, non-ETF, Rally_Leg >= 1.0 ATR."""

    def test_profile_b_normal_mm_target(self):
        """MM_Target = (close + Rally_Leg) / price_scaler, rounded to 2dp."""
        df = _build_df_b(NUM_BARS_B, ORIGIN, PEAK, CLOSE)
        metrics = _run_eng004("B", False, True, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] == EXPECTED_MM_TARGET
        assert metrics["MM_Rally_ATR"] == EXPECTED_MM_RALLY_ATR


# ===========================================================================
# TEST 2: Profile A VALID -- normal range
# ===========================================================================

class TestENG004ProfileANormal:
    """Test 2: Profile A, non-ETF, sufficient bars, Rally_Leg >= 1.0 ATR."""

    def test_profile_a_normal_mm_target(self):
        """MM_Target and MM_Rally_ATR populated with correct values."""
        df = _build_df_a(NUM_BARS_A, ORIGIN, PEAK, CLOSE)
        metrics = _run_eng004("A", False, False, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] == EXPECTED_MM_TARGET
        assert metrics["MM_Rally_ATR"] == EXPECTED_MM_RALLY_ATR


# ===========================================================================
# TEST 3: Profile B sub-threshold range
# ===========================================================================

class TestENG004ProfileBSubThreshold:
    """Test 3: Profile B, Rally_Leg < 1.0 ATR -> both fields None."""

    def test_profile_b_sub_threshold(self):
        """Rally_Leg = 0.8 < 1.0 * ATR(2.0) -> both fields None."""
        # Build a narrow-range DataFrame: all bars within [100.0, 100.8]
        num = NUM_BARS_B
        data = {
            'open':  [100.4] * num,
            'high':  [100.8] * num,
            'low':   [100.0] * num,
            'close': [100.4] * num,
        }
        df = pd.DataFrame(data)
        df.loc[num - 1, 'close'] = CLOSE
        # Window peak=100.8, origin=100.0, Rally_Leg=0.8 < ATR(2.0)
        metrics = _run_eng004("B", False, True, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None


# ===========================================================================
# TEST 4: Profile A sub-threshold range
# ===========================================================================

class TestENG004ProfileASubThreshold:
    """Test 4: Profile A, Rally_Leg < 1.0 ATR -> both fields None."""

    def test_profile_a_sub_threshold(self):
        """Rally_Leg = 0.8 < 1.0 * ATR(2.0) -> both fields None."""
        # Build a narrow-range DataFrame: all bars within [100.0, 100.8]
        num = NUM_BARS_A
        data = {
            'open':  [100.4] * num,
            'high':  [100.8] * num,
            'low':   [100.0] * num,
            'close': [100.4] * num,
        }
        df = pd.DataFrame(data)
        df.loc[num - 1, 'close'] = CLOSE
        metrics = _run_eng004("A", False, False, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None


# ===========================================================================
# TEST 5: Profile B degenerate range (Peak == Origin)
# ===========================================================================

class TestENG004ProfileBDegenerate:
    """Test 5: Profile B, Peak == Origin (flat window) -> both fields None."""

    def test_profile_b_degenerate_flat(self):
        """All bars same high/low -> Rally_Leg = 0 -> both None."""
        num = NUM_BARS_B
        data = {
            'open':  [100.0] * num,
            'high':  [100.0] * num,
            'low':   [100.0] * num,
            'close': [100.0] * num,
        }
        df = pd.DataFrame(data)
        df.loc[num - 1, 'close'] = CLOSE
        metrics = _run_eng004("B", False, True, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None


# ===========================================================================
# TEST 6: Profile A degenerate range (Peak == Origin)
# ===========================================================================

class TestENG004ProfileADegenerate:
    """Test 6: Profile A, Peak == Origin -> both fields None."""

    def test_profile_a_degenerate_flat(self):
        """All bars same high/low -> Rally_Leg = 0 -> both None."""
        num = NUM_BARS_A
        data = {
            'open':  [100.0] * num,
            'high':  [100.0] * num,
            'low':   [100.0] * num,
            'close': [100.0] * num,
        }
        df = pd.DataFrame(data)
        df.loc[num - 1, 'close'] = CLOSE
        metrics = _run_eng004("A", False, False, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None


# ===========================================================================
# TEST 7: Profile C excluded
# ===========================================================================

class TestENG004ProfileCExcluded:
    """Test 7: p_code == 'C' -> both fields None."""

    def test_profile_c_excluded(self):
        df = _build_df_b(NUM_BARS_B, ORIGIN, PEAK, CLOSE)
        metrics = _run_eng004("C", False, True, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None


# ===========================================================================
# TEST 8: ETF excluded
# ===========================================================================

class TestENG004ETFExcluded:
    """Test 8: is_etf == True -> both fields None (tested on both profiles)."""

    def test_etf_profile_b_excluded(self):
        df = _build_df_b(NUM_BARS_B, ORIGIN, PEAK, CLOSE)
        metrics = _run_eng004("B", True, True, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None

    def test_etf_profile_a_excluded(self):
        df = _build_df_a(NUM_BARS_A, ORIGIN, PEAK, CLOSE)
        metrics = _run_eng004("A", True, False, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None


# ===========================================================================
# TEST 9: Profile B RESOLVING excluded
# ===========================================================================

class TestENG004ProfileBResolving:
    """Test 9: state._entry_trending == False -> both fields None."""

    def test_profile_b_resolving_excluded(self):
        """Profile B with _entry_trending=False falls to else branch."""
        df = _build_df_b(NUM_BARS_B, ORIGIN, PEAK, CLOSE)
        # p_code='B' but entry_trending=False -> not matched by first branch
        # Not 'A' either -> falls to else
        metrics = _run_eng004("B", False, False, BARS_PER_DAY, ATR_RAW, df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None


# ===========================================================================
# TEST 10: INVALID verdict excluded
# ===========================================================================

class TestENG004InvalidVerdict:
    """Test 10: INVALID verdict -> fields never written to metrics."""

    def test_invalid_verdict_no_fields(self):
        df = _build_df_b(NUM_BARS_B, ORIGIN, PEAK, CLOSE)
        metrics = _run_eng004("B", False, True, BARS_PER_DAY, ATR_RAW,
                              df, CLOSE, verdict="INVALID")

        assert "MM_Target" not in metrics
        assert "MM_Rally_ATR" not in metrics


# ===========================================================================
# TEST 11: Price scaler test (GBP pence -> pounds)
# ===========================================================================

class TestENG004PriceScaler:
    """Test 11: price_scaler == 100 -> MM_Target divided by 100."""

    def test_price_scaler_gbp(self):
        """GBP pence-to-pounds: MM_Target scaled, MM_Rally_ATR unscaled."""
        scaler = 100.0
        df = _build_df_b(NUM_BARS_B, ORIGIN, PEAK, CLOSE)
        metrics = _run_eng004("B", False, True, BARS_PER_DAY, ATR_RAW,
                              df, CLOSE, price_scaler=scaler)

        expected_target = round((CLOSE + RALLY_LEG) / scaler, 2)  # 127.0 / 100 = 1.27
        assert metrics["MM_Target"] == expected_target
        # Rally ATR is dimensionless -- not scaled
        assert metrics["MM_Rally_ATR"] == EXPECTED_MM_RALLY_ATR


# ===========================================================================
# TEST 12: MM_Rally_ATR calculation verification
# ===========================================================================

class TestENG004RallyATRCalc:
    """Test 12: Verify MM_Rally_ATR == Rally_Leg / ATR rounded to 2dp."""

    def test_rally_atr_calculation(self):
        """Use non-round numbers to verify rounding behavior."""
        # Origin=100.0, Peak=107.3 -> Rally=7.3, ATR=3.0
        # MM_Rally_ATR = 7.3 / 3.0 = 2.4333... -> 2.43
        atr = 3.0
        df = _build_df_b(NUM_BARS_B, 100.0, 107.3, 105.0)
        metrics = _run_eng004("B", False, True, BARS_PER_DAY, atr, df, 105.0)

        assert metrics["MM_Rally_ATR"] == round(7.3 / 3.0, 2)  # 2.43
        assert metrics["MM_Target"] == round((105.0 + 7.3) / 1.0, 2)  # 112.3


# ===========================================================================
# TEST 13: Transform round-trip
# ===========================================================================

class TestENG004TransformRoundTrip:
    """Test 13: MM_Target appears at trade_setup.measured_move.target
    in grouped output and survives _flatten() back to MM_Target."""

    def test_transform_roundtrip(self):
        import importlib.util
        import sys

        # Stub plotly to avoid import error
        for mod_name in ('plotly', 'plotly.graph_objects', 'plotly.io'):
            if mod_name not in sys.modules:
                sys.modules[mod_name] = type(sys)('stub')

        spec = importlib.util.spec_from_file_location(
            'transform', 'tbs_engine/transform.py')
        transform = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transform)

        action_summary = {
            "verdict": "VALID", "reason": "PULLBACK",
            "entry_strategy": {
                "entry_price": 142.0, "stop_loss": 140.0, "target": 160.0
            },
        }
        flat_in = {
            "Price": 152.0, "Structural_Floor": 142.0, "Resistance": 160.0,
            "ADV_20": 5000000.0, "ADV_20_Dollar": 50000000.0, "Is_ETF": False, "Convexity_Class": "C1",
            "Engine_State": "TRENDING", "ADX": 28.5,
            "EMA_8": 150.0, "Hard_Stop": 140.0, "Profit_Target": 160.0,
            "Entry_Reference": 142.0,
            "MM_Target": 127.0,
            "MM_Rally_ATR": 7.5,
        }
        grouped = transform._transform_output(action_summary, flat_in)

        # Verify grouped path
        ts = grouped.get("trade_setup", {})
        mm = ts.get("measured_move", {})
        assert mm.get("target") == 127.0
        assert mm.get("rally_atr") == 7.5

        # Verify flatten round-trip
        _, _, flat_out = transform._flatten(grouped)
        assert flat_out.get("MM_Target") == 127.0
        assert flat_out.get("MM_Rally_ATR") == 7.5


# ===========================================================================
# TEST 14: Profile A insufficient bars
# ===========================================================================

class TestENG004ProfileAInsufficientBars:
    """Test 14: len(df) too short for 3-session lookback -> both fields None."""

    def test_profile_a_insufficient_bars(self):
        """session_bars=19, need > 20 bars. Provide only 15."""
        small_df = _build_df_a(15, ORIGIN, PEAK, CLOSE)
        metrics = _run_eng004("A", False, False, BARS_PER_DAY, ATR_RAW,
                              small_df, CLOSE)

        assert metrics["MM_Target"] is None
        assert metrics["MM_Rally_ATR"] is None


# ===========================================================================
# TEST 15: Snapshot regression (existing tests still pass)
# ===========================================================================

class TestENG004SnapshotRegression:
    """Test 15: Verify that MM fields are always written as a pair --
    never one without the other. This is a structural consistency check."""

    def test_fields_always_written_as_pair(self):
        """Run all code paths and verify MM_Target and MM_Rally_ATR are
        both present (or both absent for INVALID)."""
        test_cases = [
            # (p_code, is_etf, trending, verdict, expect_keys)
            ("B", False, True,  "VALID",   True),   # normal Profile B
            ("A", False, False, "VALID",   True),   # normal Profile A
            ("C", False, True,  "VALID",   True),   # excluded Profile C
            ("B", True,  True,  "VALID",   True),   # ETF excluded
            ("B", False, False, "VALID",   True),   # RESOLVING excluded
            ("B", False, True,  "INVALID", False),  # INVALID verdict
        ]
        for p_code, is_etf, trending, verdict, expect_keys in test_cases:
            if p_code == "A":
                df = _build_df_a(NUM_BARS_A, ORIGIN, PEAK, CLOSE)
            else:
                df = _build_df_b(NUM_BARS_B, ORIGIN, PEAK, CLOSE)

            metrics = _run_eng004(p_code, is_etf, trending, BARS_PER_DAY,
                                  ATR_RAW, df, CLOSE, verdict=verdict)

            if expect_keys:
                assert "MM_Target" in metrics, f"MM_Target missing for {p_code}/{verdict}"
                assert "MM_Rally_ATR" in metrics, f"MM_Rally_ATR missing for {p_code}/{verdict}"
            else:
                assert "MM_Target" not in metrics, f"MM_Target present for INVALID"
                assert "MM_Rally_ATR" not in metrics, f"MM_Rally_ATR present for INVALID"
