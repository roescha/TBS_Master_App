"""EXT-OBS-001: Extension Distance Condition Label — Unit Tests.

Tests 5-band mapping, effective limit respect, null handling, and _flatten().
Run: pytest tests/unit/test_extobs001_condition.py -v
"""
import pytest
from tbs_engine.transform import _transform_output, _flatten


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as():
    return {
        "verdict": "INVALID",
        "reason": {"label": "EXTENDED", "detail": "n/a"},
        "approaching": False,
        "volume": "NEUTRAL",
        "exit_status": {"active": False, "reason": None},
    }


def _metrics(**overrides):
    base = {
        "Price": 218.44, "Structural_Floor": 217.0, "Resistance": 225.5,
        "ADV_20": 4353443, "ADV_20_Dollar": 50000000,
        "Is_ETF": False, "Convexity_Class": "C-2",
        "EMA_8": 218.36, "EMA_21": 217.01, "SMA_50": 216.41, "SMA_200": 223.11,
        "ATR": 3.89, "VWAP": 217.0,
        "Engine_State": "TRENDING", "Engine_State_Desc": "ADX > 20",
        "Trend_Age_Bars": 2, "Trend_Age_Max": 30,
        "Active_Modifiers": "None", "Active_Modifiers_List": [],
        "Inst_Churn": "CLEAR (No Churn)",
        "ADX": 28.0, "ADX_Accel": 0.5, "ADX_Accel_State": "ACCELERATING",
        "DI_Plus": 30.0, "DI_Minus": 18.0, "DI_Spread": 12.0, "DI_Bias": "BULLISH",
        "Trend_Health_Score": 65.0, "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 50.0, "THS_Floor_Buffer_Label": "ACCEPTABLE",
        "THS_Dir_Momentum": 60.0, "THS_Dir_Momentum_Label": "HEALTHY",
        "THS_Trend_Age": 80.0, "THS_Trend_Age_Label": "STRONG",
        "THS_Structure": 55.0, "THS_Structure_Label": "ACCEPTABLE",
        "Exit_Signal": "CLEAR", "Exit_Triggers": [], "Exit_Reason": None,
        "Vol_Confirm_Ratio": 0.85, "Vol_Confirm_State": "STRONG ACCUMULATION",
        "Vol_Confirm_Bias": "BULLISH",
        "Vol_PoC_Price": 216.62, "Vol_PoC_Distance_ATR": 0.47,
        "Vol_PoC_Position": "ABOVE_POC", "PoC_Bias": "BULLISH",
        "PoC_Bias_Desc": "In profit at this level -- acts as support",
        "AVWAP_Price": 219.49, "AVWAP_Position": "BELOW",
        "AVWAP_Distance_ATR": -0.53,
        "AVWAP_Bias": "BEARISH", "AVWAP_Bias_Desc": "Price below avg cost -- overhead resistance",
        "Volume_Context_Label": "ACCUMULATION DOMINANT",
        "Vol_Summary_Label": "ACCUMULATION DOMINANT",
        "Vol_Summary_Bias": "BULLISH", "Vol_Summary_Confidence": "SPLIT",
        "Vol_Summary_Detail": "Ratio BULLISH + PoC BULLISH + AVWAP BEARISH",
        "Vol_Histogram_Period": "3 days",
        "RVOL_Value": 1.35, "RVOL_Label": "ELEVATED",
        "Anchor_Label": "VWAP (Baseline Floor)", "Anchor_Type": "Standard",
        "Floor_Anchor_Type": "VWAP", "Floor_Anchor_Label": "Intraday institutional value level",
        "Extension_Anchor_Type": "VWAP", "Extension_Anchor_Label": "Intraday institutional value level",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Failure_Context": None, "Floor_Breach_Dist": None,
        "Floor_Failure_Reclaim": None, "Floor_Failure_Threshold": 8,
        "Context_SMA50_Slope_Bias": "BEARISH",
        "Context_Golden_Cross": True, "Context_Price_vs_SMA200": 60.14,
        "Context_SMA200": 158.3, "Context_Daily_SMA50": 226.71,
        "Context_Daily_SMA50_Slope": -0.2,
        "Context_EMA_8": 220.15, "Context_EMA_21": 218.90,
        "Context_EMA_Stacked": True, "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "Daily EMA 8 above Daily EMA 21",
        "Profit_Target": 241.37, "Profit_Target_Source": "DAILY_CTX",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "Hard_Stop": 207.83, "Hard_Stop_Note": None,
        "Original_Hard_Stop": 211.16, "Stop_Adjusted_Flag": True,
        "Stop_Adjusted_Reason": "Hourly low proximity",
        "Pullback_Zone_Upper": 218.94, "Entry_Reference": 217.0,
        "Fib_A_382_Level": 217.94, "Fib_A_500_Level": 216.90,
        "Fib_A_Confluence": "BETWEEN_FIBS",
        "MM_Target": 250.12, "MM_Rally_ATR": 2.3,
        "Window_Limit": 4, "Window_Reset_Event": "PULLBACK",
        "window_count": 2,
        "ATR_Dist": 0.38, "ATR_Dist_Anchor": "VWAP",
        "ATR_Dist_Note": None, "Extension_Limit": 2.0,
        "Trend_Quality_Override": None,
        "Psych_Floor": 200.0, "Psych_Ceiling": 225.0,
        "Psych_Floor_Dist_Pct": 8.44, "Psych_Ceiling_Dist_Pct": 3.0,
        "Psych_Floor_Near_Technical": False, "Psych_Floor_Near_Structural": False,
        "Psych_Ceiling_Near_Technical": True, "Psych_Increment": 25.0,
        "RN_Target_Proximity": "CLEAR", "RN_Stop_Proximity": "CLEAR",
        "RN_Floor_Proximity": "CLEAR",
        "Reward_Risk": 3.5, "Reward_Risk_Note": None,
        "Capital_Reward_Risk": 2.15, "Capital_RR_Label": "HEALTHY",
        "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Price R:R 3.50 >= 2.0. Capital R:R 2.15 (HEALTHY).",
        "Expectancy_Threshold": 2.0, "Expectancy_Threshold_Note": None,
        "Data_Basis": "SWING analysis based on completed bar 09:30-10:30 ET.",
    }
    base.update(overrides)
    return base


def _get_condition(atr_dist, ext_limit=2.0, eff_limit=None):
    overrides = {"ATR_Dist": atr_dist, "Extension_Limit": ext_limit}
    if eff_limit is not None:
        overrides["Extension_Limit_Effective"] = eff_limit
    m = _metrics(**overrides)
    r = _transform_output(_as(), m)
    ext = r.get("extension_analysis", {})
    return ext.get("condition", {})


# ===========================================================================
# Band boundary tests
# ===========================================================================

class TestExtObs001Bands:
    def test_overextended(self):
        c = _get_condition(2.5)
        assert c["label"] == "OVEREXTENDED"
        assert "Warning" in c["desc"]

    def test_elevated(self):
        c = _get_condition(1.5)
        assert c["label"] == "ELEVATED"
        assert "Caution" in c["desc"]

    def test_elevated_exact_boundary(self):
        c = _get_condition(1.0)
        assert c["label"] == "ELEVATED"

    def test_normal(self):
        c = _get_condition(0.5)
        assert c["label"] == "NORMAL"
        assert "Healthy" in c["desc"]

    def test_normal_exact_boundary(self):
        c = _get_condition(0.25)
        assert c["label"] == "NORMAL"

    def test_at_floor(self):
        c = _get_condition(0.1)
        assert c["label"] == "AT_FLOOR"
        assert "Optimal" in c["desc"]

    def test_at_floor_zero(self):
        c = _get_condition(0.0)
        assert c["label"] == "AT_FLOOR"

    def test_at_floor_exact_lower_boundary(self):
        c = _get_condition(-0.25)
        assert c["label"] == "AT_FLOOR"

    def test_below_floor(self):
        c = _get_condition(-0.5)
        assert c["label"] == "BELOW_FLOOR"
        assert "Warning" in c["desc"]

    def test_null_atr_dist(self):
        c = _get_condition(None)
        assert c["label"] is None
        assert "not available" in c["desc"]


# ===========================================================================
# Effective limit tests
# ===========================================================================

class TestExtObs001EffectiveLimit:
    def test_breakout_exemption_elevated(self):
        """eff_limit=3.0, atr_dist=2.5 → ELEVATED (not OVEREXTENDED)."""
        c = _get_condition(2.5, ext_limit=2.0, eff_limit=3.0)
        assert c["label"] == "ELEVATED"

    def test_breakout_exemption_overextended(self):
        """eff_limit=3.0, atr_dist=3.5 → OVEREXTENDED."""
        c = _get_condition(3.5, ext_limit=2.0, eff_limit=3.0)
        assert c["label"] == "OVEREXTENDED"


# ===========================================================================
# Structural
# ===========================================================================

class TestExtObs001Structural:
    def test_condition_exists_in_extension_analysis(self):
        m = _metrics()
        r = _transform_output(_as(), m)
        ext = r.get("extension_analysis", {})
        assert "condition" in ext
        assert "label" in ext["condition"]
        assert "desc" in ext["condition"]

    def test_flatten_extension_condition(self):
        m = _metrics(ATR_Dist=0.5)
        grouped = _transform_output(_as(), m)
        _, _, flat = _flatten(grouped)
        assert flat.get("Extension_Condition") == "NORMAL"
