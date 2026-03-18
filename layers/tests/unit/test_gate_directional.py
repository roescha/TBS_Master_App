"""Unit tests for _gate_directional.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
import math
from ibkr_purity_engine import GateResult, _gate_directional


class TestGateDirectional:
    """Tests for Gate 4.1 — Directional Dominance."""

    def test_nominal_pass_plus_dominant(self):
        """di_plus=30 > di_minus=20 — gate passes."""
        result = _gate_directional(
            di_plus=30.0, di_minus=20.0, p_code="B",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is None

    def test_nominal_fail_minus_dominant(self):
        """di_minus=30 > di_plus=20, no exemption — gate fires."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="B",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "DIRECTIONAL BLOCK"
        assert result.legacy_diagnostic is not None
        assert "-DI (30.00) > +DI (20.00)" in result.legacy_diagnostic

    def test_boundary_di_equal(self):
        """di_plus == di_minus — NOT minus > plus, gate passes."""
        result = _gate_directional(
            di_plus=25.0, di_minus=25.0, p_code="B",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is None

    def test_variant_profile_a_ema_stack_exemption(self):
        """Profile A: -DI dominant but ema_stacked=True — exemption, gate passes."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="A",
            ema_stacked=True, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is None

    def test_variant_profile_a_no_ema_exemption(self):
        """Profile A: -DI dominant, ema_stacked=False — no exemption, gate fires."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="A",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_profile_b_trending_exemption(self):
        """Profile B: -DI dominant but TRENDING + full MA stack — exemption, gate passes."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="B",
            ema_stacked=False, _entry_trending=True,
            ma_stack_full=True, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is None

    def test_variant_profile_b_trending_no_full_stack(self):
        """Profile B: TRENDING but ma_stack_full=False — no exemption, gate fires."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="B",
            ema_stacked=False, _entry_trending=True,
            ma_stack_full=False, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_profile_c_counter_cyclical_exemption(self):
        """Profile C: within 5% of SMA 200 + positive ADX slope — exemption."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="C",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=4.0,
            adx_t=26.0, adx_t1=25.0,  # positive slope
        )
        assert result is None

    def test_variant_profile_c_no_exemption_far_from_floor(self):
        """Profile C: floor_prox_pct > 5% — no counter-cyclical exemption."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="C",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=6.0,
            adx_t=26.0, adx_t1=25.0,
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_profile_c_negative_adx_slope(self):
        """Profile C: within 5% but ADX declining — no exemption."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="C",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=3.0,
            adx_t=24.0, adx_t1=25.0,  # negative slope
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_nan_di_values(self):
        """NaN DI values — data integrity rejection."""
        result = _gate_directional(
            di_plus=float("nan"), di_minus=25.0, p_code="B",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert "DATA INTEGRITY" in result.legacy_diagnostic

    def test_variant_nan_di_minus(self):
        """NaN di_minus — data integrity rejection."""
        result = _gate_directional(
            di_plus=25.0, di_minus=float("nan"), p_code="B",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=10.0,
            adx_t=25.0, adx_t1=24.0,
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert "DATA INTEGRITY" in result.legacy_diagnostic

    def test_variant_profile_c_boundary_5pct(self):
        """Profile C: floor_prox_pct=5.0 (exactly at threshold) — exemption applies (<= 5.0)."""
        result = _gate_directional(
            di_plus=20.0, di_minus=30.0, p_code="C",
            ema_stacked=False, _entry_trending=False,
            ma_stack_full=False, floor_prox_pct=5.0,
            adx_t=26.0, adx_t1=25.0,
        )
        assert result is None
