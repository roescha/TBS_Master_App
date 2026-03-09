"""Unit tests for _gate_data_integrity.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
import math
from ibkr_purity_engine import _gate_data_integrity


class TestGateDataIntegrity:
    """Tests for Gate: Data Integrity Check (ATR NaN/0)."""

    def test_nominal_pass_valid_atr(self, metrics):
        """atr_raw=1.5 — valid ATR, gate passes."""
        result = _gate_data_integrity(atr_raw=1.5, metrics=metrics)
        assert result is None

    def test_nominal_fail_nan_atr(self, metrics):
        """atr_raw=NaN — invalid ATR, gate rejects."""
        result = _gate_data_integrity(atr_raw=float("nan"), metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: DATA INTEGRITY)")

    def test_boundary_zero_atr(self, metrics):
        """atr_raw=0 — boundary, gate rejects."""
        result = _gate_data_integrity(atr_raw=0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: DATA INTEGRITY)")

    def test_variant_large_atr(self, metrics):
        """atr_raw=999.9 — large but valid ATR, gate passes."""
        result = _gate_data_integrity(atr_raw=999.9, metrics=metrics)
        assert result is None

    def test_variant_negative_atr(self, metrics):
        """atr_raw=-1.0 — negative ATR, not NaN/0 so gate passes (no negative check)."""
        result = _gate_data_integrity(atr_raw=-1.0, metrics=metrics)
        assert result is None

    def test_variant_none_atr(self, metrics):
        """atr_raw=None — pd.isna(None) is True, gate rejects."""
        result = _gate_data_integrity(atr_raw=None, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
