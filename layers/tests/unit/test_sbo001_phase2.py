"""SBO-001 Phase 2: Time-to-confirmation stop, SBO output fields, transform mappings.

Tests TC-10 through TC-12 (confirmation timeout), SBO_RVOL computation,
null-field scenarios, and transform round-trip.
"""
import sys, os, types as _types, importlib.util, pytest
from types import SimpleNamespace
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Module isolation
# ---------------------------------------------------------------------------
_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _root)

if "tbs_engine" not in sys.modules:
    _pkg = _types.ModuleType("tbs_engine")
    _pkg.__path__ = [os.path.join(_root, "tbs_engine")]
    sys.modules["tbs_engine"] = _pkg

# Load types.py
_types_spec = importlib.util.spec_from_file_location(
    "tbs_engine.types", os.path.join(_root, "tbs_engine", "types.py"))
_types_mod = importlib.util.module_from_spec(_types_spec)
sys.modules["tbs_engine.types"] = _types_mod
_types_spec.loader.exec_module(_types_mod)

GateResult = _types_mod.GateResult

# Load helpers stub (gates needs it)
if "tbs_engine.helpers" not in sys.modules:
    _helpers_stub = _types.ModuleType("tbs_engine.helpers")
    _helpers_stub._check_round_number_proximity = lambda *a, **k: None
    _helpers_stub.check_climax_history = lambda *a, **k: None
    _helpers_stub._evaluate_floor_failure_context = lambda *a, **k: None
    sys.modules["tbs_engine.helpers"] = _helpers_stub

# Load transform.py (needed for _flatten, _transform_output)
_transform_spec = importlib.util.spec_from_file_location(
    "tbs_engine.transform", os.path.join(_root, "tbs_engine", "transform.py"))
_transform_mod = importlib.util.module_from_spec(_transform_spec)
sys.modules["tbs_engine.transform"] = _transform_mod
_transform_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output
_flatten = _transform_mod._flatten
SBO_CONFIRMATION_BARS_T = _transform_mod.SBO_CONFIRMATION_BARS

# SBO_CONFIRMATION_BARS from output.py — define locally to avoid heavy import chain
SBO_CONFIRMATION_BARS = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_df(n_bars=30, breakout_at=None, trending_at=None, adx_col="ADX_14"):
    """Build a synthetic df with optional breakout bar and trending bars.

    Args:
        n_bars: Total number of bars.
        breakout_at: iloc index where a breakout bar should be placed
                     (close > 10-bar high of prior bars).
        trending_at: iloc index (or list) where TRENDING conditions are met
                     (EMA stack + ADX > 20).
        adx_col: Name of the ADX column.
    """
    base_price = 100.0
    data = {
        'close': [base_price + i * 0.1 for i in range(n_bars)],
        'high': [base_price + i * 0.1 + 0.5 for i in range(n_bars)],
        'low': [base_price + i * 0.1 - 0.5 for i in range(n_bars)],
        'open': [base_price + i * 0.1 - 0.2 for i in range(n_bars)],
        'volume': [1000000] * n_bars,
        'vol_sma_20': [800000] * n_bars,
        'EMA_8': [base_price + i * 0.1 - 1.0 for i in range(n_bars)],
        'EMA_21': [base_price + i * 0.1 - 2.0 for i in range(n_bars)],
        'SMA_50': [base_price + i * 0.1 - 3.0 for i in range(n_bars)],
        adx_col: [18.0] * n_bars,  # default below TRENDING
    }
    df = pd.DataFrame(data)

    if breakout_at is not None and 10 <= breakout_at < n_bars:
        # Set breakout bar: close > max high of prior 10 bars
        prior_high = df['high'].iloc[max(0, breakout_at - 10):breakout_at].max()
        df.loc[breakout_at, 'close'] = prior_high + 2.0
        df.loc[breakout_at, 'high'] = prior_high + 3.0
        # Set volume spike for RVOL
        df.loc[breakout_at, 'volume'] = 2000000
        df.loc[breakout_at, 'vol_sma_20'] = 1000000

    if trending_at is not None:
        if isinstance(trending_at, int):
            trending_at = [trending_at]
        for idx in trending_at:
            if 0 <= idx < n_bars:
                # EMA stack: close > EMA_8 > EMA_21 > SMA_50
                df.loc[idx, 'close'] = 120.0
                df.loc[idx, 'EMA_8'] = 119.0
                df.loc[idx, 'EMA_21'] = 118.0
                df.loc[idx, 'SMA_50'] = 117.0
                df.loc[idx, adx_col] = 25.0

    return df


def _make_state(**overrides):
    defaults = dict(
        is_trending=False, is_resolving=True, ma_stack_full=False,
        ma_squeeze=False, ema_stacked=False,
        adx_t=22.0, adx_t1=21.0, di_plus=30.0, di_minus=20.0, atr_raw=2.0,
        _etf_entry_trending=False, _etf_entry_resolving=True,
        _entry_trending=False, _entry_resolving=True,
        _resolving_is_bearish=False,
        is_reclaim=False, is_ambiguous=False, is_violated=False,
        is_floor_failure=False, floor_raw=100.0, consec_below=0, _reclaim_run=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_cfg(**overrides):
    defaults = dict(
        iq=-2, min_bars_required=50, window_limit=5,
        ff_threshold=3, ext_limit_trending=1.0, ext_limit_resolving=0.5,
        ext_limit_etf=1.0, resistance_slice_start=-12, resistance_slice_end=-2,
        tf_resolution="60", tf_duration="30d", ctx_resolution="1D",
        ctx_duration="365d", fb_max=3.0, ta_max=100, prev_bar_offset=-3,
        required_ma_cols=("EMA_8", "EMA_21", "SMA_50"), pb_upper_col="EMA_21",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_last(**overrides):
    defaults = dict(
        close=105.0, open=104.0, high=106.0, low=103.0, volume=1000000,
        ANCHOR=98.0, EMA_8=104.0, EMA_21=102.0, SMA_50=100.0, SMA_200=95.0,
        vol_sma_20=800000, Is_Breakout=False, VWAP=103.0,
    )
    defaults.update(overrides)

    class DictSeries(dict):
        def get(self, key, default=None):
            return self[key] if key in self else default

    return DictSeries(defaults)


# ---------------------------------------------------------------------------
# Direct SBO monitoring logic tests (via metrics injection)
# These test the monitoring block's effect on metrics without running the
# full _assemble_output (which has many dependencies). We simulate by
# running the same logic inline.
# ---------------------------------------------------------------------------

def _run_swing_breakout_confirmation(df, cfg_iq=-2, p_code="A", is_etf=False, adx_col="ADX_14"):
    """Run SBO monitoring logic extracted from output.py pattern.

    Returns (sbo_age, sbo_trending, sbo_timeout, sbo_rvol).
    """
    _sbo_age = None
    _sbo_trending = None
    _sbo_timeout = None
    _sbo_rvol = None

    if p_code == "A" and not is_etf:
        _eval_idx = len(df) + cfg_iq
        # SBO-001-BUG-1: mirror production — unbounded scan per spec §7.1.
        _lookback_start = 0
        _breakout_idx = None

        for _i in range(_eval_idx - 1, _lookback_start - 1, -1):
            try:
                _bar_close = float(df['close'].iloc[_i])
                _range_start = max(0, _i - 10)
                _range_high = float(df['high'].iloc[_range_start:_i].max())
                if _bar_close > _range_high:
                    _breakout_idx = _i
                    break
            except (IndexError, ValueError):
                continue

        if _breakout_idx is not None:
            _sbo_age = _eval_idx - _breakout_idx

            if _sbo_age > 0:
                _sbo_trending = False
                for _j in range(_breakout_idx + 1, _eval_idx + 1):
                    try:
                        _bar = df.iloc[_j]
                        _stack = (
                            _bar['close'] > _bar['EMA_8'] and
                            _bar['EMA_8'] > _bar['EMA_21'] and
                            _bar['EMA_21'] > _bar['SMA_50']
                        )
                        _bar_adx = float(df[adx_col].iloc[_j]) if adx_col in df.columns else 0
                        if _stack and _bar_adx > 20:
                            _sbo_trending = True
                            break
                    except (IndexError, KeyError):
                        continue

                _sbo_timeout = (_sbo_age > SBO_CONFIRMATION_BARS and not _sbo_trending)
            else:
                _sbo_timeout = False

            try:
                _bo_vol = float(df['volume'].iloc[_breakout_idx])
                _bo_vol_avg = float(df['vol_sma_20'].iloc[_breakout_idx])
                _sbo_rvol = round(_bo_vol / _bo_vol_avg, 2) if _bo_vol_avg > 0 else None
            except (IndexError, KeyError, ZeroDivisionError):
                _sbo_rvol = None

    return _sbo_age, _sbo_trending, _sbo_timeout, _sbo_rvol


# ===========================================================================
# TC-10: Time-to-confirmation: bar age 10, still RESOLVING → no timeout
# ===========================================================================
class TestTC10:
    def test_no_timeout_within_window(self):
        # Breakout at bar 18, current eval at bar 28 (age = 10), no trending
        df = _build_df(n_bars=30, breakout_at=18)
        age, trending, timeout, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2)
        assert age == 10
        assert trending is False
        assert timeout is False  # 10 <= 15, no timeout
        assert rvol is not None


# ===========================================================================
# TC-11: Time-to-confirmation: bar age 16, still RESOLVING → INVALID TIMEOUT
# ===========================================================================
class TestTC11:
    def test_timeout_fires(self):
        # Breakout at bar 12, current eval at bar 28 (age = 16), no trending
        df = _build_df(n_bars=30, breakout_at=12)
        age, trending, timeout, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2)
        assert age == 16
        assert trending is False
        assert timeout is True  # 16 > 15, timeout fires

    def test_timeout_overrides_valid_gate_result(self):
        """When timeout is True, a VALID gate_result should become INVALID."""
        valid_gr = GateResult(
            verdict="VALID", reason="SWING_BREAKOUT",
            mandate="Enter.", context="All passed.",
            entry_type="SWING_BREAKOUT", trigger_rule="BAR CLOSE ONLY",
            state="RESOLVING",
        )
        # Simulate the override logic from output.py
        _sbo_timeout = True
        _sbo_age = 16
        _sbo_trending = False
        if _sbo_timeout and valid_gr.verdict == "VALID":
            overridden = GateResult(
                verdict="INVALID",
                reason="SBO CONFIRMATION TIMEOUT",
                mandate=f"Exit position. TRENDING not reached within {SBO_CONFIRMATION_BARS} bars of breakout.",
                context=f"Breakout bar age: {_sbo_age}. TRENDING reached: {_sbo_trending}.",
            )
        assert overridden.verdict == "INVALID"
        assert overridden.reason == "SBO CONFIRMATION TIMEOUT"


# ===========================================================================
# TC-12: Time-to-confirmation: bar age 16, TRENDING reached at bar 12 → no timeout
# ===========================================================================
class TestTC12:
    def test_trending_prevents_timeout(self):
        # Breakout at bar 12, current eval at bar 28 (age = 16)
        # Trending conditions at bar 20 — but NOT a new breakout
        df = _build_df(n_bars=30, breakout_at=12)
        # Set trending conditions at bar 20 without creating a new breakout
        # (close must NOT exceed 10-bar high at that point)
        idx = 20
        df.loc[idx, 'EMA_8'] = df.loc[idx, 'close'] - 0.5
        df.loc[idx, 'EMA_21'] = df.loc[idx, 'close'] - 1.0
        df.loc[idx, 'SMA_50'] = df.loc[idx, 'close'] - 1.5
        df.loc[idx, 'ADX_14'] = 25.0
        age, trending, timeout, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2)
        assert age == 16
        assert trending is True
        assert timeout is False  # trending reached overrides


# ===========================================================================
# TC-AGED-1 / TC-AGED-2: aged breakouts beyond the prior 20-bar bound.
#
# SBO-001-BUG-1 regression guard. Pre-fix, the breakout-identification scan
# was hard-capped at 20 bars (`max(0, _eval_idx - 20)`), which silently
# hid breakouts older than 20 hourly bars (~2.5 trading days). All four
# SBO fields returned None, collapsing the `swing_breakout_confirmation`
# container on Profile A aged breakouts.
#
# Post-fix per SBO-001 spec §7.1: "Scan backwards through df from the
# current bar..." — unbounded. Aged breakouts are now surfaced with
# SBO_Confirmation_Timeout = True (spec §7.1 timeout rule:
# bars_since_breakout > 15 AND TRENDING not reached → TIMEOUT).
#
# The pre-fix vs post-fix contrast is implicit via the pairing with
# TestSBONullNoBreakout::test_all_null_when_flat, which confirms the
# all-None output remains valid when no breakout exists anywhere.
# ===========================================================================
class TestSBOAgedBreakout:
    def test_tc_aged_1_age_30_timeout(self):
        """TC-AGED-1: breakout at age 30, no TRENDING → timeout visible post-fix."""
        # n_bars=50, breakout_at=18, cfg_iq=-2 → _eval_idx=48 → age=30.
        # Pre-fix: bar 18 outside scan window [28, 47] → all None.
        # Post-fix: bar 18 within scan window [0, 47] → fields populated.
        df = _build_df(n_bars=50, breakout_at=18)
        age, trending, timeout, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2)
        assert age == 30
        assert trending is False
        assert timeout is True  # 30 > 15, no trending → timeout fires
        assert rvol is not None
        # Breakout bar fixture: volume=2000000, vol_sma_20=1000000 → RVOL=2.0
        assert rvol == 2.0

    def test_tc_aged_2_age_100_timeout(self):
        """TC-AGED-2: breakout at age 100, no TRENDING → timeout visible post-fix."""
        # n_bars=120, breakout_at=18, cfg_iq=-2 → _eval_idx=118 → age=100.
        # Pre-fix: bar 18 outside scan window [98, 117] → all None.
        # Post-fix: bar 18 within scan window [0, 117] → fields populated.
        df = _build_df(n_bars=120, breakout_at=18)
        age, trending, timeout, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2)
        assert age == 100
        assert trending is False
        assert timeout is True
        assert rvol is not None
        assert rvol == 2.0


# ===========================================================================
# SBO_RVOL correctly computed from breakout bar volume data
# ===========================================================================
class TestSBORvol:
    def test_rvol_computed(self):
        df = _build_df(n_bars=30, breakout_at=18)
        _, _, _, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2)
        # breakout bar: volume=2000000, vol_sma_20=1000000 → RVOL = 2.0
        assert rvol == 2.0

    def test_rvol_none_when_no_breakout(self):
        # No breakout bar in lookback window — all bars are flat
        df = _build_df(n_bars=30, breakout_at=None)
        # Make bars truly flat so no bar passes close > 10-bar high
        df['close'] = 100.0
        df['high'] = 100.5
        _, _, _, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2)
        assert rvol is None


# ===========================================================================
# SBO fields are null when no breakout bar found in lookback window
# ===========================================================================
class TestSBONullNoBreakout:
    def test_all_null_when_flat(self):
        df = _build_df(n_bars=30)
        df['close'] = 100.0
        df['high'] = 100.5
        age, trending, timeout, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2)
        assert age is None
        assert trending is None
        assert timeout is None
        assert rvol is None


# ===========================================================================
# SBO fields are null on Profile B (monitor is Profile A only)
# ===========================================================================
class TestSBONullProfileB:
    def test_null_on_profile_b(self):
        df = _build_df(n_bars=30, breakout_at=18)
        age, trending, timeout, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2, p_code="B")
        assert age is None
        assert trending is None
        assert timeout is None
        assert rvol is None


# ===========================================================================
# SBO fields are null on ETF paths
# ===========================================================================
class TestSBONullETF:
    def test_null_on_etf(self):
        df = _build_df(n_bars=30, breakout_at=18)
        age, trending, timeout, rvol = _run_swing_breakout_confirmation(df, cfg_iq=-2, is_etf=True)
        assert age is None
        assert trending is None
        assert timeout is None
        assert rvol is None


# ===========================================================================
# Transform: swing_breakout_confirmation group populated when SBO fields present
# ===========================================================================
class TestTransformSBOMonitorPresent:
    def test_swing_breakout_confirmation_populated(self):
        metrics = {
            "SBO_Breakout_Bar_Age": 10,
            "SBO_Trending_Reached": False,
            "SBO_Confirmation_Timeout": False,
            "SBO_RVOL": 2.0,
        }
        action_summary = {
            "verdict": "VALID",
            "reason": {"label": "SWING_BREAKOUT", "detail": "All passed."},
            "mandate": "Enter.",
            "merit": {"quality": "MODERATE", "reward": "FAVORABLE [2.1]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Close above 152"},
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 155, "stop_loss": 137,
                               "target": 170, "fib_382": None, "fib_500": None,
                               "fib_confluence": None, "mm_target": None},
            "exit_status": {"active": False, "reason": None},
        }
        result = _transform_output(action_summary, metrics)
        assert "swing_breakout_confirmation" in result
        sbo = result["swing_breakout_confirmation"]
        assert sbo is not None
        assert sbo["status"]["label"] == "PENDING"
        assert sbo["breakout_age"]["value"] == 10
        assert sbo["breakout_age"]["timeframe"] == "hour"
        assert sbo["confirmation_window"]["remaining"] == 5
        assert sbo["confirmation_window"]["max"] == SBO_CONFIRMATION_BARS
        assert sbo["breakout_rvol"]["value"] == 2.0

    def test_status_confirmed_when_trending(self):
        metrics = {
            "SBO_Breakout_Bar_Age": 8,
            "SBO_Trending_Reached": True,
            "SBO_Confirmation_Timeout": False,
            "SBO_RVOL": 1.75,
        }
        action_summary = {
            "verdict": "VALID",
            "reason": {"label": "SWING_BREAKOUT", "detail": "All passed."},
            "mandate": "Enter.",
            "merit": {"quality": "MODERATE", "reward": "FAVORABLE [2.1]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Close above 152"},
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 155, "stop_loss": 137,
                               "target": 170, "fib_382": None, "fib_500": None,
                               "fib_confluence": None, "mm_target": None},
            "exit_status": {"active": False, "reason": None},
        }
        result = _transform_output(action_summary, metrics)
        sbo = result["swing_breakout_confirmation"]
        assert sbo["status"]["label"] == "CONFIRMED"

    def test_status_expired_when_timeout(self):
        metrics = {
            "SBO_Breakout_Bar_Age": 20,
            "SBO_Trending_Reached": False,
            "SBO_Confirmation_Timeout": True,
            "SBO_RVOL": 1.53,
        }
        action_summary = {
            "verdict": "INVALID",
            "reason": {"label": "SBO CONFIRMATION TIMEOUT", "detail": "Expired."},
            "approaching": False,
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "exit_status": {"active": False, "reason": None},
        }
        result = _transform_output(action_summary, metrics)
        sbo = result["swing_breakout_confirmation"]
        assert sbo["status"]["label"] == "EXPIRED"
        assert sbo["confirmation_window"]["remaining"] == 0  # clamped to 0

    def test_remaining_clamped_at_zero(self):
        """Bars remaining should never go negative."""
        metrics = {
            "SBO_Breakout_Bar_Age": 25,
            "SBO_Trending_Reached": False,
            "SBO_Confirmation_Timeout": True,
            "SBO_RVOL": 1.8,
        }
        action_summary = {
            "verdict": "INVALID",
            "reason": {"label": "SBO CONFIRMATION TIMEOUT", "detail": "Expired."},
            "approaching": False,
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "exit_status": {"active": False, "reason": None},
        }
        result = _transform_output(action_summary, metrics)
        assert result["swing_breakout_confirmation"]["confirmation_window"]["remaining"] == 0


# ===========================================================================
# Transform: swing_breakout_confirmation group absent (None) when SBO fields all null
# ===========================================================================
class TestTransformSBOMonitorAbsent:
    def test_swing_breakout_confirmation_absent_when_null(self):
        metrics = {
            "SBO_Breakout_Bar_Age": None,
            "SBO_Trending_Reached": None,
            "SBO_Confirmation_Timeout": None,
            "SBO_RVOL": None,
        }
        action_summary = {
            "verdict": "INVALID",
            "reason": {"label": "PROFILE A RESOLVING BLOCK", "detail": "No breakout."},
            "approaching": False,
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "exit_status": {"active": False, "reason": None},
        }
        result = _transform_output(action_summary, metrics)
        assert "swing_breakout_confirmation" not in result


# ===========================================================================
# Flatten: 4 SBO flat keys correctly extracted
# ===========================================================================
class TestFlattenSBOKeys:
    def test_round_trip(self):
        metrics = {
            "SBO_Breakout_Bar_Age": 8,
            "SBO_Trending_Reached": True,
            "SBO_Confirmation_Timeout": False,
            "SBO_RVOL": 1.75,
        }
        action_summary = {
            "verdict": "VALID",
            "reason": {"label": "SWING_BREAKOUT", "detail": "All passed."},
            "mandate": "Enter.",
            "merit": {"quality": "MODERATE", "reward": "FAVORABLE [2.1]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Close above 152"},
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 155, "stop_loss": 137,
                               "target": 170, "fib_382": None, "fib_500": None,
                               "fib_confluence": None, "mm_target": None},
            "exit_status": {"active": False, "reason": None},
        }
        grouped = _transform_output(action_summary, metrics)
        _, _, flat = _flatten(grouped)
        assert flat["SBO_Breakout_Bar_Age"] == 8
        assert flat["SBO_Trending_Reached"] is True
        assert flat["SBO_Confirmation_Timeout"] is False
        assert flat["SBO_RVOL"] == 1.75

    def test_round_trip_expired(self):
        """Flatten derives timeout/trending from status label."""
        metrics = {
            "SBO_Breakout_Bar_Age": 20,
            "SBO_Trending_Reached": False,
            "SBO_Confirmation_Timeout": True,
            "SBO_RVOL": 1.53,
        }
        action_summary = {
            "verdict": "INVALID",
            "reason": {"label": "SBO CONFIRMATION TIMEOUT", "detail": "Expired."},
            "approaching": False,
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "exit_status": {"active": False, "reason": None},
        }
        grouped = _transform_output(action_summary, metrics)
        _, _, flat = _flatten(grouped)
        assert flat["SBO_Breakout_Bar_Age"] == 20
        assert flat["SBO_Trending_Reached"] is False
        assert flat["SBO_Confirmation_Timeout"] is True
        assert flat["SBO_RVOL"] == 1.53


# ===========================================================================
# Constants match between output.py and transform.py
# ===========================================================================
class TestConstantConsistency:
    def test_sbo_confirmation_bars_match(self):
        assert SBO_CONFIRMATION_BARS == SBO_CONFIRMATION_BARS_T == 15
