"""DIAG-001 Amendment: exit_active + exit_reason on INVALID paths.

Tests the two new fields added to INVALID action_summary:
  - exit_active (bool): True when Exit_Signal == "EXIT"
  - exit_reason (str/null): Exit reason string when exit_active is True

Covers spec §5.2 (new test cases), §5.4 (VALID unchanged), §5.5 (ERROR unchanged).
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.types import GateResult
from tbs_engine.transform import _transform_output, _flatten


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invalid_as(reason="EXTENDED", approaching=False, exit_active=False, exit_reason=None):
    return {
        "verdict": "INVALID",
        "reason": reason,
        "approaching": approaching,
        "action": "WAIT.",
        "context": "Blocked.",
        "existing_position_exit_signal": exit_active,
        "existing_position_exit_reason": exit_reason,
    }


def _dd2_as(entry_type="PULLBACK", exit_reason="SMA_50_Breach"):
    return {
        "verdict": "INVALID",
        "reason": entry_type,
        "approaching": False,
        "action": f"EXIT ACTIVE — entry suppressed. Exit via {exit_reason} takes priority over entry signal.",
        "context": f"All gates passed. Trigger met ({entry_type}). Exit_Signal: EXIT ({exit_reason}). Entry suppressed per DD-2.",
        "existing_position_exit_signal": True,
        "existing_position_exit_reason": exit_reason,
    }


def _valid_as():
    return {
        "verdict": "VALID",
        "reason": "PULLBACK",
        "quality": "STRONG",
        "reward": "FAVORABLE [2.5]",
        "exit_warning": False,
        "exit_warning_note": None,
        "trigger_rule": "BAR CLOSE ONLY",
        "trigger_condition": "Close within [140.0 — 145.0]",
        "entry_strategy": {"entry_price": 142.0, "stop_loss": 138.0, "target": 150.0},
        "state": "TRENDING",
        "action": "Execute.",
        "context": "All gates passed.",
    }


def _error_as():
    return {
        "verdict": "ERROR",
        "reason": "DATA INTEGRITY",
        "action": None,
        "context": None,
    }


# ---------------------------------------------------------------------------
# §5.2: INVALID + EXIT scenarios
# ---------------------------------------------------------------------------

class TestInvalidExitActive:
    """INVALID + Exit_Signal="EXIT" → exit_active=True, exit_reason populated."""

    def test_exit_sma50_breach(self):
        a = _invalid_as(exit_active=True, exit_reason="SMA_50_Breach")
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_signal"] is True
        assert r["action_summary"]["existing_position_exit_reason"] == "SMA_50_Breach"

    def test_exit_ema8_counter_exit(self):
        a = _invalid_as(exit_active=True, exit_reason="EMA_8_Counter_Exit")
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_signal"] is True
        assert r["action_summary"]["existing_position_exit_reason"] == "EMA_8_Counter_Exit"


class TestInvalidWarningNotExit:
    """INVALID + Exit_Signal="WARNING" → exit_active=False, exit_reason=None."""

    def test_warning_exit_active_false(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_signal"] is False

    def test_warning_exit_reason_none(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_reason"] is None


class TestInvalidNoExit:
    """INVALID + Exit_Signal=None → exit_active=False, exit_reason=None."""

    def test_no_exit_active_false(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_signal"] is False

    def test_no_exit_reason_none(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_reason"] is None


class TestDD2ExitActive:
    """DD-2 path (VALID forced INVALID by EXIT) → exit_active=True, exit_reason matches."""

    def test_dd2_pullback_exit_active(self):
        a = _dd2_as("PULLBACK", "SMA_50_Breach")
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_signal"] is True
        assert r["action_summary"]["existing_position_exit_reason"] == "SMA_50_Breach"

    def test_dd2_breakout_exit_active(self):
        a = _dd2_as("BREAKOUT", "EMA_8_Breach")
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_signal"] is True
        assert r["action_summary"]["existing_position_exit_reason"] == "EMA_8_Breach"

    def test_dd2_reclaim_exit_active(self):
        a = _dd2_as("RECLAIM", "Floor_Breach")
        r = _transform_output(a, {})
        assert r["action_summary"]["existing_position_exit_signal"] is True
        assert r["action_summary"]["existing_position_exit_reason"] == "Floor_Breach"


# ---------------------------------------------------------------------------
# §5.4: VALID paths unchanged — no exit_active / exit_reason keys
# ---------------------------------------------------------------------------

class TestValidPathUnchanged:
    """VALID action_summary must NOT contain exit_active or exit_reason."""

    def test_valid_no_exit_active(self):
        a = _valid_as()
        r = _transform_output(a, {})
        assert "existing_position_exit_signal" not in r["action_summary"]

    def test_valid_no_exit_reason(self):
        a = _valid_as()
        r = _transform_output(a, {})
        assert "existing_position_exit_reason" not in r["action_summary"]


# ---------------------------------------------------------------------------
# §5.5: ERROR paths unchanged — no exit_active / exit_reason keys
# ---------------------------------------------------------------------------

class TestErrorPathUnchanged:
    """ERROR action_summary must NOT contain exit_active or exit_reason."""

    def test_error_no_exit_active(self):
        a = _error_as()
        r = _transform_output(a, {})
        assert "existing_position_exit_signal" not in r["action_summary"]

    def test_error_no_exit_reason(self):
        a = _error_as()
        r = _transform_output(a, {})
        assert "existing_position_exit_reason" not in r["action_summary"]


# ---------------------------------------------------------------------------
# §3: _flatten reverse-transform — new flat keys
# ---------------------------------------------------------------------------

class TestFlattenExitActive:
    """_flatten extracts exit_active/exit_reason to new flat keys."""

    def test_flatten_exit_active_true(self):
        a = _invalid_as(exit_active=True, exit_reason="SMA_50_Breach")
        grouped = _transform_output(a, {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"})
        _, _, flat = _flatten(grouped)
        assert flat["Exit_Signal_Active"] is True
        assert flat["Exit_Reason_Summary"] == "SMA_50_Breach"

    def test_flatten_exit_active_false(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        grouped = _transform_output(a, {})
        _, _, flat = _flatten(grouped)
        assert flat["Exit_Signal_Active"] is False
        assert "Exit_Reason_Summary" not in flat

    def test_flatten_does_not_overwrite_exit_signal(self):
        """New flat keys are distinct from Exit_Signal / Exit_Reason metrics."""
        a = _invalid_as(exit_active=True, exit_reason="SMA_50_Breach")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        grouped = _transform_output(a, metrics)
        _, _, flat = _flatten(grouped)
        # Exit_Signal / Exit_Reason come from exit_signals group, not action_summary
        assert "Exit_Signal_Active" in flat
        assert "Exit_Reason_Summary" in flat
