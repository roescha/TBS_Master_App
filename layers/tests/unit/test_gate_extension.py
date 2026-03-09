"""Unit tests for _gate_extension.

RFT-001 Phase 2 — Gate Unit Tests.
Updated RFT-003 Phase 3 — _gate_extension now accepts (ctx, atr_dist, ext_limit).
"""

import pytest
from ibkr_purity_engine import _gate_extension
from tests.conftest import build_extension_ctx


class TestGateExtension:
    """Tests for Gate 5 — Extension."""

    def test_nominal_pass(self, extension_base_params):
        """atr_dist=0.5, limit=1.0 — within limit, gate passes."""
        ctx, atr_dist, ext_limit = build_extension_ctx(extension_base_params)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is None

    def test_nominal_fail_extended(self, extension_base_params):
        """atr_dist=1.8, limit=1.0 — extended beyond limit, gate fires."""
        p = extension_base_params
        p["atr_dist"] = 1.8
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is not None
        assert result[0] == "HALT"
        assert result[1].startswith("WAIT (reason: EXTENDED)")
        assert "1.80 ATR" in result[1]

    def test_boundary_exactly_at_limit(self, extension_base_params):
        """atr_dist=1.0, limit=1.0 — NOT > limit, gate passes."""
        p = extension_base_params
        p["atr_dist"] = 1.0
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is None

    def test_boundary_just_above_limit(self, extension_base_params):
        """atr_dist=1.01, limit=1.0 — just above, gate fires."""
        p = extension_base_params
        p["atr_dist"] = 1.01
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_breakout_bar_relaxation(self, extension_base_params):
        """Profile B breakout bar: close > resistance_raw, not trending, _entry_resolving.
        Effective limit relaxes to 1.5 instead of ext_limit."""
        p = extension_base_params
        p["atr_dist"] = 1.3
        p["ext_limit"] = 1.0
        p["p_code"] = "B"
        p["last"] = {"close": 161.0, "open": 159.0, "SMA_200": 130.0}  # close > resistance_raw (160)
        p["is_trending"] = False
        p["is_resolving"] = True  # Must be True so the outer condition doesn't skip for Profile B
        p["_entry_resolving"] = True
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        # 1.3 <= 1.5 (relaxed limit) → passes
        assert result is None

    def test_variant_breakout_bar_still_blocked(self, extension_base_params):
        """Breakout bar but atr_dist exceeds even the relaxed 1.5 limit."""
        p = extension_base_params
        p["atr_dist"] = 1.6
        p["ext_limit"] = 1.0
        p["p_code"] = "B"
        p["last"] = {"close": 161.0, "open": 159.0, "SMA_200": 130.0}
        p["is_trending"] = False
        p["is_resolving"] = True  # Must be True so the outer condition doesn't skip for Profile B
        p["_entry_resolving"] = True
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_profile_a_no_breakout_relaxation(self, extension_base_params):
        """Profile A: breakout bar logic is only for Profile B."""
        p = extension_base_params
        p["atr_dist"] = 1.3
        p["ext_limit"] = 1.0
        p["p_code"] = "A"
        p["last"] = {"close": 161.0, "open": 159.0, "SMA_200": 130.0}
        p["is_trending"] = False
        p["_entry_resolving"] = True
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        # Profile A: _is_breakout_bar = False, ext_limit stays 1.0, 1.3 > 1.0 → HALT
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_profile_b_not_trending_not_resolving_skip(self, extension_base_params):
        """Profile B, not ETF, not trending, not resolving — secondary condition skips gate."""
        p = extension_base_params
        p["atr_dist"] = 1.5
        p["p_code"] = "B"
        p["is_etf"] = False
        p["is_trending"] = False
        p["is_resolving"] = False
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        # The `not (p_code == "B" and not is_etf and not (is_trending or is_resolving))`
        # evaluates: not (True and True and True) = not True = False → skips entire block
        assert result is None

    def test_override_eligible_metrics(self, extension_base_params):
        """When extension fires for Profile B with all override conditions met,
        Trend_Quality_Override is written with Eligible=True."""
        p = extension_base_params
        p["atr_dist"] = 1.5
        p["is_trending"] = True
        p["adx_accel_state"] = "ACCELERATING"
        p["vol_confirm_state"] = "STRONG INSTITUTIONAL"
        p["_resistance_suppressed"] = False
        p["exit_signal"] = False
        # Need the override R:R to be >= 0.5
        # resistance_raw=160, last close=150, tight_stop = structural_floor - 1.0*atr = 140 - 2.0 = 138
        # override reward = 160-150=10, override risk = 150-138=12, rr=0.83 >= 0.5
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is not None
        assert result[0] == "HALT"
        assert p["metrics"].get("Trend_Quality_Override", {}).get("Eligible") is True

    def test_override_ineligible_etf(self, extension_base_params):
        """ETF: override structurally ineligible."""
        p = extension_base_params
        p["atr_dist"] = 1.5
        p["is_etf"] = True
        # When is_etf=True, the outer condition includes the gate
        # But override block checks `if _ceil is not None and not is_etf`
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is not None
        assert result[0] == "HALT"
        override = p["metrics"].get("Trend_Quality_Override", {})
        assert override.get("Eligible") is False

    def test_override_ineligible_profile_a(self, extension_base_params):
        """Profile A: override structurally ineligible."""
        p = extension_base_params
        p["atr_dist"] = 1.8
        p["p_code"] = "A"
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is not None
        assert result[0] == "HALT"
        override = p["metrics"].get("Trend_Quality_Override", {})
        assert override.get("Eligible") is False
        assert "Profile A" in override.get("Reason", "")

    def test_profile_c_floor_proximity_within_extension(self, extension_base_params):
        """Profile C inside extension block: floor_prox_pct > 15% triggers floor proximity reject."""
        p = extension_base_params
        p["atr_dist"] = 1.5
        p["ext_limit"] = 1.0
        p["p_code"] = "C"
        p["is_etf"] = False
        p["is_trending"] = True
        p["is_resolving"] = False
        p["floor_prox_pct"] = 20.0
        p["last"] = {"close": 150.0, "open": 149.0, "SMA_200": 130.0}
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is not None
        assert result[0] == "HALT"
        assert "FLOOR PROXIMITY FAILED" in result[1]
