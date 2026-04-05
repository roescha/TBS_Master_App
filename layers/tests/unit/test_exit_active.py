"""DIAG-001 Amendment + AS-001: exit_status on INVALID/WAIT paths.

Tests the exit_status field in action_summary.
Updated for AS-001 restructuring.
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _transform_output, _flatten


def _invalid_as(reason="EXTENDED", approaching=False, exit_active=False, exit_reason=None):
    return {
        "verdict": "INVALID",
        "reason": {"label": reason, "detail": "Blocked."},
        "approaching": approaching,
        "volume": None,
        "exit_status": {"active": exit_active, "reason": exit_reason},
    }


def _dd2_as(entry_type="PULLBACK", exit_reason="SMA_50_Breach"):
    return {
        "verdict": "INVALID",
        "reason": {"label": entry_type, "detail": f"Exit_Signal: EXIT ({exit_reason})."},
        "approaching": False,
        "mandate": f"EXIT ACTIVE -- entry suppressed.",
        "volume": None,
        "exit_status": {"active": True, "reason": exit_reason},
    }


def _valid_as():
    return {
        "verdict": "VALID",
        "reason": {"label": "PULLBACK", "detail": "All gates passed."},
        "mandate": "Execute.",
        "merit": {"quality": "STRONG", "reward": "FAVORABLE [2.5]"},
        "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Close within [140.0 -- 145.0]"},
        "entry_strategy": {"entry_price": 142.0, "stop_loss": 138.0, "target": 150.0},
        "volume": None,
        "exit_status": {"active": False, "reason": None},
    }


def _error_as():
    return {
        "verdict": "ERROR",
        "reason": {"label": "DATA INTEGRITY", "detail": None},
        "exit_status": {"active": False, "reason": None},
    }


class TestInvalidExitActive:
    def test_exit_sma50_breach(self):
        a = _invalid_as(exit_active=True, exit_reason="SMA_50_Breach")
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is True
        assert r["action_summary"]["exit_status"]["reason"] == "SMA_50_Breach"

    def test_exit_ema8_counter_exit(self):
        a = _invalid_as(exit_active=True, exit_reason="EMA_8_Counter_Exit")
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is True
        assert r["action_summary"]["exit_status"]["reason"] == "EMA_8_Counter_Exit"


class TestInvalidWarningNotExit:
    def test_warning_exit_active_false(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is False

    def test_warning_exit_reason_none(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["reason"] is None


class TestInvalidNoExit:
    def test_no_exit_active_false(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is False

    def test_no_exit_reason_none(self):
        a = _invalid_as(exit_active=False, exit_reason=None)
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["reason"] is None


class TestDD2ExitActive:
    def test_dd2_pullback_exit_active(self):
        a = _dd2_as("PULLBACK", "SMA_50_Breach")
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is True
        assert r["action_summary"]["exit_status"]["reason"] == "SMA_50_Breach"

    def test_dd2_breakout_exit_active(self):
        a = _dd2_as("BREAKOUT", "EMA_8_Breach")
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is True

    def test_dd2_reclaim_exit_active(self):
        a = _dd2_as("RECLAIM", "Floor_Breach")
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is True


class TestValidPathExitStatus:
    def test_valid_exit_status(self):
        a = _valid_as()
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is False


class TestErrorPathExitStatus:
    def test_error_exit_status(self):
        a = _error_as()
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_status"]["active"] is False


class TestFlattenExitActive:
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
        a = _invalid_as(exit_active=True, exit_reason="SMA_50_Breach")
        metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "SMA_50_Breach"}
        grouped = _transform_output(a, metrics)
        _, _, flat = _flatten(grouped)
        assert "Exit_Signal_Active" in flat
        assert "Exit_Reason_Summary" in flat
