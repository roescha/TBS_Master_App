"""ENG-006 Fibonacci Extension Projections + ENG-003-OBS-1 Confluence Re-Point.

Bundle: ENG006_Fibonacci_Extension_Projections_Bundle_Spec_v1_0.md (§6 test mandate).

Two NON-GATE, output-layer Fibonacci changes sharing the rally-leg block in
output.py ``_assemble_output``:

  ENG-006     — three forward Fibonacci extension projections (127.2% / 161.8%
                / 261.8%) appended to the target hierarchy for Profile A + B,
                projected from the per-profile structural floor (Point C).
  ENG-003-OBS-1 — Profile-A confluence comparison re-pointed from current price
                (last['close']) to the Daily EMA 21 entry-zone reference
                (metrics["Daily_Protective_Anchor"], raw), with a null guard.

Test surface (spec §6):
  - NON-GATE structural guards: NotInGatesFile + VerdictInvariance (both items).
  - Functional: extension formula per profile, Profile C exemption, degenerate
    guards, hierarchy sort position + EXCEEDED routing, MAPPED_FLAT_KEYS +
    round-trip coverage, confluence re-point behaviour, null guard.

The output.py blocks are exercised through the REAL ``_assemble_output`` (focus
chart patched out) so the functional assertions differential-verify: they FAIL
against pre-edit source and PASS post-edit. The transform.py changes are
exercised through the REAL ``_transform_output`` / ``_flatten`` / MAPPED_FLAT_KEYS.

TEST-HRN-001: real-package imports below go through Python's own (idempotent)
sys.modules machinery — no spec_from_file_location exec writes that would
overwrite tbs_engine.types.GateResult and break isinstance() in sibling tests.
"""

import os
import sys
import inspect
import unittest.mock as mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from types import SimpleNamespace

# Real-source imports (canonical package identity — TEST-HRN-001 safe).
from tbs_engine.types import GateResult
from tbs_engine.output import _assemble_output
from tbs_engine.transform import (
    _transform_output, _flatten, MAPPED_FLAT_KEYS, _CONVICTION_TIER_MAP,
)
import tbs_engine.gates as _gates_mod


# ===========================================================================
# Shared geometry (reused across the formula + re-point fixtures)
# ===========================================================================
ORIGIN = 100.0          # rally-window low  (Point A)
PEAK = 120.0            # rally-window high (Point B)
RALLY_RANGE = PEAK - ORIGIN  # 20.0
FLOOR_C = 110.0         # structural floor  (Point C)
ATR_RAW = 2.0
PRICE_SCALER = 1.0

# Display-scaled extension expectations: Point_C + ratio * rally_range
EXP_EXT_1272 = round((FLOOR_C + 1.272 * RALLY_RANGE) / PRICE_SCALER, 2)  # 135.44
EXP_EXT_1618 = round((FLOOR_C + 1.618 * RALLY_RANGE) / PRICE_SCALER, 2)  # 142.36
EXP_EXT_2618 = round((FLOOR_C + 2.618 * RALLY_RANGE) / PRICE_SCALER, 2)  # 162.36

# ENG-003 retracement levels for the same rally leg (raw):
#   _fib_a_382_raw = peak - 0.382 * range ; _fib_a_500_raw = peak - 0.500 * range
FIB_A_382_RAW = PEAK - 0.382 * RALLY_RANGE  # 112.36
FIB_A_500_RAW = PEAK - 0.500 * RALLY_RANGE  # 110.00

BARS_PER_DAY_A = 6.5                       # US session -> session_bars = 19
SESSION_BARS_A = int(BARS_PER_DAY_A * 3)   # 19


# ===========================================================================
# DataFrame + ctx builders for the real _assemble_output
# ===========================================================================

def _build_rally_df(n, origin, peak, close, win_lo_idx, win_hi_idx, anchor):
    """OHLC frame whose target window min(low)=origin and max(high)=peak.

    Baseline low sits above origin and baseline high below peak so the planted
    bars dominate the window extrema. The evaluation bar (iloc[-1]) is excluded
    from every rally window (slices end at -1).
    """
    base_low = origin + 5.0
    base_high = peak - 5.0
    df = pd.DataFrame({
        "open":  [close] * n,
        "close": [close] * n,
        "high":  [base_high] * n,
        "low":   [base_low] * n,
        "EMA_8":  [close] * n,
        "EMA_21": [close] * n,
        "SMA_50": [close] * n,
        "SMA_200": [close] * n,
        "ANCHOR": [anchor] * n,
        "vol_sma_9": [np.nan] * n,
    })
    df.loc[win_lo_idx, "low"] = origin
    df.loc[win_hi_idx, "high"] = peak
    df.loc[n - 1, "close"] = close
    return df


def _df_profile_b(origin=ORIGIN, peak=PEAK, close=118.0, anchor=FLOOR_C, n=15):
    """Profile B rally window = df.iloc[-11:-1] -> indices [n-11, n-2]."""
    return _build_rally_df(n, origin, peak, close, n - 11, n - 6, anchor)


def _df_profile_a(origin=ORIGIN, peak=PEAK, close=118.0, anchor=FLOOR_C, n=30):
    """Profile A rally window = df.iloc[-(19+1):-1] -> indices [n-20, n-2]."""
    return _build_rally_df(n, origin, peak, close, n - 20, n - 10, anchor)


def _make_state(**kw):
    d = dict(
        adx_t=28.0, adx_t1=27.0, di_plus=30.0, di_minus=15.0,
        atr_raw=ATR_RAW, floor_raw=FLOOR_C,
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


def _base_metrics(**overrides):
    """Pre-populated metrics dict broad enough for _assemble_output to complete."""
    m = {}
    m["Price"] = 118.0; m["Structural_Floor"] = FLOOR_C; m["Resistance"] = 160.0
    m["ADV_20"] = 5_000_000.0; m["ADV_20_Dollar"] = 50_000_000.0
    m["Is_ETF"] = False; m["Convexity_Class"] = "C1"
    m["ETF_Primary_Exchange"] = None; m["ETF_Detection_Source"] = None
    m["Entry_Reference"] = FLOOR_C; m["Hard_Stop"] = 108.0; m["Profit_Target"] = 160.0
    m["Capital_RR_Label"] = "HEALTHY"; m["Capital_Reward_Risk"] = 2.35
    m["Exit_Signal"] = False; m["Exit_Reason"] = "No exit"
    m["Pullback_Zone_Upper"] = 119.0
    m["Engine_State"] = "TRENDING"; m["Trend_Age_Bars"] = 15
    m["Active_Modifiers"] = "None"; m["Inst_Churn"] = "LOW"
    m["ADX"] = 28.5; m["ADX_Accel"] = 1.2; m["ADX_Accel_State"] = "ACCELERATING"
    m["DI_Plus"] = 30.0; m["DI_Minus"] = 15.0
    m["Conviction"] = "HIGH-CONVICTION"; m["Trend_Quality_Override"] = None
    m["Vol_Confirm_Ratio"] = 1.8; m["Vol_Confirm_State"] = "STRONG ACCUMULATION"
    m["Reward_Risk"] = 3.5; m["Reward_Risk_Note"] = None; m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    m["EMA_8"] = 118.0; m["EMA_21"] = 116.0; m["SMA_50"] = 112.0; m["SMA_200"] = 100.0
    m["VWAP"] = None; m["ATR"] = ATR_RAW
    m["Profit_Target_Source"] = "10_Bar_Resistance"
    m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Profit_Target_Synthetic"] = None; m["Profit_Target_Synthetic_Note"] = None
    m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 107.0
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
    m.update(overrides)
    return m


def _make_ctx(p_code="B", df=None, structural_floor_raw=FLOOR_C,
              bars_per_day=1.0, state=None, metrics=None, is_etf=False,
              price_scaler=PRICE_SCALER, **kw):
    if state is None:
        state = _make_state()
    if df is None:
        df = _df_profile_b()
    if metrics is None:
        metrics = _base_metrics()
    last = df.iloc[-1]
    cfg = SimpleNamespace(
        fb_max=3.0, ta_max=50, iq=-1, min_bars_required=10,
        window_limit=20, ff_threshold=4,
        ext_limit_trending=1.0, ext_limit_resolving=1.0, ext_limit_etf=1.0,
        resistance_slice_start=-10, resistance_slice_end=None,
        tf_resolution="1D", tf_duration="6mo",
        ctx_resolution="1W", ctx_duration="2y",
        prev_bar_offset=-1, required_ma_cols=("EMA_8", "EMA_21", "SMA_50"),
        pb_upper_col="SMA_50",
    )
    d = dict(
        state=state, cfg=cfg, p_code=p_code, is_etf=is_etf, _is_c3=False,
        df=df, last=last, metrics=metrics, price_scaler=price_scaler,
        actual_price=float(last["close"]),
        structural_floor_raw=structural_floor_raw, hard_stop_raw=108.0,
        resistance_raw=160.0, bars_per_day=bars_per_day, atr_dist=0.5,
        ext_limit=1.0, floor_prox_pct=5.0, adx_accel=0.5,
        adx_accel_state="CRUISING", vol_confirm_ratio=1.2,
        vol_confirm_state="CONFIRMED", exit_signal=False,
        window_count=5, window_limit=20,
        floor_price=FLOOR_C, hard_stop=108.0, resistance_display=160.0,
        _resistance_suppressed=False, chart_ref="", cons_high_raw=155.0,
        risk_a=None, reward_a=None, chart_dir=".", clean_ticker="TEST",
        adx_col="ADX_14", dmp_col="DI+_14", dmn_col="DI-_14",
        profile=("Profile A" if p_code == "A" else "Profile B"),
        prev_high=121.0, prox_anchor=116.0,
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
    d.update(kw)
    return SimpleNamespace(**d)


def _valid_gate():
    return GateResult(
        verdict="VALID", reason="PULLBACK",
        mandate="Execute at THIS bar's close.",
        context="In pullback zone.",
        entry_type="PULLBACK", trigger_rule="BAR CLOSE ONLY",
        state="TRENDING",
    )


def _wait_gate():
    return GateResult(
        verdict="WAIT", reason="THESIS INTACT",
        mandate="WAIT for trigger.", context="No trigger yet.",
    )


def _invalid_gate():
    return GateResult(
        verdict="INVALID", reason="EXTENDED",
        mandate="WAIT. Extended beyond limit.", context="EXTENDED: blocked.",
    )


def _run_assemble(ctx, gate_result):
    """Run the REAL _assemble_output with focus-chart I/O patched out.

    Returns the grouped result. ctx.metrics is mutated in place, so callers can
    read the extension / confluence flat keys off ctx.metrics afterwards.
    """
    with mock.patch("tbs_engine.output._build_focus_chart", return_value=""):
        return _assemble_output(ctx, gate_result, {"mode": "INFO"}, debug=False)


# ===========================================================================
# transform.py fixtures (hierarchy / round-trip)
# ===========================================================================

def _t_action_summary():
    return {
        "verdict": "VALID",
        "reason": {"label": "VALID PULLBACK", "detail": ""},
        "mandate": "ENTER",
        "context": "",
    }


def _t_flat_metrics(**overrides):
    """Flat metrics broad enough for _transform_output's target hierarchy."""
    m = {
        "Price": 130.0,
        "Structural_Floor": 125.0,
        "Floor_Anchor_Type": "EMA_21",
        "Floor_Anchor_Label": "Intraday institutional value level",
        "Anchor_Label": "VWAP (Baseline Floor)",
        "Anchor_Type": "Standard",
        "Extension_Anchor_Type": "VWAP",
        "Extension_Anchor_Label": "Intraday institutional value level",
        "Hard_Stop": 120.0,
        "Resistance": 135.0,
        "EMA_8": 129.0, "EMA_21": 127.0, "SMA_50": 122.0, "SMA_200": 110.0,
        "VWAP": 126.0, "ATR": 2.5,
        "ADV_20": 5_000_000.0, "ADV_20_Dollar": 650_000_000.0, "Is_ETF": False,
        "Profit_Target": 135.0,
        "Profit_Target_Source": "10_Bar_Resistance",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "MM_Target": 140.0,
        "Psych_Floor": 125.0, "Psych_Ceiling": None,
        "Daily_Protective_Anchor": 128.0, "Daily_Hard_Stop": 124.0,
        "Daily_ATR": 3.0, "Context_EMA_21": 128.0, "Context_Daily_SMA50": 123.0,
        "Context_SMA200": 110.0, "AVWAP_Price": 127.5,
        "Established_Hourly_Low": 126.0,
        "Engine_State": "TRENDING", "ADX": 30.0,
        "Active_Modifiers_List": [],
        "window_count": 3, "Window_Limit": 4, "Window_Reset_Event": "PULLBACK",
        "Reward_Risk": 2.5,
        # ENG-006 keys default absent (None)
        "Fib_Ext_1272_Level": None,
        "Fib_Ext_1618_Level": None,
        "Fib_Ext_2618_Level": None,
    }
    m.update(overrides)
    return m


def _target(flat_overrides=None):
    fm = _t_flat_metrics(**(flat_overrides or {}))
    grouped = _transform_output(_t_action_summary(), fm)
    return grouped["trade_setup"]["target"]


# ===========================================================================
# §6 NON-GATE: NotInGatesFile
# ===========================================================================

class TestENG006NotInGatesFile:
    """No gate function reads any ENG-006 extension key (NON-GATE mandate)."""

    def test_extension_keys_absent_from_gates(self):
        src = inspect.getsource(_gates_mod)
        for token in ("Fib_Ext_1272_Level", "Fib_Ext_1618_Level",
                      "Fib_Ext_2618_Level", "FIB_EXTENSION"):
            assert token not in src, (
                f"{token!r} must not appear in gates.py (NON-GATE mandate)"
            )


class TestENG003OBS1NotInGatesFile:
    """No gate verdict branch keys off the Fibonacci confluence label."""

    def test_confluence_labels_absent_from_gates(self):
        src = inspect.getsource(_gates_mod)
        for token in ("Fib_A_Confluence", "Fib_Confluence"):
            assert token not in src, (
                f"{token!r} must not appear in gates.py — no gate may branch on "
                f"the confluence verdict (NON-GATE mandate)"
            )


# ===========================================================================
# §6 NON-GATE: VerdictInvariance
# ===========================================================================

class TestENG006VerdictInvariance:
    """Varying the ENG-006 inputs (structural floor = Point C) must not move
    the verdict — extensions are post-gate informational rows. Asserts identity
    across a representative gate cohort and both extension-bearing profiles."""

    @pytest.mark.parametrize("gate_fn", [_valid_gate, _wait_gate, _invalid_gate])
    @pytest.mark.parametrize("p_code,df_fn,bpd", [
        ("A", _df_profile_a, BARS_PER_DAY_A),
        ("B", _df_profile_b, 1.0),
    ])
    def test_verdict_independent_of_extension_anchor(self, gate_fn, p_code, df_fn, bpd):
        verdicts = set()
        for floor in (FLOOR_C, FLOOR_C + 5000.0):  # tiny vs huge extensions
            ctx = _make_ctx(p_code=p_code, df=df_fn(), structural_floor_raw=floor,
                            bars_per_day=bpd, metrics=_base_metrics())
            result = _run_assemble(ctx, gate_fn())
            verdicts.add(result["action_summary"]["verdict"])
        # Invariance: the post-output verdict must not move with the extension
        # anchor (the only ENG-006 input varied here), whatever its value.
        assert len(verdicts) == 1, (
            f"verdict moved with the extension anchor: {verdicts}"
        )


class TestENG003OBS1VerdictInvariance:
    """Varying the Profile-A entry-zone reference (Daily_Protective_Anchor) must
    not move the verdict — the confluence diagnostic is NON-GATE."""

    @pytest.mark.parametrize("gate_fn", [_valid_gate, _wait_gate, _invalid_gate])
    def test_verdict_independent_of_entry_zone_ref(self, gate_fn):
        verdicts = set()
        for dpa in (FIB_A_382_RAW, FIB_A_500_RAW, 105.0, 0.0):
            ctx = _make_ctx(p_code="A", df=_df_profile_a(), bars_per_day=BARS_PER_DAY_A,
                            metrics=_base_metrics(Daily_Protective_Anchor=dpa))
            ctx.daily_protective_anchor = dpa
            result = _run_assemble(ctx, gate_fn())
            verdicts.add(result["action_summary"]["verdict"])
        # Invariance: re-pointing the confluence input must not move the verdict.
        assert len(verdicts) == 1, (
            f"verdict moved with the entry-zone reference: {verdicts}"
        )


# ===========================================================================
# §6 Functional: ENG-006 extension formula (per profile)
# ===========================================================================

class TestENG006ExtensionFormula:
    """Extension = structural_floor + ratio * (peak - origin), display-scaled."""

    def test_profile_b_extension_values(self):
        ctx = _make_ctx(p_code="B", df=_df_profile_b(),
                        structural_floor_raw=FLOOR_C, bars_per_day=1.0)
        _run_assemble(ctx, _valid_gate())
        m = ctx.metrics
        assert m["Fib_Ext_1272_Level"] == EXP_EXT_1272
        assert m["Fib_Ext_1618_Level"] == EXP_EXT_1618
        assert m["Fib_Ext_2618_Level"] == EXP_EXT_2618

    def test_profile_a_extension_values(self):
        ctx = _make_ctx(p_code="A", df=_df_profile_a(),
                        structural_floor_raw=FLOOR_C, bars_per_day=BARS_PER_DAY_A)
        _run_assemble(ctx, _valid_gate())
        m = ctx.metrics
        assert m["Fib_Ext_1272_Level"] == EXP_EXT_1272
        assert m["Fib_Ext_1618_Level"] == EXP_EXT_1618
        assert m["Fib_Ext_2618_Level"] == EXP_EXT_2618

    def test_extension_display_scaled_lse(self):
        """price_scaler=100 (LSE pence->pounds): values divided by 100."""
        scaler = 100.0
        ctx = _make_ctx(p_code="B", df=_df_profile_b(),
                        structural_floor_raw=FLOOR_C, bars_per_day=1.0,
                        price_scaler=scaler)
        _run_assemble(ctx, _valid_gate())
        m = ctx.metrics
        assert m["Fib_Ext_1272_Level"] == round((FLOOR_C + 1.272 * RALLY_RANGE) / scaler, 2)
        assert m["Fib_Ext_1618_Level"] == round((FLOOR_C + 1.618 * RALLY_RANGE) / scaler, 2)
        assert m["Fib_Ext_2618_Level"] == round((FLOOR_C + 2.618 * RALLY_RANGE) / scaler, 2)


class TestENG006ProfileCExemption:
    """Profile C is exempt — no extension levels computed."""

    def test_profile_c_all_none(self):
        ctx = _make_ctx(p_code="C", df=_df_profile_a(),
                        structural_floor_raw=FLOOR_C, bars_per_day=BARS_PER_DAY_A)
        _run_assemble(ctx, _valid_gate())
        m = ctx.metrics
        assert m["Fib_Ext_1272_Level"] is None
        assert m["Fib_Ext_1618_Level"] is None
        assert m["Fib_Ext_2618_Level"] is None


class TestENG006DegenerateGuards:
    """Window unavailable / rally_range below the per-profile minimum -> None."""

    def test_profile_a_range_below_minimum(self):
        # peak - origin = 0.4 < 0.5 * atr_raw (=1.0) -> all None
        df = _df_profile_a(origin=100.0, peak=100.4)
        ctx = _make_ctx(p_code="A", df=df, structural_floor_raw=FLOOR_C,
                        bars_per_day=BARS_PER_DAY_A)
        _run_assemble(ctx, _valid_gate())
        m = ctx.metrics
        assert m["Fib_Ext_1272_Level"] is None
        assert m["Fib_Ext_1618_Level"] is None
        assert m["Fib_Ext_2618_Level"] is None

    def test_profile_a_window_unavailable(self):
        # df shorter than session_bars + 1 (=20) -> window guard fails -> None
        df = _df_profile_a(n=15)
        ctx = _make_ctx(p_code="A", df=df, structural_floor_raw=FLOOR_C,
                        bars_per_day=BARS_PER_DAY_A)
        _run_assemble(ctx, _valid_gate())
        m = ctx.metrics
        assert m["Fib_Ext_1272_Level"] is None
        assert m["Fib_Ext_1618_Level"] is None
        assert m["Fib_Ext_2618_Level"] is None

    def test_profile_b_degenerate_range(self):
        # origin == peak -> rally_range == 0, fails the > 0 guard -> None
        df = _df_profile_b(origin=110.0, peak=110.0)
        ctx = _make_ctx(p_code="B", df=df, structural_floor_raw=FLOOR_C,
                        bars_per_day=1.0)
        _run_assemble(ctx, _valid_gate())
        m = ctx.metrics
        assert m["Fib_Ext_1272_Level"] is None
        assert m["Fib_Ext_1618_Level"] is None
        assert m["Fib_Ext_2618_Level"] is None

    def test_etf_short_circuits(self):
        ctx = _make_ctx(p_code="B", df=_df_profile_b(), is_etf=True,
                        structural_floor_raw=FLOOR_C, bars_per_day=1.0)
        _run_assemble(ctx, _valid_gate())
        m = ctx.metrics
        assert m["Fib_Ext_1272_Level"] is None
        assert m["Fib_Ext_1618_Level"] is None
        assert m["Fib_Ext_2618_Level"] is None


# ===========================================================================
# §6 Functional: ENG-006 target hierarchy integration (transform.py)
# ===========================================================================

class TestENG006HierarchyIntegration:
    """Extension rows appear in target.hierarchy, sorted ascending into correct
    position relative to MEASURED_MOVE; EXCEEDED rows route to cleared_levels."""

    def test_extension_rows_present_and_labelled(self):
        target = _target({
            "Fib_Ext_1272_Level": EXP_EXT_1272,   # 135.44 > price 130
            "Fib_Ext_1618_Level": EXP_EXT_1618,   # 142.36
            "Fib_Ext_2618_Level": EXP_EXT_2618,   # 162.36
        })
        labels = [e["label"] for e in target["hierarchy"]]
        assert "FIB_EXTENSION_1272" in labels
        assert "FIB_EXTENSION_1618" in labels
        assert "FIB_EXTENSION_2618" in labels

    def test_extension_rows_role_projection(self):
        target = _target({"Fib_Ext_1618_Level": EXP_EXT_1618})
        row = next(e for e in target["hierarchy"] if e["label"] == "FIB_EXTENSION_1618")
        assert row["role"]["label"] == "PROJECTION"
        assert "161.8%" in row["role"]["desc"]
        # NON-GATE: never an escalation winner unless it equals Profit_Target.
        assert row["escalation_winner"] is False

    def test_sorted_ascending_relative_to_measured_move(self):
        # MM_Target=140 sits between FIB_EXTENSION_1272 (135.44) and _1618 (142.36).
        target = _target({
            "MM_Target": 140.0,
            "Fib_Ext_1272_Level": EXP_EXT_1272,
            "Fib_Ext_1618_Level": EXP_EXT_1618,
            "Fib_Ext_2618_Level": EXP_EXT_2618,
        })
        labels = [e["label"] for e in target["hierarchy"]]
        prices = [e["price"] for e in target["hierarchy"]]
        assert prices == sorted(prices), "hierarchy must be ascending by price"
        i1272 = labels.index("FIB_EXTENSION_1272")
        imm = labels.index("MEASURED_MOVE")
        i1618 = labels.index("FIB_EXTENSION_1618")
        assert i1272 < imm < i1618

    def test_exceeded_routes_to_cleared_levels(self):
        # Extension below current price (130) -> EXCEEDED -> cleared_levels.
        target = _target({"Fib_Ext_1272_Level": 125.0})
        cleared = target.get("cleared_levels") or []
        cleared_labels = {e["label"] for e in cleared}
        hierarchy_labels = {e["label"] for e in (target["hierarchy"] or [])}
        assert "FIB_EXTENSION_1272" in cleared_labels
        assert "FIB_EXTENSION_1272" not in hierarchy_labels
        row = next(e for e in cleared if e["label"] == "FIB_EXTENSION_1272")
        assert row["status"] == "EXCEEDED"

    def test_absent_extensions_no_rows(self):
        target = _target()  # all three None
        labels = {e["label"] for e in (target["hierarchy"] or [])}
        assert not any(l.startswith("FIB_EXTENSION") for l in labels)


# ===========================================================================
# §6 Functional: MAPPED_FLAT_KEYS membership + round-trip coverage
# ===========================================================================

class TestENG006KeyCoverage:

    def test_keys_in_mapped_flat_keys(self):
        for k in ("Fib_Ext_1272_Level", "Fib_Ext_1618_Level", "Fib_Ext_2618_Level"):
            assert k in MAPPED_FLAT_KEYS, f"{k} must be registered in MAPPED_FLAT_KEYS"

    def test_round_trip_reconstructs_scalars(self):
        fm = _t_flat_metrics(
            Fib_Ext_1272_Level=EXP_EXT_1272,
            Fib_Ext_1618_Level=EXP_EXT_1618,
            Fib_Ext_2618_Level=EXP_EXT_2618,
        )
        grouped = _transform_output(_t_action_summary(), fm)
        _, _, flat = _flatten(grouped)
        assert flat["Fib_Ext_1272_Level"] == EXP_EXT_1272
        assert flat["Fib_Ext_1618_Level"] == EXP_EXT_1618
        assert flat["Fib_Ext_2618_Level"] == EXP_EXT_2618
        for k in ("Fib_Ext_1272_Level", "Fib_Ext_1618_Level", "Fib_Ext_2618_Level"):
            assert not isinstance(flat[k], (dict, list))

    def test_round_trip_none_safe(self):
        grouped = _transform_output(_t_action_summary(), _t_flat_metrics())
        _, _, flat = _flatten(grouped)
        # Absent extensions reconstruct as None (scalar), never a dict.
        for k in ("Fib_Ext_1272_Level", "Fib_Ext_1618_Level", "Fib_Ext_2618_Level"):
            assert flat.get(k) is None


# ===========================================================================
# §6 Functional: ENG-003-OBS-1 confluence re-point (Profile A)
# ===========================================================================

class TestENG003OBS1RePoint:
    """Confluence ladder compares the Daily EMA 21 entry zone, not last['close'].

    Each fixture sets last['close'] to a value that would yield a DIFFERENT label
    under the pre-edit (price-based) logic, so the assertion differential-verifies.
    """

    def _run(self, dpa, close):
        df = _df_profile_a(close=close)
        ctx = _make_ctx(p_code="A", df=df, bars_per_day=BARS_PER_DAY_A,
                        metrics=_base_metrics(Daily_Protective_Anchor=dpa))
        ctx.daily_protective_anchor = dpa
        _run_assemble(ctx, _valid_gate())
        return ctx.metrics

    def test_entry_zone_below_grid_yields_below_fibs(self):
        # IE-style: price at the 38.2% level (pre-edit -> CONFLUENCE_382) but the
        # entry zone sits below the grid -> BELOW_FIBS (the honest answer).
        m = self._run(dpa=105.0, close=FIB_A_382_RAW)
        assert m["Fib_A_Confluence"] == "BELOW_FIBS"

    def test_entry_zone_at_382_yields_confluence_382(self):
        # Entry zone exactly at 38.2%; price set away from any level.
        m = self._run(dpa=FIB_A_382_RAW, close=ORIGIN)
        assert m["Fib_A_Confluence"] == "CONFLUENCE_382"

    def test_entry_zone_at_500_yields_confluence_500(self):
        m = self._run(dpa=FIB_A_500_RAW, close=ORIGIN)
        assert m["Fib_A_Confluence"] == "CONFLUENCE_500"

    def test_levels_still_emitted(self):
        m = self._run(dpa=105.0, close=FIB_A_382_RAW)
        assert m["Fib_A_382_Level"] is not None
        assert m["Fib_A_500_Level"] is not None


class TestENG003OBS1NullGuard:
    """Daily EMA 21 reference absent (0.0 / None) -> Fib_A_Confluence = None,
    but the Fib level fields remain valid geometry and are still emitted."""

    def _run(self, dpa):
        df = _df_profile_a(close=FIB_A_382_RAW)  # price at 382 (pre-edit -> CONFLUENCE_382)
        metrics = _base_metrics()
        if dpa is None:
            metrics["Daily_Protective_Anchor"] = None
        else:
            metrics["Daily_Protective_Anchor"] = dpa
        ctx = _make_ctx(p_code="A", df=df, bars_per_day=BARS_PER_DAY_A, metrics=metrics)
        if dpa is not None:
            ctx.daily_protective_anchor = dpa
        _run_assemble(ctx, _valid_gate())
        return ctx.metrics

    def test_zero_reference_suppresses_confluence(self):
        m = self._run(dpa=0.0)
        assert m["Fib_A_Confluence"] is None
        assert m["Fib_A_382_Level"] is not None
        assert m["Fib_A_500_Level"] is not None

    def test_none_reference_suppresses_confluence(self):
        m = self._run(dpa=None)
        assert m["Fib_A_Confluence"] is None
        assert m["Fib_A_382_Level"] is not None
        assert m["Fib_A_500_Level"] is not None


# ===========================================================================
# Addendum 1 §A4 — Pre-closure fixes (ENG-006-OBS-1 + EZR-001)
#
# ENG-006-OBS-1 — _CONVICTION_TIER_MAP now maps the three FIB_EXTENSION_* labels
#                 to ("PROJECTION", 4) so the rows emit non-null conviction.
# EZR-001       — transform-display re-source of the Profile A PULLBACK entry
#                 reference (-> Daily EMA 21) and range lower (-> Pullback_Zone_Lower).
#
# All tests drive the REAL _transform_output through crafted flat_metrics, so the
# functional assertions differential-verify (FAIL pre-edit, PASS post-edit).
# ===========================================================================

# EZR-001 display geometry (consistent display-scaled units).
HOURLY_FLOOR = 124.0    # Entry_Reference / structural floor (residual hourly EMA 21)
DAILY_EMA21 = 128.0     # Daily_Protective_Anchor (the AVWAP-001 entry-zone center)
PB_LOWER = 126.0        # Pullback_Zone_Lower (Daily EMA 21 - 0.5 ATR)
PB_UPPER = 130.0        # Pullback_Zone_Upper (Daily EMA 21 + 0.5 ATR)

DB_PROFILE_A = "SWING (hourly)"     # _db -> "SWING" => Profile A
DB_PROFILE_B = "TREND (daily)"      # not SWING / not WEALTH => Profile B path
DB_PROFILE_C = "WEALTH (weekly)"    # _db -> "WEALTH" => Profile C path


def _entry_zone(profile_db, **overrides):
    """Build the entry_zone sub-object from the real transform layer.

    Profile A (SWING) PULLBACK defaults that do NOT trip the inversion guard
    (HOURLY_FLOOR < PB_UPPER). Override per test.
    """
    base = {
        "Data_Basis": profile_db,
        "Window_Reset_Event": "PULLBACK",
        "Entry_Reference": HOURLY_FLOOR,
        "Pullback_Zone_Upper": PB_UPPER,
        "Pullback_Zone_Lower": PB_LOWER,
        "Daily_Protective_Anchor": DAILY_EMA21,
        "Entry_Zone_Reference": "Daily EMA 21",
        "BRK_Model_Active": False,
    }
    base.update(overrides)
    grouped = _transform_output(_t_action_summary(), _t_flat_metrics(**base))
    return grouped["trade_setup"]["entry_zone"]


# --- §A4.1 ENG-006-OBS-1: conviction non-null --------------------------------

class TestPreClosureENG006OBS1Conviction:
    """FIB_EXTENSION_* rows carry conviction_tier == PROJECTION / rank == 4."""

    def test_map_has_extension_labels(self):
        for label in ("FIB_EXTENSION_1272", "FIB_EXTENSION_1618", "FIB_EXTENSION_2618"):
            assert _CONVICTION_TIER_MAP.get(label) == ("PROJECTION", 4), (
                f"{label} must map to ('PROJECTION', 4)"
            )

    def test_hierarchy_rows_carry_conviction(self):
        # All three extensions above current price (130) -> remain in hierarchy.
        target = _target({
            "Fib_Ext_1272_Level": EXP_EXT_1272,
            "Fib_Ext_1618_Level": EXP_EXT_1618,
            "Fib_Ext_2618_Level": EXP_EXT_2618,
        })
        ext_rows = [e for e in target["hierarchy"] if e["label"].startswith("FIB_EXTENSION")]
        assert len(ext_rows) == 3
        for row in ext_rows:
            assert row["conviction_tier"] == "PROJECTION"
            assert row["conviction_rank"] == 4

    def test_cleared_extension_also_carries_conviction(self):
        # Below price (130) -> EXCEEDED -> cleared_levels; annotation must persist.
        target = _target({"Fib_Ext_1272_Level": 125.0})
        cleared = target.get("cleared_levels") or []
        row = next(e for e in cleared if e["label"] == "FIB_EXTENSION_1272")
        assert row["conviction_tier"] == "PROJECTION"
        assert row["conviction_rank"] == 4


# --- §A4.2 EZR-001: Profile A native PULLBACK alignment ----------------------

class TestPreClosureEZR001Alignment:
    """Profile A native PULLBACK: reference.price -> Daily EMA 21;
    entry_price_range.lower -> Pullback_Zone_Lower (upper unchanged)."""

    def test_reference_and_range_aligned(self):
        ez = _entry_zone(DB_PROFILE_A)
        assert ez["reference"]["price"] == DAILY_EMA21
        assert ez["entry_price_range"]["lower"] == PB_LOWER
        assert ez["entry_price_range"]["upper"] == PB_UPPER

    def test_reference_diverges_from_residual_floor(self):
        # Differential: pre-edit reference.price would be HOURLY_FLOOR.
        ez = _entry_zone(DB_PROFILE_A)
        assert ez["reference"]["price"] != HOURLY_FLOOR
        assert ez["entry_price_range"]["lower"] != HOURLY_FLOOR


# --- §A4.3 EZR-001: fallback-pullback ---------------------------------------

class TestPreClosureEZR001FallbackPullback:
    """Profile A fallback-pullback (_render_as_pullback_fallback): reference.price
    re-sources to Daily EMA 21; entry_price_range is NOT rendered (native only)."""

    def test_fallback_reference_resourced_no_range(self):
        ez = _entry_zone(
            DB_PROFILE_A,
            Window_Reset_Event="BREAKOUT",       # historical trigger
            Breakout_Thesis_Status="FAILED",     # -> _render_as_pullback_fallback
            BRK_Model_Active=False,
        )
        assert ez["reference"]["price"] == DAILY_EMA21
        assert ez["entry_price_range"] is None


# --- §A4.4 EZR-001: null guard ----------------------------------------------

class TestPreClosureEZR001NullGuard:
    """Daily_Protective_Anchor <= 0 / None -> reference.price falls back to the
    structural floor (no null/zero reference emitted)."""

    @pytest.mark.parametrize("bad_anchor", [0.0, None])
    def test_anchor_unavailable_falls_back_to_floor(self, bad_anchor):
        ez = _entry_zone(DB_PROFILE_A, Daily_Protective_Anchor=bad_anchor)
        assert ez["reference"] is not None
        assert ez["reference"]["price"] == HOURLY_FLOOR


# --- §A4.5 EZR-001: regression guards (must be unchanged) --------------------

class TestPreClosureEZR001Regression:
    """RECLAIM / Profile B / Profile C / inversion paths are byte-identical."""

    def test_profile_a_reclaim_unchanged(self):
        # RECLAIM is neither pullback nor fallback -> reference stays _entry_ref.
        ez = _entry_zone(DB_PROFILE_A, Window_Reset_Event="RECLAIM")
        assert ez["reference"]["price"] == HOURLY_FLOOR          # not DAILY_EMA21
        assert ez["reference"]["desc"] == "Structural floor (reclaim target)"

    def test_profile_b_pullback_not_resourced(self):
        ez = _entry_zone(DB_PROFILE_B)
        assert ez["reference"]["price"] == HOURLY_FLOOR          # not DAILY_EMA21
        assert ez["entry_price_range"]["lower"] == HOURLY_FLOOR  # not PB_LOWER

    def test_profile_c_pullback_not_resourced(self):
        ez = _entry_zone(DB_PROFILE_C)
        assert ez["reference"]["price"] == HOURLY_FLOOR          # not DAILY_EMA21

    def test_inversion_guard_preserved(self):
        # Structural floor above the zone upper -> inversion. The guard reads
        # _entry_ref (NOT the re-sourced display value), so it must still fire:
        # entry_price_range suppressed + [INVERTED] desc suffix.
        ez = _entry_zone(DB_PROFILE_A, Entry_Reference=PB_UPPER + 5.0)
        assert ez["entry_price_range"] is None
        assert "[INVERTED: EMA structure broken]" in ez["desc"]


# --- §A4.6 NON-GATE / verdict invariance (bundle pre-closure) ---------------

class TestPreClosureNotInGatesFile:
    """Neither pre-closure fix introduces a key read by any gate function.

    ENG-006-OBS-1 adds only conviction-map labels (FIB_EXTENSION_*); EZR-001 is
    display-only and re-uses existing flat keys (Daily EMA 21 / pullback zone),
    none of which any gate verdict branches on (Addendum §A5)."""

    def test_extension_labels_absent_from_gates(self):
        src = inspect.getsource(_gates_mod)
        for token in ("FIB_EXTENSION_1272", "FIB_EXTENSION_1618",
                      "FIB_EXTENSION_2618", "FIB_EXTENSION"):
            assert token not in src, f"{token!r} must not appear in gates.py"


class TestPreClosureVerdictInvariance:
    """The two transform edits do not move the passthrough verdict."""

    def test_extension_rows_verdict_unchanged(self):
        grouped = _transform_output(_t_action_summary(), _t_flat_metrics(
            Fib_Ext_1272_Level=EXP_EXT_1272,
            Fib_Ext_1618_Level=EXP_EXT_1618,
            Fib_Ext_2618_Level=EXP_EXT_2618,
        ))
        assert grouped["action_summary"]["verdict"] == "VALID"

    @pytest.mark.parametrize("profile_db", [DB_PROFILE_A, DB_PROFILE_B, DB_PROFILE_C])
    def test_entry_zone_resource_verdict_unchanged(self, profile_db):
        grouped = _transform_output(_t_action_summary(), _t_flat_metrics(
            Data_Basis=profile_db,
            Window_Reset_Event="PULLBACK",
            Entry_Reference=HOURLY_FLOOR,
            Pullback_Zone_Upper=PB_UPPER,
            Pullback_Zone_Lower=PB_LOWER,
            Daily_Protective_Anchor=DAILY_EMA21,
        ))
        assert grouped["action_summary"]["verdict"] == "VALID"


# ===========================================================================
# Addendum 1 v1.2 §A4 case 7 — EZR-001-OBS-1 (Profile A PULLBACK desc/price
# consistency). The desc-side counterpart to §A3.2: when reference.price is the
# re-sourced Daily EMA 21 anchor, reference.desc must read "Daily EMA 21" rather
# than the residual hourly Anchor_Label — including on Entry_Zone_Reference-absent
# verdict-gate early-return paths (the CMG witness). Gated on the SAME boolean as
# the §A3.2 price re-source, so price + desc move together by construction.
# ===========================================================================

class TestPreClosureEZR001OBS1DescAlignment:
    """reference.desc tracks the §A3.2 price re-source (Addendum 1 v1.2 §A3.3)."""

    def test_early_return_desc_matches_daily_anchor_price(self):
        # CMG case: Daily_Protective_Anchor > 0 but Entry_Zone_Reference unset
        # (verdict-gate early-return before trigger.py's Profile A block ran).
        # Pre-edit: desc falls back to the hourly Anchor_Label; post-edit: "Daily EMA 21".
        ez = _entry_zone(
            DB_PROFILE_A,
            Entry_Zone_Reference=None,
            Anchor_Label="EMA 21 (Structural Floor)",
        )
        assert ez["reference"]["price"] == DAILY_EMA21
        assert ez["reference"]["desc"] == "Daily EMA 21"

    def test_set_path_uses_runtime_value_no_regression(self):
        # INSW case: Entry_Zone_Reference present -> desc uses the runtime value
        # (unchanged from pre-fix); price + desc stay consistent.
        ez = _entry_zone(DB_PROFILE_A, Entry_Zone_Reference="Daily EMA 21")
        assert ez["reference"]["desc"] == "Daily EMA 21"
        assert ez["reference"]["price"] == DAILY_EMA21

    def test_within_profile_a_anchor_nonpositive_stays_hourly(self):
        # Daily_Protective_Anchor <= 0: neither the price re-source nor the desc
        # override fires -> both stay hourly-consistent (§A3.3 fallback row).
        ez = _entry_zone(
            DB_PROFILE_A,
            Daily_Protective_Anchor=0.0,
            Entry_Zone_Reference=None,
            Anchor_Label="EMA 21 (Structural Floor)",
        )
        assert ez["reference"]["price"] == HOURLY_FLOOR
        assert ez["reference"]["desc"] == "EMA 21 (Structural Floor)"

    def test_reclaim_desc_unchanged(self):
        # RECLAIM: override never fires -> desc keeps the reclaim-target string.
        ez = _entry_zone(DB_PROFILE_A, Window_Reset_Event="RECLAIM")
        assert ez["reference"]["desc"] == "Structural floor (reclaim target)"

    def test_profile_b_c_desc_unchanged(self):
        # Non-Profile-A: override never fires -> desc + price keep hourly values.
        for db in (DB_PROFILE_B, DB_PROFILE_C):
            ez = _entry_zone(db, Entry_Zone_Reference=None,
                             Anchor_Label="EMA 21 (Structural Floor)")
            assert ez["reference"]["desc"] == "EMA 21 (Structural Floor)"
            assert ez["reference"]["price"] == HOURLY_FLOOR
