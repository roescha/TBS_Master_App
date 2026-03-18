"""Unit tests for _gate_data_integrity.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
import math
from ibkr_purity_engine import GateResult, _gate_data_integrity


class TestGateDataIntegrity:
    """Tests for Gate: Data Integrity Check (ATR NaN/0)."""

    def test_nominal_pass_valid_atr(self):
        """atr_raw=1.5 — valid ATR, gate passes."""
        result = _gate_data_integrity(atr_raw=1.5)
        assert result is None

    def test_nominal_fail_nan_atr(self):
        """atr_raw=NaN — invalid ATR, gate rejects."""
        result = _gate_data_integrity(atr_raw=float("nan"))
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "DATA INTEGRITY"
        assert result.legacy_diagnostic is not None

    def test_boundary_zero_atr(self):
        """atr_raw=0 — boundary, gate rejects."""
        result = _gate_data_integrity(atr_raw=0)
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "DATA INTEGRITY"
        assert result.legacy_diagnostic is not None

    def test_variant_large_atr(self):
        """atr_raw=999.9 — large but valid ATR, gate passes."""
        result = _gate_data_integrity(atr_raw=999.9)
        assert result is None

    def test_variant_negative_atr(self):
        """atr_raw=-1.0 — negative ATR, not NaN/0 so gate passes (no negative check)."""
        result = _gate_data_integrity(atr_raw=-1.0)
        assert result is None

    def test_variant_none_atr(self):
        """atr_raw=None — pd.isna(None) is True, gate rejects."""
        result = _gate_data_integrity(atr_raw=None)
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
