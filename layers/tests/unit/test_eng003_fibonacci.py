"""ENG-003: Fibonacci Retracement Confluence Diagnostic — Unit Tests

Tests the ENG-003 computation block in isolation using crafted DataFrames
and known inputs. Same inline-testing pattern as test_phase4_extractions.py.

Rally leg reference: Origin = 100.0, Peak = 110.0, Range = 10.0
  Fib 38.2% level = 110.0 - 0.382 * 10.0 = 106.18
  Fib 50.0% level = 110.0 - 0.500 * 10.0 = 105.00

bars_per_day = 6.5 (US) → session_bars = int(6.5 * 3) = 19
atr_raw = 2.0 → 0.5 * ATR = 1.0  (range 10.0 clears easily)
price_scaler = 1.0
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helper: build a DataFrame with controlled high/low over a lookback window
# ---------------------------------------------------------------------------
def _build_df(num_bars, origin, peak, close_price):
    """Build a DataFrame where the last `session_bars` bars (excluding the
    final evaluation bar) contain the given origin (low.min) and peak (high.max).

    The evaluation bar (iloc[-1]) carries `close_price` and is excluded from
    the lookback window by the ENG-003 slice `df.iloc[-(session_bars+1):-1]`.
    """
    data = {
        'open':  [origin + 1.0] * num_bars,
        'high':  [origin + 2.0] * num_bars,  # baseline high
        'low':   [origin + 0.5] * num_bars,  # baseline low above origin
        'close': [origin + 1.0] * num_bars,
    }
    df = pd.DataFrame(data)

    # Plant the peak and origin inside the 3-session lookback window.
    # session_bars = 19 (for bars_per_day=6.5). Window = iloc[-(19+1):-1] = iloc[-20:-1].
    # So the window covers indices [num_bars-20, num_bars-2] inclusive.
    # Place peak at the start of window, origin at the end.
    window_start = num_bars - 20  # iloc[-(19+1)]
    window_end = num_bars - 2     # iloc[-2] (last bar in window)

    df.loc[window_start, 'high'] = peak
    df.loc[window_end, 'low'] = origin

    # Evaluation bar (last row) — this is the "current bar"
    df.loc[num_bars - 1, 'close'] = close_price

    return df


def _run_eng003(p_code, is_etf, bars_per_day, atr_raw, df, close_price, price_scaler=1.0):
    """Execute the ENG-003 computation block and return the 3 Fib_A_ metric fields."""
    metrics = {}
    state = SimpleNamespace(atr_raw=atr_raw)
    last = df.iloc[-1].copy()
    last['close'] = close_price  # ensure close matches

    _fib_a_session_bars = int(bars_per_day * 3)
    _fib_a_min_bars = int(bars_per_day * 2)

    if p_code == "A" and not is_etf:
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

    return metrics


# ===========================================================================
# Constants for all tests
# ===========================================================================
BARS_PER_DAY = 6.5      # US market
SESSION_BARS = int(BARS_PER_DAY * 3)  # 19
ATR_RAW = 2.0
ORIGIN = 100.0
PEAK = 110.0
RANGE = PEAK - ORIGIN   # 10.0
FIB_382 = PEAK - 0.382 * RANGE  # 106.18
FIB_500 = PEAK - 0.500 * RANGE  # 105.00
NUM_BARS = 25  # Comfortable margin above 19 + 1 = 20
PRICE_SCALER = 1.0


# ===========================================================================
# SCOPE GUARD TESTS (3)
# ===========================================================================

class TestENG003ScopeGuards:
    """Tests 1-3: scope guards that should null all Fib_A fields."""

    def test_eng003_scope_profile_b_returns_none(self):
        """p_code == 'B' → all three Fib_A fields are None."""
        df = _build_df(NUM_BARS, ORIGIN, PEAK, close_price=106.18)
        metrics = _run_eng003("B", False, BARS_PER_DAY, ATR_RAW, df, 106.18)

        assert metrics["Fib_A_382_Level"] is None
        assert metrics["Fib_A_500_Level"] is None
        assert metrics["Fib_A_Confluence"] is None

    def test_eng003_scope_etf_returns_none(self):
        """p_code == 'A' but is_etf == True → all three fields None."""
        df = _build_df(NUM_BARS, ORIGIN, PEAK, close_price=106.18)
        metrics = _run_eng003("A", True, BARS_PER_DAY, ATR_RAW, df, 106.18)

        assert metrics["Fib_A_382_Level"] is None
        assert metrics["Fib_A_500_Level"] is None
        assert metrics["Fib_A_Confluence"] is None

    def test_eng003_scope_insufficient_bars(self):
        """DataFrame has fewer bars than session_bars + 1 → all three fields None."""
        # session_bars = 19, need > 20 bars. Provide only 15.
        small_df = _build_df(15, ORIGIN, PEAK, close_price=106.18)
        metrics = _run_eng003("A", False, BARS_PER_DAY, ATR_RAW, small_df, 106.18)

        assert metrics["Fib_A_382_Level"] is None
        assert metrics["Fib_A_500_Level"] is None
        assert metrics["Fib_A_Confluence"] is None


# ===========================================================================
# DEGENERATE GUARD TEST (1)
# ===========================================================================

class TestENG003DegenerateGuard:
    """Test 4: range below 0.5 * ATR → null all fields."""

    def test_eng003_degenerate_range_below_half_atr(self):
        """3-session window with range < 0.5 ATR → all three fields None."""
        # ATR = 2.0, so 0.5 * ATR = 1.0. Build a flat window where range < 1.0.
        # All bars have high=100.4, low=100.0 → range = 0.4 < 1.0
        num = NUM_BARS
        data = {
            'open':  [100.2] * num,
            'high':  [100.4] * num,
            'low':   [100.0] * num,
            'close': [100.2] * num,
        }
        df = pd.DataFrame(data)
        df.loc[num - 1, 'close'] = 100.2
        metrics = _run_eng003("A", False, BARS_PER_DAY, ATR_RAW, df, 100.2)

        assert metrics["Fib_A_382_Level"] is None
        assert metrics["Fib_A_500_Level"] is None
        assert metrics["Fib_A_Confluence"] is None


# ===========================================================================
# CONFLUENCE CLASSIFICATION TESTS (5)
# ===========================================================================

class TestENG003ConfluenceClassification:
    """Tests 5-9: verify each of the 5 confluence classification values."""

    def test_eng003_confluence_382(self):
        """Price within ±0.5% of 38.2% level → CONFLUENCE_382.

        Fib 38.2% = 106.18. Tolerance = 0.005 * 106.18 = 0.5309.
        Price = 106.18 → abs(106.18 - 106.18) = 0 ≤ 0.5309 ✓
        """
        df = _build_df(NUM_BARS, ORIGIN, PEAK, close_price=106.18)
        metrics = _run_eng003("A", False, BARS_PER_DAY, ATR_RAW, df, 106.18)

        assert metrics["Fib_A_382_Level"] == round(FIB_382, 2)
        assert metrics["Fib_A_500_Level"] == round(FIB_500, 2)
        assert metrics["Fib_A_Confluence"] == "CONFLUENCE_382"

    def test_eng003_confluence_500(self):
        """Price within ±0.5% of 50.0% level → CONFLUENCE_500.

        Fib 50.0% = 105.00. Tolerance = 0.005 * 105.00 = 0.525.
        Price = 105.00 → abs(105.00 - 105.00) = 0 ≤ 0.525 ✓
        Must NOT be within 382 tolerance: abs(105.00 - 106.18) = 1.18 > 0.5309 ✓
        """
        df = _build_df(NUM_BARS, ORIGIN, PEAK, close_price=105.00)
        metrics = _run_eng003("A", False, BARS_PER_DAY, ATR_RAW, df, 105.00)

        assert metrics["Fib_A_382_Level"] == round(FIB_382, 2)
        assert metrics["Fib_A_500_Level"] == round(FIB_500, 2)
        assert metrics["Fib_A_Confluence"] == "CONFLUENCE_500"

    def test_eng003_between_fibs(self):
        """Price between 38.2% and 50.0% but outside tolerance of both → BETWEEN_FIBS.

        Fib 38.2% = 106.18, Fib 50.0% = 105.00.
        Price = 105.60 → between 105.00 and 106.18.
        Tolerance 382 = 0.5309 → abs(105.60 - 106.18) = 0.58 > 0.5309 ✓
        Tolerance 500 = 0.525  → abs(105.60 - 105.00) = 0.60 > 0.525 ✓
        """
        df = _build_df(NUM_BARS, ORIGIN, PEAK, close_price=105.60)
        metrics = _run_eng003("A", False, BARS_PER_DAY, ATR_RAW, df, 105.60)

        assert metrics["Fib_A_382_Level"] == round(FIB_382, 2)
        assert metrics["Fib_A_500_Level"] == round(FIB_500, 2)
        assert metrics["Fib_A_Confluence"] == "BETWEEN_FIBS"

    def test_eng003_above_fibs(self):
        """Price above 38.2% level → ABOVE_FIBS.

        Fib 38.2% = 106.18. Tolerance = 0.5309.
        Price = 108.00 → 108.00 > 106.18 and abs(108.00 - 106.18) = 1.82 > 0.5309 ✓
        """
        df = _build_df(NUM_BARS, ORIGIN, PEAK, close_price=108.00)
        metrics = _run_eng003("A", False, BARS_PER_DAY, ATR_RAW, df, 108.00)

        assert metrics["Fib_A_382_Level"] == round(FIB_382, 2)
        assert metrics["Fib_A_500_Level"] == round(FIB_500, 2)
        assert metrics["Fib_A_Confluence"] == "ABOVE_FIBS"

    def test_eng003_below_fibs(self):
        """Price below 50.0% level → BELOW_FIBS.

        Fib 50.0% = 105.00. Tolerance = 0.525.
        Price = 103.00 → 103.00 < 105.00 and abs(103.00 - 105.00) = 2.00 > 0.525 ✓
        """
        df = _build_df(NUM_BARS, ORIGIN, PEAK, close_price=103.00)
        metrics = _run_eng003("A", False, BARS_PER_DAY, ATR_RAW, df, 103.00)

        assert metrics["Fib_A_382_Level"] == round(FIB_382, 2)
        assert metrics["Fib_A_500_Level"] == round(FIB_500, 2)
        assert metrics["Fib_A_Confluence"] == "BELOW_FIBS"
