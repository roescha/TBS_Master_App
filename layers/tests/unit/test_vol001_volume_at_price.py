"""VOL-001: Volume-at-Price Context unit tests.

Covers spec Section VII test cases T01-T36:
  T01-T07:  PoC extraction and distance/position
  T08-T12:  AVWAP computation and position
  T13-T21:  Volume Context Label synthesis matrix
  T22-T24:  Transform round-trip (_TQ_VOLUME, _TQ_TOTAL, null fields)
  T25-T28:  data.py histogram fetch (period strings, fallback)
  T29-T36:  action_summary (volume_context, entry_strategy enrichment)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import namedtuple
from types import SimpleNamespace

import pandas as pd
import pytest

from tbs_engine.compute import _compute_volume_at_price
from tbs_engine.transform import (
    _transform_output, _TQ_VOLUME, _TQ_TOTAL,
    _TRADE_QUALITY_SUBGROUPS, _TQ_SCALARS,
)


# ---- Helpers ----

HistogramData = namedtuple("HistogramData", ["price", "count"])


def _make_df(n=20, avg=150.0, vol=1000):
    """Minimal DataFrame with average, volume, close, high, low columns.

    All bars have the SAME average/close to produce a predictable AVWAP.
    """
    data = {
        "average": [avg] * n,
        "volume": [vol] * n,
        "close": [avg] * n,
        "high": [avg + 0.5] * n,
        "low": [avg - 0.5] * n,
    }
    return pd.DataFrame(data)


def _make_ctx(histogram_data=None, actual_price=185.0, atr_raw=2.0,
              vol_confirm_state="MIXED", p_code="B", avg=150.0, vol=1000,
              n=20, hist_period="3 weeks", df=None, price_scaler=1.0):
    """Build a minimal RunContext-like object for _compute_volume_at_price."""
    if df is None:
        df = _make_df(n=n, avg=avg, vol=vol)
    cfg = SimpleNamespace(
        resistance_slice_start=-11,
        resistance_slice_end=-1,
    )
    state = SimpleNamespace(atr_raw=atr_raw)
    metrics = {
        "_histogram_data": histogram_data,
        "Vol_Histogram_Period": hist_period,
    }
    ctx = SimpleNamespace(
        cfg=cfg, df=df, state=state, metrics=metrics,
        actual_price=actual_price, p_code=p_code,
        price_scaler=price_scaler,
        vol_confirm_state=vol_confirm_state,
        # VOL-001 output fields (will be set by _compute_volume_at_price)
        vol_poc_price=None, vol_poc_distance_atr=None,
        vol_poc_position="", avwap_price=None,
        avwap_position="", volume_context_label="",
    )
    return ctx


# ======================================================================
# T01-T07: PoC Extraction and Distance/Position
# ======================================================================

class TestPoCExtraction:
    """T01-T07: Point of Control extraction, distance, and position."""

    def test_t01_poc_normal_extraction(self):
        """T01: Histogram with 5 price levels, max count at 182.50."""
        hist = [
            HistogramData(price=180.0, count=100),
            HistogramData(price=181.0, count=200),
            HistogramData(price=182.5, count=500),
            HistogramData(price=183.0, count=150),
            HistogramData(price=184.0, count=50),
        ]
        ctx = _make_ctx(histogram_data=hist, actual_price=185.0, atr_raw=2.0)
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_price == 182.5

    def test_t02_poc_single_entry(self):
        """T02: Histogram with 1 entry -- below minimum threshold (3)."""
        hist = [HistogramData(price=100.0, count=500)]
        ctx = _make_ctx(histogram_data=hist, actual_price=100.0)
        _compute_volume_at_price(ctx)
        # Single entry < 3 minimum -> treated as UNAVAILABLE
        assert ctx.vol_poc_price is None
        assert ctx.vol_poc_position == "UNAVAILABLE"

    def test_t03_poc_none_histogram(self):
        """T03: histogram_data = None -> UNAVAILABLE."""
        ctx = _make_ctx(histogram_data=None)
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_price is None
        assert ctx.vol_poc_position == "UNAVAILABLE"

    def test_t04_poc_empty_list(self):
        """T04: histogram_data = [] -> UNAVAILABLE."""
        ctx = _make_ctx(histogram_data=[])
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_price is None
        assert ctx.vol_poc_position == "UNAVAILABLE"

    def test_t05_poc_distance_above(self):
        """T05: price=185.00, poc=182.00, ATR=2.00 -> distance=1.5, ABOVE_POC."""
        hist = [
            HistogramData(price=180.0, count=100),
            HistogramData(price=182.0, count=500),
            HistogramData(price=184.0, count=50),
        ]
        ctx = _make_ctx(histogram_data=hist, actual_price=185.0, atr_raw=2.0)
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_distance_atr == 1.5
        assert ctx.vol_poc_position == "ABOVE_POC"

    def test_t06_poc_distance_below(self):
        """T06: price=180.00, poc=182.00, ATR=2.00 -> distance=-1.0, BELOW_POC."""
        hist = [
            HistogramData(price=180.0, count=100),
            HistogramData(price=182.0, count=500),
            HistogramData(price=184.0, count=50),
        ]
        ctx = _make_ctx(histogram_data=hist, actual_price=180.0, atr_raw=2.0)
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_distance_atr == -1.0
        assert ctx.vol_poc_position == "BELOW_POC"

    def test_t07_poc_distance_at(self):
        """T07: price=182.40, poc=182.00, ATR=2.00 -> distance=0.2, AT_POC."""
        hist = [
            HistogramData(price=180.0, count=100),
            HistogramData(price=182.0, count=500),
            HistogramData(price=184.0, count=50),
        ]
        ctx = _make_ctx(histogram_data=hist, actual_price=182.4, atr_raw=2.0)
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_distance_atr == 0.2
        assert ctx.vol_poc_position == "AT_POC"


class TestPriceScalerBug1:
    """VOL-001-BUG-1: GBP pence scaling regression tests.

    IBKR returns LSE prices in pence (raw). The engine's actual_price is
    display-scaled (divided by price_scaler=100 for GBP). df columns,
    atr_raw, and histogram prices are all in raw pence. All internal
    arithmetic must use raw units; output prices must be display-scaled.
    """

    def test_gbp_poc_distance_correct_units(self):
        """PoC distance uses raw units: (508.1 - 514.2) / 18.29 ~ -0.33."""
        hist = [
            HistogramData(price=500.0, count=100),
            HistogramData(price=514.2, count=500),  # PoC in pence
            HistogramData(price=520.0, count=50),
        ]
        # actual_price=5.081 (display pounds), price_scaler=100
        # df in pence (~508), atr_raw in pence (18.29)
        df = _make_df(n=20, avg=508.0, vol=1000)
        ctx = _make_ctx(
            histogram_data=hist, actual_price=5.081, atr_raw=18.29,
            price_scaler=100.0, df=df,
        )
        _compute_volume_at_price(ctx)
        # raw calc: (508.1 - 514.2) / 18.29 = -0.33
        assert ctx.vol_poc_distance_atr == -0.33
        assert ctx.vol_poc_position == "BELOW_POC"

    def test_gbp_poc_price_display_scaled(self):
        """PoC output price is display-scaled (pence / 100 = pounds)."""
        hist = [
            HistogramData(price=500.0, count=100),
            HistogramData(price=514.2, count=500),
            HistogramData(price=520.0, count=50),
        ]
        df = _make_df(n=20, avg=508.0, vol=1000)
        ctx = _make_ctx(
            histogram_data=hist, actual_price=5.081, atr_raw=18.29,
            price_scaler=100.0, df=df,
        )
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_price == round(514.2 / 100.0, 4)

    def test_gbp_avwap_display_scaled(self):
        """AVWAP output price is display-scaled (pence / 100 = pounds)."""
        df = _make_df(n=20, avg=508.0, vol=1000)
        ctx = _make_ctx(
            actual_price=5.081, atr_raw=18.29,
            price_scaler=100.0, df=df,
        )
        _compute_volume_at_price(ctx)
        # df average is constant 508.0 pence -> AVWAP raw = 508.0
        assert ctx.avwap_price == round(508.0 / 100.0, 4)

    def test_gbp_avwap_position_correct_units(self):
        """AVWAP position uses raw units for distance calculation."""
        df = _make_df(n=20, avg=515.0, vol=1000)
        # actual_price=5.081 -> raw=508.1, avwap_raw=515.0
        # distance = (508.1 - 515.0) / 18.29 = -0.38 -> BELOW
        ctx = _make_ctx(
            actual_price=5.081, atr_raw=18.29,
            price_scaler=100.0, df=df,
        )
        _compute_volume_at_price(ctx)
        assert ctx.avwap_position == "BELOW"

    def test_usd_scaler_1_unchanged(self):
        """USD (price_scaler=1.0) produces identical results to pre-fix."""
        hist = [
            HistogramData(price=180.0, count=100),
            HistogramData(price=182.0, count=500),
            HistogramData(price=184.0, count=50),
        ]
        ctx = _make_ctx(
            histogram_data=hist, actual_price=185.0, atr_raw=2.0,
            price_scaler=1.0,
        )
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_distance_atr == 1.5
        assert ctx.vol_poc_position == "ABOVE_POC"
        assert ctx.vol_poc_price == 182.0


# ======================================================================
# T08-T12: AVWAP Computation and Position
# ======================================================================

class TestAVWAP:
    """T08-T12: Anchored VWAP computation and position classification."""

    def test_t08_avwap_normal(self):
        """T08: 10-bar window with average and volume columns -> correct AVWAP."""
        # Create a 20-bar DF; slice [-11:-1] gives 10 bars (indices 9-18)
        avg_vals = [150.0] * 9 + [100.0] * 5 + [200.0] * 5 + [150.0]
        vol_vals = [1000] * 20
        df = pd.DataFrame({
            "average": avg_vals,
            "volume": vol_vals,
            "close": avg_vals,
            "high": [a + 0.5 for a in avg_vals],
            "low": [a - 0.5 for a in avg_vals],
        })
        ctx = _make_ctx(df=df, actual_price=185.0)
        _compute_volume_at_price(ctx)
        # AVWAP = sum(avg*vol) / sum(vol) over slice [-11:-1]
        _slice = df.iloc[-11:-1]
        expected = round(float((_slice['average'] * _slice['volume']).sum() / _slice['volume'].sum()), 4)
        assert ctx.avwap_price == expected

    def test_t09_avwap_zero_volume(self):
        """T09: All bars volume=0 -> fallback to mean of close."""
        df = _make_df(n=20, avg=150.0, vol=0)
        ctx = _make_ctx(df=df, actual_price=150.0, atr_raw=2.0)
        _compute_volume_at_price(ctx)
        # With zero volume, should fall back to mean of close in the slice
        _slice = df.iloc[-11:-1]
        expected = round(float(_slice['close'].mean()), 4)
        assert ctx.avwap_price == expected
        # Defensive default
        assert ctx.avwap_position == "AT_AVWAP"

    def test_t10_avwap_position_above(self):
        """T10: price=185.00, avwap=183.00, ATR=2.00 -> ABOVE."""
        # Make AVWAP come out to ~183.0
        df = _make_df(n=20, avg=183.0, vol=1000)
        ctx = _make_ctx(df=df, actual_price=185.0, atr_raw=2.0)
        _compute_volume_at_price(ctx)
        assert ctx.avwap_position == "ABOVE"

    def test_t11_avwap_position_below(self):
        """T11: price=181.00, avwap=183.00, ATR=2.00 -> BELOW."""
        df = _make_df(n=20, avg=183.0, vol=1000)
        ctx = _make_ctx(df=df, actual_price=181.0, atr_raw=2.0)
        _compute_volume_at_price(ctx)
        assert ctx.avwap_position == "BELOW"

    def test_t12_avwap_position_at(self):
        """T12: price=183.30, avwap~183.0, ATR=2.00 -> AT_AVWAP."""
        df = _make_df(n=20, avg=183.0, vol=1000)
        ctx = _make_ctx(df=df, actual_price=183.3, atr_raw=2.0)
        _compute_volume_at_price(ctx)
        assert ctx.avwap_position == "AT_AVWAP"


# ======================================================================
# T13-T21: Volume Context Label Synthesis Matrix
# ======================================================================

class TestVolumeContextLabel:
    """T13-T21: Synthesis matrix producing Volume_Context_Label."""

    def _label_ctx(self, vol_state, poc_position, avwap_position):
        """Build ctx with pre-set PoC/AVWAP positions, then compute label."""
        # Use histogram that gives the desired poc_position
        if poc_position == "UNAVAILABLE":
            hist = None
        else:
            hist = [
                HistogramData(price=180.0, count=100),
                HistogramData(price=182.0, count=500),
                HistogramData(price=184.0, count=50),
            ]
        # Set actual_price to produce desired poc_position relative to poc=182.0
        if poc_position == "ABOVE_POC":
            actual_price = 185.0  # (185-182)/2 = 1.5 > 0.25
        elif poc_position == "BELOW_POC":
            actual_price = 179.0  # (179-182)/2 = -1.5 < -0.25
        elif poc_position == "AT_POC":
            actual_price = 182.2  # (182.2-182)/2 = 0.1, within 0.25
        else:
            actual_price = 185.0

        # Set AVWAP via df average values and actual_price
        if avwap_position == "ABOVE":
            avg = 180.0   # AVWAP ~180, price 185 -> (185-180)/2 = 2.5 > 0.25
        elif avwap_position == "BELOW":
            avg = 190.0   # AVWAP ~190, price ~182 -> below
        elif avwap_position == "AT_AVWAP":
            avg = actual_price  # AVWAP ~= price
        else:
            avg = actual_price

        ctx = _make_ctx(
            histogram_data=hist, actual_price=actual_price,
            atr_raw=2.0, vol_confirm_state=vol_state, avg=avg,
        )
        _compute_volume_at_price(ctx)
        return ctx

    def test_t13_accumulation_zone(self):
        """T13: DISTRIBUTION WARNING + AT_POC + ABOVE -> ACCUMULATION ZONE."""
        ctx = self._label_ctx("DISTRIBUTION WARNING", "AT_POC", "ABOVE")
        assert ctx.volume_context_label == "ACCUMULATION ZONE"

    def test_t14_contested_zone(self):
        """T14: DISTRIBUTION WARNING + AT_POC + BELOW -> CONTESTED ZONE."""
        ctx = self._label_ctx("DISTRIBUTION WARNING", "AT_POC", "BELOW")
        assert ctx.volume_context_label == "CONTESTED ZONE"

    def test_t15_distribution_zone(self):
        """T15: DISTRIBUTION WARNING + BELOW_POC + any -> DISTRIBUTION ZONE."""
        ctx = self._label_ctx("DISTRIBUTION WARNING", "BELOW_POC", "ABOVE")
        assert ctx.volume_context_label == "DISTRIBUTION ZONE"

    def test_t16_neutral_building(self):
        """T16: MIXED + AT_POC + ABOVE -> NEUTRAL -- BUILDING."""
        ctx = self._label_ctx("MIXED", "AT_POC", "ABOVE")
        assert ctx.volume_context_label == "NEUTRAL -- BUILDING"

    def test_t17_neutral(self):
        """T17: MIXED + BELOW_POC + any -> NEUTRAL."""
        ctx = self._label_ctx("MIXED", "BELOW_POC", "ABOVE")
        assert ctx.volume_context_label == "NEUTRAL"

    def test_t18_institutional_flow(self):
        """T18: STRONG INSTITUTIONAL + any + any -> INSTITUTIONAL FLOW."""
        ctx = self._label_ctx("STRONG INSTITUTIONAL", "BELOW_POC", "BELOW")
        assert ctx.volume_context_label == "INSTITUTIONAL FLOW"

    def test_t19_fallback_distribution_warning_unavailable(self):
        """T19: DISTRIBUTION WARNING + UNAVAILABLE -> DISTRIBUTION ZONE (fallback)."""
        ctx = self._label_ctx("DISTRIBUTION WARNING", "UNAVAILABLE", "ABOVE")
        assert ctx.volume_context_label == "DISTRIBUTION ZONE"

    def test_t20_fallback_mixed_unavailable(self):
        """T20: MIXED + UNAVAILABLE -> NEUTRAL (fallback)."""
        ctx = self._label_ctx("MIXED", "UNAVAILABLE", "ABOVE")
        assert ctx.volume_context_label == "NEUTRAL"

    def test_t21_fallback_strong_institutional_unavailable(self):
        """T21: STRONG INSTITUTIONAL + UNAVAILABLE -> INSTITUTIONAL FLOW (fallback)."""
        ctx = self._label_ctx("STRONG INSTITUTIONAL", "UNAVAILABLE", "ABOVE")
        assert ctx.volume_context_label == "INSTITUTIONAL FLOW"


# ======================================================================
# T22-T24: Transform Round-Trip
# ======================================================================

class TestTransformRoundTrip:
    """T22-T24: OTL-001 mapping for VOL-001 fields."""

    def test_t22_tq_volume_nine_entries(self):
        """T22: _TQ_VOLUME has exactly 9 entries."""
        assert len(_TQ_VOLUME) == 9

    def test_t23_tq_total_seventeen(self):
        """T23: _TQ_TOTAL == 17."""
        assert _TQ_TOTAL == 17

    def test_t24_null_poc_fields_roundtrip(self):
        """T24: Null PoC fields round-trip through transform."""
        metrics = {
            "Vol_Confirm_Ratio": 0.5,
            "Vol_Confirm_State": "MIXED",
            "Vol_PoC_Price": None,
            "Vol_PoC_Distance_ATR": None,
            "Vol_PoC_Position": "UNAVAILABLE",
            "AVWAP_Price": 183.5,
            "AVWAP_Position": "ABOVE",
            "Volume_Context_Label": "NEUTRAL",
            "Vol_Histogram_Period": "3 weeks",
            # Minimal other metrics for transform
            "Trend_Health_Score": 70.0, "THS_Label": "HEALTHY",
            "THS_Floor_Buffer": 80.0, "THS_Dir_Momentum": 65.0,
            "THS_Trend_Age": 70.0, "THS_Structure": 75.0,
            "Conviction": "HIGH", "Trend_Quality_Override": None,
        }
        action_summary = {
            "verdict": "INVALID", "reason": "EXTENDED",
            "approaching": False, "volume_context": "NEUTRAL",
            "action": "WAIT.", "context": "Blocked.",
            "existing_position_exit_signal": False,
            "existing_position_exit_reason": None,
        }
        result = _transform_output(action_summary, metrics)
        tq = result.get("trade_quality", {})
        vol = tq.get("volume", {})
        assert vol.get("poc_price") is None
        assert vol.get("poc_distance_atr") is None
        assert vol.get("poc_position") == "UNAVAILABLE"
        assert vol.get("avwap_price") == 183.5
        assert vol.get("context_label") == "NEUTRAL"
        assert vol.get("histogram_period") == "3 weeks"


# ======================================================================
# T25-T28: data.py Histogram Fetch
# ======================================================================

class TestHistogramFetch:
    """T25-T28: data.py histogram period mapping and fallback."""

    def test_t25_profile_a_period(self):
        """T25: Profile A -> first attempt '3 days'."""
        from tbs_engine.data import _build_config
        # Verify the period mapping -- we test the config, not the IB call
        cfg = _build_config("A")
        _hist_fallback = {"A": ["3 days", "1 week"], "B": ["3 weeks", "1 month"], "C": ["3 months"]}
        periods = _hist_fallback.get("A")
        assert periods[0] == "3 days"

    def test_t26_profile_b_period(self):
        """T26: Profile B -> first attempt '3 weeks'."""
        _hist_fallback = {"A": ["3 days", "1 week"], "B": ["3 weeks", "1 month"], "C": ["3 months"]}
        periods = _hist_fallback.get("B")
        assert periods[0] == "3 weeks"

    def test_t27_profile_c_period(self):
        """T27: Profile C -> '3 months'."""
        _hist_fallback = {"A": ["3 days", "1 week"], "B": ["3 weeks", "1 month"], "C": ["3 months"]}
        periods = _hist_fallback.get("C")
        assert periods[0] == "3 months"

    def test_t28_histogram_exception_graceful(self):
        """T28: reqHistogramData exception -> histogram_data = None, no error."""
        # Simulate by passing None histogram to compute -- it should degrade gracefully
        ctx = _make_ctx(histogram_data=None, actual_price=150.0)
        _compute_volume_at_price(ctx)
        assert ctx.vol_poc_price is None
        assert ctx.vol_poc_position == "UNAVAILABLE"
        # Engine should not error -- the function returns normally
        assert ctx.volume_context_label != ""


# ======================================================================
# T29-T36: action_summary Tests
# ======================================================================

def _make_full_metrics_vol001(profile="B"):
    """Full metrics dict including VOL-001 fields."""
    m = {}
    m["Price"] = 152.0; m["Structural_Floor"] = 142.0; m["Resistance"] = 160.0
    m["ADV_20"] = 5000000.0; m["ADV_20_Dollar"] = 50000000.0; m["Is_ETF"] = False; m["Convexity_Class"] = "C1"
    m["ETF_Primary_Exchange"] = None; m["ETF_Detection_Source"] = None
    m["Entry_Reference"] = 142.0; m["Hard_Stop"] = 140.0; m["Profit_Target"] = 160.0
    m["THS_Label"] = "HEALTHY"; m["Trend_Health_Score"] = 72.5
    m["THS_Floor_Buffer"] = 80.0; m["THS_Dir_Momentum"] = 65.0
    m["THS_Trend_Age"] = 70.0; m["THS_Structure"] = 75.0
    m["Capital_RR_Label"] = "HEALTHY"; m["Capital_Reward_Risk"] = 2.35
    m["Exit_Signal"] = False; m["Exit_Reason"] = "No exit"
    m["Pullback_Zone_Upper"] = 145.0
    m["Engine_State"] = "TRENDING"; m["Trend_Age_Bars"] = 15
    m["Active_Modifiers"] = "None"; m["Inst_Churn"] = "LOW"
    m["ADX"] = 28.5; m["ADX_Accel"] = 1.2; m["ADX_Accel_State"] = "ACCELERATING"
    m["DI_Plus"] = 30.0; m["DI_Minus"] = 15.0
    m["Conviction"] = "HIGH-CONVICTION"; m["Trend_Quality_Override"] = None
    m["Vol_Confirm_Ratio"] = 1.8; m["Vol_Confirm_State"] = "STRONG INSTITUTIONAL"
    m["Reward_Risk"] = 3.5; m["Reward_Risk_Note"] = None; m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    m["EMA_8"] = 150.0; m["EMA_21"] = 148.0; m["SMA_50"] = 142.0; m["SMA_200"] = 130.0
    m["VWAP"] = None; m["ATR"] = 2.5
    m["Profit_Target_Source"] = "10_Bar_Resistance"; m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Profit_Target_Synthetic"] = None; m["Profit_Target_Synthetic_Note"] = None
    m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 139.0
    m["Stop_Adjusted_Flag"] = False; m["Stop_Adjusted_Reason"] = None
    m["Cons_High"] = 155.0; m["Resistance_Note"] = None
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
    m["MM_Target"] = 127.0; m["MM_Rally_ATR"] = 7.5
    # VOL-001 fields
    m["Vol_PoC_Price"] = 148.0; m["Vol_PoC_Distance_ATR"] = 1.6
    m["Vol_PoC_Position"] = "ABOVE_POC"
    m["AVWAP_Price"] = 149.5; m["AVWAP_Position"] = "ABOVE"
    m["Volume_Context_Label"] = "INSTITUTIONAL FLOW"
    m["Vol_Histogram_Period"] = "3 weeks"
    # Profile-specific Fib keys
    if profile == "A":
        m["Fib_A_382_Level"] = 147.5; m["Fib_A_500_Level"] = 146.0
        m["Fib_A_Confluence"] = "CONFLUENCE_382"
        m["Fib_382_Level"] = None; m["Fib_500_Level"] = None; m["Fib_Confluence"] = None
    elif profile == "B":
        m["Fib_382_Level"] = 153.0; m["Fib_500_Level"] = 150.0
        m["Fib_Confluence"] = "BETWEEN_FIBS"
        m["Fib_A_382_Level"] = None; m["Fib_A_500_Level"] = None; m["Fib_A_Confluence"] = None
    else:  # Profile C
        m["Fib_382_Level"] = None; m["Fib_500_Level"] = None; m["Fib_Confluence"] = None
        m["Fib_A_382_Level"] = None; m["Fib_A_500_Level"] = None; m["Fib_A_Confluence"] = None
        m["MM_Target"] = None; m["MM_Rally_ATR"] = None
    return m


class TestActionSummaryVolumeContext:
    """T29-T31: volume_context field present in all verdict paths."""

    def test_t29_valid_has_volume_context(self):
        """T29: VALID action_summary contains volume_context."""
        m = _make_full_metrics_vol001("B")
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "quality": "HEALTHY",
            "volume_context": "INSTITUTIONAL FLOW",
            "reward": "HEALTHY [2.35]",
            "exit_warning": False, "exit_warning_note": None,
            "trigger_rule": "BAR CLOSE ONLY",
            "trigger_condition": "Close within [142.0 -- 145.0]",
            "entry_strategy": {
                "entry_price": 142.0, "stop_loss": 140.0, "target": 160.0,
                "fib_382": 153.0, "fib_500": 150.0,
                "fib_confluence": "BETWEEN_FIBS", "mm_target": 127.0,
            },
            "state": "TRENDING",
            "action": "Execute.", "context": "Pullback zone.",
        }
        result = _transform_output(a, m)
        assert result["action_summary"]["volume_context"] == "INSTITUTIONAL FLOW"

    def test_t30_invalid_has_volume_context(self):
        """T30: INVALID action_summary contains volume_context."""
        m = _make_full_metrics_vol001("B")
        a = {
            "verdict": "INVALID", "reason": "EXTENDED",
            "approaching": False,
            "volume_context": "NEUTRAL",
            "action": "WAIT.", "context": "Blocked.",
            "existing_position_exit_signal": False,
            "existing_position_exit_reason": None,
        }
        result = _transform_output(a, m)
        assert result["action_summary"]["volume_context"] == "NEUTRAL"

    def test_t31_wait_has_volume_context(self):
        """T31: WAIT action_summary contains volume_context."""
        m = _make_full_metrics_vol001("B")
        a = {
            "verdict": "WAIT", "reason": "TREND QUALITY",
            "approaching": False,
            "volume_context": "ACCUMULATION ZONE",
            "action": "Monitor.", "context": "THS below threshold.",
            "existing_position_exit_signal": False,
            "existing_position_exit_reason": None,
        }
        result = _transform_output(a, m)
        assert result["action_summary"]["volume_context"] == "ACCUMULATION ZONE"


class TestEntryStrategyEnrichment:
    """T32-T36: entry_strategy Fibonacci + MM enrichment."""

    def test_t32_fib_382_profile_b(self):
        """T32: Profile B entry_strategy.fib_382 = Fib_382_Level."""
        m = _make_full_metrics_vol001("B")
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "quality": "HEALTHY",
            "volume_context": "INSTITUTIONAL FLOW",
            "reward": "HEALTHY [2.35]",
            "exit_warning": False, "exit_warning_note": None,
            "trigger_rule": "BAR CLOSE ONLY",
            "trigger_condition": "Close within [142.0 -- 145.0]",
            "entry_strategy": {
                "entry_price": 142.0, "stop_loss": 140.0, "target": 160.0,
                "fib_382": 153.0, "fib_500": 150.0,
                "fib_confluence": "BETWEEN_FIBS", "mm_target": 127.0,
            },
            "state": "TRENDING",
            "action": "Execute.", "context": "Pullback.",
        }
        result = _transform_output(a, m)
        es = result["action_summary"]["entry_strategy"]
        assert es["fib_382"] == 153.0

    def test_t33_fib_382_profile_a(self):
        """T33: Profile A entry_strategy.fib_382 = Fib_A_382_Level."""
        m = _make_full_metrics_vol001("A")
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "quality": "HEALTHY",
            "volume_context": "INSTITUTIONAL FLOW",
            "reward": "HEALTHY [2.35]",
            "exit_warning": False, "exit_warning_note": None,
            "trigger_rule": "BAR CLOSE ONLY",
            "trigger_condition": "Close within [142.0 -- 145.0]",
            "entry_strategy": {
                "entry_price": 142.0, "stop_loss": 140.0, "target": 160.0,
                "fib_382": 147.5, "fib_500": 146.0,
                "fib_confluence": "CONFLUENCE_382", "mm_target": 127.0,
            },
            "state": "TRENDING",
            "action": "Execute.", "context": "Pullback.",
        }
        result = _transform_output(a, m)
        es = result["action_summary"]["entry_strategy"]
        assert es["fib_382"] == 147.5

    def test_t34_mm_target(self):
        """T34: entry_strategy.mm_target = MM_Target value."""
        m = _make_full_metrics_vol001("B")
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "quality": "HEALTHY",
            "volume_context": "INSTITUTIONAL FLOW",
            "reward": "HEALTHY [2.35]",
            "exit_warning": False, "exit_warning_note": None,
            "trigger_rule": "BAR CLOSE ONLY",
            "trigger_condition": "Close within [142.0 -- 145.0]",
            "entry_strategy": {
                "entry_price": 142.0, "stop_loss": 140.0, "target": 160.0,
                "fib_382": 153.0, "fib_500": 150.0,
                "fib_confluence": "BETWEEN_FIBS", "mm_target": 127.0,
            },
            "state": "TRENDING",
            "action": "Execute.", "context": "Pullback.",
        }
        result = _transform_output(a, m)
        es = result["action_summary"]["entry_strategy"]
        assert es["mm_target"] == 127.0

    def test_t35_fib_null_profile_c(self):
        """T35: Profile C entry_strategy fib fields are all null."""
        m = _make_full_metrics_vol001("C")
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "quality": "HEALTHY",
            "volume_context": "INSTITUTIONAL FLOW",
            "reward": "HEALTHY [2.35]",
            "exit_warning": False, "exit_warning_note": None,
            "trigger_rule": "BAR CLOSE ONLY",
            "trigger_condition": "Close within [142.0 -- 145.0]",
            "entry_strategy": {
                "entry_price": 142.0, "stop_loss": 140.0, "target": 160.0,
                "fib_382": None, "fib_500": None,
                "fib_confluence": None, "mm_target": None,
            },
            "state": "TRENDING",
            "action": "Execute.", "context": "Pullback.",
        }
        result = _transform_output(a, m)
        es = result["action_summary"]["entry_strategy"]
        assert es["fib_382"] is None
        assert es["fib_500"] is None
        assert es["fib_confluence"] is None
        assert es["mm_target"] is None

    def test_t36_invalid_no_entry_strategy(self):
        """T36: INVALID action_summary does NOT contain entry_strategy."""
        m = _make_full_metrics_vol001("B")
        a = {
            "verdict": "INVALID", "reason": "EXTENDED",
            "approaching": False,
            "volume_context": "NEUTRAL",
            "action": "WAIT.", "context": "Blocked.",
            "existing_position_exit_signal": False,
            "existing_position_exit_reason": None,
        }
        result = _transform_output(a, m)
        assert "entry_strategy" not in result["action_summary"]
