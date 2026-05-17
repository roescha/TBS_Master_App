"""HFI-001-B -- Higher Frame Interpretation: higher_frame.sma200.price_distance
banding tests across all three profiles.

Adds pct, unit_pct, condition {label, desc}, and thresholds to
higher_frame.sma200.price_distance with three timeframe-aware vocabularies:
    - Profile A daily   -> CYCLICAL_*   (new, 6 tokens)
    - Profile B weekly  -> SECULAR_*    (reused from _macro_secular_elevation)
    - Profile C monthly -> DECADAL_*    (new, 6 tokens)

Cutoffs are identical across all three timeframes per brief D5:
    0 / 25 / 75 / 150 / 300 %

Closes gap log §A2 Gap 1.

PCM-001 live-validation caveat: Profile C higher_frame is typically null
due to the monthly SMA 200 history requirement (~17 years). Tests use
synthetic flat-key fixtures to exercise the DECADAL_* path; live
validation requires a megacap with 17+ years of monthly bars.

Test classes (per brief §4):
    1. TestHFI001BCyclicalBandLogic     (7) -- All 6 CYCLICAL bands + boundaries
    2. TestHFI001BSecularReuse          (3) -- Profile B weekly emits SECULAR_*
                                                identically to macro_frame.sma200
    3. TestHFI001BDecadalBandLogic      (7) -- All 6 DECADAL bands + boundaries
    4. TestHFI001BEmissionShape         (5) -- All 3 profiles emit full shape
    5. TestHFI001BVocabularyHygiene     (4) -- 3 vocab sets disjoint + no
                                                collision with adjacent vocab
    6. TestHFI001BPercentageMath        (3) -- pct = dollars/sma200 * 100
    7. TestHFI001BLiveDataAnchors       (6) -- Brief §4 live anchors verified
"""

import os
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tbs_engine.transform import (
    _transform_output,
    _daily_cyclical_elevation,
    _monthly_decadal_elevation,
    _macro_secular_elevation,
    _HFI_DAILY_CYCLICAL_THRESHOLDS,
    _HFI_MONTHLY_DECADAL_THRESHOLDS,
    _MACRO_ELEVATION_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_action_summary():
    return {
        "verdict": "INVALID",
        "reason": {"label": "TEST", "detail": "HFI-001-B fixture"},
        "approaching": False,
        "volume": "NEUTRAL",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
        "caution_factors": [],
        "volatility_regime": {"label": "ALIGNED", "interpretation": "STANDARD"},
    }


def _flat_metrics_for_higher_frame(profile_letter, price_vs_sma200, sma200_price):
    """Minimal flat metrics that drive _transform_output to produce a
    populated higher_frame.sma200.price_distance sub-object for the
    requested profile.

    The timeframe detection at transform.py:1250-1294 keys off
    Context_{Daily,Weekly,Monthly}_SMA50 presence -- we set the right
    one per profile.
    """
    common = {
        "Engine_State": "MID-RANGE (ADX <20)",
        "Engine_State_Desc": "Test",
        "Anchor_Type": "SMA_200",
        "Anchor_Label": "200-SMA",
        "Floor_Anchor_Type": "SMA_200",
        "Floor_Anchor_Label": "Long-term floor",
        "Price_Current": 100.0,
        "Bar_Close": 100.0,
        "Structural_Floor": 90.0,
        "ATR": 2.0,
        "ATR_Period": 14,
        "Volatility_Regime": "ALIGNED",
    }
    if profile_letter == "A":
        common["Data_Basis"] = "SWING analysis."
        common["Context_Daily_SMA50"] = 95.0   # trigger DAILY timeframe branch
        common["Context_Price_vs_SMA200"] = price_vs_sma200
        common["Context_SMA200"] = sma200_price
    elif profile_letter == "B":
        common["Data_Basis"] = "TREND analysis."
        common["Context_Weekly_SMA50"] = 95.0  # trigger WEEKLY timeframe branch
        common["Context_Weekly_Price_vs_SMA200"] = price_vs_sma200
        common["Context_Weekly_SMA200"] = sma200_price
    elif profile_letter == "C":
        common["Data_Basis"] = "WEALTH analysis."
        common["Context_Monthly_SMA50"] = 95.0  # trigger MONTHLY timeframe branch
        common["Context_Monthly_Price_vs_SMA200"] = price_vs_sma200
        common["Context_Monthly_SMA200"] = sma200_price
    return common


def _get_higher_frame_price_distance(profile_letter, price_vs_sma200, sma200_price):
    flat = _flat_metrics_for_higher_frame(profile_letter, price_vs_sma200, sma200_price)
    grouped = _transform_output(_base_action_summary(), flat)
    fa = grouped.get("floor_analysis", {})
    hf = fa.get("higher_frame", {})
    sma200 = hf.get("sma200", {}) if hf else {}
    return sma200.get("price_distance") if sma200 else None


# ===========================================================================
# 1. TestHFI001BCyclicalBandLogic (7 tests)
# ===========================================================================

class TestHFI001BCyclicalBandLogic:
    """Verify _daily_cyclical_elevation across all 6 CYCLICAL bands."""

    def test_below_cyclical_mean_negative_pct(self):
        for v in [-50.0, -10.0, -0.01]:
            cond, _ = _daily_cyclical_elevation(v)
            assert cond["label"] == "BELOW_CYCLICAL_MEAN", f"{v}% should be BELOW_CYCLICAL_MEAN"

    def test_early_cyclical_at_exactly_zero_and_in_range(self):
        # 0% is the lower boundary of EARLY (BELOW ends strict-below 0)
        cond, _ = _daily_cyclical_elevation(0.0)
        assert cond["label"] == "EARLY_CYCLICAL_ELEVATION"
        for v in [9.2, 21.16, 24.99]:  # 9.2 = LIN A anchor, 21.16 = NVDA A live
            cond, _ = _daily_cyclical_elevation(v)
            assert cond["label"] == "EARLY_CYCLICAL_ELEVATION", f"{v}% should be EARLY_CYCLICAL_ELEVATION"

    def test_established_cyclical_at_exactly_25(self):
        cond, _ = _daily_cyclical_elevation(25.0)
        assert cond["label"] == "ESTABLISHED_CYCLICAL_ELEVATION"
        # ENPH A live anchor from brief §4: 45.1% -> ESTABLISHED
        cond, _ = _daily_cyclical_elevation(45.1)
        assert cond["label"] == "ESTABLISHED_CYCLICAL_ELEVATION"
        cond, _ = _daily_cyclical_elevation(74.99)
        assert cond["label"] == "ESTABLISHED_CYCLICAL_ELEVATION"

    def test_mature_cyclical_at_exactly_75(self):
        cond, _ = _daily_cyclical_elevation(75.0)
        assert cond["label"] == "MATURE_CYCLICAL_ELEVATION"
        cond, _ = _daily_cyclical_elevation(149.99)
        assert cond["label"] == "MATURE_CYCLICAL_ELEVATION"

    def test_late_cyclical_at_exactly_150(self):
        cond, _ = _daily_cyclical_elevation(150.0)
        assert cond["label"] == "LATE_CYCLICAL_ELEVATION"
        cond, _ = _daily_cyclical_elevation(299.99)
        assert cond["label"] == "LATE_CYCLICAL_ELEVATION"

    def test_parabolic_cyclical_at_or_above_300(self):
        cond, _ = _daily_cyclical_elevation(300.0)
        assert cond["label"] == "PARABOLIC_CYCLICAL_ELEVATION"
        cond, _ = _daily_cyclical_elevation(1000.0)
        assert cond["label"] == "PARABOLIC_CYCLICAL_ELEVATION"

    def test_none_input_returns_none_condition_with_thresholds(self):
        cond, thr = _daily_cyclical_elevation(None)
        assert cond is None
        assert isinstance(thr, dict)
        assert thr["below_cyclical_at"] == 0
        assert thr["late_at"] == 300


# ===========================================================================
# 2. TestHFI001BSecularReuse (3 tests)
# ===========================================================================

class TestHFI001BSecularReuse:
    """Verify Profile B weekly higher_frame REUSES _macro_secular_elevation
    exactly per D3 -- this is the charter-compliance check that vocabulary
    does NOT fragment across the macro_frame vs higher_frame surfaces when
    the underlying timeframe is identical.
    """

    def test_profile_b_weekly_emits_secular_labels(self):
        # Sweep across all 6 SECULAR bands on Profile B's higher_frame surface
        sample_points = [
            (-10.0, "BELOW_SECULAR_MEAN"),
            (10.0,  "EARLY_SECULAR_ELEVATION"),
            (50.0,  "ESTABLISHED_SECULAR_ELEVATION"),
            (100.0, "MATURE_SECULAR_ELEVATION"),
            (200.0, "LATE_SECULAR_ELEVATION"),
            (400.0, "PARABOLIC_SECULAR_ELEVATION"),
        ]
        for pct, expected_label in sample_points:
            # Use sma200=100 so dollars value == pct
            pd = _get_higher_frame_price_distance("B", pct, 100.0)
            assert pd["condition"]["label"] == expected_label, (
                f"Profile B weekly at {pct}% should emit {expected_label}, "
                f"got {pd['condition']['label']!r}"
            )

    def test_profile_b_weekly_thresholds_identical_to_macro(self):
        """Profile B weekly higher_frame.sma200 thresholds dict MUST be the
        same _MACRO_ELEVATION_THRESHOLDS object as macro_frame.sma200. This
        is the strongest possible guarantee against D3 fragmentation: a future
        maintainer who introduces a copy will trip this identity check.
        """
        pd = _get_higher_frame_price_distance("B", 14.78, 100.0)  # EOG B anchor
        assert pd["thresholds"] is _MACRO_ELEVATION_THRESHOLDS

    def test_profile_b_weekly_outer_desc_says_secular_trend_reference(self):
        pd = _get_higher_frame_price_distance("B", 14.78, 100.0)
        assert pd["desc"] == (
            "WEEKLY close distance from WEEKLY SMA 200 -- secular trend reference"
        )


# ===========================================================================
# 3. TestHFI001BDecadalBandLogic (7 tests)
# ===========================================================================

class TestHFI001BDecadalBandLogic:
    """Verify _monthly_decadal_elevation across all 6 DECADAL bands. Pure
    helper tests; emission-path tests are in TestHFI001BEmissionShape since
    live Profile C DECADAL_* data is gated by the PCM-001 history
    requirement (see brief §4 live-validation note).
    """

    def test_below_decadal_mean_negative_pct(self):
        for v in [-100.0, -25.0, -0.01]:
            cond, _ = _monthly_decadal_elevation(v)
            assert cond["label"] == "BELOW_DECADAL_MEAN", f"{v}% should be BELOW_DECADAL_MEAN"

    def test_early_decadal_at_zero_and_in_range(self):
        cond, _ = _monthly_decadal_elevation(0.0)
        assert cond["label"] == "EARLY_DECADAL_ELEVATION"
        for v in [10.0, 24.99]:
            cond, _ = _monthly_decadal_elevation(v)
            assert cond["label"] == "EARLY_DECADAL_ELEVATION"

    def test_established_decadal_at_exactly_25(self):
        cond, _ = _monthly_decadal_elevation(25.0)
        assert cond["label"] == "ESTABLISHED_DECADAL_ELEVATION"
        cond, _ = _monthly_decadal_elevation(74.99)
        assert cond["label"] == "ESTABLISHED_DECADAL_ELEVATION"

    def test_mature_decadal_at_exactly_75(self):
        cond, _ = _monthly_decadal_elevation(75.0)
        assert cond["label"] == "MATURE_DECADAL_ELEVATION"
        cond, _ = _monthly_decadal_elevation(149.99)
        assert cond["label"] == "MATURE_DECADAL_ELEVATION"

    def test_late_decadal_at_exactly_150(self):
        cond, _ = _monthly_decadal_elevation(150.0)
        assert cond["label"] == "LATE_DECADAL_ELEVATION"
        cond, _ = _monthly_decadal_elevation(299.99)
        assert cond["label"] == "LATE_DECADAL_ELEVATION"

    def test_parabolic_decadal_at_or_above_300(self):
        cond, _ = _monthly_decadal_elevation(300.0)
        assert cond["label"] == "PARABOLIC_DECADAL_ELEVATION"
        cond, _ = _monthly_decadal_elevation(500.0)
        assert cond["label"] == "PARABOLIC_DECADAL_ELEVATION"

    def test_none_input_returns_none_condition_with_thresholds(self):
        cond, thr = _monthly_decadal_elevation(None)
        assert cond is None
        assert isinstance(thr, dict)
        assert thr["below_decadal_at"] == 0
        assert thr["late_at"] == 300


# ===========================================================================
# 4. TestHFI001BEmissionShape (5 tests)
# ===========================================================================

class TestHFI001BEmissionShape:
    """Verify higher_frame.sma200.price_distance sub-object shape across all
    three profiles. Schema: {value, unit, pct, unit_pct, condition, thresholds, desc}
    """

    def test_profile_a_daily_full_shape(self):
        # NVDA A live anchor: value 39.35, sma200 185.97 -> pct ~21.16 -> EARLY_CYCLICAL
        pd = _get_higher_frame_price_distance("A", 39.35, 185.97)
        assert pd is not None
        # All 7 keys present
        for key in ("value", "unit", "pct", "unit_pct", "condition", "thresholds", "desc"):
            assert key in pd, f"Missing key: {key}"
        assert pd["value"] == 39.35
        assert pd["unit"] == "dollars"
        assert pd["unit_pct"] == "%"
        assert pd["pct"] == 21.16
        assert pd["condition"]["label"] == "EARLY_CYCLICAL_ELEVATION"
        assert pd["desc"] == (
            "DAILY close distance from DAILY SMA 200 -- intermediate cyclical reference"
        )
        # All 5 threshold keys
        for k in ("below_cyclical_at", "early_at", "established_at", "mature_at", "late_at"):
            assert k in pd["thresholds"]

    def test_profile_b_weekly_full_shape(self):
        # PLTR B live anchor: value 70.46, sma200 63.53 -> pct ~110.91 -> MATURE_SECULAR
        pd = _get_higher_frame_price_distance("B", 70.46, 63.53)
        assert pd is not None
        for key in ("value", "unit", "pct", "unit_pct", "condition", "thresholds", "desc"):
            assert key in pd
        assert pd["pct"] == 110.91
        assert pd["condition"]["label"] == "MATURE_SECULAR_ELEVATION"
        assert "secular trend reference" in pd["desc"]
        # SECULAR thresholds dict
        for k in ("below_secular_at", "early_at", "established_at", "mature_at", "late_at"):
            assert k in pd["thresholds"]

    def test_profile_c_monthly_full_shape(self):
        # Synthetic Profile C data (PCM-001 gates most real tickers).
        # value 75, sma200 50 -> pct 150% -> LATE_DECADAL
        pd = _get_higher_frame_price_distance("C", 75.0, 50.0)
        assert pd is not None
        for key in ("value", "unit", "pct", "unit_pct", "condition", "thresholds", "desc"):
            assert key in pd
        assert pd["pct"] == 150.0
        assert pd["condition"]["label"] == "LATE_DECADAL_ELEVATION"
        assert "multi-decade structural reference" in pd["desc"]
        for k in ("below_decadal_at", "early_at", "established_at", "mature_at", "late_at"):
            assert k in pd["thresholds"]

    def test_price_distance_none_when_dollars_missing(self):
        # If price_vs_sma200 flat key is absent, the whole price_distance
        # sub-object should be None (preserves WKC-001 v1.1 null-handling).
        flat = _flat_metrics_for_higher_frame("A", None, 185.97)
        # Remove the dollar key to force null
        flat.pop("Context_Price_vs_SMA200", None)
        grouped = _transform_output(_base_action_summary(), flat)
        fa = grouped.get("floor_analysis", {})
        hf = fa.get("higher_frame", {})
        sma200 = hf.get("sma200") if hf else None
        if sma200:
            assert sma200.get("price_distance") is None

    def test_division_by_zero_guarded(self):
        # If sma200 price is 0 (theoretical only, gates should prevent),
        # pct must be None rather than crashing. Mirrors the macro_frame
        # pattern at transform.py:1491.
        pd = _get_higher_frame_price_distance("A", 10.0, 0)
        # Either price_distance is None (gated) or pct is None (defensive)
        if pd is not None:
            assert pd["pct"] is None, "Division-by-zero must yield pct=None, not crash"


# ===========================================================================
# 5. TestHFI001BVocabularyHygiene (4 tests)
# ===========================================================================

class TestHFI001BVocabularyHygiene:
    """Verify the three HFI-001-B vocabularies (CYCLICAL_*, SECULAR_*,
    DECADAL_*) are mutually disjoint and don't collide with adjacent
    engine vocabularies. Brief §4 'Vocabulary Collision Audit' pre-locked
    these claims; this class is the enforcement.
    """

    @staticmethod
    def _collect_labels(helper):
        observed = set()
        for v in [-50.0, 0.0, 10.0, 25.0, 50.0, 75.0, 100.0, 150.0, 200.0, 300.0, 400.0]:
            cond, _ = helper(v)
            if cond is not None:
                observed.add(cond["label"])
        return observed

    def test_three_vocabularies_are_mutually_disjoint(self):
        cyclical_labels = self._collect_labels(_daily_cyclical_elevation)
        secular_labels  = self._collect_labels(_macro_secular_elevation)
        decadal_labels  = self._collect_labels(_monthly_decadal_elevation)

        assert len(cyclical_labels) == 6, f"Expected 6 CYCLICAL labels, got {len(cyclical_labels)}"
        assert len(secular_labels) == 6, f"Expected 6 SECULAR labels, got {len(secular_labels)}"
        assert len(decadal_labels) == 6, f"Expected 6 DECADAL labels, got {len(decadal_labels)}"

        assert not (cyclical_labels & secular_labels), (
            f"CYCLICAL and SECULAR overlap: {cyclical_labels & secular_labels}"
        )
        assert not (cyclical_labels & decadal_labels), (
            f"CYCLICAL and DECADAL overlap: {cyclical_labels & decadal_labels}"
        )
        assert not (secular_labels & decadal_labels), (
            f"SECULAR and DECADAL overlap: {secular_labels & decadal_labels}"
        )

    def test_no_collision_with_extension_analysis_vocab(self):
        """extension_analysis.condition.label uses OVEREXTENDED / BELOW_FLOOR
        / EXHAUSTION / BLOW_OFF_ZONE for ATR-units overextension. HFI-001-B
        (percentage-units) must use distinct vocabulary so the operator sees
        these as complementary perspectives, not duplicates.
        """
        forbidden = {"OVEREXTENDED", "BELOW_FLOOR", "EXHAUSTION", "BLOW_OFF_ZONE"}
        all_labels = (
            self._collect_labels(_daily_cyclical_elevation)
            | self._collect_labels(_macro_secular_elevation)
            | self._collect_labels(_monthly_decadal_elevation)
        )
        overlap = all_labels & forbidden
        assert not overlap, (
            f"HFI-001-B vocabulary collides with extension_analysis: {overlap}"
        )

    def test_no_collision_with_fpc001_vocab(self):
        """FPC-001 uses WITHIN_ZONE / EDGE_OF_ZONE / BEYOND_ZONE /
        FAR_BEYOND_ZONE / EXTREME_DISTANCE on floor_proximity_pct.
        HFI-001-B must not reuse those tokens."""
        forbidden = {
            "WITHIN_ZONE", "EDGE_OF_ZONE", "BEYOND_ZONE",
            "FAR_BEYOND_ZONE", "EXTREME_DISTANCE",
        }
        all_labels = (
            self._collect_labels(_daily_cyclical_elevation)
            | self._collect_labels(_macro_secular_elevation)
            | self._collect_labels(_monthly_decadal_elevation)
        )
        overlap = all_labels & forbidden
        assert not overlap, f"HFI-001-B vocabulary collides with FPC-001: {overlap}"

    def test_no_collision_with_structural_breakdown_token(self):
        """STRUCTURAL_* prefix was REJECTED for DECADAL_* during design
        because STRUCTURAL_BREAKDOWN already exists in
        floor_failure.context (D4 rationale). Enforce: no HFI-001-B label
        starts with STRUCTURAL_.
        """
        all_labels = (
            self._collect_labels(_daily_cyclical_elevation)
            | self._collect_labels(_macro_secular_elevation)
            | self._collect_labels(_monthly_decadal_elevation)
        )
        offenders = {lbl for lbl in all_labels if lbl.startswith("STRUCTURAL_")}
        assert not offenders, (
            f"HFI-001-B vocabulary uses rejected STRUCTURAL_* prefix: {offenders} "
            "-- collides with floor_failure.context STRUCTURAL_BREAKDOWN"
        )


# ===========================================================================
# 6. TestHFI001BPercentageMath (3 tests)
# ===========================================================================

class TestHFI001BPercentageMath:
    """Verify pct = (dollars / sma200) * 100, rounded to 2dp. Math is
    identical across all three profiles since cutoffs are unified per D5,
    but we test all three to lock the per-profile flat-key wiring.
    """

    def test_profile_a_pct_math(self):
        # 42.63 / 463.48 * 100 = 9.197... -> rounded to 9.2
        pd = _get_higher_frame_price_distance("A", 42.63, 463.48)
        assert pd["pct"] == 9.2

    def test_profile_b_pct_math(self):
        # PLTR B live: 70.46 / 63.53 * 100 = 110.9082... -> 110.91
        pd = _get_higher_frame_price_distance("B", 70.46, 63.53)
        assert pd["pct"] == 110.91

    def test_profile_c_pct_math(self):
        # Synthetic: 30 / 20 * 100 = 150.0
        pd = _get_higher_frame_price_distance("C", 30.0, 20.0)
        assert pd["pct"] == 150.0


# ===========================================================================
# 7. TestHFI001BLiveDataAnchors (6 tests)
# ===========================================================================

class TestHFI001BLiveDataAnchors:
    """Verify all live-data anchors cited in brief §4 produce the predicted
    band classifications. These are the empirical justifications for the
    locked cutoff schedule -- they must hold or D5 is invalidated.
    """

    def test_lin_a_daily_9_2_pct_is_early_cyclical(self):
        # Brief §4 anchor: LIN A daily 9.2% -> EARLY_CYCLICAL
        cond, _ = _daily_cyclical_elevation(9.2)
        assert cond["label"] == "EARLY_CYCLICAL_ELEVATION"

    def test_oxy_a_daily_24_8_pct_at_boundary(self):
        # Brief §4 anchor: OXY A daily 24.8% -> ESTABLISHED boundary
        # (24.8 is just inside EARLY since cutoff is strict-below 25)
        cond, _ = _daily_cyclical_elevation(24.8)
        assert cond["label"] == "EARLY_CYCLICAL_ELEVATION", (
            "24.8% should be EARLY (cutoff at 25 is strict-below)"
        )
        # The boundary itself emits ESTABLISHED
        cond, _ = _daily_cyclical_elevation(25.0)
        assert cond["label"] == "ESTABLISHED_CYCLICAL_ELEVATION"

    def test_enph_a_daily_45_1_pct_is_established_cyclical(self):
        # Brief §4 anchor: ENPH A daily 45.1% -> ESTABLISHED_CYCLICAL
        cond, _ = _daily_cyclical_elevation(45.1)
        assert cond["label"] == "ESTABLISHED_CYCLICAL_ELEVATION"

    def test_eog_b_weekly_14_78_pct_is_early_secular(self):
        # Brief §4 anchor: EOG B weekly 14.78% -> EARLY_SECULAR
        cond, _ = _macro_secular_elevation(14.78)
        assert cond["label"] == "EARLY_SECULAR_ELEVATION"

    def test_pltr_b_weekly_110_9_pct_is_mature_secular(self):
        # Brief §4 anchor: PLTR B weekly 110.9% -> MATURE_SECULAR
        # Also confirmed in live run from validation session: pct = 110.91
        cond, _ = _macro_secular_elevation(110.9)
        assert cond["label"] == "MATURE_SECULAR_ELEVATION"
        cond, _ = _macro_secular_elevation(110.91)
        assert cond["label"] == "MATURE_SECULAR_ELEVATION"

    def test_nvda_a_daily_21_16_pct_is_early_cyclical_live(self):
        # Live anchor from HFI-001-A validation session: NVDA A higher_frame
        # value=39.35 sma200=185.97 -> pct=21.16 -> EARLY_CYCLICAL.
        # This is the FULL emission-path live anchor that will validate
        # automatically on the next NVDA A run.
        pd = _get_higher_frame_price_distance("A", 39.35, 185.97)
        assert pd["pct"] == 21.16
        assert pd["condition"]["label"] == "EARLY_CYCLICAL_ELEVATION"
