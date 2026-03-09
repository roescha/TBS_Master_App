"""Unit tests for _gate_floor_failure, _gate_floor_violation, _gate_floor_violation_active.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
from ibkr_purity_engine import (
    _gate_floor_failure,
    _gate_floor_violation,
    _gate_floor_violation_active,
)


# ── _gate_floor_failure ─────────────────────────────────────────────────────

class TestGateFloorFailure:
    """Tests for Gate 1 — Floor Failure."""

    def test_nominal_pass_no_failure(self, metrics):
        """consec_below=0, is_floor_failure=False — gate passes."""
        result = _gate_floor_failure(
            consec_below=0, is_floor_failure=False, p_code="A", metrics=metrics
        )
        assert result is None

    def test_nominal_fail_profile_a(self, metrics):
        """consec_below=9, is_floor_failure=True, Profile A — gate rejects."""
        result = _gate_floor_failure(
            consec_below=9, is_floor_failure=True, p_code="A", metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: FLOOR FAILURE)")
        assert "9 consecutive bars" in result[1]
        assert "evaluated on last completed bar" in result[1]

    def test_boundary_profile_a_at_threshold(self, metrics):
        """consec_below=8, is_floor_failure=True — Profile A threshold is 8, gate fires."""
        result = _gate_floor_failure(
            consec_below=8, is_floor_failure=True, p_code="A", metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "8 consecutive bars" in result[1]

    def test_variant_profile_b_fail(self, metrics):
        """Profile B/C: threshold=4, is_floor_failure=True — gate rejects."""
        result = _gate_floor_failure(
            consec_below=5, is_floor_failure=True, p_code="B", metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: FLOOR FAILURE)")
        # Profile B diagnostic does NOT include "evaluated on last completed bar"
        assert "evaluated on last completed bar" not in result[1]

    def test_variant_profile_c_fail(self, metrics):
        """Profile C with floor failure — gate rejects with Profile B/C diagnostic."""
        result = _gate_floor_failure(
            consec_below=4, is_floor_failure=True, p_code="C", metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "evaluated on last completed bar" not in result[1]

    def test_not_floor_failure_high_consec(self, metrics):
        """consec_below=10 but is_floor_failure=False — gate passes (flag is what matters)."""
        result = _gate_floor_failure(
            consec_below=10, is_floor_failure=False, p_code="A", metrics=metrics
        )
        assert result is None


# ── _gate_floor_violation ────────────────────────────────────────────────────

class TestGateFloorViolation:
    """Tests for Gate 1 — Floor Violation (floor_dist check)."""

    def test_nominal_pass_above_floor(self, metrics):
        """floor_dist=0.3 (above floor) — gate passes."""
        result = _gate_floor_violation(
            floor_dist=0.3, is_violated=False, p_code="B", metrics=metrics
        )
        assert result is None

    def test_nominal_fail_below_floor(self, metrics):
        """floor_dist=-0.6 (below floor, beyond -0.15 threshold) — gate fires."""
        result = _gate_floor_violation(
            floor_dist=-0.6, is_violated=False, p_code="B", metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("WAIT (reason: FLOOR VIOLATION)")
        assert "0.60 ATR below Floor" in result[1]

    def test_boundary_exactly_at_floor(self, metrics):
        """floor_dist=0.0 — not < -0.15, gate passes."""
        result = _gate_floor_violation(
            floor_dist=0.0, is_violated=False, p_code="B", metrics=metrics
        )
        assert result is None

    def test_boundary_at_threshold(self, metrics):
        """floor_dist=-0.15 — not strictly less than -0.15, gate passes."""
        result = _gate_floor_violation(
            floor_dist=-0.15, is_violated=False, p_code="B", metrics=metrics
        )
        assert result is None

    def test_boundary_just_below_threshold(self, metrics):
        """floor_dist=-0.16 — just below -0.15, gate fires."""
        result = _gate_floor_violation(
            floor_dist=-0.16, is_violated=False, p_code="B", metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_profile_a_diagnostic(self, metrics):
        """Profile A — diagnostic includes 'evaluated on last completed bar'."""
        result = _gate_floor_violation(
            floor_dist=-0.5, is_violated=False, p_code="A", metrics=metrics
        )
        assert result is not None
        assert "evaluated on last completed bar" in result[1]

    def test_variant_already_violated(self, metrics):
        """is_violated=True — gate passes even with bad floor_dist (skips this check)."""
        result = _gate_floor_violation(
            floor_dist=-0.6, is_violated=True, p_code="B", metrics=metrics
        )
        # condition is floor_dist < -0.15 AND NOT is_violated
        assert result is None


# ── _gate_floor_violation_active ─────────────────────────────────────────────

class TestGateFloorViolationActive:
    """Tests for Gate 1.5 — Floor Violation Active (no reclaim)."""

    def test_nominal_pass_reclaim(self, metrics):
        """is_reclaim=True — gate passes, reclaim detected."""
        result = _gate_floor_violation_active(
            is_violated=True,
            is_reclaim=True,
            consec_below=2,
            floor_price=100.0,
            last_close=101.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        assert result is None

    def test_nominal_fail_no_reclaim(self, metrics):
        """is_violated=True, is_reclaim=False — gate fires."""
        result = _gate_floor_violation_active(
            is_violated=True,
            is_reclaim=False,
            consec_below=3,
            floor_price=100.0,
            last_close=98.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("WAIT (reason: FLOOR VIOLATION)")
        assert "FLOOR VIOLATION ACTIVE" in result[1]
        assert "3 bar(s) below Floor" in result[1]

    def test_boundary_one_bar_below(self, metrics):
        """consec_below=1 — boundary single bar, gate fires."""
        result = _gate_floor_violation_active(
            is_violated=True,
            is_reclaim=False,
            consec_below=1,
            floor_price=100.0,
            last_close=99.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        assert result is not None
        assert "1 bar(s) below Floor" in result[1]

    def test_variant_not_violated(self, metrics):
        """is_violated=False — gate passes regardless of reclaim."""
        result = _gate_floor_violation_active(
            is_violated=False,
            is_reclaim=False,
            consec_below=5,
            floor_price=100.0,
            last_close=98.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        assert result is None

    def test_diagnostic_contains_close_and_floor(self, metrics):
        """Diagnostic contains actual close and floor values."""
        result = _gate_floor_violation_active(
            is_violated=True,
            is_reclaim=False,
            consec_below=2,
            floor_price=50.0,
            last_close=4800.0,
            price_scaler=100.0,  # LSE pence→GBP
            metrics=metrics,
        )
        assert result is not None
        assert "Close 48.0" in result[1]
        assert "Floor 50.0" in result[1]
