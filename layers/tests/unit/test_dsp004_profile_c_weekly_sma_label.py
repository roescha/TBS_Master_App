"""DSP-004 — Profile C Weekly Anchor Label tests.

Spec: DSP004_Profile_C_Weekly_Anchor_Label_Spec_v1_0.md (S150)

Covers the seven test cases enumerated in spec §6.2:

    TC-1  test_profile_c_sma50_label_is_weekly                   — primary fix (SMA 50 emits WEEKLY_SMA_50 on Profile C)
    TC-2  test_profile_c_sma200_label_is_weekly                  — primary fix (SMA 200 emits WEEKLY_SMA_200 on Profile C)
    TC-3  test_profile_c_sma50_label_desc_agree_on_timeframe     — label / desc timeframe agreement on Profile C SMA 50
    TC-4  test_profile_c_sma200_label_desc_agree_on_timeframe    — label / desc timeframe agreement on Profile C SMA 200
    TC-5  test_profile_a_sma50_unchanged                         — regression-witness: Profile A retains DAILY_SMA_50
    TC-6  test_profile_b_sma50_unchanged                         — regression-witness: Profile B retains DAILY_SMA_50
    TC-7  test_profile_c_overhead_levels_carries_weekly_label    — BUGR-002 partition cascade transparency

[DSP-004] Profile-aware label tier per PEO Open Decision #16 Option (a).

Construction notes:
    - Uses the safe `spec_from_file_location` direct-import pattern per
      TEST-HRN-001 (no `sys.modules` registration). Mirrors
      `test_bugr002_hierarchy_partition.py` and `test_pa001_phase3_hierarchies.py`.
    - Base fixture mirrors `test_bugr002_hierarchy_partition.py` shape with
      Floor_Anchor_Type-driven profile selection ("EMA_21" → A, "SMA_50" → B,
      "SMA_200" → C per transform.py:1911-1918).
    - Differential expectation per spec §6.3:
        * TC-1, TC-2, TC-3, TC-4, TC-7 FAIL pre-fix (emit DAILY_SMA_*)
        * TC-5, TC-6 PASS both pre-fix and post-fix (regression-invariant)
        * All seven PASS post-fix.
"""

import pytest
import sys
import os

# ---------------------------------------------------------------------------
# Direct file import — transform.py has zero imports within tbs_engine; loading
# through the package __init__ would pull tbs_engine.main → tbs_engine.data →
# ib_insync, which we don't need for a pure _transform_output test.
# (TEST-HRN-001 safe pattern — mirrors test_bugr002_hierarchy_partition.py)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import importlib.util

_root = os.path.join(os.path.dirname(__file__), "..", "..")
_spec = importlib.util.spec_from_file_location(
    "tbs_engine_transform",
    os.path.join(_root, "tbs_engine", "transform.py"),
)
_transform_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output


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

    Mirrors `test_bugr002_hierarchy_partition.py::_base_flat_metrics` shape.
    Defaults to Profile A (Floor_Anchor_Type=EMA_21) with Price=130.0 — i.e.
    the 'healthy setup' shape with all levels strictly below price. Tests
    override Floor_Anchor_Type, the relevant SMA values, and Price to construct
    Profile-specific scenarios.
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

        # Targets (all above Price=130)
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

        # Floor sources (defaults below Price=130)
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


def _profile_a_overrides():
    """Profile A: Floor_Anchor_Type in {VWAP, EMA_21}.

    Profile A reads Context_Daily_SMA50 (with SMA_50 fallback) for the SMA 50
    entry per transform.py:1973-1974. The base fixture already defaults to
    EMA_21, so this is effectively the no-op shape — present here for clarity
    in the regression-witness test cases.
    """
    return {
        "Floor_Anchor_Type": "EMA_21",
    }


def _profile_b_overrides():
    """Profile B: Floor_Anchor_Type == SMA_50.

    Mirrors `test_bugr002_hierarchy_partition.py::_profile_b_overrides`.
    Profile B's primary chart is daily; no VWAP. DAILY_HARD_STOP is guarded
    out via Daily_Hard_Stop=0.0 (BUGR-001 > 0 guard).
    """
    return {
        "Floor_Anchor_Type": "SMA_50",
        "VWAP": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
    }


def _profile_c_overrides():
    """Profile C: Floor_Anchor_Type == SMA_200.

    Profile C's primary chart is weekly per PA-001; the SMA values in
    flat_metrics carry the weekly-frame computation. Profile C reads SMA_50
    and SMA_200 directly (no Context_* fallback). Mirrors the
    `_profile_b_overrides` precedent shape.
    """
    return {
        "Floor_Anchor_Type": "SMA_200",
        "VWAP": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
    }


def _all_floor_entries(stop):
    """Return concatenation of hierarchy + overhead_levels (label-bearing
    entries only). Useful for regression-witness assertions that don't care
    about which side of the partition the entry landed on."""
    entries = []
    for key in ("hierarchy", "overhead_levels"):
        v = stop.get(key)
        if v:
            entries.extend(v)
    return entries


def _labels(entries):
    """Convenience: extract the 'label' string from each entry."""
    return [e.get("label") for e in entries]


def _entries_with_label(entries, label):
    """Filter entries to those matching the given label."""
    return [e for e in entries if e.get("label") == label]


# ===========================================================================
# TestDSP004ProfileCWeeklySMALabel — single test class per spec §6.1
# ===========================================================================


class TestDSP004ProfileCWeeklySMALabel:
    """[DSP-004] Profile C Weekly Anchor Label/Desc Mismatch — fix verification.

    Spec §6.2 enumerates seven test cases:
      - TC-1..TC-4 + TC-7: Profile C label/desc agreement (the bug witnesses;
        FAIL pre-fix, PASS post-fix)
      - TC-5, TC-6: Profile A/B regression-witnesses (PASS pre + post; assert
        DAILY_SMA_* preserved)
    """

    # --- TC-1 -------------------------------------------------------------
    def test_profile_c_sma50_label_is_weekly(self):
        """[DSP-004] TC-1: Profile C SMA 50 anchor entry emits 'WEEKLY_SMA_50'.

        Pre-fix this FAILS (emits 'DAILY_SMA_50'). Post-fix PASS.
        """
        fm = _base_flat_metrics(
            **_profile_c_overrides(),
            Price=255.0,
            SMA_50=247.85,
            SMA_200=180.0,
        )
        out = _transform_output(_base_action_summary(), fm)
        stop = out["trade_setup"]["stop"]
        all_entries = _all_floor_entries(stop)
        sma50_entries = [
            e for e in all_entries
            if e.get("price") == 247.85
        ]
        assert sma50_entries, (
            f"Expected SMA 50 entry @ 247.85; got labels={_labels(all_entries)}"
        )
        assert sma50_entries[0]["label"] == "WEEKLY_SMA_50", (
            f"Profile C SMA 50 anchor must emit WEEKLY_SMA_50; got "
            f"{sma50_entries[0]['label']!r}"
        )

    # --- TC-2 -------------------------------------------------------------
    def test_profile_c_sma200_label_is_weekly(self):
        """[DSP-004] TC-2: Profile C SMA 200 anchor entry emits 'WEEKLY_SMA_200'.

        Pre-fix this FAILS (emits 'DAILY_SMA_200'). Post-fix PASS.
        """
        fm = _base_flat_metrics(
            **_profile_c_overrides(),
            Price=255.0,
            SMA_50=247.85,
            SMA_200=180.0,
        )
        out = _transform_output(_base_action_summary(), fm)
        stop = out["trade_setup"]["stop"]
        all_entries = _all_floor_entries(stop)
        sma200_entries = [
            e for e in all_entries
            if e.get("price") == 180.0
        ]
        assert sma200_entries, (
            f"Expected SMA 200 entry @ 180.0; got labels={_labels(all_entries)}"
        )
        assert sma200_entries[0]["label"] == "WEEKLY_SMA_200", (
            f"Profile C SMA 200 anchor must emit WEEKLY_SMA_200; got "
            f"{sma200_entries[0]['label']!r}"
        )

    # --- TC-3 -------------------------------------------------------------
    def test_profile_c_sma50_label_desc_agree_on_timeframe(self):
        """[DSP-004] TC-3: Profile C SMA 50 entry's label and role.desc agree
        on timeframe (both 'Weekly').

        Pre-fix this FAILS (label=DAILY_SMA_50, desc='Weekly SMA 50 ...' —
        timeframe disagreement). Post-fix PASS.
        """
        fm = _base_flat_metrics(
            **_profile_c_overrides(),
            Price=255.0,
            SMA_50=247.85,
            SMA_200=180.0,
        )
        out = _transform_output(_base_action_summary(), fm)
        stop = out["trade_setup"]["stop"]
        all_entries = _all_floor_entries(stop)
        sma50_entries = [
            e for e in all_entries
            if e.get("price") == 247.85
        ]
        assert sma50_entries, "Expected SMA 50 entry @ 247.85"
        entry = sma50_entries[0]
        label = entry["label"]
        desc = entry["role"]["desc"]
        assert "WEEKLY_" in label, (
            f"Profile C SMA 50 label should contain 'WEEKLY_'; got {label!r}"
        )
        assert "Weekly SMA 50" in desc, (
            f"Profile C SMA 50 role.desc should contain 'Weekly SMA 50'; "
            f"got {desc!r}"
        )

    # --- TC-4 -------------------------------------------------------------
    def test_profile_c_sma200_label_desc_agree_on_timeframe(self):
        """[DSP-004] TC-4: Profile C SMA 200 entry's label and role.desc agree
        on timeframe (both 'Weekly').

        Pre-fix this FAILS (label=DAILY_SMA_200, desc='Weekly SMA 200 ...' —
        timeframe disagreement). Post-fix PASS.
        """
        fm = _base_flat_metrics(
            **_profile_c_overrides(),
            Price=255.0,
            SMA_50=247.85,
            SMA_200=180.0,
        )
        out = _transform_output(_base_action_summary(), fm)
        stop = out["trade_setup"]["stop"]
        all_entries = _all_floor_entries(stop)
        sma200_entries = [
            e for e in all_entries
            if e.get("price") == 180.0
        ]
        assert sma200_entries, "Expected SMA 200 entry @ 180.0"
        entry = sma200_entries[0]
        label = entry["label"]
        desc = entry["role"]["desc"]
        assert "WEEKLY_" in label, (
            f"Profile C SMA 200 label should contain 'WEEKLY_'; got {label!r}"
        )
        assert "Weekly SMA 200" in desc, (
            f"Profile C SMA 200 role.desc should contain 'Weekly SMA 200'; "
            f"got {desc!r}"
        )

    # --- TC-5 (regression-witness) ----------------------------------------
    def test_profile_a_sma50_unchanged(self):
        """[DSP-004] TC-5 regression-witness: Profile A SMA 50 entry retains
        'DAILY_SMA_50' (pre + post fix).

        PASS pre-fix (label was already DAILY_SMA_50 and desc was 'Daily SMA 50
        ...' — matched).
        PASS post-fix (profile-aware map preserves DAILY_SMA_50 on Profile A).
        """
        fm = _base_flat_metrics(
            **_profile_a_overrides(),
            Price=140.0,
            Context_Daily_SMA50=130.0,
            SMA_50=130.0,  # fallback path coverage; equal value to Context_*
        )
        out = _transform_output(_base_action_summary(), fm)
        stop = out["trade_setup"]["stop"]
        all_entries = _all_floor_entries(stop)
        sma50_daily = _entries_with_label(all_entries, "DAILY_SMA_50")
        assert sma50_daily, (
            f"Profile A must retain DAILY_SMA_50 SMA 50 anchor entry; "
            f"got labels={_labels(all_entries)}"
        )
        # Negative invariant: Profile A must NOT emit WEEKLY_SMA_50
        weekly = _entries_with_label(all_entries, "WEEKLY_SMA_50")
        assert not weekly, (
            f"Profile A must NOT emit WEEKLY_SMA_50; got entries={weekly}"
        )

    # --- TC-6 (regression-witness) ----------------------------------------
    def test_profile_b_sma50_unchanged(self):
        """[DSP-004] TC-6 regression-witness: Profile B SMA 50 entry retains
        'DAILY_SMA_50' (pre + post fix). Profile B's structural floor IS the
        daily SMA 50 — role.label = FLOOR.

        PASS pre + post fix.
        """
        fm = _base_flat_metrics(
            **_profile_b_overrides(),
            Price=140.0,
            SMA_50=130.0,
        )
        out = _transform_output(_base_action_summary(), fm)
        stop = out["trade_setup"]["stop"]
        all_entries = _all_floor_entries(stop)
        sma50_daily = _entries_with_label(all_entries, "DAILY_SMA_50")
        assert sma50_daily, (
            f"Profile B must retain DAILY_SMA_50 SMA 50 anchor entry; "
            f"got labels={_labels(all_entries)}"
        )
        # Profile B's SMA 50 anchor is the structural floor (role.label=FLOOR)
        entry = sma50_daily[0]
        assert entry["role"]["label"] == "FLOOR", (
            f"Profile B SMA 50 anchor must have role.label=FLOOR; "
            f"got {entry['role']['label']!r}"
        )
        # Negative invariant: Profile B must NOT emit WEEKLY_SMA_50
        weekly = _entries_with_label(all_entries, "WEEKLY_SMA_50")
        assert not weekly, (
            f"Profile B must NOT emit WEEKLY_SMA_50; got entries={weekly}"
        )

    # --- TC-7 -------------------------------------------------------------
    def test_profile_c_overhead_levels_carries_weekly_label(self):
        """[DSP-004] TC-7: BUGR-002 partition cascade transparency.

        Profile C with current_price=240 splits the SMA anchors:
          - SMA_50=247.85 (>= 240) → routes to overhead_levels
          - SMA_200=180.0 (< 240)  → routes to hierarchy

        Post-fix both must carry the new WEEKLY_SMA_* labels through the
        partition (partition logic operates on price, not label).
        Pre-fix this FAILS (both emit DAILY_*).
        """
        fm = _base_flat_metrics(
            **_profile_c_overrides(),
            Price=240.0,
            SMA_50=247.85,
            SMA_200=180.0,
        )
        out = _transform_output(_base_action_summary(), fm)
        stop = out["trade_setup"]["stop"]

        # SMA 50 above price → overhead_levels carrying WEEKLY_SMA_50
        oh = stop.get("overhead_levels") or []
        oh_labels = _labels(oh)
        assert "WEEKLY_SMA_50" in oh_labels, (
            f"Profile C SMA 50 (above price) must route to overhead_levels "
            f"with label WEEKLY_SMA_50; got overhead labels={oh_labels}"
        )

        # SMA 200 below price → hierarchy carrying WEEKLY_SMA_200
        h = stop.get("hierarchy") or []
        h_labels = _labels(h)
        assert "WEEKLY_SMA_200" in h_labels, (
            f"Profile C SMA 200 (below price) must route to hierarchy "
            f"with label WEEKLY_SMA_200; got hierarchy labels={h_labels}"
        )

        # Cross-side cleanliness: WEEKLY_SMA_50 must not be in hierarchy,
        # and WEEKLY_SMA_200 must not be in overhead_levels (partition by
        # price, label cascades transparently).
        assert "WEEKLY_SMA_50" not in h_labels, (
            f"WEEKLY_SMA_50 (price 247.85 above current 240) must not be in "
            f"hierarchy; got {h_labels}"
        )
        assert "WEEKLY_SMA_200" not in oh_labels, (
            f"WEEKLY_SMA_200 (price 180.0 below current 240) must not be in "
            f"overhead_levels; got {oh_labels}"
        )
