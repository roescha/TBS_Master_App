"""BUGR-002 — Stop and Target Hierarchy Partition tests.

Spec: BUGR002_Stop_Target_Hierarchy_Partition_Spec_v1_0.docx (S132)

Covers the twelve test classes enumerated in spec §6.1:

    1. TestStopSidePartition        — mixed below/above case
    2. TestStopSideBelowOnly        — healthy setup (all floors below price)
    3. TestStopSideAboveOnly        — catastrophic drawdown (all floors above)
    4. TestStopSideBRKActive        — BRK-001 scoping preserved through partition
    5. TestStopSideProfileB         — DAILY_HARD_STOP > 0 guard + VWAP absence
    6. TestTargetSidePartition      — mixed above/cleared case
    7. TestTargetSideAboveOnly      — fresh setup (all targets above)
    8. TestTargetSideCleared        — strong uptrend with EXCEEDED rows
    9. TestTargetSideBRKActive      — BRK-001 line 1788 filter preserved
   10. TestEmptyArrays              — edge cases with one or both arrays null
   11. TestBRK001DriftAlignment     — regression guard on NEW_SUPPORT / THESIS_STOP
   12. TestFlattenStability         — _flatten() coverage unchanged post-partition

Construction notes:
    - Uses direct importlib load to avoid the tbs_engine package init chain
      (which pulls ib_insync via tbs_engine.main → tbs_engine.data).
    - Base fixture mirrors test_pa001_phase3_hierarchies.py with a few BUGR-002
      specific anchor-price shifts in per-test overrides.
    - Partition predicate on stop side: price <  current_price → hierarchy;
                                        price >= current_price → overhead_levels.
    - Partition predicate on target side: price >  current_price → hierarchy;
                                          price <= current_price → cleared_levels.
"""

import pytest
import sys
import os

# ---------------------------------------------------------------------------
# Direct file import — transform.py has zero imports within tbs_engine; loading
# through the package __init__ would pull tbs_engine.main → tbs_engine.data →
# ib_insync, which we don't need for a pure _transform_output test.
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
_flatten = _transform_mod._flatten
MAPPED_FLAT_KEYS = _transform_mod.MAPPED_FLAT_KEYS


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
    level values that are all strictly below price — i.e. the 'healthy setup'
    shape. Tests override specific prices to construct mixed / above-only /
    below-only / BRK-active scenarios.
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

        # Psychological levels (floor strictly below price by construction)
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

        # Floor sources (all below Price=130)
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
    """Minimal overrides to trigger the Profile B path.

    Profile B: primary chart is daily, Floor_Anchor_Type == SMA_50. No VWAP
    (Profile A only). DAILY_HARD_STOP should be absent (BUGR-001 > 0 guard).
    """
    return {
        "Floor_Anchor_Type": "SMA_50",
        "VWAP": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,   # BUGR-001: guarded at _transform_output
    }


def _brk_active_overrides():
    """Overrides that trigger BRK-001 scoping (stop side: replaces floor
    entries with NEW_SUPPORT / TIGHT_STOP / CATASTROPHIC_STOP + retained
    PSYCHOLOGICAL; target side: filters to above-current only)."""
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
# 1. TestStopSidePartition — mixed below/above case
# ===========================================================================


class TestStopSidePartition:
    """Spec §5.1: stop-side partition splits _floor_entries into hierarchy
    (below price) and overhead_levels (at or above price). Mixed case mirrors
    the live S123 sample (IGV / CRM: SMA_200 above price)."""

    # Shift SMA_200 above price to force the partition to split
    _MIXED = {
        "Price": 130.0,
        "Context_SMA200": 140.0,   # above price — lands in overhead_levels
    }

    def test_hierarchy_has_below_price_levels_only(self):
        """hierarchy contains only entries with price < current_price."""
        stop = _get_stop(self._MIXED)
        assert stop["hierarchy"] is not None
        for entry in stop["hierarchy"]:
            assert entry["price"] < 130.0, (
                f"{entry['label']} @ {entry['price']} should not be in hierarchy "
                f"when current_price=130.0"
            )

    def test_overhead_has_at_or_above_price_levels_only(self):
        """overhead_levels contains only entries with price >= current_price."""
        stop = _get_stop(self._MIXED)
        assert stop["overhead_levels"] is not None
        for entry in stop["overhead_levels"]:
            assert entry["price"] >= 130.0, (
                f"{entry['label']} @ {entry['price']} should not be in overhead_levels "
                f"when current_price=130.0"
            )

    def test_sma200_routed_to_overhead_when_above_price(self):
        """Live-sample regression: SMA_200 above price must land in overhead_levels."""
        stop = _get_stop(self._MIXED)
        oh_labels = [e["label"] for e in stop["overhead_levels"]]
        assert "DAILY_SMA_200" in oh_labels
        h_labels = [e["label"] for e in stop["hierarchy"]]
        assert "DAILY_SMA_200" not in h_labels

    def test_hierarchy_sort_descending(self):
        """hierarchy sorted descending (highest-below-first)."""
        stop = _get_stop(self._MIXED)
        prices = [e["price"] for e in stop["hierarchy"]]
        assert prices == sorted(prices, reverse=True), f"Not descending: {prices}"

    def test_overhead_sort_ascending_nearest_first(self):
        """overhead_levels sorted ascending (nearest-above-price first, §4.8)."""
        stop = _get_stop({
            "Price": 130.0,
            "Context_SMA200": 140.0,
            "SMA_200": 140.0,
            # Also push EMA_21 above so we have two levels in overhead
            "Daily_Protective_Anchor": 135.0,
            "Context_EMA_21": 135.0,
        })
        oh = stop["overhead_levels"]
        assert oh is not None and len(oh) >= 2
        prices = [e["price"] for e in oh]
        assert prices == sorted(prices), f"overhead_levels not ascending: {prices}"

    def test_overhead_entries_have_no_status_field(self):
        """§4.3: status field stripped from overhead_levels entries."""
        stop = _get_stop(self._MIXED)
        for entry in stop["overhead_levels"]:
            assert "status" not in entry, (
                f"{entry['label']} in overhead_levels should not carry status "
                f"(found: {entry.get('status')})"
            )

    def test_hierarchy_entries_retain_status_field(self):
        """hierarchy entries retain HOLDING/BREACHED status per §5.1."""
        stop = _get_stop(self._MIXED)
        for entry in stop["hierarchy"]:
            assert "status" in entry, f"{entry['label']} missing status in hierarchy"
            # SESSION_VWAP uses ABOVE/BELOW vocabulary on Profile A (AVWAP-001);
            # all other anchors use HOLDING/BREACHED.
            if entry["label"] == "SESSION_VWAP":
                assert entry["status"] in ("ABOVE", "BELOW")
            else:
                assert entry["status"] in ("HOLDING", "BREACHED"), (
                    f"{entry['label']} has unexpected status {entry['status']!r}"
                )

    def test_overhead_retains_price_label_role_desc(self):
        """§4.3: overhead_levels entries keep price/label/role/desc shape."""
        stop = _get_stop(self._MIXED)
        for entry in stop["overhead_levels"]:
            assert "price" in entry
            assert "label" in entry
            assert "role" in entry
            assert "label" in entry["role"]
            assert "desc" in entry["role"]


# ===========================================================================
# 2. TestStopSideBelowOnly — healthy setup
# ===========================================================================


class TestStopSideBelowOnly:
    """All floors below current price. hierarchy populated, overhead_levels
    should be null (§4.6: emit null rather than empty list)."""

    def test_all_floors_below_populate_hierarchy(self):
        """Base fixture has all floors below Price=130 — all 9 in hierarchy."""
        stop = _get_stop()
        assert stop["hierarchy"] is not None
        labels = {e["label"] for e in stop["hierarchy"]}
        # All 9 Profile A anchors should be present
        expected = {"SESSION_VWAP", "AVWAP_10BAR", "DAILY_EMA_21",
                    "DAILY_SMA_50", "DAILY_SMA_200", "ESTABLISHED_LOW",
                    "HARD_STOP", "DAILY_HARD_STOP", "PSYCHOLOGICAL"}
        assert labels == expected, f"Missing: {expected - labels}, Extra: {labels - expected}"

    def test_overhead_null_when_all_below(self):
        """§4.6: overhead_levels is None (not an empty list) when empty."""
        stop = _get_stop()
        assert stop["overhead_levels"] is None, (
            f"Expected None, got {stop['overhead_levels']!r}"
        )


# ===========================================================================
# 3. TestStopSideAboveOnly — catastrophic drawdown
# ===========================================================================


class TestStopSideAboveOnly:
    """All floors above current price — e.g. post-gap-down catastrophic drawdown.
    hierarchy becomes null; overhead_levels carries all entries."""

    # Push price below every floor-anchor source value
    _CATASTROPHE = {"Price": 50.0}

    def test_hierarchy_null_when_all_floors_above(self):
        stop = _get_stop(self._CATASTROPHE)
        assert stop["hierarchy"] is None, (
            f"Expected hierarchy null, got {stop['hierarchy']!r}"
        )

    def test_overhead_contains_all_entries(self):
        stop = _get_stop(self._CATASTROPHE)
        oh = stop["overhead_levels"]
        assert oh is not None and len(oh) >= 8  # at least 8 anchors all overhead

    def test_overhead_ascending_in_catastrophe(self):
        stop = _get_stop(self._CATASTROPHE)
        prices = [e["price"] for e in stop["overhead_levels"]]
        assert prices == sorted(prices)

    def test_catastrophe_with_psych_floor_retained_below(self):
        """Psych_Floor can still be below price in some catastrophe variants —
        verify it then lands in hierarchy while everything else goes overhead."""
        stop = _get_stop({"Price": 112.5, "Psych_Floor": 110.0})
        # Psych_Floor at 110 is below 112.5 → hierarchy; everything else above
        assert stop["hierarchy"] is not None
        h_labels = {e["label"] for e in stop["hierarchy"]}
        assert "PSYCHOLOGICAL" in h_labels
        assert stop["overhead_levels"] is not None
        oh_labels = {e["label"] for e in stop["overhead_levels"]}
        assert "PSYCHOLOGICAL" not in oh_labels


# ===========================================================================
# 4. TestStopSideBRKActive — BRK-001 scoping preserved
# ===========================================================================


class TestStopSideBRKActive:
    """§4.5 + §5.4: BRK-001 replaces _floor_entries with three BRK-scoped
    levels plus retained PSYCHOLOGICAL. All four construction-guaranteed below
    price → hierarchy populated, overhead_levels null."""

    def test_brk_hierarchy_contains_brk_levels_plus_psych(self):
        stop = _get_stop(_brk_active_overrides())
        assert stop["hierarchy"] is not None
        labels = {e["label"] for e in stop["hierarchy"]}
        # NEW_SUPPORT + TIGHT_STOP + CATASTROPHIC_STOP + PSYCHOLOGICAL
        assert labels == {"NEW_SUPPORT", "TIGHT_STOP",
                          "CATASTROPHIC_STOP", "PSYCHOLOGICAL"}

    def test_brk_hierarchy_sort_descending(self):
        stop = _get_stop(_brk_active_overrides())
        prices = [e["price"] for e in stop["hierarchy"]]
        assert prices == sorted(prices, reverse=True)

    def test_brk_overhead_null(self):
        """BRK-001 scoping rule: pre-breakout structural levels not in the stop
        container at all → overhead_levels null (nothing to route above)."""
        stop = _get_stop(_brk_active_overrides())
        assert stop["overhead_levels"] is None

    def test_brk_pre_breakout_levels_absent(self):
        """BRK-001 §4.5: SESSION_VWAP / EMA_21 / SMA_50 / SMA_200 / etc. not
        present in hierarchy OR overhead_levels on BRK-active paths."""
        stop = _get_stop(_brk_active_overrides())
        h_labels = {e["label"] for e in (stop["hierarchy"] or [])}
        for excluded in ("SESSION_VWAP", "AVWAP_10BAR", "DAILY_EMA_21",
                         "DAILY_SMA_50", "DAILY_SMA_200", "ESTABLISHED_LOW",
                         "HARD_STOP", "DAILY_HARD_STOP"):
            assert excluded not in h_labels, (
                f"{excluded} should be excluded on BRK-active path"
            )


# ===========================================================================
# 5. TestStopSideProfileB — BUGR-001 guard + VWAP absence
# ===========================================================================


class TestStopSideProfileB:
    """Profile B run. Invariants to verify through the partition:
      - DAILY_HARD_STOP absent (BUGR-001 > 0 guard at transform.py:1938)
      - SESSION_VWAP absent (Profile A only)
    """

    def test_profile_b_no_session_vwap(self):
        """SESSION_VWAP only emitted when Floor_Anchor_Type == 'EMA_21'."""
        stop = _get_stop(_profile_b_overrides())
        h_labels = {e["label"] for e in (stop["hierarchy"] or [])}
        oh_labels = {e["label"] for e in (stop["overhead_levels"] or [])}
        assert "SESSION_VWAP" not in h_labels
        assert "SESSION_VWAP" not in oh_labels

    def test_profile_b_daily_hard_stop_zero_absent(self):
        """BUGR-001: DAILY_HARD_STOP at 0.0 guarded, must not appear anywhere."""
        stop = _get_stop(_profile_b_overrides())
        h_labels = {e["label"] for e in (stop["hierarchy"] or [])}
        oh_labels = {e["label"] for e in (stop["overhead_levels"] or [])}
        assert "DAILY_HARD_STOP" not in h_labels
        assert "DAILY_HARD_STOP" not in oh_labels

    def test_profile_b_daily_hard_stop_negative_absent(self):
        """BUGR-001 guard is > 0 — a negative value must also be excluded."""
        ov = _profile_b_overrides()
        ov["Daily_Hard_Stop"] = -5.0
        stop = _get_stop(ov)
        h_labels = {e["label"] for e in (stop["hierarchy"] or [])}
        oh_labels = {e["label"] for e in (stop["overhead_levels"] or [])}
        assert "DAILY_HARD_STOP" not in h_labels
        assert "DAILY_HARD_STOP" not in oh_labels

    def test_profile_b_hierarchy_still_populated(self):
        """Profile B still produces a valid stop cascade from the remaining anchors."""
        stop = _get_stop(_profile_b_overrides())
        assert stop["hierarchy"] is not None and len(stop["hierarchy"]) > 0


# ===========================================================================
# 6. TestTargetSidePartition — mixed above/cleared case
# ===========================================================================


class TestTargetSidePartition:
    """Spec §5.2: target-side partition splits _target_entries into hierarchy
    (above price) and cleared_levels (at or below price — EXCEEDED rows)."""

    # Push DAILY_HIGH below price so it is EXCEEDED and lands in cleared_levels
    _MIXED = {
        "Price": 138.0,
        # DAILY_HIGH source (Resistance) = 135 < 138 → EXCEEDED
        # MM_Target = 140 > 138 → hierarchy
        # Blue_Sky_Target = 145 > 138 → hierarchy
        # Fundamental_Target = 150 > 138 → hierarchy
        # Psych_Ceiling = 140 > 138 → hierarchy
        "Profit_Target": 140.0,   # winner follows the closest active target
    }

    def test_hierarchy_has_above_price_targets_only(self):
        target = _get_target(self._MIXED)
        assert target["hierarchy"] is not None
        for entry in target["hierarchy"]:
            assert entry["price"] > 138.0

    def test_cleared_has_at_or_below_price_targets_only(self):
        target = _get_target(self._MIXED)
        assert target["cleared_levels"] is not None
        for entry in target["cleared_levels"]:
            assert entry["price"] <= 138.0

    def test_daily_high_exceeded_routed_to_cleared(self):
        """DAILY_HIGH @ 135 with Price=138 is EXCEEDED → cleared_levels."""
        target = _get_target(self._MIXED)
        cl_labels = [e["label"] for e in target["cleared_levels"]]
        h_labels = [e["label"] for e in target["hierarchy"]]
        assert "DAILY_HIGH" in cl_labels
        assert "DAILY_HIGH" not in h_labels

    def test_hierarchy_sort_ascending(self):
        target = _get_target(self._MIXED)
        prices = [e["price"] for e in target["hierarchy"]]
        assert prices == sorted(prices), f"hierarchy not ascending: {prices}"

    def test_cleared_sort_ascending(self):
        """§4.8: cleared_levels sorted ascending (preserves target convention)."""
        target = _get_target({
            "Price": 150.0,
            # All targets below 150 → cleared; DAILY_HIGH=135, MM=140,
            # PSYCH=140, BS=145, FUND=150 (== 150, boundary → cleared), Resistance=135
        })
        cl = target["cleared_levels"]
        assert cl is not None and len(cl) >= 2
        prices = [e["price"] for e in cl]
        assert prices == sorted(prices), f"cleared_levels not ascending: {prices}"

    def test_status_retained_on_hierarchy_entries(self):
        """§4.7: status ACTIVE retained on hierarchy entries."""
        target = _get_target(self._MIXED)
        for entry in target["hierarchy"]:
            assert entry.get("status") == "ACTIVE", (
                f"{entry['label']} status should be ACTIVE, got {entry.get('status')!r}"
            )

    def test_status_retained_on_cleared_entries(self):
        """§4.7: status EXCEEDED retained on cleared_levels entries (NOT stripped
        unlike stop-side overhead_levels)."""
        target = _get_target(self._MIXED)
        for entry in target["cleared_levels"]:
            assert entry.get("status") == "EXCEEDED", (
                f"{entry['label']} status should be EXCEEDED, got {entry.get('status')!r}"
            )

    def test_escalation_winner_retained_on_both_arrays(self):
        """§4.7: escalation_winner field carries through partition on both arrays."""
        target = _get_target(self._MIXED)
        for arr_name in ("hierarchy", "cleared_levels"):
            arr = target[arr_name] or []
            for entry in arr:
                assert "escalation_winner" in entry, (
                    f"{entry['label']} missing escalation_winner in {arr_name}"
                )


# ===========================================================================
# 7. TestTargetSideAboveOnly — fresh setup
# ===========================================================================


class TestTargetSideAboveOnly:
    """Fresh setup: all targets above current price. hierarchy populated,
    cleared_levels null per §4.6."""

    def test_all_targets_above_populate_hierarchy(self):
        """Base fixture: Price=130, every target above 130."""
        target = _get_target()
        assert target["hierarchy"] is not None
        labels = {e["label"] for e in target["hierarchy"]}
        # DAILY_HIGH + MM + ATR_PROJECTION + ANALYST + PSYCHOLOGICAL
        # (WEEKLY_HIGH only fires on PE-41 escalation — not in base fixture)
        assert "DAILY_HIGH" in labels
        assert "MEASURED_MOVE" in labels
        assert "ATR_PROJECTION" in labels
        assert "ANALYST_CONSENSUS" in labels
        assert "PSYCHOLOGICAL" in labels

    def test_cleared_null_when_all_above(self):
        """§4.6: cleared_levels is None (not an empty list) when empty."""
        target = _get_target()
        assert target["cleared_levels"] is None


# ===========================================================================
# 8. TestTargetSideCleared — strong uptrend with EXCEEDED rows
# ===========================================================================


class TestTargetSideCleared:
    """Strong uptrend: multiple EXCEEDED rows. Verify cleared_levels sort,
    escalation_winner field carries through."""

    def test_multiple_exceeded_targets_in_cleared(self):
        """Price well above multiple targets → most go to cleared_levels."""
        target = _get_target({
            "Price": 147.0,
            # Price=147 > DAILY_HIGH=135, > MM=140, > PSYCH=140, > BS=145
            # Only FUND=150 remains in hierarchy
            "Profit_Target": 150.0,
        })
        assert target["cleared_levels"] is not None
        cl_labels = {e["label"] for e in target["cleared_levels"]}
        # At least DAILY_HIGH and MEASURED_MOVE should be in cleared
        assert "DAILY_HIGH" in cl_labels
        assert "MEASURED_MOVE" in cl_labels

    def test_cleared_levels_all_have_exceeded_status(self):
        target = _get_target({"Price": 147.0, "Profit_Target": 150.0})
        for entry in target["cleared_levels"]:
            assert entry["status"] == "EXCEEDED"

    def test_hierarchy_still_has_remaining_forward_target(self):
        """Even with multiple EXCEEDED rows, forward targets still in hierarchy."""
        target = _get_target({"Price": 147.0, "Profit_Target": 150.0})
        assert target["hierarchy"] is not None
        h_labels = {e["label"] for e in target["hierarchy"]}
        assert "ANALYST_CONSENSUS" in h_labels

    def test_escalation_winner_carries_through_to_cleared(self):
        """If a pre-existing escalation_winner row becomes EXCEEDED, the
        escalation_winner field still travels to cleared_levels (§4.7)."""
        # Force DAILY_HIGH to be the winner by pinning Profit_Target==Resistance;
        # then push price above 135 so DAILY_HIGH is EXCEEDED.
        target = _get_target({
            "Price": 138.0,
            "Profit_Target": 135.0,   # matches Resistance → DAILY_HIGH is winner
        })
        # DAILY_HIGH should be in cleared (price 135 <= 138) with escalation_winner=True
        cl = target["cleared_levels"] or []
        daily_high = next((e for e in cl if e["label"] == "DAILY_HIGH"), None)
        assert daily_high is not None
        assert daily_high["escalation_winner"] is True


# ===========================================================================
# 9. TestTargetSideBRKActive
# ===========================================================================


class TestTargetSideBRKActive:
    """§5.2 + line 1788: BRK-001 active path applies its own > current_price
    filter and reassigns escalation_winner to MEASURED_MOVE. All post-filter
    entries are above-current by construction → hierarchy populated,
    cleared_levels null."""

    def test_brk_cleared_null(self):
        target = _get_target(_brk_active_overrides())
        assert target["cleared_levels"] is None

    def test_brk_hierarchy_populated(self):
        target = _get_target(_brk_active_overrides())
        assert target["hierarchy"] is not None
        assert len(target["hierarchy"]) > 0

    def test_brk_measured_move_is_escalation_winner(self):
        """BRK-001 §4.5: MM becomes escalation_winner, others demoted."""
        target = _get_target(_brk_active_overrides())
        h = target["hierarchy"]
        mm = next((e for e in h if e["label"] == "MEASURED_MOVE"), None)
        assert mm is not None, "MM should be in BRK hierarchy"
        assert mm["escalation_winner"] is True
        # All others should have escalation_winner=False
        for entry in h:
            if entry["label"] != "MEASURED_MOVE":
                assert entry["escalation_winner"] is False, (
                    f"{entry['label']} should have winner=False on BRK path"
                )


# ===========================================================================
# 10. TestEmptyArrays — §4.6 nullable semantics
# ===========================================================================


class TestEmptyArrays:
    """Spec §4.6: both arrays on each side are independently nullable. When
    empty, emit None rather than an empty list."""

    def test_stop_overhead_null_not_empty_list(self):
        """Healthy setup: overhead_levels is None (not [])."""
        stop = _get_stop()
        assert stop["overhead_levels"] is None
        assert stop["overhead_levels"] != []

    def test_target_cleared_null_not_empty_list(self):
        """Fresh setup: cleared_levels is None (not [])."""
        target = _get_target()
        assert target["cleared_levels"] is None
        assert target["cleared_levels"] != []

    def test_stop_hierarchy_null_under_catastrophic_drawdown(self):
        """Price below every floor → hierarchy is None."""
        stop = _get_stop({"Price": 50.0})
        assert stop["hierarchy"] is None

    def test_target_hierarchy_null_when_all_exceeded(self):
        """Price above every target → hierarchy is None."""
        target = _get_target({"Price": 200.0})
        assert target["hierarchy"] is None

    def test_both_stop_fields_present_as_keys(self):
        """Even when a side is null, the key must be present so downstream
        consumers can rely on `target["overhead_levels"]` lookup without
        KeyError."""
        stop = _get_stop()
        assert "hierarchy" in stop
        assert "overhead_levels" in stop

    def test_both_target_fields_present_as_keys(self):
        target = _get_target()
        assert "hierarchy" in target
        assert "cleared_levels" in target


# ===========================================================================
# 11. TestBRK001DriftAlignment — regression guard on NEW_SUPPORT / THESIS_STOP
# ===========================================================================


class TestBRK001DriftAlignment:
    """BRK-001-DRIFT-1 (§4.9): code emits NEW_SUPPORT (not POST_BREAKOUT_SUPPORT)
    and THESIS_STOP (not BREAKOUT_STOP). Doc 2 is being amended to match code
    during the subsequent DIA session; these tests guard against future
    accidental renames of the code-authoritative strings."""

    def test_new_support_label_emitted(self):
        stop = _get_stop(_brk_active_overrides())
        labels = {e["label"] for e in stop["hierarchy"]}
        assert "NEW_SUPPORT" in labels, (
            "BRK-001 scoping must emit label 'NEW_SUPPORT' (not "
            "'POST_BREAKOUT_SUPPORT' — BRK-001-DRIFT-1, code authoritative)."
        )

    def test_thesis_stop_role_label_emitted(self):
        stop = _get_stop(_brk_active_overrides())
        tight_stop = next(
            (e for e in stop["hierarchy"] if e["label"] == "TIGHT_STOP"), None
        )
        assert tight_stop is not None
        assert tight_stop["role"]["label"] == "THESIS_STOP", (
            "BRK-001 scoping must emit role 'THESIS_STOP' (not "
            "'BREAKOUT_STOP' — BRK-001-DRIFT-1, code authoritative)."
        )

    def test_breakout_support_role_preserved(self):
        """NEW_SUPPORT carries role BREAKOUT_SUPPORT (unchanged — not drifted)."""
        stop = _get_stop(_brk_active_overrides())
        ns = next(
            (e for e in stop["hierarchy"] if e["label"] == "NEW_SUPPORT"), None
        )
        assert ns is not None
        assert ns["role"]["label"] == "BREAKOUT_SUPPORT"


# ===========================================================================
# 12. TestFlattenStability — _flatten() coverage unchanged
# ===========================================================================


class TestFlattenStability:
    """§5.3: _flatten() reads the post-partition hierarchy arrays. The narrower
    semantics (hierarchy = below-price on stop / above-price on target) mean
    Target_Hierarchy_Count, Floor_Hierarchy_Count, and Target_Hierarchy_Winner
    all measure the partitioned 'hierarchy' array only. MAPPED_FLAT_KEYS is
    unchanged (no new flat keys added for overhead_levels / cleared_levels per
    §5.3 default recommendation)."""

    def test_mapped_flat_keys_contain_existing_hierarchy_keys(self):
        assert "Target_Hierarchy_Count" in MAPPED_FLAT_KEYS
        assert "Target_Hierarchy_Winner" in MAPPED_FLAT_KEYS
        assert "Floor_Hierarchy_Count" in MAPPED_FLAT_KEYS

    def test_mapped_flat_keys_no_overhead_levels_key(self):
        """§5.3 default: no flat-key exposure for overhead_levels / cleared_levels."""
        assert "Overhead_Levels_Count" not in MAPPED_FLAT_KEYS
        assert "Cleared_Levels_Count" not in MAPPED_FLAT_KEYS

    def test_flatten_target_hierarchy_count_narrower_post_partition(self):
        """On mixed case, Target_Hierarchy_Count reflects hierarchy-only (not
        hierarchy + cleared_levels combined)."""
        fm = _base_flat_metrics(Price=138.0, Profit_Target=140.0)
        grouped = _transform_output(_base_action_summary(), fm)
        target = grouped["trade_setup"]["target"]
        h_count = len(target["hierarchy"])
        cl_count = len(target["cleared_levels"] or [])

        status, diagnostic, flat = _flatten(grouped)
        assert flat["Target_Hierarchy_Count"] == h_count
        # Demonstrate the narrowing: post-partition count < total entries
        assert flat["Target_Hierarchy_Count"] < (h_count + cl_count) or cl_count == 0

    def test_flatten_floor_hierarchy_count_narrower_post_partition(self):
        """On mixed case, Floor_Hierarchy_Count reflects hierarchy-only."""
        fm = _base_flat_metrics(Context_SMA200=140.0)
        grouped = _transform_output(_base_action_summary(), fm)
        stop = grouped["trade_setup"]["stop"]
        h_count = len(stop["hierarchy"])
        oh_count = len(stop["overhead_levels"] or [])

        status, diagnostic, flat = _flatten(grouped)
        assert flat["Floor_Hierarchy_Count"] == h_count
        assert flat["Floor_Hierarchy_Count"] < (h_count + oh_count) or oh_count == 0

    def test_flatten_target_hierarchy_winner_from_hierarchy_only(self):
        """Target_Hierarchy_Winner reads escalation_winner from hierarchy only.
        If the winner is EXCEEDED and lives in cleared_levels, the flat-key
        returns None (narrower semantics — consumers should watch for this)."""
        # Force DAILY_HIGH to be the winner AND make it EXCEEDED
        fm = _base_flat_metrics(Price=138.0, Profit_Target=135.0)
        grouped = _transform_output(_base_action_summary(), fm)
        status, diagnostic, flat = _flatten(grouped)
        # DAILY_HIGH (winner) is in cleared_levels, not hierarchy → Winner is None
        assert flat["Target_Hierarchy_Winner"] is None

    def test_flatten_target_hierarchy_winner_normal_case(self):
        """In the healthy base-fixture case, the escalation_winner is in
        hierarchy → Target_Hierarchy_Winner returns the label."""
        fm = _base_flat_metrics()
        grouped = _transform_output(_base_action_summary(), fm)
        status, diagnostic, flat = _flatten(grouped)
        # Base fixture: Profit_Target=135 matches Resistance=135 → DAILY_HIGH wins
        # All targets are above Price=130 → DAILY_HIGH is in hierarchy
        assert flat["Target_Hierarchy_Winner"] == "DAILY_HIGH"
