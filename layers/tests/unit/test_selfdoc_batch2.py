"""SelfDoc Batch 2 -- Unit Tests.

Covers: VOL-003, FA-001, SNAP-001, SETUP-001, EXT-001, PSY-002, AS-001.
Tests grouped output shapes, label derivation, _flatten() backward compat.

Run: pytest tests/unit/test_selfdoc_batch2.py -v
"""
import pytest
from tbs_engine.transform import _transform_output, _flatten, MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_action_summary(verdict="INVALID"):
    if verdict == "VALID":
        return {
            "verdict": "VALID",
            "reason": {"label": "PULLBACK", "detail": "All gates passed. Pullback to VWAP confirmed."},
            "mandate": "BUY. Close within pullback zone. Execute at market.",
            "merit": {"quality": "HEALTHY", "reward": "HEALTHY [2.15]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Close within [217.0 -- 218.94]"},
            "volume": "ACCUMULATION DOMINANT",
            "entry_strategy": {"entry_price": 217.0, "stop_loss": 207.83, "target": 241.37},
            "exit_status": {"active": False, "reason": None},
        }
    elif verdict == "WAIT":
        return {
            "verdict": "WAIT",
            "reason": {"label": "TREND QUALITY", "detail": "THS 37 <= 50 (WEAK). Sub-scores: Floor_Buffer=19, Dir_Momentum=13, Trend_Age=100, Structure=57."},
            "approaching": False,
            "volume": "ACCUMULATION DOMINANT",
            "exit_status": {"active": False, "reason": None},
        }
    return {
        "verdict": "INVALID",
        "reason": {"label": "EXTENDED", "detail": "Price extended 1.8 ATR beyond limit."},
        "approaching": False,
        "volume": "NEUTRAL",
        "exit_status": {"active": False, "reason": None},
    }


def _build_base_metrics():
    return {
        "Price": 218.44, "Structural_Floor": 217.0, "Resistance": 225.5,
        "ADV_20": 4353443, "ADV_20_Dollar": 50000000,
        "Is_ETF": False, "Convexity_Class": "C-2",
        "EMA_8": 218.36, "EMA_21": 217.01, "SMA_50": 216.41, "SMA_200": 223.11,
        "ATR": 3.89, "VWAP": 217.0,
        "Engine_State": "TRENDING", "Engine_State_Desc": "ADX > 20 + full MA stack + no squeeze",
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
        # VOL-003
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
        # FA-001
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
        # SETUP-001
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
        # EXT-001
        "ATR_Dist": 0.38, "ATR_Dist_Anchor": "VWAP",
        "ATR_Dist_Note": None, "Extension_Limit": 1.5,
        "Trend_Quality_Override": None,
        # PSY-002
        "Psych_Floor": 200.0, "Psych_Ceiling": 225.0,
        "Psych_Floor_Dist_Pct": 8.44, "Psych_Ceiling_Dist_Pct": 3.0,
        "Psych_Floor_Near_Technical": False, "Psych_Floor_Near_Structural": False,
        "Psych_Ceiling_Near_Technical": True, "Psych_Increment": 25.0,
        "RN_Target_Proximity": "CLEAR", "RN_Stop_Proximity": "CLEAR",
        "RN_Floor_Proximity": "CLEAR",
        # Risk
        "Reward_Risk": 3.5, "Reward_Risk_Note": None,
        "Capital_Reward_Risk": 2.15, "Capital_RR_Label": "HEALTHY",
        "Risk_Summary_Label": "FAVORABLE", "Risk_Summary_Desc": "Price R:R 3.50 >= 2.0. Capital R:R 2.15 (HEALTHY).",
        "Expectancy_Threshold": 2.0, "Expectancy_Threshold_Note": None,
        "Data_Basis": "SWING analysis based on completed bar 09:30-10:30 ET.",
    }


# ===========================================================================
# VOL-003: Volume Output Self-Documentation + RVOL
# ===========================================================================

class TestVOL003RVOLLabels:
    """RVOL label band derivation."""

    @pytest.mark.parametrize("val,expected", [
        (0.3, "QUIET"), (0.6, "BELOW AVERAGE"), (1.0, "NORMAL"),
        (1.5, "ELEVATED"), (2.5, "HIGH"), (4.0, "EXTREME"),
    ])
    def test_rvol_label_band(self, val, expected):
        if val < 0.5: label = "QUIET"
        elif val < 0.8: label = "BELOW AVERAGE"
        elif val < 1.2: label = "NORMAL"
        elif val < 2.0: label = "ELEVATED"
        elif val < 3.0: label = "HIGH"
        else: label = "EXTREME"
        assert label == expected


class TestVOL003VocabReplacements:
    """Volume vocabulary updated from institutional to accumulation."""

    def test_strong_accumulation_in_output(self):
        m = _build_base_metrics()
        assert m["Vol_Confirm_State"] == "STRONG ACCUMULATION"

    def test_accumulation_dominant_label(self):
        m = _build_base_metrics()
        assert m["Vol_Summary_Label"] == "ACCUMULATION DOMINANT"


class TestVOL003VolumeSection:
    """Volume section in trade_quality has correct structure."""

    def test_volume_summary_present(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        vol = r["trade_quality"]["volume"]
        assert "summary" in vol
        assert vol["summary"]["label"] == "ACCUMULATION DOMINANT"
        assert vol["summary"]["bias"] == "BULLISH"
        assert vol["summary"]["confidence"] == "SPLIT"

    def test_rvol_present(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        vol = r["trade_quality"]["volume"]
        assert vol["rvol"]["value"] == 1.35
        assert vol["rvol"]["label"] == "ELEVATED"

    def test_confirmation_ratio(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        vol = r["trade_quality"]["volume"]
        assert vol["confirmation_ratio"]["value"] == 0.85
        assert vol["confirmation_ratio"]["label"] == "STRONG ACCUMULATION"
        assert vol["confirmation_ratio"]["bias"] == "BULLISH"

    def test_poc_structure(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        poc = r["trade_quality"]["volume"]["poc"]
        assert poc["price"] == 216.62
        assert poc["position"] == "ABOVE_POC"
        assert poc["bias"] == "BULLISH"
        assert poc["distance_atr"]["value"] == 0.47

    def test_avwap_structure(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        avwap = r["trade_quality"]["volume"]["avwap"]
        assert avwap["price"] == 219.49
        assert avwap["position"] == "BELOW"
        assert avwap["bias"] == "BEARISH"

    def test_avg_daily_dollar_volume_in_volume(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        vol = r["trade_quality"]["volume"]
        assert vol["avg_daily_dollar_volume"]["value"] == 50000000
        assert vol["avg_daily_dollar_volume"]["unit"] == "USD"


# ===========================================================================
# FA-001: Floor Analysis Self-Documentation
# ===========================================================================

class TestFA001Anchor:
    """Floor analysis anchor sub-object."""

    def test_anchor_structure(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        anchor = r["floor_analysis"]["anchor"]
        assert anchor["type"] == "VWAP"
        assert anchor["label"] == "Intraday institutional value level"
        assert anchor["price"] == 217.0

    def test_floor_failure_clear(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        ff = r["floor_analysis"]["floor_failure"]
        assert ff["status"]["label"] == "CLEAR"

    def test_higher_frame_ema(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        hf = r["floor_analysis"]["higher_frame"]
        assert hf is not None
        assert hf["ema"]["ema_8"] == 220.15
        assert hf["ema"]["stacked"] is True
        assert hf["ema"]["bias"]["label"] == "BULLISH"


# ===========================================================================
# SNAP-001: Trade Snapshot Self-Documentation
# ===========================================================================

class TestSNAP001TradeSnapshot:
    """Trade snapshot restructured with price_levels."""

    def test_price_object(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        p = r["trade_snapshot"]["price"]
        assert p["current"] is not None
        assert "source" in p
        assert p["source"]["label"] is not None

    def test_price_levels_present(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        pl = r["trade_snapshot"]["price_levels"]
        assert pl["ema_8"]["price"] == 218.36
        assert pl["sma_50"]["price"] == 216.41

    def test_atr_object(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        atr = r["trade_snapshot"]["atr"]
        assert atr["value"] == 3.89
        assert atr["period"] == 14

    def test_classification_convexity_desc(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        cls = r["trade_snapshot"]["classification"]
        assert cls["convexity"]["label"] == "C-2"
        assert "mechanical exit" in cls["convexity"]["desc"].lower()

    def test_no_price_indicators_section(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        assert "price_indicators" not in r


# ===========================================================================
# SETUP-001: Trade Setup Self-Documentation
# ===========================================================================

class TestSETUP001TradeSetup:
    """Trade setup reduced from 8 to 5 sub-groups."""

    def test_five_subgroups(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        ts = r["trade_setup"]
        assert set(ts.keys()) == {"target", "stop", "entry_zone", "rally", "execution_window"}

    def test_target_role_compulsory(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        tgt = r["trade_setup"]["target"]
        assert tgt["role"]["label"] == "COMPULSORY"

    def test_stop_adjustment(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        stop = r["trade_setup"]["stop"]
        assert stop["adjustment"]["adjusted"] is True
        assert stop["adjustment"]["original_price"] == 211.16

    def test_rally_projected_move(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        rally = r["trade_setup"]["rally"]
        assert rally is not None
        assert rally["projected_move"]["price"] == 250.12


# ===========================================================================
# EXT-001: Extension Analysis Self-Documentation
# ===========================================================================

class TestEXT001ExtensionAnalysis:
    """New top-level extension_analysis section."""

    def test_section_present(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        assert "extension_analysis" in r

    def test_distance_structure(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        ext = r["extension_analysis"]
        assert ext["distance"]["value"] == 0.38
        assert ext["distance"]["unit"] == "ATR"

    def test_anchor_matches_fa001(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        ext_anchor = r["extension_analysis"]["anchor"]["label"]
        fa_anchor = r["floor_analysis"]["anchor"]["type"]
        assert ext_anchor == fa_anchor


# ===========================================================================
# PSY-002: Psychological Levels Self-Documentation
# ===========================================================================

class TestPSY002PsychologicalLevels:
    """New top-level psychological_levels section."""

    def test_section_present(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        assert "psychological_levels" in r

    def test_increment_surfaced(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        psy = r["psychological_levels"]
        assert psy["increment"]["value"] == 25.0

    def test_ceiling_distance_pct(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        psy = r["psychological_levels"]
        assert psy["ceiling"]["distance_pct"] == 3.0

    def test_near_structural_floor_renamed(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        psy = r["psychological_levels"]
        assert "near_structural_floor" in psy["floor"]

    def test_at_target_clear(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        psy = r["psychological_levels"]
        assert psy["at_target"]["label"] == "CLEAR"

    def test_fields_not_in_floor_analysis(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        fa = r["floor_analysis"]
        assert "psych_floor" not in fa
        assert "psych_floor_dist_pct" not in fa
        assert "psych_near_technical" not in fa


# ===========================================================================
# AS-001: Action Summary Self-Documentation
# ===========================================================================

class TestAS001ActionSummaryWAIT:
    """WAIT verdict action_summary structure."""

    def test_reason_is_dict(self):
        r = _transform_output(_build_action_summary("WAIT"), _build_base_metrics())
        reason = r["action_summary"]["reason"]
        assert isinstance(reason, dict)
        assert reason["label"] == "TREND QUALITY"
        assert "Sub-scores" in reason["detail"]

    def test_ths_abbreviations_expanded(self):
        r = _transform_output(_build_action_summary("WAIT"), _build_base_metrics())
        detail = r["action_summary"]["reason"]["detail"]
        assert "Floor_Buffer=" in detail
        assert "Dir_Momentum=" in detail
        assert "Trend_Age=" in detail
        assert "Structure=" in detail

    def test_exit_status(self):
        r = _transform_output(_build_action_summary("WAIT"), _build_base_metrics())
        es = r["action_summary"]["exit_status"]
        assert es["active"] is False
        assert es["reason"] is None

    def test_volume_key(self):
        r = _transform_output(_build_action_summary("WAIT"), _build_base_metrics())
        assert "volume" in r["action_summary"]
        assert "volume_context" not in r["action_summary"]


class TestAS001ActionSummaryVALID:
    """VALID verdict action_summary structure."""

    def test_mandate_present(self):
        r = _transform_output(_build_action_summary("VALID"), _build_base_metrics())
        assert "mandate" in r["action_summary"]
        assert "action" not in r["action_summary"]

    def test_merit_merged(self):
        r = _transform_output(_build_action_summary("VALID"), _build_base_metrics())
        merit = r["action_summary"]["merit"]
        assert merit["quality"] == "HEALTHY"
        assert "HEALTHY" in merit["reward"]

    def test_trigger_merged(self):
        r = _transform_output(_build_action_summary("VALID"), _build_base_metrics())
        trigger = r["action_summary"]["trigger"]
        assert trigger["rule"] == "BAR CLOSE ONLY"
        assert "Close within" in trigger["condition"]


class TestAS001ActionSummaryINVALID:
    """INVALID verdict action_summary structure."""

    def test_no_mandate_on_invalid(self):
        r = _transform_output(_build_action_summary("INVALID"), _build_base_metrics())
        assert "mandate" not in r["action_summary"]

    def test_no_merit_on_invalid(self):
        r = _transform_output(_build_action_summary("INVALID"), _build_base_metrics())
        assert "merit" not in r["action_summary"]

    def test_no_trigger_on_invalid(self):
        r = _transform_output(_build_action_summary("INVALID"), _build_base_metrics())
        assert "trigger" not in r["action_summary"]


# ===========================================================================
# _flatten() round-trip tests
# ===========================================================================

class TestFlattenRoundTrip:
    """_flatten extracts same flat keys from new grouped structure."""

    def test_vol_context_label_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("Volume_Context_Label") == "ACCUMULATION DOMINANT"

    def test_vol_confirm_ratio_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("Vol_Confirm_Ratio") == 0.85

    def test_psych_floor_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("Psych_Floor") == 200.0

    def test_psych_ceiling_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("Psych_Ceiling") == 225.0

    def test_atr_dist_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("ATR_Dist") == 0.38

    def test_exit_status_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("Exit_Signal_Active") is False

    def test_price_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("EMA_8") == 218.36
        assert flat.get("SMA_50") == 216.41

    def test_profit_target_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("Profit_Target") == 241.37

    def test_hard_stop_roundtrip(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        _, _, flat = _flatten(r)
        assert flat.get("Hard_Stop") == 207.83


# ===========================================================================
# Top-level section count
# ===========================================================================

class TestSectionCount:
    """Final section count: 15 (Batch 2 + IVR-001 + RLY-001 rally_state)."""

    def test_twelve_sections(self):
        r = _transform_output(_build_action_summary(), _build_base_metrics())
        expected = {
            "data_basis", "action_summary", "trade_snapshot", "trade_quality",
            "trade_risk", "trend_state", "floor_analysis", "trade_setup",
            "extension_analysis", "psychological_levels", "volatility_regime",
            "rally_state",
            "entry_proximity", "exit_signals", "recovery_analysis",
        }
        assert set(r.keys()) == expected
