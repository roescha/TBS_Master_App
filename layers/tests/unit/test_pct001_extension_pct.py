"""PCT-001 -- Percentage-from-Anchor Parallel Metric tests.

Spec: BUNDLE001_SWING_Output_Enrichment_Spec_v1_1.md (S153 v1.1)

Covers the six test classes enumerated in spec §5.2:

    1. TestPCT001ProfileADailyExtensionPct          -- Profile A daily distance_pct
    2. TestPCT001ProfileAMediumTerm                 -- Profile A medium_term reduced shape
    3. TestPCT001ProfileBLegacyAlias                -- Profile B both keys identical
    4. TestPCT001ProfileBLabelCautionUnchanged      -- DQ-8 scope guard (no _Label alias)
    5. TestPCT001ProfileADailyExtensionPctNullSafety -- defensive None on degenerate input
    6. TestPCT001ProfileCNoChange                   -- DQ-7 scope guard (Profile C unchanged)

Construction notes:
    - Uses direct importlib load (TEST-HRN-001 safe pattern); transform.py has
      zero imports within tbs_engine.
    - Profile detection in transform.py uses Floor_Anchor_Type as proxy
      ("EMA_21" -> Profile A, "SMA_50" -> Profile B, "SMA_200" -> Profile C).
    - Profile A medium_term block (transform.py:1825) requires
      _floor_anchor_for_ext == "EMA_21" AND _medium_term_extension is None
      (i.e., Profile B's block at line 1800 must NOT have populated it -- so
      MediumTerm_Extension_Pct must be absent on Profile A test inputs).
    - Profile A daily distance_pct (transform.py:1755-1762) requires the
      _daily_extension block to fire, which needs Daily_Extension_Distance
      non-null. distance_pct.value is None when Context_EMA_21 is None
      (defensive null-safety per spec §4.2.1).
"""

import os
import sys
import importlib.util

import pytest


# ---------------------------------------------------------------------------
# Direct file import -- TEST-HRN-001 safe pattern
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_root = os.path.join(os.path.dirname(__file__), "..", "..")
_spec = importlib.util.spec_from_file_location(
    "tbs_engine_transform_pct001",
    os.path.join(_root, "tbs_engine", "transform.py"),
)
_transform_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output
_flatten = _transform_mod._flatten


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_action_summary():
    return {
        "verdict": "VALID",
        "reason": {"label": "VALID PULLBACK", "detail": ""},
        "mandate": "ENTER",
        "context": "",
    }


def _base_flat_metrics(**overrides):
    """Base flat_metrics with all hierarchy source values populated.

    Defaults to Profile A (Floor_Anchor_Type=EMA_21) with Price=130.0,
    Context_EMA_21=127.0, Context_Daily_SMA50=123.0. By default
    MediumTerm_Extension_Pct is ABSENT so the Profile A medium_term block at
    transform.py:1825 fires (Profile B block at 1800 does not populate
    _medium_term_extension). Tests override specific keys for Profile B/C
    scenarios or to construct null-safety paths.
    """
    m = {
        # Core
        "Price": 130.0,
        "Structural_Floor": 125.0,
        "Floor_Anchor_Type": "EMA_21",
        "Floor_Anchor_Label": "Intraday institutional value level",
        "Anchor_Label": "VWAP (Baseline Floor)",
        "Anchor_Type": "Standard",
        "Extension_Anchor_Type": "VWAP",
        "Extension_Anchor_Label": "Intraday institutional value level",
        "Hard_Stop": 120.0,
        "Resistance": 135.0,
        "EMA_8": 129.0,
        "EMA_21": 127.0,
        "SMA_50": 122.0,
        "SMA_200": 110.0,
        "VWAP": 126.0,
        "ATR": 2.5,
        "ADV_20": 5000000.0,
        "ADV_20_Dollar": 650000000.0,
        "Is_ETF": False,

        # Daily extension (PCT-001 trigger -- Daily_Extension_Distance is the
        # gate at transform.py:1745 to enter the _daily_extension block where
        # distance_pct is computed)
        "Daily_Extension_Distance": 0.8,
        "Daily_Extension_Label": "NORMAL",

        # Targets
        "Profit_Target": 135.0,
        "Profit_Target_Source": "10_Bar_Resistance",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "MM_Target": 140.0,
        "Blue_Sky_Target": 145.0,
        "Blue_Sky_Method": "ATR_PROJECTION",
        "Blue_Sky_Detected": True,
        "Fundamental_Target": 150.0,

        # Psychological
        "Psych_Floor": 125.0,
        "Psych_Ceiling": 140.0,
        "Psych_Floor_Dist_Pct": 3.85,
        "Psych_Ceiling_Dist_Pct": 7.69,
        "Psych_Floor_Near_Structural": False,
        "Psych_Ceiling_Near_Technical": False,
        "Psych_Increment": 5.0,
        "RN_Target_Proximity": None,
        "RN_Stop_Proximity": None,
        "RN_Floor_Proximity": None,

        # Floor sources
        "Daily_Protective_Anchor": 128.0,
        "Daily_Hard_Stop": 124.0,
        "Daily_ATR": 3.0,
        "Context_EMA_21": 128.0,
        "Context_Daily_SMA50": 123.0,
        "Context_SMA200": 112.0,
        "AVWAP_Price": 127.5,
        "Established_Hourly_Low": 126.0,

        # Engine state
        "Engine_State": "TRENDING",
        "Engine_State_Desc": "ADX > 20 + full MA stack + no squeeze",
        "ADX": 30.0,
        "ADX_Accel": 0.5,
        "ADX_Accel_State": "ACCELERATING",
        "DI_Plus": 25.0,
        "DI_Minus": 15.0,
        "DI_Spread": 10.0,
        "DI_Bias": "BULLISH",
        "Trend_Age_Bars": 5,
        "Trend_Age_Max": 20,
        "Active_Modifiers": "None",
        "Active_Modifiers_List": [],
        "Inst_Churn": "CLEAR (No Churn)",
        "ATR_Dist": 0.8,
        "ATR_Dist_Anchor": "VWAP",
        "Extension_Limit": 1.5,
        "Trend_Health_Score": 65.0,
        "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 70.0,
        "THS_Dir_Momentum": 60.0,
        "THS_Trend_Age": 55.0,
        "THS_Structure": 50.0,
        "THS_Floor_Buffer_Label": "HEALTHY",
        "THS_Dir_Momentum_Label": "HEALTHY",
        "THS_Trend_Age_Label": "ACCEPTABLE",
        "THS_Structure_Label": "ACCEPTABLE",
        "THS_Death_Cross_Cap": False,
        "THS_Component_Cap": None,
        "THS_VWAP_Floor_Penalty": False,
        "THS_VWAP_Floor_Note": None,
        "THS_Context_Advisory": None,
        "Vol_Confirm_Ratio": 1.2,
        "Vol_Confirm_State": "STRONG ACCUMULATION",
        "Vol_Confirm_Bias": "BULLISH",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Failure_Threshold": 8,
        "Exit_Signal": "HOLD",
        "window_count": 3,
        "Window_Limit": 4,
        "Window_Reset_Event": "PULLBACK",
        "Reward_Risk": 2.5,
        "Reward_Risk_Note": None,
        "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Reward/Risk above 2.0 -- strong setup",
    }
    m.update(overrides)
    return m


def _profile_b_overrides():
    """Profile B overrides: Floor_Anchor_Type=SMA_50, MediumTerm_Extension_Pct
    populated to trigger the Profile B medium_term block at transform.py:1800.

    NB: Profile A daily distance_pct block ALSO fires on Profile B if
    Daily_Extension_Distance is non-null AND Context_EMA_21 is non-null -- the
    block's gate is on Daily_Extension_Distance, not on Floor_Anchor_Type.
    However the medium_term Profile-A-only block at 1825 is correctly guarded
    on Floor_Anchor_Type == "EMA_21" so on Profile B only the Profile B
    block at 1800 populates _medium_term_extension.
    """
    return {
        "Floor_Anchor_Type": "SMA_50",
        "VWAP": None,
        "AVWAP_Price": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
        # Profile B uses weekly context frame for higher_frame -- swap daily
        # SMA50 for weekly to drive _hf_timeframe = WEEKLY
        "Context_Daily_SMA50": None,
        "Context_Weekly_SMA50": 121.0,
        "Context_Weekly_SMA50_Slope": 0.3,
        # Profile B medium_term trigger -- MediumTerm_Extension_Pct present
        "MediumTerm_Extension_Pct": 6.5,
        "MediumTerm_Extension_Label": "NORMAL",
    }


def _profile_c_overrides():
    """Profile C overrides: Floor_Anchor_Type=SMA_200, weekly primary +
    monthly context frame. No Daily_Extension_Distance, no
    MediumTerm_Extension_Pct -- neither extension block fires on Profile C
    per DQ-7 scope guard."""
    return {
        "Floor_Anchor_Type": "SMA_200",
        "VWAP": None,
        "AVWAP_Price": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
        "Daily_Extension_Distance": None,
        "Daily_Extension_Label": None,
        "Context_Daily_SMA50": None,
        "Context_Monthly_SMA50": 118.0,
        "Context_Monthly_SMA50_Slope": 0.4,
        "Context_Monthly_SMA200": 108.0,
    }


def _get_grouped(flat_overrides=None):
    """Run _transform_output with default base and return grouped dict."""
    fm = _base_flat_metrics(**(flat_overrides or {}))
    return _transform_output(_base_action_summary(), fm)


def _get_flat(flat_overrides=None):
    """Run engine end-to-end (grouped -> flatten) and return flat metrics dict.

    _flatten returns a 3-tuple (status, diagnostic, flat_metrics_dict).
    The flat_metrics dict is the third element.
    """
    grouped = _get_grouped(flat_overrides)
    _status, _diagnostic, flat = _flatten(grouped)
    return flat


def _get_extension(flat_overrides=None):
    """Shortcut: returns top-level extension_analysis dict.

    Per the engine output structure (transform.py:2681), extension_analysis
    is a TOP-LEVEL group key, NOT nested inside trade_setup. The spec §5.2
    prose used the path 'trade_setup.extension_analysis...' which is
    inaccurate -- the engine source is canonical per SIR §2.
    """
    return _get_grouped(flat_overrides).get("extension_analysis")


# ===========================================================================
# 1. TestPCT001ProfileADailyExtensionPct -- Profile A daily distance_pct field
# ===========================================================================


class TestPCT001ProfileADailyExtensionPct:
    """Spec §4.2.1 + §5.2: on a Profile A path with non-null
    Daily_Extension_Distance, assert trade_setup.extension_analysis.daily.
    distance_pct.value is non-null, unit is '%', and desc references
    'Percentage distance from Daily EMA 21'. Assert flat key
    Pct_From_Daily_EMA21 carries the same value as
    extension_analysis.daily.distance_pct.value."""

    def test_distance_pct_field_present_and_populated(self):
        """Profile A: extension_analysis.daily.distance_pct is non-null."""
        ext = _get_extension()
        assert ext is not None
        assert ext.get("daily") is not None
        daily = ext["daily"]
        assert "distance_pct" in daily, (
            "Profile A daily block missing distance_pct sibling field"
        )
        assert daily["distance_pct"] is not None

    def test_distance_pct_shape_value_unit_desc(self):
        """distance_pct mirrors existing distance field shape: {value, unit, desc}."""
        ext = _get_extension()
        daily = ext["daily"]
        dp = daily["distance_pct"]
        assert "value" in dp
        assert "unit" in dp
        assert "desc" in dp
        assert dp["value"] is not None
        assert dp["unit"] == "%"
        assert "Percentage distance from Daily EMA 21" in dp["desc"]

    def test_distance_pct_value_arithmetic(self):
        """Computation: (Price - Context_EMA_21) / Context_EMA_21 * 100.
        Base fixture has Price=130, Context_EMA_21=128 -> (2/128)*100 = 1.5625
        rounded to 1.56."""
        ext = _get_extension()
        daily = ext["daily"]
        # (130 - 128) / 128 * 100 = 1.5625 -> round(.,2) = 1.56
        assert daily["distance_pct"]["value"] == 1.56

    def test_flat_key_pct_from_daily_ema21_matches_grouped(self):
        """Flat key Pct_From_Daily_EMA21 carries the same value as
        extension_analysis.daily.distance_pct.value."""
        flat = _get_flat()
        ext = _get_extension()
        expected = ext["daily"]["distance_pct"]["value"]
        assert flat.get("Pct_From_Daily_EMA21") == expected

    def test_distance_pct_sibling_to_distance(self):
        """distance and distance_pct coexist as siblings -- ATR-unit and %-unit
        in parallel (DQ-6 'parallel' framing)."""
        ext = _get_extension()
        daily = ext["daily"]
        assert "distance" in daily
        assert "distance_pct" in daily
        assert daily["distance"]["unit"] == "ATR"
        assert daily["distance_pct"]["unit"] == "%"


# ===========================================================================
# 2. TestPCT001ProfileAMediumTerm -- Profile A medium_term reduced shape (DQ-8)
# ===========================================================================


class TestPCT001ProfileAMediumTerm:
    """Spec §4.2.2 + §5.2: on a Profile A path with non-null Context_Daily_SMA50
    and non-null Price, assert trade_setup.extension_analysis.medium_term is
    non-null and has exactly two top-level keys (distance, anchor) -- no
    condition, no thresholds, no caution_note per DQ-8. Assert flat key
    Pct_From_Daily_SMA50 carries the same value as
    extension_analysis.medium_term.distance.value."""

    def test_medium_term_block_present_on_profile_a(self):
        """Profile A: extension_analysis.medium_term is non-null when
        Floor_Anchor_Type=EMA_21 and Context_Daily_SMA50 is populated."""
        ext = _get_extension()
        assert ext.get("medium_term") is not None, (
            "Profile A medium_term block did not fire -- check guard at "
            "transform.py:1825 (_floor_anchor_for_ext == 'EMA_21' and "
            "_medium_term_extension is None)"
        )

    def test_medium_term_has_only_distance_anchor_and_interpretation_keys(self):
        """DQ-8 reduced shape + OD-3 interpretation extension: exactly THREE
        top-level keys (distance, anchor, interpretation). No condition, no
        thresholds, no caution_note per DQ-8 -- Profile A retains no
        research-grounded gating thresholds. The interpretation field is
        industry-convention guidance (informational only, does NOT gate)."""
        ext = _get_extension()
        mt = ext["medium_term"]
        assert set(mt.keys()) == {"distance", "anchor", "interpretation"}, (
            f"Profile A medium_term should have exactly "
            f"{{distance, anchor, interpretation}}, got {set(mt.keys())}"
        )
        # Explicit negative assertions per DQ-8 (gating siblings still absent)
        assert "condition" not in mt
        assert "thresholds" not in mt
        assert "caution_note" not in mt

    def test_medium_term_distance_shape_and_unit(self):
        """distance field: {value, unit='%', desc}."""
        ext = _get_extension()
        mt = ext["medium_term"]
        assert "value" in mt["distance"]
        assert mt["distance"]["unit"] == "%"
        assert "desc" in mt["distance"]

    def test_medium_term_anchor_label(self):
        """anchor.label = 'SMA_50' (Daily 50-period SMA on Profile A)."""
        ext = _get_extension()
        mt = ext["medium_term"]
        assert mt["anchor"]["label"] == "SMA_50"

    def test_medium_term_distance_value_arithmetic(self):
        """Computation: (Price - Context_Daily_SMA50) / Context_Daily_SMA50 * 100.
        Base fixture: (130 - 123) / 123 * 100 = 5.6910... -> 5.69."""
        ext = _get_extension()
        mt = ext["medium_term"]
        assert mt["distance"]["value"] == 5.69

    def test_flat_key_pct_from_daily_sma50_matches_grouped(self):
        """Flat key Pct_From_Daily_SMA50 == extension_analysis.medium_term.
        distance.value on Profile A (alias path runs uniformly for both
        profiles via the flatten layer at transform.py:3206)."""
        flat = _get_flat()
        ext = _get_extension()
        expected = ext["medium_term"]["distance"]["value"]
        assert flat.get("Pct_From_Daily_SMA50") == expected


# ===========================================================================
# 3. TestPCT001ProfileBLegacyAlias -- Profile B both keys identical
# ===========================================================================


class TestPCT001ProfileBLegacyAlias:
    """Spec §4.2.3 + §5.2: on a Profile B path with non-null
    MediumTerm_Extension_Pct, assert both MediumTerm_Extension_Pct and
    Pct_From_Daily_SMA50 flat keys exist; assert their values are identical."""

    def test_both_keys_present_on_profile_b(self):
        """Profile B flat output contains both legacy and canonical keys."""
        flat = _get_flat(_profile_b_overrides())
        assert "MediumTerm_Extension_Pct" in flat, (
            "Profile B missing legacy MediumTerm_Extension_Pct key"
        )
        assert "Pct_From_Daily_SMA50" in flat, (
            "Profile B missing canonical Pct_From_Daily_SMA50 alias key"
        )

    def test_both_keys_identical_value(self):
        """Single-value alias per DQ-8 -- bit-identical values."""
        flat = _get_flat(_profile_b_overrides())
        assert flat["MediumTerm_Extension_Pct"] == flat["Pct_From_Daily_SMA50"]
        # Specifically: base fixture override sets MediumTerm_Extension_Pct=6.5
        assert flat["MediumTerm_Extension_Pct"] == 6.5
        assert flat["Pct_From_Daily_SMA50"] == 6.5

    def test_profile_b_medium_term_block_unchanged_shape(self):
        """Profile B medium_term block at transform.py:1800 retains its full
        shape (distance, anchor, condition, thresholds) -- DQ-7 scope guard.
        PCT-001 §4.2.3 is an addition of a flat-key alias only; the grouped
        medium_term block is not restructured."""
        ext = _get_extension(_profile_b_overrides())
        mt = ext["medium_term"]
        # Profile B has the full 4-key (+optional caution_note) shape
        assert "distance" in mt
        assert "anchor" in mt
        assert "condition" in mt
        assert "thresholds" in mt


# ===========================================================================
# 4. TestPCT001ProfileBLabelCautionUnchanged -- DQ-8 scope guard
# ===========================================================================


class TestPCT001ProfileBLabelCautionUnchanged:
    """Spec §4.2.6 + §5.2 + DQ-8 scope guard: Profile B still emits
    MediumTerm_Extension_Label (and MediumTerm_Extension_Caution_Note when
    warranted) under their legacy names. No Pct_From_Daily_SMA50_Label or
    Pct_From_Daily_SMA50_Caution_Note flat keys exist -- the alias is
    single-value only, Label/Caution_Note aliasing was explicitly deferred
    to a future hygiene pass."""

    def test_medium_term_label_legacy_name_still_emits(self):
        """Profile B retains MediumTerm_Extension_Label flat key."""
        flat = _get_flat(_profile_b_overrides())
        assert "MediumTerm_Extension_Label" in flat
        # Profile B fixture override sets MediumTerm_Extension_Label="NORMAL"
        assert flat["MediumTerm_Extension_Label"] == "NORMAL"

    def test_caution_note_legacy_name_when_warranted(self):
        """Profile B retains MediumTerm_Extension_Caution_Note under legacy
        name when conditions warrant a caution note. Construct a CAUTION
        case with caution_note populated to confirm legacy key emission."""
        overrides = _profile_b_overrides()
        overrides["MediumTerm_Extension_Label"] = "CAUTION"
        overrides["MediumTerm_Extension_Caution_Note"] = (
            "SMA 50 distance approaching exhaustion -- monitor"
        )
        flat = _get_flat(overrides)
        assert "MediumTerm_Extension_Caution_Note" in flat
        assert flat["MediumTerm_Extension_Caution_Note"] == (
            "SMA 50 distance approaching exhaustion -- monitor"
        )

    def test_no_pct_from_daily_sma50_label_alias(self):
        """DQ-8: NO Pct_From_Daily_SMA50_Label flat key exists."""
        flat = _get_flat(_profile_b_overrides())
        assert "Pct_From_Daily_SMA50_Label" not in flat

    def test_no_pct_from_daily_sma50_caution_note_alias(self):
        """DQ-8: NO Pct_From_Daily_SMA50_Caution_Note flat key exists."""
        overrides = _profile_b_overrides()
        overrides["MediumTerm_Extension_Label"] = "CAUTION"
        overrides["MediumTerm_Extension_Caution_Note"] = "test note"
        flat = _get_flat(overrides)
        assert "Pct_From_Daily_SMA50_Caution_Note" not in flat


# ===========================================================================
# 5. TestPCT001ProfileADailyExtensionPctNullSafety -- defensive None per §4.2.1
# ===========================================================================


class TestPCT001ProfileADailyExtensionPctNullSafety:
    """Spec §4.2.1 + §5.2: on a Profile A path where Context_EMA_21 is None
    (degenerate -- shouldn't occur on real evaluation paths but the code is
    defensive), assert extension_analysis.daily.distance_pct.value is None,
    the rest of extension_analysis.daily is unchanged, and Pct_From_Daily_EMA21
    flat key is None."""

    def test_distance_pct_value_is_none_when_context_ema21_missing(self):
        """Context_EMA_21=None -> distance_pct.value=None; field still present
        (the dict literal at transform.py:1762 unconditionally writes the
        distance_pct entry once _daily_extension is being constructed)."""
        ext = _get_extension({"Context_EMA_21": None})
        daily = ext["daily"]
        assert "distance_pct" in daily
        assert daily["distance_pct"]["value"] is None
        # Other distance_pct sub-fields still well-formed
        assert daily["distance_pct"]["unit"] == "%"
        assert "Percentage distance from Daily EMA 21" in daily["distance_pct"]["desc"]

    def test_other_daily_fields_unchanged(self):
        """The rest of extension_analysis.daily is unchanged when
        Context_EMA_21 is None -- ATR-unit distance and other sub-fields
        keep their normal shape."""
        ext = _get_extension({"Context_EMA_21": None})
        daily = ext["daily"]
        # ATR-unit distance still populated (sourced from
        # Daily_Extension_Distance, not Context_EMA_21)
        assert daily["distance"]["value"] == 0.8
        assert daily["distance"]["unit"] == "ATR"
        # anchor/condition/thresholds preserved
        assert daily["anchor"]["label"] == "EMA_21"
        assert "condition" in daily
        assert "thresholds" in daily

    def test_flat_key_pct_from_daily_ema21_is_none(self):
        """Pct_From_Daily_EMA21 flat key is None when Context_EMA_21 is None."""
        flat = _get_flat({"Context_EMA_21": None})
        assert flat.get("Pct_From_Daily_EMA21") is None

    def test_distance_pct_value_none_when_price_missing(self):
        """Price=None -> distance_pct.value=None (parallel defensive guard).
        Note: removing Price entirely would break many other parts of the
        engine; we set it to None explicitly to exercise the conditional
        at transform.py:1758."""
        ext = _get_extension({"Price": None})
        daily = ext["daily"]
        assert daily["distance_pct"]["value"] is None

    def test_distance_pct_value_none_when_context_ema21_zero(self):
        """Context_EMA_21=0 -> distance_pct.value=None (guards
        division-by-zero per the > 0 check at transform.py:1758)."""
        ext = _get_extension({"Context_EMA_21": 0})
        daily = ext["daily"]
        assert daily["distance_pct"]["value"] is None


# ===========================================================================
# 6. TestPCT001ProfileCNoChange -- DQ-7 scope guard
# ===========================================================================


class TestPCT001ProfileCNoChange:
    """Spec §4.2.6 + §5.2 + DQ-7 scope guard: on a Profile C path, assert NO
    Pct_From_Daily_EMA21 or Pct_From_Daily_SMA50 flat key is emitted; assert
    extension_analysis shape is unchanged from pre-Bundle 1 baseline (no
    Profile C-specific PCT-001 additions). Profile C extension surfacing is
    deferred to WKC-001 / future."""

    def test_no_pct_from_daily_ema21_on_profile_c(self):
        """Profile C: Pct_From_Daily_EMA21 flat key is None or absent.
        Profile C has Floor_Anchor_Type=SMA_200, so the Profile A daily
        extension block (gated on Daily_Extension_Distance, which is None
        in the Profile C fixture) does not fire."""
        flat = _get_flat(_profile_c_overrides())
        # Per the flatten layer at transform.py:3184 only running inside
        # `if _daily and isinstance(_daily, dict):` -- when daily extension
        # didn't fire, the key may be absent or written as None elsewhere.
        # Conservative assertion: value is None (not populated).
        assert flat.get("Pct_From_Daily_EMA21") is None

    def test_no_pct_from_daily_sma50_on_profile_c(self):
        """Profile C: Pct_From_Daily_SMA50 flat key is None or absent.
        The flatten alias at transform.py:3206 only fires when
        extension_analysis.medium_term is present; Profile C has neither
        MediumTerm_Extension_Pct (Profile B trigger) nor the Profile A
        medium_term block firing (Floor_Anchor_Type != EMA_21)."""
        flat = _get_flat(_profile_c_overrides())
        assert flat.get("Pct_From_Daily_SMA50") is None

    def test_extension_analysis_no_pct001_additions_on_profile_c(self):
        """Profile C: extension_analysis.medium_term remains None (neither
        Profile A nor Profile B block fires); extension_analysis.daily is
        also None when Daily_Extension_Distance is absent."""
        ext = _get_extension(_profile_c_overrides())
        assert ext.get("medium_term") is None
        assert ext.get("daily") is None

    def test_profile_c_legacy_medium_term_keys_absent(self):
        """Profile C should not have MediumTerm_Extension_* keys populated --
        regression witness that PCT-001 didn't inadvertently introduce
        Profile C surfacing."""
        flat = _get_flat(_profile_c_overrides())
        assert flat.get("MediumTerm_Extension_Pct") is None
        assert flat.get("MediumTerm_Extension_Label") is None


# ===========================================================================
# 7. TestPCT001MediumTermInterpretation -- OD-3 closure (Operator scope ext)
# ===========================================================================


class TestPCT001MediumTermInterpretation:
    """OD-3 closure (post-Bundle 1 Operator scope extension): Profile A
    medium_term block gains an `interpretation` sibling field with
    industry-convention bands derived from distance.value (% from daily
    SMA 50).

    Bands (from _derive_medium_term_interpretation at transform.py):
        pct < -5:    BELOW_SMA_50
        -5 to 5:     HEALTHY
        5 to 10:     STRETCHED
        10 to 15:    EXTENDED
        15 to 20:    OVEREXTENDED
        20 to 30:    SIGNIFICANTLY_OVEREXTENDED
        pct >= 30:   BLOW_OFF_ZONE

    Industry-convention bands (O'Neil / Minervini frameworks), not
    TBS-research-calibrated. INFORMATIONAL only -- does NOT gate the
    verdict. DQ-8 retained: no `condition` / `thresholds` /
    `caution_note` siblings.
    """

    def test_interpretation_field_present_on_profile_a(self):
        """Profile A medium_term has an `interpretation` sibling with
        {label, desc} shape."""
        ext = _get_extension()  # base fixture: ~5.69% above SMA 50 -> STRETCHED
        mt = ext["medium_term"]
        assert "interpretation" in mt
        assert mt["interpretation"] is not None
        assert "label" in mt["interpretation"]
        assert "desc" in mt["interpretation"]
        assert isinstance(mt["interpretation"]["label"], str)
        assert isinstance(mt["interpretation"]["desc"], str)

    # ---- Band coverage tests across the percentage range ----

    def test_band_healthy_for_low_positive_distance(self):
        """3.33% above SMA 50 -> HEALTHY (within normal trending range)."""
        # Price=124, SMA50=120 -> (124-120)/120*100 = 3.33%
        ext = _get_extension({"Price": 124.0, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "HEALTHY"

    def test_band_healthy_for_minor_negative_distance(self):
        """-3% (slight below) -> HEALTHY (boundary -5% to 5%)."""
        # Price=116.4, SMA50=120 -> -3.00%
        ext = _get_extension({"Price": 116.4, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "HEALTHY"

    def test_band_below_sma_50_for_deep_negative(self):
        """-10% below SMA 50 -> BELOW_SMA_50 (trend-break warning)."""
        ext = _get_extension({"Price": 108.0, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "BELOW_SMA_50"

    def test_band_stretched_for_7pct(self):
        """7% above SMA 50 -> STRETCHED."""
        # Price=128.4, SMA50=120 -> 7.00%
        ext = _get_extension({"Price": 128.4, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "STRETCHED"

    def test_band_extended_for_12pct(self):
        """12% above SMA 50 -> EXTENDED."""
        ext = _get_extension({"Price": 134.4, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "EXTENDED"

    def test_band_overextended_for_17pct(self):
        """17% above SMA 50 -> OVEREXTENDED."""
        ext = _get_extension({"Price": 140.4, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "OVEREXTENDED"

    def test_band_significantly_overextended_for_23pct(self):
        """23% above SMA 50 -> SIGNIFICANTLY_OVEREXTENDED.
        Matches the GLW manual-test scenario (23.4% reading)."""
        ext = _get_extension({"Price": 147.6, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "SIGNIFICANTLY_OVEREXTENDED"

    def test_band_blow_off_zone_for_35pct(self):
        """35% above SMA 50 -> BLOW_OFF_ZONE."""
        ext = _get_extension({"Price": 162.0, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "BLOW_OFF_ZONE"

    # ---- Boundary cases ----

    def test_band_boundary_at_exactly_5pct(self):
        """Exactly 5% (boundary) -> STRETCHED (5 to 10% band starts at 5).
        The conditional is `if pct < 5.0`, so 5.0 itself enters STRETCHED."""
        # Price=126, SMA50=120 -> exactly 5.00%
        ext = _get_extension({"Price": 126.0, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "STRETCHED"

    def test_band_boundary_at_exactly_20pct(self):
        """Exactly 20% (boundary) -> SIGNIFICANTLY_OVEREXTENDED."""
        ext = _get_extension({"Price": 144.0, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "SIGNIFICANTLY_OVEREXTENDED"

    def test_band_boundary_at_exactly_30pct(self):
        """Exactly 30% (boundary) -> BLOW_OFF_ZONE."""
        ext = _get_extension({"Price": 156.0, "Context_Daily_SMA50": 120.0})
        assert ext["medium_term"]["interpretation"]["label"] == "BLOW_OFF_ZONE"

    # ---- Scope guards (parallel to existing PCT-001 tests) ----

    def test_profile_b_medium_term_unchanged_no_interpretation_field(self):
        """Profile B medium_term retains its 4-key shape (distance, anchor,
        condition, thresholds) WITHOUT an interpretation field -- the new
        field is Profile A only. Profile B's `condition` already serves the
        interpretation role with research-grounded thresholds."""
        ext = _get_extension(_profile_b_overrides())
        mt = ext["medium_term"]
        assert "interpretation" not in mt, (
            "Profile B medium_term should NOT have an interpretation field "
            "(its condition field with research-grounded thresholds already "
            "serves the interpretation role)"
        )
        # Profile B's full shape still present
        assert "distance" in mt
        assert "anchor" in mt
        assert "condition" in mt
        assert "thresholds" in mt

    def test_profile_c_no_medium_term_no_interpretation(self):
        """Profile C: medium_term is None entirely (DQ-7 scope guard).
        No interpretation to derive."""
        ext = _get_extension(_profile_c_overrides())
        assert ext.get("medium_term") is None

    def test_interpretation_desc_is_actionable_one_liner(self):
        """Each interpretation.desc is a short, actionable one-liner --
        not a multi-paragraph essay. Sanity check: < 200 chars."""
        ext = _get_extension()
        desc = ext["medium_term"]["interpretation"]["desc"]
        assert len(desc) < 200, (
            f"interpretation.desc too long ({len(desc)} chars) -- should "
            f"be a short actionable one-liner"
        )

    def test_helper_returns_none_tuple_for_none_input(self):
        """_derive_medium_term_interpretation(None) returns (None, None).
        Defensive null-path verified at the helper level."""
        lbl, desc = _transform_mod._derive_medium_term_interpretation(None)
        assert lbl is None
        assert desc is None
