"""Unit tests for _gate_capital_expectancy (CEG-001).

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
from ibkr_purity_engine import _gate_capital_expectancy


class TestGateCapitalExpectancy:
    """Tests for CEG-001 — Capital Expectancy Gate."""

    def test_nominal_pass_good_cap_rr(self, capital_expectancy_base_params):
        """cap_rr=1.4 — above 1.0 minimum, gate passes."""
        # reward=160-150=10, risk=150-140=10, rr=1.0 ... adjust for 1.4
        p = capital_expectancy_base_params
        p["cons_high_raw"] = 164.0  # reward=14, risk=10, rr=1.4
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_Reward_Risk"] == 1.4

    def test_nominal_fail_low_cap_rr(self, capital_expectancy_base_params):
        """cap_rr < 1.0 — gate fires."""
        p = capital_expectancy_base_params
        p["cons_high_raw"] = 153.0   # reward=3, risk=10, rr=0.3
        result = _gate_capital_expectancy(**p)
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: CAPITAL EXPECTANCY FAILED)")
        assert "0.3" in result[1]

    def test_boundary_cap_rr_exactly_1(self, capital_expectancy_base_params):
        """cap_rr=1.0 — NOT < 1.0, gate passes."""
        p = capital_expectancy_base_params
        p["cons_high_raw"] = 160.0  # reward=10, risk=10, rr=1.0
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_Reward_Risk"] == 1.0

    def test_boundary_cap_rr_just_below_1(self, capital_expectancy_base_params):
        """cap_rr=0.99 — below 1.0, gate fires."""
        p = capital_expectancy_base_params
        p["cons_high_raw"] = 159.9  # reward=9.9, risk=10, rr=0.99
        result = _gate_capital_expectancy(**p)
        assert result is not None
        assert result[0] == "HALT"

    def test_metrics_label_narrow(self, capital_expectancy_base_params):
        """cap_rr between 1.0 and 1.5 — label is NARROW."""
        p = capital_expectancy_base_params
        p["cons_high_raw"] = 162.0  # reward=12, risk=10, rr=1.2
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_RR_Label"] == "NARROW"

    def test_metrics_label_healthy(self, capital_expectancy_base_params):
        """cap_rr >= 1.5 — label is HEALTHY."""
        p = capital_expectancy_base_params
        p["cons_high_raw"] = 165.0  # reward=15, risk=10, rr=1.5
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_RR_Label"] == "HEALTHY"

    def test_variant_profile_b_no_gate(self):
        """Profile B: computes Capital_Reward_Risk for transparency, never rejects."""
        metrics = {}
        result = _gate_capital_expectancy(
            p_code="B", risk_a=1.0,
            cons_high_raw=160.0, last_close=150.0,
            hard_stop_raw=148.0,
            resistance_raw=155.0,  # Profile B uses resistance_raw
            atr_raw=2.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None
        # Profile B: reward = resistance_raw - last_close = 5, risk = 150-148=2, rr=2.5
        assert metrics["Capital_Reward_Risk"] == 2.5
        assert metrics["Capital_RR_Label"] == "HEALTHY"

    def test_variant_profile_b_label_narrow(self):
        """Profile B: narrow R:R computes correctly."""
        metrics = {}
        result = _gate_capital_expectancy(
            p_code="B", risk_a=1.0,
            cons_high_raw=160.0, last_close=150.0,
            hard_stop_raw=146.0,
            resistance_raw=155.0,  # reward=5, risk=4, rr=1.25
            atr_raw=2.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None
        assert metrics["Capital_RR_Label"] == "NARROW"

    def test_variant_reward_lte_zero(self, capital_expectancy_base_params):
        """Reward <= 0: no upside — writes Capital_Reward_Risk=0.0, no rejection."""
        p = capital_expectancy_base_params
        p["cons_high_raw"] = 149.0  # reward = 149-150 = -1 (<=0)
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_Reward_Risk"] == 0.0

    def test_variant_capital_risk_lte_zero(self, capital_expectancy_base_params):
        """capital_risk <= 0 (stop above price) — writes None."""
        p = capital_expectancy_base_params
        p["hard_stop_raw"] = 155.0  # risk = 150-155 = -5
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_Reward_Risk"] is None

    def test_variant_profile_a_small_risk(self):
        """Profile A, risk_a < 20% ATR — PE-CAL-2 path, no gate, but metrics computed."""
        metrics = {}
        result = _gate_capital_expectancy(
            p_code="A", risk_a=0.3,  # < 0.20 * 2.0 = 0.4
            cons_high_raw=160.0, last_close=150.0,
            hard_stop_raw=140.0, resistance_raw=165.0,
            atr_raw=2.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None
        # Should still compute metrics for dashboard visibility
        assert metrics["Capital_Reward_Risk"] == 1.0  # reward=10, risk=10

    def test_variant_profile_c_not_applicable(self):
        """Profile C — writes None, no gate logic."""
        metrics = {}
        result = _gate_capital_expectancy(
            p_code="C", risk_a=1.0,
            cons_high_raw=160.0, last_close=150.0,
            hard_stop_raw=140.0, resistance_raw=165.0,
            atr_raw=2.0, price_scaler=1.0, metrics=metrics,
        )
        assert result is None
        assert metrics["Capital_Reward_Risk"] is None
        assert metrics["Capital_RR_Label"] is None
