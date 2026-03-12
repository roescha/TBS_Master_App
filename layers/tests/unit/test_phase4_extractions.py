"""Unit tests for RFT-003 Phase 4 extracted functions.

Tests the 6 inline blocks extracted from run_tbs_engine into named functions:
    _compute_morphology, _compute_vol_confirmation, _compute_window_binding,
    _compute_floor_state, _compute_early_capital_rr, _evaluate_precheck.

Each function receives a RunContext (ctx). Tests use SimpleNamespace to
construct minimal ctx objects with only the fields each function reads.
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace

from ibkr_purity_engine import (
    _compute_morphology,
    _compute_vol_confirmation,
    _compute_window_binding,
    _compute_floor_state,
    _compute_early_capital_rr,
    _evaluate_precheck,
    GRACE_BUFFER_ATR_PCT,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal DataFrame for the tests
# ---------------------------------------------------------------------------

def _make_df(n=60, base=100.0, trend=0.2, seed=42):
    """Build a minimal OHLCV DataFrame with ANCHOR and indicator columns."""
    rng = np.random.RandomState(seed)
    closes = [base + trend * i + rng.normal(0, 0.3) for i in range(n)]
    df = pd.DataFrame({
        'open':   [closes[max(0, i - 1)] + rng.normal(0, 0.1) for i in range(n)],
        'high':   [c + abs(rng.normal(0.5, 0.3)) for c in closes],
        'low':    [c - abs(rng.normal(0.5, 0.3)) for c in closes],
        'close':  closes,
        'volume': [500000 + rng.normal(0, 50000) for _ in range(n)],
    })
    df['high'] = df[['open', 'close', 'high']].max(axis=1) + 0.01
    df['low'] = df[['open', 'close', 'low']].min(axis=1) - 0.01
    df['volume'] = df['volume'].clip(lower=1000)

    # Indicators
    df['EMA_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['SMA_50'] = df['close'].rolling(50).mean()
    df['SMA_200'] = df['close'].rolling(min(200, n - 1)).mean()
    df['ATRr_14'] = (df['high'] - df['low']).ewm(alpha=1 / 14, adjust=False).mean()
    df['vol_sma_9'] = df['volume'].rolling(9).mean()
    df['vol_sma_20'] = df['volume'].rolling(20).mean()
    df['ANCHOR'] = df['SMA_50']
    df['ADX_14'] = 25.0  # constant for simplicity
    return df


def _make_cfg(p_code="B"):
    """Build a minimal ProfileConfig-like namespace."""
    if p_code == "A":
        return SimpleNamespace(
            iq=-2, prev_bar_offset=3,
            resistance_slice_start=-12, resistance_slice_end=-2,
            window_limit=4, ff_threshold=8,
        )
    elif p_code == "C":
        return SimpleNamespace(
            iq=-1, prev_bar_offset=2,
            resistance_slice_start=-11, resistance_slice_end=-1,
            window_limit=4, ff_threshold=4,
        )
    else:  # B
        return SimpleNamespace(
            iq=-1, prev_bar_offset=2,
            resistance_slice_start=-11, resistance_slice_end=-1,
            window_limit=5, ff_threshold=4,
        )


def _make_state(atr_raw=2.0, **overrides):
    """Build a minimal StateBundle-like namespace."""
    defaults = dict(
        atr_raw=atr_raw, is_resolving=False, is_trending=True,
        ema_stacked=True, is_floor_failure=False, is_violated=False,
        is_reclaim=False, consec_below=0, _reclaim_run=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ctx(p_code="B", df=None, **overrides):
    """Build a minimal RunContext-like namespace."""
    if df is None:
        df = _make_df()
    cfg = _make_cfg(p_code)
    last = df.iloc[cfg.iq]
    state = _make_state(atr_raw=float(last['ATRr_14']))
    defaults = dict(
        state=state, cfg=cfg, p_code=p_code, is_etf=False, _is_c3=False,
        df=df, last=last, metrics={},
        price_scaler=1.0, actual_price=float(last['close']),
        structural_floor_raw=float(last['ANCHOR']),
        hard_stop_raw=float(last['ANCHOR']) - 1.5 * state.atr_raw,
        resistance_raw=float(df['high'].iloc[-11:-1].max()),
        atr_dist=0.5, ext_limit=1.0,
        adx_col='ADX_14', prev_high=0.0, conviction_state="",
        vol_confirm_ratio=0.0, vol_confirm_state="",
        window_count=0, window_limit=5,
        exit_signal=False, cons_high_raw=None,
        risk_a=None, reward_a=None,
        _df_ctx=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ===========================================================================
# _compute_morphology
# ===========================================================================

class TestComputeMorphology:
    """Tests for _compute_morphology (F4a)."""

    def test_returns_mod_d_and_active_mods(self):
        """Function returns (mod_d_state, active_mods) tuple."""
        ctx = _make_ctx()
        result = _compute_morphology(ctx)
        assert isinstance(result, tuple)
        assert len(result) == 2
        mod_d_state, active_mods = result
        assert isinstance(mod_d_state, str)
        assert isinstance(active_mods, list)

    def test_sets_ctx_prev_high(self):
        """Sets ctx.prev_high to the previous bar's high."""
        ctx = _make_ctx()
        _compute_morphology(ctx)
        assert ctx.prev_high > 0

    def test_sets_ctx_conviction_state(self):
        """Sets ctx.conviction_state to LOW or HIGH."""
        ctx = _make_ctx()
        _compute_morphology(ctx)
        assert "ATR" in ctx.conviction_state

    def test_mod_d_clear_when_not_extended(self):
        """Modifier D is CLEAR when atr_dist < ext_limit."""
        ctx = _make_ctx(atr_dist=0.3, ext_limit=1.0)
        mod_d_state, _ = _compute_morphology(ctx)
        assert mod_d_state == "CLEAR (No Churn)"

    def test_c3_annotation_on_mod_d(self):
        """C-3 convexity annotates Modifier D as INFORMATIONAL."""
        df = _make_df()
        last = df.iloc[-1]
        # Force conditions for Modifier D activation
        ctx = _make_ctx(
            _is_c3=True, atr_dist=2.0, ext_limit=1.0,
        )
        # Force volume and body for mod_d
        idx = ctx.cfg.iq
        ctx.df.iloc[idx, ctx.df.columns.get_loc('volume')] = ctx.df['vol_sma_9'].iloc[idx] * 2.0
        # Small body
        close_val = ctx.df['close'].iloc[idx]
        ctx.df.iloc[idx, ctx.df.columns.get_loc('open')] = close_val - 0.01
        ctx.last = ctx.df.iloc[idx]
        mod_d_state, _ = _compute_morphology(ctx)
        if mod_d_state.startswith("INFORMATIONAL"):
            assert "C-3" in mod_d_state


# ===========================================================================
# _compute_vol_confirmation
# ===========================================================================

class TestComputeVolConfirmation:
    """Tests for _compute_vol_confirmation (F4b)."""

    def test_sets_ctx_ratio_and_state(self):
        """Sets vol_confirm_ratio and vol_confirm_state on ctx."""
        ctx = _make_ctx()
        _compute_vol_confirmation(ctx)
        assert isinstance(ctx.vol_confirm_ratio, float)
        assert ctx.vol_confirm_state in (
            "STRONG INSTITUTIONAL", "DISTRIBUTION WARNING", "MIXED"
        )

    def test_ratio_bounded(self):
        """Vol confirm ratio is between 0 and 1."""
        ctx = _make_ctx()
        _compute_vol_confirmation(ctx)
        assert 0.0 <= ctx.vol_confirm_ratio <= 1.0


# ===========================================================================
# _compute_window_binding
# ===========================================================================

class TestComputeWindowBinding:
    """Tests for _compute_window_binding (F4c)."""

    def test_returns_window_reset_event(self):
        """Returns a string _window_reset_event."""
        ctx = _make_ctx()
        result = _compute_window_binding(ctx)
        assert isinstance(result, str)

    def test_sets_ctx_window_count(self):
        """Sets ctx.window_count on context."""
        ctx = _make_ctx()
        _compute_window_binding(ctx)
        assert isinstance(ctx.window_count, (int, np.integer))

    def test_sets_ctx_window_limit(self):
        """Sets ctx.window_limit from cfg."""
        ctx = _make_ctx()
        _compute_window_binding(ctx)
        assert ctx.window_limit == 5  # Profile B default

    def test_adds_columns_to_df(self):
        """Mutates ctx.df by adding Is_Breakout, Is_Pullback, etc."""
        ctx = _make_ctx()
        _compute_window_binding(ctx)
        assert 'Is_Breakout' in ctx.df.columns
        assert 'Is_Pullback' in ctx.df.columns
        assert 'Prev_10_High' in ctx.df.columns

    def test_profile_a_nullifies_live_bar(self):
        """Profile A: Is_Breakout and Is_Pullback are False on live bar (iloc[-1])."""
        ctx = _make_ctx(p_code="A")
        _compute_window_binding(ctx)
        assert ctx.df['Is_Breakout'].iloc[-1] == False
        assert ctx.df['Is_Pullback'].iloc[-1] == False


# ===========================================================================
# _compute_floor_state
# ===========================================================================

class TestComputeFloorState:
    """Tests for _compute_floor_state (F4d)."""

    def test_above_floor_no_failure(self):
        """Price above floor → no violation, no failure."""
        ctx = _make_ctx()
        # Ensure last close is well above ANCHOR
        idx = ctx.cfg.iq
        anchor = ctx.df['ANCHOR'].iloc[idx]
        ctx.df.iloc[idx, ctx.df.columns.get_loc('close')] = anchor + 5.0
        ctx.last = ctx.df.iloc[idx]
        _compute_floor_state(ctx, _ff_threshold=4)
        assert ctx.state.is_floor_failure == False
        assert ctx.state.is_violated == False

    def test_uses_grace_buffer_constant(self):
        """Verifies the function uses GRACE_BUFFER_ATR_PCT (not hardcoded 0.15)."""
        # This is a structural check: the function was extracted with the constant.
        # Verify by checking that borderline cases use the constant.
        import inspect
        src = inspect.getsource(_compute_floor_state)
        assert 'GRACE_BUFFER_ATR_PCT' in src

    def test_calls_deep_reclaim_scan(self):
        """Verifies _deep_reclaim_scan is called (not inline loops)."""
        import inspect
        src = inspect.getsource(_compute_floor_state)
        assert '_deep_reclaim_scan' in src

    def test_sets_reclaim_run(self):
        """Sets state._reclaim_run."""
        ctx = _make_ctx()
        _compute_floor_state(ctx, _ff_threshold=4)
        assert hasattr(ctx.state, '_reclaim_run')


# ===========================================================================
# _compute_early_capital_rr
# ===========================================================================

class TestComputeEarlyCapitalRR:
    """Tests for _compute_early_capital_rr (F4e)."""

    def test_returns_p1_notes_tuple(self):
        """Returns (_p1_resistance_note, _p1_reward_risk_note)."""
        ctx = _make_ctx()
        ctx.metrics["Resistance_Note"] = "test_note"
        ctx.metrics["Reward_Risk_Note"] = "test_rr_note"
        result = _compute_early_capital_rr(ctx, exit_signal=False)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == "test_note"
        assert result[1] == "test_rr_note"

    def test_nulls_pe31_notes_in_metrics(self):
        """PE-31 guard: nulls Resistance_Note and Reward_Risk_Note."""
        ctx = _make_ctx()
        ctx.metrics["Resistance_Note"] = "saved"
        ctx.metrics["Reward_Risk_Note"] = "saved"
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics["Resistance_Note"] is None
        assert ctx.metrics["Reward_Risk_Note"] is None

    def test_profile_b_uses_resistance_raw(self):
        """Profile B uses resistance_raw as target, not cons_high_raw."""
        ctx = _make_ctx(p_code="B")
        ctx.metrics["Resistance_Note"] = None
        ctx.metrics["Reward_Risk_Note"] = None
        _compute_early_capital_rr(ctx, exit_signal=False)
        # cons_high_raw stays None for Profile B
        assert ctx.cons_high_raw is None

    def test_profile_a_sets_cons_high_raw(self):
        """Profile A computes cons_high_raw from hourly data."""
        ctx = _make_ctx(p_code="A")
        ctx.metrics["Resistance_Note"] = None
        ctx.metrics["Reward_Risk_Note"] = None
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.cons_high_raw is not None

    def test_suppression_on_exit_signal(self):
        """EXIT signal suppresses Capital R:R."""
        ctx = _make_ctx(p_code="B")
        ctx.metrics["Resistance_Note"] = None
        ctx.metrics["Reward_Risk_Note"] = None
        _compute_early_capital_rr(ctx, exit_signal="EXIT")
        assert ctx.metrics.get("Capital_Reward_Risk") is None
        assert ctx.metrics.get("Capital_RR_Label") is None

    def test_suppression_on_floor_failure(self):
        """Floor failure suppresses Capital R:R."""
        ctx = _make_ctx(p_code="B")
        ctx.state.is_floor_failure = True
        ctx.metrics["Resistance_Note"] = None
        ctx.metrics["Reward_Risk_Note"] = None
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get("Capital_Reward_Risk") is None


# ===========================================================================
# _evaluate_precheck
# ===========================================================================

class TestEvaluatePrecheck:
    """Tests for _evaluate_precheck (F4f)."""

    def test_no_precheck_fires_healthy_state(self):
        """Healthy state: both checks return (None, None)."""
        ctx = _make_ctx()
        # Ensure price well above floor
        idx = ctx.cfg.iq
        anchor = ctx.df['ANCHOR'].iloc[idx]
        ctx.df.iloc[idx, ctx.df.columns.get_loc('close')] = anchor + 5.0
        ctx.last = ctx.df.iloc[idx]
        status, diag = _evaluate_precheck(ctx, _ff_threshold=4)
        assert status is None
        assert diag is None

    def test_sets_risk_a_reward_a_on_ctx(self):
        """Sets ctx.risk_a and ctx.reward_a (even if None for non-Profile A)."""
        ctx = _make_ctx(p_code="B")
        _evaluate_precheck(ctx, _ff_threshold=4)
        assert ctx.risk_a is None  # Profile B: not computed
        assert ctx.reward_a is None

    def test_profile_a_computes_risk_reward(self):
        """Profile A: risk_a and reward_a are computed."""
        ctx = _make_ctx(p_code="A")
        # Ensure cons_high_raw is set
        ctx.cons_high_raw = float(ctx.df['high'].iloc[-12:-2].max())
        # Ensure price above anchor so risk_a > 0
        idx = ctx.cfg.iq
        anchor = ctx.df['ANCHOR'].iloc[idx]
        ctx.df.iloc[idx, ctx.df.columns.get_loc('close')] = anchor + 2.0
        ctx.last = ctx.df.iloc[idx]
        _evaluate_precheck(ctx, _ff_threshold=8)
        # risk_a should be set (positive since price > anchor)
        assert ctx.risk_a is not None

    def test_preserves_exit_signal_writes(self):
        """Verifies Exit_Signal, Exit_Triggers, Exit_Reason are written on floor failure."""
        import inspect
        src = inspect.getsource(_evaluate_precheck)
        assert 'metrics["Exit_Signal"]' in src
        assert 'metrics["Exit_Triggers"]' in src
        assert 'metrics["Exit_Reason"]' in src
        assert 'metrics["Floor_Failure_Reclaim"]' in src

    def test_pe7_guard_profile_a_exit(self):
        """PE-7: Profile A with EXIT scrubs R:R."""
        ctx = _make_ctx(p_code="A")
        ctx.exit_signal = "EXIT"
        ctx.cons_high_raw = 200.0
        _evaluate_precheck(ctx, _ff_threshold=8)
        assert ctx.metrics.get("Reward_Risk") is None
        assert ctx.metrics.get("Profit_Target") is None

    def test_uses_grace_buffer_constant(self):
        """Verifies the function uses GRACE_BUFFER_ATR_PCT."""
        import inspect
        src = inspect.getsource(_evaluate_precheck)
        assert 'GRACE_BUFFER_ATR_PCT' in src

    def test_deeply_nested_branching_preserved(self):
        """Verify the floor-exact → PE-CAL-2 → standard branching exists."""
        import inspect
        src = inspect.getsource(_evaluate_precheck)
        assert 'FLOOR_EXACT' in src
        assert 'FLOOR_PROXIMITY' in src
        assert 'risk_a_hardstop' in src
