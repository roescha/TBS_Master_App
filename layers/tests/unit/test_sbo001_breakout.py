"""SBO-001 Phase 1: Swing Breakout Entry Protocol — unit tests.

Tests the SWING_BREAKOUT trigger path (Profile A), volume gate hardening
(Profile B), pre-state bypass (main.py), and extension exemption expansion.
"""
import sys, os, types as _types, importlib.util, pytest
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Module isolation — prevent tbs_engine/__init__.py from pulling in
# the full dependency chain (ib_insync, etc.)
# ---------------------------------------------------------------------------
_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _root)

# Ensure tbs_engine package exists without triggering __init__.py imports
if "tbs_engine" not in sys.modules:
    _pkg = _types.ModuleType("tbs_engine")
    _pkg.__path__ = [os.path.join(_root, "tbs_engine")]
    sys.modules["tbs_engine"] = _pkg

# Load types.py directly
_types_spec = importlib.util.spec_from_file_location(
    "tbs_engine.types", os.path.join(_root, "tbs_engine", "types.py"))
_types_mod = importlib.util.module_from_spec(_types_spec)
sys.modules["tbs_engine.types"] = _types_mod
_types_spec.loader.exec_module(_types_mod)

GateResult = _types_mod.GateResult

# Load trigger.py
_trig_spec = importlib.util.spec_from_file_location(
    "tbs_engine.trigger", os.path.join(_root, "tbs_engine", "trigger.py"))
_trig_mod = importlib.util.module_from_spec(_trig_spec)
sys.modules["tbs_engine.trigger"] = _trig_mod
_trig_spec.loader.exec_module(_trig_mod)

_identify_trigger = _trig_mod._identify_trigger
SBO_VOLUME_THRESHOLD = _trig_mod.SBO_VOLUME_THRESHOLD

# Load gates.py (needs helpers stub)
if "tbs_engine.helpers" not in sys.modules:
    _helpers_stub = _types.ModuleType("tbs_engine.helpers")
    _helpers_stub._check_round_number_proximity = lambda *a, **k: None
    _helpers_stub.check_climax_history = lambda *a, **k: None
    _helpers_stub._evaluate_floor_failure_context = lambda *a, **k: None
    sys.modules["tbs_engine.helpers"] = _helpers_stub

_gates_spec = importlib.util.spec_from_file_location(
    "tbs_engine.gates", os.path.join(_root, "tbs_engine", "gates.py"))
_gates_mod = importlib.util.module_from_spec(_gates_spec)
sys.modules["tbs_engine.gates"] = _gates_mod
_gates_spec.loader.exec_module(_gates_mod)

_gate_extension = _gates_mod._gate_extension


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    defaults = dict(
        is_trending=False, is_resolving=True, ma_stack_full=False,
        ma_squeeze=False, ema_stacked=False,
        adx_t=22.0, adx_t1=21.0, di_plus=30.0, di_minus=20.0, atr_raw=2.0,
        _etf_entry_trending=False, _etf_entry_resolving=True,
        _entry_trending=False, _entry_resolving=True,
        _resolving_is_bearish=False,
        is_reclaim=False, is_ambiguous=False, is_violated=False,
        is_floor_failure=False, floor_raw=0.0, consec_below=0, _reclaim_run=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_last(**overrides):
    defaults = dict(
        close=155.0, open=150.0, high=156.0, low=149.0, volume=2000000,
        ANCHOR=140.0, EMA_8=148.0, EMA_21=145.0, SMA_50=142.0, SMA_200=135.0,
        vol_sma_20=1000000, Is_Breakout=True,
    )
    defaults.update(overrides)

    class DictSeries(dict):
        def get(self, key, default=None):
            return self[key] if key in self else default

    return DictSeries(defaults)


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


def _make_ctx(state=None, last=None, cfg=None, p_code="A", is_etf=False, **overrides):
    s = state or _make_state()
    l = last or _make_last()
    c = cfg or _make_cfg()
    defaults = dict(
        state=s, cfg=c, p_code=p_code, is_etf=is_etf, _is_c3=False,
        df=None, last=l, metrics={},
        price_scaler=1.0, actual_price=155.0,
        structural_floor_raw=140.0, hard_stop_raw=137.0, resistance_raw=152.0,
        bars_per_day=6.5, atr_dist=0.3, ext_limit=0.5,
        floor_prox_pct=5.0, adx_accel=0.5, adx_accel_state="ACCELERATING",
        vol_confirm_ratio=0.5, vol_confirm_state="MIXED",
        exit_signal=False, window_count=0, window_limit=5,
        floor_price=140.0, hard_stop=137.0, resistance_display=152.0,
        _resistance_suppressed=False, chart_ref="",
        cons_high_raw=170.0, risk_a=1.5, reward_a=3.0,
        prev_high=154.0, prox_anchor=148.0,
        _prx_ctx=None, chart_dir="", clean_ticker="TEST",
        adx_col="", dmp_col="", dmn_col="", profile="SWING",
        _ssg_adjusted=False, _ssg_original_raw=0.0, _ssg_reason="",
        _is_lse_etf=False, currency="USD", vwap_col="VWAP",
        adx_t2=19.0, _df_ctx=None,
        vol_poc_price=None, vol_poc_distance_atr=None, vol_poc_position="",
        avwap_price=None, avwap_position="", volume_context_label="",
        _recovery_base_result=None, _recovery_target=None,
        _recovery_target_source="", _crg_bypass_context="", _recovery_exit=None,
        _sbo_prestate=False,
        # AVWAP-001: daily entry zone fields required by trigger.py for Profile A
        daily_protective_anchor=0.0, daily_atr=0.0, daily_hard_stop=0.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _run_trigger(ctx, gate_result=None, _capital_rr=2.0, _reward_label="FAVORABLE"):
    return _identify_trigger(
        ctx, gate_result=gate_result,
        _capital_rr=_capital_rr, _reward_label=_reward_label,
        _p1_resistance_note=None, _p1_reward_risk_note=None,
    )


# ===========================================================================
# TC-01: Profile A RESOLVING breakout, all conditions met → VALID SWING_BREAKOUT
# ===========================================================================
class TestTC01:
    def test_verdict(self):
        ctx = _make_ctx(p_code="A", resistance_raw=152.0,
                        last=_make_last(close=155.0, EMA_8=148.0, volume=2000000, vol_sma_20=1000000),
                        state=_make_state(di_plus=30.0, di_minus=20.0))
        r = _run_trigger(ctx)
        assert r.verdict == "VALID"
        assert r.entry_type == "SWING_BREAKOUT"
        assert r.trigger_rule == "BAR CLOSE ONLY"
        assert r.state == "RESOLVING"


# ===========================================================================
# TC-02: Profile A RESOLVING breakout, volume < 1.5 → INVALID
# ===========================================================================
class TestTC02:
    def test_verdict(self):
        ctx = _make_ctx(p_code="A", resistance_raw=152.0,
                        last=_make_last(close=155.0, EMA_8=148.0, volume=1200000, vol_sma_20=1000000),
                        state=_make_state(di_plus=30.0, di_minus=20.0))
        r = _run_trigger(ctx)
        assert r.verdict == "INVALID"
        assert r.reason == "PROFILE A RESOLVING BLOCK"


# ===========================================================================
# TC-03: Profile A RESOLVING breakout, -DI > +DI → INVALID
# ===========================================================================
class TestTC03:
    def test_verdict(self):
        ctx = _make_ctx(p_code="A", resistance_raw=152.0,
                        last=_make_last(close=155.0, EMA_8=148.0, volume=2000000, vol_sma_20=1000000),
                        state=_make_state(di_plus=18.0, di_minus=25.0))
        r = _run_trigger(ctx)
        assert r.verdict == "INVALID"
        assert r.reason == "PROFILE A RESOLVING BLOCK"


# ===========================================================================
# TC-04: Profile A pre-state (ADX 18, ACCELERATING), all met → VALID SWING_BREAKOUT
# This tests the trigger layer receiving a pre-state candidate that has
# already passed the main.py pre-state path (ctx._sbo_prestate=True).
# The trigger should fire SWING_BREAKOUT because _entry_resolving is False
# but the pre-state flag is set.  However, trigger.py's Priority 3 block
# requires _entry_resolving.  The pre-state path in main.py bypasses midrange
# and falls through to trigger with _entry_resolving=False — so it falls to
# Priority 4 AMBIGUOUS.  But wait: per the spec, state._entry_resolving will
# be True when ADX >= 20.  For ADX 18 (pre-state), _entry_resolving is False.
#
# Actually re-reading the architecture: the pre-state path sets
# ctx._sbo_prestate=True and the trigger chain still reaches Priority 3
# only if _entry_resolving is True.  For ADX 18, _entry_resolving=False,
# so the trigger block won't fire.  We need the trigger to also check
# ctx._sbo_prestate to enter Priority 3.
#
# Let me verify... The spec says the pre-state path routes to the trigger
# layer where SWING_BREAKOUT fires.  This means we need to adjust the
# Priority 3 condition.  Let me fix this.
# ===========================================================================


# ---------------------------------------------------------------------------
# FIX: The Priority 3 condition in trigger.py must also trigger on pre-state.
# Let me check if this is needed and fix before testing.
# ---------------------------------------------------------------------------

# For now, test TC-04 with _entry_resolving=True to validate the SWING_BREAKOUT
# path itself. The pre-state integration test (via main.py full path) would
# be an integration test.

class TestTC04:
    """Pre-state path — simulated by setting _sbo_prestate=True.
    For ADX 18, _entry_resolving is False, but _sbo_prestate=True
    activates Priority 3 in trigger.py.
    """
    def test_verdict_with_prestate_flag(self):
        ctx = _make_ctx(
            p_code="A", resistance_raw=152.0, _sbo_prestate=True,
            last=_make_last(close=155.0, EMA_8=148.0, volume=2000000, vol_sma_20=1000000),
            state=_make_state(adx_t=18.0, di_plus=30.0, di_minus=20.0,
                              _entry_resolving=False, is_resolving=False),
        )
        r = _run_trigger(ctx)
        assert r.verdict == "VALID"
        assert r.entry_type == "SWING_BREAKOUT"

    def test_verdict_when_resolving(self):
        """Pre-state with _entry_resolving=True (ADX exactly 20 edge)."""
        ctx = _make_ctx(
            p_code="A", resistance_raw=152.0, _sbo_prestate=True,
            last=_make_last(close=155.0, EMA_8=148.0, volume=2000000, vol_sma_20=1000000),
            state=_make_state(adx_t=20.0, di_plus=30.0, di_minus=20.0,
                              _entry_resolving=True),
        )
        r = _run_trigger(ctx)
        assert r.verdict == "VALID"
        assert r.entry_type == "SWING_BREAKOUT"


# ===========================================================================
# TC-05: Profile A pre-state, ADX 18, CRUISING → INVALID MID-RANGE
# (Pre-state qualifying check fails — standard cascade applies)
# This is a main.py integration concern; at trigger level, it's just
# _entry_resolving=False → AMBIGUOUS.
# ===========================================================================
class TestTC05:
    def test_verdict(self):
        ctx = _make_ctx(
            p_code="A", resistance_raw=152.0, _sbo_prestate=False,
            state=_make_state(adx_t=18.0, _entry_resolving=False, is_resolving=False),
        )
        r = _run_trigger(ctx)
        assert r.verdict == "INVALID"


# ===========================================================================
# TC-06: Profile A pre-state, ADX 16.5 → INVALID
# ===========================================================================
class TestTC06:
    def test_verdict(self):
        ctx = _make_ctx(
            p_code="A", resistance_raw=152.0, _sbo_prestate=False,
            state=_make_state(adx_t=16.5, _entry_resolving=False, is_resolving=False),
        )
        r = _run_trigger(ctx)
        assert r.verdict == "INVALID"


# ===========================================================================
# TC-07: Profile B BREAKOUT, volume ≥ 1.5, +DI > -DI → VALID BREAKOUT
# ===========================================================================
class TestTC07:
    def test_verdict(self):
        ctx = _make_ctx(
            p_code="B", resistance_raw=152.0,
            last=_make_last(close=155.0, EMA_8=148.0, volume=2000000, vol_sma_20=1000000),
            state=_make_state(di_plus=30.0, di_minus=20.0),
        )
        r = _run_trigger(ctx)
        assert r.verdict == "VALID"
        assert r.entry_type == "BREAKOUT"
        assert r.trigger_rule == "INTRADAY"
        assert r.state == "RESOLVING"


# ===========================================================================
# TC-08: Profile B BREAKOUT, volume < 1.5 → INVALID
# ===========================================================================
class TestTC08:
    def test_verdict(self):
        ctx = _make_ctx(
            p_code="B", resistance_raw=152.0,
            last=_make_last(close=155.0, EMA_8=148.0, volume=1200000, vol_sma_20=1000000),
            state=_make_state(di_plus=30.0, di_minus=20.0),
        )
        r = _run_trigger(ctx)
        assert r.verdict == "INVALID"
        assert r.reason == "NO BREAKOUT"
        assert "volume" in r.legacy_diagnostic.lower()


# ===========================================================================
# TC-09: Profile B BREAKOUT, -DI > +DI → INVALID
# ===========================================================================
class TestTC09:
    def test_verdict(self):
        ctx = _make_ctx(
            p_code="B", resistance_raw=152.0,
            last=_make_last(close=155.0, EMA_8=148.0, volume=2000000, vol_sma_20=1000000),
            state=_make_state(di_plus=18.0, di_minus=25.0),
        )
        r = _run_trigger(ctx)
        assert r.verdict == "INVALID"
        assert r.reason == "NO BREAKOUT"
        assert "DI" in r.legacy_diagnostic or "directional" in r.legacy_diagnostic.lower()


# ===========================================================================
# TC-13: Extension: Profile A RESOLVING breakout at 1.2 ATR → passes extension
# ===========================================================================
class TestTC13:
    def test_passes(self):
        last = _make_last(close=155.0)
        state = SimpleNamespace(
            is_trending=False, is_resolving=True,
            _entry_trending=False, _entry_resolving=True, atr_raw=2.0,
        )
        ctx = SimpleNamespace(
            state=state, p_code="A", is_etf=False, last=last,
            resistance_raw=152.0, resistance_display=152.0,
            _resistance_suppressed=False, floor_prox_pct=5.0,
            metrics={}, adx_accel_state="CRUISING", adx_accel=0.0,
            vol_confirm_state="MIXED", vol_confirm_ratio=0.5,
            exit_signal=False, structural_floor_raw=140.0,
            price_scaler=1.0, ext_limit=0.5, _sbo_prestate=False,
        )
        result = _gate_extension(ctx, atr_dist=1.2, ext_limit=0.5)
        assert result is None  # passes — 1.2 < 1.5 exemption limit


# ===========================================================================
# TC-14: AVWAP-001 DQ-4: Profile A intraday extension gate RETIRED
# ===========================================================================
class TestTC14:
    def test_fails(self):
        """AVWAP-001: Profile A skips intraday extension, gate passes."""
        last = _make_last(close=155.0)
        state = SimpleNamespace(
            is_trending=False, is_resolving=True,
            _entry_trending=False, _entry_resolving=True, atr_raw=2.0,
        )
        ctx = SimpleNamespace(
            state=state, p_code="A", is_etf=False, last=last,
            resistance_raw=152.0, resistance_display=152.0,
            _resistance_suppressed=False, floor_prox_pct=5.0,
            metrics={}, adx_accel_state="CRUISING", adx_accel=0.0,
            vol_confirm_state="MIXED", vol_confirm_ratio=0.5,
            exit_signal=False, structural_floor_raw=140.0,
            price_scaler=1.0, ext_limit=0.5, _sbo_prestate=False,
        )
        result = _gate_extension(ctx, atr_dist=1.8, ext_limit=0.5)
        assert result is None  # AVWAP-001: intraday extension retired for Profile A


# ===========================================================================
# TC-15: CRG failed + pre-state conditions met → standard CRG rejection
# This is a main.py integration test. At the trigger level, if CRG
# sets gate_result before trigger, the trigger chain is skipped.
# ===========================================================================
class TestTC15:
    def test_crg_rejection_passthrough(self):
        crg_block = GateResult(
            verdict="INVALID", reason="CRG-1", mandate="CRG block.",
            context="Weekly structure broken.",
        )
        ctx = _make_ctx(p_code="A", _sbo_prestate=False)
        r = _run_trigger(ctx, gate_result=crg_block)
        assert r.verdict == "INVALID"
        assert r.reason == "CRG-1"


# ===========================================================================
# TC-16: ETF RESOLVING breakout with volume → VALID (ANCHOR for convex support)
# ===========================================================================
class TestTC16:
    def test_verdict(self):
        ctx = _make_ctx(
            p_code="A", is_etf=True, resistance_raw=152.0,
            last=_make_last(close=155.0, ANCHOR=148.0, EMA_8=146.0,
                            volume=2000000, vol_sma_20=1000000),
            state=_make_state(di_plus=30.0, di_minus=20.0,
                              _etf_entry_resolving=True),
        )
        r = _run_trigger(ctx)
        assert r.verdict == "VALID"
        assert r.entry_type == "SWING_BREAKOUT"
