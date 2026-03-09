"""Unit tests for _gate_expectancy.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
from ibkr_purity_engine import _gate_expectancy


class TestGateExpectancy:
    """Tests for Gate 5.6 — Expectancy Gate (Profile A)."""

    def test_nominal_pass_profile_b_skipped(self, metrics):
        """Profile B — gate skips entirely, returns None."""
        result = _gate_expectancy(
            p_code="B", risk_a=1.0, reward_a=0.5,
            cons_high_raw=160.0, last_close=150.0,
            floor_price=140.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None

    def test_nominal_pass_profile_c_skipped(self, metrics):
        """Profile C — gate skips entirely."""
        result = _gate_expectancy(
            p_code="C", risk_a=1.0, reward_a=0.5,
            cons_high_raw=160.0, last_close=150.0,
            floor_price=140.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None

    def test_nominal_pass_good_rr(self, metrics):
        """Profile A: reward >= 2*risk — gate passes."""
        result = _gate_expectancy(
            p_code="A", risk_a=5.0, reward_a=12.0,  # 12 >= 2*5=10
            cons_high_raw=162.0, last_close=150.0,
            floor_price=145.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None

    def test_nominal_fail_bad_rr(self, metrics):
        """Profile A: rr=0.8 (reward < 2*risk) — gate fires."""
        # risk=5.0, reward=4.0 → 4.0 < 2*5.0=10.0
        result = _gate_expectancy(
            p_code="A", risk_a=5.0, reward_a=4.0,
            cons_high_raw=154.0, last_close=150.0,
            floor_price=145.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: EXPECTANCY FAILED)")

    def test_boundary_exactly_at_minimum(self, metrics):
        """Profile A: reward = exactly 2*risk — NOT < 2*risk, gate passes."""
        result = _gate_expectancy(
            p_code="A", risk_a=5.0, reward_a=10.0,  # 10.0 == 2*5.0
            cons_high_raw=160.0, last_close=150.0,
            floor_price=145.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None

    def test_boundary_just_below_minimum(self, metrics):
        """Profile A: reward just below 2*risk — gate fires."""
        result = _gate_expectancy(
            p_code="A", risk_a=5.0, reward_a=9.99,
            cons_high_raw=160.0, last_close=150.0,
            floor_price=145.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_floor_exact_entry(self, metrics):
        """risk_a=0 — floor-exact entry, gate passes (PE-CAL-2 bypass)."""
        result = _gate_expectancy(
            p_code="A", risk_a=0, reward_a=5.0,
            cons_high_raw=155.0, last_close=150.0,
            floor_price=150.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None

    def test_variant_reward_zero_or_negative(self, metrics):
        """reward <= 0: price exceeded consolidation high — specific diagnostic."""
        result = _gate_expectancy(
            p_code="A", risk_a=5.0, reward_a=-2.0,
            cons_high_raw=148.0, last_close=150.0,
            floor_price=145.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "no reward remaining" in result[1]

    def test_variant_reward_exactly_zero(self, metrics):
        """reward=0 — triggers 'no reward remaining' path."""
        result = _gate_expectancy(
            p_code="A", risk_a=5.0, reward_a=0.0,
            cons_high_raw=150.0, last_close=150.0,
            floor_price=145.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "no reward remaining" in result[1]
