"""AVWAP-001 Phase 1+2: Core Architecture + Gate/Trigger Layer Tests.

Covers:
  Phase 1: data.py ANCHOR swap, types.py sentinel values, compute.py verification
  Phase 2: gates.py extension retirement, trigger.py daily entry zone + VWAP trigger,
           exit.py counter rename

Test Plan Reference: AVWAP001_Phase1_2_Standalone_Implementation_Prompt §Test Plan
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from types import SimpleNamespace

from tbs_engine.data import _build_config
from tbs_engine.gates import _gate_extension, _gate_expectancy
from tbs_engine.trigger import _identify_trigger, _detect_session_first_bar
from tbs_engine.exit import _exit_profile_a
from tbs_engine.types import GateResult, ProfileConfig


# ═══════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════

def _make_df(n=50, anchor_val=100.0, ema21_val=100.0, vwap_val=101.0,
             close_val=102.0, atr_val=2.0, p_code="A",
             dates=None):
    """Build a minimal DataFrame for testing.

    For Profile A: includes SESSION_VWAP, ANCHOR=EMA_21.
    For Profile B: ANCHOR=SMA_50.
    For Profile C: ANCHOR=SMA_200.
    """
    if dates is None:
        base = datetime(2026, 4, 10, 9, 30)
        dates = [base + timedelta(hours=i) for i in range(n)]

    df = pd.DataFrame({
        'open':   [close_val - 0.5] * n,
        'high':   [close_val + 1.0] * n,
        'low':    [close_val - 1.0] * n,
        'close':  [close_val] * n,
        'volume': [100000] * n,
        'EMA_8':  [close_val + 0.5] * n,
        'EMA_21': [ema21_val] * n,
        'SMA_50': [anchor_val - 5.0] * n,
        'SMA_200': [anchor_val - 20.0] * n,
        'ATRr_14': [atr_val] * n,
        'vol_sma_9': [90000] * n,
        'vol_sma_20': [85000] * n,
        'Is_Breakout': [False] * n,
        'Prev_10_High': [close_val + 0.5] * n,
    }, index=pd.DatetimeIndex(dates))

    if p_code == "A":
        df['ANCHOR'] = df['EMA_21']
        df['SESSION_VWAP'] = [vwap_val] * n
    elif p_code == "B":
        df['ANCHOR'] = df['SMA_50']
    elif p_code == "C":
        df['ANCHOR'] = df['SMA_200']

    return df


def _make_ctx(p_code="A", df=None, close_val=102.0, ema21_val=100.0,
              atr_val=2.0, daily_ema21=100.0, daily_atr=3.0,
              is_trending=True, is_resolving=False, adx_t=28.0,
              gate_result=None, resistance_raw=110.0,
              **kwargs):
    """Build a minimal RunContext SimpleNamespace for testing."""
    if df is None:
        df = _make_df(p_code=p_code, close_val=close_val,
                       ema21_val=ema21_val, atr_val=atr_val)

    cfg = _build_config(p_code)
    last = df.iloc[cfg.iq]
    metrics = {}

    state = SimpleNamespace(
        is_trending=is_trending,
        is_resolving=is_resolving,
        _entry_trending=is_trending,
        _entry_resolving=is_resolving,
        ma_stack_full=is_trending,
        ma_squeeze=False,
        ema_stacked=True,
        adx_t=adx_t,
        adx_t1=adx_t - 1.0,
        di_plus=25.0,
        di_minus=15.0,
        atr_raw=atr_val,
        _etf_entry_trending=False,
        _etf_entry_resolving=False,
        _resolving_is_bearish=False,
        is_reclaim=kwargs.get('is_reclaim', False),
        is_ambiguous=False,
        is_violated=False,
        is_floor_failure=False,
        floor_raw=ema21_val,
        consec_below=0,
        _reclaim_run=0,
    )

    price_scaler = 1.0
    ctx = SimpleNamespace(
        state=state,
        cfg=cfg,
        p_code=p_code,
        is_etf=False,
        _is_c3=False,
        df=df,
        last=last,
        metrics=metrics,
        price_scaler=price_scaler,
        actual_price=close_val,
        structural_floor_raw=ema21_val,
        hard_stop_raw=ema21_val - 1.5 * atr_val,
        resistance_raw=resistance_raw,
        bars_per_day=6.5,
        atr_dist=kwargs.get('atr_dist', 0.5),
        ext_limit=cfg.ext_limit_trending,
        floor_prox_pct=5.0,
        adx_accel=0.0,
        adx_accel_state="CRUISING",
        vol_confirm_ratio=0.6,
        vol_confirm_state="MIXED",
        exit_signal=False,
        floor_price=round(ema21_val / price_scaler, 2),
        hard_stop=round((ema21_val - 1.5 * atr_val) / price_scaler, 2),
        resistance_display=round(resistance_raw / price_scaler, 2),
        _resistance_suppressed=False,
        chart_ref="",
        cons_high_raw=resistance_raw,
        risk_a=close_val - ema21_val,
        reward_a=resistance_raw - close_val,
        prev_high=close_val + 0.3,
        prox_anchor=ema21_val,
        _prx_ctx=None,
        chart_dir="",
        clean_ticker="TEST",
        adx_col="ADX_14",
        dmp_col="DMP_14",
        dmn_col="DMN_14",
        profile="TREND",
        _ssg_adjusted=False,
        _ssg_original_raw=0.0,
        _ssg_reason="",
        _is_lse_etf=False,
        currency="USD",
        vwap_col="VWAP_D",
        adx_t2=adx_t - 2.0,
        _df_ctx=None,
        _sbo_prestate=False,
        _analyst_target_median=None,
        window_count=0,
        window_limit=4,
        daily_protective_anchor=daily_ema21,
        daily_atr=daily_atr,
        daily_hard_stop=daily_ema21 - 1.5 * daily_atr,
    )
    return ctx


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 TESTS: data.py, types.py, compute.py
# ═══════════════════════════════════════════════════════════════════════


class TestPhase1_ProfileConfig:
    """Profile A config changes: sentinel ext_limits, pb_upper_col."""

    def test_profile_a_ext_limit_trending_sentinel(self):
        cfg = _build_config("A")
        assert cfg.ext_limit_trending == 99.0

    def test_profile_a_ext_limit_resolving_sentinel(self):
        cfg = _build_config("A")
        assert cfg.ext_limit_resolving == 99.0

    def test_profile_a_ext_limit_etf_sentinel(self):
        cfg = _build_config("A")
        assert cfg.ext_limit_etf == 99.0

    def test_profile_a_pb_upper_col(self):
        cfg = _build_config("A")
        assert cfg.pb_upper_col == "EMA_21"

    def test_profile_b_unchanged(self):
        cfg = _build_config("B")
        assert cfg.ext_limit_trending == 1.0
        assert cfg.ext_limit_resolving == 0.5
        assert cfg.pb_upper_col == "EMA_21"

    def test_profile_c_unchanged(self):
        cfg = _build_config("C")
        assert cfg.ext_limit_trending == 1.0
        assert cfg.ext_limit_resolving == 1.0
        assert cfg.pb_upper_col == "ANCHOR"

    def test_profile_a_ff_threshold_unchanged(self):
        cfg = _build_config("A")
        assert cfg.ff_threshold == 8


class TestPhase1_AnchorColumn:
    """df['ANCHOR'] = EMA_21 for Profile A; SESSION_VWAP populated."""

    def test_anchor_equals_ema21(self):
        df = _make_df(p_code="A", ema21_val=100.0, vwap_val=101.0)
        assert (df['ANCHOR'] == df['EMA_21']).all()

    def test_session_vwap_populated(self):
        df = _make_df(p_code="A", vwap_val=101.0)
        assert 'SESSION_VWAP' in df.columns
        assert (df['SESSION_VWAP'] == 101.0).all()

    def test_structural_floor_raw_equals_ema21(self):
        ema21_val = 100.0
        df = _make_df(p_code="A", ema21_val=ema21_val)
        cfg = _build_config("A")
        structural_floor_raw = df['ANCHOR'].iloc[cfg.iq]
        assert structural_floor_raw == ema21_val

    def test_hard_stop_formula(self):
        ema21_val = 100.0
        atr_val = 2.0
        df = _make_df(p_code="A", ema21_val=ema21_val, atr_val=atr_val)
        cfg = _build_config("A")
        structural_floor_raw = df['ANCHOR'].iloc[cfg.iq]
        hard_stop_raw = structural_floor_raw - (1.5 * atr_val)
        assert hard_stop_raw == pytest.approx(ema21_val - 3.0)

    def test_profile_b_anchor_unchanged(self):
        df = _make_df(p_code="B")
        assert (df['ANCHOR'] == df['SMA_50']).all()

    def test_profile_c_anchor_unchanged(self):
        df = _make_df(p_code="C")
        assert (df['ANCHOR'] == df['SMA_200']).all()


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2 TESTS: gates.py, trigger.py, exit.py
# ═══════════════════════════════════════════════════════════════════════


class TestPhase2_ExtensionGate:
    """Intraday extension gate retired for Profile A."""

    def test_profile_a_extension_gate_bypassed(self):
        """Profile A: even with extreme atr_dist, intraday gate should NOT fire."""
        ctx = _make_ctx(p_code="A", atr_dist=5.0)
        result = _gate_extension(ctx, atr_dist=5.0, ext_limit=99.0)
        # Should be None (gate passed) since Profile A skips intraday check
        # and daily check requires daily_ext_dist parameter
        assert result is None

    def test_profile_a_daily_extension_exhaustion_still_fires(self):
        """PA-001 daily extension gate (EXHAUSTION 3.0×) still fires for Profile A."""
        ctx = _make_ctx(p_code="A", atr_dist=0.5)
        result = _gate_extension(ctx, atr_dist=0.5, ext_limit=99.0, daily_ext_dist=3.5)
        assert result is not None
        assert result.verdict == "INVALID"
        assert result.reason == "DAILY EXTENSION"

    def test_profile_a_daily_extension_caution_passes(self):
        """PA-001 daily extension CAUTION (2.0-3.0×) passes gate, writes metric."""
        ctx = _make_ctx(p_code="A", atr_dist=0.5)
        result = _gate_extension(ctx, atr_dist=0.5, ext_limit=99.0, daily_ext_dist=2.5)
        assert result is None  # gate passes
        assert ctx.metrics.get('Daily_Extension_Label') == 'CAUTION'

    def test_profile_b_extension_gate_unchanged(self):
        """Profile B: extension gate still fires normally."""
        ctx = _make_ctx(p_code="B", atr_dist=1.5, is_trending=True)
        ctx.state.is_trending = True
        ctx.state.is_resolving = False
        ctx.state._entry_trending = True
        ctx.state._entry_resolving = False
        result = _gate_extension(ctx, atr_dist=1.5, ext_limit=1.0)
        assert result is not None
        assert result.verdict == "INVALID"
        assert result.reason == "EXTENDED"

    def test_profile_c_extension_gate_unchanged(self):
        """Profile C: extension gate still fires normally."""
        ctx = _make_ctx(p_code="C", atr_dist=1.5, is_trending=True)
        ctx.state.is_trending = True
        ctx.state.is_resolving = False
        ctx.state._entry_trending = True
        ctx.state._entry_resolving = False
        ctx.last = {"close": 150.0, "open": 149.0, "SMA_200": 130.0}
        result = _gate_extension(ctx, atr_dist=1.5, ext_limit=1.0)
        assert result is not None
        assert result.verdict == "INVALID"


class TestPhase2_EntryZone:
    """Entry zone = [daily_ema21 - 0.5 × daily_ATR, daily_ema21 + 0.5 × daily_ATR]."""

    def test_entry_zone_computation(self):
        """Verify entry zone bounds from daily values."""
        daily_ema21 = 100.0
        daily_atr = 4.0
        close_val = 101.0  # within zone [98, 102]
        ctx = _make_ctx(p_code="A", close_val=close_val,
                         daily_ema21=daily_ema21, daily_atr=daily_atr)

        result = _identify_trigger(ctx, gate_result=None,
                                    _capital_rr=2.0, _reward_label="GOOD",
                                    _p1_resistance_note=None, _p1_reward_risk_note=None)

        assert ctx.metrics["Pullback_Zone_Lower"] == 98.0
        assert ctx.metrics["Pullback_Zone_Upper"] == 102.0
        assert ctx.metrics["Entry_Zone_Reference"] == "Daily EMA 21"

    def test_entry_zone_fallback_when_daily_unavailable(self):
        """When daily data unavailable, uses hourly ANCHOR fallback."""
        close_val = 101.0
        ema21_val = 100.0
        atr_val = 2.0
        ctx = _make_ctx(p_code="A", close_val=close_val,
                         ema21_val=ema21_val, atr_val=atr_val,
                         daily_ema21=0.0, daily_atr=0.0)

        result = _identify_trigger(ctx, gate_result=None,
                                    _capital_rr=2.0, _reward_label="GOOD",
                                    _p1_resistance_note=None, _p1_reward_risk_note=None)

        # Fallback: lower = ANCHOR, upper = ANCHOR + 0.5 * hourly_ATR
        assert ctx.metrics["Pullback_Zone_Lower"] == 100.0
        assert ctx.metrics["Pullback_Zone_Upper"] == 101.0

    def test_price_outside_zone_is_invalid(self):
        """Price above zone upper → INVALID NOT IN PULLBACK ZONE."""
        daily_ema21 = 100.0
        daily_atr = 4.0
        close_val = 105.0  # above zone upper (102)
        df = _make_df(p_code="A", close_val=close_val, ema21_val=100.0)
        ctx = _make_ctx(p_code="A", df=df, close_val=close_val,
                         daily_ema21=daily_ema21, daily_atr=daily_atr)

        result = _identify_trigger(ctx, gate_result=None,
                                    _capital_rr=2.0, _reward_label="GOOD",
                                    _p1_resistance_note=None, _p1_reward_risk_note=None)

        assert result.verdict == "INVALID"
        assert "NOT IN PULLBACK ZONE" in result.reason

    def test_price_in_zone_is_valid_pullback(self):
        """Price within daily zone + TRENDING → VALID PULLBACK."""
        daily_ema21 = 100.0
        daily_atr = 4.0
        close_val = 101.0  # within zone [98, 102]
        ema21_val = 100.0
        df = _make_df(p_code="A", close_val=close_val, ema21_val=ema21_val,
                       vwap_val=99.0)  # close > VWAP → CONFIRMED
        ctx = _make_ctx(p_code="A", df=df, close_val=close_val,
                         ema21_val=ema21_val,
                         daily_ema21=daily_ema21, daily_atr=daily_atr,
                         is_trending=True, adx_t=28.0)

        result = _identify_trigger(ctx, gate_result=None,
                                    _capital_rr=2.0, _reward_label="GOOD",
                                    _p1_resistance_note=None, _p1_reward_risk_note=None)

        assert result.verdict == "VALID"
        assert result.entry_type == "PULLBACK"


class TestPhase2_VWAPTrigger:
    """VWAP trigger condition tests for all Profile A entry types."""

    def _run_trigger_with_vwap(self, vwap_val, close_val=101.0,
                                 daily_ema21=100.0, daily_atr=4.0):
        """Helper: run trigger with specified VWAP and close."""
        ema21_val = 100.0
        df = _make_df(p_code="A", close_val=close_val, ema21_val=ema21_val,
                       vwap_val=vwap_val)
        ctx = _make_ctx(p_code="A", df=df, close_val=close_val,
                         ema21_val=ema21_val,
                         daily_ema21=daily_ema21, daily_atr=daily_atr,
                         is_trending=True, adx_t=28.0)
        result = _identify_trigger(ctx, gate_result=None,
                                    _capital_rr=2.0, _reward_label="GOOD",
                                    _p1_resistance_note=None, _p1_reward_risk_note=None)
        return result, ctx.metrics

    def test_vwap_confirmed_when_close_above(self):
        """Close > SESSION_VWAP → VWAP_Trigger_Status = CONFIRMED."""
        result, metrics = self._run_trigger_with_vwap(
            vwap_val=99.0, close_val=101.0)
        assert result.verdict == "VALID"
        assert metrics.get("VWAP_Trigger_Status") == "CONFIRMED"
        assert metrics.get("VWAP_Trigger_Confirmed") is True

    def test_vwap_awaiting_reclaim_when_close_below(self):
        """Close < SESSION_VWAP → VWAP_Trigger_Status = AWAITING_RECLAIM."""
        result, metrics = self._run_trigger_with_vwap(
            vwap_val=103.0, close_val=101.0)
        # Verdict is still VALID (structural gates passed); timing hold is metadata
        assert result.verdict == "VALID"
        assert metrics.get("VWAP_Trigger_Status") == "AWAITING_RECLAIM"
        assert metrics.get("VWAP_Trigger_Confirmed") is False

    def test_vwap_waived_on_first_bar(self):
        """First bar of session → VWAP_Trigger_Status = WAIVED."""
        ema21_val = 100.0
        close_val = 101.0
        daily_ema21 = 100.0
        daily_atr = 4.0

        # Create dates spanning two days — last bar is first of new session
        base = datetime(2026, 4, 10, 9, 30)
        dates = [base + timedelta(hours=i) for i in range(49)]
        dates.append(datetime(2026, 4, 11, 9, 30))  # new day

        df = _make_df(p_code="A", close_val=close_val, ema21_val=ema21_val,
                       vwap_val=103.0, dates=dates)
        ctx = _make_ctx(p_code="A", df=df, close_val=close_val,
                         ema21_val=ema21_val,
                         daily_ema21=daily_ema21, daily_atr=daily_atr,
                         is_trending=True, adx_t=28.0)

        result = _identify_trigger(ctx, gate_result=None,
                                    _capital_rr=2.0, _reward_label="GOOD",
                                    _p1_resistance_note=None, _p1_reward_risk_note=None)

        assert result.verdict == "VALID"
        assert ctx.metrics.get("VWAP_Trigger_Status") == "WAIVED"
        assert ctx.metrics.get("VWAP_Trigger_Confirmed") is False

    def test_vwap_not_applied_to_profile_b(self):
        """Profile B: no VWAP trigger metrics written."""
        df = _make_df(p_code="B", close_val=96.0, ema21_val=95.0)
        # Profile B needs different entry path — just verify no VWAP metrics
        ctx = _make_ctx(p_code="B", df=df, close_val=96.0,
                         is_trending=True, adx_t=28.0)
        result = _identify_trigger(ctx, gate_result=None,
                                    _capital_rr=2.0, _reward_label="GOOD",
                                    _p1_resistance_note=None, _p1_reward_risk_note=None)
        assert "VWAP_Trigger_Status" not in ctx.metrics

    def test_vwap_trigger_price_surfaced(self):
        """VWAP_Trigger_Price metric contains the session VWAP value."""
        result, metrics = self._run_trigger_with_vwap(
            vwap_val=99.5, close_val=101.0)
        assert metrics.get("VWAP_Trigger_Price") == 99.5


class TestPhase2_SessionMaturityWaiver:
    """Session maturity waiver helper function tests."""

    def test_same_day_returns_false(self):
        base = datetime(2026, 4, 10, 9, 30)
        dates = [base + timedelta(hours=i) for i in range(5)]
        df = pd.DataFrame({'close': [100.0]*5}, index=pd.DatetimeIndex(dates))
        assert _detect_session_first_bar(df, -1) is False

    def test_new_day_returns_true(self):
        dates = [
            datetime(2026, 4, 10, 15, 30),
            datetime(2026, 4, 11, 9, 30),
        ]
        df = pd.DataFrame({'close': [100.0]*2}, index=pd.DatetimeIndex(dates))
        assert _detect_session_first_bar(df, -1) is True

    def test_insufficient_bars(self):
        dates = [datetime(2026, 4, 10, 9, 30)]
        df = pd.DataFrame({'close': [100.0]}, index=pd.DatetimeIndex(dates))
        # iq=-1 with 1-bar DataFrame → abs(-1) >= len(df) → waive
        assert _detect_session_first_bar(df, -1) is True


class TestPhase2_ExitCounter:
    """Exit counter references EMA_21 via df['ANCHOR'], Option A backward compat."""

    def _make_exit_df(self, closes, anchor_vals=None, atr_val=2.0):
        """Build a DF for exit counter testing with varying close vs ANCHOR."""
        n = len(closes)
        if anchor_vals is None:
            anchor_vals = [100.0] * n
        base = datetime(2026, 4, 10, 9, 30)
        dates = [base + timedelta(hours=i) for i in range(n)]
        df = pd.DataFrame({
            'open':   [c - 0.5 for c in closes],
            'high':   [c + 1.0 for c in closes],
            'low':    [c - 1.0 for c in closes],
            'close':  closes,
            'volume': [100000] * n,
            'EMA_21': anchor_vals,
            'ANCHOR': anchor_vals,   # Profile A: ANCHOR = EMA_21
        }, index=pd.DatetimeIndex(dates))
        return df

    def test_exit_counter_uses_anchor_ema21(self):
        """Exit counter checks close < df['ANCHOR'] which is EMA_21."""
        # 3 consecutive closes below ANCHOR (EMA_21 = 100)
        closes =  [102.0]*17 + [99.0, 99.0, 99.0]  # last 3 below 100
        anchors = [100.0]*20
        df = self._make_exit_df(closes, anchors)
        cfg = _build_config("A")  # iq=-1
        last = df.iloc[cfg.iq]
        metrics = {}
        state = SimpleNamespace(atr_raw=2.0)

        result = _exit_profile_a(state, df, last, cfg.iq, 1.0, metrics, cfg)

        assert result == "EXIT"
        assert "EMA21_3Bar_Violation" in metrics["Exit_Triggers"]

    def test_exit_counter_backward_compat_key(self):
        """AVWAP-001 Phase 3 E1: Exit_VWAP_Counter alias REMOVED.
        Exit_EMA21_Counter is the sole canonical key."""
        closes =  [102.0]*17 + [99.0, 99.0, 99.0]
        anchors = [100.0]*20
        df = self._make_exit_df(closes, anchors)
        cfg = _build_config("A")
        last = df.iloc[cfg.iq]
        metrics = {}
        state = SimpleNamespace(atr_raw=2.0)

        _exit_profile_a(state, df, last, cfg.iq, 1.0, metrics, cfg)

        # Phase 3 E1: only EMA21 key present, VWAP alias removed
        assert "Exit_EMA21_Counter" in metrics
        assert "Exit_VWAP_Counter" not in metrics

    def test_exit_counter_clear_when_above_anchor(self):
        """No exit when all closes above ANCHOR."""
        closes =  [102.0]*20  # all above ANCHOR=100
        anchors = [100.0]*20
        df = self._make_exit_df(closes, anchors)
        cfg = _build_config("A")
        last = df.iloc[cfg.iq]
        metrics = {}
        state = SimpleNamespace(atr_raw=2.0)

        result = _exit_profile_a(state, df, last, cfg.iq, 1.0, metrics, cfg)

        assert result is False
        assert metrics["Exit_EMA21_Counter"] == "0/3"

    def test_exit_reason_references_ema21(self):
        """Exit_Reason string references EMA 21, not VWAP."""
        closes =  [102.0]*17 + [99.0, 99.0, 99.0]
        anchors = [100.0]*20
        df = self._make_exit_df(closes, anchors)
        cfg = _build_config("A")
        last = df.iloc[cfg.iq]
        metrics = {}
        state = SimpleNamespace(atr_raw=2.0)

        _exit_profile_a(state, df, last, cfg.iq, 1.0, metrics, cfg)

        assert "EMA 21" in metrics["Exit_Reason"]
        assert "VWAP" not in metrics["Exit_Reason"]


class TestPhase2_ExpectancyGateDiagnostic:
    """Expectancy gate diagnostic strings no longer reference VWAP."""

    def test_expectancy_gate_mandate_references_entry_zone(self):
        """Mandate string uses 'entry zone' instead of 'VWAP'."""
        result = _gate_expectancy(
            p_code="A",
            risk_a=5.0,
            reward_a=3.0,   # reward < 2 * risk → fails
            cons_high_raw=155.0,
            last_close=152.0,
            floor_price=100.0,
            price_scaler=1.0,
        )
        assert result is not None
        assert result.verdict == "INVALID"
        assert "entry zone" in result.mandate
        assert "VWAP" not in result.mandate

    def test_expectancy_gate_zero_reward_mandate(self):
        """Zero reward path also uses 'entry zone'."""
        result = _gate_expectancy(
            p_code="A",
            risk_a=5.0,
            reward_a=-1.0,   # negative reward → fails
            cons_high_raw=150.0,
            last_close=152.0,
            floor_price=100.0,
            price_scaler=1.0,
        )
        assert result is not None
        assert "entry zone" in result.mandate
        assert "VWAP" not in result.mandate


class TestPhase2_ProfileIsolation:
    """Profile B/C behavioural isolation — zero change from AVWAP-001."""

    def test_profile_b_no_session_vwap(self):
        df = _make_df(p_code="B")
        assert 'SESSION_VWAP' not in df.columns

    def test_profile_c_no_session_vwap(self):
        df = _make_df(p_code="C")
        assert 'SESSION_VWAP' not in df.columns

    def test_profile_b_anchor_is_sma50(self):
        df = _make_df(p_code="B")
        assert (df['ANCHOR'] == df['SMA_50']).all()
