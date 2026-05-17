"""HFI-001-A -- Higher Frame Interpretation: primary-frame ADX banding tests.

Adds a `condition: {label, desc}` sub-object + `thresholds` dictionary to
`trend_state.directional.adx` on the primary frame across all three profiles.
Reuses the existing _ths_band vocabulary (CRITICAL / WEAK / CAUTION /
ACCEPTABLE / HEALTHY / STRONG) at cutoffs 15 / 20 / 25 / 33 / 40 already
locked for `macro_frame.adx` in WKC-001 v1.1.

Closes gap log §A2 Gap 2 (trend_state.directional.adx lacks band).

Profile-aware desc text identifies the actual primary timeframe:
    Profile A (SWING)  -> "Hourly ADX ..."
    Profile B (TREND)  -> "Daily ADX ..."
    Profile C (WEALTH) -> "Weekly ADX ..."

Bands (transform.py:_primary_adx_condition):
    < 15:        CRITICAL    (no directional structure)
    15 - 20:     WEAK        (sub-threshold; no regime)
    20 - 25:     CAUTION     (regime just emerging)
    25 - 33:     ACCEPTABLE  (regime confirmed)
    33 - 40:     HEALTHY     (strong regime)
    >= 40:       STRONG      (powerful regime; THS_Dir_Momentum saturation)

Backward compatibility:
    value, threshold (= 20 integer), and outer desc all preserved unchanged.
    condition and thresholds are additive.

Test classes:
    1. TestHFI001ABandLogic              (8) -- All bands + boundaries + None
    2. TestHFI001AEmission               (5) -- Sub-object shape via _transform_output
    3. TestHFI001AVocabularyConsistency  (2) -- Labels + cutoffs identical to macro_frame.adx
    4. TestHFI001AProfileTimeframeAwareness (3) -- Desc Hourly/Daily/Weekly per profile
"""

import os
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tbs_engine.transform import (
    _transform_output,
    _primary_adx_condition,
    _macro_adx_condition,
    _MACRO_ADX_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_action_summary():
    return {
        "verdict": "INVALID",
        "reason": {"label": "TEST", "detail": "HFI-001-A fixture"},
        "approaching": False,
        "volume": "NEUTRAL",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
        "caution_factors": [],
        "volatility_regime": {"label": "ALIGNED", "interpretation": "STANDARD"},
    }


# Data_Basis substrings that drive the engine's profile-to-timeframe mapping.
# These mirror what output.py:1946-1958 emits per profile.
_DATA_BASIS_PROFILE_A = "SWING analysis based on completed bar 09:30-10:30 ET. Live price at 14:32 ET."
_DATA_BASIS_PROFILE_B = "TREND analysis with data up to 2024-10-15 close ET."
_DATA_BASIS_PROFILE_C = "WEALTH analysis with data up to 2024-10-11 close ET."


def _base_flat_metrics(profile_letter, adx_value):
    """Minimal flat metrics for driving _transform_output with a chosen
    profile and ADX value. We only care about the trend_state.directional.adx
    sub-object here; everything else is given safe defaults.
    """
    data_basis = {
        "A": _DATA_BASIS_PROFILE_A,
        "B": _DATA_BASIS_PROFILE_B,
        "C": _DATA_BASIS_PROFILE_C,
    }[profile_letter]
    return {
        "Data_Basis": data_basis,
        "ADX": adx_value,
        "Engine_State": "MID-RANGE (ADX <20)",
        "Engine_State_Desc": "Test desc",
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


def _get_directional_adx(profile_letter, adx_value):
    """Drive _transform_output and return the directional.adx sub-object."""
    flat = _base_flat_metrics(profile_letter, adx_value)
    grouped = _transform_output(_base_action_summary(), flat)
    ts = grouped.get("trend_state", {})
    return ts.get("directional", {}).get("adx", {})


# ===========================================================================
# 1. TestHFI001ABandLogic (8 tests)
# ===========================================================================

class TestHFI001ABandLogic:
    """Verify _primary_adx_condition returns correct band across all 6 bands.
    Boundary cases tested explicitly at every cutoff (15 / 20 / 25 / 33 / 40).
    """

    def test_critical_below_15(self):
        for v in [0.0, 5.0, 10.0, 14.99]:
            cond, _ = _primary_adx_condition(v, "Hourly")
            assert cond["label"] == "CRITICAL", f"ADX {v} should be CRITICAL"

    def test_weak_at_exactly_15(self):
        # 15.0 is the lower boundary of WEAK (CRITICAL ends strict-below 15)
        cond, _ = _primary_adx_condition(15.0, "Hourly")
        assert cond["label"] == "WEAK"

    def test_weak_in_15_to_20_range(self):
        for v in [15.0, 17.5, 19.99]:
            cond, _ = _primary_adx_condition(v, "Daily")
            assert cond["label"] == "WEAK", f"ADX {v} should be WEAK"

    def test_caution_at_exactly_20(self):
        # 20.0 boundary: gate threshold from state classifier; CAUTION starts here
        cond, _ = _primary_adx_condition(20.0, "Daily")
        assert cond["label"] == "CAUTION"
        cond, _ = _primary_adx_condition(24.99, "Daily")
        assert cond["label"] == "CAUTION"

    def test_acceptable_at_exactly_25_and_lin_live_value(self):
        # 25.0 boundary; LIN A live value of 25.86 from brief §3 -> ACCEPTABLE
        cond, _ = _primary_adx_condition(25.0, "Hourly")
        assert cond["label"] == "ACCEPTABLE"
        cond, _ = _primary_adx_condition(25.86, "Hourly")
        assert cond["label"] == "ACCEPTABLE", (
            "LIN A live ADX value (25.86) should classify as ACCEPTABLE -- "
            "the band-classification anchor cited in HFI-001 design brief §3"
        )
        cond, _ = _primary_adx_condition(32.99, "Hourly")
        assert cond["label"] == "ACCEPTABLE"

    def test_healthy_in_33_to_40_range(self):
        cond, _ = _primary_adx_condition(33.0, "Weekly")
        assert cond["label"] == "HEALTHY"
        cond, _ = _primary_adx_condition(39.99, "Weekly")
        assert cond["label"] == "HEALTHY"

    def test_strong_at_or_above_40(self):
        cond, _ = _primary_adx_condition(40.0, "Hourly")
        assert cond["label"] == "STRONG"
        cond, _ = _primary_adx_condition(75.0, "Hourly")
        assert cond["label"] == "STRONG"

    def test_none_input_returns_none_condition_with_thresholds(self):
        # FPC-001 convention: thresholds dict ALWAYS emitted, condition is None
        cond, thr = _primary_adx_condition(None, "Hourly")
        assert cond is None
        assert isinstance(thr, dict)
        assert thr["critical_below"] == 15
        assert thr["strong_at_or_above"] == 40


# ===========================================================================
# 2. TestHFI001AEmission (5 tests)
# ===========================================================================

class TestHFI001AEmission:
    """Verify trend_state.directional.adx sub-object shape post-transform.
    Schema: {value, threshold, condition: {label, desc}, thresholds, desc}
    """

    def test_emission_includes_value_threshold_condition_and_thresholds(self):
        # Anchor case: LIN A 25.86 -> ACCEPTABLE on Profile A hourly
        adx_obj = _get_directional_adx("A", 25.86)
        assert adx_obj["value"] == 25.86
        # Legacy single-integer threshold preserved (state-boundary gate at 20)
        assert adx_obj["threshold"] == 20
        # New condition + thresholds
        assert isinstance(adx_obj["condition"], dict)
        assert adx_obj["condition"]["label"] == "ACCEPTABLE"
        assert "Hourly" in adx_obj["condition"]["desc"]
        assert isinstance(adx_obj["thresholds"], dict)
        # All 6 threshold keys present
        for key in ("critical_below", "weak_below", "caution_below",
                    "acceptable_below", "healthy_below", "strong_at_or_above"):
            assert key in adx_obj["thresholds"], f"Missing threshold key: {key}"

    def test_emission_outer_desc_preserved(self):
        # Backward compatibility: outer 'desc' field unchanged
        adx_obj = _get_directional_adx("A", 25.86)
        assert adx_obj["desc"] == "Trend strength (state boundary)"

    def test_emission_when_adx_is_none(self):
        # Schema stability: thresholds dict present, condition is None
        adx_obj = _get_directional_adx("A", None)
        assert adx_obj["value"] is None
        assert adx_obj["threshold"] == 20  # static field unaffected
        assert adx_obj["condition"] is None
        assert isinstance(adx_obj["thresholds"], dict)
        assert adx_obj["thresholds"]["critical_below"] == 15

    def test_emission_critical_band_profile_b(self):
        # EOG B live anchor from brief §3: ADX 13.39 -> CRITICAL
        adx_obj = _get_directional_adx("B", 13.39)
        assert adx_obj["condition"]["label"] == "CRITICAL"
        assert "Daily" in adx_obj["condition"]["desc"]

    def test_emission_strong_band_profile_c(self):
        # Profile C weekly with a high ADX -> STRONG label, Weekly desc
        adx_obj = _get_directional_adx("C", 45.0)
        assert adx_obj["condition"]["label"] == "STRONG"
        assert "Weekly" in adx_obj["condition"]["desc"]


# ===========================================================================
# 3. TestHFI001AVocabularyConsistency (2 tests)
# ===========================================================================

class TestHFI001AVocabularyConsistency:
    """Verify the HFI-001-A primary-frame vocabulary stays in lockstep with
    the WKC-001 v1.1 macro_frame.adx vocabulary. Per D-spec, these MUST be
    identical (labels + cutoffs). Drift on either side is a charter
    violation (vocabulary fragmentation) and must surface immediately.
    """

    def test_band_labels_identical_to_macro_adx_across_all_cutoffs(self):
        """Sweep ADX values across every band; macro and primary must agree
        on the LABEL at every single sample point.
        """
        # Sample points chosen to hit every band including all boundaries
        sample_points = [
            0.0, 5.0, 10.0, 14.99,   # CRITICAL
            15.0, 17.5, 19.99,        # WEAK
            20.0, 22.5, 24.99,        # CAUTION
            25.0, 28.0, 32.99,        # ACCEPTABLE
            33.0, 36.0, 39.99,        # HEALTHY
            40.0, 60.0, 100.0,        # STRONG
        ]
        for v in sample_points:
            macro_cond, _ = _macro_adx_condition(v)
            primary_cond, _ = _primary_adx_condition(v, "Hourly")
            assert macro_cond["label"] == primary_cond["label"], (
                f"Label drift at ADX={v}: macro={macro_cond['label']!r} "
                f"vs primary={primary_cond['label']!r}. "
                "HFI-001 D-spec requires identity."
            )

    def test_thresholds_dict_identical_to_macro_adx(self):
        """Both helpers must return the SAME thresholds dict. We assert
        value equality (== dict comparison) AND identity (is, since both
        reuse the same module-level constant per HFI-001-A implementation).
        """
        _, macro_thr = _macro_adx_condition(25.0)
        _, primary_thr = _primary_adx_condition(25.0, "Hourly")
        assert macro_thr == primary_thr, (
            "thresholds dict drift between macro_frame.adx and primary-frame "
            "adx -- HFI-001 D-spec requires identical cutoffs"
        )
        # Identity check: both should be the same _MACRO_ADX_THRESHOLDS
        # constant. This is the strongest possible guarantee against drift --
        # any future maintainer who introduces a separate copy will trip this.
        assert macro_thr is _MACRO_ADX_THRESHOLDS
        assert primary_thr is _MACRO_ADX_THRESHOLDS


# ===========================================================================
# 4. TestHFI001AProfileTimeframeAwareness (3 tests)
# ===========================================================================

class TestHFI001AProfileTimeframeAwareness:
    """Verify the desc text identifies the ACTUAL primary timeframe per
    profile (not a generic 'primary frame' string). Brief §3:
        Profile A -> Hourly
        Profile B -> Daily
        Profile C -> Weekly
    """

    def test_profile_a_desc_says_hourly(self):
        adx_obj = _get_directional_adx("A", 25.86)
        desc = adx_obj["condition"]["desc"]
        assert desc.startswith("Hourly ADX"), (
            f"Profile A desc should start with 'Hourly ADX', got: {desc!r}"
        )
        # Must NOT contain other timeframe words (defensive)
        assert "Daily ADX" not in desc
        assert "Weekly ADX" not in desc

    def test_profile_b_desc_says_daily(self):
        adx_obj = _get_directional_adx("B", 13.39)  # CRITICAL band
        desc = adx_obj["condition"]["desc"]
        assert desc.startswith("Daily ADX"), (
            f"Profile B desc should start with 'Daily ADX', got: {desc!r}"
        )
        assert "Hourly ADX" not in desc
        assert "Weekly ADX" not in desc

    def test_profile_c_desc_says_weekly(self):
        adx_obj = _get_directional_adx("C", 45.0)  # STRONG band
        desc = adx_obj["condition"]["desc"]
        assert desc.startswith("Weekly ADX"), (
            f"Profile C desc should start with 'Weekly ADX', got: {desc!r}"
        )
        assert "Hourly ADX" not in desc
        assert "Daily ADX" not in desc
