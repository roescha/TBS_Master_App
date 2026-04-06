"""RISK-002: Trade Risk Partial Population Annotation — complete flag.

12 test cases covering computation (output.py), transform, flatten round-trip,
MAPPED_FLAT_KEYS registration, and integration-style VALID/INVALID paths.

Spec: RISK002_Implementation_Prompt.md
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
from tbs_engine.output import _assemble_output, THS_GATE_THRESHOLD
from tbs_engine.transform import _transform_output, _flatten, MAPPED_FLAT_KEYS

# ============================================================================
# Helpers (from test_struct001_phase3.py pattern)
# ============================================================================

def _make_state(**kw):
    d = dict(
        adx_t=28.0, adx_t1=27.0, di_plus=30.0, di_minus=15.0,
        atr_raw=2.0, floor_raw=140.0,
        is_floor_failure=False, is_violated=False, is_reclaim=False,
        ema_stacked=True, ma_squeeze=False, ma_stack_full=True,
        is_trending=True, is_resolving=False,
        _entry_trending=True, _entry_resolving=False,
        _etf_entry_trending=True, _etf_entry_resolving=False,
        _resolving_is_bearish=False, _reclaim_run=0,
        is_ambiguous=False, consec_below=0,
    )
    d.update(kw)
    return SimpleNamespace(**d)


def _make_df(n=30, close=150.0, anchor=142.0, ema8=150.0, ema21=148.0,
             sma50=142.0, sma200=130.0):
    d = {
        "close": [close]*n, "open": [close-1]*n,
        "high": [close+2]*n, "low": [close-2]*n,
        "EMA_8": [ema8]*n, "EMA_21": [ema21]*n,
        "SMA_50": [sma50]*n, "SMA_200": [sma200]*n,
        "ANCHOR": [anchor]*n, "vol_sma_9": [np.nan]*n,
    }
    return pd.DataFrame(d)


def _base_metrics():
    m = {}
    m["Price"] = 150.0; m["Structural_Floor"] = 140.0; m["Resistance"] = 160.0
    m["ADV_20"] = 5000000.0; m["ADV_20_Dollar"] = 50000000.0; m["Is_ETF"] = False; m["Convexity_Class"] = "C1"
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
    return m


def _make_ctx(p_code="B", state_kw=None, extra_metrics=None):
    state = _make_state(**(state_kw or {}))
    df = _make_df()
    last = df.iloc[-1]
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
    metrics = _base_metrics()
    if extra_metrics:
        metrics.update(extra_metrics)
    profile_map = {'A': 'Profile A', 'B': 'Profile B', 'C': 'Profile C'}
    _is_c3 = (p_code == 'C')
    return SimpleNamespace(
        state=state, cfg=cfg, p_code=p_code, is_etf=False, _is_c3=_is_c3,
        df=df, last=last, metrics=metrics, price_scaler=1.0,
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
        profile=profile_map.get(p_code, "Profile B"),
        prev_high=152.0, prox_anchor=148.0,
        _prx_ctx={"mode": "INFO"}, _is_lse_etf=False,
        _ssg_adjusted=False, _ssg_original_raw=0.0, _ssg_reason="",
        currency="USD", vwap_col="VWAP", adx_t2=26.0,
        _df_ctx=None,
        vol_poc_price=None, vol_poc_distance_atr=None,
        vol_poc_position="", avwap_price=None, avwap_position="",
        avwap_distance_atr=None,
        volume_context_label="",
        vol_bias="NEUTRAL", vol_confidence="MIXED", vol_bias_detail="",
        is_c3=_is_c3, profile_map=profile_map,
    )


def _run(gate_label="VALID", gate_reason=None, p_code="B", extra_metrics=None):
    ctx = _make_ctx(p_code=p_code, extra_metrics=extra_metrics)
    if gate_label == "VALID":
        gr = GateResult(verdict=gate_label, reason=gate_reason or "PULLBACK",
                        mandate="Execute at THIS bar's close.",
                        context="Price 150.0 in pullback zone.",
                        entry_type="PULLBACK", trigger_rule="BAR CLOSE ONLY",
                        state="TRENDING")
    else:
        gr = GateResult(verdict=gate_label, reason=gate_reason or "FLOOR",
                        mandate="Do not enter.",
                        context="Gate rejected.")

    _captured = {}
    _orig = _transform_output

    def _intercept(action_summary, flat_metrics, **kw):
        _captured['metrics'] = flat_metrics.copy()
        return _orig(action_summary, flat_metrics, **kw)

    with mock.patch("tbs_engine.output._transform_output", side_effect=_intercept):
        with mock.patch("tbs_engine.output._build_focus_chart"):
            result = _assemble_output(ctx, gr, {"mode": "INFO"}, debug=False)
    return _captured.get('metrics', {}), result


# ============================================================================
# 1-4: Computation tests (output.py)
# ============================================================================

class TestRisk002Computation:
    """Tests 1-4: Risk_Assessment_Complete flag in flat metrics."""

    def test_01_complete_when_both_populated(self):
        m, _ = _run(extra_metrics={"Reward_Risk": 2.5, "Capital_Reward_Risk": 1.8})
        assert m["Risk_Assessment_Complete"] is True

    def test_02_incomplete_when_price_rr_null(self):
        m, _ = _run(extra_metrics={"Reward_Risk": None, "Capital_Reward_Risk": 1.8})
        assert m["Risk_Assessment_Complete"] is False

    def test_03_incomplete_when_capital_rr_null(self):
        m, _ = _run(extra_metrics={"Reward_Risk": 2.5, "Capital_Reward_Risk": None})
        assert m["Risk_Assessment_Complete"] is False

    def test_04_incomplete_when_both_null(self):
        m, _ = _run(extra_metrics={"Reward_Risk": None, "Capital_Reward_Risk": None})
        assert m["Risk_Assessment_Complete"] is False


# ============================================================================
# 5-7: Transform tests (transform.py)
# ============================================================================

class TestRisk002Transform:
    """Tests 5-7: complete flag in grouped output."""

    def test_05_complete_true_surfaces(self):
        _, g = _run(extra_metrics={"Reward_Risk": 2.5, "Capital_Reward_Risk": 1.8})
        assert g["trade_risk"]["complete"] is True

    def test_06_complete_false_surfaces(self):
        _, g = _run(extra_metrics={"Reward_Risk": None, "Capital_Reward_Risk": 1.8})
        assert g["trade_risk"]["complete"] is False

    def test_07_default_false_when_key_absent(self):
        """Transform with a metrics dict that never had Risk_Assessment_Complete."""
        m = _base_metrics()
        # Don't run _assemble_output — go straight to transform so key is absent
        # _transform_output expects (action_summary, flat_metrics)
        action_summary = {"verdict": "VALID", "reason": "PULLBACK"}
        grouped = _transform_output(action_summary, m)
        assert grouped["trade_risk"]["complete"] is False


# ============================================================================
# 8-9: Round-trip tests
# ============================================================================

class TestRisk002RoundTrip:
    """Tests 8-9: transform -> flatten recovers boolean."""

    def test_08_flatten_recovers_true(self):
        _, g = _run(extra_metrics={"Reward_Risk": 2.5, "Capital_Reward_Risk": 1.8})
        _, _, flat = _flatten(g)
        assert flat["Risk_Assessment_Complete"] is True

    def test_09_flatten_recovers_false(self):
        _, g = _run(extra_metrics={"Reward_Risk": None, "Capital_Reward_Risk": 1.8})
        _, _, flat = _flatten(g)
        assert flat["Risk_Assessment_Complete"] is False


# ============================================================================
# 10: MAPPED_FLAT_KEYS test
# ============================================================================

class TestRisk002MappedKeys:
    def test_10_key_registered(self):
        assert "Risk_Assessment_Complete" in MAPPED_FLAT_KEYS


# ============================================================================
# 11-12: Integration-style tests
# ============================================================================

class TestRisk002Integration:
    """Tests 11-12: VALID and INVALID paths end-to-end."""

    def test_11_valid_verdict_complete_true(self):
        m, g = _run(gate_label="VALID",
                     extra_metrics={"Reward_Risk": 3.5, "Capital_Reward_Risk": 2.5})
        assert m["Risk_Assessment_Complete"] is True
        assert g["trade_risk"]["complete"] is True
        assert m["Reward_Risk"] is not None
        assert m["Capital_Reward_Risk"] is not None

    def test_12_invalid_verdict_capital_rr_only(self):
        m, g = _run(gate_label="INVALID", gate_reason="CRG",
                     extra_metrics={"Reward_Risk": None, "Capital_Reward_Risk": 2.5,
                                    "Capital_RR_Label": "HEALTHY"})
        assert m["Risk_Assessment_Complete"] is False
        assert g["trade_risk"]["complete"] is False
        assert m["Capital_Reward_Risk"] is not None
        assert m["Reward_Risk"] is None
