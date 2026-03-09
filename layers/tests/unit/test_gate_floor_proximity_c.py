"""Unit tests for _gate_floor_proximity_c.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
import math
from ibkr_purity_engine import _gate_floor_proximity_c


class TestGateFloorProximityC:
    """Tests for Gate 5.5 — Profile C Floor Proximity Audit."""

    def test_nominal_pass_profile_b_skipped(self, metrics):
        """Profile B — gate skips entirely, returns None."""
        result = _gate_floor_proximity_c(
            p_code="B",
            last={"SMA_200": 100.0, "close": 115.0},
            floor_prox_pct=20.0,
            metrics=metrics,
        )
        assert result is None

    def test_nominal_pass_profile_a_skipped(self, metrics):
        """Profile A — gate skips entirely."""
        result = _gate_floor_proximity_c(
            p_code="A",
            last={"SMA_200": 100.0, "close": 115.0},
            floor_prox_pct=20.0,
            metrics=metrics,
        )
        assert result is None

    def test_nominal_fail_profile_c_far_from_floor(self, metrics):
        """Profile C, prox=5% — well within threshold, gate passes."""
        result = _gate_floor_proximity_c(
            p_code="C",
            last={"SMA_200": 100.0, "close": 105.0},
            floor_prox_pct=5.0,
            metrics=metrics,
        )
        assert result is None

    def test_nominal_fail_profile_c_too_far(self, metrics):
        """Profile C, prox=20% — exceeds 15%, gate fires."""
        result = _gate_floor_proximity_c(
            p_code="C",
            last={"SMA_200": 100.0, "close": 120.0},
            floor_prox_pct=20.0,
            metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: FLOOR PROXIMITY FAILED)")
        assert "20.00%" in result[1]

    def test_boundary_exactly_at_threshold(self, metrics):
        """prox=15.0% — NOT > 15.0, gate passes."""
        result = _gate_floor_proximity_c(
            p_code="C",
            last={"SMA_200": 100.0, "close": 115.0},
            floor_prox_pct=15.0,
            metrics=metrics,
        )
        assert result is None

    def test_boundary_just_above_threshold(self, metrics):
        """prox=15.01% — just above 15%, gate fires."""
        result = _gate_floor_proximity_c(
            p_code="C",
            last={"SMA_200": 100.0, "close": 115.01},
            floor_prox_pct=15.01,
            metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_invalid_sma200_nan(self, metrics):
        """NaN SMA_200 — data integrity rejection."""
        result = _gate_floor_proximity_c(
            p_code="C",
            last={"SMA_200": float("nan"), "close": 115.0},
            floor_prox_pct=5.0,
            metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]

    def test_variant_invalid_sma200_zero(self, metrics):
        """SMA_200=0 — data integrity rejection."""
        result = _gate_floor_proximity_c(
            p_code="C",
            last={"SMA_200": 0, "close": 115.0},
            floor_prox_pct=5.0,
            metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]
