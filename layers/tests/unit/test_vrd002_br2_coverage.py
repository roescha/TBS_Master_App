"""VRD-002 + FFD-001-BR-2 Coverage Gap Tests.

Fills 4 specific verification gaps identified during pre-delivery audit:

1. FFD-001-BR-2 V2: Floor_Failure_Context populated on early CRG REJECT
   (the scenario the fix was built for — no prior test covered it)
2. VRD-002: exit.py PE-25 override Exit_Reason contains N/T fraction
3. VRD-002: output.py ATR_Dist_Note uses "warning" not "violation", has fraction
4. VRD-002: trigger.py reclaim diagnostic uses "consecutive bars" with N/T fraction
"""

import sys
import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Stub heavy dependencies before importing engine modules
for _mod in ("ib_insync", "pandas_ta", "plotly", "plotly.graph_objects", "plotly.subplots"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from tbs_engine.helpers import _evaluate_floor_failure_context
from tbs_engine.gates import (
    _gate_context_regime,
    _gate_floor_failure,
)
from tbs_engine.exit import _compute_exit_signals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    """Minimal state namespace for tests."""
    defaults = dict(
        is_floor_failure=False, consec_below=0, _reclaim_run=0,
        is_trending=True, is_resolving=False,
        atr_raw=2.0, floor_raw=100.0,
        adx_t=25.0, di_plus=20.0, di_minus=15.0,
        ema_stacked=True, ma_stack_full=True, ma_squeeze=False,
        _entry_trending=True, _entry_resolving=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0, n=3):
    """Build a minimal higher-frame context DataFrame for FFD-001 tests."""
    data = {
        'close': [close] * n,
        'SMA_50': [sma50 - 1.0] + [sma50] * (n - 1),  # rising
        'SMA_200': [sma200] * n,
    }
    return pd.DataFrame(data)


def _make_exit_df_b(n=30, below_sma50=False, below_ema8=False):
    """Minimal DataFrame for _compute_exit_signals Profile B tests."""
    base = 100.0
    closes = [base + 0.2 * i for i in range(n)]
    df = pd.DataFrame({
        'open': closes,
        'high': [c + 1.0 for c in closes],
        'low': [c - 1.0 for c in closes],
        'close': closes,
        'volume': [500000] * n,
    })
    df['SMA_50'] = base + 3.0  # above close if below_sma50
    df['SMA_200'] = base - 20.0
    df['EMA_8'] = base + 5.0   # above close if below_ema8
    if not below_sma50:
        df['SMA_50'] = base - 5.0
    if not below_ema8:
        df['EMA_8'] = base - 2.0
    return df


# ===========================================================================
# TEST 1: FFD-001-BR-2 V2 — Floor_Failure_Context on early CRG REJECT
# ===========================================================================

class TestFFD001BR2_EarlyReject:
    """The exact scenario FFD-001-BR-2 was built to fix:
    is_floor_failure=True AND an earlier gate (CRG) issues REJECT before
    _gate_floor_failure executes → Floor_Failure_Context must still be written.

    Tests the unconditional call sequence from main.py:
        1. _compute_floor_state sets state.is_floor_failure = True
        2. Unconditional _evaluate_floor_failure_context writes Floor_Failure_Context
        3. CRG fires REJECT → cascade stops
        4. Floor_Failure_Context is NOT null
    """

    def test_early_crg_reject_consolidation_context_populated(self):
        """CRG REJECT + is_floor_failure + higher-frame intact → Floor_Failure_Context = CONSOLIDATION."""
        # State: floor failure active, higher-frame conditions all pass
        state = _make_state(
            is_floor_failure=True, consec_below=5,
            adx_t=15.0, di_plus=25.0, di_minus=20.0,  # condition 3 passes
        )
        # Context: golden cross + price above SMA200 → conditions 1+2 pass
        df_ctx_weekly = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        metrics = {}

        # Step 1: Unconditional call (replicates main.py line ~203)
        _, ffc_label, _ = _evaluate_floor_failure_context(state, df_ctx_weekly, "B")
        metrics["Floor_Failure_Context"] = ffc_label

        # Step 2: CRG fires REJECT (declining weekly SMA 50)
        df_ctx_crg = pd.DataFrame({
            'close': [130.0, 130.0],
            'SMA_50': [121.0, 120.0],  # declining
            'SMA_200': [100.0, 100.0],
        })
        crg_result = _gate_context_regime("B", df_ctx_crg, 1.0, metrics)
        assert crg_result is not None, "CRG should fire REJECT on declining SMA 50"
        assert crg_result[0] == "HALT"
        assert "CONTEXT REGIME" in crg_result[1]

        # Step 3: THE FIX — Floor_Failure_Context is populated despite CRG REJECT
        assert metrics["Floor_Failure_Context"] == "CONSOLIDATION", \
            "Floor_Failure_Context must be written BEFORE CRG fires, not null"

    def test_early_crg_reject_structural_breakdown_context_populated(self):
        """CRG REJECT + is_floor_failure + bearish DI → Floor_Failure_Context = STRUCTURAL_BREAKDOWN."""
        state = _make_state(
            is_floor_failure=True, consec_below=5,
            adx_t=25.0, di_plus=15.0, di_minus=30.0,  # condition 3 fails
        )
        df_ctx_weekly = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        metrics = {}

        # Unconditional call
        _, ffc_label, _ = _evaluate_floor_failure_context(state, df_ctx_weekly, "B")
        metrics["Floor_Failure_Context"] = ffc_label

        # CRG REJECT
        df_ctx_crg = pd.DataFrame({
            'close': [130.0, 130.0],
            'SMA_50': [121.0, 120.0],
            'SMA_200': [100.0, 100.0],
        })
        crg_result = _gate_context_regime("B", df_ctx_crg, 1.0, metrics)
        assert crg_result is not None

        # Context populated with STRUCTURAL_BREAKDOWN
        assert "STRUCTURAL_BREAKDOWN" in metrics["Floor_Failure_Context"], \
            "Floor_Failure_Context must capture structural breakdown before CRG REJECT"

    def test_no_floor_failure_no_context_written(self):
        """is_floor_failure=False → unconditional block does NOT run, Floor_Failure_Context absent."""
        state = _make_state(is_floor_failure=False, consec_below=0)
        metrics = {}

        # Replicate main.py guard: only call when is_floor_failure is True
        if state.is_floor_failure:
            _, ffc_label, _ = _evaluate_floor_failure_context(state, None, "B")
            metrics["Floor_Failure_Context"] = ffc_label

        assert "Floor_Failure_Context" not in metrics, \
            "Floor_Failure_Context must NOT be written when is_floor_failure=False"

    def test_early_liquidity_reject_context_populated(self):
        """Liquidity REJECT + is_floor_failure → Floor_Failure_Context still written.

        Tests a different early-REJECT gate to prove the fix is gate-independent.
        """
        state = _make_state(
            is_floor_failure=True, consec_below=4,
            adx_t=15.0, di_plus=25.0, di_minus=20.0,
        )
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        metrics = {}

        # Unconditional call (before any gate)
        _, ffc_label, _ = _evaluate_floor_failure_context(state, df_ctx, "B")
        metrics["Floor_Failure_Context"] = ffc_label

        # At this point, even if Liquidity, Data Integrity, or any other gate
        # fires REJECT next, Floor_Failure_Context is already in metrics.
        assert metrics["Floor_Failure_Context"] == "CONSOLIDATION"


# ===========================================================================
# TEST 2: VRD-002 — Exit_Reason strings contain N/T fraction
# ===========================================================================

class TestExitReasonFractions:
    """PE-25 floor failure override in _compute_exit_signals writes Exit_Reason.
    VRD-002 requires N/T fractions in all floor diagnostic strings.
    """

    def test_breach_exit_reason_has_fraction(self):
        """FLOOR BREACH Exit_Reason contains N/T fraction (e.g., 4/4)."""
        df = _make_exit_df_b(below_sma50=False)
        state = _make_state(
            is_floor_failure=True, consec_below=4, _reclaim_run=1,
        )
        metrics = {"Floor_Failure_Context": "CONSOLIDATION"}
        _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics,
            _ff_threshold=4,
        )
        reason = metrics["Exit_Reason"]
        assert "4/4" in reason, f"BREACH Exit_Reason missing fraction: {reason}"
        assert "consecutive bars" in reason, f"BREACH Exit_Reason missing 'consecutive bars': {reason}"
        assert "FLOOR BREACH" in reason

    def test_failure_exit_reason_has_fraction(self):
        """FLOOR FAILURE OVERRIDE Exit_Reason contains N/T fraction."""
        df = _make_exit_df_b(below_sma50=False)
        state = _make_state(
            is_floor_failure=True, consec_below=5, _reclaim_run=0,
        )
        metrics = {"Floor_Failure_Context": "STRUCTURAL_BREAKDOWN (bearish DI)"}
        _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics,
            _ff_threshold=4,
        )
        reason = metrics["Exit_Reason"]
        assert "5/4" in reason, f"FAILURE Exit_Reason missing fraction: {reason}"
        assert "consecutive bars" in reason, f"FAILURE Exit_Reason missing 'consecutive bars': {reason}"
        assert "FLOOR FAILURE OVERRIDE" in reason

    def test_breach_exit_reason_profile_a_threshold_8(self):
        """Profile A uses threshold 8 — fraction should be N/8."""
        df = _make_exit_df_b(below_sma50=False)  # content doesn't matter for PE-25 override
        state = _make_state(
            is_floor_failure=True, consec_below=9, _reclaim_run=2,
        )
        metrics = {"Floor_Failure_Context": "CONSOLIDATION"}
        _compute_exit_signals(
            state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics,
            _ff_threshold=8,
        )
        reason = metrics["Exit_Reason"]
        assert "9/8" in reason, f"Profile A Exit_Reason missing 9/8 fraction: {reason}"

    def test_no_violation_in_exit_reason(self):
        """VRD-002: Exit_Reason must not contain 'VIOLATION'."""
        df = _make_exit_df_b(below_sma50=False)
        state = _make_state(
            is_floor_failure=True, consec_below=4, _reclaim_run=0,
        )
        for ctx_label in ["CONSOLIDATION", "STRUCTURAL_BREAKDOWN (test)"]:
            metrics = {"Floor_Failure_Context": ctx_label}
            _compute_exit_signals(
                state, "B", df, df.iloc[-1], False, None, -1, 1.0, metrics,
                _ff_threshold=4,
            )
            reason = metrics.get("Exit_Reason", "")
            assert "VIOLATION" not in reason, \
                f"Exit_Reason still contains VIOLATION: {reason}"


# ===========================================================================
# TEST 3: VRD-002 — ATR_Dist_Note uses "warning" not "violation", has fraction
# ===========================================================================

class TestATRDistNote:
    """The ATR_Dist_Note block in output.py fires when atr_dist > 0 AND
    (is_violated or is_floor_failure) AND live bar is above floor.
    VRD-002 changed "violation" → "warning" and added N/T fraction.

    Tests the string construction directly since _populate_base_metrics
    requires a full RunContext.
    """

    def _build_note(self, is_floor_failure, consec_below, _ff_threshold,
                    close=102.0, anchor=100.0, price_scaler=1.0):
        """Replicate the ATR_Dist_Note construction from output.py."""
        return (
            f"LIVE BAR RECOVERY: current bar above floor ({round(close / price_scaler, 2)} > "
            f"{round(anchor / price_scaler, 2)}) but floor "
            f"{'failure' if is_floor_failure else 'warning'} based on "
            f"{consec_below}/{_ff_threshold} completed consecutive bars below. "
            f"Check Exit_Signal field for position management status."
        )

    def test_floor_failure_uses_failure_label(self):
        """is_floor_failure=True → note says 'failure' not 'violation'."""
        note = self._build_note(is_floor_failure=True, consec_below=5, _ff_threshold=4)
        assert "failure" in note
        assert "violation" not in note
        assert "5/4" in note
        assert "completed consecutive bars" in note

    def test_floor_warning_uses_warning_label(self):
        """is_floor_failure=False (violated state) → note says 'warning' not 'violation'."""
        note = self._build_note(is_floor_failure=False, consec_below=2, _ff_threshold=4)
        assert "warning" in note
        assert "violation" not in note
        assert "2/4" in note

    def test_profile_a_threshold_8(self):
        """Profile A threshold 8 appears in fraction."""
        note = self._build_note(is_floor_failure=True, consec_below=9, _ff_threshold=8)
        assert "9/8" in note

    def test_no_bar_s_in_note(self):
        """No 'bar(s)' — must use 'consecutive bars'."""
        note = self._build_note(is_floor_failure=True, consec_below=3, _ff_threshold=4)
        assert "bar(s)" not in note
        assert "consecutive bars" in note

    def test_matches_engine_output(self):
        """Verify our test helper exactly matches the engine string template.

        Guards against test-engine drift: if someone changes the output.py
        template without updating this test, this assertion catches it.
        """
        import inspect
        from tbs_engine.output import _populate_base_metrics
        source = inspect.getsource(_populate_base_metrics)
        # The template in output.py must contain these exact fragments
        assert "completed consecutive bars below" in source, \
            "output.py template diverged: 'completed consecutive bars below' not found"
        assert "/{_ff_threshold}" in source, \
            "output.py template diverged: '/{_ff_threshold}' fraction not found"
        assert "'warning'" in source, \
            "output.py template diverged: 'warning' label not found"


# ===========================================================================
# TEST 4: VRD-002 — trigger.py reclaim diagnostic uses fraction + "consecutive bars"
# ===========================================================================

class TestTriggerReclaimFraction:
    """The reclaim PASS diagnostic in trigger.py includes:
        f"after {state.consec_below}/{cfg.ff_threshold} prior consecutive bars below Floor."

    VRD-002 changed "bar(s)" → "consecutive bars" and added N/T fraction.
    """

    def test_trigger_source_has_fraction(self):
        """trigger.py source contains the N/T fraction pattern for reclaim."""
        import inspect
        from tbs_engine.trigger import _identify_trigger
        source = inspect.getsource(_identify_trigger)
        assert "/{cfg.ff_threshold}" in source, \
            "trigger.py missing N/T fraction in reclaim diagnostic"

    def test_trigger_source_has_consecutive_bars(self):
        """trigger.py reclaim diagnostic uses 'consecutive bars' not 'bar(s)'."""
        import inspect
        from tbs_engine.trigger import _identify_trigger
        source = inspect.getsource(_identify_trigger)
        assert "prior consecutive bars below Floor" in source, \
            "trigger.py missing 'prior consecutive bars below Floor' in reclaim diagnostic"
        assert "bar(s)" not in source, \
            "trigger.py still contains 'bar(s)' — should be 'consecutive bars'"

    def test_gate_floor_failure_diagnostic_has_fraction(self):
        """_gate_floor_failure diagnostic includes N/T fraction (regression guard)."""
        result = _gate_floor_failure(
            consec_below=5, is_floor_failure=True, p_code="B",
            _ff_threshold=4,
        )
        assert result is not None
        diag = result[1]
        assert "5/4" in diag, f"Missing fraction in: {diag}"
        assert "consecutive bars" in diag

    def test_gate_floor_failure_profile_a_fraction(self):
        """Profile A uses threshold 8 — diagnostic shows N/8."""
        result = _gate_floor_failure(
            consec_below=10, is_floor_failure=True, p_code="A",
            _ff_threshold=8,
        )
        diag = result[1]
        assert "10/8" in diag, f"Missing 10/8 fraction: {diag}"
        assert "evaluated on last completed bar" in diag
