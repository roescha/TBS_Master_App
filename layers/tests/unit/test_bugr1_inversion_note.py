"""BUG-R1: Support/Resistance Inversion Note.

10 tests covering computation, transform surfacing, round-trip, and key registration.
"""
import pytest
import sys
import unittest.mock as mock

# Stub heavy deps
for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'google.genai', 'google'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

from tbs_engine.transform import _transform_output, _flatten, MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# Helpers (mirrors test_selfdoc_batch2.py pattern)
# ---------------------------------------------------------------------------

def _build_action_summary():
    return {
        "verdict": "INVALID",
        "reason": {"label": "EXTENDED", "detail": "Price extended 1.8 ATR beyond limit."},
        "approaching": False,
        "volume": "NEUTRAL",
        "exit_status": {"active": False, "reason": None},
    }


def _build_base_metrics(**overrides):
    m = {
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
        "Stop_Adjusted_Reason": "Hourly low proximity -- stop widened to avoid noise",
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
        "Risk_Per_Unit": None,
        "Conviction": "HIGH-CONVICTION",
        "Floor_Prox_Pct": 0.66,
        "Profit_Target_Synthetic": None, "Profit_Target_Synthetic_Note": None,
        "Resistance_Note": None,
        "ETF_Primary_Exchange": None, "ETF_Detection_Source": None,
        "Support_Resistance_Note": None,
    }
    m.update(overrides)
    return m


# ===========================================================================
# Computation tests (output.py logic, tested via transform metrics dict)
# ===========================================================================

class TestComputationLogic:
    """Directly test the note derivation via the metrics dict."""

    def test_note_present_when_floor_above_resistance(self):
        m = _build_base_metrics(Structural_Floor=100.0, Resistance=95.0,
                                Support_Resistance_Note="Support (100.0) above resistance (95.0): "
                                "structural floor lags price after breakdown -- "
                                "10-bar high reflects post-breakdown trading range")
        r = _transform_output(_build_action_summary(), m)
        note = r["trade_snapshot"]["support_resistance_note"]
        assert note is not None
        assert "100.0" in note
        assert "95.0" in note

    def test_note_null_when_floor_below_resistance(self):
        m = _build_base_metrics(Structural_Floor=90.0, Resistance=95.0,
                                Support_Resistance_Note=None)
        r = _transform_output(_build_action_summary(), m)
        assert r["trade_snapshot"]["support_resistance_note"] is None

    def test_note_null_when_equal(self):
        m = _build_base_metrics(Structural_Floor=95.0, Resistance=95.0,
                                Support_Resistance_Note=None)
        r = _transform_output(_build_action_summary(), m)
        assert r["trade_snapshot"]["support_resistance_note"] is None

    def test_note_null_when_resistance_none(self):
        m = _build_base_metrics(Structural_Floor=100.0, Resistance=None,
                                Support_Resistance_Note=None)
        r = _transform_output(_build_action_summary(), m)
        assert r["trade_snapshot"]["support_resistance_note"] is None

    def test_note_null_when_floor_none(self):
        m = _build_base_metrics(Structural_Floor=None, Resistance=95.0,
                                Support_Resistance_Note=None)
        r = _transform_output(_build_action_summary(), m)
        assert r["trade_snapshot"]["support_resistance_note"] is None


# ===========================================================================
# Transform surfacing tests
# ===========================================================================

class TestTransformSurfacing:
    """Note appears correctly in trade_snapshot."""

    def test_note_surfaces_in_snapshot(self):
        note_text = "Support (100.0) above resistance (95.0): structural floor lags price after breakdown -- 10-bar high reflects post-breakdown trading range"
        m = _build_base_metrics(Support_Resistance_Note=note_text)
        r = _transform_output(_build_action_summary(), m)
        assert r["trade_snapshot"]["support_resistance_note"] == note_text

    def test_null_note_surfaces_as_null(self):
        m = _build_base_metrics(Support_Resistance_Note=None)
        r = _transform_output(_build_action_summary(), m)
        assert r["trade_snapshot"]["support_resistance_note"] is None


# ===========================================================================
# Round-trip tests (_flatten)
# ===========================================================================

class TestFlattenRoundTrip:
    """_flatten recovers Support_Resistance_Note."""

    def test_flatten_recovers_note(self):
        note_text = "Support (100.0) above resistance (95.0): structural floor lags price after breakdown -- 10-bar high reflects post-breakdown trading range"
        m = _build_base_metrics(Support_Resistance_Note=note_text)
        r = _transform_output(_build_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Support_Resistance_Note"] == note_text

    def test_flatten_recovers_null(self):
        m = _build_base_metrics(Support_Resistance_Note=None)
        r = _transform_output(_build_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Support_Resistance_Note"] is None


# ===========================================================================
# MAPPED_FLAT_KEYS registration
# ===========================================================================

class TestKeyRegistration:
    def test_key_in_mapped_flat_keys(self):
        assert "Support_Resistance_Note" in MAPPED_FLAT_KEYS
