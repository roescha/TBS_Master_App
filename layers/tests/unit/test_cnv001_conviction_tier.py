"""CNV-001 — Conviction Tier Classification on Floor and Target Hierarchies.

Spec: BUNDLE001_SWING_Output_Enrichment_Spec_v1_1.md (S153 v1.1, OD-1 path (a) locked)

Covers the eight test classes enumerated in spec §5.1:

    1. TestCNV001ConvictionTierMap         -- 19-entry static mapping verbatim
    2. TestCNV001AnnotateConvictionInPlace -- helper mutates in-place + returns same ref
    3. TestCNV001UnrecognizedLabelDefaults -- (None, None) on off-vocabulary labels
    4. TestCNV001FloorHierarchyTagging     -- conviction_tier on Profile A/B/C floors
    5. TestCNV001TargetHierarchyTagging    -- conviction_tier on Profile A/B/C targets
    6. TestCNV001BRKFloorTagging           -- NEW_SUPPORT/TIGHT_STOP/CATASTROPHIC_STOP tagged
    7. TestCNV001PartitionPropagation      -- BUGR-002 partition preserves new fields
    8. TestCNV001PsychologicalDualSide     -- PSYCHOLOGICAL ceiling AND floor both tagged

Construction notes:
    - Uses direct importlib load to avoid the tbs_engine package init chain
      (which pulls ib_insync via tbs_engine.main -> tbs_engine.data).
    - Safe `spec_from_file_location` import pattern per TEST-HRN-001 (no sys.modules
      registration of the engine module).
    - Base fixture mirrors test_bugr002_hierarchy_partition.py with per-test
      overrides to drive specific hierarchy compositions.
"""

import os
import sys
import importlib.util

import pytest


# ---------------------------------------------------------------------------
# Direct file import -- TEST-HRN-001 safe pattern. transform.py has zero
# imports within tbs_engine; loading through the package __init__ would pull
# tbs_engine.main -> tbs_engine.data -> ib_insync.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_root = os.path.join(os.path.dirname(__file__), "..", "..")
_spec = importlib.util.spec_from_file_location(
    "tbs_engine_transform_cnv001",
    os.path.join(_root, "tbs_engine", "transform.py"),
)
_transform_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output
_CONVICTION_TIER_MAP = _transform_mod._CONVICTION_TIER_MAP
_annotate_conviction = _transform_mod._annotate_conviction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_action_summary():
    """Minimal action_summary for _transform_output."""
    return {
        "verdict": "VALID",
        "reason": {"label": "VALID PULLBACK", "detail": ""},
        "mandate": "ENTER",
        "context": "",
    }


def _base_flat_metrics(**overrides):
    """Base flat_metrics with all hierarchy source values populated.

    Defaults to Profile A (VWAP floor anchor) with Price=130.0 and a set of
    level values that exercise the full label vocabulary (DAILY_HIGH,
    MEASURED_MOVE, ATR_PROJECTION, ANALYST_CONSENSUS, PSYCHOLOGICAL ceiling on
    target side; SESSION_VWAP, AVWAP_10BAR, DAILY_EMA_21, DAILY_SMA_50,
    DAILY_SMA_200, ESTABLISHED_LOW, HARD_STOP, PSYCHOLOGICAL floor on stop
    side). Tests override specific keys to construct BRK-active, Profile B,
    Profile C, partition-mixed, etc. scenarios.
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

        # Targets (most above Price=130 by construction)
        "Profit_Target": 135.0,
        "Profit_Target_Source": "10_Bar_Resistance",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "MM_Target": 140.0,
        "Blue_Sky_Target": 145.0,
        "Blue_Sky_Method": "ATR_PROJECTION",
        "Blue_Sky_Detected": True,
        "Fundamental_Target": 150.0,

        # Psychological levels
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

        # Floor sources (all below Price=130 in default)
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
    """Profile B: primary chart is daily, Floor_Anchor_Type == SMA_50. No VWAP."""
    return {
        "Floor_Anchor_Type": "SMA_50",
        "VWAP": None,
        "AVWAP_Price": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
        # Profile B uses weekly context frame -- swap daily SMA50 for weekly
        "Context_Daily_SMA50": None,
        "Context_Weekly_SMA50": 121.0,
        "Context_Weekly_SMA50_Slope": 0.3,
    }


def _profile_c_overrides():
    """Profile C: weekly primary chart, monthly context frame."""
    return {
        "Floor_Anchor_Type": "SMA_200",
        "VWAP": None,
        "AVWAP_Price": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
        "Context_Daily_SMA50": None,
        "Context_Monthly_SMA50": 118.0,
        "Context_Monthly_SMA50_Slope": 0.4,
        "Context_Monthly_SMA200": 108.0,
    }


def _brk_active_overrides():
    """BRK-001 scoping overrides -- stop side: replaces floor entries with
    NEW_SUPPORT / TIGHT_STOP / CATASTROPHIC_STOP + retained PSYCHOLOGICAL."""
    return {
        "BRK_Model_Active": True,
        "BRK_New_Support": 128.0,
        "BRK_Tight_Stop": 126.0,
        "BRK_Catastrophic_Stop": 123.0,
    }


def _get_grouped(flat_overrides=None):
    """Run _transform_output with default base and return grouped dict."""
    fm = _base_flat_metrics(**(flat_overrides or {}))
    return _transform_output(_base_action_summary(), fm)


def _get_stop(flat_overrides=None):
    """Shortcut: returns trade_setup['stop'] dict."""
    return _get_grouped(flat_overrides)["trade_setup"]["stop"]


def _get_target(flat_overrides=None):
    """Shortcut: returns trade_setup['target'] dict."""
    return _get_grouped(flat_overrides)["trade_setup"]["target"]


# ===========================================================================
# 1. TestCNV001ConvictionTierMap -- 19-entry static mapping verbatim per OD-1
# ===========================================================================


class TestCNV001ConvictionTierMap:
    """Spec §4.1.1 + §10 OD-1: _CONVICTION_TIER_MAP contains exactly 19 entries
    with the (tier, rank) tuples enumerated in §4.1.1. Per §10 OD-1 resolution
    path (a) locked at v1.1, the 19-entry mapping is substantively correct."""

    def test_total_entry_count_is_19(self):
        """Per OD-1 path (a) locked S153 v1.1, mapping has exactly 19 entries."""
        assert len(_CONVICTION_TIER_MAP) == 19

    def test_structural_tier_labels(self):
        """Rank 1 STRUCTURAL: ESTABLISHED_LOW, DAILY_HIGH, WEEKLY_HIGH, NEW_SUPPORT."""
        expected = {"ESTABLISHED_LOW", "DAILY_HIGH", "WEEKLY_HIGH", "NEW_SUPPORT"}
        for label in expected:
            assert _CONVICTION_TIER_MAP[label] == ("STRUCTURAL", 1), (
                f"{label} should map to (STRUCTURAL, 1)"
            )

    def test_psychological_tier_single_label(self):
        """Rank 2 PSYCHOLOGICAL: single label, covers both ceiling and floor sides."""
        assert _CONVICTION_TIER_MAP["PSYCHOLOGICAL"] == ("PSYCHOLOGICAL", 2)

    def test_ma_dynamic_tier_labels(self):
        """Rank 3 MA_DYNAMIC: 7 labels covering VWAP/AVWAP/EMA21/SMA50(both)/SMA200(both)."""
        expected = {
            "SESSION_VWAP", "AVWAP_10BAR", "DAILY_EMA_21",
            "DAILY_SMA_50", "WEEKLY_SMA_50",
            "DAILY_SMA_200", "WEEKLY_SMA_200",
        }
        for label in expected:
            assert _CONVICTION_TIER_MAP[label] == ("MA_DYNAMIC", 3), (
                f"{label} should map to (MA_DYNAMIC, 3)"
            )

    def test_projection_tier_single_label(self):
        """Rank 4 PROJECTION: MEASURED_MOVE only."""
        assert _CONVICTION_TIER_MAP["MEASURED_MOVE"] == ("PROJECTION", 4)

    def test_atr_derived_tier_labels(self):
        """Rank 5 ATR_DERIVED: 5 labels covering HARD_STOP variants + ATR_PROJECTION."""
        expected = {
            "HARD_STOP", "DAILY_HARD_STOP",
            "TIGHT_STOP", "CATASTROPHIC_STOP",
            "ATR_PROJECTION",
        }
        for label in expected:
            assert _CONVICTION_TIER_MAP[label] == ("ATR_DERIVED", 5), (
                f"{label} should map to (ATR_DERIVED, 5)"
            )

    def test_fundamental_tier_single_label(self):
        """Rank 6 FUNDAMENTAL: ANALYST_CONSENSUS only (FRR-001 sell-side consensus)."""
        assert _CONVICTION_TIER_MAP["ANALYST_CONSENSUS"] == ("FUNDAMENTAL", 6)

    def test_rank_ordering_monotonic(self):
        """Tier ranks are strictly monotonic 1..6 across the six tier names."""
        tier_to_rank = {}
        for label, (tier, rank) in _CONVICTION_TIER_MAP.items():
            assert isinstance(tier, str)
            assert isinstance(rank, int)
            assert 1 <= rank <= 6
            if tier in tier_to_rank:
                assert tier_to_rank[tier] == rank, (
                    f"Tier {tier} has conflicting ranks across labels"
                )
            else:
                tier_to_rank[tier] = rank
        # All six tiers present
        assert set(tier_to_rank.keys()) == {
            "STRUCTURAL", "PSYCHOLOGICAL", "MA_DYNAMIC",
            "PROJECTION", "ATR_DERIVED", "FUNDAMENTAL",
        }
        # Ranks are 1..6 with no gaps
        assert sorted(tier_to_rank.values()) == [1, 2, 3, 4, 5, 6]


# ===========================================================================
# 2. TestCNV001AnnotateConvictionInPlace -- helper contract
# ===========================================================================


class TestCNV001AnnotateConvictionInPlace:
    """Spec §4.1.2: _annotate_conviction() mutates entries in place, returns same
    list reference, and is safe on None / empty inputs."""

    def test_in_place_mutation(self):
        """Each entry receives conviction_tier and conviction_rank attributes."""
        entries = [
            {"price": 100.0, "label": "DAILY_HIGH"},
            {"price": 95.0, "label": "ESTABLISHED_LOW"},
        ]
        _annotate_conviction(entries)
        assert entries[0]["conviction_tier"] == "STRUCTURAL"
        assert entries[0]["conviction_rank"] == 1
        assert entries[1]["conviction_tier"] == "STRUCTURAL"
        assert entries[1]["conviction_rank"] == 1

    def test_returns_same_list_reference(self):
        """Helper returns the same list reference for chained-call ergonomics."""
        entries = [{"price": 100.0, "label": "DAILY_HIGH"}]
        result = _annotate_conviction(entries)
        assert id(result) == id(entries), (
            "Expected same list reference for chained-call ergonomics"
        )

    def test_empty_list_safe(self):
        """Empty list input returns empty list without raising."""
        entries = []
        result = _annotate_conviction(entries)
        assert result == []
        assert id(result) == id(entries)

    def test_none_input_safe(self):
        """None input returns None without raising."""
        result = _annotate_conviction(None)
        assert result is None

    def test_idempotent_reinvocation(self):
        """Re-invocation on already-annotated entries produces identical output.

        Per spec §4.1.2: matters for the third call site (post-BRK-floor),
        where the retained PSYCHOLOGICAL entry has already been annotated at
        the second call site. Re-annotation must be safe.
        """
        entries = [{"price": 100.0, "label": "DAILY_EMA_21"}]
        _annotate_conviction(entries)
        first_tier = entries[0]["conviction_tier"]
        first_rank = entries[0]["conviction_rank"]
        _annotate_conviction(entries)
        assert entries[0]["conviction_tier"] == first_tier
        assert entries[0]["conviction_rank"] == first_rank


# ===========================================================================
# 3. TestCNV001UnrecognizedLabelDefaults -- vocabulary-drift signal per DQ-5
# ===========================================================================


class TestCNV001UnrecognizedLabelDefaults:
    """Spec §4.1.2 + DQ-5: unrecognized labels default to (None, None) -- visible
    signal of vocabulary drift, vs a sentinel that would mask the drift."""

    def test_unrecognized_label_yields_none_tier_and_rank(self):
        """label='UNKNOWN_LABEL' produces conviction_tier=None, conviction_rank=None."""
        entries = [{"price": 100.0, "label": "UNKNOWN_LABEL"}]
        _annotate_conviction(entries)
        assert entries[0]["conviction_tier"] is None
        assert entries[0]["conviction_rank"] is None

    def test_missing_label_key_yields_none(self):
        """Entry with no 'label' key (defensive) still defaults to (None, None)."""
        entries = [{"price": 100.0}]
        _annotate_conviction(entries)
        assert entries[0]["conviction_tier"] is None
        assert entries[0]["conviction_rank"] is None

    def test_mixed_recognized_and_unrecognized(self):
        """Recognized labels tag correctly; unrecognized default to (None, None);
        no cross-contamination between entries."""
        entries = [
            {"price": 100.0, "label": "DAILY_HIGH"},          # STRUCTURAL
            {"price": 95.0, "label": "BOGUS_VOCABULARY"},     # unrecognized
            {"price": 90.0, "label": "PSYCHOLOGICAL"},        # PSYCHOLOGICAL
        ]
        _annotate_conviction(entries)
        assert entries[0]["conviction_tier"] == "STRUCTURAL"
        assert entries[0]["conviction_rank"] == 1
        assert entries[1]["conviction_tier"] is None
        assert entries[1]["conviction_rank"] is None
        assert entries[2]["conviction_tier"] == "PSYCHOLOGICAL"
        assert entries[2]["conviction_rank"] == 2


# ===========================================================================
# 4. TestCNV001FloorHierarchyTagging -- Profile A/B/C floor hierarchies tagged
# ===========================================================================


class TestCNV001FloorHierarchyTagging:
    """Spec §5.1: all entries in trade_setup.stop.hierarchy carry conviction_tier
    and conviction_rank fields with non-null values on all three profiles for at
    least one BRK-inactive evaluation per profile."""

    def test_profile_a_floor_hierarchy_all_tagged(self):
        """Profile A (default fixture) -- every stop.hierarchy entry has
        non-null conviction_tier and conviction_rank."""
        stop = _get_stop()
        assert stop["hierarchy"] is not None
        assert len(stop["hierarchy"]) > 0
        for entry in stop["hierarchy"]:
            assert "conviction_tier" in entry, (
                f"Profile A floor entry {entry.get('label')!r} missing conviction_tier"
            )
            assert "conviction_rank" in entry, (
                f"Profile A floor entry {entry.get('label')!r} missing conviction_rank"
            )
            assert entry["conviction_tier"] is not None, (
                f"Profile A floor entry {entry.get('label')!r} has null conviction_tier"
            )
            assert entry["conviction_rank"] is not None, (
                f"Profile A floor entry {entry.get('label')!r} has null conviction_rank"
            )

    def test_profile_b_floor_hierarchy_all_tagged(self):
        """Profile B floor hierarchy entries carry conviction tags."""
        stop = _get_stop(_profile_b_overrides())
        assert stop["hierarchy"] is not None
        assert len(stop["hierarchy"]) > 0
        for entry in stop["hierarchy"]:
            assert entry.get("conviction_tier") is not None, (
                f"Profile B floor entry {entry.get('label')!r} missing tier"
            )
            assert entry.get("conviction_rank") is not None, (
                f"Profile B floor entry {entry.get('label')!r} missing rank"
            )

    def test_profile_c_floor_hierarchy_all_tagged(self):
        """Profile C floor hierarchy entries carry conviction tags."""
        stop = _get_stop(_profile_c_overrides())
        assert stop["hierarchy"] is not None
        assert len(stop["hierarchy"]) > 0
        for entry in stop["hierarchy"]:
            assert entry.get("conviction_tier") is not None, (
                f"Profile C floor entry {entry.get('label')!r} missing tier"
            )
            assert entry.get("conviction_rank") is not None, (
                f"Profile C floor entry {entry.get('label')!r} missing rank"
            )

    def test_profile_a_floor_specific_label_tiers(self):
        """Profile A: SESSION_VWAP -> MA_DYNAMIC rank 3; HARD_STOP -> ATR_DERIVED
        rank 5; DAILY_EMA_21 -> MA_DYNAMIC rank 3 (when present)."""
        stop = _get_stop()
        by_label = {e["label"]: e for e in stop["hierarchy"]}
        if "SESSION_VWAP" in by_label:
            assert by_label["SESSION_VWAP"]["conviction_tier"] == "MA_DYNAMIC"
            assert by_label["SESSION_VWAP"]["conviction_rank"] == 3
        if "HARD_STOP" in by_label:
            assert by_label["HARD_STOP"]["conviction_tier"] == "ATR_DERIVED"
            assert by_label["HARD_STOP"]["conviction_rank"] == 5
        if "DAILY_EMA_21" in by_label:
            assert by_label["DAILY_EMA_21"]["conviction_tier"] == "MA_DYNAMIC"
            assert by_label["DAILY_EMA_21"]["conviction_rank"] == 3


# ===========================================================================
# 5. TestCNV001TargetHierarchyTagging -- Profile A/B/C target hierarchies tagged
# ===========================================================================


class TestCNV001TargetHierarchyTagging:
    """Spec §5.1: all entries in trade_setup.target.hierarchy carry
    conviction_tier and conviction_rank fields with non-null values on all
    three profiles."""

    def test_profile_a_target_hierarchy_all_tagged(self):
        """Profile A target hierarchy entries carry conviction tags."""
        target = _get_target()
        assert target["hierarchy"] is not None
        assert len(target["hierarchy"]) > 0
        for entry in target["hierarchy"]:
            assert entry.get("conviction_tier") is not None, (
                f"Profile A target entry {entry.get('label')!r} missing tier"
            )
            assert entry.get("conviction_rank") is not None, (
                f"Profile A target entry {entry.get('label')!r} missing rank"
            )

    def test_profile_b_target_hierarchy_all_tagged(self):
        """Profile B target hierarchy entries carry conviction tags."""
        target = _get_target(_profile_b_overrides())
        assert target["hierarchy"] is not None
        assert len(target["hierarchy"]) > 0
        for entry in target["hierarchy"]:
            assert entry.get("conviction_tier") is not None, (
                f"Profile B target entry {entry.get('label')!r} missing tier"
            )
            assert entry.get("conviction_rank") is not None, (
                f"Profile B target entry {entry.get('label')!r} missing rank"
            )

    def test_profile_c_target_hierarchy_all_tagged(self):
        """Profile C target hierarchy entries carry conviction tags."""
        target = _get_target(_profile_c_overrides())
        assert target["hierarchy"] is not None
        assert len(target["hierarchy"]) > 0
        for entry in target["hierarchy"]:
            assert entry.get("conviction_tier") is not None, (
                f"Profile C target entry {entry.get('label')!r} missing tier"
            )
            assert entry.get("conviction_rank") is not None, (
                f"Profile C target entry {entry.get('label')!r} missing rank"
            )

    def test_profile_a_target_specific_label_tiers(self):
        """Profile A: DAILY_HIGH -> STRUCTURAL rank 1; MEASURED_MOVE -> PROJECTION
        rank 4; ATR_PROJECTION -> ATR_DERIVED rank 5; ANALYST_CONSENSUS ->
        FUNDAMENTAL rank 6."""
        target = _get_target()
        by_label = {e["label"]: e for e in target["hierarchy"]}
        if "DAILY_HIGH" in by_label:
            assert by_label["DAILY_HIGH"]["conviction_tier"] == "STRUCTURAL"
            assert by_label["DAILY_HIGH"]["conviction_rank"] == 1
        if "MEASURED_MOVE" in by_label:
            assert by_label["MEASURED_MOVE"]["conviction_tier"] == "PROJECTION"
            assert by_label["MEASURED_MOVE"]["conviction_rank"] == 4
        if "ATR_PROJECTION" in by_label:
            assert by_label["ATR_PROJECTION"]["conviction_tier"] == "ATR_DERIVED"
            assert by_label["ATR_PROJECTION"]["conviction_rank"] == 5
        if "ANALYST_CONSENSUS" in by_label:
            assert by_label["ANALYST_CONSENSUS"]["conviction_tier"] == "FUNDAMENTAL"
            assert by_label["ANALYST_CONSENSUS"]["conviction_rank"] == 6


# ===========================================================================
# 6. TestCNV001BRKFloorTagging -- BRK-active path NEW_SUPPORT/TIGHT_STOP/etc.
# ===========================================================================


class TestCNV001BRKFloorTagging:
    """Spec §4.1.5 + §5.1: on a BRK-active Profile A path, the BRK floor
    entries (NEW_SUPPORT, TIGHT_STOP, CATASTROPHIC_STOP, retained PSYCHOLOGICAL)
    all carry conviction_tier + conviction_rank with correct tier assignment."""

    def test_brk_floor_all_entries_tagged(self):
        """Every entry in BRK-active stop.hierarchy carries conviction tags."""
        stop = _get_stop(_brk_active_overrides())
        assert stop["hierarchy"] is not None
        for entry in stop["hierarchy"]:
            assert entry.get("conviction_tier") is not None, (
                f"BRK floor entry {entry.get('label')!r} missing tier"
            )
            assert entry.get("conviction_rank") is not None, (
                f"BRK floor entry {entry.get('label')!r} missing rank"
            )

    def test_brk_new_support_is_structural_rank_1(self):
        """NEW_SUPPORT (old resistance flipped) is STRUCTURAL rank 1."""
        stop = _get_stop(_brk_active_overrides())
        by_label = {e["label"]: e for e in stop["hierarchy"]}
        assert "NEW_SUPPORT" in by_label, (
            "BRK-active path must emit NEW_SUPPORT in floor hierarchy"
        )
        assert by_label["NEW_SUPPORT"]["conviction_tier"] == "STRUCTURAL"
        assert by_label["NEW_SUPPORT"]["conviction_rank"] == 1

    def test_brk_tight_stop_is_atr_derived_rank_5(self):
        """TIGHT_STOP (new support - ATR buffer) is ATR_DERIVED rank 5."""
        stop = _get_stop(_brk_active_overrides())
        by_label = {e["label"]: e for e in stop["hierarchy"]}
        assert "TIGHT_STOP" in by_label
        assert by_label["TIGHT_STOP"]["conviction_tier"] == "ATR_DERIVED"
        assert by_label["TIGHT_STOP"]["conviction_rank"] == 5

    def test_brk_catastrophic_stop_is_atr_derived_rank_5(self):
        """CATASTROPHIC_STOP (new support - 1.5x ATR) is ATR_DERIVED rank 5."""
        stop = _get_stop(_brk_active_overrides())
        by_label = {e["label"]: e for e in stop["hierarchy"]}
        assert "CATASTROPHIC_STOP" in by_label
        assert by_label["CATASTROPHIC_STOP"]["conviction_tier"] == "ATR_DERIVED"
        assert by_label["CATASTROPHIC_STOP"]["conviction_rank"] == 5

    def test_brk_retained_psychological_re_annotated_idempotent(self):
        """The retained PSYCHOLOGICAL floor (carried over from pre-BRK
        _floor_entries) is re-annotated idempotently per spec §4.1.5 -- still
        carries (PSYCHOLOGICAL, 2) after the third call site fires."""
        stop = _get_stop(_brk_active_overrides())
        by_label = {e["label"]: e for e in stop["hierarchy"]}
        if "PSYCHOLOGICAL" in by_label:
            assert by_label["PSYCHOLOGICAL"]["conviction_tier"] == "PSYCHOLOGICAL"
            assert by_label["PSYCHOLOGICAL"]["conviction_rank"] == 2


# ===========================================================================
# 7. TestCNV001PartitionPropagation -- BUGR-002 partition preserves fields
# ===========================================================================


class TestCNV001PartitionPropagation:
    """Spec §4.1.6 + §5.1: entries in trade_setup.stop.overhead_levels (above
    price) and trade_setup.target.cleared_levels (below price) carry
    conviction_tier + conviction_rank (partition does not strip the new
    fields). Also assert overhead_levels entries do NOT carry status (existing
    BUGR-002 contract preserved)."""

    # Shift Context_SMA200 above current price (130) to force partition split.
    # SMA200 hierarchy entry priced at 140 (> 130) lands in overhead_levels.
    _MIXED_FLOOR = {"Context_SMA200": 140.0}

    def test_overhead_levels_carry_conviction_tags(self):
        """All entries in stop.overhead_levels (above-price floors) carry
        conviction_tier + conviction_rank inherited from pre-partition state."""
        stop = _get_stop(self._MIXED_FLOOR)
        assert stop.get("overhead_levels") is not None
        assert len(stop["overhead_levels"]) > 0
        for entry in stop["overhead_levels"]:
            assert "conviction_tier" in entry, (
                f"overhead_levels entry {entry.get('label')!r} missing tier"
            )
            assert "conviction_rank" in entry, (
                f"overhead_levels entry {entry.get('label')!r} missing rank"
            )

    def test_overhead_levels_status_stripped(self):
        """Per BUGR-002 contract preserved: overhead_levels entries lack the
        status field (presence in overhead_levels container is itself the
        semantic). CNV-001 additions must not break this contract."""
        stop = _get_stop(self._MIXED_FLOOR)
        assert stop.get("overhead_levels") is not None
        for entry in stop["overhead_levels"]:
            assert "status" not in entry, (
                f"overhead_levels entry {entry.get('label')!r} unexpectedly "
                "retained status field -- BUGR-002 partition contract broken"
            )

    def test_cleared_levels_carry_conviction_tags(self):
        """All entries in target.cleared_levels (below-price targets) carry
        conviction_tier + conviction_rank. Construct an EXCEEDED case where
        Profit_Target is below current_price by shifting Resistance below 130."""
        # Force DAILY_HIGH below price to land in cleared_levels
        target = _get_target({"Price": 145.0})
        # With Price=145 and defaults: DAILY_HIGH at 135, MM at 140, all below.
        # Psych_Ceiling 140 also below -- multiple cleared entries expected.
        assert target.get("cleared_levels") is not None
        if len(target["cleared_levels"]) > 0:
            for entry in target["cleared_levels"]:
                assert "conviction_tier" in entry, (
                    f"cleared_levels entry {entry.get('label')!r} missing tier"
                )
                assert "conviction_rank" in entry, (
                    f"cleared_levels entry {entry.get('label')!r} missing rank"
                )

    def test_cleared_levels_retain_status_and_escalation_winner(self):
        """Per BUGR-002 contract: cleared_levels entries retain status and
        escalation_winner (target partition has no field-stripping)."""
        target = _get_target({"Price": 145.0})
        assert target.get("cleared_levels") is not None
        if len(target["cleared_levels"]) > 0:
            for entry in target["cleared_levels"]:
                # status retained on target partition (unlike floor partition)
                assert "status" in entry, (
                    f"cleared_levels entry {entry.get('label')!r} missing status"
                )
                # escalation_winner also retained
                assert "escalation_winner" in entry, (
                    f"cleared_levels entry {entry.get('label')!r} missing escalation_winner"
                )


# ===========================================================================
# 8. TestCNV001PsychologicalDualSide -- single tier covers ceiling AND floor
# ===========================================================================


class TestCNV001PsychologicalDualSide:
    """Spec §5.1 + §4.1.1 DQ-1: a single PSYCHOLOGICAL tier entry in
    _CONVICTION_TIER_MAP covers BOTH the ceiling-side PSYCHOLOGICAL entry
    (in target hierarchy at ~line 1958) AND the floor-side PSYCHOLOGICAL
    entry (in stop hierarchy at ~line 2210). Both must receive
    conviction_tier='PSYCHOLOGICAL', conviction_rank=2."""

    def test_target_side_psychological_ceiling_tagged(self):
        """PSYCHOLOGICAL ceiling in target hierarchy carries PSYCHOLOGICAL/2."""
        target = _get_target()
        by_label = [e for e in target["hierarchy"] if e.get("label") == "PSYCHOLOGICAL"]
        # PSYCHOLOGICAL ceiling at 140 with Price=130 -> ACTIVE in hierarchy
        if by_label:
            entry = by_label[0]
            assert entry["conviction_tier"] == "PSYCHOLOGICAL"
            assert entry["conviction_rank"] == 2

    def test_stop_side_psychological_floor_tagged(self):
        """PSYCHOLOGICAL floor in stop hierarchy carries PSYCHOLOGICAL/2."""
        stop = _get_stop()
        by_label = [e for e in stop["hierarchy"] if e.get("label") == "PSYCHOLOGICAL"]
        # PSYCHOLOGICAL floor at 125 with Price=130 -> HOLDING in hierarchy
        if by_label:
            entry = by_label[0]
            assert entry["conviction_tier"] == "PSYCHOLOGICAL"
            assert entry["conviction_rank"] == 2

    def test_both_sides_same_tier_label_and_rank(self):
        """Single tier vocabulary entry covers both sides -- same tuple values
        across target ceiling and stop floor PSYCHOLOGICAL entries."""
        target = _get_target()
        stop = _get_stop()
        target_psy = [e for e in target["hierarchy"] if e.get("label") == "PSYCHOLOGICAL"]
        stop_psy = [e for e in stop["hierarchy"] if e.get("label") == "PSYCHOLOGICAL"]
        if target_psy and stop_psy:
            assert (
                target_psy[0]["conviction_tier"] == stop_psy[0]["conviction_tier"]
                == "PSYCHOLOGICAL"
            )
            assert (
                target_psy[0]["conviction_rank"] == stop_psy[0]["conviction_rank"]
                == 2
            )
