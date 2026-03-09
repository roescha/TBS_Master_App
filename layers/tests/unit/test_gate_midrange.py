"""Unit tests for _gate_midrange.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
from ibkr_purity_engine import _gate_midrange


class TestGateMidrange:
    """Tests for Gate 4 — MID-RANGE Hard Wait."""

    def test_nominal_pass(self, metrics):
        """adx=28, no squeeze — gate passes."""
        result = _gate_midrange(
            adx_t=28.0, ma_squeeze=False, atr_dist=0.5, ext_limit=1.0, metrics=metrics
        )
        assert result is None

    def test_nominal_fail_low_adx(self, metrics):
        """adx=18 (< 20) — gate fires."""
        result = _gate_midrange(
            adx_t=18.0, ma_squeeze=False, atr_dist=0.5, ext_limit=1.0, metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("WAIT (reason: MID-RANGE (ADX < 20))")
        assert "18.00" in result[1]

    def test_boundary_adx_exactly_20(self, metrics):
        """adx=20.0 — NOT < 20, gate passes (no squeeze)."""
        result = _gate_midrange(
            adx_t=20.0, ma_squeeze=False, atr_dist=0.5, ext_limit=1.0, metrics=metrics
        )
        assert result is None

    def test_boundary_adx_just_below_20(self, metrics):
        """adx=19.99 — below 20, gate fires."""
        result = _gate_midrange(
            adx_t=19.99, ma_squeeze=False, atr_dist=0.5, ext_limit=1.0, metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_ma_squeeze(self, metrics):
        """adx=25 but ma_squeeze=True — gate fires on squeeze."""
        result = _gate_midrange(
            adx_t=25.0, ma_squeeze=True, atr_dist=0.5, ext_limit=1.0, metrics=metrics
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "MA SQUEEZE" in result[1]

    def test_variant_pe11_extension_warning(self, metrics):
        """PE-11: when MID-RANGE fires AND atr_dist > ext_limit, annotation appended."""
        result = _gate_midrange(
            adx_t=15.0, ma_squeeze=False, atr_dist=1.5, ext_limit=1.0, metrics=metrics
        )
        assert result is not None
        assert "Also EXTENDED" in result[1]
        assert "1.50 ATR" in result[1]

    def test_variant_pe11_no_extension_warning_when_within(self, metrics):
        """When atr_dist <= ext_limit, no extension warning in diagnostic."""
        result = _gate_midrange(
            adx_t=15.0, ma_squeeze=False, atr_dist=0.8, ext_limit=1.0, metrics=metrics
        )
        assert result is not None
        assert "Also EXTENDED" not in result[1]
