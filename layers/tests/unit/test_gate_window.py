"""Unit tests for _gate_window.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
from ibkr_purity_engine import GateResult, _gate_window


class TestGateWindow:
    """Tests for Gate 4.3 — Execution Window."""

    def test_nominal_pass(self):
        """count=2, limit=5 — within window, gate passes."""
        result = _gate_window(window_count=2, window_limit=5)
        assert result is None

    def test_nominal_fail(self):
        """count=7, limit=5 — exceeds window, gate fires."""
        result = _gate_window(window_count=7, window_limit=5)
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "WINDOW EXPIRED"
        assert result.legacy_diagnostic is not None
        assert "7" in result.legacy_diagnostic

    def test_boundary_at_limit(self):
        """count=5, limit=5 — NOT > limit, gate passes."""
        result = _gate_window(window_count=5, window_limit=5)
        assert result is None

    def test_boundary_one_above_limit(self):
        """count=6, limit=5 — just above limit, gate fires."""
        result = _gate_window(window_count=6, window_limit=5)
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_profile_a_limit_4(self):
        """Profile A limit=4: count=5 exceeds, gate fires."""
        result = _gate_window(window_count=5, window_limit=4)
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert "0-4" in result.legacy_diagnostic

    def test_variant_profile_a_limit_4_at_boundary(self):
        """Profile A limit=4: count=4 is AT limit, gate passes."""
        result = _gate_window(window_count=4, window_limit=4)
        assert result is None

    def test_variant_sentinel_99(self):
        """Sentinel value 99 — exceeds any limit, diagnostic shows 'NONE FOUND (sentinel)'."""
        result = _gate_window(window_count=99, window_limit=5)
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert "NONE FOUND (sentinel)" in result.legacy_diagnostic

    def test_variant_count_zero(self):
        """count=0 — always passes."""
        result = _gate_window(window_count=0, window_limit=5)
        assert result is None
