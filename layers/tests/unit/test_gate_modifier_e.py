"""Unit tests for _gate_modifier_e (Gap-Trap).

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
from ibkr_purity_engine import _gate_modifier_e


class TestGateModifierE:
    """Tests for Gate 4.2 — Modifier E Gap-Trap."""

    def test_nominal_pass_normal_open(self, metrics):
        """Normal open — no gap trap, gate passes."""
        result = _gate_modifier_e(
            last_open=101.0, prev_high=100.0, atr_raw=2.0, last_close=102.0,
            metrics=metrics,
        )
        assert result is None

    def test_nominal_fail_gap_trap(self, metrics):
        """Gap trap triggered: open > prev_high + 0.5*ATR AND close < open."""
        result = _gate_modifier_e(
            last_open=105.0, prev_high=100.0, atr_raw=2.0, last_close=103.0,
            metrics=metrics,
        )
        # 105 > 100 + 1.0 = 101 → True; 103 < 105 → True → trap fires
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: GAP TRAP)")

    def test_boundary_open_exactly_at_threshold(self, metrics):
        """Open exactly = prev_high + 0.5*ATR — NOT strictly >, gate passes."""
        # threshold = 100 + 0.5*2.0 = 101.0
        result = _gate_modifier_e(
            last_open=101.0, prev_high=100.0, atr_raw=2.0, last_close=100.5,
            metrics=metrics,
        )
        assert result is None

    def test_boundary_open_just_above_threshold(self, metrics):
        """Open just above threshold, close < open — gate fires."""
        result = _gate_modifier_e(
            last_open=101.01, prev_high=100.0, atr_raw=2.0, last_close=100.5,
            metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_gap_but_positive_close(self, metrics):
        """Gap up but close >= open — no trap (bullish continuation)."""
        result = _gate_modifier_e(
            last_open=105.0, prev_high=100.0, atr_raw=2.0, last_close=106.0,
            metrics=metrics,
        )
        assert result is None

    def test_variant_close_equals_open(self, metrics):
        """Close == open — NOT close < open, gate passes (doji)."""
        result = _gate_modifier_e(
            last_open=105.0, prev_high=100.0, atr_raw=2.0, last_close=105.0,
            metrics=metrics,
        )
        assert result is None
