"""
GOV-002 Phase 2: Sector Rotation Map -- Unit Tests

Tests the extracted computation helpers directly with pure Python data.
No ib_insync interaction, no mocking, no platform-specific concerns.

  _classify_sector_rs  -- SA-002 dual-mode RS math
  _build_rotation_map  -- Full map construction with graceful degradation
  SECTOR_ETFS          -- Constant validation

Coverage:
  - RS computation (ratio mode + spread mode)
  - Label classification boundaries
  - Graceful degradation (single fail, all fail)
  - Integration (all 11 sectors, map structure)
"""
import sys
import os
import pytest

# Ensure the module is importable from any test runner location
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ibkr_sentinel import _classify_sector_rs, _build_rotation_map, SECTOR_ETFS


# ===========================================================================
# TEST CASES: RS Computation (Ratio Mode)
# ===========================================================================

class TestRatioMode:
    """Tests 1-3: Both SPY and sector positive, SPY >= 0.1%."""

    def test_01_leading(self):
        """SPY +5%, sector +8% -> ratio mode, RS = 1.6 (LEADING)."""
        result = _classify_sector_rs(8.0, 5.0)
        assert result["spread_mode"] is False
        assert abs(result["rs"] - 1.6) < 0.01
        assert result["label"] == "LEADING"

    def test_02_inline_boundary(self):
        """SPY +5%, sector +4% -> ratio mode, RS = 0.8 (INLINE boundary)."""
        result = _classify_sector_rs(4.0, 5.0)
        assert result["spread_mode"] is False
        assert abs(result["rs"] - 0.8) < 0.01
        assert result["label"] == "INLINE"

    def test_03_lagging(self):
        """SPY +5%, sector +2% -> ratio mode, RS = 0.4 (LAGGING)."""
        result = _classify_sector_rs(2.0, 5.0)
        assert result["spread_mode"] is False
        assert abs(result["rs"] - 0.4) < 0.01
        assert result["label"] == "LAGGING"


# ===========================================================================
# TEST CASES: RS Computation (Spread Mode)
# ===========================================================================

class TestSpreadMode:
    """Tests 4-7: Negative benchmark, divergent directions, near-zero SPY."""

    def test_04_spy_negative_sector_less_negative(self):
        """SPY -8%, sector -3% -> spread = +5.0pp (LEADING)."""
        result = _classify_sector_rs(-3.0, -8.0)
        assert result["spread_mode"] is True
        assert abs(result["rs"] - 5.0) < 0.01
        assert result["label"] == "LEADING"

    def test_05_spy_negative_sector_more_negative(self):
        """SPY -8%, sector -12% -> spread = -4.0pp (LAGGING)."""
        result = _classify_sector_rs(-12.0, -8.0)
        assert result["spread_mode"] is True
        assert abs(result["rs"] - (-4.0)) < 0.01
        assert result["label"] == "LAGGING"

    def test_06_spy_negative_sector_positive(self):
        """SPY -2%, sector +3% -> spread = +5.0pp (LEADING)."""
        result = _classify_sector_rs(3.0, -2.0)
        assert result["spread_mode"] is True
        assert abs(result["rs"] - 5.0) < 0.01
        assert result["label"] == "LEADING"

    def test_07_spy_near_zero(self):
        """SPY +0.05% (near-zero < 0.1%), sector +4% -> spread mode, +3.95pp (LEADING)."""
        result = _classify_sector_rs(4.0, 0.05)
        assert result["spread_mode"] is True
        assert abs(result["rs"] - 3.95) < 0.01
        assert result["label"] == "LEADING"


# ===========================================================================
# TEST CASES: Label Classification Boundaries
# ===========================================================================

class TestLabelBoundariesRatioMode:
    """Test 8: Exact boundary values in ratio mode."""

    def test_08a_rs_above_1_2_is_leading(self):
        """RS = 1.21 -> LEADING."""
        result = _classify_sector_rs(6.05, 5.0)
        assert result["label"] == "LEADING"
        assert result["rs"] > 1.2

    def test_08b_rs_exactly_1_2_is_inline(self):
        """RS = 1.20 -> INLINE."""
        result = _classify_sector_rs(6.0, 5.0)
        assert result["label"] == "INLINE"

    def test_08c_rs_exactly_0_8_is_inline(self):
        """RS = 0.80 -> INLINE."""
        result = _classify_sector_rs(4.0, 5.0)
        assert result["label"] == "INLINE"

    def test_08d_rs_below_0_8_is_lagging(self):
        """RS = 0.79 -> LAGGING."""
        result = _classify_sector_rs(3.95, 5.0)
        assert result["label"] == "LAGGING"
        assert result["rs"] < 0.8


class TestLabelBoundariesSpreadMode:
    """Test 9: Exact boundary values in spread mode."""

    def test_09a_spread_above_2_is_leading(self):
        """Spread = +2.01pp -> LEADING (sector -2.99, SPY -5.0)."""
        result = _classify_sector_rs(-2.99, -5.0)
        assert result["spread_mode"] is True
        assert result["rs"] > 2.0
        assert result["label"] == "LEADING"

    def test_09b_spread_exactly_2_is_inline(self):
        """Spread = +2.0pp -> INLINE (sector -3.0, SPY -5.0)."""
        result = _classify_sector_rs(-3.0, -5.0)
        assert result["spread_mode"] is True
        assert abs(result["rs"] - 2.0) < 0.01
        assert result["label"] == "INLINE"

    def test_09c_spread_exactly_neg_2_is_inline(self):
        """Spread = -2.0pp -> INLINE (sector -7.0, SPY -5.0)."""
        result = _classify_sector_rs(-7.0, -5.0)
        assert result["spread_mode"] is True
        assert abs(result["rs"] - (-2.0)) < 0.01
        assert result["label"] == "INLINE"

    def test_09d_spread_below_neg_2_is_lagging(self):
        """Spread = -2.01pp -> LAGGING (sector -7.01, SPY -5.0)."""
        result = _classify_sector_rs(-7.01, -5.0)
        assert result["spread_mode"] is True
        assert result["rs"] < -2.0
        assert result["label"] == "LAGGING"


# ===========================================================================
# TEST CASES: Graceful Degradation (via _build_rotation_map)
# ===========================================================================

class TestGracefulDegradation:
    """Tests 10-12: Fetch failures handled gracefully."""

    def test_10_single_sector_failure(self):
        """XLE UNAVAILABLE: 10 sectors compute normally, XLE marked."""
        sector_data = {}
        for sym, name in SECTOR_ETFS:
            if sym == "XLE":
                sector_data[sym] = {"name": name, "status": "UNAVAILABLE"}
            else:
                sector_data[sym] = {"name": name, "change_20": 3.0}
        result = _build_rotation_map(sector_data, 5.0)
        assert result["XLE"]["status"] == "UNAVAILABLE"
        assert result["XLE"]["name"] == "Energy"
        computed = [s for s in result if "rs" in result[s]]
        assert len(computed) == 10

    def test_11_all_sectors_fail(self):
        """All 11 sectors UNAVAILABLE -> empty dict."""
        sector_data = {sym: {"name": name, "status": "UNAVAILABLE"} for sym, name in SECTOR_ETFS}
        result = _build_rotation_map(sector_data, 5.0)
        assert result == {}

    def test_12_mixed_failures(self):
        """3 sectors UNAVAILABLE, 8 sectors compute normally."""
        fail_syms = {"XLE", "XLRE", "XLB"}
        sector_data = {}
        for sym, name in SECTOR_ETFS:
            if sym in fail_syms:
                sector_data[sym] = {"name": name, "status": "UNAVAILABLE"}
            else:
                sector_data[sym] = {"name": name, "change_20": 4.0}
        result = _build_rotation_map(sector_data, 5.0)
        for sym in fail_syms:
            assert result[sym]["status"] == "UNAVAILABLE"
        computed = [s for s in result if "rs" in result[s]]
        assert len(computed) == 8


# ===========================================================================
# TEST CASES: Integration
# ===========================================================================

class TestIntegration:
    """Tests 13-14: Full rotation map structure and constant validation."""

    def test_13_all_11_sectors_present(self):
        """Full rotation map with all 11 sectors: each has name, change_20, rs, label."""
        sector_data = {sym: {"name": name, "change_20": 3.0} for sym, name in SECTOR_ETFS}
        result = _build_rotation_map(sector_data, 5.0)
        assert len(result) == 11, f"Expected 11 sectors, got {len(result)}. Keys: {list(result.keys())}"
        for sym, name in SECTOR_ETFS:
            assert sym in result, f"{sym} missing from rotation map"
            entry = result[sym]
            assert entry["name"] == name
            assert "change_20" in entry
            assert "rs" in entry
            assert "label" in entry
            assert "spread_mode" in entry

    def test_14_sector_etfs_constant(self):
        """SECTOR_ETFS has exactly 11 entries with expected symbols."""
        assert len(SECTOR_ETFS) == 11
        symbols = [s for s, _ in SECTOR_ETFS]
        expected = {"XLK", "XLV", "XLU", "XLF", "XLE", "XLI", "XLY", "XLP", "XLRE", "XLC", "XLB"}
        assert set(symbols) == expected


# ===========================================================================
# TEST CASES: Negative Benchmark Guard (TC-7 edge case from spec)
# ===========================================================================

class TestNegativeBenchmarkGuard:
    """Verify SA-002 negative benchmark guard produces correct RS."""

    def test_negative_spy_sector_outperforms(self):
        """SPY -10%, sector -4% -> spread = +6.0pp -> LEADING."""
        result = _classify_sector_rs(-4.0, -10.0)
        assert result["spread_mode"] is True
        assert abs(result["rs"] - 6.0) < 0.01
        assert result["label"] == "LEADING"

    def test_all_sectors_lagging(self):
        """All 11 sectors underperform SPY -> all LAGGING."""
        sector_data = {sym: {"name": name, "change_20": -15.0} for sym, name in SECTOR_ETFS}
        result = _build_rotation_map(sector_data, -8.0)
        for sym in result:
            entry = result[sym]
            assert entry["label"] == "LAGGING"
            assert entry["spread_mode"] is True
            assert entry["rs"] < -2.0

    def test_mode_selection_positive_both(self):
        """Both positive with SPY >= 0.1% -> ratio mode."""
        result = _classify_sector_rs(3.0, 5.0)
        assert result["spread_mode"] is False

    def test_mode_selection_negative_spy(self):
        """Negative SPY -> spread mode."""
        result = _classify_sector_rs(3.0, -2.0)
        assert result["spread_mode"] is True

    def test_mode_selection_near_zero_spy(self):
        """SPY near zero (< 0.1%) -> spread mode."""
        result = _classify_sector_rs(3.0, 0.05)
        assert result["spread_mode"] is True

    def test_mode_selection_negative_sector_positive_spy(self):
        """Negative sector with positive SPY -> spread mode (sector_change < 0)."""
        result = _classify_sector_rs(-3.0, 5.0)
        assert result["spread_mode"] is True
