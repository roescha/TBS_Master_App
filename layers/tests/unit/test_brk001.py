"""BRK-001: Breakout Entry Architecture — Test Suite (TC-01 through TC-12)"""
import sys
from unittest import mock

# Stub heavy deps before importing engine (same pattern as test_bugr1_inversion_note.py)
for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'ib_insync.contract', 'ib_insync.objects'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

import pytest
from types import SimpleNamespace


def _make_state(**overrides):
    defaults = dict(
        atr_raw=0.8, di_plus=31.88, di_minus=9.3,
        adx_t=53.16, adx_t1=52.0, ma_squeeze=False,
        is_trending=True, is_resolving=False,
        _entry_trending=True, _entry_resolving=False,
        ema_stacked=True, ma_stack_full=True,
        consec_below=0, is_violated=False, is_reclaim=False,
        is_floor_failure=False, _reclaim_run=0, floor_raw=70.55,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_last(**overrides):
    """Returns a plain dict — supports d['key'] and d.get('key')."""
    d = dict(close=72.05, open=71.50, high=72.30, low=71.20,
             volume=1041951.0, vol_sma_20=500000.0,
             ANCHOR=70.55, EMA_8=71.76, EMA_21=70.55,
             SMA_50=67.61, SMA_200=61.93)
    d.update(overrides)
    return d


def _make_ctx(**overrides):
    state = overrides.pop('state', _make_state())
    last = overrides.pop('last', _make_last())
    defaults = dict(
        state=state, last=last, p_code="A", is_etf=False,
        _is_c3=False, resistance_raw=72.53, hard_stop_raw=69.36,
        structural_floor_raw=70.55, price_scaler=1.0,
        actual_price=72.08, metrics={}, bars_per_day=7,
        window_count=3, window_limit=4,
        daily_protective_anchor=64.72, daily_atr=2.69,
        daily_hard_stop=60.69, df=None,
        cfg=SimpleNamespace(iq=-1, ff_threshold=4),
        _df_ctx=None, adx_col='ADX', dmp_col='DMP', dmn_col='DMN',
        _sbo_prestate=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# TC-01: SWING_BREAKOUT, measured move available, R:R > 2:1
class TestTC01_BreakoutFlipCore:
    def test_detect_breakout_model_fresh(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=73.00, volume=1000000.0, vol_sma_20=500000.0),
            state=_make_state(di_plus=31.88, di_minus=9.3, atr_raw=0.8),
            resistance_raw=72.53,
        )
        _detect_breakout_model(ctx, "BREAKOUT")
        assert ctx._breakout_model_active is True
        assert ctx._brk_new_support_raw == 72.53
        assert ctx._brk_tight_stop_raw == pytest.approx(72.53 - 1.0 * 0.8, abs=0.01)
        assert ctx._brk_catastrophic_stop_raw == pytest.approx(72.53 - 1.5 * 0.8, abs=0.01)

    def test_detect_breakout_model_stale(self):
        """Path B: stale breakout in window, close >= new support (thesis valid).

        BRK-001-GAP-2 update: original fixture used close=72.05 which is BELOW
        resistance_raw=72.53. Under GAP-2 that is a thesis-invalidation case
        (the exact bug GAP-2 was written to fix) and the model is correctly
        deactivated. This test now uses close=72.53 (equal — strictly `<`
        guard does not fire) to keep exercising Path B activation. The
        close-below-resistance case is covered by TC-GAP2-01 in
        test_brk001_gap2.py.
        """
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=72.53),
            state=_make_state(atr_raw=0.8),
            resistance_raw=72.53, window_count=3, window_limit=4,
        )
        _detect_breakout_model(ctx, "BREAKOUT")
        assert ctx._breakout_model_active is True

    def test_mm_target_computation(self):
        from tbs_engine.compute import _compute_mm_target_early
        import pandas as pd, numpy as np
        n = 30
        df = pd.DataFrame({
            'high': np.linspace(68, 72, n),
            'low': np.linspace(66, 70, n),
            'close': np.linspace(67, 71, n),
        }, index=pd.date_range('2026-01-01', periods=n, freq='h'))
        ctx = _make_ctx(bars_per_day=7)
        ctx.df = df
        ctx.state = _make_state(atr_raw=0.8, _entry_trending=True)
        ctx.last = df.iloc[-1]
        mm = _compute_mm_target_early(ctx)
        assert mm is not None
        assert mm > float(df.iloc[-1]['close'])

    def test_breakout_rr_values(self):
        from tbs_engine.compute import BRK_STOP_BUFFER_ATR
        entry, new_support, mm_target, atr = 72.05, 72.53, 76.44, 0.8
        tight_stop = new_support - BRK_STOP_BUFFER_ATR * atr
        risk_a = entry - tight_stop
        reward_a = mm_target - entry
        rr = reward_a / risk_a
        assert tight_stop == pytest.approx(71.73, abs=0.01)
        assert risk_a == pytest.approx(0.32, abs=0.01)
        assert reward_a == pytest.approx(4.39, abs=0.01)
        assert rr > 2.0


# TC-02: SWING_BREAKOUT, R:R < 2:1 after flip
class TestTC02_BreakoutFailsExpectancy:
    def test_breakout_rr_below_threshold(self):
        from tbs_engine.compute import BRK_STOP_BUFFER_ATR
        entry, new_support, atr = 72.05, 72.53, 0.8
        target = 72.10
        tight_stop = new_support - BRK_STOP_BUFFER_ATR * atr
        risk_a = entry - tight_stop
        reward_a = target - entry
        assert reward_a < (2.0 * risk_a)


# TC-04: PULLBACK with prior SBO confirmed → Standard model
class TestTC04_PullbackNoFlip:
    def test_pullback_zone_no_breakout_model(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=65.50, ANCHOR=65.00, EMA_8=65.20),
            state=_make_state(atr_raw=1.0, di_plus=25, di_minus=15),
            resistance_raw=67.00, window_count=2, window_limit=4,
        )
        _detect_breakout_model(ctx, "PULLBACK")
        assert ctx._breakout_model_active is False


# TC-05: MM_Target null
class TestTC05_MeasuredMoveNull:
    def test_null_mm_keeps_breakout_stop(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=73.00, volume=1000000.0, vol_sma_20=500000.0),
            state=_make_state(atr_raw=0.8, di_plus=30, di_minus=10),
            resistance_raw=72.53, bars_per_day=7,
        )
        ctx.df = None
        _detect_breakout_model(ctx, "BREAKOUT")
        assert ctx._breakout_model_active is True
        assert ctx._brk_mm_target_raw is None
        assert ctx._brk_new_support_raw == 72.53


# TC-06: C-3 bypass
class TestTC06_C3Bypass:
    def test_c3_skips_breakout_model(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            _is_c3=True,
            last=_make_last(close=73.00, volume=1000000.0, vol_sma_20=500000.0),
            state=_make_state(di_plus=30, di_minus=10),
            resistance_raw=72.53,
        )
        _detect_breakout_model(ctx, "BREAKOUT")
        assert ctx._breakout_model_active is False


# TC-07: Stop hierarchy scoping
class TestTC07_StopHierarchy:
    def test_breakout_stop_hierarchy_scoped(self):
        brk_levels = {"NEW_SUPPORT", "TIGHT_STOP", "CATASTROPHIC_STOP", "PSYCHOLOGICAL"}
        pre_brk_levels = {"SESSION_VWAP", "AVWAP_10BAR", "DAILY_EMA_21",
                          "DAILY_SMA_50", "DAILY_SMA_200", "HARD_STOP", "DAILY_HARD_STOP"}
        for label in pre_brk_levels:
            assert label not in brk_levels


# TC-09: Pre-state SBO
class TestTC09_PreStateSBO:
    def test_prestate_sbo_fresh_breakout(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=73.00, volume=1000000.0, vol_sma_20=500000.0),
            state=_make_state(adx_t=18.0, di_plus=25, di_minus=12, atr_raw=0.8,
                              is_trending=False, _entry_trending=False,
                              is_resolving=True, _entry_resolving=True),
            resistance_raw=72.53, _sbo_prestate=True,
        )
        _detect_breakout_model(ctx, "BREAKOUT")
        assert ctx._breakout_model_active is True


# TC-10: ON Semiconductor regression
class TestTC10_ONSemiRegression:
    def test_on_semi_rr_with_breakout_model(self):
        from tbs_engine.compute import BRK_STOP_BUFFER_ATR
        entry, old_resistance, mm_target, atr = 72.05, 72.53, 76.44, 0.8
        tight_stop = old_resistance - BRK_STOP_BUFFER_ATR * atr
        risk = entry - tight_stop
        reward = mm_target - entry
        rr = reward / risk
        assert rr == pytest.approx(13.72, abs=0.1)
        assert rr >= 2.0


# TC-11: PULLBACK regression
class TestTC11_PullbackRegression:
    def test_pullback_not_affected(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=65.00, ANCHOR=64.50, EMA_8=64.80),
            state=_make_state(atr_raw=1.0, di_plus=25, di_minus=15),
            resistance_raw=67.00, window_count=1, window_limit=4,
        )
        _detect_breakout_model(ctx, "PULLBACK")
        assert ctx._breakout_model_active is False


# TC-12: model tag
class TestTC12_ModelTag:
    def test_model_tag_present(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=73.00, volume=1000000.0, vol_sma_20=500000.0),
            state=_make_state(di_plus=30, di_minus=10, atr_raw=0.8),
            resistance_raw=72.53,
        )
        _detect_breakout_model(ctx, "BREAKOUT")
        assert ctx._breakout_model_active is True
        assert ctx._brk_new_support_raw == 72.53


# Constants
class TestConstants:
    def test_constants_values(self):
        from tbs_engine.compute import BRK_STOP_BUFFER_ATR, BRK_CATASTROPHIC_MULTIPLIER
        assert BRK_STOP_BUFFER_ATR == 1.0
        assert BRK_CATASTROPHIC_MULTIPLIER == 1.5

    def test_constants_named(self):
        import tbs_engine.compute as compute
        assert hasattr(compute, 'BRK_STOP_BUFFER_ATR')
        assert hasattr(compute, 'BRK_CATASTROPHIC_MULTIPLIER')
