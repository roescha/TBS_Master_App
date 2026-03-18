"""DIAG-001 Phase 2B: DD-5 exit_warning tests.

When Exit_Signal == "WARNING" coexists with VALID: exit_warning: true
with fixed note. VALID + no exit → exit_warning: false.
VALID + EXIT → forced INVALID by DD-2 (exit_warning not applicable).

Spec: DIAG_001_Action_Summary_Spec_v1_0.md §II DD-5
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.5, §10
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _transform_output

_FIXED_NOTE = "Expected on deep pullback — exit system detects price at entry zone level, not a quality concern."


def _valid_as_with_exit(exit_warning, exit_warning_note):
    return {
        "verdict": "VALID",
        "reason": "PULLBACK",
        "quality": "HEALTHY",
        "reward": "HEALTHY [2.35]",
        "exit_warning": exit_warning,
        "exit_warning_note": exit_warning_note,
        "trigger_rule": "BAR CLOSE ONLY",
        "trigger_condition": "Close within [142.0 — 145.0]",
        "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        "state": "TRENDING",
        "mandate": "Execute.",
        "context": "Test.",
    }


class TestDD5ExitWarningTrue:
    """VALID + WARNING → exit_warning=true, exit_warning_note=(fixed string)."""

    def test_exit_warning_true(self):
        a = _valid_as_with_exit(True, _FIXED_NOTE)
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_warning"] is True

    def test_exit_warning_note_exact_string(self):
        a = _valid_as_with_exit(True, _FIXED_NOTE)
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_warning_note"] == _FIXED_NOTE

    def test_fixed_note_exact_text(self):
        """Verify the EXACT fixed string from spec §10."""
        assert _FIXED_NOTE == (
            "Expected on deep pullback — exit system detects price at "
            "entry zone level, not a quality concern."
        )


class TestDD5ExitWarningFalse:
    """VALID + no exit → exit_warning=false, exit_warning_note=null."""

    def test_exit_warning_false(self):
        a = _valid_as_with_exit(False, None)
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_warning"] is False

    def test_exit_warning_note_null(self):
        a = _valid_as_with_exit(False, None)
        r = _transform_output(a, {})
        assert r["action_summary"]["exit_warning_note"] is None


class TestDD5ExitForcesInvalid:
    """VALID + EXIT → forced INVALID by DD-2 (exit_warning not applicable)."""

    def test_dd2_invalid_has_no_exit_warning(self):
        a = {
            "verdict": "INVALID",
            "reason": "PULLBACK",
            "approaching": False,
            "mandate": "EXIT ACTIVE.",
            "context": "DD-2.",
        }
        r = _transform_output(a, {})
        assert "exit_warning" not in r["action_summary"]
