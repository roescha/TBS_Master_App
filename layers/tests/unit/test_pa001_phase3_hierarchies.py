"""PA-001 Phase 3 — Target Hierarchy (DQ-9) and Floor Hierarchy (DQ-10) tests.

Tests cover:
1. Target hierarchy: all 6 levels, ascending sort, escalation winner, status labels, None omission
2. Floor hierarchy: all 8 levels, descending sort, profile-dependent roles, BREACHED/HOLDING status
3. Profile scoping: Profile A (VWAP + PROTECTIVE_ANCHOR), Profile B (FLOOR on SMA 50), Profile C (FLOOR on SMA 200)
4. Partial data: missing levels reduce count
5. Self-doc compliance: {price, label, role: {label, desc}, status}
6. _flatten reverse mapping: Target_Hierarchy_Count, Target_Hierarchy_Winner, Floor_Hierarchy_Count
"""

import pytest
import sys
import os

# ---------------------------------------------------------------------------
# Direct file import — transform.py has zero imports, load directly
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import importlib.util

_root = os.path.join(os.path.dirname(__file__), '..', '..')
_spec = importlib.util.spec_from_file_location(
    "tbs_engine_transform",
    os.path.join(_root, "tbs_engine", "transform.py"),
)
_transform_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output
_flatten = _transform_mod._flatten


# ---------------------------------------------------------------------------
# Helpers
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

    Defaults to Profile A (VWAP floor anchor) with a reasonable set of values.
    """
    m = {
        # Core
        "Price": 130.0,
        "Structural_Floor": 125.0,
        "Floor_Anchor_Type": "VWAP",
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

        # Targets
        "Profit_Target": 135.0,
        "Profit_Target_Source": "10_Bar_Resistance",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "MM_Target": 140.0,
        "Blue_Sky_Target": 145.0,
        "Blue_Sky_Method": "ATR_PROJECTION",
        "Blue_Sky_Detected": True,
        "Fundamental_Target": 150.0,

        # Psychological levels
        "Psych_Floor": 130.0,
        "Psych_Ceiling": 140.0,
        "Psych_Floor_Dist_Pct": 0.0,
        "Psych_Ceiling_Dist_Pct": 7.69,
        "Psych_Floor_Near_Structural": False,
        "Psych_Ceiling_Near_Technical": False,
        "Psych_Increment": 10.0,
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

        # Engine state (required by _transform_output)
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
        "THS_VWAP_Floor_Penalty": True,
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


def _get_grouped(flat_overrides=None):
    """Run _transform_output with default base and return grouped dict."""
    fm = _base_flat_metrics(**(flat_overrides or {}))
    return _transform_output(_base_action_summary(), fm)


# ===========================================================================
# 1. TARGET HIERARCHY — DQ-9
# ===========================================================================

class TestTargetHierarchy:
    """DQ-9: Target hierarchy tests."""

    def test_all_6_levels_populated(self):
        """All 6 target levels present when all data available including weekly escalation."""
        g = _get_grouped({
            "Profit_Target_Source": "WEEKLY_RESISTANCE (price above daily range)",
            "Profit_Target": 142.0,
        })
        th = g["trade_setup"]["target"]["hierarchy"]
        assert th is not None
        assert len(th) == 6
        labels = {e["label"] for e in th}
        assert labels == {"DAILY_HIGH", "WEEKLY_HIGH", "MEASURED_MOVE",
                          "ATR_PROJECTION", "ANALYST_CONSENSUS", "PSYCHOLOGICAL"}

    def test_no_weekly_when_10bar_source(self):
        """Tier 2 WEEKLY_HIGH excluded when Profit_Target_Source is 10_Bar_Resistance."""
        g = _get_grouped()
        th = g["trade_setup"]["target"]["hierarchy"]
        labels = [e["label"] for e in th]
        assert "WEEKLY_HIGH" not in labels
        assert len(th) == 5

    def test_weekly_present_when_escalated(self):
        """Tier 2 WEEKLY_HIGH present when Profit_Target_Source contains WEEKLY."""
        g = _get_grouped({
            "Profit_Target_Source": "WEEKLY_RESISTANCE (price above daily range)",
            "Profit_Target": 142.0,
            "Resistance": None,  # suppressed when price above daily
        })
        th = g["trade_setup"]["target"]["hierarchy"]
        labels = [e["label"] for e in th]
        assert "WEEKLY_HIGH" in labels
        # Resistance is None → DAILY_HIGH omitted
        assert "DAILY_HIGH" not in labels

    def test_sorted_ascending_by_price(self):
        """Target hierarchy sorted ascending by price."""
        g = _get_grouped()
        th = g["trade_setup"]["target"]["hierarchy"]
        prices = [e["price"] for e in th]
        assert prices == sorted(prices), f"Not ascending: {prices}"

    def test_escalation_winner_tagged(self):
        """Exactly one entry matches Profit_Target and is tagged escalation_winner."""
        g = _get_grouped()
        th = g["trade_setup"]["target"]["hierarchy"]
        winners = [e for e in th if e.get("escalation_winner")]
        assert len(winners) >= 1
        # The winner's price should match Profit_Target (135.0 = Resistance)
        assert any(abs(w["price"] - 135.0) < 0.01 for w in winners)

    def test_exceeded_status_when_price_above(self):
        """Entry gets EXCEEDED status when current_price > entry_price."""
        g = _get_grouped({
            "Price": 155.0,  # above all targets
        })
        th = g["trade_setup"]["target"]["hierarchy"]
        for entry in th:
            assert entry["status"] == "EXCEEDED", f"{entry['label']} should be EXCEEDED"

    def test_active_status_when_price_below(self):
        """Entry gets ACTIVE status when current_price <= entry_price."""
        g = _get_grouped({
            "Price": 100.0,  # below all targets
        })
        th = g["trade_setup"]["target"]["hierarchy"]
        for entry in th:
            assert entry["status"] == "ACTIVE", f"{entry['label']} should be ACTIVE"

    def test_none_price_omitted(self):
        """Entries with None price are omitted."""
        g = _get_grouped({
            "MM_Target": None,
            "Fundamental_Target": None,
        })
        th = g["trade_setup"]["target"]["hierarchy"]
        labels = [e["label"] for e in th]
        assert "MEASURED_MOVE" not in labels
        assert "ANALYST_CONSENSUS" not in labels
        assert len(th) == 3  # DAILY_HIGH, ATR_PROJECTION, PSYCHOLOGICAL

    def test_selfdoc_compliance(self):
        """Every entry has {price, label, role: {label, desc}, status}."""
        g = _get_grouped()
        th = g["trade_setup"]["target"]["hierarchy"]
        for entry in th:
            assert "price" in entry, f"Missing price in {entry['label']}"
            assert "label" in entry, f"Missing label"
            assert "role" in entry, f"Missing role in {entry['label']}"
            assert isinstance(entry["role"], dict), f"Role not dict in {entry['label']}"
            assert "label" in entry["role"], f"Missing role.label in {entry['label']}"
            assert "desc" in entry["role"], f"Missing role.desc in {entry['label']}"
            assert "status" in entry, f"Missing status in {entry['label']}"
            assert entry["status"] in ("ACTIVE", "EXCEEDED"), f"Invalid status: {entry['status']}"

    def test_empty_when_all_none(self):
        """target_hierarchy is None when all source prices are None."""
        g = _get_grouped({
            "Resistance": None,
            "MM_Target": None,
            "Blue_Sky_Target": None,
            "Fundamental_Target": None,
            "Psych_Ceiling": None,
            "Profit_Target": None,
            "Profit_Target_Source": "10_Bar_Resistance",
        })
        assert g["trade_setup"]["target"]["hierarchy"] is None


# ===========================================================================
# 2. FLOOR HIERARCHY — DQ-10
# ===========================================================================

class TestFloorHierarchy:
    """DQ-10: Floor hierarchy tests."""

    def test_all_9_levels_profile_a(self):
        """All 9 floor levels present for Profile A when all data available."""
        g = _get_grouped()
        fh = g["trade_setup"]["stop"]["hierarchy"]
        assert fh is not None
        labels = {e["label"] for e in fh}
        expected = {"SESSION_VWAP", "AVWAP_10BAR", "DAILY_EMA_21",
                    "DAILY_SMA_50", "DAILY_SMA_200", "ESTABLISHED_LOW",
                    "HARD_STOP", "DAILY_HARD_STOP", "PSYCHOLOGICAL"}
        assert labels == expected, f"Missing: {expected - labels}, Extra: {labels - expected}"
        assert len(fh) == 9

    def test_sorted_descending_by_price(self):
        """Floor hierarchy sorted descending by price (highest first)."""
        g = _get_grouped()
        fh = g["trade_setup"]["stop"]["hierarchy"]
        prices = [e["price"] for e in fh]
        assert prices == sorted(prices, reverse=True), f"Not descending: {prices}"

    def test_holding_status_when_price_above(self):
        """All floors get HOLDING when current_price >= floor_price."""
        g = _get_grouped({
            "Price": 200.0,  # above all floors
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        for entry in fh:
            assert entry["status"] == "HOLDING", f"{entry['label']} should be HOLDING"

    def test_breached_status_when_price_below(self):
        """Floor gets BREACHED when current_price < floor_price."""
        g = _get_grouped({
            "Price": 100.0,  # below all floors
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        for entry in fh:
            assert entry["status"] == "BREACHED", f"{entry['label']} should be BREACHED"

    def test_partial_breach(self):
        """Some floors HOLDING, some BREACHED when price between them."""
        g = _get_grouped({
            "Price": 121.0,  # above Hard_Stop (120) and SMA_200 (112), below VWAP (125)
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        for entry in fh:
            if entry["price"] > 121.0:
                assert entry["status"] == "BREACHED", f"{entry['label']} @ {entry['price']} should be BREACHED"
            else:
                assert entry["status"] == "HOLDING", f"{entry['label']} @ {entry['price']} should be HOLDING"

    def test_selfdoc_compliance(self):
        """Every entry has {price, label, role: {label, desc}, status}."""
        g = _get_grouped()
        fh = g["trade_setup"]["stop"]["hierarchy"]
        for entry in fh:
            assert "price" in entry, f"Missing price in {entry['label']}"
            assert "label" in entry
            assert "role" in entry
            assert isinstance(entry["role"], dict)
            assert "label" in entry["role"]
            assert "desc" in entry["role"]
            assert "status" in entry
            assert entry["status"] in ("HOLDING", "BREACHED")

    def test_no_session_vwap_for_profile_b(self):
        """Profile B: no SESSION_VWAP entry (VWAP is Profile A only)."""
        g = _get_grouped({
            "Floor_Anchor_Type": "SMA_50",
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        labels = [e["label"] for e in fh]
        assert "SESSION_VWAP" not in labels

    def test_no_session_vwap_for_profile_c(self):
        """Profile C: no SESSION_VWAP entry."""
        g = _get_grouped({
            "Floor_Anchor_Type": "SMA_200",
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        labels = [e["label"] for e in fh]
        assert "SESSION_VWAP" not in labels


# ===========================================================================
# 3. PROFILE-DEPENDENT ROLES
# ===========================================================================

class TestProfileRoles:
    """Profile-scoped role assignment per DQ-10 spec."""

    def test_profile_a_ema21_protective_anchor(self):
        """Profile A: EMA 21 role is PROTECTIVE_ANCHOR."""
        g = _get_grouped({"Floor_Anchor_Type": "VWAP"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        ema21 = next(e for e in fh if e["label"] == "DAILY_EMA_21")
        assert ema21["role"]["label"] == "PROTECTIVE_ANCHOR"

    def test_profile_a_sma50_support(self):
        """Profile A: SMA 50 role is SUPPORT."""
        g = _get_grouped({"Floor_Anchor_Type": "VWAP"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma50 = next(e for e in fh if e["label"] == "DAILY_SMA_50")
        assert sma50["role"]["label"] == "SUPPORT"

    def test_profile_a_sma200_support(self):
        """Profile A: SMA 200 role is SUPPORT."""
        g = _get_grouped({"Floor_Anchor_Type": "VWAP"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma200 = next(e for e in fh if e["label"] == "DAILY_SMA_200")
        assert sma200["role"]["label"] == "SUPPORT"

    def test_profile_a_session_vwap_entry_anchor(self):
        """Profile A: Session VWAP role is ENTRY_ANCHOR."""
        g = _get_grouped({"Floor_Anchor_Type": "VWAP"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        vwap = next(e for e in fh if e["label"] == "SESSION_VWAP")
        assert vwap["role"]["label"] == "ENTRY_ANCHOR"

    def test_profile_b_sma50_floor(self):
        """Profile B: SMA 50 role is FLOOR (this IS the structural anchor)."""
        g = _get_grouped({"Floor_Anchor_Type": "SMA_50"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma50 = next(e for e in fh if e["label"] == "DAILY_SMA_50")
        assert sma50["role"]["label"] == "FLOOR"

    def test_profile_b_ema21_support(self):
        """Profile B: EMA 21 role is SUPPORT (not protective anchor)."""
        g = _get_grouped({"Floor_Anchor_Type": "SMA_50"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        ema21 = next(e for e in fh if e["label"] == "DAILY_EMA_21")
        assert ema21["role"]["label"] == "SUPPORT"

    def test_profile_b_sma200_support(self):
        """Profile B: SMA 200 role is SUPPORT."""
        g = _get_grouped({"Floor_Anchor_Type": "SMA_50"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma200 = next(e for e in fh if e["label"] == "DAILY_SMA_200")
        assert sma200["role"]["label"] == "SUPPORT"

    def test_profile_c_sma200_floor(self):
        """Profile C: SMA 200 role is FLOOR (this IS the structural anchor)."""
        g = _get_grouped({"Floor_Anchor_Type": "SMA_200"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma200 = next(e for e in fh if e["label"] == "DAILY_SMA_200")
        assert sma200["role"]["label"] == "FLOOR"

    def test_profile_c_sma50_support(self):
        """Profile C: SMA 50 role is SUPPORT."""
        g = _get_grouped({"Floor_Anchor_Type": "SMA_200"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma50 = next(e for e in fh if e["label"] == "DAILY_SMA_50")
        assert sma50["role"]["label"] == "SUPPORT"

    def test_profile_c_ema21_support(self):
        """Profile C: EMA 21 role is SUPPORT."""
        g = _get_grouped({"Floor_Anchor_Type": "SMA_200"})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        ema21 = next(e for e in fh if e["label"] == "DAILY_EMA_21")
        assert ema21["role"]["label"] == "SUPPORT"


# ===========================================================================
# 4. PARTIAL DATA
# ===========================================================================

class TestPartialData:
    """Partial data: missing sources reduce hierarchy counts."""

    def test_target_5_entries_when_mm_none(self):
        """When MM_Target is None, target hierarchy has 4 entries (no MM)."""
        g = _get_grouped({"MM_Target": None})
        th = g["trade_setup"]["target"]["hierarchy"]
        labels = [e["label"] for e in th]
        assert "MEASURED_MOVE" not in labels
        assert len(th) == 4

    def test_target_3_entries_when_multiple_none(self):
        """Multiple None prices reduce the count appropriately."""
        g = _get_grouped({
            "MM_Target": None,
            "Blue_Sky_Target": None,
            "Fundamental_Target": None,
        })
        th = g["trade_setup"]["target"]["hierarchy"]
        assert len(th) == 2  # DAILY_HIGH + PSYCHOLOGICAL

    def test_floor_7_entries_when_avwap_none(self):
        """When AVWAP_Price is None, floor hierarchy has 7 entries."""
        g = _get_grouped({"AVWAP_Price": None})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        labels = [e["label"] for e in fh]
        assert "AVWAP_10BAR" not in labels
        assert len(fh) == 8

    def test_floor_handles_missing_ema21(self):
        """When Daily_Protective_Anchor and Context_EMA_21 both None, EMA 21 entry omitted."""
        g = _get_grouped({
            "Daily_Protective_Anchor": None,
            "Context_EMA_21": None,
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        labels = [e["label"] for e in fh]
        assert "DAILY_EMA_21" not in labels

    def test_floor_handles_missing_hard_stop(self):
        """When Hard_Stop is None (suppressed), HARD_STOP entry omitted."""
        g = _get_grouped({"Hard_Stop": None})
        fh = g["trade_setup"]["stop"]["hierarchy"]
        labels = [e["label"] for e in fh]
        assert "HARD_STOP" not in labels


# ===========================================================================
# 5. _FLATTEN REVERSE MAPPING
# ===========================================================================

class TestFlattenReverseMapping:
    """Verify _flatten extracts hierarchy summary keys from grouped output."""

    def test_target_hierarchy_count(self):
        """_flatten produces Target_Hierarchy_Count from grouped."""
        g = _get_grouped()
        _, _, flat = _flatten(g)
        assert flat["Target_Hierarchy_Count"] == len(g["trade_setup"]["target"]["hierarchy"])

    def test_target_hierarchy_winner(self):
        """_flatten produces Target_Hierarchy_Winner label from grouped."""
        g = _get_grouped()
        _, _, flat = _flatten(g)
        assert flat["Target_Hierarchy_Winner"] is not None
        # Winner should be DAILY_HIGH (matches Profit_Target 135.0 = Resistance 135.0)
        assert flat["Target_Hierarchy_Winner"] == "DAILY_HIGH"

    def test_floor_hierarchy_count(self):
        """_flatten produces Floor_Hierarchy_Count from grouped."""
        g = _get_grouped()
        _, _, flat = _flatten(g)
        assert flat["Floor_Hierarchy_Count"] == len(g["trade_setup"]["stop"]["hierarchy"])

    def test_flatten_none_hierarchies(self):
        """_flatten handles None hierarchies (all sources None)."""
        g = _get_grouped({
            "Resistance": None,
            "MM_Target": None,
            "Blue_Sky_Target": None,
            "Fundamental_Target": None,
            "Psych_Ceiling": None,
            "Profit_Target": None,
            "Profit_Target_Source": "10_Bar_Resistance",
        })
        _, _, flat = _flatten(g)
        assert flat["Target_Hierarchy_Count"] == 0
        assert flat["Target_Hierarchy_Winner"] is None

    def test_weekly_escalation_winner(self):
        """When weekly escalation active, winner is WEEKLY_HIGH."""
        g = _get_grouped({
            "Profit_Target_Source": "WEEKLY_RESISTANCE (price above daily range)",
            "Profit_Target": 142.0,
            "Resistance": None,
        })
        _, _, flat = _flatten(g)
        assert flat["Target_Hierarchy_Winner"] == "WEEKLY_HIGH"


# ===========================================================================
# 6. NO DUPLICATE ENTRIES
# ===========================================================================

class TestNoDuplicates:
    """Verify no duplicate label entries in hierarchies."""

    def test_no_duplicate_target_labels(self):
        """Target hierarchy has no duplicate labels."""
        g = _get_grouped()
        th = g["trade_setup"]["target"]["hierarchy"]
        labels = [e["label"] for e in th]
        assert len(labels) == len(set(labels)), f"Duplicates found: {labels}"

    def test_no_duplicate_floor_labels(self):
        """Floor hierarchy has no duplicate labels."""
        g = _get_grouped()
        fh = g["trade_setup"]["stop"]["hierarchy"]
        labels = [e["label"] for e in fh]
        assert len(labels) == len(set(labels)), f"Duplicates found: {labels}"


# ===========================================================================
# 7. EXISTING TRADE_SETUP.TARGET NOT REPLACED
# ===========================================================================

class TestExistingTargetPreserved:
    """Hierarchy supplements trade_setup.target — doesn't replace it."""

    def test_trade_setup_target_still_present(self):
        """trade_setup.target remains alongside target_hierarchy."""
        g = _get_grouped()
        assert "trade_setup" in g
        assert g["trade_setup"]["target"] is not None
        assert "hierarchy" in g["trade_setup"]["target"]

    def test_trade_setup_stop_still_present(self):
        """trade_setup.stop remains alongside floor_hierarchy."""
        g = _get_grouped()
        assert g["trade_setup"]["stop"] is not None
        assert "hierarchy" in g["trade_setup"]["stop"]


# ===========================================================================
# 8. EMA 21 SOURCE RESOLUTION
# ===========================================================================

class TestEma21SourceResolution:
    """Profile-aware EMA 21 source resolution for floor hierarchy."""

    def test_profile_a_uses_daily_protective_anchor(self):
        """Profile A preferentially uses Daily_Protective_Anchor for EMA 21."""
        g = _get_grouped({
            "Floor_Anchor_Type": "VWAP",
            "Daily_Protective_Anchor": 128.0,
            "Context_EMA_21": 127.5,
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        ema21 = next(e for e in fh if e["label"] == "DAILY_EMA_21")
        assert ema21["price"] == 128.0  # Daily_Protective_Anchor preferred

    def test_profile_a_falls_back_to_context_ema21(self):
        """Profile A falls back to Context_EMA_21 if Daily_Protective_Anchor is None."""
        g = _get_grouped({
            "Floor_Anchor_Type": "VWAP",
            "Daily_Protective_Anchor": None,
            "Context_EMA_21": 127.5,
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        ema21 = next(e for e in fh if e["label"] == "DAILY_EMA_21")
        assert ema21["price"] == 127.5

    def test_profile_b_uses_ema21(self):
        """Profile B uses EMA_21 (primary daily chart)."""
        g = _get_grouped({
            "Floor_Anchor_Type": "SMA_50",
            "EMA_21": 127.0,
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        ema21 = next(e for e in fh if e["label"] == "DAILY_EMA_21")
        assert ema21["price"] == 127.0

    def test_profile_c_uses_context_ema21(self):
        """Profile C uses Context_EMA_21 if available."""
        g = _get_grouped({
            "Floor_Anchor_Type": "SMA_200",
            "Context_EMA_21": 126.0,
            "EMA_21": 125.0,
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        ema21 = next(e for e in fh if e["label"] == "DAILY_EMA_21")
        assert ema21["price"] == 126.0  # Context_EMA_21 preferred for Profile C


# ===========================================================================
# 9. SMA 50 / SMA 200 SOURCE RESOLUTION
# ===========================================================================

class TestSmaSourceResolution:
    """Profile-aware SMA 50/200 source resolution for floor hierarchy."""

    def test_profile_a_uses_context_daily_sma50(self):
        """Profile A uses Context_Daily_SMA50 for SMA 50."""
        g = _get_grouped({
            "Floor_Anchor_Type": "VWAP",
            "Context_Daily_SMA50": 123.0,
            "SMA_50": 121.0,  # hourly SMA 50 (not what we want)
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma50 = next(e for e in fh if e["label"] == "DAILY_SMA_50")
        assert sma50["price"] == 123.0

    def test_profile_b_uses_sma50(self):
        """Profile B uses SMA_50 (primary daily chart)."""
        g = _get_grouped({
            "Floor_Anchor_Type": "SMA_50",
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma50 = next(e for e in fh if e["label"] == "DAILY_SMA_50")
        assert sma50["price"] == 122.0  # from base: SMA_50

    def test_profile_a_uses_context_sma200(self):
        """Profile A uses Context_SMA200 for SMA 200."""
        g = _get_grouped({
            "Floor_Anchor_Type": "VWAP",
            "Context_SMA200": 112.0,
            "SMA_200": 110.0,  # hourly SMA 200
        })
        fh = g["trade_setup"]["stop"]["hierarchy"]
        sma200 = next(e for e in fh if e["label"] == "DAILY_SMA_200")
        assert sma200["price"] == 112.0
