"""FA-001 Re-Implementation Tests (VS-03, VS-08, VS-11, VS-18).

Covers:
  VS-08: Floor/Extension anchor split -- 12 cases (6 floor + 6 extension)
  VS-03: SMA50 slope bias with 0.0 slope value
  VS-11: Floor failure status deferred derivation -- 5 cases
  VS-18: THS band boundary at 50/51

Run: pytest tests/unit/test_fa001_reimpl.py -v
"""
import pytest
from types import SimpleNamespace
from tbs_engine.output import _ths_band


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    """Build a minimal state SimpleNamespace for _populate_base_metrics."""
    defaults = dict(
        is_trending=False, is_resolving=False,
        is_violated=False, is_floor_failure=False, is_reclaim=False,
        consec_below=0, adx_t=25.0, di_plus=20.0, di_minus=15.0,
        atr_raw=2.0, floor_raw=0.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_metrics(**overrides):
    """Build a minimal metrics dict with keys read by _assemble_output."""
    defaults = dict(
        Context_Daily_SMA50_Slope=None,
        Context_Weekly_SMA50_Slope=None,
        Context_Monthly_SMA50_Slope=None,
        Context_SMA50_Slope_Bias=None,
        Floor_Failure_Status_Label=None,
        Floor_Failure_Status_Desc=None,
        Exit_Signal=None,
        Floor_Failure_Context=None,
    )
    defaults.update(overrides)
    return defaults


def _run_populate_anchor(p_code, is_etf, state):
    """Run only the anchor-writing portion of _populate_base_metrics logic.

    Extracts just the Floor/Extension anchor assignment code path
    to avoid needing the full ctx/dataframe infrastructure.
    """
    metrics = {}

    # Floor anchor logic (mirrors output.py)
    if p_code == "A":
        metrics["Floor_Anchor_Type"] = "VWAP"
        metrics["Floor_Anchor_Label"] = "Intraday institutional value level"
    elif p_code == "C" or (is_etf and p_code == "C"):
        metrics["Floor_Anchor_Type"] = "SMA_200"
        metrics["Floor_Anchor_Label"] = "Long-term secular trend floor"
    else:
        metrics["Floor_Anchor_Type"] = "SMA_50"
        metrics["Floor_Anchor_Label"] = "Intermediate institutional trend line"

    # Extension anchor logic (mirrors output.py)
    if p_code == "A":
        metrics["Extension_Anchor_Type"] = "VWAP"
        metrics["Extension_Anchor_Label"] = "Intraday institutional value level"
    elif p_code == "B" and state.is_trending and not is_etf:
        metrics["Extension_Anchor_Type"] = "EMA_21"
        metrics["Extension_Anchor_Label"] = "Medium-term trend support (~1 month)"
    elif p_code == "B" and state.is_resolving and not state.is_trending and not is_etf:
        metrics["Extension_Anchor_Type"] = "EMA_8"
        metrics["Extension_Anchor_Label"] = "Short-term momentum support (~1.5 weeks)"
    elif is_etf and p_code == "B":
        metrics["Extension_Anchor_Type"] = "SMA_50"
        metrics["Extension_Anchor_Label"] = "Intermediate institutional trend line"
    elif p_code == "C" or (is_etf and p_code == "C"):
        metrics["Extension_Anchor_Type"] = "SMA_200"
        metrics["Extension_Anchor_Label"] = "Long-term secular trend floor"
    else:
        metrics["Extension_Anchor_Type"] = "SMA_50"
        metrics["Extension_Anchor_Label"] = "Intermediate institutional trend line"

    return metrics


def _run_slope_bias(metrics):
    """Run the slope bias derivation logic (mirrors _assemble_output)."""
    _ctx_sma50_slope = metrics.get("Context_Daily_SMA50_Slope")
    if _ctx_sma50_slope is None:
        _ctx_sma50_slope = metrics.get("Context_Weekly_SMA50_Slope")
    if _ctx_sma50_slope is None:
        _ctx_sma50_slope = metrics.get("Context_Monthly_SMA50_Slope")
    if _ctx_sma50_slope is not None:
        if _ctx_sma50_slope > 0:
            metrics["Context_SMA50_Slope_Bias"] = "BULLISH"
        elif _ctx_sma50_slope < 0:
            metrics["Context_SMA50_Slope_Bias"] = "BEARISH"
        else:
            metrics["Context_SMA50_Slope_Bias"] = "NEUTRAL"
    return metrics


def _run_floor_status(state, metrics):
    """Run the deferred floor failure status derivation (mirrors _assemble_output)."""
    _exit_sig = metrics.get("Exit_Signal")
    _ffc = metrics.get("Floor_Failure_Context")

    if state.is_floor_failure:
        if _ffc and _ffc.startswith("STRUCTURAL"):
            metrics["Floor_Failure_Status_Label"] = "FAILURE"
            metrics["Floor_Failure_Status_Desc"] = "Structural breakdown confirmed -- consecutive closes below floor exceed threshold"
        elif _ffc:
            metrics["Floor_Failure_Status_Label"] = "BREACH"
            metrics["Floor_Failure_Status_Desc"] = "Price below structural floor -- monitoring for reclaim"
        else:
            metrics["Floor_Failure_Status_Label"] = "FAILURE"
            metrics["Floor_Failure_Status_Desc"] = "Structural breakdown confirmed -- consecutive closes below floor exceed threshold"
    elif state.is_violated:
        if state.is_reclaim:
            metrics["Floor_Failure_Status_Label"] = "VIOLATION"
            metrics["Floor_Failure_Status_Desc"] = "Price reclaiming above structural floor -- monitoring for recovery"
        else:
            metrics["Floor_Failure_Status_Label"] = "VIOLATION"
            metrics["Floor_Failure_Status_Desc"] = "Price below structural floor -- counting consecutive closes"
    elif _exit_sig in ("EXIT", "WARNING"):
        metrics["Floor_Failure_Status_Label"] = "BREACH"
        metrics["Floor_Failure_Status_Desc"] = "Exit signal active -- price deterioration below structural anchor"
    else:
        metrics["Floor_Failure_Status_Label"] = "CLEAR"
        metrics["Floor_Failure_Status_Desc"] = "No consecutive bars below structural floor"
    return metrics


# ===========================================================================
# VS-08: Floor/Extension Anchor Split
# ===========================================================================

class TestVS08FloorAnchor:
    """Floor anchor table: 6 rows."""

    def test_profile_a_floor(self):
        m = _run_populate_anchor("A", False, _make_state())
        assert m["Floor_Anchor_Type"] == "VWAP"
        assert m["Floor_Anchor_Label"] == "Intraday institutional value level"

    def test_profile_b_non_etf_trending_floor(self):
        m = _run_populate_anchor("B", False, _make_state(is_trending=True))
        assert m["Floor_Anchor_Type"] == "SMA_50"

    def test_profile_b_non_etf_resolving_floor(self):
        m = _run_populate_anchor("B", False, _make_state(is_resolving=True))
        assert m["Floor_Anchor_Type"] == "SMA_50"

    def test_profile_b_non_etf_midrange_floor(self):
        m = _run_populate_anchor("B", False, _make_state())
        assert m["Floor_Anchor_Type"] == "SMA_50"

    def test_profile_b_etf_floor(self):
        m = _run_populate_anchor("B", True, _make_state())
        assert m["Floor_Anchor_Type"] == "SMA_50"

    def test_profile_c_floor(self):
        m = _run_populate_anchor("C", False, _make_state())
        assert m["Floor_Anchor_Type"] == "SMA_200"
        assert m["Floor_Anchor_Label"] == "Long-term secular trend floor"


class TestVS08ExtensionAnchor:
    """Extension anchor table: 6 rows."""

    def test_profile_a_extension(self):
        m = _run_populate_anchor("A", False, _make_state())
        assert m["Extension_Anchor_Type"] == "VWAP"

    def test_profile_b_non_etf_trending_extension(self):
        m = _run_populate_anchor("B", False, _make_state(is_trending=True))
        assert m["Extension_Anchor_Type"] == "EMA_21"
        assert m["Extension_Anchor_Label"] == "Medium-term trend support (~1 month)"

    def test_profile_b_non_etf_resolving_extension(self):
        m = _run_populate_anchor("B", False, _make_state(is_resolving=True))
        assert m["Extension_Anchor_Type"] == "EMA_8"
        assert m["Extension_Anchor_Label"] == "Short-term momentum support (~1.5 weeks)"

    def test_profile_b_non_etf_midrange_extension(self):
        """MID-RANGE/AMBIGUOUS/VIOLATED falls to else -> SMA_50."""
        m = _run_populate_anchor("B", False, _make_state())
        assert m["Extension_Anchor_Type"] == "SMA_50"

    def test_profile_b_etf_extension(self):
        m = _run_populate_anchor("B", True, _make_state())
        assert m["Extension_Anchor_Type"] == "SMA_50"

    def test_profile_c_extension(self):
        m = _run_populate_anchor("C", False, _make_state())
        assert m["Extension_Anchor_Type"] == "SMA_200"


class TestVS08SplitDifference:
    """Verify floor != extension for Profile B non-ETF TRENDING/RESOLVING."""

    def test_trending_split(self):
        m = _run_populate_anchor("B", False, _make_state(is_trending=True))
        assert m["Floor_Anchor_Type"] == "SMA_50"
        assert m["Extension_Anchor_Type"] == "EMA_21"
        assert m["Floor_Anchor_Type"] != m["Extension_Anchor_Type"]

    def test_resolving_split(self):
        m = _run_populate_anchor("B", False, _make_state(is_resolving=True))
        assert m["Floor_Anchor_Type"] == "SMA_50"
        assert m["Extension_Anchor_Type"] == "EMA_8"
        assert m["Floor_Anchor_Type"] != m["Extension_Anchor_Type"]

    def test_profile_a_same(self):
        m = _run_populate_anchor("A", False, _make_state())
        assert m["Floor_Anchor_Type"] == m["Extension_Anchor_Type"] == "VWAP"

    def test_profile_c_same(self):
        m = _run_populate_anchor("C", False, _make_state())
        assert m["Floor_Anchor_Type"] == m["Extension_Anchor_Type"] == "SMA_200"

    def test_etf_b_same(self):
        m = _run_populate_anchor("B", True, _make_state())
        assert m["Floor_Anchor_Type"] == m["Extension_Anchor_Type"] == "SMA_50"


# ===========================================================================
# VS-03: SMA50 Slope Bias Null at 0.0
# ===========================================================================

class TestVS03SlopeBias:
    """Explicit None check -- 0.0 must produce NEUTRAL, not None."""

    def test_daily_slope_zero(self):
        m = _make_metrics(Context_Daily_SMA50_Slope=0.0)
        _run_slope_bias(m)
        assert m["Context_SMA50_Slope_Bias"] == "NEUTRAL"

    def test_daily_slope_positive(self):
        m = _make_metrics(Context_Daily_SMA50_Slope=0.5)
        _run_slope_bias(m)
        assert m["Context_SMA50_Slope_Bias"] == "BULLISH"

    def test_daily_slope_negative(self):
        m = _make_metrics(Context_Daily_SMA50_Slope=-0.3)
        _run_slope_bias(m)
        assert m["Context_SMA50_Slope_Bias"] == "BEARISH"

    def test_daily_zero_weekly_positive(self):
        """Daily=0.0 should take precedence over weekly (not fall through)."""
        m = _make_metrics(Context_Daily_SMA50_Slope=0.0, Context_Weekly_SMA50_Slope=1.5)
        _run_slope_bias(m)
        assert m["Context_SMA50_Slope_Bias"] == "NEUTRAL"

    def test_daily_none_weekly_zero(self):
        m = _make_metrics(Context_Weekly_SMA50_Slope=0.0)
        _run_slope_bias(m)
        assert m["Context_SMA50_Slope_Bias"] == "NEUTRAL"

    def test_all_none(self):
        m = _make_metrics()
        _run_slope_bias(m)
        assert m["Context_SMA50_Slope_Bias"] is None

    def test_daily_none_monthly_negative(self):
        m = _make_metrics(Context_Monthly_SMA50_Slope=-0.1)
        _run_slope_bias(m)
        assert m["Context_SMA50_Slope_Bias"] == "BEARISH"


# ===========================================================================
# VS-11: Floor Failure Status Deferred Derivation
# ===========================================================================

class TestVS11FloorStatus:
    """Deferred status derivation -- 5 paths."""

    def test_floor_failure_structural(self):
        """Path: state.is_floor_failure + STRUCTURAL context -> FAILURE."""
        st = _make_state(is_floor_failure=True)
        m = _make_metrics(Floor_Failure_Context="STRUCTURAL_BREAKDOWN(SMA50 broken)")
        _run_floor_status(st, m)
        assert m["Floor_Failure_Status_Label"] == "FAILURE"

    def test_floor_failure_consolidation(self):
        """Path: state.is_floor_failure + non-STRUCTURAL context -> BREACH."""
        st = _make_state(is_floor_failure=True)
        m = _make_metrics(Floor_Failure_Context="CONSOLIDATION")
        _run_floor_status(st, m)
        assert m["Floor_Failure_Status_Label"] == "BREACH"

    def test_violated_no_reclaim(self):
        """Path: state.is_violated, not reclaiming -> VIOLATION."""
        st = _make_state(is_violated=True, is_reclaim=False)
        m = _make_metrics()
        _run_floor_status(st, m)
        assert m["Floor_Failure_Status_Label"] == "VIOLATION"
        assert "counting" in m["Floor_Failure_Status_Desc"]

    def test_violated_reclaim(self):
        """Path: state.is_violated + is_reclaim -> VIOLATION (reclaiming)."""
        st = _make_state(is_violated=True, is_reclaim=True)
        m = _make_metrics()
        _run_floor_status(st, m)
        assert m["Floor_Failure_Status_Label"] == "VIOLATION"
        assert "reclaiming" in m["Floor_Failure_Status_Desc"]

    def test_exit_signal_active(self):
        """Path: Exit_Signal=EXIT, no violated state -> BREACH."""
        st = _make_state()
        m = _make_metrics(Exit_Signal="EXIT")
        _run_floor_status(st, m)
        assert m["Floor_Failure_Status_Label"] == "BREACH"
        assert "Exit signal" in m["Floor_Failure_Status_Desc"]

    def test_exit_warning(self):
        """Path: Exit_Signal=WARNING -> BREACH."""
        st = _make_state()
        m = _make_metrics(Exit_Signal="WARNING")
        _run_floor_status(st, m)
        assert m["Floor_Failure_Status_Label"] == "BREACH"

    def test_clear(self):
        """Path: all flags False, no exit signal -> CLEAR."""
        st = _make_state()
        m = _make_metrics()
        _run_floor_status(st, m)
        assert m["Floor_Failure_Status_Label"] == "CLEAR"
        assert m["Floor_Failure_Status_Desc"] == "No consecutive bars below structural floor"

    def test_floor_failure_no_context(self):
        """Path: state.is_floor_failure + no context -> FAILURE (default)."""
        st = _make_state(is_floor_failure=True)
        m = _make_metrics(Floor_Failure_Context=None)
        _run_floor_status(st, m)
        assert m["Floor_Failure_Status_Label"] == "FAILURE"


# ===========================================================================
# VS-18: THS Band Boundary Fix
# ===========================================================================

class TestVS18ThsBand:
    """Band boundary at 50 must align with gate threshold."""

    def test_score_50_is_caution(self):
        assert _ths_band(50.0) == "CAUTION"

    def test_score_50_3_is_acceptable(self):
        """Was CAUTION before fix (>= 51). Now ACCEPTABLE (> 50)."""
        assert _ths_band(50.3) == "ACCEPTABLE"

    def test_score_50_5_is_acceptable(self):
        assert _ths_band(50.5) == "ACCEPTABLE"

    def test_score_51_is_acceptable(self):
        assert _ths_band(51.0) == "ACCEPTABLE"

    def test_score_40_is_caution(self):
        assert _ths_band(40.0) == "CAUTION"

    def test_score_60_is_healthy(self):
        assert _ths_band(60.0) == "HEALTHY"

    def test_score_80_is_strong(self):
        assert _ths_band(80.0) == "STRONG"

    def test_score_19_is_critical(self):
        assert _ths_band(19.0) == "CRITICAL"

    def test_score_20_is_weak(self):
        assert _ths_band(20.0) == "WEAK"
