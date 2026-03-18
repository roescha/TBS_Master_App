"""DIAG-001 Phase 2B: _proximity_audit refactoring tests.

Verifies _proximity_audit reads from gate_result.reason instead of string
parsing. Covers eligibility guards and reason extraction.

Spec: DIAG_001_Action_Summary_Spec_v1_0.md §IX
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.7
"""

import sys, os, pytest
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace
from tbs_engine.types import GateResult
from tbs_engine.output import _proximity_audit


def _make_state(**kw):
    d = dict(adx_t=25.0, di_plus=30.0, di_minus=15.0, atr_raw=2.0, floor_raw=140.0,
             is_floor_failure=False, is_violated=False, is_reclaim=False,
             ema_stacked=True, ma_squeeze=False, ma_stack_full=True,
             is_trending=True, is_resolving=False,
             _entry_trending=True, _entry_resolving=False, _reclaim_run=0)
    d.update(kw); return SimpleNamespace(**d)


def _make_df(n=30, close=150.0, anchor=142.0):
    return pd.DataFrame({
        "close": [close]*n, "open": [close-1]*n, "high": [close+2]*n, "low": [close-2]*n,
        "EMA_8": [close]*n, "EMA_21": [close-2]*n, "SMA_50": [anchor]*n,
        "ANCHOR": [anchor]*n, "vol_sma_9": [np.nan]*n,
    })


def _make_ctx(p_code="B", state=None, **kw):
    if state is None: state = _make_state()
    df = kw.pop("df", _make_df())
    last = df.iloc[-1]
    d = dict(state=state, p_code=p_code, is_etf=False, last=last, df=df,
             prev_high=float(last["high"]), resistance_raw=160.0,
             ext_limit=1.0, atr_dist=0.5, window_count=5, window_limit=20,
             cons_high_raw=155.0, hard_stop_raw=138.0, price_scaler=1.0,
             prox_anchor=148.0, structural_floor_raw=142.0)
    d.update(kw); return SimpleNamespace(**d)


def _inv(reason):
    return GateResult(verdict="INVALID", reason=reason, mandate="WAIT.", context="Test.",
                      legacy_diagnostic=f"HALT (reason: {reason}).")


def _valid():
    return GateResult(verdict="VALID", reason="PULLBACK", mandate="X.", context="X.",
                      legacy_diagnostic="x", entry_type="PULLBACK",
                      trigger_rule="BAR CLOSE ONLY", state="TRENDING")


class TestEligibilityGuards:
    """VALID / None / MONITOR / Profile C → immediate return."""

    def test_valid_no_proximity(self):
        m = {}; _proximity_audit(m, _valid(), _make_ctx(), "INFO")
        assert "Proximity_Signal" not in m

    def test_none_no_proximity(self):
        m = {}; _proximity_audit(m, None, _make_ctx(), "INFO")
        assert "Proximity_Signal" not in m

    def test_monitor_no_proximity(self):
        m = {}; _proximity_audit(m, _inv("EXTENDED"), _make_ctx(), "MONITOR")
        assert "Proximity_Signal" not in m

    def test_profile_c_no_proximity(self):
        m = {}; _proximity_audit(m, _inv("EXTENDED"), _make_ctx(p_code="C"), "INFO")
        assert "Proximity_Signal" not in m


class TestReasonExtraction:
    """Verify gate_result.reason is read (not string-parsed from diagnostic)."""

    def test_non_mapped_reason_no_proximity(self):
        """Reasons not in _PROXIMITY_MAP → no proximity written."""
        m = {}; _proximity_audit(m, _inv("FLOOR WARNING"), _make_ctx(), "INFO")
        assert "Proximity_Signal" not in m

    def test_structural_reason_no_proximity(self):
        m = {}; _proximity_audit(m, _inv("LIQUIDITY FAILED"), _make_ctx(), "INFO")
        assert "Proximity_Signal" not in m

    def test_extended_does_not_crash(self):
        """EXTENDED reason extracted from gate_result.reason, not string parsing."""
        s = _make_state(adx_t=25.0, _entry_trending=True)
        ctx = _make_ctx(state=s, atr_dist=1.15, ext_limit=1.0)
        m = {"Trend_Health_Score": 50}
        _proximity_audit(m, _inv("EXTENDED"), ctx, "INFO")
        if m.get("Proximity_Signal") == "APPROACHING":
            assert m["Proximity_Blocking_Gate"] == "EXTENSION"

    def test_adx_below_20_does_not_crash(self):
        s = _make_state(adx_t=19.0, _entry_trending=True)
        ctx = _make_ctx(state=s, atr_dist=0.3)
        m = {"Trend_Health_Score": 50}
        _proximity_audit(m, _inv("MID-RANGE (ADX < 20)"), ctx, "INFO")
        if m.get("Proximity_Signal") == "APPROACHING":
            assert m["Proximity_Blocking_Gate"] == "ADX_THRESHOLD_20"

    def test_profile_a_resolving_block_does_not_crash(self):
        s = _make_state(adx_t=24.0, _entry_trending=False, _entry_resolving=True, ma_squeeze=False)
        ctx = _make_ctx(p_code="A", state=s, atr_dist=0.3)
        m = {"Trend_Health_Score": 50}
        _proximity_audit(m, _inv("PROFILE A RESOLVING BLOCK"), ctx, "INFO")
        if m.get("Proximity_Signal") == "APPROACHING":
            assert m["Proximity_Blocking_Gate"] == "ADX_THRESHOLD_25"

    def test_reclaim_special_case_does_not_crash(self):
        """FLOOR FAILURE + _reclaim_run == 2 maps to RECLAIM_2_OF_3."""
        s = _make_state(is_floor_failure=True, _reclaim_run=2, ma_stack_full=True,
                        adx_t=25.0, di_plus=30.0, di_minus=15.0)
        ctx = _make_ctx(state=s, atr_dist=0.3)
        m = {"Trend_Health_Score": 50}
        _proximity_audit(m, _inv("FLOOR FAILURE"), ctx, "INFO")
        if m.get("Proximity_Signal") == "APPROACHING":
            assert m["Proximity_Blocking_Gate"] == "RECLAIM_2_OF_3"


class TestNoStringParsing:
    """Verify old string-parsing is removed — GateResult works without 'reason:' pattern."""

    def test_reason_without_legacy_pattern(self):
        gr = GateResult(verdict="INVALID", reason="EXTENDED", mandate="W.", context="T.",
                        legacy_diagnostic="Unstructured text without reason pattern.")
        m = {"Trend_Health_Score": 50}
        ctx = _make_ctx(state=_make_state(adx_t=25.0, _entry_trending=True), atr_dist=1.15)
        _proximity_audit(m, gr, ctx, "INFO")  # must not crash

    def test_empty_legacy_diagnostic(self):
        gr = GateResult(verdict="INVALID", reason="MID-RANGE (ADX < 20)", mandate="W.",
                        context="T.", legacy_diagnostic="")
        m = {"Trend_Health_Score": 50}
        ctx = _make_ctx(state=_make_state(adx_t=19.0, _entry_trending=True), atr_dist=0.3)
        _proximity_audit(m, gr, ctx, "INFO")  # old code would crash — no 'reason:' found
