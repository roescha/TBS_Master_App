"""DIAG-001 Phase 2B: DD-3 entry_strategy moved tests.

entry_strategy moves from trade_snapshot to action_summary (VALID only).
INVALID path: action_summary does NOT contain entry_strategy key.
ERROR path: no entry_strategy anywhere.

Spec: DIAG_001_Action_Summary_Spec_v1_0.md §II DD-3
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.6
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _transform_output, _error_output


class TestDD3ValidPath:
    """VALID path: action_summary.entry_strategy present with 3 fields."""

    def test_entry_strategy_in_action_summary(self):
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "quality": "HEALTHY", "reward": "N/A",
            "exit_warning": False, "exit_warning_note": None,
            "trigger_rule": "BAR CLOSE ONLY", "trigger_condition": "test",
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
            "state": "TRENDING", "mandate": "Execute.", "context": "Test.",
        }
        r = _transform_output(a, {})
        es = r["action_summary"]["entry_strategy"]
        assert es["entry_price"] == 142.0
        assert es["stop_loss"] == 140.0
        assert es["target"] == 160.0

    def test_entry_strategy_not_in_trade_snapshot(self):
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "quality": "HEALTHY", "reward": "N/A",
            "exit_warning": False, "exit_warning_note": None,
            "trigger_rule": "BAR CLOSE ONLY", "trigger_condition": "test",
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
            "state": "TRENDING", "mandate": "Execute.", "context": "Test.",
        }
        r = _transform_output(a, {"Entry_Reference": 142.0, "Hard_Stop": 140.0, "Profit_Target": 160.0})
        assert "entry_strategy" not in r["trade_snapshot"]

    def test_trade_snapshot_has_5_keys(self):
        """trade_snapshot: current_price, support, resistance, avg_daily_volume, classification."""
        a = {"verdict": "VALID", "reason": "PULLBACK",
             "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0}}
        r = _transform_output(a, {})
        assert len(r["trade_snapshot"]) == 5


class TestDD3InvalidPath:
    """INVALID path: no entry_strategy anywhere."""

    def test_no_entry_strategy_in_action_summary(self):
        a = {"verdict": "INVALID", "reason": "EXTENDED", "approaching": False,
             "mandate": "WAIT.", "context": "Test."}
        r = _transform_output(a, {})
        assert "entry_strategy" not in r["action_summary"]

    def test_no_entry_strategy_in_trade_snapshot(self):
        a = {"verdict": "INVALID", "reason": "EXTENDED", "approaching": False,
             "mandate": "WAIT.", "context": "Test."}
        r = _transform_output(a, {})
        assert "entry_strategy" not in r["trade_snapshot"]


class TestDD3ErrorPath:
    """ERROR path: no entry_strategy anywhere."""

    def test_error_no_entry_strategy(self):
        r = _error_output("ERROR", "test")
        assert "entry_strategy" not in r.get("action_summary", {})
        assert "trade_snapshot" not in r  # DD-9: ERROR path has no other groups
