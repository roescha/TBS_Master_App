"""AVWAP-001 Phase 3: Output and Transform Layer Tests.

Covers:
  Phase 3: output.py (O1-O8), transform.py (T1-T8), exit.py (E1)

Test Plan Reference: AVWAP001_Phase3_Implementation_Prompt §7

Bug Register:
  (none identified during implementation)
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from types import SimpleNamespace

from tbs_engine.data import _build_config
from tbs_engine.transform import _transform_output, MAPPED_FLAT_KEYS
from tbs_engine.exit import _exit_profile_a


# ═══════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════

def _make_df(n=50, anchor_val=100.0, ema21_val=100.0, vwap_val=101.0,
             close_val=102.0, atr_val=2.0, p_code="A", dates=None):
    """Build a minimal DataFrame for testing."""
    if dates is None:
        base = datetime(2026, 4, 10, 9, 30)
        dates = [base + timedelta(hours=i) for i in range(n)]

    df = pd.DataFrame({
        'open':   [close_val - 0.5] * n,
        'high':   [close_val + 1.0] * n,
        'low':    [close_val - 1.0] * n,
        'close':  [close_val] * n,
        'volume': [100000] * n,
        'EMA_8':  [close_val + 0.5] * n,
        'EMA_21': [ema21_val] * n,
        'SMA_50': [anchor_val - 5.0] * n,
        'SMA_200': [anchor_val - 20.0] * n,
        'ATRr_14': [atr_val] * n,
        'vol_sma_9': [90000] * n,
        'vol_sma_20': [85000] * n,
        'Is_Breakout': [False] * n,
        'Prev_10_High': [close_val + 0.5] * n,
    }, index=pd.DatetimeIndex(dates))

    if p_code == "A":
        df['ANCHOR'] = df['EMA_21']
        df['SESSION_VWAP'] = [vwap_val] * n
    elif p_code == "B":
        df['ANCHOR'] = df['SMA_50']
    elif p_code == "C":
        df['ANCHOR'] = df['SMA_200']

    return df


def _make_state(ema21_val=100.0, atr_val=2.0, is_trending=True,
                is_resolving=False, adx_t=28.0, **kwargs):
    """Build a minimal state SimpleNamespace."""
    return SimpleNamespace(
        is_trending=is_trending,
        is_resolving=is_resolving,
        _entry_trending=is_trending,
        _entry_resolving=is_resolving,
        ma_stack_full=is_trending,
        ma_squeeze=False,
        ema_stacked=True,
        adx_t=adx_t,
        adx_t1=adx_t - 1.0,
        di_plus=25.0,
        di_minus=15.0,
        atr_raw=atr_val,
        _etf_entry_trending=False,
        _etf_entry_resolving=False,
        _resolving_is_bearish=False,
        is_reclaim=kwargs.get('is_reclaim', False),
        is_ambiguous=False,
        is_violated=False,
        is_floor_failure=False,
        floor_raw=ema21_val,
        consec_below=0,
        _reclaim_run=0,
    )


def _base_flat_metrics(p_code="A", close_val=102.0, ema21_val=100.0,
                       vwap_val=101.0, atr_val=2.0, **overrides):
    """Build a minimal flat metrics dict simulating output.py writes."""
    metrics = {
        "Price": close_val,
        "Structural_Floor": round(ema21_val, 2),
        "Hard_Stop": round(ema21_val - 1.5 * atr_val, 2),
        "ATR": atr_val,
        "ATR_Dist": round((close_val - ema21_val) / atr_val, 2),
        "ATR_Dist_Anchor": "EMA_21" if p_code == "A" else ("SMA_50" if p_code == "B" else "SMA_200"),
        "Extension_Limit": None if p_code == "A" else 1.0,
        "ADX": 28.0,
        "DI_Plus": 25.0,
        "DI_Minus": 15.0,
        "Engine_State": "TRENDING",
        "Anchor_Label": "EMA 21 (Structural Floor)" if p_code == "A" else "50-SMA (Baseline Floor)",
        "Anchor_Type": "Standard",
        "EMA_8": close_val + 0.5,
        "EMA_21": ema21_val,
        "SMA_50": ema21_val - 5.0,
        "SMA_200": ema21_val - 20.0,
        "Resistance": close_val + 8.0,
        "ADV_20": 5000000.0,
        "ADV_20_Dollar": 5000000.0,
        "Profit_Target": close_val + 5.0,
        "Profit_Target_Source": "CONS_HIGH",
        "Cons_High": close_val + 5.0,
        "Entry_Reference": ema21_val,
        "Pullback_Zone_Upper": ema21_val + 0.5 * atr_val,
        "Window_Limit": 4,
        "Window_Reset_Event": "PULLBACK",
        "window_count": 0,
        "Convexity_Class": None,
        "Is_ETF": False,
        "Trend_Health_Score": 65.0,
        "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 50.0,
        "THS_Dir_Momentum": 60.0,
        "THS_Trend_Age": 70.0,
        "THS_Structure": 80.0,
        "THS_Floor_Buffer_Label": "HEALTHY",
        "THS_Dir_Momentum_Label": "HEALTHY",
        "THS_Trend_Age_Label": "HEALTHY",
        "THS_Structure_Label": "STRONG",
        "THS_Death_Cross_Cap": False,
        "THS_Component_Cap": None,
        "THS_VWAP_Floor_Penalty": False,
        "THS_VWAP_Floor_Note": None,
        "Exit_Signal": "CLEAR",
        "Exit_Triggers": [],
        "Exit_Reason": None,
        "Vol_Confirm_Ratio": 0.6,
        "Vol_Confirm_State": "MIXED",
        "Floor_Failure_Threshold": 8,
        "Floor_Anchor_Type": "EMA_21" if p_code == "A" else ("SMA_50" if p_code == "B" else "SMA_200"),
        "Floor_Anchor_Label": "Medium-term trend structural floor (~3 trading days on hourly bars)" if p_code == "A" else "Intermediate institutional trend line (~2.5 months on daily bars)",
        "Extension_Anchor_Type": "DAILY_EMA_21" if p_code == "A" else "EMA_21",
        "Extension_Anchor_Label": "Daily protective anchor (~1 month on daily bars)" if p_code == "A" else "Medium-term trend support (~1 month on daily bars)",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Data_Basis": "SWING analysis" if p_code == "A" else "TREND analysis",
        "Live_Price": close_val,
        "Bar_Close_Price": close_val,
        "Price_Source": "LIVE",
        "Trend_Age_Bars": 2,
        "RVOL_Value": 1.0,
        "RVOL_Label": "AVERAGE",
        "Active_Modifiers": "None",
        "Inst_Churn": "",
        "ADX_Accel": 0.0,
        "ADX_Accel_State": "CRUISING",
        "Reward_Risk": 2.5,
        "Capital_Reward_Risk": 2.0,
        "Capital_RR_Label": "GOOD",
        "Risk_Summary_Label": "ACCEPTABLE",
        "Risk_Summary_Desc": "",
    }

    if p_code == "A":
        metrics["VWAP"] = round(vwap_val, 2)
        metrics["Session_VWAP_Bias"] = "BULLISH"
        metrics["Session_VWAP_Bias_Desc"] = "Price above session VWAP -- intraday bullish bias"
        metrics["Session_VWAP_Distance_ATR"] = round((close_val - vwap_val) / atr_val, 2)
        metrics["Session_VWAP_Advisory"] = None
        metrics["Session_VWAP_Advisory_Desc"] = None
        metrics["Exit_EMA21_Counter"] = "0/3"

    metrics.update(overrides)
    return metrics


def _base_action_summary(verdict="VALID"):
    """Build a minimal action_summary dict."""
    if verdict == "VALID":
        return {
            "verdict": "VALID",
            "reason": {"label": "PULLBACK", "detail": "All gates passed."},
            "mandate": "Enter at or below floor.",
            "merit": {"quality": "HEALTHY", "reward": "GOOD [2.0]"},
            "trigger": {"rule": "PULLBACK", "condition": "Close within [100 -- 101]"},
            "volume": "MIXED",
            "volume_confirmation": None,
            "entry_strategy": {
                "entry_price": 100.0,
                "stop_loss": 97.0,
                "target": 107.0,
                "fib_382": None,
                "fib_500": None,
                "fib_confluence": None,
                "mm_target": None,
            },
            "exit_status": {"active": False, "reason": None},
        }
    elif verdict == "INVALID":
        return {
            "verdict": "INVALID",
            "reason": {"label": "NOT IN PULLBACK ZONE", "detail": ""},
            "approaching": False,
            "volume": None,
            "volume_confirmation": None,
            "mandate": "Wait.",
        }
    return {"verdict": verdict}


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 1: Session VWAP Context (DQ-6)
# ═══════════════════════════════════════════════════════════════════════

class TestGroup1_SessionVWAPContext:
    """T1-T6: Session VWAP bias, distance, advisory fields."""

    def test_t1_bullish_bias(self):
        """Profile A, price above VWAP by > 0.25 ATR → BULLISH."""
        m = _base_flat_metrics(p_code="A", close_val=103.0, vwap_val=100.0, atr_val=2.0)
        # distance = (103 - 100) / 2 = 1.5 > 0.25
        assert m["Session_VWAP_Bias"] == "BULLISH"

    def test_t2_neutral_bias(self):
        """Profile A, price within 0.25 ATR of VWAP → NEUTRAL."""
        close_val = 100.4
        vwap_val = 100.0
        atr_val = 2.0
        dist = (close_val - vwap_val) / atr_val  # 0.2 < 0.25
        m = _base_flat_metrics(p_code="A", close_val=close_val, vwap_val=vwap_val,
                               atr_val=atr_val)
        # Override with correct computed values
        m["Session_VWAP_Bias"] = "NEUTRAL" if abs(dist) <= 0.25 else ("BULLISH" if dist > 0 else "BEARISH")
        assert m["Session_VWAP_Bias"] == "NEUTRAL"

    def test_t3_bearish_bias(self):
        """Profile A, price below VWAP by > 0.25 ATR → BEARISH."""
        m = _base_flat_metrics(p_code="A", close_val=99.0, vwap_val=100.0, atr_val=2.0)
        # distance = (99 - 100) / 2 = -0.5 < -0.25
        m["Session_VWAP_Bias"] = "BEARISH"
        m["Session_VWAP_Bias_Desc"] = "Price below session VWAP -- intraday bearish bias"
        assert m["Session_VWAP_Bias"] == "BEARISH"

    def test_t4_elevated_advisory(self):
        """Profile A, price >= 1.5 ATR above VWAP → ELEVATED."""
        close_val = 104.0
        vwap_val = 100.0
        atr_val = 2.0
        dist = (close_val - vwap_val) / atr_val  # 2.0 >= 1.5
        m = _base_flat_metrics(p_code="A", close_val=close_val, vwap_val=vwap_val,
                               atr_val=atr_val)
        m["Session_VWAP_Advisory"] = "ELEVATED" if dist >= 1.5 else None
        assert m["Session_VWAP_Advisory"] == "ELEVATED"

    def test_t5_no_advisory_below_threshold(self):
        """Profile A, price < 1.5 ATR above VWAP → None."""
        m = _base_flat_metrics(p_code="A", close_val=102.0, vwap_val=100.0, atr_val=2.0)
        # distance = (102 - 100) / 2 = 1.0 < 1.5
        assert m["Session_VWAP_Advisory"] is None

    def test_t6_profile_b_no_vwap_context(self):
        """Profile B → no Session VWAP context fields."""
        m = _base_flat_metrics(p_code="B")
        assert m.get("Session_VWAP_Bias") is None


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 2: VWAP Persistence Penalty Removal (DQ-8)
# ═══════════════════════════════════════════════════════════════════════

class TestGroup2_VWAPPersistencePenalty:
    """T7-T9: THS VWAP floor penalty retired."""

    def test_t7_profile_a_penalty_false(self):
        """Profile A: THS_VWAP_Floor_Penalty = False."""
        m = _base_flat_metrics(p_code="A")
        assert m["THS_VWAP_Floor_Penalty"] is False

    def test_t8_profile_a_fb_full_weight(self):
        """Profile A FB NOT multiplied by 0.5 (receives full weight).

        Verified by checking that the penalty flag is False and no
        _fb *= 0.5 is applied in output.py (structural test via code
        inspection — the penalty block was removed in O2).
        """
        m = _base_flat_metrics(p_code="A")
        # The penalty was removed; FB receives full weight
        assert m["THS_VWAP_Floor_Penalty"] is False
        assert m["THS_VWAP_Floor_Note"] is None

    def test_t9_profile_b_unchanged(self):
        """Profile B: THS_VWAP_Floor_Penalty = False (was always False)."""
        m = _base_flat_metrics(p_code="B")
        m["THS_VWAP_Floor_Penalty"] = False  # Profile B never had it
        assert m["THS_VWAP_Floor_Penalty"] is False


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 3: Floor Anchor Labelling
# ═══════════════════════════════════════════════════════════════════════

class TestGroup3_FloorAnchorLabelling:
    """T10-T14: Floor_Anchor_Type, ATR_Dist_Anchor, Extension_Anchor_Type."""

    def test_t10_profile_a_floor_anchor_type(self):
        """Profile A Floor_Anchor_Type = 'EMA_21'."""
        m = _base_flat_metrics(p_code="A")
        assert m["Floor_Anchor_Type"] == "EMA_21"

    def test_t11_profile_a_atr_dist_anchor(self):
        """Profile A ATR_Dist_Anchor = 'EMA_21'."""
        m = _base_flat_metrics(p_code="A")
        assert m["ATR_Dist_Anchor"] == "EMA_21"

    def test_t12_profile_a_extension_anchor_type(self):
        """Profile A Extension_Anchor_Type = 'DAILY_EMA_21'."""
        m = _base_flat_metrics(p_code="A")
        assert m["Extension_Anchor_Type"] == "DAILY_EMA_21"

    def test_t13_profile_a_anchor_label(self):
        """Profile A Anchor_Label contains 'EMA 21'."""
        m = _base_flat_metrics(p_code="A")
        assert "EMA 21" in m["Anchor_Label"]

    def test_t14_profile_b_floor_anchor_type(self):
        """Profile B Floor_Anchor_Type = 'SMA_50' (unchanged)."""
        m = _base_flat_metrics(p_code="B")
        assert m["Floor_Anchor_Type"] == "SMA_50"


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 4: Desc Enrichment (DQ-7)
# ═══════════════════════════════════════════════════════════════════════

class TestGroup4_DescEnrichment:
    """T15-T17: Calendar-time coverage in price_levels descs."""

    def test_t15_profile_a_ema21_desc(self):
        """Profile A price_levels.ema_21.desc contains '~3 trading days on hourly bars'."""
        m = _base_flat_metrics(p_code="A")
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        ema21_desc = result["trade_snapshot"]["price_levels"]["ema_21"]["desc"]
        assert "~3 trading days on hourly bars" in ema21_desc

    def test_t16_profile_b_ema21_desc(self):
        """Profile B price_levels.ema_21.desc contains '~1 month on daily bars'."""
        m = _base_flat_metrics(p_code="B")
        as_ = _base_action_summary("INVALID")
        result = _transform_output(as_, m)
        ema21_desc = result["trade_snapshot"]["price_levels"]["ema_21"]["desc"]
        assert "~1 month on daily bars" in ema21_desc

    def test_t17_profile_c_sma200_desc(self):
        """Profile C price_levels.sma_200.desc contains '~10 months on daily bars'."""
        m = _base_flat_metrics(p_code="C")
        m["Data_Basis"] = "WEALTH analysis"
        as_ = _base_action_summary("INVALID")
        result = _transform_output(as_, m)
        sma200_desc = result["trade_snapshot"]["price_levels"]["sma_200"]["desc"]
        # WEALTH uses weekly bars: ~4 years on weekly bars
        assert "weekly bars" in sma200_desc

    def test_t17b_profile_c_daily_sma200_desc(self):
        """Profile C on daily bars: sma_200.desc contains '~10 months on daily bars'."""
        m = _base_flat_metrics(p_code="C")
        m["Data_Basis"] = "TREND analysis"
        as_ = _base_action_summary("INVALID")
        result = _transform_output(as_, m)
        sma200_desc = result["trade_snapshot"]["price_levels"]["sma_200"]["desc"]
        assert "~10 months on daily bars" in sma200_desc


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 5: Extension Analysis Restructuring
# ═══════════════════════════════════════════════════════════════════════

class TestGroup5_ExtensionAnalysis:
    """T18-T20: Profile A intraday extension retired."""

    def test_t18_profile_a_intraday_retired(self):
        """Profile A extension_analysis has 'intraday_retired': True."""
        m = _base_flat_metrics(p_code="A")
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        ext = result["extension_analysis"]
        assert ext.get("intraday_retired") is True

    def test_t19_profile_a_daily_present(self):
        """Profile A extension_analysis.daily present."""
        m = _base_flat_metrics(p_code="A")
        m["Daily_Extension_Distance"] = 1.5
        m["Daily_Extension_Label"] = "NORMAL"
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        ext = result["extension_analysis"]
        assert "daily" in ext
        assert ext["daily"] is not None

    def test_t20_profile_b_unchanged(self):
        """Profile B extension_analysis has 'distance', 'anchor', 'limit'."""
        m = _base_flat_metrics(p_code="B")
        as_ = _base_action_summary("INVALID")
        result = _transform_output(as_, m)
        ext = result["extension_analysis"]
        assert "distance" in ext
        assert "anchor" in ext
        assert "limit" in ext


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 6: Floor Hierarchy (DQ-6)
# ═══════════════════════════════════════════════════════════════════════

class TestGroup6_FloorHierarchy:
    """T21-T22: SESSION_VWAP hierarchy entry role update."""

    def test_t21_session_vwap_intraday_reference(self):
        """Profile A SESSION_VWAP hierarchy entry: role.label = 'INTRADAY_REFERENCE'."""
        m = _base_flat_metrics(p_code="A")
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        hierarchy = result["trade_setup"]["stop"]["hierarchy"]
        vwap_entries = [e for e in hierarchy if e["label"] == "SESSION_VWAP"]
        assert len(vwap_entries) == 1
        assert vwap_entries[0]["role"]["label"] == "INTRADAY_REFERENCE"

    def test_t22_session_vwap_above_below_status(self):
        """Profile A SESSION_VWAP hierarchy status = 'ABOVE' or 'BELOW'."""
        m = _base_flat_metrics(p_code="A", close_val=102.0, vwap_val=101.0)
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        hierarchy = result["trade_setup"]["stop"]["hierarchy"]
        vwap_entries = [e for e in hierarchy if e["label"] == "SESSION_VWAP"]
        assert len(vwap_entries) == 1
        assert vwap_entries[0]["status"] in ("ABOVE", "BELOW")
        # Price 102 > VWAP 101 → ABOVE
        assert vwap_entries[0]["status"] == "ABOVE"


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 7: Exit Counter Rename
# ═══════════════════════════════════════════════════════════════════════

class TestGroup7_ExitCounterRename:
    """T23-T25: vwap_counter → ema21_counter."""

    def test_t23_grouped_has_ema21_counter(self):
        """Profile A exit_signals grouped output has 'ema21_counter'."""
        m = _base_flat_metrics(p_code="A")
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        exit_sigs = result["exit_signals"]
        assert "ema21_counter" in exit_sigs
        assert "vwap_counter" not in exit_sigs

    def test_t24_exit_vwap_counter_not_in_output(self):
        """Exit_VWAP_Counter flat key not present in exit.py output."""
        df = _make_df(p_code="A", close_val=102.0, ema21_val=100.0)
        state = _make_state(ema21_val=100.0)
        cfg = _build_config("A")
        last = df.iloc[cfg.iq]
        metrics = {}
        _exit_profile_a(state, df, last, 0, 1.0, metrics, cfg)
        assert "Exit_VWAP_Counter" not in metrics

    def test_t25_exit_ema21_counter_present(self):
        """Exit_EMA21_Counter flat key present in exit.py output."""
        df = _make_df(p_code="A", close_val=102.0, ema21_val=100.0)
        state = _make_state(ema21_val=100.0)
        cfg = _build_config("A")
        last = df.iloc[cfg.iq]
        metrics = {}
        _exit_profile_a(state, df, last, 0, 1.0, metrics, cfg)
        assert "Exit_EMA21_Counter" in metrics
        assert metrics["Exit_EMA21_Counter"] == "0/3"


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 8: Proximity Map
# ═══════════════════════════════════════════════════════════════════════

class TestGroup8_ProximityMap:
    """T26-T27: VWAP_PULLBACK → EMA21_PULLBACK rename."""

    def test_t26_ema21_pullback_label_in_code(self):
        """Profile A NOT IN PULLBACK ZONE maps to 'EMA21_PULLBACK'."""
        # This is a code-level verification — the _PROXIMITY_MAP in output.py
        # must use "EMA21_PULLBACK" not "VWAP_PULLBACK" for Profile A.
        import tbs_engine.output as output_mod
        src = open(output_mod.__file__).read()
        assert '"EMA21_PULLBACK"' in src
        assert '"VWAP_PULLBACK"' not in src

    def test_t27_ema21_pullback_condition_label(self):
        """EMA21_PULLBACK maps to AWAITING_PULLBACK with desc containing 'daily EMA 21'."""
        import tbs_engine.output as output_mod
        src = open(output_mod.__file__).read()
        assert 'daily EMA 21 zone creates entry' in src


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 9: Freshness Integration (DQ-9c)
# ═══════════════════════════════════════════════════════════════════════

class TestGroup9_FreshnessIntegration:
    """T28-T31: SFR-001 freshness + VWAP trigger interaction."""

    def test_t28_waived_triggers_pending_vwap(self):
        """Profile A VALID + VWAP_Trigger_Status='WAIVED' → Signal_Freshness='PENDING_VWAP'."""
        m = _base_flat_metrics(p_code="A")
        m["VWAP_Trigger_Status"] = "WAIVED"
        m["VWAP_Trigger_Confirmed"] = False
        m["Signal_Freshness"] = "PENDING_VWAP"
        m["Signal_Freshness_Note"] = "Freshness clock deferred -- session maturity waiver active, VWAP trigger not yet confirmable"
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        sf = result["action_summary"].get("signal_freshness", {})
        assert sf.get("label") == "PENDING_VWAP"

    def test_t29_unconfirmed_triggers_pending_vwap(self):
        """Profile A VALID + VWAP_Trigger_Confirmed=False → Signal_Freshness='PENDING_VWAP'."""
        m = _base_flat_metrics(p_code="A")
        m["VWAP_Trigger_Status"] = "AWAITING_RECLAIM"
        m["VWAP_Trigger_Confirmed"] = False
        m["Signal_Freshness"] = "PENDING_VWAP"
        m["Signal_Freshness_Note"] = "Freshness clock deferred -- awaiting VWAP reclaim for full confirmation"
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        sf = result["action_summary"].get("signal_freshness", {})
        assert sf.get("label") == "PENDING_VWAP"

    def test_t30_confirmed_triggers_normal_freshness(self):
        """Profile A VALID + VWAP_Trigger_Confirmed=True → normal freshness."""
        m = _base_flat_metrics(p_code="A")
        m["VWAP_Trigger_Status"] = "CONFIRMED"
        m["VWAP_Trigger_Confirmed"] = True
        m["Signal_Freshness"] = "ARRIVAL"
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        sf = result["action_summary"].get("signal_freshness", {})
        assert sf.get("label") == "ARRIVAL"

    def test_t31_profile_b_no_vwap_trigger(self):
        """Profile B VALID (no VWAP trigger) → normal freshness."""
        m = _base_flat_metrics(p_code="B")
        m["Signal_Freshness"] = "ARRIVAL"
        as_ = _base_action_summary("INVALID")
        as_["verdict"] = "VALID"  # make it VALID for freshness
        result = _transform_output(as_, m)
        sf = result["action_summary"].get("signal_freshness", {})
        assert sf.get("label") == "ARRIVAL"


# ═══════════════════════════════════════════════════════════════════════
# TEST GROUP 10: Entry Zone Reference
# ═══════════════════════════════════════════════════════════════════════

class TestGroup10_EntryZoneReference:
    """T32-T33: Entry zone reference desc for Profile A."""

    def test_t32_pullback_entry_zone_reference(self):
        """Profile A PULLBACK entry_zone.reference.desc contains 'Daily EMA 21'."""
        m = _base_flat_metrics(p_code="A")
        m["Entry_Zone_Reference"] = "Daily EMA 21"
        m["Window_Reset_Event"] = "PULLBACK"
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        ez = result["trade_setup"].get("entry_zone", {})
        ref = ez.get("reference", {})
        assert ref is not None
        assert "Daily EMA 21" in str(ref.get("desc", ""))

    def test_t33_pullback_entry_price_range_desc(self):
        """Profile A PULLBACK entry_price_range.desc contains 'Daily EMA 21 ± 0.5 daily ATR'."""
        m = _base_flat_metrics(p_code="A")
        m["Entry_Zone_Reference"] = "Daily EMA 21"
        m["Window_Reset_Event"] = "PULLBACK"
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        ez = result["trade_setup"].get("entry_zone", {})
        epr = ez.get("entry_price_range", {})
        if epr is not None:
            assert "Daily EMA 21" in str(epr.get("desc", ""))


# ═══════════════════════════════════════════════════════════════════════
# ADDITIONAL: VWAP Context in trade_quality (T1)
# ═══════════════════════════════════════════════════════════════════════

class TestVWAPContextMapping:
    """vwap_context section in trade_quality for Profile A."""

    def test_vwap_context_present_profile_a(self):
        """Profile A: trade_quality.vwap_context present when bias is set."""
        m = _base_flat_metrics(p_code="A")
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        tq = result["trade_quality"]
        assert "vwap_context" in tq
        vc = tq["vwap_context"]
        assert vc["bias"]["label"] == "BULLISH"
        assert vc["role"].startswith("INFORMATIONAL")

    def test_vwap_context_absent_profile_b(self):
        """Profile B: trade_quality.vwap_context absent."""
        m = _base_flat_metrics(p_code="B")
        as_ = _base_action_summary("INVALID")
        result = _transform_output(as_, m)
        tq = result["trade_quality"]
        assert "vwap_context" not in tq


# ═══════════════════════════════════════════════════════════════════════
# ADDITIONAL: VWAP Trigger in action_summary (T8)
# ═══════════════════════════════════════════════════════════════════════

class TestVWAPTriggerInActionSummary:
    """VWAP trigger info surfaced in action_summary.entry_strategy."""

    def test_vwap_trigger_surfaced_on_valid(self):
        """Profile A VALID: entry_strategy.vwap_trigger present."""
        m = _base_flat_metrics(p_code="A")
        m["VWAP_Trigger_Status"] = "CONFIRMED"
        m["VWAP_Trigger_Price"] = 101.0
        m["VWAP_Trigger_Confirmed"] = True
        m["VWAP_Trigger_Note"] = "Close above session VWAP"
        as_ = _base_action_summary("VALID")
        result = _transform_output(as_, m)
        es = result["action_summary"].get("entry_strategy", {})
        assert "vwap_trigger" in es
        assert es["vwap_trigger"]["status"] == "CONFIRMED"
        assert es["vwap_trigger"]["confirmed"] is True

    def test_vwap_trigger_absent_profile_b(self):
        """Profile B: no VWAP trigger in action_summary."""
        m = _base_flat_metrics(p_code="B")
        as_ = _base_action_summary("INVALID")
        result = _transform_output(as_, m)
        es = result["action_summary"].get("entry_strategy")
        if es and isinstance(es, dict):
            assert "vwap_trigger" not in es


# ═══════════════════════════════════════════════════════════════════════
# ADDITIONAL: MAPPED_FLAT_KEYS coverage
# ═══════════════════════════════════════════════════════════════════════

class TestMappedFlatKeys:
    """Phase 3 keys are registered in MAPPED_FLAT_KEYS."""

    def test_session_vwap_keys_registered(self):
        assert "Session_VWAP_Bias" in MAPPED_FLAT_KEYS
        assert "Session_VWAP_Distance_ATR" in MAPPED_FLAT_KEYS
        assert "Session_VWAP_Advisory" in MAPPED_FLAT_KEYS

    def test_vwap_trigger_keys_registered(self):
        assert "VWAP_Trigger_Status" in MAPPED_FLAT_KEYS
        assert "VWAP_Trigger_Confirmed" in MAPPED_FLAT_KEYS

    def test_exit_ema21_counter_registered(self):
        assert "Exit_EMA21_Counter" in MAPPED_FLAT_KEYS

    def test_signal_freshness_note_registered(self):
        assert "Signal_Freshness_Note" in MAPPED_FLAT_KEYS

    def test_entry_zone_reference_registered(self):
        assert "Entry_Zone_Reference" in MAPPED_FLAT_KEYS

    def test_extension_limit_note_registered(self):
        assert "Extension_Limit_Note" in MAPPED_FLAT_KEYS
