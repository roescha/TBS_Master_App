"""Unit tests for _gate_midrange.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
from ibkr_purity_engine import GateResult, _gate_midrange


class TestGateMidrange:
    """Tests for Gate 4 — MID-RANGE Hard Wait."""

    def test_nominal_pass(self):
        """adx=28, no squeeze — gate passes."""
        result = _gate_midrange(
            adx_t=28.0, ma_squeeze=False, atr_dist=0.5, ext_limit=1.0
        )
        assert result is None

    def test_nominal_fail_low_adx(self):
        """adx=18 (< 20) — gate fires."""
        result = _gate_midrange(
            adx_t=18.0, ma_squeeze=False, atr_dist=0.5, ext_limit=1.0
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "MID-RANGE (ADX < 20)"
        assert result.legacy_diagnostic is not None
        assert "18.00" in result.legacy_diagnostic

    def test_boundary_adx_exactly_20(self):
        """adx=20.0 — NOT < 20, gate passes (no squeeze)."""
        result = _gate_midrange(
            adx_t=20.0, ma_squeeze=False, atr_dist=0.5, ext_limit=1.0
        )
        assert result is None

    def test_boundary_adx_just_below_20(self):
        """adx=19.99 — below 20, gate fires."""
        result = _gate_midrange(
            adx_t=19.99, ma_squeeze=False, atr_dist=0.5, ext_limit=1.0
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_ma_squeeze(self):
        """adx=25 but ma_squeeze=True — gate fires on squeeze."""
        result = _gate_midrange(
            adx_t=25.0, ma_squeeze=True, atr_dist=0.5, ext_limit=1.0
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert "MA SQUEEZE" in result.legacy_diagnostic

    def test_variant_pe11_extension_warning(self):
        """PE-11: when MID-RANGE fires AND atr_dist > ext_limit, annotation appended."""
        result = _gate_midrange(
            adx_t=15.0, ma_squeeze=False, atr_dist=1.5, ext_limit=1.0
        )
        assert result is not None
        assert "Also EXTENDED" in result.legacy_diagnostic
        assert "1.50 ATR" in result.legacy_diagnostic

    def test_variant_pe11_no_extension_warning_when_within(self):
        """When atr_dist <= ext_limit, no extension warning in diagnostic."""
        result = _gate_midrange(
            adx_t=15.0, ma_squeeze=False, atr_dist=0.8, ext_limit=1.0
        )
        assert result is not None
        assert "Also EXTENDED" not in result.legacy_diagnostic
