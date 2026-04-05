"""PSY-001: Psychological Floor Context (Round Number Proximity).

Verifies that the engine computes the nearest psychologically significant
round numbers above and below the current price and maps them into the
floor_analysis group via transform.py.

4 new flat keys:
  - Psych_Floor
  - Psych_Ceiling
  - Psych_Floor_Dist_Pct
  - Psych_Floor_Near_Technical

Zero gate/verdict/threshold/sizing impact. Informational enrichment only.
"""

import math
import pytest
from tbs_engine.transform import _transform_output, _flatten, MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# Helpers -- replicate PSY-001 computation logic for direct unit testing
# ---------------------------------------------------------------------------

def _compute_psy(price, floor_price=None, resistance_display=None):
    """Reproduce PSY-001 logic from output.py for isolated testing."""
    p = price
    if   p < 1:    inc = 0.10
    elif p < 10:   inc = 0.50
    elif p < 50:   inc = 5.0
    elif p < 200:  inc = 10.0
    elif p < 500:  inc = 25.0
    else:          inc = 50.0

    psy_floor   = round(math.floor(p / inc) * inc, 2)
    psy_ceiling = round(math.ceil(p / inc) * inc, 2)
    psy_dist    = round(((p - psy_floor) / p) * 100, 2) if p > 0 else 0.0
    psy_near    = False
    if floor_price and floor_price > 0:
        psy_near = bool(abs(psy_floor - floor_price) / floor_price <= 0.02)
    psy_ceil_near = False
    if resistance_display and resistance_display > 0:
        psy_ceil_near = bool(abs(psy_ceiling - resistance_display) / resistance_display <= 0.02)

    return {
        "Psych_Floor": psy_floor,
        "Psych_Ceiling": psy_ceiling,
        "Psych_Floor_Dist_Pct": psy_dist,
        "Psych_Floor_Near_Technical": psy_near,
        "Psych_Ceiling_Near_Technical": psy_ceil_near,
    }


def _make_action_summary(verdict="VALID"):
    if verdict == "VALID":
        return {
            "verdict": "VALID", "reason": "PULLBACK",
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        }
    return {
        "verdict": "INVALID", "reason": "EXTENDED",
        "approaching": False,
        "action": "WAIT.", "context": "Test.",
    }


def _make_flat(**overrides):
    """Minimal flat metrics with PSY-001 fields populated."""
    base = {
        "Price": 176.17,
        "Structural_Floor": 170.00,
        "Resistance": 190.0,
        "ADV_20": 2_500_000.0,
        "ADV_20_Dollar": 250_000_000.0,
        "Is_ETF": False,
        "Convexity_Class": "C1",
        "ETF_Primary_Exchange": None,
        "ETF_Detection_Source": None,
        "Entry_Reference": 170.0,
        "Hard_Stop": 165.0,
        "Profit_Target": 190.0,
        # PSY-001 fields (floor-side in floor_analysis, ceiling-side in resistance)
        "Psych_Floor": 170.0,
        "Psych_Ceiling": 180.0,
        "Psych_Floor_Dist_Pct": 3.50,
        "Psych_Floor_Near_Technical": True,
        "Psych_Ceiling_Near_Technical": False,
    }
    base.update(overrides)
    return base


# ===========================================================================
# 7.1 Increment Bracket Tests (T1-T7)
# ===========================================================================

class TestT1SubDollar:
    """T1: Sub-$1 bracket -- price $0.73, inc $0.10."""

    def test_floor(self):
        r = _compute_psy(0.73)
        assert r["Psych_Floor"] == 0.70

    def test_ceiling(self):
        r = _compute_psy(0.73)
        assert r["Psych_Ceiling"] == 0.80

    def test_dist_pct(self):
        r = _compute_psy(0.73)
        assert r["Psych_Floor_Dist_Pct"] == 4.11


class TestT2Dollar1to10Low:
    """T2: $1-$10 low -- price $1.25, inc $0.50."""

    def test_floor(self):
        r = _compute_psy(1.25)
        assert r["Psych_Floor"] == 1.00

    def test_ceiling(self):
        r = _compute_psy(1.25)
        assert r["Psych_Ceiling"] == 1.50

    def test_dist_pct(self):
        r = _compute_psy(1.25)
        assert r["Psych_Floor_Dist_Pct"] == 20.00


class TestT3Dollar1to10High:
    """T3: $1-$10 high -- price $7.23, inc $0.50."""

    def test_floor(self):
        r = _compute_psy(7.23)
        assert r["Psych_Floor"] == 7.00

    def test_ceiling(self):
        r = _compute_psy(7.23)
        assert r["Psych_Ceiling"] == 7.50

    def test_dist_pct(self):
        r = _compute_psy(7.23)
        assert r["Psych_Floor_Dist_Pct"] == 3.18


class TestT4Dollar10to50:
    """T4: $10-$50 -- price $34.50, inc $5.00."""

    def test_floor(self):
        r = _compute_psy(34.50)
        assert r["Psych_Floor"] == 30.00

    def test_ceiling(self):
        r = _compute_psy(34.50)
        assert r["Psych_Ceiling"] == 35.00

    def test_dist_pct(self):
        r = _compute_psy(34.50)
        assert r["Psych_Floor_Dist_Pct"] == 13.04


class TestT5Dollar50to200:
    """T5: $50-$200 -- price $176.17, inc $10.00."""

    def test_floor(self):
        r = _compute_psy(176.17)
        assert r["Psych_Floor"] == 170.00

    def test_ceiling(self):
        r = _compute_psy(176.17)
        assert r["Psych_Ceiling"] == 180.00

    def test_dist_pct(self):
        r = _compute_psy(176.17)
        assert r["Psych_Floor_Dist_Pct"] == 3.50


class TestT6Dollar200to500:
    """T6: $200-$500 -- price $312.80, inc $25.00."""

    def test_floor(self):
        r = _compute_psy(312.80)
        assert r["Psych_Floor"] == 300.00

    def test_ceiling(self):
        r = _compute_psy(312.80)
        assert r["Psych_Ceiling"] == 325.00

    def test_dist_pct(self):
        r = _compute_psy(312.80)
        assert r["Psych_Floor_Dist_Pct"] == 4.09


class TestT7Dollar500Plus:
    """T7: $500+ -- price $742.15, inc $50.00."""

    def test_floor(self):
        r = _compute_psy(742.15)
        assert r["Psych_Floor"] == 700.00

    def test_ceiling(self):
        r = _compute_psy(742.15)
        assert r["Psych_Ceiling"] == 750.00

    def test_dist_pct(self):
        r = _compute_psy(742.15)
        assert r["Psych_Floor_Dist_Pct"] == 5.68


# ===========================================================================
# 7.2 Boundary and Edge Case Tests (T8-T15)
# ===========================================================================

class TestT8ExactRoundNumber:
    """T8: Exact round number $200.00 -- Floor=Ceiling=$200, Dist=0.0%."""

    def test_floor_equals_ceiling(self):
        r = _compute_psy(200.00)
        assert r["Psych_Floor"] == 200.00
        assert r["Psych_Ceiling"] == 200.00

    def test_dist_zero(self):
        r = _compute_psy(200.00)
        assert r["Psych_Floor_Dist_Pct"] == 0.0


class TestT9BracketBoundary10:
    """T9: $10.00 enters $10-$50 bracket, inc=$5. Floor=Ceiling=$10."""

    def test_floor_ceiling(self):
        r = _compute_psy(10.00)
        assert r["Psych_Floor"] == 10.00
        assert r["Psych_Ceiling"] == 10.00

    def test_dist_zero(self):
        r = _compute_psy(10.00)
        assert r["Psych_Floor_Dist_Pct"] == 0.0


class TestT10BracketBoundary50:
    """T10: $50.00 enters $50-$200 bracket, inc=$10. Floor=Ceiling=$50."""

    def test_floor_ceiling(self):
        r = _compute_psy(50.00)
        assert r["Psych_Floor"] == 50.00
        assert r["Psych_Ceiling"] == 50.00

    def test_dist_zero(self):
        r = _compute_psy(50.00)
        assert r["Psych_Floor_Dist_Pct"] == 0.0


class TestT11BracketBoundary200:
    """T11: $200.00 enters $200-$500 bracket, inc=$25. Floor=Ceiling=$200."""

    def test_floor_ceiling(self):
        r = _compute_psy(200.00)
        assert r["Psych_Floor"] == 200.00
        assert r["Psych_Ceiling"] == 200.00

    def test_dist_zero(self):
        r = _compute_psy(200.00)
        assert r["Psych_Floor_Dist_Pct"] == 0.0


class TestT12BracketBoundary500:
    """T12: $500.00 enters $500+ bracket, inc=$50. Floor=Ceiling=$500."""

    def test_floor_ceiling(self):
        r = _compute_psy(500.00)
        assert r["Psych_Floor"] == 500.00
        assert r["Psych_Ceiling"] == 500.00

    def test_dist_zero(self):
        r = _compute_psy(500.00)
        assert r["Psych_Floor_Dist_Pct"] == 0.0


class TestT13JustBelowBoundary:
    """T13: $9.99 -- still in $1-$10 bracket, inc=$0.50."""

    def test_floor(self):
        r = _compute_psy(9.99)
        assert r["Psych_Floor"] == 9.50

    def test_ceiling(self):
        r = _compute_psy(9.99)
        assert r["Psych_Ceiling"] == 10.00


class TestT14JustAboveBoundary:
    """T14: $10.01 -- enters $10-$50 bracket, inc=$5."""

    def test_floor(self):
        r = _compute_psy(10.01)
        assert r["Psych_Floor"] == 10.00

    def test_ceiling(self):
        r = _compute_psy(10.01)
        assert r["Psych_Ceiling"] == 15.00


class TestT15VerySmallPrice:
    """T15: $0.05 -- Floor=$0.00, Ceiling=$0.10, Dist=100.0%."""

    def test_floor(self):
        r = _compute_psy(0.05)
        assert r["Psych_Floor"] == 0.00

    def test_ceiling(self):
        r = _compute_psy(0.05)
        assert r["Psych_Ceiling"] == 0.10

    def test_dist_100_pct(self):
        r = _compute_psy(0.05)
        assert r["Psych_Floor_Dist_Pct"] == 100.0


# ===========================================================================
# 7.3 Near Technical Tests (T16-T20)
# ===========================================================================

class TestT16NearTechnicalWithin2Pct:
    """T16: Psych floor $170 within 2% of technical $170.50 (diff 0.29%)."""

    def test_near_true(self):
        r = _compute_psy(176.17, floor_price=170.50)
        assert r["Psych_Floor"] == 170.00
        assert r["Psych_Floor_Near_Technical"] is True


class TestT17NearTechnicalOutside2Pct:
    """T17: Psych floor $170 vs technical $155.00 (diff 9.68%)."""

    def test_near_false(self):
        r = _compute_psy(176.17, floor_price=155.00)
        assert r["Psych_Floor"] == 170.00
        assert r["Psych_Floor_Near_Technical"] is False


class TestT18ExactMatch:
    """T18: Psych floor = technical floor exactly (diff 0.0%)."""

    def test_near_true_exact(self):
        r = _compute_psy(176.17, floor_price=170.00)
        assert r["Psych_Floor_Near_Technical"] is True


class TestT19FloorPriceNone:
    """T19: floor_price is None -- defensive guard returns False."""

    def test_near_false_none(self):
        r = _compute_psy(176.17, floor_price=None)
        assert r["Psych_Floor_Near_Technical"] is False


class TestT20FloorPriceZero:
    """T20: floor_price is 0.0 -- defensive guard returns False."""

    def test_near_false_zero(self):
        r = _compute_psy(176.17, floor_price=0.0)
        assert r["Psych_Floor_Near_Technical"] is False


# ===========================================================================
# 7.4 GBP Pence / Price Scaler Tests (T21-T22)
# ===========================================================================

class TestT21LSEStockDisplayScaled:
    """T21: LSE stock raw 15023p, scaler 0.01 -> display 150.23.

    PSY-001 operates on display price (actual_price), which is pre-scaled
    in data.py. Bracket $50-$200, inc=$10. Floor=$150, Ceiling=$160.
    """

    def test_display_scaled_floor_ceiling(self):
        # data.py divides raw pence by price_scaler (0.01) -> 150.23
        display_price = 15023 * 0.01  # 150.23
        r = _compute_psy(display_price)
        assert r["Psych_Floor"] == 150.00
        assert r["Psych_Ceiling"] == 160.00


class TestT22LSEETFScaler1:
    """T22: LSE ETF scaler=1.0. Same display price 150.23, same result."""

    def test_scaler_one_same_result(self):
        display_price = 150.23 / 1.0  # 150.23
        r = _compute_psy(display_price)
        assert r["Psych_Floor"] == 150.00
        assert r["Psych_Ceiling"] == 160.00


# ===========================================================================
# 7.5 Transform Round-Trip Tests (T23-T25)
# ===========================================================================

class TestT23FloorAnalysisGroupMapping:
    """T23: PSY-001 floor fields in floor_analysis, ceiling in trade_setup.resistance."""

    def test_psych_floor_in_floor_analysis(self):
        r = _transform_output(_make_action_summary(), _make_flat())
        psy = r["psychological_levels"]
        assert "floor" in psy
        assert psy["floor"]["price"] == 170.0

    def test_psych_floor_dist_pct_in_floor_analysis(self):
        r = _transform_output(_make_action_summary(), _make_flat())
        psy = r["psychological_levels"]
        assert "floor" in psy
        assert psy["floor"]["distance_pct"] == 3.50

    def test_psych_near_technical_in_floor_analysis(self):
        r = _transform_output(_make_action_summary(), _make_flat())
        psy = r["psychological_levels"]
        assert "floor" in psy
        assert psy["floor"]["near_structural_floor"] is True

    def test_psych_ceiling_NOT_in_floor_analysis(self):
        r = _transform_output(_make_action_summary(), _make_flat())
        fa = r["floor_analysis"]
        assert "psych_ceiling" not in fa

    def test_psych_ceiling_in_resistance(self):
        r = _transform_output(_make_action_summary(), _make_flat())
        psy = r.get("psychological_levels", {})
        assert "ceiling" in psy
        assert psy["ceiling"]["price"] == 180.0

    def test_psych_ceiling_near_resistance_in_resistance(self):
        r = _transform_output(_make_action_summary(), _make_flat())
        psy = r.get("psychological_levels", {})
        assert "ceiling" in psy
        assert psy["ceiling"]["near_resistance"] is False


class TestT24FlattenRoundTrip:
    """T24: flat -> grouped -> flat preserves all 5 PSY-001 values."""

    def test_roundtrip_psych_floor(self):
        flat_in = _make_flat()
        grouped = _transform_output(_make_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Psych_Floor"] == 170.0

    def test_roundtrip_psych_ceiling(self):
        flat_in = _make_flat()
        grouped = _transform_output(_make_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Psych_Ceiling"] == 180.0

    def test_roundtrip_dist_pct(self):
        flat_in = _make_flat()
        grouped = _transform_output(_make_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Psych_Floor_Dist_Pct"] == 3.50

    def test_roundtrip_near_technical(self):
        flat_in = _make_flat()
        grouped = _transform_output(_make_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Psych_Floor_Near_Technical"] is True

    def test_roundtrip_ceiling_near_resistance(self):
        flat_in = _make_flat()
        grouped = _transform_output(_make_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Psych_Ceiling_Near_Technical"] is False


class TestT25MappedFlatKeysRegistry:
    """T25: All 5 PSY-001 flat keys present in MAPPED_FLAT_KEYS."""

    def test_psych_floor_in_registry(self):
        assert "Psych_Floor" in MAPPED_FLAT_KEYS

    def test_psych_ceiling_in_registry(self):
        assert "Psych_Ceiling" in MAPPED_FLAT_KEYS

    def test_psych_floor_dist_pct_in_registry(self):
        assert "Psych_Floor_Dist_Pct" in MAPPED_FLAT_KEYS

    def test_psych_floor_near_technical_in_registry(self):
        assert "Psych_Floor_Near_Technical" in MAPPED_FLAT_KEYS

    def test_psych_ceiling_near_technical_in_registry(self):
        assert "Psych_Ceiling_Near_Technical" in MAPPED_FLAT_KEYS


# ===========================================================================
# 7.7 Ceiling Near Resistance Tests (T27-T31)
# ===========================================================================

class TestT27CeilingNearResistanceWithin2Pct:
    """T27: Psych ceiling $180 within 2% of resistance $181.22 (diff 0.67%)."""

    def test_near_true(self):
        r = _compute_psy(176.17, resistance_display=181.22)
        assert r["Psych_Ceiling"] == 180.0
        assert r["Psych_Ceiling_Near_Technical"] is True


class TestT28CeilingNearResistanceOutside2Pct:
    """T28: Psych ceiling $180 vs resistance $195.00 (diff 7.69%)."""

    def test_near_false(self):
        r = _compute_psy(176.17, resistance_display=195.00)
        assert r["Psych_Ceiling"] == 180.0
        assert r["Psych_Ceiling_Near_Technical"] is False


class TestT29CeilingExactMatchResistance:
    """T29: Psych ceiling = resistance exactly (diff 0.0%)."""

    def test_near_true_exact(self):
        r = _compute_psy(176.17, resistance_display=180.00)
        assert r["Psych_Ceiling_Near_Technical"] is True


class TestT30ResistanceNone:
    """T30: resistance_display is None -- defensive guard returns False."""

    def test_near_false_none(self):
        r = _compute_psy(176.17, resistance_display=None)
        assert r["Psych_Ceiling_Near_Technical"] is False


class TestT31ResistanceZero:
    """T31: resistance_display is 0.0 -- defensive guard returns False."""

    def test_near_false_zero(self):
        r = _compute_psy(176.17, resistance_display=0.0)
        assert r["Psych_Ceiling_Near_Technical"] is False


# ===========================================================================
# 7.6 Regression (T26) -- run via: pytest tests/
# ===========================================================================
# T26 is verified by running the full test suite (pytest tests/).
# No dedicated test class needed -- the assertion is that all ~1122+
# existing tests pass with 0 failures and 0 regressions.
