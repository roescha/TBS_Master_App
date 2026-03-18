"""DIAG-001 Phase 2B: action_summary INVALID path tests.

Tests representative INVALID reason labels (all 23 from spec §IV.1).
Each verifies: verdict="INVALID", reason=(exact label), approaching=(boolean),
mandate/context present, no entry_strategy, no status/diagnostic keys.

Spec: DIAG_001_Action_Summary_Spec_v1_0.md §V.2
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.2
"""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _transform_output


def _invalid_action_summary(reason, approaching=False, exit_active=False, exit_reason=None, mandate="WAIT.", context="Blocked."):
    return {
        "verdict": "INVALID",
        "reason": reason,
        "approaching": approaching,
        "action": mandate,
        "context": context,
        "existing_position_exit_signal": exit_active,
        "existing_position_exit_reason": exit_reason,
    }


def _make_output(reason, approaching=False):
    a = _invalid_action_summary(reason, approaching=approaching)
    return _transform_output(a, {})


# Complete list of 23 INVALID reason labels from spec §IV.1
_ALL_INVALID_REASONS = [
    "CONTEXT REGIME FAILED",
    "DATA INTEGRITY",
    "LIQUIDITY FAILED",
    "FLOOR BREACH",
    "FLOOR FAILURE",
    "FLOOR WARNING",
    "FLOOR WARNING ACTIVE",
    "VOLUME CLIMAX",
    "MID-RANGE (ADX < 20)",
    "MID-RANGE (MA SQUEEZE)",
    "DIRECTIONAL BLOCK",
    "GAP TRAP",
    "WINDOW EXPIRED",
    "EXTENDED",
    "FLOOR PROXIMITY FAILED",
    "EXPECTANCY FAILED",
    "CAPITAL EXPECTANCY FAILED",
    "RECLAIM WITHOUT REGIME",
    "NOT IN PULLBACK ZONE",
    "NO BREAKOUT",
    "PROFILE A RESOLVING BLOCK",
    "AMBIGUOUS STATE",
    "UNSUPPORTED ASSET CLASS",
]


class TestInvalidShape:
    """Verify INVALID shape: 7 fields (verdict, reason, approaching, exit_active, exit_reason, mandate, context)."""

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_verdict_invalid(self, reason):
        r = _make_output(reason)
        assert r["action_summary"]["verdict"] == "INVALID"

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_reason_matches(self, reason):
        r = _make_output(reason)
        assert r["action_summary"]["reason"] == reason

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_approaching_is_boolean(self, reason):
        r = _make_output(reason)
        assert isinstance(r["action_summary"]["approaching"], bool)

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_exit_active_is_boolean(self, reason):
        r = _make_output(reason)
        assert isinstance(r["action_summary"]["existing_position_exit_signal"], bool)

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_exit_reason_is_str_or_none(self, reason):
        r = _make_output(reason)
        val = r["action_summary"]["existing_position_exit_reason"]
        assert val is None or isinstance(val, str)

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_mandate_present(self, reason):
        r = _make_output(reason)
        assert r["action_summary"]["action"] is not None

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_context_present(self, reason):
        r = _make_output(reason)
        assert r["action_summary"]["context"] is not None

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_no_entry_strategy(self, reason):
        r = _make_output(reason)
        assert "entry_strategy" not in r["action_summary"]

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_no_status_key(self, reason):
        r = _make_output(reason)
        assert "status" not in r

    @pytest.mark.parametrize("reason", _ALL_INVALID_REASONS)
    def test_no_diagnostic_key(self, reason):
        r = _make_output(reason)
        assert "diagnostic" not in r


class TestInvalidApproaching:
    """DD-6: approaching boolean on INVALID paths."""

    def test_approaching_true(self):
        r = _make_output("EXTENDED", approaching=True)
        assert r["action_summary"]["approaching"] is True

    def test_approaching_false(self):
        r = _make_output("FLOOR FAILURE", approaching=False)
        assert r["action_summary"]["approaching"] is False


class TestInvalidFieldCount:
    """INVALID shape: exactly 7 fields."""

    def test_invalid_has_7_fields(self):
        a = _invalid_action_summary("EXTENDED")
        assert len(a) == 7


class TestInvalidNoRetiredVocab:
    """Verify retired vocabulary never appears."""

    def test_no_pre_approved(self):
        r = _make_output("EXTENDED")
        for key, val in r["action_summary"].items():
            if isinstance(val, str):
                assert "PRE-APPROVED" not in val

    def test_no_wait_verdict(self):
        r = _make_output("EXTENDED")
        assert r["action_summary"]["verdict"] != "WAIT"

    def test_no_reject_verdict(self):
        r = _make_output("EXTENDED")
        assert r["action_summary"]["verdict"] != "REJECT"
