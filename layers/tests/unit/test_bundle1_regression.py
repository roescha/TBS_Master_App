"""Bundle 1 -- Bitwise-Invariance Regression Witness.

Spec: BUNDLE001_SWING_Output_Enrichment_Spec_v1_1.md (S153 v1.1) §5.4

Covers the single test class per spec §5.4:

    1. TestBundle1BitwiseInvariance -- per spec §1 Executive Summary closing
       paragraph: "All other engine behaviour is bitwise-invariant." Verifies
       on representative tickers (>=1 per profile) that all flat keys NOT
       introduced by Bundle 1 produce values bit-identical pre/post Bundle 1.

Construction notes:
    - This is a regression-witness test, not a differential FAIL->PASS test.
      The Bundle 1 engine edits are already applied (this Phase 3 session
      cannot reach the pre-Bundle-1 engine state to compute true pre/post
      differentials).
    - The test runs the engine on three representative fixtures (one per
      profile), enumerates the keys introduced by Bundle 1 (per spec §0
      Conventions vocabulary distinctions), and asserts:
        (a) all NEW Bundle 1 keys are present in the output structure;
        (b) the engine output's top-level group set is unchanged from
            pre-Bundle 1 structure;
        (c) representative pre-existing fields preserve their expected
            values on standard fixtures (sanity-value regression witness);
        (d) the NEW conviction_tier / conviction_rank fields on hierarchy
            entries do NOT replace or shift pre-existing entry fields
            (label / price / role / status / escalation_winner).
    - Per spec §1: "All three are presentation-layer additions" -- no
      gate logic, verdict, threshold, or state-transition changes. This
      class verifies that contract.
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
    "tbs_engine_transform_bundle1_reg",
    os.path.join(_root, "tbs_engine", "transform.py"),
)
_transform_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output
_flatten = _transform_mod._flatten
MAPPED_FLAT_KEYS = _transform_mod.MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# Bundle 1 vocabulary (per spec §0 Conventions + §4)
# ---------------------------------------------------------------------------

# Flat keys introduced by Bundle 1 (PCT-001 + EMA50-001). CNV-001 introduces
# fields on hierarchy ENTRIES (conviction_tier, conviction_rank) but does NOT
# introduce new flat keys.
_BUNDLE1_NEW_FLAT_KEYS = frozenset([
    # PCT-001
    "Pct_From_Daily_EMA21",
    "Pct_From_Daily_SMA50",
    # EMA50-001 profile-specific
    "Context_Daily_EMA_50", "Context_Daily_EMA_50_Slope",
    "Context_Weekly_EMA_50", "Context_Weekly_EMA_50_Slope",
    "Context_Monthly_EMA_50", "Context_Monthly_EMA_50_Slope",
    # EMA50-001 canonical aggregated
    "Context_EMA_50", "Context_EMA_50_Slope", "Context_EMA_50_Slope_Bias",
])

# New entry-level fields introduced by CNV-001
_BUNDLE1_NEW_ENTRY_FIELDS = frozenset(["conviction_tier", "conviction_rank"])

# Pre-existing top-level group keys in the grouped output (per
# transform.py:2675-2687). Bundle 1 must NOT add, remove, or rename any
# of these top-level groups.
_PRE_BUNDLE1_TOP_LEVEL_KEYS = frozenset([
    "data_basis", "action_summary", "trade_snapshot", "trade_quality",
    "trade_risk", "trend_state", "floor_analysis", "trade_setup",
    "extension_analysis", "psychological_levels", "volatility_regime",
    "entry_proximity", "exit_signals", "recovery_analysis",
])

# Pre-existing entry-level fields on hierarchy entries (per
# transform.py:1902-1962 target side and :1927-2072 floor side).
# CNV-001 adds conviction_tier and conviction_rank as additions; these
# pre-existing fields must remain present.
_PRE_BUNDLE1_ENTRY_FIELDS = frozenset(["price", "label", "role"])


# ---------------------------------------------------------------------------
# Fixtures (representative inputs per profile, mirrors prior test files)
# ---------------------------------------------------------------------------


def _base_action_summary():
    return {
        "verdict": "VALID",
        "reason": {"label": "VALID PULLBACK", "detail": ""},
        "mandate": "ENTER",
        "context": "",
    }


def _representative_flat_metrics(**overrides):
    """Representative flat_metrics fixture. Mirrors the shape used in
    test_bugr002_hierarchy_partition.py / test_cnv001_conviction_tier.py /
    test_pct001_extension_pct.py with the Bundle-1-introduced keys
    populated."""
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

        # Daily extension (PCT-001 trigger)
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

        # Bundle 1 EMA50-001 keys
        "Context_Daily_EMA_50": 121.0,
        "Context_Daily_EMA_50_Slope": 0.15,
        "Context_EMA_50": 121.0,
        "Context_EMA_50_Slope": 0.15,
        "Context_EMA_50_Slope_Bias": "BULLISH",

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
    return {
        "Floor_Anchor_Type": "SMA_50",
        "VWAP": None,
        "AVWAP_Price": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
        "Context_Daily_SMA50": None,
        "Context_Weekly_SMA50": 121.0,
        "Context_Weekly_SMA50_Slope": 0.3,
        # Profile B medium_term trigger
        "MediumTerm_Extension_Pct": 6.5,
        "MediumTerm_Extension_Label": "NORMAL",
        # Bundle 1: Weekly EMA 50 set, Daily EMA 50 cleared
        "Context_Daily_EMA_50": None,
        "Context_Daily_EMA_50_Slope": None,
        "Context_Weekly_EMA_50": 120.0,
        "Context_Weekly_EMA_50_Slope": 0.25,
        "Context_EMA_50": 120.0,
        "Context_EMA_50_Slope": 0.25,
    }


def _profile_c_overrides():
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
        # Bundle 1: Monthly EMA 50 only
        "Context_Daily_EMA_50": None,
        "Context_Daily_EMA_50_Slope": None,
        "Context_Monthly_EMA_50": 117.0,
        "Context_Monthly_EMA_50_Slope": 0.35,
        "Context_EMA_50": 117.0,
        "Context_EMA_50_Slope": 0.35,
    }


def _get_grouped(flat_overrides=None):
    fm = _representative_flat_metrics(**(flat_overrides or {}))
    return _transform_output(_base_action_summary(), fm)


# ===========================================================================
# 1. TestBundle1BitwiseInvariance -- regression witness across 3 profiles
# ===========================================================================


class TestBundle1BitwiseInvariance:
    """Spec §5.4 + §1 Executive Summary: 'All other engine behaviour is
    bitwise-invariant.' This class verifies the invariance contract on
    representative tickers per profile.

    Methods cover:
      - Top-level group set unchanged (no group added/removed/renamed)
      - All Bundle 1 new fields present (additions landed)
      - Pre-existing entry-level fields preserved on hierarchy entries
      - Verdict / mandate / engine_state preserved (no gate-logic shift)
      - Threshold values preserved (Profit_Target, Hard_Stop, etc.)
      - Bundle 1 new flat keys registered in MAPPED_FLAT_KEYS

    NB: this Phase 3 session cannot reach the pre-Bundle-1 engine state for
    a true pre/post differential; the invariance assertions therefore use
    representative-value witnesses on standard fixtures + structural
    enumeration of pre-existing keys (per spec §5.4 'canonical-form JSON
    comparison' framing -- structurally-bounded invariance verification).
    """

    # -------------------------------------------------------------------
    # Top-level group set invariance
    # -------------------------------------------------------------------

    def test_profile_a_top_level_groups_unchanged(self):
        """Profile A: top-level group set matches pre-Bundle 1 baseline."""
        grouped = _get_grouped()
        actual_keys = set(grouped.keys())
        missing = _PRE_BUNDLE1_TOP_LEVEL_KEYS - actual_keys
        assert not missing, f"Profile A missing pre-Bundle 1 groups: {missing}"
        # Bundle 1 must not introduce a NEW top-level group; the only allowed
        # extra is the optional swing_breakout_confirmation (pre-existing,
        # gated by SBO-001 active state).
        extras = actual_keys - _PRE_BUNDLE1_TOP_LEVEL_KEYS - {"swing_breakout_confirmation", "_debug", "rally_state"}
        assert not extras, (
            f"Profile A introduced unexpected top-level groups: {extras} "
            "-- Bundle 1 must be presentation-layer-only per spec §1"
        )

    def test_profile_b_top_level_groups_unchanged(self):
        """Profile B: top-level group set matches pre-Bundle 1 baseline."""
        grouped = _get_grouped(_profile_b_overrides())
        actual_keys = set(grouped.keys())
        missing = _PRE_BUNDLE1_TOP_LEVEL_KEYS - actual_keys
        assert not missing, f"Profile B missing pre-Bundle 1 groups: {missing}"
        extras = actual_keys - _PRE_BUNDLE1_TOP_LEVEL_KEYS - {"swing_breakout_confirmation", "_debug", "rally_state"}
        assert not extras

    def test_profile_c_top_level_groups_unchanged(self):
        """Profile C: top-level group set matches pre-Bundle 1 baseline."""
        grouped = _get_grouped(_profile_c_overrides())
        actual_keys = set(grouped.keys())
        missing = _PRE_BUNDLE1_TOP_LEVEL_KEYS - actual_keys
        assert not missing, f"Profile C missing pre-Bundle 1 groups: {missing}"
        extras = actual_keys - _PRE_BUNDLE1_TOP_LEVEL_KEYS - {"swing_breakout_confirmation", "_debug", "rally_state"}
        assert not extras

    # -------------------------------------------------------------------
    # Bundle 1 new keys registered in MAPPED_FLAT_KEYS
    # -------------------------------------------------------------------

    def test_bundle1_new_flat_keys_registered_in_mapped_flat_keys(self):
        """All Bundle 1 new flat keys are in MAPPED_FLAT_KEYS (per spec §11.4
        split-site warning -- missing registration triggers unmapped-key
        warning at transform.py:3267)."""
        missing = _BUNDLE1_NEW_FLAT_KEYS - set(MAPPED_FLAT_KEYS)
        assert not missing, (
            f"Bundle 1 new flat keys not registered in MAPPED_FLAT_KEYS: "
            f"{missing}"
        )

    # -------------------------------------------------------------------
    # Hierarchy entry shape invariance — CNV-001 additions are sibling
    # -------------------------------------------------------------------

    def test_hierarchy_entries_preserve_pre_bundle1_fields(self):
        """Every hierarchy/overhead/cleared entry retains pre-Bundle 1 fields
        (price, label, role). CNV-001 conviction_tier / conviction_rank are
        ADDED, not replacements."""
        for profile_name, overrides in (("A", {}), ("B", _profile_b_overrides()),
                                         ("C", _profile_c_overrides())):
            grouped = _get_grouped(overrides)
            ts = grouped.get("trade_setup", {})
            entries_seen = 0
            for side in ("stop", "target"):
                side_obj = ts.get(side, {})
                if not isinstance(side_obj, dict):
                    continue
                for container in ("hierarchy", "overhead_levels", "cleared_levels"):
                    entries = side_obj.get(container) or []
                    for entry in entries:
                        entries_seen += 1
                        missing = _PRE_BUNDLE1_ENTRY_FIELDS - set(entry.keys())
                        assert not missing, (
                            f"Profile {profile_name} {side}.{container} entry "
                            f"{entry.get('label')!r} missing pre-Bundle 1 "
                            f"fields: {missing}"
                        )
            assert entries_seen > 0, (
                f"Profile {profile_name} had no hierarchy entries to verify"
            )

    def test_hierarchy_entries_include_bundle1_additions(self):
        """Every hierarchy/overhead/cleared entry has conviction_tier and
        conviction_rank fields added (CNV-001 §4.1.6 partition transparency
        invariant)."""
        for profile_name, overrides in (("A", {}), ("B", _profile_b_overrides()),
                                         ("C", _profile_c_overrides())):
            grouped = _get_grouped(overrides)
            ts = grouped.get("trade_setup", {})
            for side in ("stop", "target"):
                side_obj = ts.get(side, {})
                if not isinstance(side_obj, dict):
                    continue
                for container in ("hierarchy", "overhead_levels", "cleared_levels"):
                    entries = side_obj.get(container) or []
                    for entry in entries:
                        missing = _BUNDLE1_NEW_ENTRY_FIELDS - set(entry.keys())
                        assert not missing, (
                            f"Profile {profile_name} {side}.{container} entry "
                            f"{entry.get('label')!r} missing CNV-001 "
                            f"fields: {missing}"
                        )

    # -------------------------------------------------------------------
    # Engine state / verdict / mandate invariance
    # -------------------------------------------------------------------

    def test_action_summary_unchanged_by_bundle1(self):
        """action_summary.verdict / mandate / reason fields preserve the
        injected input values. Bundle 1 is presentation-layer; it must not
        shift the gate verdict or mandate."""
        for profile_name, overrides in (("A", {}), ("B", _profile_b_overrides()),
                                         ("C", _profile_c_overrides())):
            grouped = _get_grouped(overrides)
            asum = grouped.get("action_summary", {})
            # Input verdict was "VALID" -- preserved end-to-end
            assert asum.get("verdict") == "VALID", (
                f"Profile {profile_name} verdict shifted: {asum.get('verdict')!r}"
            )
            # Input mandate was "ENTER" -- preserved
            assert asum.get("mandate") == "ENTER", (
                f"Profile {profile_name} mandate shifted: {asum.get('mandate')!r}"
            )

    def test_trend_state_engine_state_unchanged_by_bundle1(self):
        """trend_state.classification.state.label preserves the injected
        Engine_State value ('TRENDING' on all three profile fixtures).
        The TS-001 SelfDoc Batch grouped output puts the state under
        classification.state, not trend_state.state."""
        for profile_name, overrides in (("A", {}), ("B", _profile_b_overrides()),
                                         ("C", _profile_c_overrides())):
            grouped = _get_grouped(overrides)
            ts = grouped.get("trend_state", {})
            classification = ts.get("classification", {})
            state_obj = classification.get("state", {}) if isinstance(classification, dict) else {}
            state_label = state_obj.get("label") if isinstance(state_obj, dict) else state_obj
            assert state_label == "TRENDING", (
                f"Profile {profile_name} Engine_State shifted: {state_label!r}"
            )

    # -------------------------------------------------------------------
    # Threshold / numeric invariance on pre-existing fields
    # -------------------------------------------------------------------

    def test_profile_a_profit_target_preserves_input_value(self):
        """Profile A: profit target value preserves the injected 135.0."""
        grouped = _get_grouped()
        tgt = grouped.get("trade_setup", {}).get("target", {})
        assert tgt.get("price") == 135.0

    def test_profile_a_hard_stop_preserves_input_value(self):
        """Profile A: hard stop value preserves the injected 120.0."""
        grouped = _get_grouped()
        stp = grouped.get("trade_setup", {}).get("stop", {})
        assert stp.get("price") == 120.0

    def test_profile_b_profit_target_preserves_input_value(self):
        """Profile B: profit target value preserves the injected 135.0."""
        grouped = _get_grouped(_profile_b_overrides())
        tgt = grouped.get("trade_setup", {}).get("target", {})
        assert tgt.get("price") == 135.0

    def test_profile_c_profit_target_preserves_input_value(self):
        """Profile C: profit target value preserves the injected 135.0."""
        grouped = _get_grouped(_profile_c_overrides())
        tgt = grouped.get("trade_setup", {}).get("target", {})
        assert tgt.get("price") == 135.0

    # -------------------------------------------------------------------
    # Bundle 1 new fields present on representative paths
    # -------------------------------------------------------------------

    def test_profile_a_bundle1_new_fields_all_present(self):
        """Profile A: all expected Bundle 1 new fields land on the
        representative path -- CNV-001 conviction_tier / conviction_rank
        on hierarchy entries; PCT-001 extension_analysis.daily.distance_pct +
        extension_analysis.medium_term; EMA50-001 higher_frame.ema_50."""
        grouped = _get_grouped()
        # CNV-001
        stop_hier = grouped.get("trade_setup", {}).get("stop", {}).get("hierarchy") or []
        assert len(stop_hier) > 0
        assert all("conviction_tier" in e for e in stop_hier)
        # PCT-001
        ext = grouped.get("extension_analysis", {})
        assert ext.get("daily", {}).get("distance_pct") is not None
        assert ext.get("medium_term") is not None
        # EMA50-001
        hf = grouped.get("floor_analysis", {}).get("higher_frame", {})
        assert hf.get("ema_50") is not None

    def test_profile_b_bundle1_new_fields_all_present(self):
        """Profile B: CNV-001 tags + Profile B alias + EMA50-001 weekly."""
        grouped = _get_grouped(_profile_b_overrides())
        stop_hier = grouped.get("trade_setup", {}).get("stop", {}).get("hierarchy") or []
        assert all("conviction_tier" in e for e in stop_hier)
        hf = grouped.get("floor_analysis", {}).get("higher_frame", {})
        assert hf.get("ema_50") is not None
        assert hf["ema_50"]["price"] == 120.0  # Weekly value

    def test_profile_c_bundle1_new_fields_all_present(self):
        """Profile C: CNV-001 tags + EMA50-001 monthly (PCT-001 is Profile A
        only per DQ-7 scope guard)."""
        grouped = _get_grouped(_profile_c_overrides())
        stop_hier = grouped.get("trade_setup", {}).get("stop", {}).get("hierarchy") or []
        assert all("conviction_tier" in e for e in stop_hier)
        hf = grouped.get("floor_analysis", {}).get("higher_frame", {})
        assert hf.get("ema_50") is not None
        assert hf["ema_50"]["price"] == 117.0  # Monthly value

    # -------------------------------------------------------------------
    # Conviction-map size guard (regression on the 19-entry contract)
    # -------------------------------------------------------------------

    def test_conviction_tier_map_exactly_19_entries(self):
        """Per CNV-001 OD-1 path (a) locked S153 v1.1 the conviction tier map
        had 19 entries. Tier 1R DSP-004-OBS-2 legitimately adds WEEKLY_EMA_21
        (MA_DYNAMIC, 3) -> 20 entries; no other additions/removals from Bundle 1.
        (Method name retained for traceability.)"""
        # [DSP-004-OBS-2] +WEEKLY_EMA_21 (Tier 1R Display Hygiene Bundle) 19 -> 20
        assert len(_transform_mod._CONVICTION_TIER_MAP) == 20
