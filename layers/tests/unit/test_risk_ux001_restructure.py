"""RISK-UX-001: Trade Risk Structural Cleanup + Blue Sky Relocation — Unit Tests.

25 test cases covering:
  1-8:   Summary label (five labels, risk_per_unit relocation, complete removal)
  9-14:  Blue sky relocation to trade_setup.target
  15-21: Fundamental restructure (fundamental_rr → fundamental_reward_risk)
  22-25: Intermediate restructure (bare value → object)
"""

import sys, os, pytest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'google.genai', 'google'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

from tbs_engine.transform import _transform_output, _flatten


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_metrics():
    """Comprehensive flat metrics dict for transform testing."""
    m = {}
    m["Price"] = 150.0; m["Structural_Floor"] = 140.0; m["Resistance"] = 160.0
    m["ADV_20"] = 5000000.0; m["ADV_20_Dollar"] = 50000000.0; m["Is_ETF"] = False
    m["Convexity_Class"] = "C1"
    m["ETF_Primary_Exchange"] = None; m["ETF_Detection_Source"] = None
    m["Entry_Reference"] = 140.0; m["Hard_Stop"] = 138.0; m["Profit_Target"] = 160.0
    m["Capital_RR_Label"] = "HEALTHY"; m["Capital_Reward_Risk"] = 2.35
    m["Exit_Signal"] = False; m["Exit_Reason"] = "No exit"
    m["Pullback_Zone_Upper"] = 145.0
    m["Engine_State"] = "TRENDING"; m["Trend_Age_Bars"] = 15
    m["Active_Modifiers"] = "None"; m["Inst_Churn"] = "LOW"
    m["ADX"] = 28.5; m["ADX_Accel"] = 1.2; m["ADX_Accel_State"] = "ACCELERATING"
    m["DI_Plus"] = 30.0; m["DI_Minus"] = 15.0
    m["Conviction"] = "HIGH-CONVICTION"; m["Trend_Quality_Override"] = None
    m["Vol_Confirm_Ratio"] = 1.8; m["Vol_Confirm_State"] = "STRONG ACCUMULATION"
    m["Reward_Risk"] = 3.5; m["Reward_Risk_Note"] = None; m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    m["EMA_8"] = 150.0; m["EMA_21"] = 148.0; m["SMA_50"] = 142.0; m["SMA_200"] = 130.0
    m["VWAP"] = None; m["ATR"] = 2.5
    m["Profit_Target_Source"] = "10_Bar_Resistance"
    m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Profit_Target_Synthetic"] = None; m["Profit_Target_Synthetic_Note"] = None
    m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 137.0
    m["Stop_Adjusted_Flag"] = False; m["Stop_Adjusted_Reason"] = None
    m["Cons_High"] = 155.0; m["Resistance_Note"] = None
    m["Fib_382_Level"] = None; m["Fib_500_Level"] = None; m["Fib_Confluence"] = None
    m["Fib_A_382_Level"] = None; m["Fib_A_500_Level"] = None; m["Fib_A_Confluence"] = None
    m["RN_Target_Proximity"] = "CLEAR"; m["RN_Stop_Proximity"] = None
    m["RN_Floor_Proximity"] = None
    m["ATR_Dist"] = 0.45; m["ATR_Dist_Anchor"] = "SMA_50"; m["ATR_Dist_Note"] = None
    m["Anchor_Label"] = "SMA_50 Floor"; m["Anchor_Type"] = "Standard"
    m["Floor_Prox_Pct"] = None; m["Extension_Limit"] = 1.0
    m["Window_Limit"] = 20; m["Window_Reset_Event"] = None
    m["Proximity_Signal"] = None; m["Proximity_Blocking_Gate"] = None
    m["Proximity_Distance"] = None; m["Proximity_Target"] = None
    m["Proximity_Note"] = None
    m["Proximity_Condition_Label"] = None; m["Proximity_Condition_Desc"] = None
    m["Proximity_Distance_Unit"] = None
    m["Exit_Triggers"] = "None"; m["Exit_VWAP_Counter"] = None
    m["Exit_EMA8_Counter"] = None; m["Established_Hourly_Low"] = None
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
    m["MM_Target"] = None; m["MM_Rally_ATR"] = None
    m["Risk_Summary_Label"] = None; m["Risk_Summary_Desc"] = None
    m["Vol_Confirm_Bias"] = None
    m["Vol_PoC_Price"] = None; m["Vol_PoC_Distance_ATR"] = None; m["Vol_PoC_Position"] = None
    m["AVWAP_Price"] = None; m["AVWAP_Position"] = None; m["AVWAP_Distance_ATR"] = None
    m["DI_Spread"] = None; m["DI_Bias"] = None
    # Blue sky defaults
    m["Blue_Sky_Detected"] = False; m["Blue_Sky_Target"] = None
    m["Blue_Sky_Method"] = None; m["Blue_Sky_ATR_Headroom"] = None
    # Fundamental defaults
    m["Fundamental_RR"] = None; m["Fundamental_RR_Label"] = None
    m["Fundamental_Target"] = None; m["Fundamental_Floor"] = None
    m["Fundamental_Target_High"] = None; m["Fundamental_Analyst_Count"] = None
    m["Fundamental_RR_Note"] = None
    return m


def _run(extra_metrics=None):
    m = _base_metrics()
    if extra_metrics:
        m.update(extra_metrics)
    action_summary = {"verdict": "VALID", "reason": "PULLBACK"}
    g = _transform_output(action_summary, m)
    return g


# ===========================================================================
# 1-8: Summary label tests
# ===========================================================================

class TestSummaryLabel:

    def test_01_not_available_no_rr_data(self):
        """No R:R data → label NOT_AVAILABLE."""
        g = _run({"Reward_Risk": None, "Capital_Reward_Risk": None,
                  "Capital_RR_Label": None, "Risk_Summary_Label": None})
        s = g["trade_risk"]["summary"]
        assert s["label"] == "NOT_AVAILABLE"
        assert "structural floor" in s["desc"]

    def test_02_partial_capital_rr_only(self):
        """Capital R:R only → label PARTIAL."""
        g = _run({"Reward_Risk": None, "Capital_Reward_Risk": 1.8,
                  "Capital_RR_Label": "HEALTHY", "Risk_Summary_Label": None})
        s = g["trade_risk"]["summary"]
        assert s["label"] == "PARTIAL"
        assert "Capital R:R" in s["desc"]
        assert "not computed" in s["desc"]

    def test_03_favorable(self):
        g = _run({"Risk_Summary_Label": "FAVORABLE",
                  "Risk_Summary_Desc": "Price R:R 3.50 >= 2.0. Capital R:R 2.15 (HEALTHY)."})
        assert g["trade_risk"]["summary"]["label"] == "FAVORABLE"

    def test_04_adequate(self):
        g = _run({"Risk_Summary_Label": "ADEQUATE",
                  "Risk_Summary_Desc": "Adequate."})
        assert g["trade_risk"]["summary"]["label"] == "ADEQUATE"

    def test_05_unfavorable(self):
        g = _run({"Risk_Summary_Label": "UNFAVORABLE",
                  "Risk_Summary_Desc": "Unfavorable."})
        assert g["trade_risk"]["summary"]["label"] == "UNFAVORABLE"

    def test_06_risk_per_unit_inside_summary(self):
        g = _run({"Risk_Per_Unit": 2.50, "Risk_Summary_Label": "FAVORABLE",
                  "Risk_Summary_Desc": "ok"})
        rpu = g["trade_risk"]["summary"]["risk_per_unit"]
        assert rpu is not None
        assert rpu["value"] == 2.50
        assert "desc" in rpu

    def test_07_risk_per_unit_null(self):
        g = _run({"Risk_Per_Unit": None, "Risk_Summary_Label": "FAVORABLE",
                  "Risk_Summary_Desc": "ok"})
        assert g["trade_risk"]["summary"]["risk_per_unit"] is None

    def test_08_complete_key_absent(self):
        g = _run()
        assert "complete" not in g["trade_risk"]


# ===========================================================================
# 9-14: Blue sky relocation tests
# ===========================================================================

class TestBlueSkyRelocation:

    def test_09_detected_in_target(self):
        g = _run({"Blue_Sky_Detected": True, "Blue_Sky_Target": 285.0,
                  "Blue_Sky_Method": "ATR_PROJECTION", "Blue_Sky_ATR_Headroom": 0.3,
                  "Profit_Target": 285.0})
        bs = g["trade_setup"]["target"]["blue_sky"]
        assert bs is not None
        assert bs["detected"] is True
        assert bs["method"] == "ATR_PROJECTION"
        assert bs["atr_headroom"] == 0.3
        assert "desc" in bs

    def test_10_not_detected_null(self):
        g = _run({"Blue_Sky_Detected": False})
        assert g["trade_setup"]["target"]["blue_sky"] is None

    def test_11_atr_projection_desc(self):
        g = _run({"Blue_Sky_Detected": True, "Blue_Sky_Method": "ATR_PROJECTION",
                  "Blue_Sky_ATR_Headroom": 0.3, "Profit_Target": 285.0})
        assert "ATR projection" in g["trade_setup"]["target"]["blue_sky"]["desc"]

    def test_12_measured_move_desc(self):
        g = _run({"Blue_Sky_Detected": True, "Blue_Sky_Method": "MEASURED_MOVE",
                  "Blue_Sky_ATR_Headroom": 0.3, "Profit_Target": 290.0})
        assert "measured move" in g["trade_setup"]["target"]["blue_sky"]["desc"]

    def test_13_trade_risk_no_blue_sky_keys(self):
        g = _run({"Blue_Sky_Detected": True, "Blue_Sky_Method": "ATR_PROJECTION",
                  "Blue_Sky_ATR_Headroom": 0.3, "Profit_Target": 285.0})
        tr = g["trade_risk"]
        for k in ("blue_sky_detected", "blue_sky_target", "blue_sky_method", "blue_sky_atr_headroom"):
            assert k not in tr, f"{k} should not be in trade_risk"

    def test_14_flatten_round_trip_blue_sky(self):
        g = _run({"Blue_Sky_Detected": True, "Blue_Sky_Target": 285.0,
                  "Blue_Sky_Method": "ATR_PROJECTION", "Blue_Sky_ATR_Headroom": 0.3,
                  "Profit_Target": 285.0})
        _, _, flat = _flatten(g)
        assert flat["Blue_Sky_Detected"] is True
        assert flat["Blue_Sky_Method"] == "ATR_PROJECTION"
        assert flat["Blue_Sky_ATR_Headroom"] == 0.3


# ===========================================================================
# 15-21: Fundamental restructure tests
# ===========================================================================

class TestFundamentalRestructure:

    def test_15_key_is_fundamental_reward_risk(self):
        g = _run()
        assert "fundamental_reward_risk" in g["trade_risk"]
        assert "fundamental_rr" not in g["trade_risk"]

    def test_16_analyst_levels_sub_object(self):
        g = _run({"Fundamental_Target": 150.0, "Fundamental_Floor": 90.0,
                  "Fundamental_Target_High": 200.0, "Fundamental_Analyst_Count": 10,
                  "Fundamental_RR": 5.0, "Fundamental_RR_Label": "STRONG"})
        al = g["trade_risk"]["fundamental_reward_risk"]["analyst_levels"]
        assert al is not None
        assert al["target"] == 150.0
        assert al["floor"] == 90.0
        assert al["ceiling"] == 200.0
        assert al["coverage"] == 10

    def test_17_analyst_levels_desc(self):
        g = _run({"Fundamental_Target": 150.0, "Fundamental_RR": 5.0})
        al = g["trade_risk"]["fundamental_reward_risk"]["analyst_levels"]
        assert "Institutional price levels" in al["desc"]

    def test_18_note_renamed_to_advisory(self):
        g = _run({"Fundamental_RR_Note": "Low coverage", "Fundamental_Target": 150.0,
                  "Fundamental_RR": 2.0})
        frr = g["trade_risk"]["fundamental_reward_risk"]
        assert "note" not in frr
        assert frr["advisory"] == "Low coverage"

    def test_19_root_desc(self):
        g = _run()
        frr = g["trade_risk"]["fundamental_reward_risk"]
        assert "Fundamental R:R" in frr["desc"]

    def test_20_no_data_analyst_levels_null(self):
        g = _run({"Fundamental_Target": None, "Fundamental_RR": None})
        assert g["trade_risk"]["fundamental_reward_risk"]["analyst_levels"] is None

    def test_21_flatten_round_trip_fundamental(self):
        g = _run({"Fundamental_Target": 150.0, "Fundamental_Floor": 90.0,
                  "Fundamental_Target_High": 200.0, "Fundamental_Analyst_Count": 10,
                  "Fundamental_RR": 5.0, "Fundamental_RR_Label": "STRONG",
                  "Fundamental_RR_Note": "Good coverage"})
        _, _, flat = _flatten(g)
        assert flat["Fundamental_RR"] == 5.0
        assert flat["Fundamental_RR_Label"] == "STRONG"
        assert flat["Fundamental_Target"] == 150.0
        assert flat["Fundamental_Floor"] == 90.0
        assert flat["Fundamental_Target_High"] == 200.0
        assert flat["Fundamental_Analyst_Count"] == 10
        assert flat["Fundamental_RR_Note"] == "Good coverage"


# ===========================================================================
# 22-25: Intermediate restructure tests
# ===========================================================================

class TestIntermediateRestructure:

    def test_22_intermediate_object_when_populated(self):
        g = _run({"Profit_Target_Synthetic": 155.0})
        inter = g["trade_setup"]["target"]["intermediate"]
        assert inter is not None
        assert inter["price"] == 155.0
        assert "method" in inter
        assert "desc" in inter

    def test_23_intermediate_method(self):
        g = _run({"Profit_Target_Synthetic": 155.0})
        assert g["trade_setup"]["target"]["intermediate"]["method"] == "Floor + 1.5 ATR"

    def test_24_intermediate_null_when_none(self):
        g = _run({"Profit_Target_Synthetic": None})
        assert g["trade_setup"]["target"]["intermediate"] is None

    def test_25_flatten_round_trip_intermediate(self):
        g = _run({"Profit_Target_Synthetic": 155.0})
        _, _, flat = _flatten(g)
        assert flat["Profit_Target_Synthetic"] == 155.0
