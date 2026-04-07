"""PE-44: Rally Confluence — rename assessment → confluence, populate desc.

Tests trigger × label desc derivation and _flatten() backward compat.
Run: pytest tests/unit/test_pe44_confluence.py -v
"""
import pytest
from tbs_engine.transform import _transform_output, _flatten


# ---------------------------------------------------------------------------
# Helpers (minimal — reuse pattern from test_selfdoc_batch2)
# ---------------------------------------------------------------------------

def _as(verdict="INVALID"):
    return {
        "verdict": verdict,
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
        "ATR_Dist_Note": None, "Extension_Limit": 1.5,
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


def _get_confluence(trigger, label):
    """Build metrics with given trigger and fib label, return confluence sub-object."""
    m = _metrics(
        Window_Reset_Event=trigger,
        Fib_A_Confluence=label,
    )
    r = _transform_output(_as(), m)
    rally = r.get("trade_setup", {}).get("rally", {})
    return rally.get("confluence", {})


# ===========================================================================
# PULLBACK trigger
# ===========================================================================

class TestPE44PullbackConfluence:
    def test_pullback_confluence_382(self):
        c = _get_confluence("PULLBACK", "CONFLUENCE_382")
        assert "Institutional floor" in c["desc"]
        assert "38.2%" in c["desc"]

    def test_pullback_confluence_500(self):
        c = _get_confluence("PULLBACK", "CONFLUENCE_500")
        assert "Institutional floor" in c["desc"]
        assert "50%" in c["desc"]

    def test_pullback_above_fibs(self):
        c = _get_confluence("PULLBACK", "ABOVE_FIBS")
        assert "Above institutional support" in c["desc"]

    def test_pullback_between_fibs(self):
        c = _get_confluence("PULLBACK", "BETWEEN_FIBS")
        assert "Caution" in c["desc"]

    def test_pullback_below_fibs(self):
        c = _get_confluence("PULLBACK", "BELOW_FIBS")
        assert "Warning" in c["desc"]


# ===========================================================================
# RECLAIM trigger
# ===========================================================================

class TestPE44ReclaimConfluence:
    def test_reclaim_confluence_382(self):
        c = _get_confluence("RECLAIM", "CONFLUENCE_382")
        assert "Warning" in c["desc"]
        assert "resistance" in c["desc"]

    def test_reclaim_confluence_500(self):
        c = _get_confluence("RECLAIM", "CONFLUENCE_500")
        assert "Warning" in c["desc"]
        assert "resistance" in c["desc"]

    def test_reclaim_above_fibs(self):
        c = _get_confluence("RECLAIM", "ABOVE_FIBS")
        assert "Cleared" in c["desc"]

    def test_reclaim_between_fibs(self):
        c = _get_confluence("RECLAIM", "BETWEEN_FIBS")
        assert "Caution" in c["desc"]

    def test_reclaim_below_fibs(self):
        c = _get_confluence("RECLAIM", "BELOW_FIBS")
        assert "Early recovery" in c["desc"]


# ===========================================================================
# BREAKOUT trigger
# ===========================================================================

class TestPE44BreakoutConfluence:
    def test_breakout_any_label(self):
        c = _get_confluence("BREAKOUT", "ABOVE_FIBS")
        assert c["label"] is None
        assert "not applicable" in c["desc"]

    def test_breakout_between_fibs_still_null(self):
        c = _get_confluence("BREAKOUT", "BETWEEN_FIBS")
        assert c["label"] is None


# ===========================================================================
# Structural
# ===========================================================================

class TestPE44Structural:
    def test_field_named_confluence_not_assessment(self):
        m = _metrics()
        r = _transform_output(_as(), m)
        rally = r.get("trade_setup", {}).get("rally", {})
        assert "confluence" in rally
        assert "assessment" not in rally

    def test_no_rally_when_no_fib_data(self):
        m = _metrics(
            Fib_A_382_Level=None, Fib_A_500_Level=None, MM_Target=None,
        )
        r = _transform_output(_as(), m)
        rally = r.get("trade_setup", {}).get("rally")
        assert rally is None

    def test_flatten_fib_a_confluence_roundtrip(self):
        m = _metrics(Window_Reset_Event="PULLBACK", Fib_A_Confluence="CONFLUENCE_382")
        grouped = _transform_output(_as(), m)
        _, _, flat = _flatten(grouped)
        assert flat.get("Fib_A_Confluence") == "CONFLUENCE_382"
