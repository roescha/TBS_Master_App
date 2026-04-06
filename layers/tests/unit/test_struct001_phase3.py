"""STRUCT-001 Phase 3: Structural Prerequisites + Scoring Adjustments.

27 test cases from STRUCT001_Phase3_Spec_v1_0.docx Section VIII.
Covers: P-1 death cross cap, DQ-1 SQ golden cross weight, P-4 VWAP floor
persistence, DQ-6 component floor cap, P-2/P-3 context advisory.

Spec: STRUCT001_Phase3_Spec_v1_0.docx
Prompt: STRUCT001_Phase3_Implementation_Prompt.md
"""

import sys, os, pytest
import pandas as pd, numpy as np
import unittest.mock as mock

# Insert test root for tbs_engine package access
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub heavy deps so tbs_engine.__init__ can import without ib_insync etc.
for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'google.genai', 'google'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

from types import SimpleNamespace
from tbs_engine.types import GateResult
from tbs_engine.output import _assemble_output, THS_GATE_THRESHOLD
from tbs_engine.transform import _transform_output

# ============================================================================
# Helpers (adapted from test_struct001_sq_directional.py)
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
             sma50=142.0, sma200=130.0, sma200_nan=False):
    d = {
        "close": [close]*n, "open": [close-1]*n,
        "high": [close+2]*n, "low": [close-2]*n,
        "EMA_8": [ema8]*n, "EMA_21": [ema21]*n,
        "SMA_50": [sma50]*n, "ANCHOR": [anchor]*n, "vol_sma_9": [np.nan]*n,
    }
    if sma200_nan:
        d["SMA_200"] = [np.nan]*n
    else:
        d["SMA_200"] = [sma200]*n
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
    m["Exit_Triggers"] = "None"; m["Exit_VWAP_Counter"] = None
    m["Exit_EMA8_Counter"] = None; m["Established_Hourly_Low"] = None
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
    m["MM_Target"] = None; m["MM_Rally_ATR"] = None
    return m


def _make_ctx(p_code="B", ema8=150.0, ema21=148.0, sma50=142.0, sma200=130.0,
              close=150.0, state_kw=None, _is_c3=False, sma200_nan=False,
              extra_metrics=None):
    state = _make_state(**(state_kw or {}))
    df = _make_df(close=close, ema8=ema8, ema21=ema21, sma50=sma50,
                  sma200=sma200, sma200_nan=sma200_nan)
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
    )


def _valid_gate():
    return GateResult(
        verdict="VALID", reason="PULLBACK",
        mandate="Execute at THIS bar's close.",
        context="Price 150.0 in pullback zone.",
        entry_type="PULLBACK", trigger_rule="BAR CLOSE ONLY",
        state="TRENDING",
    )


def _invalid_gate():
    return GateResult(
        verdict="INVALID", reason="FLOOR",
        mandate="Do not enter.",
        context="Floor broken.",
    )


def _run(ctx, gate=None):
    """Run _assemble_output and capture raw flat metrics via transform intercept."""
    _captured = {}
    _orig = _transform_output

    def _intercept(action_summary, flat_metrics, **kw):
        _captured['metrics'] = flat_metrics.copy()
        _captured['as'] = action_summary.copy()
        return _orig(action_summary, flat_metrics, **kw)

    with mock.patch("tbs_engine.output._transform_output", side_effect=_intercept):
        with mock.patch("tbs_engine.output._build_focus_chart"):
            result = _assemble_output(ctx, gate or _valid_gate(),
                                      {"mode": "INFO"}, debug=False)
    return result, _captured.get('metrics', {}), _captured.get('as', {})


# ============================================================================
# P-1: Death Cross Prerequisite (Tests 1-6)
# ============================================================================
class TestP1DeathCross:

    def test_01_death_cross_profile_b(self):
        """#1: SMA50 < SMA200, Profile B → THS capped at 50."""
        ctx = _make_ctx(p_code='B', sma50=125.0, sma200=130.0)
        _, m, _ = _run(ctx)
        assert m['Trend_Health_Score'] <= THS_GATE_THRESHOLD
        assert m['THS_Death_Cross_Cap'] is True

    def test_02_death_cross_profile_c(self):
        """#2: SMA50 < SMA200, Profile C → THS capped at 50."""
        ctx = _make_ctx(p_code='C', sma50=125.0, sma200=130.0, _is_c3=True)
        _, m, _ = _run(ctx)
        assert m['Trend_Health_Score'] <= THS_GATE_THRESHOLD
        assert m['THS_Death_Cross_Cap'] is True

    def test_03_death_cross_profile_a_no_cap(self):
        """#3: SMA50 < SMA200, Profile A → P-1 does not fire."""
        ctx = _make_ctx(p_code='A', sma50=125.0, sma200=130.0)
        _, m, _ = _run(ctx)
        assert m['THS_Death_Cross_Cap'] is False

    def test_04_golden_cross_profile_b(self):
        """#4: SMA50 > SMA200, Profile B → no cap."""
        ctx = _make_ctx(p_code='B', sma50=142.0, sma200=130.0)
        _, m, _ = _run(ctx)
        assert m['THS_Death_Cross_Cap'] is False

    def test_05_sma200_nan_profile_b(self):
        """#5: SMA200 is NaN, Profile B → data guard, P-1 skips."""
        ctx = _make_ctx(p_code='B', sma200_nan=True)
        _, m, _ = _run(ctx)
        assert m['THS_Death_Cross_Cap'] is False

    def test_06_death_cross_high_subs(self):
        """#6: Death cross + high sub-scores → THS cannot exceed 50."""
        # All subs healthy but death cross present
        ctx = _make_ctx(p_code='B', sma50=125.0, sma200=130.0,
                        close=150.0, ema8=150.0, ema21=148.0)
        _, m, _ = _run(ctx)
        assert m['Trend_Health_Score'] <= THS_GATE_THRESHOLD
        assert m['THS_Death_Cross_Cap'] is True


# ============================================================================
# DQ-1: SQ Golden Cross Weight (Tests 7-10)
# ============================================================================
class TestDQ1GoldenCrossWeight:

    def test_07_golden_cross_profile_a_weight_25(self):
        """#7: Golden cross present, Profile A → _stk += 25."""
        # Profile A with golden cross: stk = 15+15+10+25 = 65
        # Profile B with golden cross: stk = 15+15+10+10 = 50
        ctx_a = _make_ctx(p_code='A', close=151.0, ema8=150.0, ema21=148.0,
                          sma50=142.0, sma200=130.0)
        ctx_b = _make_ctx(p_code='B', close=151.0, ema8=150.0, ema21=148.0,
                          sma50=142.0, sma200=130.0)
        _, m_a, _ = _run(ctx_a)
        _, m_b, _ = _run(ctx_b)
        sq_diff = m_a['THS_Structure'] - m_b['THS_Structure']
        assert sq_diff == 15.0, f"Profile A SQ should be 15 higher, got diff {sq_diff}"

    def test_08_golden_cross_profile_b_weight_10(self):
        """#8: Golden cross present, Profile B → _stk += 10 (unchanged)."""
        # Full stack B: 15+15+10+10=50, separation 50 → SQ=100
        ctx = _make_ctx(p_code='B', close=151.0, ema8=150.0, ema21=148.0,
                        sma50=142.0, sma200=130.0)
        _, m, _ = _run(ctx)
        assert m['THS_Structure'] == 100.0

    def test_09_no_golden_cross_profile_a(self):
        """#9: No golden cross, Profile A → _stk += 0, same as before."""
        # Death cross: SMA50 < SMA200 → gc component = 0
        # stk = 15+15+10+0 = 40, separation = 50 → SQ = 90
        ctx = _make_ctx(p_code='A', close=151.0, ema8=150.0, ema21=148.0,
                        sma50=125.0, sma200=130.0)
        _, m, _ = _run(ctx)
        assert m['THS_Structure'] == 90.0

    def test_10_max_sq_profile_a(self):
        """#10: Full stack + separation, Profile A → SQ = 115."""
        # stk = 15+15+10+25 = 65, separation(capped at 50) → SQ = 115
        ctx = _make_ctx(p_code='A', close=151.0, ema8=150.0, ema21=148.0,
                        sma50=142.0, sma200=130.0)
        _, m, _ = _run(ctx)
        assert m['THS_Structure'] == 115.0


# ============================================================================
# P-4: VWAP Floor Persistence (Tests 11-13)
# ============================================================================
class TestP4VWAPFloor:

    def test_11_profile_a_fb_halved(self):
        """#11: Profile A, close above VWAP → FB halved, note set."""
        ctx_a = _make_ctx(p_code='A')
        ctx_b = _make_ctx(p_code='B')
        _, m_a, _ = _run(ctx_a)
        _, m_b, _ = _run(ctx_b)
        # Same inputs, Profile A FB should be half of Profile B FB
        assert m_a['THS_Floor_Buffer'] == pytest.approx(m_b['THS_Floor_Buffer'] * 0.5)
        assert m_a['THS_VWAP_Floor_Penalty'] is True
        assert m_a['THS_VWAP_Floor_Note'] is not None

    def test_12_profile_b_fb_unchanged(self):
        """#12: Profile B → multiplier not applied."""
        ctx = _make_ctx(p_code='B')
        _, m, _ = _run(ctx)
        assert m['THS_VWAP_Floor_Penalty'] is False
        assert m['THS_VWAP_Floor_Note'] is None

    def test_13_profile_a_fb_zero(self):
        """#13: Profile A, FB = 0 (below floor) → 0 * 0.5 = 0."""
        # close < floor_raw → _fb_atr < 0 → _fb = 0
        ctx = _make_ctx(p_code='A', close=135.0,
                        state_kw={'floor_raw': 140.0})
        _, m, _ = _run(ctx)
        assert m['THS_Floor_Buffer'] == 0.0
        assert m['THS_VWAP_Floor_Penalty'] is True


# ============================================================================
# DQ-6: Component Floor Cap (Tests 14-19)
# ============================================================================
class TestDQ6ComponentCap:

    def test_14_dm_critical_cap(self):
        """#14: DM = 15 (CRITICAL), other subs healthy → THS ≤ 50."""
        # adx_t=15 → adx_s=0, di_plus barely above di_minus → low DM
        ctx = _make_ctx(p_code='B',
                        state_kw={'adx_t': 15.0, 'di_plus': 16.0, 'di_minus': 15.0})
        _, m, _ = _run(ctx)
        assert m['THS_Dir_Momentum'] < 40
        assert m['Trend_Health_Score'] <= THS_GATE_THRESHOLD
        assert m['THS_Component_Cap'] is not None
        assert 'Dir_Momentum' in m['THS_Component_Cap']

    def test_15_sq_critical_cap(self):
        """#15: SQ = 10 (CRITICAL), other subs healthy → THS ≤ 50."""
        # Inverted stack: close < EMA8 < EMA21, no golden cross → low SQ
        ctx = _make_ctx(p_code='B', close=135.0, ema8=140.0, ema21=148.0,
                        sma50=150.0, sma200=160.0)
        _, m, _ = _run(ctx)
        assert m['THS_Structure'] < 40
        assert m['Trend_Health_Score'] <= THS_GATE_THRESHOLD
        assert m['THS_Component_Cap'] is not None
        assert 'Structure' in m['THS_Component_Cap']

    def test_16_fb_critical_no_cap(self):
        """#16: FB = 5 (CRITICAL), DM/SQ healthy → no cap (FB excluded)."""
        # close barely above floor → low FB, but DM and SQ healthy
        ctx = _make_ctx(p_code='A', close=140.5,
                        state_kw={'floor_raw': 140.0})
        _, m, _ = _run(ctx)
        assert m['THS_Floor_Buffer'] < 40
        assert m['THS_Component_Cap'] is None

    def test_17_ta_critical_no_cap(self):
        """#17: TA = 0 (CRITICAL), DM/SQ healthy → no cap (TA excluded)."""
        ctx = _make_ctx(p_code='B')
        # window_count = ta_max → TA = 0
        ctx.window_count = 50  # equals ta_max
        _, m, _ = _run(ctx)
        assert m['THS_Trend_Age'] == 0.0
        assert m['THS_Component_Cap'] is None

    def test_18_both_dm_sq_below_40(self):
        """#18: DM = 39.9, SQ = 39.9 → DM triggers first (elif)."""
        # Low ADX for low DM, inverted stack for low SQ
        ctx = _make_ctx(p_code='B', close=135.0, ema8=140.0, ema21=148.0,
                        sma50=150.0, sma200=160.0,
                        state_kw={'adx_t': 15.0, 'di_plus': 16.0, 'di_minus': 15.0})
        _, m, _ = _run(ctx)
        assert m['THS_Dir_Momentum'] < 40
        assert m['THS_Structure'] < 40
        assert 'Dir_Momentum' in m['THS_Component_Cap']  # DM triggers first

    def test_19_dm_sq_at_40_no_cap(self):
        """#19: DM = 40, SQ = 40 → boundary: 40 is not < 40, no cap."""
        # adx_t=27 → adx_s = (27-15)/30 = 0.4, di_plus-di_minus = 10 → di_s=0.5
        # DM = (0.4*0.6 + 0.5*0.4)*100 = (0.24+0.20)*100 = 44 → above 40
        # Need to engineer DM exactly at 40: (0.6*adx_s + 0.4*di_s)*100 = 40
        # If di_plus=di_minus → di_s=0: adx_s = 40/60 = 0.667 → adx_t = 0.667*30+15 = 35
        # DM = (0.667*0.6 + 0)*100 = 40.0
        # SQ: need stk=40, sep=0 → close>EMA8=15, EMA8>EMA21=15, EMA21>SMA50=10
        # → stk=40 (no golden cross), EMA8=EMA21 → sep=0 → SQ=40
        ctx = _make_ctx(p_code='B', close=151.0, ema8=149.0, ema21=148.0,
                        sma50=142.0, sma200=160.0,  # death cross → gc=0
                        state_kw={'adx_t': 35.0, 'di_plus': 15.0, 'di_minus': 15.0})
        _, m, _ = _run(ctx)
        assert m['THS_Dir_Momentum'] >= 40, f"DM should be >= 40, got {m['THS_Dir_Momentum']}"
        assert m['THS_Structure'] >= 40, f"SQ should be >= 40, got {m['THS_Structure']}"
        assert m['THS_Component_Cap'] is None


# ============================================================================
# P-2/P-3: Context Advisory (Tests 20-23)
# ============================================================================
class TestP2P3ContextAdvisory:

    def test_20_both_warnings_profile_a(self):
        """#20: Context EMA bearish + slope declining → both warnings."""
        ctx = _make_ctx(p_code='A', extra_metrics={
            'Context_EMA_Stacked': False,
            'Context_EMA_Bias': 'BEARISH',
            'Context_Daily_SMA50_Slope': -0.5,
        })
        _, m, _ = _run(ctx)
        adv = m['THS_Context_Advisory']
        assert adv is not None
        assert 'Daily EMA 8 < EMA 21' in adv
        assert 'Daily SMA 50 slope declining' in adv
        assert '|' in adv

    def test_21_all_bullish_none(self):
        """#21: Context EMA bullish, slope rising → None."""
        ctx = _make_ctx(p_code='B', extra_metrics={
            'Context_EMA_Stacked': True,
            'Context_EMA_Bias': 'BULLISH',
            'Context_Weekly_SMA50_Slope': 0.3,
        })
        _, m, _ = _run(ctx)
        assert m['THS_Context_Advisory'] is None

    def test_22_ema_bearish_only(self):
        """#22: Context EMA bearish only → single warning, no pipe."""
        ctx = _make_ctx(p_code='B', extra_metrics={
            'Context_EMA_Stacked': False,
            'Context_EMA_Bias': 'BEARISH',
            'Context_Weekly_SMA50_Slope': 0.3,  # positive → no slope warning
        })
        _, m, _ = _run(ctx)
        adv = m['THS_Context_Advisory']
        assert adv is not None
        assert 'Weekly EMA 8 < EMA 21' in adv
        assert '|' not in adv

    def test_23_context_data_none(self):
        """#23: Context EMA data None → no advisory."""
        ctx = _make_ctx(p_code='A', extra_metrics={
            'Context_EMA_Stacked': None,
            'Context_EMA_Bias': None,
            'Context_Daily_SMA50_Slope': None,
        })
        _, m, _ = _run(ctx)
        assert m['THS_Context_Advisory'] is None


# ============================================================================
# Integration Tests (Tests 24-27)
# ============================================================================
class TestIntegration:

    def test_24_p1_and_dq6_both_fire(self):
        """#24: P-1 + DQ-6 both fire → THS ≤ 50, both caps logged."""
        # Death cross + low DM
        ctx = _make_ctx(p_code='B', sma50=125.0, sma200=130.0,
                        state_kw={'adx_t': 15.0, 'di_plus': 16.0, 'di_minus': 15.0})
        result, m, raw_as = _run(ctx)
        assert m['Trend_Health_Score'] <= THS_GATE_THRESHOLD
        assert m['THS_Death_Cross_Cap'] is True
        assert m['THS_Component_Cap'] is not None
        # Check gate context has both enrichments
        if raw_as.get("verdict") == "WAIT":
            ctx_str = raw_as.get("reason", {}).get("detail", "")
            assert 'STRUCTURAL' in ctx_str, f"Missing STRUCTURAL in: {ctx_str}"
            assert 'POLARIZATION' in ctx_str, f"Missing POLARIZATION in: {ctx_str}"

    def test_25_p4_and_dq6(self):
        """#25: P-4 + DQ-6: low FB + low DM → THS ≤ 50, both active."""
        ctx = _make_ctx(p_code='A',
                        state_kw={'adx_t': 15.0, 'di_plus': 16.0, 'di_minus': 15.0})
        _, m, _ = _run(ctx)
        assert m['THS_VWAP_Floor_Penalty'] is True
        assert m['THS_Component_Cap'] is not None
        assert m['Trend_Health_Score'] <= THS_GATE_THRESHOLD

    def test_26_all_healthy_no_caps(self):
        """#26: All healthy, no caps or advisories → THS unchanged."""
        ctx = _make_ctx(p_code='B', sma50=142.0, sma200=130.0)
        _, m, _ = _run(ctx)
        assert m['THS_Death_Cross_Cap'] is False
        assert m['THS_Component_Cap'] is None
        assert m['THS_VWAP_Floor_Penalty'] is False
        assert m['THS_Context_Advisory'] is None
        assert m['Trend_Health_Score'] > THS_GATE_THRESHOLD

    def test_27_invalid_verdict_caps_still_set(self):
        """#27: INVALID verdict (prior gate blocked) → caps still set on all paths."""
        ctx = _make_ctx(p_code='B', sma50=125.0, sma200=130.0,
                        state_kw={'adx_t': 15.0, 'di_plus': 16.0, 'di_minus': 15.0})
        _, m, _ = _run(ctx, gate=_invalid_gate())
        # P-1 and DQ-6 metrics are written regardless of verdict
        assert m['THS_Death_Cross_Cap'] is True
        assert m['THS_Component_Cap'] is not None
        assert 'THS_VWAP_Floor_Penalty' in m
        assert 'THS_Context_Advisory' in m
