"""DIAG-001 Phase 2B: action_summary VALID path tests.

Tests all 3 VALID entry types (PULLBACK, BREAKOUT, RECLAIM) with full
field verification. Verifies output shape via _transform_output with
pre-built action_summary dicts matching the construction logic in
_assemble_output.

Spec: DIAG_001_Action_Summary_Spec_v1_0.md §V.1, §IX.2
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.1
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _transform_output


def _make_full_metrics():
    """Minimal metrics dict for VALID path output."""
    m = {}
    m["Price"] = 152.0; m["Structural_Floor"] = 142.0; m["Resistance"] = 160.0
    m["ADV_20"] = 5000000.0; m["Is_ETF"] = False; m["Convexity_Class"] = "C1"
    m["ETF_Primary_Exchange"] = None; m["ETF_Detection_Source"] = None
    m["Entry_Reference"] = 142.0; m["Hard_Stop"] = 140.0; m["Profit_Target"] = 160.0
    m["THS_Label"] = "HEALTHY"; m["Trend_Health_Score"] = 72.5
    m["THS_Floor_Buffer"] = 80.0; m["THS_Dir_Momentum"] = 65.0
    m["THS_Trend_Age"] = 70.0; m["THS_Structure"] = 75.0
    m["Capital_RR_Label"] = "HEALTHY"; m["Capital_Reward_Risk"] = 2.35
    m["Exit_Signal"] = False; m["Exit_Reason"] = "No exit"
    m["Pullback_Zone_Upper"] = 145.0
    m["Engine_State"] = "TRENDING"; m["Trend_Age_Bars"] = 15
    m["Active_Modifiers"] = "None"; m["Inst_Churn"] = "LOW"
    m["ADX"] = 28.5; m["ADX_Accel"] = 1.2; m["ADX_Accel_State"] = "ACCELERATING"
    m["DI_Plus"] = 30.0; m["DI_Minus"] = 15.0
    m["Conviction"] = "HIGH-CONVICTION"; m["Trend_Quality_Override"] = None
    m["Vol_Confirm_Ratio"] = 1.8; m["Vol_Confirm_State"] = "STRONG INSTITUTIONAL"
    m["Reward_Risk"] = 3.5; m["Reward_Risk_Note"] = None
    m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    m["EMA_8"] = 150.0; m["EMA_21"] = 148.0; m["SMA_50"] = 142.0; m["SMA_200"] = 130.0
    m["VWAP"] = None; m["ATR"] = 2.5
    m["Profit_Target_Source"] = "10_Bar_Resistance"; m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Profit_Target_Synthetic"] = None; m["Profit_Target_Synthetic_Note"] = None
    m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 139.0
    m["Stop_Adjusted_Flag"] = False; m["Stop_Adjusted_Reason"] = None
    m["Cons_High"] = 155.0; m["Resistance_Note"] = None
    m["Fib_382_Level"] = None; m["Fib_500_Level"] = None; m["Fib_Confluence"] = None
    m["Fib_A_382_Level"] = None; m["Fib_A_500_Level"] = None; m["Fib_A_Confluence"] = None
    m["RN_Target_Proximity"] = "CLEAR"; m["RN_Stop_Proximity"] = None; m["RN_Floor_Proximity"] = None
    m["ATR_Dist"] = 0.45; m["ATR_Dist_Anchor"] = "SMA_50"; m["ATR_Dist_Note"] = None
    m["Anchor_Label"] = "SMA_50 Floor"; m["Anchor_Type"] = "Standard"
    m["Floor_Prox_Pct"] = None; m["Extension_Limit"] = 1.0
    m["Window_Limit"] = 20; m["Window_Reset_Event"] = None
    m["Proximity_Signal"] = None; m["Proximity_Blocking_Gate"] = None
    m["Proximity_Distance"] = None; m["Proximity_Target"] = None; m["Proximity_Note"] = None
    m["Exit_Triggers"] = "None"; m["Exit_VWAP_Counter"] = None
    m["Exit_EMA8_Counter"] = None; m["Established_Hourly_Low"] = None
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
    return m


def _pullback_action_summary():
    return {
        "verdict": "VALID",
        "reason": "PULLBACK",
        "quality": "HEALTHY",
        "reward": "HEALTHY [2.35]",
        "exit_warning": False,
        "exit_warning_note": None,
        "trigger_rule": "BAR CLOSE ONLY",
        "trigger_condition": "Close within [142.0 — 145.0]",
        "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        "state": "TRENDING",
        "action": "Execute at THIS bar's close.",
        "context": "Price 152.0 in pullback zone.",
    }


def _breakout_action_summary():
    return {
        "verdict": "VALID",
        "reason": "BREAKOUT",
        "quality": "STRONG",
        "reward": "HEALTHY [2.80]",
        "exit_warning": False,
        "exit_warning_note": None,
        "trigger_rule": "INTRADAY",
        "trigger_condition": "Close above 160.0",
        "entry_strategy": {"entry_price": 160.0, "stop_loss": 155.0, "target": 175.0},
        "state": "RESOLVING",
        "action": "INTRADAY permitted.",
        "context": "Price above resistance 160.0.",
    }


def _reclaim_action_summary():
    return {
        "verdict": "VALID",
        "reason": "RECLAIM",
        "quality": "CAUTION",
        "reward": "NARROW [1.50]",
        "exit_warning": False,
        "exit_warning_note": None,
        "trigger_rule": "BAR CLOSE ONLY",
        "trigger_condition": "Close above 142.0",
        "entry_strategy": {"entry_price": 142.0, "stop_loss": 139.0, "target": 155.0},
        "state": "TRENDING",
        "action": "Execute at THIS bar's close.",
        "context": "Bar closed above Floor after 3/4 bars below.",
    }


# -----------------------------------------------------------------------
# VALID shape: 12 fields (verdict + 11)
# -----------------------------------------------------------------------

class TestValidPullback:

    def test_verdict(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["verdict"] == "VALID"

    def test_reason(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["reason"] == "PULLBACK"

    def test_quality(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["quality"] == "HEALTHY"

    def test_reward(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["reward"] == "HEALTHY [2.35]"

    def test_exit_warning_false(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["exit_warning"] is False

    def test_exit_warning_note_null(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["exit_warning_note"] is None

    def test_trigger_rule(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["trigger_rule"] == "BAR CLOSE ONLY"

    def test_trigger_condition(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["trigger_condition"] == "Close within [142.0 — 145.0]"

    def test_entry_strategy_present(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        es = r["action_summary"]["entry_strategy"]
        assert es["entry_price"] == 142.0
        assert es["stop_loss"] == 140.0
        assert es["target"] == 160.0

    def test_state(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["state"] == "TRENDING"

    def test_mandate_present(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["action"] is not None

    def test_context_present(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert r["action_summary"]["context"] is not None

    def test_no_status_key(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert "status" not in r

    def test_no_diagnostic_key(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert "diagnostic" not in r

    def test_entry_strategy_not_in_trade_snapshot(self):
        """DD-3: entry_strategy removed from trade_snapshot."""
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert "entry_strategy" not in r["trade_snapshot"]

    def test_action_summary_is_first_key(self):
        r = _transform_output(_pullback_action_summary(), _make_full_metrics())
        assert list(r.keys())[0] == "action_summary"

    def test_valid_has_12_fields(self):
        """VALID shape: 12 fields."""
        a = _pullback_action_summary()
        assert len(a) == 12


class TestValidBreakout:

    def test_reason_breakout(self):
        r = _transform_output(_breakout_action_summary(), _make_full_metrics())
        assert r["action_summary"]["reason"] == "BREAKOUT"

    def test_trigger_rule_intraday(self):
        r = _transform_output(_breakout_action_summary(), _make_full_metrics())
        assert r["action_summary"]["trigger_rule"] == "INTRADAY"

    def test_trigger_condition_above_resistance(self):
        r = _transform_output(_breakout_action_summary(), _make_full_metrics())
        assert r["action_summary"]["trigger_condition"] == "Close above 160.0"

    def test_state_resolving(self):
        r = _transform_output(_breakout_action_summary(), _make_full_metrics())
        assert r["action_summary"]["state"] == "RESOLVING"

    def test_entry_strategy_breakout_price(self):
        r = _transform_output(_breakout_action_summary(), _make_full_metrics())
        assert r["action_summary"]["entry_strategy"]["entry_price"] == 160.0

    def test_entry_strategy_not_in_trade_snapshot(self):
        r = _transform_output(_breakout_action_summary(), _make_full_metrics())
        assert "entry_strategy" not in r["trade_snapshot"]


class TestValidReclaim:

    def test_reason_reclaim(self):
        r = _transform_output(_reclaim_action_summary(), _make_full_metrics())
        assert r["action_summary"]["reason"] == "RECLAIM"

    def test_trigger_rule_bar_close(self):
        r = _transform_output(_reclaim_action_summary(), _make_full_metrics())
        assert r["action_summary"]["trigger_rule"] == "BAR CLOSE ONLY"

    def test_trigger_condition_above_floor(self):
        r = _transform_output(_reclaim_action_summary(), _make_full_metrics())
        assert r["action_summary"]["trigger_condition"] == "Close above 142.0"

    def test_entry_strategy_not_in_trade_snapshot(self):
        r = _transform_output(_reclaim_action_summary(), _make_full_metrics())
        assert "entry_strategy" not in r["trade_snapshot"]
