"""STRUCT-001 Phase 1: SQ Directional EMA Separation Fix.

Verifies that bearish EMA separation (EMA_8 < EMA_21) contributes 0 to the
SQ separation_score, not a positive value via abs().

Evidence: E-6 from STRUCT-001 — 17 occurrences across validation sweep where
abs() rewarded widening bearish gaps identically to bullish gaps.

Fix: output.py line 446 — abs(EMA_8 - EMA_21) changed to max(0, EMA_8 - EMA_21).
"""

import sys, os, pytest
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace
from tbs_engine.types import GateResult
from tbs_engine.output import _assemble_output

# ============================================================================
# Helpers (subset from test_ths001)
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
    return pd.DataFrame({
        "close": [close]*n, "open": [close-1]*n,
        "high": [close+2]*n, "low": [close-2]*n,
        "EMA_8": [ema8]*n, "EMA_21": [ema21]*n,
        "SMA_50": [sma50]*n, "SMA_200": [sma200]*n,
        "ANCHOR": [anchor]*n, "vol_sma_9": [np.nan]*n,
    })


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
    m["Exit_Triggers"] = "None"; m["Exit_VWAP_Counter"] = None
    m["Exit_EMA8_Counter"] = None; m["Established_Hourly_Low"] = None
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
    m["MM_Target"] = None; m["MM_Rally_ATR"] = None
    return m


def _make_ctx(p_code="B", ema8=150.0, ema21=148.0, sma50=142.0, sma200=130.0,
              close=150.0, state_kw=None, _is_c3=False):
    state = _make_state(**(state_kw or {}))
    df = _make_df(close=close, ema8=ema8, ema21=ema21, sma50=sma50, sma200=sma200)
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
    return SimpleNamespace(
        state=state, cfg=cfg, p_code=p_code, is_etf=False, _is_c3=_is_c3,
        df=df, last=last, metrics=metrics, price_scaler=1.0,
        actual_price=float(close),
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
        profile="Profile B", prev_high=152.0, prox_anchor=148.0,
        _prx_ctx={"mode": "INFO"}, _is_lse_etf=False,
        _ssg_adjusted=False, _ssg_original_raw=0.0, _ssg_reason="",
        currency="USD", vwap_col="VWAP", adx_t2=26.0,
        _df_ctx=None,
        vol_poc_price=None, vol_poc_distance_atr=None,
        vol_poc_position="", avwap_price=None, avwap_position="",
        avwap_distance_atr=None,
        volume_context_label="",
        vol_bias="NEUTRAL", vol_confidence="MIXED", vol_bias_detail="",
    )


def _valid_gate():
    return GateResult(
        verdict="VALID", reason="PULLBACK",
        mandate="Execute at THIS bar's close.",
        context="Price 150.0 in pullback zone.",
        entry_type="PULLBACK", trigger_rule="BAR CLOSE ONLY",
        state="TRENDING",
    )


def _run(ctx):
    import unittest.mock as mock
    try:
        result = _assemble_output(ctx, _valid_gate(), {"mode": "INFO"}, debug=False)
    except Exception:
        with mock.patch("tbs_engine.output._build_focus_chart"):
            result = _assemble_output(ctx, _valid_gate(), {"mode": "INFO"}, debug=False)
    return result


# ============================================================================
# Tests
# ============================================================================

class TestSQDirectionalSeparation:
    """Verify bearish EMA separation contributes 0 to SQ."""

    def test_bullish_separation_scores_positive(self):
        """Bullish EMA gap (EMA_8 > EMA_21) adds to SQ via separation_score."""
        # EMA_8 = 150, EMA_21 = 148 → gap = 2.0, atr = 2.0 → ema_gap = 1.0
        # separation_score = clamp(1.0/1.0, 0, 1) * 50 = 50
        # stack: close(151)>EMA8(150)=15, EMA8>EMA21=15, EMA21(148)>SMA50(142)=10, SMA50>SMA200=10 → stk=50
        # SQ = 50 + 50 = 100
        ctx = _make_ctx(ema8=150.0, ema21=148.0, close=151.0)
        result = _run(ctx)
        sq = result["trade_quality"]["trend_health"]["structure"]["value"]
        assert sq == 100.0, f"Bullish full-stack + 1 ATR gap should score 100, got {sq}"

    def test_bearish_separation_scores_zero_contribution(self):
        """Bearish EMA gap (EMA_8 < EMA_21) must contribute 0 separation_score.

        Pre-fix (abs): this would score stack(15) + separation(50) = 65.
        Post-fix (max): this scores stack(15) + separation(0) = 15.
        """
        # EMA_8 = 146, EMA_21 = 148 → gap = -2.0 → max(0, -2) = 0
        # stack: close(150)>EMA8(146)=15, EMA8(146)<EMA21(148)=0, EMA21>SMA50=10, SMA50>SMA200=10 → stk=35
        # SQ = 35 + 0 = 35
        ctx = _make_ctx(ema8=146.0, ema21=148.0, close=150.0)
        result = _run(ctx)
        sq = result["trade_quality"]["trend_health"]["structure"]["value"]
        assert sq == 35.0, f"Bearish EMA gap should score stack-only (35), got {sq}"

    def test_wide_bearish_separation_still_zero(self):
        """Wide bearish gap (EMA_8 far below EMA_21) still contributes 0.

        This is the worst-case E-6 scenario: pre-fix, a 2 ATR bearish gap
        would have scored 50 separation points (clamped at max).
        """
        # EMA_8 = 140, EMA_21 = 148 → gap = -8.0 → max(0, -8) = 0
        # stack: close(150)>EMA8(140)=15, EMA8<EMA21=0, EMA21>SMA50=10, SMA50>SMA200=10 → stk=35
        # SQ = 35 + 0 = 35
        ctx = _make_ctx(ema8=140.0, ema21=148.0, close=150.0)
        result = _run(ctx)
        sq = result["trade_quality"]["trend_health"]["structure"]["value"]
        assert sq == 35.0, f"Wide bearish gap should still score 35, got {sq}"

    def test_fully_inverted_stack_with_bearish_gap_scores_near_zero(self):
        """Fully inverted stack (close < EMA_8 < EMA_21, no golden cross).

        Pre-fix: stack=0, separation=50 → SQ=50 (dangerously high).
        Post-fix: stack=0, separation=0 → SQ=0 (correct).
        """
        # close=135 < EMA_8=140 < EMA_21=148 < SMA_50=150, SMA_50>SMA_200=10
        # stack: close<EMA8=0, EMA8<EMA21=0, EMA21<SMA50=0, SMA50>SMA200=10 → stk=10
        # separation: max(0, 140-148) = 0
        # SQ = 10 + 0 = 10
        ctx = _make_ctx(close=135.0, ema8=140.0, ema21=148.0, sma50=150.0, sma200=130.0)
        result = _run(ctx)
        sq = result["trade_quality"]["trend_health"]["structure"]["value"]
        assert sq == 10.0, f"Fully inverted + bearish gap should score 10, got {sq}"

    def test_zero_separation_scores_zero(self):
        """EMA_8 == EMA_21 → separation = 0 (edge case)."""
        ctx = _make_ctx(ema8=148.0, ema21=148.0, close=150.0)
        result = _run(ctx)
        sq = result["trade_quality"]["trend_health"]["structure"]["value"]
        # stack: close>EMA8=15, EMA8==EMA21 (not >)=0, EMA21>SMA50=10, SMA50>SMA200=10 → stk=35
        assert sq == 35.0, f"Equal EMAs should score stack-only (35), got {sq}"

    def test_small_bullish_separation(self):
        """Small bullish gap contributes proportional separation_score."""
        # EMA_8 = 149, EMA_21 = 148 → gap = 1.0, atr = 2.0 → ema_gap = 0.5
        # separation = clamp(0.5/1.0, 0, 1) * 50 = 25
        # stack: close>EMA8=15, EMA8>EMA21=15, EMA21>SMA50=10, SMA50>SMA200=10 → stk=50
        # SQ = 50 + 25 = 75
        ctx = _make_ctx(ema8=149.0, ema21=148.0, close=150.0)
        result = _run(ctx)
        sq = result["trade_quality"]["trend_health"]["structure"]["value"]
        assert sq == 75.0, f"Half-ATR bullish gap should score 75, got {sq}"

    def test_bearish_separation_lowers_ths(self):
        """Verify that fixing the bearish SQ actually lowers the overall THS."""
        # Build two contexts: bullish vs bearish EMA, everything else equal
        ctx_bull = _make_ctx(ema8=150.0, ema21=148.0, close=150.0)
        ctx_bear = _make_ctx(ema8=146.0, ema21=148.0, close=150.0)
        result_bull = _run(ctx_bull)
        result_bear = _run(ctx_bear)
        ths_bull = result_bull["trade_quality"]["trend_health"]["score"]["value"]
        ths_bear = result_bear["trade_quality"]["trend_health"]["score"]["value"]
        assert ths_bear < ths_bull, (
            f"Bearish EMA THS ({ths_bear}) should be lower than bullish ({ths_bull})"
        )
