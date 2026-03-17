"""OTL-001: Unit tests for _transform_output() — final structure.

Groups: trade_snapshot, trade_quality, trade_risk, trend_state,
price_indicators, floor_analysis, trade_setup, entry_proximity,
exit_signals, _debug (optional).
"""

import copy
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import (
    _transform_output, _flatten, _audit_key_coverage, _error_output,
    _TREND_STATE_SUBGROUPS, _TRADE_QUALITY_SUBGROUPS, _TQ_SCALARS,
    _TRADE_SETUP_SUBGROUPS, _GROUP_TRADE_RISK,
    _GROUP_TRADE_SNAPSHOT_MAPPED, _GROUP_TRADE_SNAPSHOT_CLASSIFICATION,
    _GROUP_PRICE_INDICATORS, _GROUP_FLOOR_ANALYSIS_TOP,
    _GROUP_ENTRY_PROXIMITY, _GROUP_EXIT_SIGNALS, _GROUP_DEBUG,
    _HIGHER_FRAME_MAP, _HIGHER_FRAME_ALL_KEYS,
    _SEM001_RENAMES, MAPPED_FLAT_KEYS,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _make_full_flat_metrics(profile="B"):
    m = {}
    # trend_state.classification
    m["Engine_State"] = "TRENDING"; m["Trend_Age_Bars"] = 15
    m["Active_Modifiers"] = "MOD_A, MOD_C"; m["Inst_Churn"] = "LOW"
    # trend_state.directional
    m["ADX"] = 28.5; m["ADX_Accel"] = 1.2; m["ADX_Accel_State"] = "ACCELERATING"
    m["DI_Plus"] = 30.0; m["DI_Minus"] = 15.0
    # trade_quality scalars
    m["Conviction"] = "HIGH-CONVICTION"; m["Trend_Quality_Override"] = None
    # trade_quality.trend_health
    m["Trend_Health_Score"] = 72.5; m["THS_Label"] = "HEALTHY"
    m["THS_Floor_Buffer"] = 80.0; m["THS_Dir_Momentum"] = 65.0
    m["THS_Trend_Age"] = 70.0; m["THS_Structure"] = 75.0
    # trade_quality.volume
    m["Vol_Confirm_Ratio"] = 1.8; m["Vol_Confirm_State"] = "STRONG INSTITUTIONAL"
    # trade_risk
    m["Reward_Risk"] = 3.5; m["Reward_Risk_Note"] = None
    m["Capital_Reward_Risk"] = 2.8; m["Capital_RR_Label"] = "HEALTHY"
    m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    # price_indicators
    m["EMA_8"] = 150.0; m["EMA_21"] = 148.0; m["SMA_50"] = 142.0
    m["SMA_200"] = 130.0; m["VWAP"] = 149.5 if profile == "A" else None; m["ATR"] = 2.5
    # trade_setup.targets
    m["Profit_Target"] = 160.0; m["Profit_Target_Source"] = "10_Bar_Resistance"
    m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Profit_Target_Synthetic"] = None; m["Profit_Target_Synthetic_Note"] = None
    # trade_setup.stops
    m["Hard_Stop"] = 140.0; m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 139.0
    m["Stop_Adjusted_Flag"] = True; m["Stop_Adjusted_Reason"] = "SSG-001"
    m["Structural_Floor"] = 142.0
    # trade_setup.resistance
    m["Cons_High"] = 155.0; m["Resistance"] = 160.0; m["Resistance_Note"] = None
    # trade_setup.fibonacci
    m["Fib_382_Level"] = 153.0; m["Fib_500_Level"] = 150.0
    m["Fib_Confluence"] = "BETWEEN_FIBS"
    m["Fib_A_382_Level"] = None; m["Fib_A_500_Level"] = None; m["Fib_A_Confluence"] = None
    # trade_setup.round_numbers
    m["RN_Target_Proximity"] = "CLEAR"; m["RN_Stop_Proximity"] = None
    m["RN_Floor_Proximity"] = None
    # trade_setup.positioning
    m["ATR_Dist"] = 0.45; m["ATR_Dist_Anchor"] = "SMA_50"
    m["ATR_Dist_Note"] = None; m["Anchor_Label"] = "SMA_50 Floor (Profile B)"
    m["Anchor_Type"] = "Standard"; m["Floor_Prox_Pct"] = None
    m["Extension_Limit"] = 1.0
    # trade_setup.execution_window
    m["Window_Limit"] = 20; m["Window_Reset_Event"] = None
    # entry_proximity
    m["Proximity_Signal"] = None; m["Proximity_Blocking_Gate"] = None
    m["Proximity_Distance"] = None; m["Proximity_Target"] = None
    m["Proximity_Note"] = None
    # exit_signals
    m["Exit_Signal"] = False; m["Exit_Triggers"] = "None"
    m["Exit_Reason"] = "No exit conditions met"
    m["Exit_VWAP_Counter"] = None; m["Exit_EMA8_Counter"] = None
    m["Established_Hourly_Low"] = None
    # floor_analysis
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
    # higher_frame context
    if profile == "A":
        m["Context_Golden_Cross"] = True; m["Context_Price_vs_SMA200"] = 5.2
        m["Context_SMA200"] = 130.0; m["Context_Daily_SMA50"] = 145.0
        m["Context_Daily_SMA50_Slope"] = 0.35
    elif profile == "B":
        m["Context_Weekly_Golden_Cross"] = True; m["Context_Weekly_Price_vs_SMA200"] = 8.0
        m["Context_Weekly_SMA50"] = 140.0; m["Context_Weekly_SMA50_Slope"] = 0.5
        m["Context_Weekly_SMA50_Rising"] = True
    elif profile == "C":
        m["Context_Monthly_Golden_Cross"] = False; m["Context_Monthly_Price_vs_SMA200"] = -2.0
        m["Context_Monthly_SMA200"] = 135.0; m["Context_Monthly_SMA50"] = 138.0
        m["Context_Monthly_SMA50_Slope"] = -0.1
    # trade_snapshot
    m["Price"] = 152.0; m["ADV_20"] = 5000000.0; m["Is_ETF"] = False
    m["ETF_Detection_Source"] = None; m["ETF_Primary_Exchange"] = None
    m["Convexity_Class"] = "C1"
    m["Entry_Reference"] = 142.0  # non-BREAKOUT → Structural_Floor
    # _debug
    m["actual_price"] = 15200.0; m["adx_t"] = 28.5; m["adx_t1"] = 27.0
    m["adx_t2"] = 25.5; m["adx_accel"] = 1.2; m["adx_accel_state"] = "ACCELERATING"
    m["di_plus"] = 30.0; m["di_minus"] = 15.0; m["atr_raw"] = 250.0
    m["hard_stop_raw"] = 14000.0; m["resistance_raw"] = 16000.0
    m["structural_floor_raw"] = 14200.0; m["price_scaler"] = 1.0
    m["is_etf"] = False; m["_is_lse_etf"] = False; m["_ssg_adjusted"] = True
    m["_ssg_original_raw"] = 13900.0; m["_ssg_reason"] = "floor proximity"
    m["_early_return"] = False; m["ma_squeeze"] = False
    m["clean_ticker"] = "AAPL"; m["currency"] = "USD"
    m["bars_per_day"] = 6.5; m["window_count"] = 5
    m["adx_col"] = "ADX_14"; m["dmp_col"] = "DMP_14"
    m["dmn_col"] = "DMN_14"; m["vwap_col"] = "VWAP_D"
    return m


# ---------------------------------------------------------------------------
# 6A — Group structure
# ---------------------------------------------------------------------------

class Test6A_GroupStructure:

    def test_top_level_keys(self):
        r = _transform_output("PASS", "diag", _make_full_flat_metrics())
        expected = {"status", "diagnostic", "trade_snapshot", "trade_quality",
                    "trade_risk", "trend_state", "price_indicators",
                    "floor_analysis", "trade_setup", "entry_proximity", "exit_signals"}
        assert set(r.keys()) == expected

    def test_debug_absent_by_default(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert "_debug" not in r

    def test_debug_present_when_requested(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics(), debug=True)
        assert "_debug" in r

    def test_reading_order(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert list(r.keys()) == [
            "status", "diagnostic", "trade_snapshot", "trade_quality",
            "trade_risk", "trend_state", "price_indicators", "floor_analysis",
            "trade_setup", "entry_proximity", "exit_signals"]

    def test_no_old_group_names(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics(), debug=True)
        for old in ("verdict", "proximity", "diagnostics", "floor_context", "asset"):
            assert old not in r


# ---------------------------------------------------------------------------
# 6B — Key completeness
# ---------------------------------------------------------------------------

class Test6B_KeyCompleteness:

    def test_trade_snapshot_6_top_level(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert len(r["trade_snapshot"]) == 6  # current_price, support, resistance, entry_strategy, avg_daily_volume, classification

    def test_trade_snapshot_has_support_resistance(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        ts = r["trade_snapshot"]
        assert "support" in ts
        assert "resistance" in ts
        assert ts["support"] == 142.0      # Structural_Floor
        assert ts["resistance"] == 160.0   # Resistance

    def test_trade_snapshot_avg_daily_volume(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert "avg_daily_volume" in r["trade_snapshot"]
        assert r["trade_snapshot"]["avg_daily_volume"] == 5000000.0

    def test_trade_snapshot_classification_equity(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        cls = r["trade_snapshot"]["classification"]
        assert cls["type"] == "EQUITY"
        assert cls["convexity"] == "C1"
        assert cls["etf_detection"] is None
        assert len(cls) == 4

    def test_trade_snapshot_classification_etf(self):
        flat = _make_full_flat_metrics()
        flat["Is_ETF"] = True
        flat["ETF_Detection_Source"] = "EXCHANGE_MATCH"
        r = _transform_output("PASS", "d", flat)
        cls = r["trade_snapshot"]["classification"]
        assert cls["type"] == "ETF"
        assert cls["etf_detection"] == "EXCHANGE_MATCH"

    def test_trade_quality_10_leaves(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        tq = r["trade_quality"]
        count = sum(len(v) if isinstance(v, dict) else 1 for v in tq.values())
        assert count == 10

    def test_trade_risk_7(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert len(r["trade_risk"]) == 7

    def test_trade_risk_has_risk_per_unit(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert "risk_per_unit" in r["trade_risk"]

    def test_trade_risk_has_threshold(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        tr = r["trade_risk"]
        assert tr["threshold"] == 2.0
        assert "threshold_note" in tr

    def test_trend_state_9_leaves(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert sum(len(sg) for sg in r["trend_state"].values()) == 9

    def test_price_indicators_6(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert len(r["price_indicators"]) == 6

    def test_floor_analysis_structure(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        fa = r["floor_analysis"]
        assert len(fa) == 5  # 4 top + higher_frame
        assert "higher_frame" in fa

    def test_trade_setup_32_leaves(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        s = r["trade_setup"]
        count = sum(len(v) if isinstance(v, dict) else 1 for v in s.values())
        assert count == 32

    def test_trade_setup_subgroup_counts(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        s = r["trade_setup"]
        assert len(s["targets"]) == 5
        assert len(s["stops"]) == 6
        assert len(s["resistance"]) == 3
        assert len(s["fibonacci"]) == 6
        assert len(s["round_numbers"]) == 3
        assert len(s["positioning"]) == 7
        assert len(s["execution_window"]) == 2

    def test_trade_setup_no_reward_risk(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert "reward_risk" not in r["trade_setup"]

    def test_trade_setup_no_expectancy(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert "expectancy" not in r["trade_setup"]

    def test_entry_proximity_5(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert len(r["entry_proximity"]) == 5

    def test_exit_signals_6(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert len(r["exit_signals"]) == 6

    def test_debug_28(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics(), debug=True)
        assert len(r["_debug"]) == 28


# ---------------------------------------------------------------------------
# 6C — SEM-001 renames
# ---------------------------------------------------------------------------

class Test6C_SEM001Renames:

    RENAME_CHECKS = [
        ("Inst_Churn",           ("trend_state", "classification"), "churn"),
        ("Cons_High",            ("trade_setup", "resistance"),     "high"),
        ("Stop_Adjusted_Flag",   ("trade_setup", "stops"),          "adjusted"),
        ("RN_Target_Proximity",  ("trade_setup", "round_numbers"),  "target"),
        ("RN_Stop_Proximity",    ("trade_setup", "round_numbers"),  "stop"),
        ("RN_Floor_Proximity",   ("trade_setup", "round_numbers"),  "floor"),
        ("ATR_Dist",             ("trade_setup", "positioning"),    "atr_distance"),
        ("ATR_Dist_Anchor",      ("trade_setup", "positioning"),    "atr_distance_anchor"),
        ("ATR_Dist_Note",        ("trade_setup", "positioning"),    "atr_distance_note"),
        ("Floor_Prox_Pct",       ("trade_setup", "positioning"),    "floor_proximity_pct"),
        ("Floor_Failure_Reclaim",("floor_analysis",),               "reclaim_progress"),
    ]

    @pytest.mark.parametrize("flat_key,path,stripped_key", RENAME_CHECKS)
    def test_rename_value(self, flat_key, path, stripped_key):
        flat = _make_full_flat_metrics()
        flat[flat_key] = f"TEST_{flat_key}"
        r = _transform_output("PASS", "d", flat)
        node = r
        for seg in path:
            node = node[seg]
        assert node[stripped_key] == f"TEST_{flat_key}"

    def test_rename_count(self):
        assert len(_SEM001_RENAMES) == 11


# ---------------------------------------------------------------------------
# 6D — Higher-frame normalisation
# ---------------------------------------------------------------------------

class Test6D_HigherFrame:

    def test_profile_a(self):
        hf = _transform_output("PASS", "d", _make_full_flat_metrics("A"))["floor_analysis"]["higher_frame"]
        assert hf["golden_cross"] is True
        assert hf["daily_sma50"] == 145.0

    def test_profile_b(self):
        hf = _transform_output("PASS", "d", _make_full_flat_metrics("B"))["floor_analysis"]["higher_frame"]
        assert hf["sma50_rising"] is True

    def test_profile_c(self):
        hf = _transform_output("PASS", "d", _make_full_flat_metrics("C"))["floor_analysis"]["higher_frame"]
        assert hf["golden_cross"] is False

    def test_all_absent(self):
        flat = _make_full_flat_metrics("B")
        for fk, _ in _HIGHER_FRAME_MAP:
            flat.pop(fk, None)
        hf = _transform_output("HALT", "R", flat)["floor_analysis"]["higher_frame"]
        for k in _HIGHER_FRAME_ALL_KEYS:
            assert hf[k] is None


# ---------------------------------------------------------------------------
# 6E — Null preservation
# ---------------------------------------------------------------------------

class Test6E_NullPreservation:

    def test_null_in_subgroups(self):
        flat = _make_full_flat_metrics()
        flat["Reward_Risk"] = None
        flat["Profit_Target"] = None
        r = _transform_output("PASS", "d", flat)
        assert r["trade_risk"]["ratio"] is None
        assert r["trade_setup"]["targets"]["level"] is None

    def test_missing_key_defaults_none(self):
        flat = _make_full_flat_metrics()
        flat.pop("VWAP", None)
        r = _transform_output("PASS", "d", flat)
        assert r["price_indicators"]["vwap"] is None


# ---------------------------------------------------------------------------
# 6F — Pure function
# ---------------------------------------------------------------------------

class Test6F_PureFunction:

    def test_no_mutation(self):
        flat = _make_full_flat_metrics()
        orig = copy.deepcopy(flat)
        _transform_output("PASS", "d", flat)
        assert flat == orig


# ---------------------------------------------------------------------------
# 6G — Unmapped keys
# ---------------------------------------------------------------------------

class Test6G_UnmappedKeys:

    def test_spurious_key_dropped(self):
        flat = _make_full_flat_metrics()
        flat["__garbage"] = 999
        r = _transform_output("PASS", "d", flat, debug=True)
        for group in r.values():
            if isinstance(group, dict):
                assert "__garbage" not in group
                for v in group.values():
                    if isinstance(v, dict):
                        assert "__garbage" not in v

    def test_audit_catches_unmapped(self):
        flat = _make_full_flat_metrics()
        flat["__garbage"] = 999
        assert "__garbage" in _audit_key_coverage(flat)

    def test_audit_clean(self):
        assert len(_audit_key_coverage(_make_full_flat_metrics())) == 0


# ---------------------------------------------------------------------------
# Key relocation
# ---------------------------------------------------------------------------

class TestKeyRelocation:

    def test_risk_per_unit_in_trade_risk(self):
        flat = _make_full_flat_metrics()
        flat["Risk_Per_Unit"] = 0.75
        r = _transform_output("PASS", "d", flat)
        assert r["trade_risk"]["risk_per_unit"] == 0.75
        assert "risk_per_unit" not in r["trade_snapshot"]

    def test_expectancy_in_trade_risk(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert r["trade_risk"]["threshold"] == 2.0

    def test_conviction_in_trade_quality(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert r["trade_quality"]["range_quality"] == "HIGH-CONVICTION"

    def test_volume_in_trade_quality(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert r["trade_quality"]["volume"]["relative_volume"] == 1.8

    def test_positioning_in_trade_setup(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        p = r["trade_setup"]["positioning"]
        assert p["atr_distance"] == 0.45
        assert p["extension_limit"] == 1.0

    def test_support_resistance_in_snapshot(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert r["trade_snapshot"]["support"] == 142.0
        assert r["trade_snapshot"]["resistance"] == 160.0

    def test_support_resistance_null_when_absent(self):
        r = _transform_output("HALT", "d", {})
        assert r["trade_snapshot"]["support"] is None
        assert r["trade_snapshot"]["resistance"] is None

    def test_current_price_renamed(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        assert r["trade_snapshot"]["current_price"] == 152.0
        assert "price" not in r["trade_snapshot"]

    def test_entry_price_non_breakout(self):
        """Non-BREAKOUT → entry_price = Structural_Floor."""
        flat = _make_full_flat_metrics()  # Engine_State = TRENDING
        flat["Entry_Reference"] = flat["Structural_Floor"]
        r = _transform_output("PASS", "d", flat)
        es = r["trade_snapshot"]["entry_strategy"]
        assert es["entry_price"] == 142.0
        assert es["entry_price"] == r["trade_snapshot"]["support"]

    def test_entry_price_breakout(self):
        """BREAKOUT → entry_price = Resistance."""
        flat = _make_full_flat_metrics()
        flat["Engine_State"] = "BREAKOUT"
        flat["Entry_Reference"] = flat["Resistance"]
        r = _transform_output("PASS", "d", flat)
        es = r["trade_snapshot"]["entry_strategy"]
        assert es["entry_price"] == 160.0
        assert es["entry_price"] == r["trade_snapshot"]["resistance"]

    def test_entry_strategy_null_when_absent(self):
        r = _transform_output("HALT", "d", {})
        es = r["trade_snapshot"]["entry_strategy"]
        assert es["entry_price"] is None
        assert es["stop_loss"] is None
        assert es["target"] is None

    def test_entry_strategy_stop_loss_and_target(self):
        flat = _make_full_flat_metrics()
        flat["Entry_Reference"] = flat["Structural_Floor"]
        r = _transform_output("PASS", "d", flat)
        es = r["trade_snapshot"]["entry_strategy"]
        assert es["stop_loss"] == 140.0    # Hard_Stop
        assert es["target"] == 160.0       # Profit_Target
        assert len(es) == 3

    def test_snapshot_display_order(self):
        r = _transform_output("PASS", "d", _make_full_flat_metrics())
        keys = list(r["trade_snapshot"].keys())
        assert keys == ["current_price", "support", "resistance",
                        "entry_strategy", "avg_daily_volume", "classification"]


# ---------------------------------------------------------------------------
# Flatten round-trip
# ---------------------------------------------------------------------------

class TestFlatten:

    def test_roundtrip(self):
        flat = _make_full_flat_metrics(profile="B")
        r = _transform_output("PASS", "PRE-APPROVED", flat, debug=True)
        status, diag, flat_out = _flatten(r)
        assert status == "PASS"
        assert flat_out["Engine_State"] == "TRENDING"
        assert flat_out["ADX"] == 28.5
        assert flat_out["Inst_Churn"] == "LOW"
        assert flat_out["Cons_High"] == 155.0
        assert flat_out["ATR_Dist"] == 0.45
        assert flat_out["Profit_Target"] == 160.0
        assert flat_out["Hard_Stop"] == 140.0
        assert flat_out["EMA_8"] == 150.0
        assert flat_out["Conviction"] == "HIGH-CONVICTION"
        assert flat_out["Reward_Risk"] == 3.5
        assert flat_out["Expectancy_Threshold"] == 2.0
        assert flat_out["Extension_Limit"] == 1.0
        assert flat_out["Window_Limit"] == 20
        assert flat_out["Vol_Confirm_Ratio"] == 1.8
        assert flat_out["Trend_Health_Score"] == 72.5
        assert flat_out["ADV_20"] == 5000000.0
        assert flat_out["Structural_Floor"] == 142.0
        assert flat_out["Resistance"] == 160.0
        assert flat_out["Price"] == 152.0
        assert flat_out["Entry_Reference"] == 142.0


# ---------------------------------------------------------------------------
# Mapping integrity
# ---------------------------------------------------------------------------

class TestMappingIntegrity:

    def test_total_129(self):
        assert len(MAPPED_FLAT_KEYS) == 129

    def test_no_duplicate_flat_keys(self):
        seen = {}
        all_tables = [("trade_snapshot_mapped", _GROUP_TRADE_SNAPSHOT_MAPPED),
                      ("trade_snapshot_classification", _GROUP_TRADE_SNAPSHOT_CLASSIFICATION)]
        for sg, t in _TRADE_QUALITY_SUBGROUPS:
            all_tables.append((f"trade_quality.{sg}", t))
        all_tables.append(("trade_quality._scalars", _TQ_SCALARS))
        all_tables.append(("trade_risk", _GROUP_TRADE_RISK))
        for sg, t in _TREND_STATE_SUBGROUPS:
            all_tables.append((f"trend_state.{sg}", t))
        all_tables.append(("price_indicators", _GROUP_PRICE_INDICATORS))
        all_tables.append(("floor_analysis", _GROUP_FLOOR_ANALYSIS_TOP))
        for sg, t in _TRADE_SETUP_SUBGROUPS:
            all_tables.append((f"trade_setup.{sg}", t))
        for name, t in [("entry_proximity", _GROUP_ENTRY_PROXIMITY),
                         ("exit_signals", _GROUP_EXIT_SIGNALS),
                         ("_debug", _GROUP_DEBUG)]:
            all_tables.append((name, t))
        for group_name, table in all_tables:
            for fk, _ in table:
                if fk in seen:
                    pytest.fail(f"'{fk}' in both '{seen[fk]}' and '{group_name}'")
                seen[fk] = group_name


# ---------------------------------------------------------------------------
# Error output
# ---------------------------------------------------------------------------

class TestErrorOutput:

    def test_error_has_correct_structure(self):
        r = _error_output("ERROR", "test")
        assert isinstance(r["trade_setup"]["targets"], dict)
        assert isinstance(r["trade_quality"]["trend_health"], dict)
        assert isinstance(r["trade_risk"], dict)
        assert r["trade_snapshot"]["support"] is None
        assert r["trade_risk"]["ratio"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
