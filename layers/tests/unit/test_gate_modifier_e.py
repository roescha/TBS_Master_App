"""Unit tests for _gate_modifier_e (Gap-Trap).

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
from ibkr_purity_engine import GateResult, _gate_modifier_e


class TestGateModifierE:
    """Tests for Gate 4.2 — Modifier E Gap-Trap."""

    def test_nominal_pass_normal_open(self):
        """Normal open — no gap trap, gate passes."""
        result = _gate_modifier_e(
            last_open=101.0, prev_high=100.0, atr_raw=2.0, last_close=102.0,
        )
        assert result is None

    def test_nominal_fail_gap_trap(self):
        """Gap trap triggered: open > prev_high + 0.5*ATR AND close < open."""
        result = _gate_modifier_e(
            last_open=105.0, prev_high=100.0, atr_raw=2.0, last_close=103.0,
        )
        # 105 > 100 + 1.0 = 101 → True; 103 < 105 → True → trap fires
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "GAP TRAP"
        assert result.legacy_diagnostic is not None

    def test_boundary_open_exactly_at_threshold(self):
        """Open exactly = prev_high + 0.5*ATR — NOT strictly >, gate passes."""
        # threshold = 100 + 0.5*2.0 = 101.0
        result = _gate_modifier_e(
            last_open=101.0, prev_high=100.0, atr_raw=2.0, last_close=100.5,
        )
        assert result is None

    def test_boundary_open_just_above_threshold(self):
        """Open just above threshold, close < open — gate fires."""
        result = _gate_modifier_e(
            last_open=101.01, prev_high=100.0, atr_raw=2.0, last_close=100.5,
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_gap_but_positive_close(self):
        """Gap up but close >= open — no trap (bullish continuation)."""
        result = _gate_modifier_e(
            last_open=105.0, prev_high=100.0, atr_raw=2.0, last_close=106.0,
        )
        assert result is None

    def test_variant_close_equals_open(self):
        """Close == open — NOT close < open, gate passes (doji)."""
        result = _gate_modifier_e(
            last_open=105.0, prev_high=100.0, atr_raw=2.0, last_close=105.0,
        )
        assert result is None
