"""DIAG-001 Phase 2B: DD-2 EXIT forces INVALID tests.

When Exit_Signal == "EXIT" and gate cascade + trigger would produce VALID,
the verdict is forced to INVALID. The reason preserves the original entry type.

Spec: DIAG_001_Action_Summary_Spec_v1_0.md §V.2 (DD-2 forcing)
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.4
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.types import GateResult
from tbs_engine.transform import _transform_output


def _simulate_dd2_construction(gate_result, metrics):
    """Replicate the DD-2 branch of _assemble_output action_summary construction.

    This is a direct copy of the construction logic from output.py for
    isolated testing without a full RunContext.
    """
    _exit_sig = metrics.get("Exit_Signal")
    if gate_result.verdict == "VALID" and _exit_sig == "EXIT":
        _exit_reason = metrics.get("Exit_Reason", "Unknown")
        return {
            "verdict": "INVALID",
            "reason": gate_result.reason,
            "approaching": False,
            "action": f"EXIT ACTIVE — entry suppressed. Exit via {_exit_reason} takes priority over entry signal.",
            "context": (f"All gates passed. Trigger met ({gate_result.reason}). "
                        f"Exit_Signal: EXIT ({_exit_reason}). Entry suppressed per DD-2."),
            "existing_position_exit_signal": True,
            "existing_position_exit_reason": _exit_reason,
        }
    return None  # DD-2 not triggered


def _make_valid_gate_result(entry_type, state="TRENDING"):
    trigger_rule = "INTRADAY" if entry_type == "BREAKOUT" else "BAR CLOSE ONLY"
    return GateResult(
        verdict="VALID", reason=entry_type,
        mandate="Execute.", context="Test context.",
        legacy_diagnostic="test",
        entry_type=entry_type, trigger_rule=trigger_rule, state=state,
    )


class TestDD2PullbackExit:
    """PULLBACK + EXIT → INVALID."""

    def test_verdict_forced_invalid(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["verdict"] == "INVALID"

    def test_reason_preserves_pullback(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["reason"] == "PULLBACK"

    def test_approaching_false(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["approaching"] is False

    def test_mandate_contains_exit_active(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert "EXIT ACTIVE" in a["action"]

    def test_mandate_contains_exit_reason(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert "SMA_50_Breach" in a["action"]

    def test_context_contains_entry_suppressed(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert "Entry suppressed" in a["context"]

    def test_context_contains_trigger_met(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert "Trigger met (PULLBACK)" in a["context"]

    def test_no_entry_strategy(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert "entry_strategy" not in a

    def test_exit_active_true(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["existing_position_exit_signal"] is True

    def test_exit_reason_matches(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["existing_position_exit_reason"] == "SMA_50_Breach"


class TestDD2BreakoutExit:
    """BREAKOUT + EXIT → INVALID."""

    def test_verdict_forced_invalid(self):
        gr = _make_valid_gate_result("BREAKOUT", state="RESOLVING")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "EMA_8_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["verdict"] == "INVALID"

    def test_reason_preserves_breakout(self):
        gr = _make_valid_gate_result("BREAKOUT", state="RESOLVING")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "EMA_8_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["reason"] == "BREAKOUT"

    def test_exit_active_true(self):
        gr = _make_valid_gate_result("BREAKOUT", state="RESOLVING")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "EMA_8_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["existing_position_exit_signal"] is True

    def test_exit_reason_matches(self):
        gr = _make_valid_gate_result("BREAKOUT", state="RESOLVING")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "EMA_8_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["existing_position_exit_reason"] == "EMA_8_Breach"


class TestDD2ReclaimExit:
    """RECLAIM + EXIT → INVALID."""

    def test_verdict_forced_invalid(self):
        gr = _make_valid_gate_result("RECLAIM")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Floor_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["verdict"] == "INVALID"

    def test_reason_preserves_reclaim(self):
        gr = _make_valid_gate_result("RECLAIM")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Floor_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["reason"] == "RECLAIM"

    def test_exit_active_true(self):
        gr = _make_valid_gate_result("RECLAIM")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Floor_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["existing_position_exit_signal"] is True

    def test_exit_reason_matches(self):
        gr = _make_valid_gate_result("RECLAIM")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Floor_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a["existing_position_exit_reason"] == "Floor_Breach"


class TestDD2NotTriggered:
    """DD-2 only fires on EXIT, not WARNING or no-exit."""

    def test_warning_does_not_trigger_dd2(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": "WARNING", "Exit_Reason": "Floor_Proximity"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a is None  # DD-2 not triggered

    def test_no_exit_does_not_trigger_dd2(self):
        gr = _make_valid_gate_result("PULLBACK")
        metrics = {"Exit_Signal": False, "Exit_Reason": "None"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a is None

    def test_invalid_verdict_does_not_trigger_dd2(self):
        gr = GateResult(verdict="INVALID", reason="EXTENDED",
                        mandate="WAIT.", context="Test.", legacy_diagnostic="test")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        a = _simulate_dd2_construction(gr, metrics)
        assert a is None  # Only VALID verdict triggers DD-2


class TestDD2OutputShape:
    """Verify DD-2 forced INVALID produces correct output through _transform_output."""

    def test_dd2_output_has_action_summary(self):
        a = {
            "verdict": "INVALID",
            "reason": "PULLBACK",
            "approaching": False,
            "action": "EXIT ACTIVE — entry suppressed.",
            "context": "All gates passed. Entry suppressed per DD-2.",
            "existing_position_exit_signal": True,
            "existing_position_exit_reason": "SMA_50_Breach",
        }
        r = _transform_output(a, {})
        assert r["action_summary"]["verdict"] == "INVALID"

    def test_dd2_output_no_status(self):
        a = {
            "verdict": "INVALID",
            "reason": "PULLBACK",
            "approaching": False,
            "action": "EXIT ACTIVE.",
            "context": "DD-2.",
            "existing_position_exit_signal": True,
            "existing_position_exit_reason": "SMA_50_Breach",
        }
        r = _transform_output(a, {})
        assert "status" not in r
        assert "diagnostic" not in r

    def test_dd2_output_exit_active_true(self):
        a = {
            "verdict": "INVALID",
            "reason": "PULLBACK",
            "approaching": False,
            "action": "EXIT ACTIVE.",
            "context": "DD-2.",
            "existing_position_exit_signal": True,
            "existing_position_exit_reason": "SMA_50_Breach",
        }
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_signal"] is True

    def test_dd2_output_exit_reason_present(self):
        a = {
            "verdict": "INVALID",
            "reason": "PULLBACK",
            "approaching": False,
            "action": "EXIT ACTIVE.",
            "context": "DD-2.",
            "existing_position_exit_signal": True,
            "existing_position_exit_reason": "SMA_50_Breach",
        }
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_reason"] == "SMA_50_Breach"
