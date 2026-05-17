"""FPC-001 -- Floor Proximity (Profile C) Banding tests.

Adds a `condition: {label, desc}` sub-object + `thresholds` dictionary to
`floor_analysis.floor_proximity_pct`, with cutoffs aligned to the Profile C
floor proximity gate at gates.py:_gate_floor_proximity_c (gate strict-rejects
when x > 15.0%).

Closes gap log §A2 Gap 3 (floor_proximity_pct lacks band).

Boundary semantics:
    - EDGE_OF_ZONE upper bound INCLUSIVE at 15.0 to match the gate
      (gate uses `> 15.0` strict comparison; x == 15.0 still passes gate)
    - Other internal boundaries use strict `<` per engine RVOL-band convention

Bands (transform.py:_floor_proximity_pct_band):
    < 5.0:        WITHIN_ZONE       (tightly floor-anchored)
    5.0 - 15.0:   EDGE_OF_ZONE      (approaching gate limit; still passes)
    > 15.0 - 30:  BEYOND_ZONE       (gate fails; just-beyond)
    30 - < 100:   FAR_BEYOND_ZONE   (deeply stretched)
    >= 100:       EXTREME_DISTANCE  (extreme; price > 2x floor)

Test classes:
    1. TestFPC001BandLogic           (10) -- All bands + gate-boundary inclusivity
    2. TestFPC001Emission            (5)  -- Sub-object shape via _transform_output
    3. TestFPC001GateAlignment       (3)  -- Boundary semantics match gates.py
    4. TestFPC001VocabularyHygiene   (2)  -- No collision with adjacent engine vocab
"""

import os
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tbs_engine.transform import _transform_output, _floor_proximity_pct_band


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_action_summary():
    return {
        "verdict": "INVALID",
        "reason": {"label": "TEST", "detail": "FPC-001 fixture"},
        "approaching": False,
        "volume": "NEUTRAL",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
        "caution_factors": [],
        "volatility_regime": {"label": "ALIGNED", "interpretation": "STANDARD"},
    }


def _base_flat_metrics_profile_c(floor_prox_pct_value):
    """Minimal flat metrics for a Profile C run with floor_proximity_pct set."""
    return {
        "Profile_Code": "C",
        "Floor_Anchor_Type": "SMA_200",
        "Anchor_Type": "SMA_200",
        "Anchor_Label": "200-SMA (Baseline Floor)",
        "Floor_Anchor_Label": "Long-term secular trend floor",
        "Price_Current": 506.11,
        "Bar_Close": 506.11,
        "Engine_State": "MID-RANGE (ADX <20)",
        "Structural_Floor": 414.22,
        "ATR_Period": 14,
        "ATR": 20.41,
        "Volatility_Regime": "ALIGNED",
        "Floor_Prox_Pct": floor_prox_pct_value,
    }


# ===========================================================================
# 1. TestFPC001BandLogic (10 tests)
# ===========================================================================

class TestFPC001BandLogic:
    """Verify _floor_proximity_pct_band returns correct band across all 5 bands.
    All boundary cases tested explicitly.
    """

    def test_within_zone_below_5_pct(self):
        cond, _ = _floor_proximity_pct_band(0.0)
        assert cond["label"] == "WITHIN_ZONE"
        cond, _ = _floor_proximity_pct_band(4.99)
        assert cond["label"] == "WITHIN_ZONE"

    def test_edge_of_zone_at_exactly_5_pct(self):
        # Lower boundary -- 5.0 falls in EDGE (not WITHIN)
        cond, _ = _floor_proximity_pct_band(5.0)
        assert cond["label"] == "EDGE_OF_ZONE"

    def test_edge_of_zone_in_5_to_15_pct_range(self):
        for v in [5.5, 8.0, 10.0, 12.5, 14.99]:
            cond, _ = _floor_proximity_pct_band(v)
            assert cond["label"] == "EDGE_OF_ZONE", f"{v}% should be EDGE_OF_ZONE"

    def test_edge_of_zone_AT_GATE_BOUNDARY_15_pct(self):
        """CRITICAL: x == 15.0 must be EDGE_OF_ZONE (gate uses `>` strict)."""
        cond, _ = _floor_proximity_pct_band(15.0)
        assert cond["label"] == "EDGE_OF_ZONE", (
            "15.0% must be EDGE_OF_ZONE because the gate at "
            "gates.py:_gate_floor_proximity_c uses `> 15.0` (strict) -- "
            "x == 15.0 still passes the gate"
        )

    def test_beyond_zone_JUST_ABOVE_gate_boundary(self):
        """CRITICAL: x just above 15.0 must be BEYOND_ZONE (gate failure)."""
        cond, _ = _floor_proximity_pct_band(15.01)
        assert cond["label"] == "BEYOND_ZONE"

    def test_beyond_zone_15_to_30_range_includes_LIN_C_live_value(self):
        # LIN Profile C live value from real IBKR run: 22.18%
        cond, _ = _floor_proximity_pct_band(22.18)
        assert cond["label"] == "BEYOND_ZONE", (
            "LIN C live value (22.18%) must be BEYOND_ZONE -- "
            "matches engine's actual gate-fail verdict on that run"
        )
        for v in [16.0, 20.0, 25.0, 29.99]:
            cond, _ = _floor_proximity_pct_band(v)
            assert cond["label"] == "BEYOND_ZONE", f"{v}% should be BEYOND_ZONE"

    def test_far_beyond_zone_at_exactly_30_pct(self):
        cond, _ = _floor_proximity_pct_band(30.0)
        assert cond["label"] == "FAR_BEYOND_ZONE"

    def test_far_beyond_zone_30_to_100_range(self):
        for v in [30.0, 45.0, 75.0, 99.99]:
            cond, _ = _floor_proximity_pct_band(v)
            assert cond["label"] == "FAR_BEYOND_ZONE", f"{v}% should be FAR_BEYOND_ZONE"

    def test_extreme_distance_at_or_above_100_pct(self):
        cond, _ = _floor_proximity_pct_band(100.0)
        assert cond["label"] == "EXTREME_DISTANCE"
        cond, _ = _floor_proximity_pct_band(250.0)
        assert cond["label"] == "EXTREME_DISTANCE"

    def test_none_input_returns_none_condition_with_thresholds(self):
        cond, thr = _floor_proximity_pct_band(None)
        assert cond is None
        # Thresholds dict still returned for schema consistency
        assert isinstance(thr, dict)
        assert thr["edge_of_zone_at_or_below"] == 15.0


# ===========================================================================
# 2. TestFPC001Emission (5 tests)
# ===========================================================================

class TestFPC001Emission:
    """Verify floor_proximity_pct sub-object shape post-transform.
    Schema: {value, unit, condition: {label, desc}, thresholds, desc}
    """

    def _get_fp(self, pct_value):
        flat = _base_flat_metrics_profile_c(pct_value)
        grouped = _transform_output(_base_action_summary(), flat)
        fa = grouped.get("floor_analysis", {})
        return fa.get("floor_proximity_pct")

    def test_emission_includes_value_and_condition_and_thresholds(self):
        fp = self._get_fp(22.18)  # LIN C live value
        assert fp is not None
        assert fp["value"] == 22.18
        assert fp["unit"] == "%"
        assert isinstance(fp["condition"], dict)
        assert fp["condition"]["label"] == "BEYOND_ZONE"
        assert isinstance(fp["thresholds"], dict)
        # All 5 threshold keys present
        for key in ("within_zone_below", "edge_of_zone_at_or_below",
                    "beyond_zone_below", "far_beyond_zone_below",
                    "extreme_distance_at_or_above"):
            assert key in fp["thresholds"]

    def test_emission_within_zone(self):
        fp = self._get_fp(3.5)
        assert fp["condition"]["label"] == "WITHIN_ZONE"
        # Desc surfaces the operator-facing meaning
        assert "floor-anchored" in fp["condition"]["desc"].lower() or "within" in fp["condition"]["desc"].lower()

    def test_emission_extreme_distance(self):
        fp = self._get_fp(150.0)
        assert fp["condition"]["label"] == "EXTREME_DISTANCE"

    def test_emission_none_when_floor_prox_pct_missing(self):
        # No Floor_Prox_Pct flat key -- whole sub-object should be None (legacy behavior)
        flat = _base_flat_metrics_profile_c(None)
        flat.pop("Floor_Prox_Pct", None)  # ensure missing
        grouped = _transform_output(_base_action_summary(), flat)
        fa = grouped.get("floor_analysis", {})
        assert fa.get("floor_proximity_pct") is None

    def test_emission_desc_preserved_from_v1_0(self):
        # The outer-level desc string must remain unchanged for backward compat
        fp = self._get_fp(10.0)
        assert fp["desc"] == "Price distance from structural floor as percentage"


# ===========================================================================
# 3. TestFPC001GateAlignment (3 tests)
# ===========================================================================

class TestFPC001GateAlignment:
    """Verify band cutoffs align with the actual gate in gates.py.

    The gate at gates.py:_gate_floor_proximity_c rejects when:
        floor_prox_pct > 15.0   (strict greater-than)

    This means:
        - x < 15.0  → gate passes → band must be WITHIN_ZONE or EDGE_OF_ZONE
        - x == 15.0 → gate passes → band must be EDGE_OF_ZONE (boundary-inclusive)
        - x > 15.0  → gate fails  → band must be BEYOND_ZONE or worse
    """

    def test_gate_boundary_inclusivity(self):
        """At exactly 15.0, gate passes -> band must reflect 'still inside'."""
        cond, _ = _floor_proximity_pct_band(15.0)
        # Must be a non-rejection band
        assert cond["label"] in ("WITHIN_ZONE", "EDGE_OF_ZONE"), (
            f"At 15.0%, gate passes (gate uses strict `> 15.0`), so band "
            f"must NOT indicate gate failure. Got {cond['label']}"
        )

    def test_gate_failure_just_above_boundary(self):
        """Just above 15.0, gate fails -> band must be BEYOND_ZONE or worse."""
        cond, _ = _floor_proximity_pct_band(15.01)
        assert cond["label"] in ("BEYOND_ZONE", "FAR_BEYOND_ZONE", "EXTREME_DISTANCE"), (
            f"At 15.01%, gate fails (gate uses strict `> 15.0`), so band "
            f"must indicate gate failure. Got {cond['label']}"
        )

    def test_thresholds_dict_documents_gate_boundary(self):
        """The thresholds dict must explicitly expose the 15.0 gate boundary
        with a name signalling its inclusive semantics."""
        _, thr = _floor_proximity_pct_band(0.0)
        assert thr.get("edge_of_zone_at_or_below") == 15.0, (
            "The 15.0 gate boundary must be documented as "
            "'edge_of_zone_at_or_below' to signal boundary-inclusive semantics"
        )


# ===========================================================================
# 4. TestFPC001VocabularyHygiene (2 tests)
# ===========================================================================

class TestFPC001VocabularyHygiene:
    """Verify FPC-001 vocabulary doesn't collide with semantically adjacent
    engine vocabulary that the operator could conflate.
    """

    def test_no_collision_with_extension_analysis_vocab(self):
        """extension_analysis.condition.label uses OVEREXTENDED for ATR-units
        Profile C overextension. FPC-001 (percentage-units) must use distinct
        vocabulary so the operator sees these as complementary perspectives,
        not duplicates."""
        forbidden = {"OVEREXTENDED", "BELOW_FLOOR", "EXHAUSTION", "BLOW_OFF_ZONE"}
        observed = set()
        for v in [0.0, 5.0, 15.0, 22.0, 50.0, 200.0]:
            cond, _ = _floor_proximity_pct_band(v)
            if cond is not None:
                observed.add(cond["label"])
        overlap = observed & forbidden
        assert not overlap, (
            f"FPC-001 vocabulary {observed} collides with extension_analysis "
            f"vocabulary {overlap} -- operator may conflate distinct views"
        )

    def test_no_collision_with_volume_summary_zone_labels(self):
        """volume.summary.label uses 'SUPPORTED ZONE' / 'CONTESTED ZONE' for
        participation-zone semantics. FPC-001 uses _ZONE suffix for
        proximity-zone semantics. They're disambiguated by parent path,
        but ensure FPC-001 doesn't accidentally use those exact strings."""
        forbidden = {"SUPPORTED ZONE", "CONTESTED ZONE", "ACCUMULATION DOMINANT"}
        observed = set()
        for v in [0.0, 5.0, 15.0, 22.0, 50.0, 200.0]:
            cond, _ = _floor_proximity_pct_band(v)
            if cond is not None:
                observed.add(cond["label"])
        overlap = observed & forbidden
        assert not overlap, (
            f"FPC-001 reuses volume.summary participation-zone labels: {overlap}"
        )
