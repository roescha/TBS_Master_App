"""Unit tests for _identify_trigger GateResult returns.

DIAG-001 Phase 2A — §8.4
Verifies all 8 trigger paths: 3 VALID + 5 INVALID.
Verifies Pullback_Zone_Upper written to metrics on all paths.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from ibkr_purity_engine import GateResult, _identify_trigger


def _make_trigger_ctx(
    p_code="B", is_etf=False, is_reclaim=False,
    entry_trending=False, entry_resolving=False,
    adx_t=28.0, close=100.0, anchor=95.0, ema8=97.0,
    pb_upper_col_val=98.0, resistance_raw=110.0,
    atr_raw=2.0, floor_price=95.0, hard_stop="90.00",
    resistance_display=110.0, resistance_suppressed=False,
    consec_below=3,
    ff_threshold=4, is_breakout=True, ma_stack_full=True,
):
    """Build minimal RunContext mock for _identify_trigger."""
    ctx = MagicMock()
    state = MagicMock()
    cfg = MagicMock()

    state.is_reclaim = is_reclaim
    state._entry_trending = entry_trending
    state._entry_resolving = entry_resolving
    state.adx_t = adx_t
    state.atr_raw = atr_raw
    state.consec_below = consec_below
    state.ma_stack_full = ma_stack_full

    cfg.ff_threshold = ff_threshold
    cfg.pb_upper_col = "PB_UPPER"

    # Build minimal DataFrame
    n = 5
    data = {
        'close': [close] * n,
        'ANCHOR': [anchor] * n,
        'EMA_8': [ema8] * n,
        'PB_UPPER': [pb_upper_col_val] * n,
        'open': [close - 1] * n,
        'Is_Breakout': [is_breakout] * n,
    }
    df = pd.DataFrame(data)
    last = df.iloc[-1]

    ctx.state = state
    ctx.cfg = cfg
    ctx.p_code = p_code
    ctx.is_etf = is_etf
    ctx.metrics = {}
    ctx.last = last
    ctx.df = df
    ctx.resistance_raw = resistance_raw
    ctx.resistance_display = resistance_display
    ctx.floor_price = floor_price
    ctx.hard_stop = hard_stop
    ctx.chart_ref = ""
    ctx.price_scaler = 1.0
    ctx._resistance_suppressed = resistance_suppressed

    return ctx


class TestIdentifyTriggerValidPaths:
    """3 VALID paths: RECLAIM, PULLBACK, BREAKOUT."""

    def test_reclaim_valid(self):
        """Reclaim with TRENDING state → VALID RECLAIM."""
        ctx = _make_trigger_ctx(
            is_reclaim=True, entry_trending=True,
            close=96.0, anchor=95.0, floor_price=95.0,
        )
        result = _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=1.8, _reward_label="HEALTHY",
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert isinstance(result, GateResult)
        assert result.verdict == "VALID"
        assert result.reason == "RECLAIM"
        assert result.entry_type == "RECLAIM"
        assert result.trigger_rule == "BAR CLOSE ONLY"
        assert result.state in ("TRENDING", "RESOLVING")
        assert result.mandate is not None
        assert result.context is not None
        assert result.legacy_diagnostic is not None
        assert "PRE-APPROVED" in result.legacy_diagnostic
        # Pullback_Zone_Upper written
        assert "Pullback_Zone_Upper" in ctx.metrics

    def test_pullback_valid(self):
        """Price in pullback zone during TRENDING → VALID PULLBACK."""
        ctx = _make_trigger_ctx(
            entry_trending=True,
            close=96.0, anchor=95.0, pb_upper_col_val=98.0,
            atr_raw=2.0,
        )
        result = _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=2.0, _reward_label="HEALTHY",
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert isinstance(result, GateResult)
        assert result.verdict == "VALID"
        assert result.reason == "PULLBACK"
        assert result.entry_type == "PULLBACK"
        assert result.trigger_rule == "BAR CLOSE ONLY"
        assert result.state == "TRENDING"
        assert result.legacy_diagnostic is not None
        assert "PRE-APPROVED" in result.legacy_diagnostic
        assert "Pullback_Zone_Upper" in ctx.metrics

    def test_breakout_valid(self):
        """Close above resistance in RESOLVING → VALID BREAKOUT."""
        ctx = _make_trigger_ctx(
            entry_resolving=True, p_code="B",
            close=115.0, anchor=95.0, ema8=97.0,
            resistance_raw=110.0,
        )
        result = _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=1.5, _reward_label="HEALTHY",
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert isinstance(result, GateResult)
        assert result.verdict == "VALID"
        assert result.reason == "BREAKOUT"
        assert result.entry_type == "BREAKOUT"
        assert result.trigger_rule == "INTRADAY"
        assert result.state == "RESOLVING"
        assert result.legacy_diagnostic is not None
        assert "PRE-APPROVED" in result.legacy_diagnostic
        assert "Pullback_Zone_Upper" in ctx.metrics


class TestIdentifyTriggerInvalidPaths:
    """5 INVALID paths."""

    def test_reclaim_without_regime(self):
        """Reclaim with AMBIGUOUS state → INVALID RECLAIM WITHOUT REGIME."""
        ctx = _make_trigger_ctx(
            is_reclaim=True,
            entry_trending=False, entry_resolving=False,
            close=96.0, anchor=95.0,
        )
        result = _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=None, _reward_label=None,
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "RECLAIM WITHOUT REGIME"
        assert result.legacy_diagnostic is not None
        assert "Pullback_Zone_Upper" in ctx.metrics

    def test_not_in_pullback_zone(self):
        """TRENDING but price above pullback zone → INVALID NOT IN PULLBACK ZONE."""
        ctx = _make_trigger_ctx(
            entry_trending=True,
            close=120.0, anchor=95.0, pb_upper_col_val=98.0,
            atr_raw=2.0,
        )
        result = _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=None, _reward_label=None,
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "NOT IN PULLBACK ZONE"
        assert result.legacy_diagnostic is not None
        assert "Pullback_Zone_Upper" in ctx.metrics

    def test_profile_a_resolving_block(self):
        """Profile A in RESOLVING state → INVALID PROFILE A RESOLVING BLOCK."""
        ctx = _make_trigger_ctx(
            p_code="A", entry_resolving=True, entry_trending=False,
            close=100.0, anchor=95.0,
        )
        result = _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=None, _reward_label=None,
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "PROFILE A RESOLVING BLOCK"
        assert result.legacy_diagnostic is not None
        assert "Pullback_Zone_Upper" in ctx.metrics

    def test_no_breakout(self):
        """RESOLVING but no breakout → INVALID NO BREAKOUT."""
        ctx = _make_trigger_ctx(
            p_code="B", entry_resolving=True,
            close=105.0, anchor=95.0,
            resistance_raw=110.0, is_breakout=False,
        )
        result = _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=None, _reward_label=None,
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "NO BREAKOUT"
        assert result.legacy_diagnostic is not None
        assert "Pullback_Zone_Upper" in ctx.metrics

    def test_ambiguous_state(self):
        """ADX > 20 but no trending/resolving → INVALID AMBIGUOUS STATE."""
        ctx = _make_trigger_ctx(
            entry_trending=False, entry_resolving=False,
            is_reclaim=False, adx_t=22.0,
            close=100.0, anchor=95.0,
        )
        result = _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=None, _reward_label=None,
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "AMBIGUOUS STATE"
        assert result.legacy_diagnostic is not None
        assert "Pullback_Zone_Upper" in ctx.metrics


class TestIdentifyTriggerPassthrough:
    """Gate result passthrough: prior gate fires → trigger skipped."""

    def test_prior_gate_passes_through(self):
        """When gate_result is already set, trigger returns it unchanged."""
        prior = GateResult(
            verdict="INVALID", reason="EXTENDED",
            mandate="WAIT.", context="Extended.",
            legacy_diagnostic="WAIT (reason: EXTENDED)...",
        )
        ctx = _make_trigger_ctx(close=100.0, anchor=95.0)
        result = _identify_trigger(
            ctx, gate_result=prior,
            _capital_rr=None, _reward_label=None,
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert result is prior
        assert result.reason == "EXTENDED"
        # Pullback_Zone_Upper still written
        assert "Pullback_Zone_Upper" in ctx.metrics


class TestPullbackZoneUpperMetric:
    """Pullback_Zone_Upper written on ALL paths."""

    def test_written_on_valid_path(self):
        """Pullback_Zone_Upper written when trigger resolves VALID."""
        ctx = _make_trigger_ctx(
            entry_trending=True,
            close=96.0, anchor=95.0, pb_upper_col_val=98.0,
            atr_raw=2.0,
        )
        _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=2.0, _reward_label="HEALTHY",
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert "Pullback_Zone_Upper" in ctx.metrics
        # Value = round((pb_upper_col_val + 0.5 * atr_raw) / price_scaler, 2)
        expected = round((98.0 + 0.5 * 2.0) / 1.0, 2)
        assert ctx.metrics["Pullback_Zone_Upper"] == expected

    def test_written_on_invalid_path(self):
        """Pullback_Zone_Upper written when trigger resolves INVALID."""
        ctx = _make_trigger_ctx(
            entry_trending=False, entry_resolving=False,
            is_reclaim=False,
        )
        _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=None, _reward_label=None,
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        assert "Pullback_Zone_Upper" in ctx.metrics

    def test_value_matches_formula(self):
        """Pullback_Zone_Upper = round((pb_upper_col + 0.5 * atr_raw) / price_scaler, 2)."""
        ctx = _make_trigger_ctx(
            pb_upper_col_val=150.0, atr_raw=5.0,
        )
        ctx.price_scaler = 100.0  # e.g. LSE pence
        _identify_trigger(
            ctx, gate_result=None,
            _capital_rr=None, _reward_label=None,
            _p1_resistance_note=None, _p1_reward_risk_note=None,
        )
        expected = round((150.0 + 0.5 * 5.0) / 100.0, 2)
        assert ctx.metrics["Pullback_Zone_Upper"] == expected
