"""SBC-001 -- Swing Breakout Confirmation RVOL Banding tests.

Adds a `condition: {label, desc}` sub-object + `thresholds` to
`swing_breakout_confirmation.breakout_rvol`, mirroring the vocabulary and
cutoffs of the existing `volume.rvol.label` band logic (output.py:2225-2237).

Closes gap log §A2 Gap 4 (breakout_rvol lacks band).

Vocabulary (locked from output.py:2225-2237 -- engine-wide RVOL band coherence):
    < 0.5: QUIET
    0.5-0.8: BELOW AVERAGE
    0.8-1.2: NORMAL
    1.2-2.0: ELEVATED
    2.0-3.0: HIGH
    >= 3.0: EXTREME

Test classes:
    1. TestSBC001BandLogic              (8) -- All band cutoffs verified
    2. TestSBC001BreakoutRvolEmission   (5) -- Sub-object shape on actual breakout data
    3. TestSBC001VocabularyConsistency  (2) -- Same labels as volume.rvol
"""

import os
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tbs_engine.transform import _transform_output, _breakout_rvol_band


# ---------------------------------------------------------------------------
# Fixtures (minimal -- only the fields needed to trigger breakout_rvol emission)
# ---------------------------------------------------------------------------

def _base_action_summary():
    return {
        "verdict": "VALID",
        "reason": {"label": "TEST", "detail": "SBC-001 test fixture"},
        "approaching": False,
        "volume": "NEUTRAL",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
        "caution_factors": [],
        "volatility_regime": {"label": "NORMAL", "interpretation": "STANDARD"},
    }


def _base_flat_metrics_with_sbo(sbo_rvol_value):
    """Minimal flat metrics that trigger swing_breakout_confirmation emission.
    Profile A breakout context.
    """
    return {
        "Floor_Anchor_Type": "EMA_21",
        "Profile_Code": "A",
        "Price_Current": 60.0,
        "Bar_Close": 60.0,
        "Engine_State": "TRENDING",
        "Structural_Floor": 57.5,
        "Anchor_Type": "EMA_21",
        "Anchor_Label": "EMA 21 (Structural Floor)",
        "ATR_Period": 14,
        "ATR": 0.5,
        "Volatility_Regime": "NORMAL",
        # SBO-001 minimum requirements for swing_breakout_confirmation emission
        "SBO_Breakout_Bar_Age": 4,
        "SBO_Trending_Reached": True,
        "SBO_Confirmation_Timeout": False,
        "SBO_RVOL": sbo_rvol_value,
    }


# ===========================================================================
# 1. TestSBC001BandLogic (8 tests)
# ===========================================================================

class TestSBC001BandLogic:
    """Verify _breakout_rvol_band returns correct (label, desc, thresholds)
    across all 6 bands, including boundary cases.
    """

    def test_quiet_band_below_0_5(self):
        cond, thr = _breakout_rvol_band(0.3)
        assert cond["label"] == "QUIET"
        assert "well below" in cond["desc"].lower() or "insufficient" in cond["desc"].lower()

    def test_below_average_band_0_5_to_0_8(self):
        # Boundary lower
        cond, _ = _breakout_rvol_band(0.5)
        assert cond["label"] == "BELOW AVERAGE"
        # Mid-range
        cond, _ = _breakout_rvol_band(0.7)
        assert cond["label"] == "BELOW AVERAGE"
        # Boundary upper (0.8 falls in next band)
        cond, _ = _breakout_rvol_band(0.79)
        assert cond["label"] == "BELOW AVERAGE"

    def test_normal_band_0_8_to_1_2(self):
        cond, _ = _breakout_rvol_band(0.8)
        assert cond["label"] == "NORMAL"
        cond, _ = _breakout_rvol_band(1.0)
        assert cond["label"] == "NORMAL"
        cond, _ = _breakout_rvol_band(1.19)
        assert cond["label"] == "NORMAL"

    def test_elevated_band_1_2_to_2_0(self):
        cond, _ = _breakout_rvol_band(1.2)
        assert cond["label"] == "ELEVATED"
        # Real-world value from gap log §A2 NVDA example
        cond, _ = _breakout_rvol_band(1.94)
        assert cond["label"] == "ELEVATED"
        cond, _ = _breakout_rvol_band(1.99)
        assert cond["label"] == "ELEVATED"

    def test_high_band_2_0_to_3_0(self):
        cond, _ = _breakout_rvol_band(2.0)
        assert cond["label"] == "HIGH"
        # Real-world value from gap log §A2 OXY example
        cond, _ = _breakout_rvol_band(2.84)
        assert cond["label"] == "HIGH"
        cond, _ = _breakout_rvol_band(2.99)
        assert cond["label"] == "HIGH"

    def test_extreme_band_at_or_above_3_0(self):
        cond, _ = _breakout_rvol_band(3.0)
        assert cond["label"] == "EXTREME"
        cond, _ = _breakout_rvol_band(5.5)
        assert cond["label"] == "EXTREME"

    def test_none_input_returns_none_label_with_thresholds(self):
        cond, thr = _breakout_rvol_band(None)
        assert cond is None
        # Thresholds dict still returned for schema consistency
        assert isinstance(thr, dict)
        for key in ("quiet_below", "below_average_below", "normal_below",
                    "elevated_below", "high_below", "extreme_at_or_above"):
            assert key in thr

    def test_thresholds_dict_values_match_band_cutoffs(self):
        _, thr = _breakout_rvol_band(1.0)
        assert thr["quiet_below"] == 0.5
        assert thr["below_average_below"] == 0.8
        assert thr["normal_below"] == 1.2
        assert thr["elevated_below"] == 2.0
        assert thr["high_below"] == 3.0
        assert thr["extreme_at_or_above"] == 3.0


# ===========================================================================
# 2. TestSBC001BreakoutRvolEmission (5 tests)
# ===========================================================================

class TestSBC001BreakoutRvolEmission:
    """Verify breakout_rvol sub-object shape post-transform.
    Schema: {value, condition: {label, desc}, thresholds, desc}
    """

    def _get_breakout_rvol(self, sbo_rvol_value):
        flat_in = _base_flat_metrics_with_sbo(sbo_rvol_value)
        grouped = _transform_output(_base_action_summary(), flat_in)
        sbc = grouped.get("swing_breakout_confirmation")
        assert sbc is not None, "swing_breakout_confirmation should emit when SBO_Breakout_Bar_Age is set"
        return sbc.get("breakout_rvol")

    def test_breakout_rvol_has_value_and_condition(self):
        br = self._get_breakout_rvol(1.94)  # NVDA value
        assert br["value"] == 1.94
        assert isinstance(br["condition"], dict)
        assert br["condition"]["label"] == "ELEVATED"
        assert "breakout" in br["condition"]["desc"].lower()

    def test_breakout_rvol_has_thresholds(self):
        br = self._get_breakout_rvol(2.84)  # OXY value
        assert isinstance(br["thresholds"], dict)
        # All 6 threshold keys present
        for key in ("quiet_below", "below_average_below", "normal_below",
                    "elevated_below", "high_below", "extreme_at_or_above"):
            assert key in br["thresholds"]

    def test_breakout_rvol_extreme_band(self):
        br = self._get_breakout_rvol(5.0)
        assert br["value"] == 5.0
        assert br["condition"]["label"] == "EXTREME"

    def test_breakout_rvol_condition_none_when_value_none(self):
        # Edge case: SBO_RVOL None but other SBO fields populated
        flat_in = _base_flat_metrics_with_sbo(None)
        grouped = _transform_output(_base_action_summary(), flat_in)
        sbc = grouped.get("swing_breakout_confirmation")
        br = sbc.get("breakout_rvol")
        assert br["value"] is None
        # condition is None when value is None
        assert br["condition"] is None
        # thresholds dict still present (schema consistency for downstream consumers)
        assert isinstance(br["thresholds"], dict)

    def test_breakout_rvol_quiet_band_warns_low_conviction(self):
        # Operator should see explicit warning for sub-0.5 breakout rvol
        br = self._get_breakout_rvol(0.3)
        assert br["condition"]["label"] == "QUIET"
        # Desc should explicitly flag the institutional commitment problem
        desc = br["condition"]["desc"].lower()
        assert "insufficient" in desc or "weak" in desc or "below" in desc


# ===========================================================================
# 3. TestSBC001VocabularyConsistency (2 tests)
# ===========================================================================

class TestSBC001VocabularyConsistency:
    """Verify the breakout_rvol band labels match the existing volume.rvol
    band labels exactly (engine-wide RVOL vocabulary coherence).
    """

    def test_band_labels_match_volume_rvol_vocabulary(self):
        # The output.py:2225-2237 vocabulary for current-bar volume.rvol:
        #   < 0.5: QUIET
        #   0.5-0.8: BELOW AVERAGE
        #   0.8-1.2: NORMAL
        #   1.2-2.0: ELEVATED
        #   2.0-3.0: HIGH
        #   >= 3.0: EXTREME
        # breakout_rvol must use the IDENTICAL set
        expected_labels = {"QUIET", "BELOW AVERAGE", "NORMAL",
                           "ELEVATED", "HIGH", "EXTREME"}
        observed_labels = set()
        for v in [0.3, 0.6, 1.0, 1.5, 2.5, 4.0]:
            cond, _ = _breakout_rvol_band(v)
            observed_labels.add(cond["label"])
        assert observed_labels == expected_labels, (
            f"Vocabulary mismatch: breakout_rvol uses {observed_labels}, "
            f"expected {expected_labels} (matching volume.rvol)"
        )

    def test_band_cutoffs_match_volume_rvol_cutoffs(self):
        # output.py:2226-2236 cutoffs: 0.5, 0.8, 1.2, 2.0, 3.0
        # Verify boundaries (each lower bound triggers the new band)
        for cutoff, expected_label in [
            (0.5, "BELOW AVERAGE"),
            (0.8, "NORMAL"),
            (1.2, "ELEVATED"),
            (2.0, "HIGH"),
            (3.0, "EXTREME"),
        ]:
            cond, _ = _breakout_rvol_band(cutoff)
            assert cond["label"] == expected_label, (
                f"Cutoff {cutoff} should trigger {expected_label}, "
                f"got {cond['label']} -- vocabulary divergence from volume.rvol"
            )
