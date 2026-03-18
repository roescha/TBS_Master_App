"""Unit tests for _gate_liquidity.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
import math
from ibkr_purity_engine import GateResult, _gate_liquidity


class TestGateLiquidity:
    """Tests for Gate 0 — Liquidity Check."""

    def test_nominal_pass_equity(self):
        """adv=15M (equity) — above $5M threshold, gate passes."""
        result = _gate_liquidity(
            adv_20=15_000_000, is_etf=False, _is_lse_etf=False
        )
        assert result is None

    def test_nominal_fail_equity(self):
        """adv=0.5M (equity) — below $5M threshold, gate fires."""
        result = _gate_liquidity(
            adv_20=500_000, is_etf=False, _is_lse_etf=False
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "LIQUIDITY FAILED"
        assert result.legacy_diagnostic is not None
        assert "EQUITY" in result.legacy_diagnostic

    def test_boundary_exactly_at_equity_threshold(self):
        """adv=5M (equity) — NOT < 5M, gate passes."""
        result = _gate_liquidity(
            adv_20=5_000_000, is_etf=False, _is_lse_etf=False
        )
        assert result is None

    def test_boundary_just_below_equity_threshold(self):
        """adv=4,999,999 — just below $5M, gate fires."""
        result = _gate_liquidity(
            adv_20=4_999_999, is_etf=False, _is_lse_etf=False
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_etf_threshold(self):
        """ETF threshold is $50M, not $5M."""
        # 15M passes equity but fails ETF
        result = _gate_liquidity(
            adv_20=15_000_000, is_etf=True, _is_lse_etf=False
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert "ETF" in result.legacy_diagnostic

    def test_variant_etf_pass(self):
        """ETF with adv=60M — above $50M threshold, passes."""
        result = _gate_liquidity(
            adv_20=60_000_000, is_etf=True, _is_lse_etf=False
        )
        assert result is None

    def test_variant_etf_boundary(self):
        """ETF: adv=50M — NOT < 50M, gate passes."""
        result = _gate_liquidity(
            adv_20=50_000_000, is_etf=True, _is_lse_etf=False
        )
        assert result is None

    def test_variant_lse_etf_threshold(self):
        """LSE ETF: threshold is $5M (not $50M like regular ETFs)."""
        result = _gate_liquidity(
            adv_20=6_000_000, is_etf=True, _is_lse_etf=True
        )
        assert result is None

    def test_variant_lse_etf_fail(self):
        """LSE ETF: adv=3M — below $5M threshold, gate fires."""
        result = _gate_liquidity(
            adv_20=3_000_000, is_etf=True, _is_lse_etf=True
        )
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"

    def test_variant_nan_adv(self):
        """adv=NaN — pd.isna check is True, condition `not pd.isna(adv_20)` fails, gate passes."""
        result = _gate_liquidity(
            adv_20=float("nan"), is_etf=False, _is_lse_etf=False
        )
        # The gate only rejects when `not pd.isna(adv_20) and adv_20 < limit`
        # If NaN, the first condition is False, so it passes
        assert result is None
