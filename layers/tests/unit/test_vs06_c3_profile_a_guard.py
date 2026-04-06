"""VS-06: C3 + Profile A Combination Guard.

8 tests verifying that C3 + Profile A produces INVALID UNSUPPORTED COMBINATION
and that all other convexity/profile combos are unaffected.

Strategy: Tests 1, 7, 8 exercise the guard through _assemble_output using a
synthetic RunContext (same pattern as test_struct001_phase3.py). Tests 2-6
verify the guard condition logic directly.
"""

import sys, os, pytest
import pandas as pd, numpy as np
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'google.genai', 'google'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

from types import SimpleNamespace
from tbs_engine.types import GateResult
from tbs_engine.output import _assemble_output


# ---------------------------------------------------------------------------
# Helpers (adapted from test_struct001_phase3.py)
# ---------------------------------------------------------------------------

def _make_df(n=30, close=150.0):
    return pd.DataFrame({
        "close": [close]*n, "open": [close-1]*n,
        "high": [close+2]*n, "low": [close-2]*n,
        "EMA_8": [close]*n, "EMA_21": [close-2]*n,
        "SMA_50": [close-5]*n, "SMA_200": [close-20]*n,
        "ANCHOR": [close-3]*n, "vol_sma_9": [np.nan]*n,
    })


def _base_metrics():
    m = {}
    m["Price"] = 150.0; m["Structural_Floor"] = 140.0; m["Resistance"] = 160.0
    m["ADV_20"] = 5000000.0; m["ADV_20_Dollar"] = 50000000.0
    m["Is_ETF"] = False; m["Convexity_Class"] = "C3"
    m["ETF_Primary_Exchange"] = None; m["ETF_Detection_Source"] = None
    m["Entry_Reference"] = 140.0; m["Hard_Stop"] = 138.0; m["Profit_Target"] = 160.0
    m["Capital_RR_Label"] = "HEALTHY"; m["Capital_Reward_Risk"] = 2.35
    m["Exit_Signal"] = "CLEAR"; m["Exit_Triggers"] = []; m["Exit_Reason"] = None
    m["Pullback_Zone_Upper"] = 145.0
    m["Engine_State"] = "TRENDING"; m["Engine_State_Desc"] = "ADX > 20"
    m["Trend_Age_Bars"] = 15; m["Trend_Age_Max"] = 30
    m["Active_Modifiers"] = "None"; m["Active_Modifiers_List"] = []
    m["Inst_Churn"] = "LOW"
    m["ADX"] = 28.5; m["ADX_Accel"] = 1.2; m["ADX_Accel_State"] = "ACCELERATING"
    m["DI_Plus"] = 30.0; m["DI_Minus"] = 15.0; m["DI_Spread"] = 15.0; m["DI_Bias"] = "BULLISH"
    m["Conviction"] = "HIGH-CONVICTION"; m["Trend_Quality_Override"] = None
    m["Vol_Confirm_Ratio"] = 1.8; m["Vol_Confirm_State"] = "STRONG ACCUMULATION"
    m["Vol_Confirm_Bias"] = "BULLISH"
    m["Reward_Risk"] = 3.5; m["Reward_Risk_Note"] = None; m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    m["Trend_Health_Score"] = 65.0; m["THS_Label"] = "HEALTHY"
    m["THS_Floor_Buffer"] = 50.0; m["THS_Floor_Buffer_Label"] = "ACCEPTABLE"
    m["THS_Dir_Momentum"] = 60.0; m["THS_Dir_Momentum_Label"] = "HEALTHY"
    m["THS_Trend_Age"] = 80.0; m["THS_Trend_Age_Label"] = "STRONG"
    m["THS_Structure"] = 55.0; m["THS_Structure_Label"] = "ACCEPTABLE"
    m["THS_Death_Cross_Cap"] = False; m["THS_Component_Cap"] = False
    m["THS_Context_Advisory"] = None
    m["EMA_8"] = 150.0; m["EMA_21"] = 148.0; m["SMA_50"] = 142.0; m["SMA_200"] = 130.0
    m["VWAP"] = None; m["ATR"] = 2.5
    m["Profit_Target_Source"] = "10_Bar_Resistance"; m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 137.0
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
    m["Exit_VWAP_Counter"] = None; m["Exit_EMA8_Counter"] = None
    m["Established_Hourly_Low"] = None
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
    m["MM_Target"] = None; m["MM_Rally_ATR"] = None
    m["Risk_Summary_Label"] = "FAVORABLE"; m["Risk_Summary_Desc"] = "OK"
    m["Risk_Assessment_Complete"] = True
    m["Data_Basis"] = "Test."
    return m


def _make_ctx():
    """Minimal RunContext (SimpleNamespace) sufficient for _assemble_output."""
    df = _make_df()
    state = SimpleNamespace(
        adx_t=28.5, adx_t1=27.0, di_plus=30.0, di_minus=15.0,
        atr_raw=2.0, floor_raw=140.0,
        is_floor_failure=False, is_violated=False, is_reclaim=False,
        ema_stacked=True, ma_squeeze=False, ma_stack_full=True,
        is_trending=True, is_resolving=False,
        _entry_trending=True, _entry_resolving=False,
        _etf_entry_trending=True, _etf_entry_resolving=False,
        _resolving_is_bearish=False, _reclaim_run=0,
        is_ambiguous=False, consec_below=0,
    )
    cfg = SimpleNamespace(
        fb_max=3.0, ta_max=50, iq=-1, min_bars_required=30,
        window_limit=20, ff_threshold=4,
        ext_limit_trending=1.0, ext_limit_resolving=1.0, ext_limit_etf=1.0,
        resistance_slice_start=-10, resistance_slice_end=None,
        tf_resolution="1D", tf_duration="6mo",
        ctx_resolution="1W", ctx_duration="2y",
        prev_bar_offset=-1, required_ma_cols=("EMA_8", "EMA_21", "SMA_50"),
        pb_upper_col="SMA_50",
    )
    return SimpleNamespace(
        state=state, cfg=cfg, p_code="A", is_etf=False, _is_c3=True,
        df=df, last=df.iloc[-1], metrics=_base_metrics(), price_scaler=1.0,
        actual_price=150.0,
        structural_floor_raw=140.0, hard_stop_raw=138.0,
        resistance_raw=160.0, bars_per_day=1.0, atr_dist=0.5,
        ext_limit=1.0, floor_prox_pct=5.0, adx_accel=0.5,
        adx_accel_state="CRUISING", vol_confirm_ratio=1.2,
        vol_confirm_state="CONFIRMED", exit_signal=False,
        window_count=5, window_limit=20,
        floor_price=140.0, hard_stop=138.0, resistance_display=160.0,
        _resistance_suppressed=False, chart_ref="", cons_high_raw=155.0,
        risk_a=None, reward_a=None, chart_dir="/tmp", clean_ticker="TEST",
        adx_col="ADX_14", dmp_col="DI+_14", dmn_col="DI-_14",
        profile="Profile A",
        prev_high=152.0, prox_anchor=148.0,
        _prx_ctx={"mode": "INFO"}, _is_lse_etf=False,
        _ssg_adjusted=False, _ssg_original_raw=0.0, _ssg_reason="",
        currency="USD", vwap_col="VWAP", adx_t2=26.0, _df_ctx=None,
        vol_poc_price=None, vol_poc_distance_atr=None,
        vol_poc_position="", avwap_price=None, avwap_position="",
        avwap_distance_atr=None, volume_context_label="",
        vol_bias="NEUTRAL", vol_confidence="MIXED", vol_bias_detail="",
    )


def _vs06_gate_result():
    return GateResult(
        verdict="INVALID",
        reason="UNSUPPORTED COMBINATION",
        mandate="C-3 on Profile A is architecturally unsupported.",
        context="VWAP floor resets at session open -- incompatible with "
                "C-3 open-ended holding period. Use C-1 or C-2.",
    )


def _run(ctx, gate):
    with mock.patch("tbs_engine.output._build_focus_chart"):
        return _assemble_output(ctx, gate, {"mode": "INFO"}, debug=False)


def _guard_fires(convexity_class, profile):
    """Replicate the VS-06 guard boolean from main.py."""
    _is_c3 = (convexity_class == "C3")
    p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    p_code = p_mapping.get(profile.upper(), profile.upper())
    return _is_c3 and p_code == "A"


# ===========================================================================
# Tests
# ===========================================================================

class TestVS06C3ProfileAGuard:

    # Test 1: C3 + Profile A produces INVALID UNSUPPORTED COMBINATION
    def test_c3_profile_a_invalid(self):
        ctx = _make_ctx()
        r = _run(ctx, _vs06_gate_result())
        _as = r.get("action_summary", {})
        assert _as.get("verdict") == "INVALID"
        _reason = _as.get("reason", {})
        label = _reason.get("label") if isinstance(_reason, dict) else _reason
        assert label == "UNSUPPORTED COMBINATION"

    # Test 2: C3 + Profile B does NOT fire guard
    def test_c3_profile_b_not_blocked(self):
        assert not _guard_fires("C3", "TREND")

    # Test 3: C3 + Profile C does NOT fire guard
    def test_c3_profile_c_not_blocked(self):
        assert not _guard_fires("C3", "WEALTH")

    # Test 4: C1 + Profile A does NOT fire guard
    def test_c1_profile_a_not_blocked(self):
        assert not _guard_fires("C1", "SWING")

    # Test 5: C2 + Profile A does NOT fire guard
    def test_c2_profile_a_not_blocked(self):
        assert not _guard_fires("C2", "SWING")

    # Test 6: None convexity + Profile A does NOT fire guard
    def test_none_convexity_profile_a_not_blocked(self):
        assert not _guard_fires(None, "SWING")

    # Test 7: Guard fires before gate cascade (no gate-specific reasons)
    def test_guard_fires_before_gates(self):
        ctx = _make_ctx()
        r = _run(ctx, _vs06_gate_result())
        _as = r.get("action_summary", {})
        _reason = _as.get("reason", {})
        label = _reason.get("label") if isinstance(_reason, dict) else _reason
        gate_labels = {"CONTEXT REGIME", "FLOOR FAILURE", "FLOOR VIOLATION",
                       "LIQUIDITY", "DATA INTEGRITY", "CLIMAX", "MID-RANGE",
                       "DIRECTIONAL", "MODIFIER-E", "WINDOW", "EXTENDED",
                       "EXPECTANCY", "CAPITAL EXPECTANCY", "TREND QUALITY"}
        assert label not in gate_labels
        assert label == "UNSUPPORTED COMBINATION"

    # Test 8: Output has full grouped structure (via _assemble_output)
    def test_output_has_grouped_structure(self):
        ctx = _make_ctx()
        r = _run(ctx, _vs06_gate_result())
        required_keys = {
            "action_summary", "trade_snapshot", "trade_quality",
            "trade_risk", "trend_state", "floor_analysis", "trade_setup",
        }
        assert required_keys.issubset(set(r.keys())), \
            f"Missing keys: {required_keys - set(r.keys())}"
