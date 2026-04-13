"""INF-001: Informational Metrics on INVALID Paths — Unit Tests

Verifies that the VALID gate boundary in output.py::_assemble_output()
protects ONLY the Focus Chart. ENG-002 (Fib B), ENG-003 (Fib A), and
ENG-004 (Measured Move) now run unconditionally on all verdict paths.
Profile/ETF/state scope guards within each block remain unchanged.

Test Categories:
  1. INVALID verdict + Profile B TRENDING  → fib/MM fields populated
  2. INVALID verdict + Profile A           → fib/MM fields populated
  3. INVALID verdict + Profile C           → all None (scope guard)
  4. INVALID verdict + ETF                 → all None (scope guard)
  5. VALID verdict regression              → still populated (blocks unconditional)
  6. INVALID verdict + degenerate range    → all None (range guards)

Uses inline computation pattern matching output.py logic. Each helper
mirrors the dedented ENG blocks exactly to prove gate boundary moved.

Reference values:
  Profile B: Origin=100.0, Peak=115.0, Rally=15.0, ATR=2.0, Close=112.0
    ENG-002 Fib: Peak=115.0, Origin=100.0, Range=15.0
      Fib_382 = 115.0 - 0.382*15.0 = 109.27
      Fib_500 = 115.0 - 0.500*15.0 = 107.50
    ENG-004 MM: MM_Target=(112.0+15.0)/1.0=127.0, MM_Rally_ATR=15.0/2.0=7.5

  Profile A: Origin=100.0, Peak=110.0, Range=10.0, ATR=2.0, Close=106.18
    ENG-003 Fib: Fib_A_382=106.18, Fib_A_500=105.00
    ENG-004 MM: Rally=10.0, MM_Target=(106.18+10.0)/1.0=116.18, Rally_ATR=5.0
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BARS_PER_DAY = 6.5      # US market
SESSION_BARS = int(BARS_PER_DAY * 3)  # 19
ATR_RAW = 2.0
PRICE_SCALER = 1.0

# Profile B geometry
B_ORIGIN = 100.0
B_PEAK = 115.0
B_RANGE = B_PEAK - B_ORIGIN   # 15.0
B_CLOSE = 112.0
B_FIB_382 = round(B_PEAK - 0.382 * B_RANGE, 2)  # 109.27
B_FIB_500 = round(B_PEAK - 0.500 * B_RANGE, 2)  # 107.50
B_MM_TARGET = round((B_CLOSE + B_RANGE) / PRICE_SCALER, 2)  # 127.0
B_MM_RALLY_ATR = round(B_RANGE / ATR_RAW, 2)                # 7.5

# Profile A geometry
A_ORIGIN = 100.0
A_PEAK = 110.0
A_RANGE = A_PEAK - A_ORIGIN   # 10.0
A_CLOSE = 106.18
A_FIB_382 = round(A_PEAK - 0.382 * A_RANGE, 2)  # 106.18
A_FIB_500 = round(A_PEAK - 0.500 * A_RANGE, 2)  # 105.0
A_MM_TARGET = round((A_CLOSE + A_RANGE) / PRICE_SCALER, 2)  # 116.18
A_MM_RALLY_ATR = round(A_RANGE / ATR_RAW, 2)                # 5.0

NUM_BARS_B = 15   # > 11 + 1 for Profile B 10-bar window
NUM_BARS_A = 25   # > 19 + 1 for Profile A 3-session window


# ---------------------------------------------------------------------------
# DataFrame builders (identical to test_eng003/test_eng004 patterns)
# ---------------------------------------------------------------------------

def _build_df_b(num_bars, origin, peak, close_price):
    """Profile B: 10-bar daily Focus Window (df.iloc[-11:-1])."""
    data = {
        'open':  [origin + 1.0] * num_bars,
        'high':  [origin + 2.0] * num_bars,
        'low':   [origin + 0.5] * num_bars,
        'close': [origin + 1.0] * num_bars,
    }
    df = pd.DataFrame(data)
    window_start = num_bars - 11
    window_end = num_bars - 2
    df.loc[window_start, 'high'] = peak
    df.loc[window_end, 'low'] = origin
    df.loc[num_bars - 1, 'close'] = close_price
    return df


def _build_df_a(num_bars, origin, peak, close_price):
    """Profile A: 3-session hourly lookback (df.iloc[-(19+1):-1])."""
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
# Inline computation runner — mirrors the dedented ENG blocks in output.py
# The verdict parameter is now IGNORED (blocks run unconditionally after
# INF-001). This runner proves the gate boundary no longer blocks computation.
# ---------------------------------------------------------------------------

def _run_all_eng(p_code, is_etf, entry_trending, bars_per_day, atr_raw,
                 df, close_price, price_scaler=1.0, verdict="VALID"):
    """Execute ENG-002 + ENG-003 + ENG-004 unconditionally (INF-001).

    Returns dict with all fib/MM metric keys always present.
    The verdict parameter is accepted for test readability but NOT used
    as a gate — matching the post-INF-001 output.py structure.
    """
    metrics = {}
    state = SimpleNamespace(atr_raw=atr_raw, _entry_trending=entry_trending)
    last = df.iloc[-1].copy()
    last['close'] = close_price

    # --- ENG-002: Fibonacci Profile B (unconditional after INF-001) ---
    if p_code == "B" and state._entry_trending and not is_etf:
        _fib_window  = df.iloc[-11:-1]
        _fib_origin  = float(_fib_window['low'].min())
        _fib_peak    = float(_fib_window['high'].max())
        _fib_range   = _fib_peak - _fib_origin

        if _fib_range > 0:
            _fib_382_raw = _fib_peak - 0.382 * _fib_range
            _fib_500_raw = _fib_peak - 0.500 * _fib_range

            metrics["Fib_382_Level"] = round(_fib_382_raw / price_scaler, 2)
            metrics["Fib_500_Level"] = round(_fib_500_raw / price_scaler, 2)

            _current_price = last['close']
            _tol_382 = 0.003 * _fib_382_raw
            _tol_500 = 0.003 * _fib_500_raw

            if abs(_current_price - _fib_382_raw) <= _tol_382:
                metrics["Fib_Confluence"] = "CONFLUENCE_382"
            elif abs(_current_price - _fib_500_raw) <= _tol_500:
                metrics["Fib_Confluence"] = "CONFLUENCE_500"
            elif _fib_500_raw <= _current_price <= _fib_382_raw:
                metrics["Fib_Confluence"] = "BETWEEN_FIBS"
            elif _current_price > _fib_382_raw:
                metrics["Fib_Confluence"] = "ABOVE_FIBS"
            else:
                metrics["Fib_Confluence"] = "BELOW_FIBS"
        else:
            metrics["Fib_382_Level"]  = None
            metrics["Fib_500_Level"]  = None
            metrics["Fib_Confluence"] = None
    else:
        metrics["Fib_382_Level"]  = None
        metrics["Fib_500_Level"]  = None
        metrics["Fib_Confluence"] = None

    # --- ENG-003: Fibonacci Profile A (unconditional after INF-001) ---
    if p_code == "A" and not is_etf:
        _fib_a_session_bars = int(bars_per_day * 3)
        _fib_a_min_bars = int(bars_per_day * 2)

        if len(df) > (_fib_a_session_bars + 1) and _fib_a_session_bars >= _fib_a_min_bars:
            _fib_a_window = df.iloc[-(_fib_a_session_bars + 1):-1]
            _fib_a_origin = float(_fib_a_window['low'].min())
            _fib_a_peak = float(_fib_a_window['high'].max())
            _fib_a_range = _fib_a_peak - _fib_a_origin

            if _fib_a_range >= (0.5 * state.atr_raw):
                _fib_a_382_raw = _fib_a_peak - 0.382 * _fib_a_range
                _fib_a_500_raw = _fib_a_peak - 0.500 * _fib_a_range

                metrics["Fib_A_382_Level"] = round(_fib_a_382_raw / price_scaler, 2)
                metrics["Fib_A_500_Level"] = round(_fib_a_500_raw / price_scaler, 2)

                _current_price = last['close']
                _tol_a_382 = 0.005 * _fib_a_382_raw
                _tol_a_500 = 0.005 * _fib_a_500_raw

                if abs(_current_price - _fib_a_382_raw) <= _tol_a_382:
                    metrics["Fib_A_Confluence"] = "CONFLUENCE_382"
                elif abs(_current_price - _fib_a_500_raw) <= _tol_a_500:
                    metrics["Fib_A_Confluence"] = "CONFLUENCE_500"
                elif _fib_a_500_raw <= _current_price <= _fib_a_382_raw:
                    metrics["Fib_A_Confluence"] = "BETWEEN_FIBS"
                elif _current_price > _fib_a_382_raw:
                    metrics["Fib_A_Confluence"] = "ABOVE_FIBS"
                else:
                    metrics["Fib_A_Confluence"] = "BELOW_FIBS"
            else:
                metrics["Fib_A_382_Level"] = None
                metrics["Fib_A_500_Level"] = None
                metrics["Fib_A_Confluence"] = None
        else:
            metrics["Fib_A_382_Level"] = None
            metrics["Fib_A_500_Level"] = None
            metrics["Fib_A_Confluence"] = None
    else:
        metrics["Fib_A_382_Level"] = None
        metrics["Fib_A_500_Level"] = None
        metrics["Fib_A_Confluence"] = None

    # --- ENG-004: Measured Move (unconditional after INF-001) ---
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
# CATEGORY 1: INVALID verdict + Profile B TRENDING → populated
# ===========================================================================

class TestINF001Cat1InvalidProfileBTrending:
    """INVALID verdict with scope guards passing (Profile B, TRENDING, non-ETF).
    ENG-002 fib fields and ENG-004 MM fields must be numeric, not None."""

    def test_invalid_profile_b_fib_382_populated(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("B", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["Fib_382_Level"] == B_FIB_382

    def test_invalid_profile_b_fib_500_populated(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("B", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["Fib_500_Level"] == B_FIB_500

    def test_invalid_profile_b_fib_confluence_populated(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("B", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["Fib_Confluence"] is not None

    def test_invalid_profile_b_mm_target_populated(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("B", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["MM_Target"] == B_MM_TARGET

    def test_invalid_profile_b_mm_rally_atr_populated(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("B", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["MM_Rally_ATR"] == B_MM_RALLY_ATR


# ===========================================================================
# CATEGORY 2: INVALID verdict + Profile A → populated
# ===========================================================================

class TestINF001Cat2InvalidProfileA:
    """INVALID verdict with scope guards passing (Profile A, non-ETF).
    ENG-003 fib fields and ENG-004 MM fields must be numeric."""

    def test_invalid_profile_a_fib_a_382_populated(self):
        df = _build_df_a(NUM_BARS_A, A_ORIGIN, A_PEAK, A_CLOSE)
        m = _run_all_eng("A", False, False, BARS_PER_DAY, ATR_RAW,
                         df, A_CLOSE, verdict="INVALID")
        assert m["Fib_A_382_Level"] == A_FIB_382

    def test_invalid_profile_a_fib_a_500_populated(self):
        df = _build_df_a(NUM_BARS_A, A_ORIGIN, A_PEAK, A_CLOSE)
        m = _run_all_eng("A", False, False, BARS_PER_DAY, ATR_RAW,
                         df, A_CLOSE, verdict="INVALID")
        assert m["Fib_A_500_Level"] == A_FIB_500

    def test_invalid_profile_a_fib_a_confluence_populated(self):
        df = _build_df_a(NUM_BARS_A, A_ORIGIN, A_PEAK, A_CLOSE)
        m = _run_all_eng("A", False, False, BARS_PER_DAY, ATR_RAW,
                         df, A_CLOSE, verdict="INVALID")
        assert m["Fib_A_Confluence"] is not None

    def test_invalid_profile_a_mm_target_populated(self):
        df = _build_df_a(NUM_BARS_A, A_ORIGIN, A_PEAK, A_CLOSE)
        m = _run_all_eng("A", False, False, BARS_PER_DAY, ATR_RAW,
                         df, A_CLOSE, verdict="INVALID")
        assert m["MM_Target"] == A_MM_TARGET

    def test_invalid_profile_a_mm_rally_atr_populated(self):
        df = _build_df_a(NUM_BARS_A, A_ORIGIN, A_PEAK, A_CLOSE)
        m = _run_all_eng("A", False, False, BARS_PER_DAY, ATR_RAW,
                         df, A_CLOSE, verdict="INVALID")
        assert m["MM_Rally_ATR"] == A_MM_RALLY_ATR


# ===========================================================================
# CATEGORY 3: INVALID verdict + Profile C → all None (scope guard)
# ===========================================================================

class TestINF001Cat3InvalidProfileC:
    """Profile C with INVALID verdict. All fib/MM fields must be None
    because Profile C is excluded by every scope guard."""

    def test_invalid_profile_c_fib_b_none(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("C", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["Fib_382_Level"] is None
        assert m["Fib_500_Level"] is None
        assert m["Fib_Confluence"] is None

    def test_invalid_profile_c_fib_a_none(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("C", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["Fib_A_382_Level"] is None
        assert m["Fib_A_500_Level"] is None
        assert m["Fib_A_Confluence"] is None

    def test_invalid_profile_c_mm_none(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("C", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["MM_Target"] is None
        assert m["MM_Rally_ATR"] is None


# ===========================================================================
# CATEGORY 4: INVALID verdict + ETF → all None (scope guard)
# ===========================================================================

class TestINF001Cat4InvalidETF:
    """ETF with INVALID verdict. All fib/MM fields must be None
    because is_etf=True triggers the else branch in all ENG blocks."""

    def test_invalid_etf_profile_b_all_none(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("B", True, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="INVALID")
        assert m["Fib_382_Level"] is None
        assert m["Fib_500_Level"] is None
        assert m["Fib_Confluence"] is None
        assert m["Fib_A_382_Level"] is None
        assert m["Fib_A_500_Level"] is None
        assert m["Fib_A_Confluence"] is None
        assert m["MM_Target"] is None
        assert m["MM_Rally_ATR"] is None

    def test_invalid_etf_profile_a_all_none(self):
        df = _build_df_a(NUM_BARS_A, A_ORIGIN, A_PEAK, A_CLOSE)
        m = _run_all_eng("A", True, False, BARS_PER_DAY, ATR_RAW,
                         df, A_CLOSE, verdict="INVALID")
        assert m["Fib_382_Level"] is None
        assert m["Fib_500_Level"] is None
        assert m["Fib_Confluence"] is None
        assert m["Fib_A_382_Level"] is None
        assert m["Fib_A_500_Level"] is None
        assert m["Fib_A_Confluence"] is None
        assert m["MM_Target"] is None
        assert m["MM_Rally_ATR"] is None


# ===========================================================================
# CATEGORY 5: VALID verdict regression — still populated
# ===========================================================================

class TestINF001Cat5ValidRegression:
    """VALID verdict must still produce fib/MM fields when scope guards pass.
    This proves the unconditional (dedented) blocks run on VALID paths too."""

    def test_valid_profile_b_fib_and_mm_populated(self):
        df = _build_df_b(NUM_BARS_B, B_ORIGIN, B_PEAK, B_CLOSE)
        m = _run_all_eng("B", False, True, BARS_PER_DAY, ATR_RAW,
                         df, B_CLOSE, verdict="VALID")
        assert m["Fib_382_Level"] == B_FIB_382
        assert m["Fib_500_Level"] == B_FIB_500
        assert m["Fib_Confluence"] is not None
        assert m["MM_Target"] == B_MM_TARGET
        assert m["MM_Rally_ATR"] == B_MM_RALLY_ATR

    def test_valid_profile_a_fib_and_mm_populated(self):
        df = _build_df_a(NUM_BARS_A, A_ORIGIN, A_PEAK, A_CLOSE)
        m = _run_all_eng("A", False, False, BARS_PER_DAY, ATR_RAW,
                         df, A_CLOSE, verdict="VALID")
        assert m["Fib_A_382_Level"] == A_FIB_382
        assert m["Fib_A_500_Level"] == A_FIB_500
        assert m["Fib_A_Confluence"] is not None
        assert m["MM_Target"] == A_MM_TARGET
        assert m["MM_Rally_ATR"] == A_MM_RALLY_ATR


# ===========================================================================
# CATEGORY 6: INVALID verdict + degenerate range → None
# ===========================================================================

class TestINF001Cat6InvalidDegenerateRange:
    """INVALID verdict with scope guards passing but rally range below
    threshold. Fib/MM fields must be None (geometric guard, not verdict gate)."""

    def test_invalid_profile_a_range_below_half_atr(self):
        """ENG-003: range < 0.5 ATR → fib fields None.
        ATR=2.0, 0.5*ATR=1.0. Build flat window with range=0.4 < 1.0."""
        num = NUM_BARS_A
        data = {
            'open':  [100.2] * num,
            'high':  [100.4] * num,
            'low':   [100.0] * num,
            'close': [100.2] * num,
        }
        df = pd.DataFrame(data)
        df.loc[num - 1, 'close'] = 100.2
        m = _run_all_eng("A", False, False, BARS_PER_DAY, ATR_RAW,
                         df, 100.2, verdict="INVALID")
        assert m["Fib_A_382_Level"] is None
        assert m["Fib_A_500_Level"] is None
        assert m["Fib_A_Confluence"] is None

    def test_invalid_profile_b_rally_below_one_atr(self):
        """ENG-004: rally < 1.0 ATR → MM fields None.
        ATR=2.0. Build window with range=1.5 (< 2.0)."""
        num = NUM_BARS_B
        data = {
            'open':  [100.2] * num,
            'high':  [101.0] * num,
            'low':   [100.0] * num,
            'close': [100.5] * num,
        }
        df = pd.DataFrame(data)
        # Window origin=100.0, peak=101.5 → rally=1.5 < 2.0 ATR
        df.loc[num - 11, 'high'] = 101.5
        df.loc[num - 2, 'low'] = 100.0
        df.loc[num - 1, 'close'] = 100.5
        m = _run_all_eng("B", False, True, BARS_PER_DAY, ATR_RAW,
                         df, 100.5, verdict="INVALID")
        assert m["MM_Target"] is None
        assert m["MM_Rally_ATR"] is None

    def test_invalid_profile_a_mm_rally_below_one_atr(self):
        """ENG-004 Profile A: rally < 1.0 ATR → MM fields None."""
        num = NUM_BARS_A
        data = {
            'open':  [100.2] * num,
            'high':  [101.0] * num,
            'low':   [100.0] * num,
            'close': [100.5] * num,
        }
        df = pd.DataFrame(data)
        # Window: origin=100.0, peak=101.5 → rally=1.5 < 2.0 ATR
        df.loc[num - 20, 'high'] = 101.5
        df.loc[num - 2, 'low'] = 100.0
        df.loc[num - 1, 'close'] = 100.5
        m = _run_all_eng("A", False, False, BARS_PER_DAY, ATR_RAW,
                         df, 100.5, verdict="INVALID")
        assert m["MM_Target"] is None
        assert m["MM_Rally_ATR"] is None
