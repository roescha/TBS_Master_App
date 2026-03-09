"""Unit tests for _gate_context_regime (CRG-1 + CRG-2).

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
import pandas as pd
from  ibkr_purity_engine import _gate_context_regime


class TestGateContextRegimeProfileA:
    """Tests for CRG-1 — Profile A (Daily SMA 50/200 Golden Cross)."""

    def test_nominal_pass(self, metrics):
        """SMA_50 > SMA_200, price above SMA_200 — gate passes."""
        df = pd.DataFrame({"SMA_50": [210.0], "SMA_200": [200.0], "close": [220.0]})
        result = _gate_context_regime(p_code="A", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is None
        assert metrics["Context_Golden_Cross"] is True
        assert metrics["Context_Price_vs_SMA200"] == 20.0

    def test_nominal_fail_no_golden_cross(self, metrics):
        """SMA_50 < SMA_200 — golden cross absent, gate fires."""
        df = pd.DataFrame({"SMA_50": [190.0], "SMA_200": [200.0], "close": [195.0]})
        result = _gate_context_regime(p_code="A", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: CONTEXT REGIME FAILED)")
        assert "Daily Golden Cross absent" in result[1]

    def test_nominal_fail_price_below_sma200(self, metrics):
        """SMA_50 > SMA_200 but price below SMA_200 — gate fires."""
        df = pd.DataFrame({"SMA_50": [210.0], "SMA_200": [200.0], "close": [195.0]})
        result = _gate_context_regime(p_code="A", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert "Price below Daily SMA 200" in result[1]

    def test_fail_both_conditions(self, metrics):
        """Both golden cross absent AND price below SMA200."""
        df = pd.DataFrame({"SMA_50": [190.0], "SMA_200": [200.0], "close": [195.0]})
        result = _gate_context_regime(p_code="A", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert "Daily Golden Cross absent" in result[1]
        assert "Price below Daily SMA 200" in result[1]

    def test_boundary_price_exactly_equals_sma200(self, metrics):
        """Price exactly = SMA_200 — close <= SMA_200 triggers."""
        df = pd.DataFrame({"SMA_50": [210.0], "SMA_200": [200.0], "close": [200.0]})
        result = _gate_context_regime(p_code="A", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert "Price below Daily SMA 200" in result[1]

    def test_variant_insufficient_data_none(self, metrics):
        """df_ctx=None — data integrity failure."""
        result = _gate_context_regime(p_code="A", df_ctx=None, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]
        assert metrics["Context_Golden_Cross"] is None

    def test_variant_nan_sma_values(self, metrics):
        """SMA columns present but values are NaN."""
        df = pd.DataFrame({"SMA_50": [float("nan")], "SMA_200": [200.0], "close": [195.0]})
        result = _gate_context_regime(p_code="A", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]

    def test_variant_missing_columns(self, metrics):
        """df_ctx exists but missing SMA columns."""
        df = pd.DataFrame({"close": [195.0]})
        result = _gate_context_regime(p_code="A", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]

    def test_metrics_sma200_price_scaler(self, metrics):
        """Context_SMA200 respects price_scaler (ENG-005 fix)."""
        df = pd.DataFrame({"SMA_50": [21000.0], "SMA_200": [20000.0], "close": [22000.0]})
        result = _gate_context_regime(p_code="A", df_ctx=df, price_scaler=100.0, metrics=metrics)
        assert result is None
        assert metrics["Context_SMA200"] == 200.0


class TestGateContextRegimeProfileB:
    """Tests for CRG-2 — Profile B (Weekly SMA 50 slope)."""

    def test_nominal_pass_rising(self, metrics):
        """Weekly SMA 50 rising — gate passes."""
        df = pd.DataFrame({"SMA_50": [100.0, 105.0], "close": [110.0, 115.0]})
        result = _gate_context_regime(p_code="B", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is None
        assert metrics["Context_Weekly_SMA50_Rising"] is True
        assert metrics["Context_Weekly_SMA50_Slope"] == 5.0

    def test_nominal_fail_declining(self, metrics):
        """Weekly SMA 50 declining — gate fires."""
        df = pd.DataFrame({"SMA_50": [105.0, 100.0], "close": [110.0, 95.0]})
        result = _gate_context_regime(p_code="B", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("REJECT (reason: CONTEXT REGIME FAILED)")
        assert "Weekly SMA 50 declining" in result[1]

    def test_boundary_flat_sma(self, metrics):
        """Weekly SMA 50 flat (equal values) — NOT rising, gate fires."""
        df = pd.DataFrame({"SMA_50": [100.0, 100.0], "close": [110.0, 110.0]})
        result = _gate_context_regime(p_code="B", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_insufficient_data_none(self, metrics):
        """df_ctx=None — data integrity failure."""
        result = _gate_context_regime(p_code="B", df_ctx=None, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]

    def test_variant_single_bar(self, metrics):
        """df_ctx has only 1 bar (need >= 2) — data integrity failure."""
        df = pd.DataFrame({"SMA_50": [100.0], "close": [110.0]})
        result = _gate_context_regime(p_code="B", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]

    def test_variant_nan_sma50(self, metrics):
        """NaN in SMA_50 values — data integrity failure."""
        df = pd.DataFrame({"SMA_50": [100.0, float("nan")], "close": [110.0, 115.0]})
        result = _gate_context_regime(p_code="B", df_ctx=df, price_scaler=1.0, metrics=metrics)
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]
        assert metrics["Context_Weekly_SMA50_Rising"] is None

    def test_metrics_slope_with_scaler(self, metrics):
        """Slope is scaled by price_scaler."""
        df = pd.DataFrame({"SMA_50": [10000.0, 10500.0], "close": [11000.0, 11500.0]})
        result = _gate_context_regime(p_code="B", df_ctx=df, price_scaler=100.0, metrics=metrics)
        assert result is None
        assert metrics["Context_Weekly_SMA50_Slope"] == 5.0  # 500/100


class TestGateContextRegimeProfileC:
    """Tests for Profile C — gate skips entirely."""

    def test_profile_c_skipped(self, metrics):
        """Profile C — no CRG logic, gate passes."""
        result = _gate_context_regime(p_code="C", df_ctx=None, price_scaler=1.0, metrics=metrics)
        assert result is None
