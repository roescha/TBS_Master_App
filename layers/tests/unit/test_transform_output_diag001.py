"""DIAG-001 Phase 2B: _transform_output updated structure tests.

Replaces test_transform_output.py. Verifies:
- action_summary as first key in output
- No status or diagnostic keys
- entry_strategy NOT in trade_snapshot (DD-3)
- All other groups (trade_quality through exit_signals) unchanged
- _debug group present when debug=True

Spec: DIAG_001_Action_Summary_Spec_v1_0.md §V.4
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.8
"""

import copy
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import (
    _transform_output, _flatten, _audit_key_coverage, _error_output,
    _TREND_STATE_SUBGROUPS, _TRADE_QUALITY_SUBGROUPS, _TQ_SCALARS,
    _TRADE_SETUP_SUBGROUPS, _GROUP_TRADE_RISK,
    _GROUP_TRADE_SNAPSHOT_MAPPED, _GROUP_TRADE_SNAPSHOT_CLASSIFICATION,
    _GROUP_PRICE_INDICATORS, _GROUP_FLOOR_ANALYSIS_TOP,
    _GROUP_ENTRY_PROXIMITY, _GROUP_EXIT_SIGNALS, _GROUP_DEBUG,
    _HIGHER_FRAME_MAP, _HIGHER_FRAME_ALL_KEYS,
    MAPPED_FLAT_KEYS,
)


def _make_full_flat_metrics(profile="B"):
    """Full metrics dict for testing grouped output."""
    m = {}
    m["Engine_State"] = "TRENDING"; m["Trend_Age_Bars"] = 15
    m["Active_Modifiers"] = "MOD_A, MOD_C"; m["Inst_Churn"] = "LOW"
    m["ADX"] = 28.5; m["ADX_Accel"] = 1.2; m["ADX_Accel_State"] = "ACCELERATING"
    m["DI_Plus"] = 30.0; m["DI_Minus"] = 15.0
    # TS-001: new keys
    m["Engine_State_Desc"] = "ADX > 20 + full MA stack + no squeeze"
    m["Trend_Age_Max"] = 80; m["Active_Modifiers_List"] = []
    m["DI_Spread"] = 15.0; m["DI_Bias"] = "BULLISH"
    m["Trend_Quality_Override"] = None
    m["Trend_Health_Score"] = 72.5; m["THS_Label"] = "HEALTHY"
    m["THS_Floor_Buffer"] = 80.0; m["THS_Dir_Momentum"] = 65.0
    m["THS_Trend_Age"] = 70.0; m["THS_Structure"] = 75.0
    # THS-002: sub-score labels
    m["THS_Floor_Buffer_Label"] = "STRONG"; m["THS_Dir_Momentum_Label"] = "HEALTHY"
    m["THS_Trend_Age_Label"] = "HEALTHY"; m["THS_Structure_Label"] = "HEALTHY"
    m["Vol_Confirm_Ratio"] = 1.8; m["Vol_Confirm_State"] = "STRONG ACCUMULATION"
    m["Reward_Risk"] = 3.5; m["Reward_Risk_Note"] = None
    m["Capital_Reward_Risk"] = 2.8; m["Capital_RR_Label"] = "HEALTHY"
    m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    # RISK-001: summary keys
    m["Risk_Summary_Label"] = "FAVORABLE"; m["Risk_Summary_Desc"] = "test."
    m["EMA_8"] = 150.0; m["EMA_21"] = 148.0; m["SMA_50"] = 142.0
    m["SMA_200"] = 130.0; m["VWAP"] = 149.5 if profile == "A" else None; m["ATR"] = 2.5
    m["Profit_Target"] = 160.0; m["Profit_Target_Source"] = "10_Bar_Resistance"
    m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Profit_Target_Synthetic"] = None; m["Profit_Target_Synthetic_Note"] = None
    m["Hard_Stop"] = 140.0; m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 139.0
    m["Stop_Adjusted_Flag"] = True; m["Stop_Adjusted_Reason"] = "SSG-001"
    m["Structural_Floor"] = 142.0; m["Pullback_Zone_Upper"] = 145.0
    m["Cons_High"] = 155.0; m["Resistance"] = 160.0; m["Resistance_Note"] = None
    m["Fib_382_Level"] = 153.0; m["Fib_500_Level"] = 150.0
    m["Fib_Confluence"] = "BETWEEN_FIBS"
    m["Fib_A_382_Level"] = None; m["Fib_A_500_Level"] = None; m["Fib_A_Confluence"] = None
    m["RN_Target_Proximity"] = "CLEAR"; m["RN_Stop_Proximity"] = None
    m["RN_Floor_Proximity"] = None
    m["MM_Target"] = 127.0; m["MM_Rally_ATR"] = 7.5
    m["ATR_Dist"] = 0.45; m["ATR_Dist_Anchor"] = "SMA_50"
    m["ATR_Dist_Note"] = None; m["Anchor_Label"] = "SMA_50 Floor (Profile B)"
    m["Anchor_Type"] = "Standard"; m["Floor_Prox_Pct"] = None
    m["Extension_Limit"] = 1.0
    m["Window_Limit"] = 20; m["Window_Reset_Event"] = None
    m["Proximity_Signal"] = None; m["Proximity_Blocking_Gate"] = None
    m["Proximity_Distance"] = None; m["Proximity_Target"] = None
    m["Proximity_Note"] = None
    # PROX-001: new keys
    m["Proximity_Condition_Label"] = None; m["Proximity_Condition_Desc"] = None
    m["Proximity_Distance_Unit"] = None
    m["Exit_Signal"] = "CLEAR"; m["Exit_Triggers"] = []
    m["Exit_Reason"] = None
    m["Exit_VWAP_Counter"] = None; m["Exit_EMA8_Counter"] = None
    m["Established_Hourly_Low"] = None
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
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
    m["Price"] = 152.0; m["ADV_20"] = 5000000.0; m["ADV_20_Dollar"] = 50000000.0; m["Is_ETF"] = False
    m["ETF_Detection_Source"] = None; m["ETF_Primary_Exchange"] = None
    m["Convexity_Class"] = "C1"
    m["Entry_Reference"] = 142.0
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


def _valid_action_summary():
    return {
        "verdict": "VALID", "reason": "PULLBACK",
        "quality": "HEALTHY", "reward": "HEALTHY [2.8]",
        "exit_warning": False, "exit_warning_note": None,
        "trigger_rule": "BAR CLOSE ONLY", "trigger_condition": "test",
        "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        "state": "TRENDING", "action": "Execute.", "context": "Test.",
    }


def _invalid_action_summary():
    return {
        "verdict": "INVALID", "reason": "EXTENDED",
        "approaching": False, "action": "WAIT.", "context": "Test.",
    }


# -----------------------------------------------------------------------
# Group Structure
# -----------------------------------------------------------------------

class TestGroupStructure:

    def test_top_level_keys(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        expected = {"data_basis", "action_summary", "trade_snapshot", "trade_quality",
                    "trade_risk", "trend_state",
                    "floor_analysis", "trade_setup", "extension_analysis",
                    "psychological_levels", "entry_proximity", "exit_signals"}
        assert set(r.keys()) == expected

    def test_no_status_key(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert "status" not in r

    def test_no_diagnostic_key(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert "diagnostic" not in r

    def test_debug_absent_by_default(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert "_debug" not in r

    def test_debug_present_when_requested(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics(), debug=True)
        assert "_debug" in r

    def test_reading_order(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert list(r.keys()) == [
            "data_basis", "action_summary", "trade_snapshot", "trade_quality",
            "trade_risk", "trend_state", "floor_analysis",
            "trade_setup", "extension_analysis", "psychological_levels",
            "entry_proximity", "exit_signals"]

    def test_action_summary_first_key(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        keys = list(r.keys())
        assert keys[0] == "data_basis"       # PE-42: data_basis before action_summary
        assert keys[1] == "action_summary"


# -----------------------------------------------------------------------
# Trade Snapshot — DD-3
# -----------------------------------------------------------------------

class TestTradeSnapshot:

    def test_no_entry_strategy_in_trade_snapshot(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert "entry_strategy" not in r["trade_snapshot"]

    def test_trade_snapshot_has_expected_keys(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert len(r["trade_snapshot"]) == 8  # SNAP-001 restructured + BUG-R1

    def test_trade_snapshot_keys(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert set(r["trade_snapshot"].keys()) == {
            "price", "structural_floor", "resistance",
            "support_resistance_note",
            "atr", "avg_daily_volume",
            "classification", "price_levels"}

    def test_support_resistance_values(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert r["trade_snapshot"]["structural_floor"]["price"] == 142.0
        assert r["trade_snapshot"]["resistance"]["price"] == 160.0

    def test_current_price(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert r["trade_snapshot"]["price"]["current"] == 152.0


# -----------------------------------------------------------------------
# Other groups unchanged
# -----------------------------------------------------------------------

class TestUnchangedGroups:

    def test_trade_quality_structure(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        tq = r["trade_quality"]
        assert "trend_health" in tq
        assert "volume" in tq
        assert tq["trend_health"]["score"]["value"] == 72.5

    def test_trade_risk_structure(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert r["trade_risk"]["price_reward_risk"]["value"] == 3.5

    def test_trend_state_structure(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert r["trend_state"]["classification"]["state"]["label"] == "TRENDING"

    def test_price_indicators(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert r["trade_snapshot"]["price_levels"]["ema_8"]["price"] == 150.0

    def test_floor_analysis(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert "higher_frame" in r["floor_analysis"]

    def test_trade_setup(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert "stop" in r["trade_setup"]

    def test_entry_proximity(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert r["entry_proximity"]["signal"]["label"] == "NONE"

    def test_exit_signals(self):
        r = _transform_output(_valid_action_summary(), _make_full_flat_metrics())
        assert r["exit_signals"]["signal"]["label"] == "CLEAR"


# -----------------------------------------------------------------------
# Mapping integrity
# -----------------------------------------------------------------------

class TestMappingIntegrity:

    def test_total_mapped_keys(self):
        assert len(MAPPED_FLAT_KEYS) >= 165  # SelfDoc Batch 1: +13 new keys

    def test_audit_clean(self):
        assert len(_audit_key_coverage(_make_full_flat_metrics())) == 0

    def test_trade_setup_total(self):
        total = sum(len(t) for _, t in _TRADE_SETUP_SUBGROUPS)
        assert total == 0  # ENG-004: +2 (MM), PSY-001: +2 (Psych_Ceiling, Psych_Ceiling_Near_Technical)
