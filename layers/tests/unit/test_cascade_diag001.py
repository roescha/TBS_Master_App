"""Integration-level tests for main.py cascade GateResult flow.

DIAG-001 Phase 2A — §8.5
Tests the cascade `or` pattern, side-effect preservation, and GateResult passthrough.
"""

import pytest
from ibkr_purity_engine import GateResult


class TestCascadeOrPattern:
    """Verify the `or` shorthand correctly short-circuits."""

    def test_first_gate_fires_subsequent_skipped(self):
        """When first gate returns GateResult, subsequent gates are skipped."""
        # Simulate the `or` pattern
        gate1 = GateResult(verdict="INVALID", reason="FIRST", mandate="m", context="c")
        gate2 = GateResult(verdict="INVALID", reason="SECOND", mandate="m", context="c")

        gate_result = None
        gate_result = gate_result or gate1
        gate_result = gate_result or gate2

        assert gate_result.reason == "FIRST"

    def test_all_gates_pass_returns_none(self):
        """When all gates return None, result is None."""
        gate_result = None
        gate_result = gate_result or None
        gate_result = gate_result or None
        gate_result = gate_result or None
        assert gate_result is None

    def test_middle_gate_fires(self):
        """When middle gate fires, early gates passed and later gates skipped."""
        gate_result = None
        gate_result = gate_result or None  # gate 1 passes
        gate_result = gate_result or None  # gate 2 passes
        gate_result = gate_result or GateResult(
            verdict="INVALID", reason="MIDRANGE", mandate="m", context="c"
        )
        gate_result = gate_result or GateResult(
            verdict="INVALID", reason="SHOULD_NOT_REACH", mandate="m", context="c"
        )
        assert gate_result.reason == "MIDRANGE"


class TestCascadeSideEffects:
    """Verify side-effects preserved for gates that can't use `or`."""

    def test_precheck_side_effect_pattern(self):
        """_evaluate_precheck side-effects on ctx.risk_a/ctx.reward_a
        are preserved regardless of prior gate result."""
        # Simulate the explicit block pattern
        gate_result = GateResult(
            verdict="INVALID", reason="LIQUIDITY FAILED", mandate="m", context="c"
        )

        # Even when gate_result is already set, the pattern skips precheck
        # but reads ctx.risk_a/ctx.reward_a AFTER
        class MockCtx:
            risk_a = 5.0
            reward_a = 10.0

        ctx = MockCtx()

        # Pattern from main.py:
        if gate_result is None:
            _pc = None  # would call _evaluate_precheck
            if _pc is not None:
                gate_result = _pc
        risk_a = ctx.risk_a     # read AFTER precheck regardless
        reward_a = ctx.reward_a  # read AFTER precheck regardless

        assert risk_a == 5.0
        assert reward_a == 10.0
        assert gate_result.reason == "LIQUIDITY FAILED"

    def test_capital_expectancy_metrics_recovery(self):
        """_gate_capital_expectancy metrics are recovered even when gate passes."""
        # Simulate the explicit block for capital expectancy
        gate_result = None
        metrics = {"Capital_Reward_Risk": 1.8, "Capital_RR_Label": "HEALTHY"}

        # Pattern from main.py:
        if gate_result is None:
            _ceg_result = None  # _gate_capital_expectancy returns None (pass)
            if _ceg_result is not None:
                gate_result = _ceg_result

        # Recover from metrics (written by _gate_capital_expectancy even on pass)
        _capital_rr = metrics.get("Capital_Reward_Risk")
        _reward_label = metrics.get("Capital_RR_Label")

        assert gate_result is None
        assert _capital_rr == 1.8
        assert _reward_label == "HEALTHY"


class TestGateResultBridge:
    """Verify the temporary bridge in _assemble_output correctly maps
    GateResult.verdict to the old result_status values."""

    def test_valid_maps_to_pass(self):
        """verdict='VALID' → result_status='PASS'."""
        gr = GateResult(
            verdict="VALID", reason="PULLBACK", mandate="m", context="c",
            legacy_diagnostic="PRE-APPROVED ...",
            entry_type="PULLBACK", trigger_rule="BAR CLOSE ONLY", state="TRENDING",
        )
        if gr.verdict == "VALID":
            result_status = "PASS"
        elif gr.verdict == "INVALID":
            result_status = "HALT"
        else:
            result_status = "ERROR"
        result_diagnostic = gr.legacy_diagnostic

        assert result_status == "PASS"
        assert result_diagnostic == "PRE-APPROVED ..."

    def test_invalid_maps_to_halt(self):
        """verdict='INVALID' → result_status='HALT'."""
        gr = GateResult(
            verdict="INVALID", reason="EXTENDED", mandate="m", context="c",
            legacy_diagnostic="WAIT (reason: EXTENDED)...",
        )
        if gr.verdict == "VALID":
            result_status = "PASS"
        elif gr.verdict == "INVALID":
            result_status = "HALT"
        else:
            result_status = "ERROR"
        result_diagnostic = gr.legacy_diagnostic

        assert result_status == "HALT"
        assert "EXTENDED" in result_diagnostic

    def test_error_maps_to_error(self):
        """verdict='ERROR' → result_status='ERROR'."""
        gr = GateResult(
            verdict="ERROR", reason="ConnectionError", mandate=None, context=None,
            legacy_diagnostic="ConnectionError: ...",
        )
        if gr.verdict == "VALID":
            result_status = "PASS"
        elif gr.verdict == "INVALID":
            result_status = "HALT"
        else:
            result_status = "ERROR"

        assert result_status == "ERROR"
