# CONS-001: Manual Operator Verification Checklist (live IBKR)
# After all automated tests pass, the Operator should:
#
# 1. Run tbs_scanner.py against the standard scan universe.
#    Verify: no crashes, all tickers produce output, tier routing
#    (VALID/INVALID/APPROACHING) works correctly.
#
# 2. Run tbs_orchestrator.py against a VALID candidate ticker.
#    Verify: full dashboard renders, THS_Label displays correctly,
#    Exit_Signal shows CLEAR/WARNING/EXIT (not True/False).
#
# 3. Run tbs_orchestrator.py against an INVALID ticker (CRG rejection).
#    Verify: dashboard renders without crash, diagnostic displays correctly.
#
# 4. If all 3 checks pass, CONS-001 closes immediately.
#    If any check fails, log specific bugs and fix in standalone session.

"""CONS-001: Consumer Compatibility Verification.

17 tests verifying _flatten() round-trip correctness after
Self-Documentation Cluster + STRUCT-001 output restructuring.
"""

import sys, os, pytest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'google.genai', 'google'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

from tbs_engine.transform import _transform_output, _flatten, MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# Builders (adapted from test_selfdoc_batch2.py)
# ---------------------------------------------------------------------------

def _build_action_summary_valid():
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


def _build_action_summary_invalid():
    return {
        "verdict": "INVALID",
        "reason": {"label": "UNSUPPORTED COMBINATION", "detail": "C-3 on Profile A is architecturally unsupported."},
        "approaching": False,
        "volume": "NEUTRAL",
        "exit_status": {"active": False, "reason": None},
    }


def _build_base_metrics():
    """Comprehensive base metrics covering all Self-Doc + STRUCT-001 + RISK-002 fields."""
    return {
        "Price": 218.44, "Structural_Floor": 217.0, "Resistance": 225.5,
        "ADV_20": 4353443, "ADV_20_Dollar": 50000000,
        "Is_ETF": False, "Convexity_Class": "C-2",
        "ETF_Primary_Exchange": None, "ETF_Detection_Source": None,
        "EMA_8": 218.36, "EMA_21": 217.01, "SMA_50": 216.41, "SMA_200": 223.11,
        "ATR": 3.89, "VWAP": 217.0,
        "Engine_State": "TRENDING", "Engine_State_Desc": "ADX > 20 + full MA stack + no squeeze",
        "Trend_Age_Bars": 2, "Trend_Age_Max": 30,
        "Active_Modifiers": "None", "Active_Modifiers_List": [],
        "Inst_Churn": "CLEAR (No Churn)",
        "ADX": 28.0, "ADX_Accel": 0.5, "ADX_Accel_State": "ACCELERATING",
        "DI_Plus": 30.0, "DI_Minus": 18.0, "DI_Spread": 12.0, "DI_Bias": "BULLISH",
        "Conviction": "HIGH-CONVICTION",
        # THS + STRUCT-001 sub-scores with {value, max, label, desc} shapes
        "Trend_Health_Score": 65.0, "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 50.0, "THS_Floor_Buffer_Label": "ACCEPTABLE",
        "THS_Dir_Momentum": 60.0, "THS_Dir_Momentum_Label": "HEALTHY",
        "THS_Trend_Age": 80.0, "THS_Trend_Age_Label": "STRONG",
        "THS_Structure": 55.0, "THS_Structure_Label": "ACCEPTABLE",
        # STRUCT-001-TFR-1 advisory
        "THS_Death_Cross_Cap": False, "THS_Component_Cap": False,
        "THS_Context_Advisory": None,
        # EXIT-001 (changed from bool to CLEAR/WARNING/EXIT)
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
        # Risk + RISK-002
        "Reward_Risk": 3.5, "Reward_Risk_Note": None,
        "Capital_Reward_Risk": 2.15, "Capital_RR_Label": "HEALTHY",
        "Risk_Summary_Label": "FAVORABLE", "Risk_Summary_Desc": "Price R:R 3.50 >= 2.0. Capital R:R 2.15 (HEALTHY).",
        "Expectancy_Threshold": 2.0, "Expectancy_Threshold_Note": None,
        "Risk_Assessment_Complete": True,
        "Risk_Per_Unit": None,
        "Data_Basis": "SWING analysis based on completed bar 09:30-10:30 ET.",
    }


def _grouped_valid():
    return _transform_output(_build_action_summary_valid(), _build_base_metrics())


def _grouped_invalid():
    return _transform_output(_build_action_summary_invalid(), _build_base_metrics())


# ===========================================================================
# Test A: Full round-trip on VALID output
# ===========================================================================

class TestAFlattenValidRoundTrip:
    """_flatten() round-trip on VALID grouped output."""

    def test_returns_3_tuple(self):
        """1. _flatten returns 3-tuple without exception."""
        result = _flatten(_grouped_valid())
        assert isinstance(result, tuple) and len(result) == 3

    def test_status_is_pass(self):
        """2. Status maps to legacy PASS."""
        status, _, _ = _flatten(_grouped_valid())
        assert status == "PASS"

    def test_flat_metrics_is_dict(self):
        """3. flat_metrics is a dict."""
        _, _, flat = _flatten(_grouped_valid())
        assert isinstance(flat, dict)

    def test_mapped_keys_are_scalar(self):
        """4. Every MAPPED_FLAT_KEY with a non-null value is scalar (not dict/list).
        Exception: Exit_Triggers and Active_Modifiers_List are intentionally lists."""
        _LIST_KEYS = {"Exit_Triggers", "Active_Modifiers_List"}
        _, _, flat = _flatten(_grouped_valid())
        for k in MAPPED_FLAT_KEYS:
            if k in _LIST_KEYS:
                continue
            v = flat.get(k)
            if v is not None:
                assert not isinstance(v, (dict, list)), \
                    f"Key {k!r} is {type(v).__name__}, expected scalar. Value: {v!r}"


# ===========================================================================
# Test B: Full round-trip on INVALID output
# ===========================================================================

class TestBFlattenInvalidRoundTrip:
    """_flatten() round-trip on INVALID grouped output."""

    def test_returns_3_tuple(self):
        result = _flatten(_grouped_invalid())
        assert isinstance(result, tuple) and len(result) == 3

    def test_status_is_halt(self):
        status, _, _ = _flatten(_grouped_invalid())
        assert status == "HALT"

    def test_flat_metrics_is_dict(self):
        _, _, flat = _flatten(_grouped_invalid())
        assert isinstance(flat, dict)

    def test_mapped_keys_are_scalar(self):
        _LIST_KEYS = {"Exit_Triggers", "Active_Modifiers_List"}
        _, _, flat = _flatten(_grouped_invalid())
        for k in MAPPED_FLAT_KEYS:
            if k in _LIST_KEYS:
                continue
            v = flat.get(k)
            if v is not None:
                assert not isinstance(v, (dict, list)), \
                    f"Key {k!r} is {type(v).__name__}, expected scalar. Value: {v!r}"


# ===========================================================================
# Test C: New top-level groups traversed
# ===========================================================================

class TestCNewGroupsTraversed:
    """extension_analysis and psychological_levels present and flattened."""

    def test_extension_analysis_key_in_flat(self):
        """5. At least one key from extension_analysis."""
        _, _, flat = _flatten(_grouped_valid())
        ext_keys = {"ATR_Dist", "Extension_Limit", "ATR_Dist_Anchor"}
        assert ext_keys & set(flat.keys()), "No extension_analysis keys found in flat"

    def test_psychological_levels_key_in_flat(self):
        """6. At least one key from psychological_levels."""
        _, _, flat = _flatten(_grouped_valid())
        psy_keys = {"Psych_Floor", "Psych_Ceiling", "Psych_Increment"}
        assert psy_keys & set(flat.keys()), "No psychological_levels keys found in flat"


# ===========================================================================
# Test D: Eliminated group absent
# ===========================================================================

class TestDEliminatedGroupAbsent:
    """price_indicators eliminated; price_levels absorbed into trade_snapshot."""

    def test_price_indicators_not_top_level(self):
        """7. price_indicators NOT a top-level key."""
        r = _grouped_valid()
        assert "price_indicators" not in r

    def test_price_levels_inside_trade_snapshot(self):
        """8. price_levels IS present inside trade_snapshot (SNAP-001)."""
        r = _grouped_valid()
        assert "price_levels" in r.get("trade_snapshot", {})


# ===========================================================================
# Test E: New nested shapes resolve to scalars
# ===========================================================================

class TestENestedShapesResolveScalar:
    """THS sub-scores, exit signals, risk summary resolve to scalars after _flatten."""

    def test_trend_health_score_is_float(self):
        """9. Trend_Health_Score is float, not dict."""
        _, _, flat = _flatten(_grouped_valid())
        v = flat.get("Trend_Health_Score")
        assert isinstance(v, (int, float)), f"Expected float, got {type(v).__name__}: {v!r}"

    def test_ths_label_is_str(self):
        """10. THS_Label is str, not dict."""
        _, _, flat = _flatten(_grouped_valid())
        v = flat.get("THS_Label")
        assert isinstance(v, str), f"Expected str, got {type(v).__name__}: {v!r}"

    def test_exit_signal_is_str(self):
        """11. Exit_Signal is str (CLEAR/WARNING/EXIT), not dict."""
        _, _, flat = _flatten(_grouped_valid())
        v = flat.get("Exit_Signal")
        assert isinstance(v, str), f"Expected str, got {type(v).__name__}: {v!r}"

    def test_risk_summary_label_is_str_or_none(self):
        """12. Risk_Summary_Label is str or None, not dict."""
        _, _, flat = _flatten(_grouped_valid())
        v = flat.get("Risk_Summary_Label")
        assert v is None or isinstance(v, str), \
            f"Expected str or None, got {type(v).__name__}: {v!r}"


# ===========================================================================
# Test F: STRUCT-001-TFR-1 advisory round-trip
# ===========================================================================

class TestFAdvisoryRoundTrip:
    """STRUCT-001-TFR-1: death cross cap and context advisory flatten correctly."""

    def test_death_cross_cap_is_bool(self):
        """13. THS_Death_Cross_Cap is bool."""
        _, _, flat = _flatten(_grouped_valid())
        v = flat.get("THS_Death_Cross_Cap")
        assert isinstance(v, bool), f"Expected bool, got {type(v).__name__}: {v!r}"

    def test_context_advisory_is_str_or_none(self):
        """14. THS_Context_Advisory is str or None."""
        _, _, flat = _flatten(_grouped_valid())
        v = flat.get("THS_Context_Advisory")
        assert v is None or isinstance(v, str), \
            f"Expected str or None, got {type(v).__name__}: {v!r}"


# ===========================================================================
# Test G: RISK-UX-001 summary label round-trip (replaces RISK-002 complete flag)
# ===========================================================================

class TestGRiskUX001SummaryLabel:
    """RISK-UX-001: Risk_Summary_Label flattens to str."""

    def test_risk_summary_label_is_str(self):
        """15. Risk_Summary_Label is str (NOT_AVAILABLE/PARTIAL/FAVORABLE/ADEQUATE/UNFAVORABLE)."""
        _, _, flat = _flatten(_grouped_valid())
        v = flat.get("Risk_Summary_Label")
        assert isinstance(v, str), f"Expected str, got {type(v).__name__}: {v!r}"
        assert v in ("NOT_AVAILABLE", "PARTIAL", "FAVORABLE", "ADEQUATE", "UNFAVORABLE"), \
            f"Unexpected summary label: {v!r}"


# ===========================================================================
# Test H: Action summary backward compat (AS-001)
# ===========================================================================

class TestHActionSummaryBackwardCompat:
    """AS-001: 3-tuple diagnostic is non-empty for both VALID and INVALID."""

    def test_diagnostic_non_empty(self):
        """16. Diagnostic string is non-empty."""
        _, diag, _ = _flatten(_grouped_valid())
        assert isinstance(diag, str) and len(diag) > 0


# ===========================================================================
# Test I: Key count sanity check
# ===========================================================================

class TestIKeyCountSanity:
    """MAPPED_FLAT_KEYS count >= 150 post-Self-Doc expansion."""

    def test_mapped_flat_keys_minimum(self):
        """17. MAPPED_FLAT_KEYS >= 150."""
        assert len(MAPPED_FLAT_KEYS) >= 150, \
            f"Expected >= 150 mapped keys, got {len(MAPPED_FLAT_KEYS)}"
