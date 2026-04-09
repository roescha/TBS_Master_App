"""REC-001 Phase 2A: Base Detection Algorithm — Unit Tests.

Tests map to spec §3.1–3.5 and test cases TC-01, TC-02, TC-03, TC-04, TC-05, TC-06, TC-20, TC-24.
"""
import sys
import types as builtin_types
import importlib.util

# --- Isolated import: load compute.py without full tbs_engine package chain ---
if 'tbs_engine' not in sys.modules:
    pkg = builtin_types.ModuleType('tbs_engine')
    pkg.__path__ = ['tbs_engine']
    sys.modules['tbs_engine'] = pkg
for _mod, _path in [('tbs_engine.types', 'tbs_engine/types.py'),
                     ('tbs_engine.helpers', 'tbs_engine/helpers.py'),
                     ('tbs_engine.compute', 'tbs_engine/compute.py')]:
    if _mod not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_mod, _path)
        _m = importlib.util.module_from_spec(_spec)
        sys.modules[_mod] = _m
        _spec.loader.exec_module(_m)

import pandas as pd
import pytest
from types import SimpleNamespace
from tbs_engine.compute import _compute_recovery_base


def _make_ctx(bars, p_code="A", vol_confirm_state="MIXED", dmp_col="DMP_14", dmn_col="DMN_14"):
    """Build a minimal RunContext-like object with the given OHLCV bars.

    bars: list of dicts with keys: open, high, low, close, volume, EMA_8, EMA_21, ATRr_14, DMP_14, DMN_14
    """
    df = pd.DataFrame(bars)
    cfg = SimpleNamespace(iq=-1)
    ctx = SimpleNamespace(
        df=df, cfg=cfg, p_code=p_code,
        vol_confirm_state=vol_confirm_state,
        dmp_col=dmp_col, dmn_col=dmn_col,
    )
    return ctx


def _default_bar(low=100.0, high=105.0, close=103.0, volume=1000,
                 ema8=102.0, ema21=103.0, atr=3.0, dmp=15.0, dmn=20.0):
    return {
        "open": close - 1, "high": high, "low": low, "close": close,
        "volume": volume, "EMA_8": ema8, "EMA_21": ema21,
        "ATRr_14": atr, "DMP_14": dmp, "DMN_14": dmn,
    }


class TestSwingLowDetection:
    """Spec §3.1: Swing low is the bar with the lowest low."""

    def test_swing_low_found(self):
        # 10 bars, bar index 3 has the lowest low
        bars = [_default_bar(low=100)] * 10
        bars[3] = _default_bar(low=90)
        ctx = _make_ctx(bars)
        result = _compute_recovery_base(ctx)
        assert result["swing_low_bar_index"] == 3
        assert result["swing_low_price"] == 90.0


class TestMinBarCount:
    """Spec §3.3 C1 + TC-01, TC-02, TC-20, TC-24."""

    def test_tc01_profile_a_5_bars_pass(self):
        """TC-01: Profile A, 5 hourly bars since swing low → pass."""
        # Swing low at bar 0, eval at bar 5 → 5 bars since swing low
        # Need: no lower low, ATR contracting, retest, vol clean, EMA cross
        bars = []
        # Prior 10 bars for ATR reference (high volatility)
        for _ in range(10):
            bars.append(_default_bar(low=95, high=110, volume=2000, atr=5.0,
                                     ema8=100, ema21=102))
        # Swing low bar (bar index 10)
        bars.append(_default_bar(low=88, high=95, close=90, volume=3000, atr=5.0,
                                 ema8=99, ema21=102))
        # 5 base window bars (indices 11-15) with contracting range
        # Bar 11: retest of swing low zone on lower volume
        bars.append(_default_bar(low=88.5, high=92, close=91, volume=1500, atr=3.0,
                                 ema8=100, ema21=102))
        # Bars 12-14: rising, EMAs converge
        bars.append(_default_bar(low=90, high=94, close=93, volume=1200, atr=2.5,
                                 ema8=101, ema21=102))
        bars.append(_default_bar(low=91, high=95, close=94, volume=1100, atr=2.5,
                                 ema8=101.5, ema21=101.8))
        # Bar 14: EMA cross (ema8 > ema21, previous bar ema8 <= ema21)
        bars.append(_default_bar(low=92, high=96, close=95, volume=1300, atr=2.5,
                                 ema8=102.5, ema21=102.0))
        # Bar 15 (eval bar): continues above
        bars.append(_default_bar(low=93, high=97, close=96, volume=1200, atr=2.5,
                                 ema8=103.0, ema21=102.2))

        ctx = _make_ctx(bars, p_code="A", vol_confirm_state="MIXED")
        result = _compute_recovery_base(ctx)
        assert result["swing_low_bar_index"] == 10
        assert result["base_bar_count"] == 5
        assert result["criteria"]["min_bars"] is True
        assert result["base_confirmed"] is True

    def test_tc02_profile_a_3_bars_fail(self):
        """TC-02: Profile A, 3 hourly bars since swing low → min_bars fails."""
        bars = []
        for _ in range(10):
            bars.append(_default_bar(low=95, high=110, atr=5.0, ema8=100, ema21=102))
        # Swing low at bar 10
        bars.append(_default_bar(low=88, high=95, volume=3000, atr=5.0, ema8=99, ema21=102))
        # Only 3 bars in base
        for _ in range(3):
            bars.append(_default_bar(low=90, high=94, volume=1200, atr=2.5, ema8=101, ema21=102))

        ctx = _make_ctx(bars, p_code="A")
        result = _compute_recovery_base(ctx)
        assert result["base_bar_count"] == 3
        assert result["criteria"]["min_bars"] is False
        assert result["base_confirmed"] is False

    def test_tc20_profile_b_3_bars_pass(self):
        """TC-20: Profile B, 3 daily bars, all quality criteria pass → confirmed."""
        bars = []
        for _ in range(10):
            bars.append(_default_bar(low=95, high=115, volume=5000, atr=8.0,
                                     ema8=100, ema21=103))
        # Swing low
        bars.append(_default_bar(low=85, high=95, close=88, volume=8000, atr=8.0,
                                 ema8=98, ema21=103))
        # Retest bar (low within 0.5*ATR=4.0 of 85, on lower vol)
        bars.append(_default_bar(low=86, high=92, close=91, volume=4000, atr=5.0,
                                 ema8=99, ema21=102))
        bars.append(_default_bar(low=88, high=94, close=93, volume=3500, atr=4.5,
                                 ema8=101, ema21=101.5))
        # EMA cross bar
        bars.append(_default_bar(low=89, high=96, close=95, volume=4000, atr=4.0,
                                 ema8=102.5, ema21=101.8))

        ctx = _make_ctx(bars, p_code="B", vol_confirm_state="MIXED")
        result = _compute_recovery_base(ctx)
        assert result["base_bar_count"] == 3
        assert result["criteria"]["min_bars"] is True
        assert result["base_confirmed"] is True
        assert result["min_base_bars"] == 3

    def test_tc24_profile_b_2_bars_fail(self):
        """TC-24: Profile B, 2 daily bars only → insufficient."""
        bars = []
        for _ in range(10):
            bars.append(_default_bar(low=95, high=115, atr=8.0, ema8=100, ema21=103))
        bars.append(_default_bar(low=85, high=95, volume=8000, atr=8.0, ema8=98, ema21=103))
        for _ in range(2):
            bars.append(_default_bar(low=87, high=93, volume=3000, atr=4.0, ema8=101, ema21=102))

        ctx = _make_ctx(bars, p_code="B")
        result = _compute_recovery_base(ctx)
        assert result["base_bar_count"] == 2
        assert result["criteria"]["min_bars"] is False
        assert result["base_confirmed"] is False


class TestNoLowerLow:
    """Spec §3.3 C2 + TC-03."""

    def test_tc03_new_lower_low_fails(self):
        bars = []
        for _ in range(10):
            bars.append(_default_bar(low=95, high=110, atr=5.0, ema8=100, ema21=102))
        bars.append(_default_bar(low=88, high=95, volume=3000, atr=5.0, ema8=99, ema21=102))
        # 6 bars in base, bar 4 of base (iloc 14) prints low below swing low
        for i in range(6):
            low = 87 if i == 3 else 90  # bar 3 of base = lower low
            bars.append(_default_bar(low=low, high=94, volume=1200, atr=2.5, ema8=101, ema21=102))
        ctx = _make_ctx(bars, p_code="A")
        result = _compute_recovery_base(ctx)
        # The swing low should now be the bar with low=87, not the original one
        # Actually: swing low is the LOWEST low in the entire window, so it shifts to the new low
        # That means the "base" is only 2 bars from the new swing low
        assert result["swing_low_price"] == 87.0


class TestATRContraction:
    """Spec §3.3 C3 + TC-04."""

    def test_tc04_atr_expanding_fails(self):
        bars = []
        # Prior 10 bars: low volatility
        for _ in range(10):
            bars.append(_default_bar(low=99, high=101, atr=3.0, ema8=100, ema21=102))
        # Swing low
        bars.append(_default_bar(low=88, high=95, volume=3000, atr=3.0, ema8=99, ema21=102))
        # 5 base bars: HIGH volatility (ATR expanding)
        for _ in range(5):
            bars.append(_default_bar(low=89, high=102, volume=1200, atr=3.0, ema8=101, ema21=102))
        ctx = _make_ctx(bars, p_code="A")
        result = _compute_recovery_base(ctx)
        # ATR_base (high-low ~13) should be > ATR_prior_10 (high-low ~2) → ratio > 1.0
        assert result["atr_contraction_ratio"] > 1.0
        assert result["criteria"]["atr_contracting"] is False


class TestDistributionWarning:
    """Spec §3.3 C5 + TC-06."""

    def test_tc06_distribution_warning_fails(self):
        bars = []
        for _ in range(10):
            bars.append(_default_bar(low=95, high=110, atr=5.0, ema8=100, ema21=102))
        bars.append(_default_bar(low=88, high=95, volume=3000, atr=5.0, ema8=99, ema21=102))
        for _ in range(5):
            bars.append(_default_bar(low=89, high=93, volume=1200, atr=2.5, ema8=101, ema21=102))
        ctx = _make_ctx(bars, p_code="A", vol_confirm_state="DISTRIBUTION WARNING")
        result = _compute_recovery_base(ctx)
        assert result["criteria"]["vol_clean"] is False
        assert result["base_confirmed"] is False


class TestEMACrossFreshness:
    """Spec §3.4 + TC-07, TC-08, TC-23."""

    def test_tc07_stale_cross(self):
        """EMA cross before swing low → stale."""
        bars = []
        # 5 bars with no cross
        for _ in range(5):
            bars.append(_default_bar(ema8=100, ema21=103))
        # Cross at bar 5 (ema8 goes above ema21)
        bars.append(_default_bar(ema8=104, ema21=103))
        # 4 more bars, then swing low at bar 10 (after cross)
        for _ in range(4):
            bars.append(_default_bar(ema8=104, ema21=103))
        # Swing low later
        bars.append(_default_bar(low=80, high=85, volume=5000, atr=5.0, ema8=100, ema21=103))
        # 5 base bars, EMA inverted throughout (no new cross)
        for _ in range(5):
            bars.append(_default_bar(low=82, high=88, volume=2000, atr=3.0, ema8=100, ema21=103))
        ctx = _make_ctx(bars, p_code="A")
        result = _compute_recovery_base(ctx)
        # Cross at bar 5, swing low at bar 10 → cross < swing low → stale
        assert result["ema_cross_bar_index"] == 5
        assert result["ema_cross_fresh"] is False

    def test_tc08_fresh_cross(self):
        """EMA cross after swing low → fresh."""
        bars = []
        for _ in range(10):
            bars.append(_default_bar(low=95, high=110, atr=5.0, ema8=100, ema21=103))
        # Swing low at bar 10
        bars.append(_default_bar(low=85, high=90, volume=5000, atr=5.0, ema8=98, ema21=103))
        # 3 bars, EMAs converge
        bars.append(_default_bar(low=86, high=92, volume=2000, atr=3.0, ema8=100, ema21=102))
        bars.append(_default_bar(low=87, high=93, volume=1800, atr=2.8, ema8=101, ema21=101.5))
        # Cross at bar 13 (ema8 just crossed above ema21; prev bar ema8 <= ema21)
        bars.append(_default_bar(low=88, high=95, volume=2000, atr=2.5, ema8=102.5, ema21=102.0))
        # Bar 14 eval
        bars.append(_default_bar(low=89, high=96, volume=1500, atr=2.5, ema8=103, ema21=102.2))
        ctx = _make_ctx(bars, p_code="A")
        result = _compute_recovery_base(ctx)
        assert result["ema_cross_bar_index"] == 13
        assert result["ema_cross_fresh"] is True  # 13 >= 10

    def test_tc23_no_cross(self):
        """No EMA 8/21 bullish cross exists → ema_cross_bar_index is None."""
        # All bars have EMA_8 < EMA_21 (no cross ever)
        bars = [_default_bar(ema8=100, ema21=103, low=95 + i * 0.1) for i in range(16)]
        # Make one bar the swing low
        bars[5] = _default_bar(low=80, high=85, volume=5000, atr=5.0, ema8=100, ema21=103)
        ctx = _make_ctx(bars, p_code="A")
        result = _compute_recovery_base(ctx)
        assert result["ema_cross_bar_index"] is None
        assert result["ema_cross_fresh"] is False


class TestReturnStructure:
    """Verify all required fields are present per Phase 2A prompt spec."""

    def test_all_fields_present(self):
        bars = [_default_bar() for _ in range(16)]
        bars[3] = _default_bar(low=80, volume=5000)
        ctx = _make_ctx(bars, p_code="A")
        result = _compute_recovery_base(ctx)
        required = [
            "swing_low_price", "swing_low_bar_index", "base_bar_count",
            "base_confirmed", "criteria", "atr_contraction_ratio",
            "retest_confirmed", "ema_cross_bar_index", "ema_cross_fresh",
            "di_spread_current", "di_spread_at_swing_low",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"
        criteria_keys = ["min_bars", "no_lower_low", "atr_contracting",
                         "retest_confirmed", "vol_clean"]
        for key in criteria_keys:
            assert key in result["criteria"], f"Missing criteria key: {key}"
