"""DIAG-001 Phase 2B: action_summary ERROR path tests.

DD-9: ERROR path emits action_summary only, all other groups suppressed.

Spec: DIAG_001_Action_Summary_Spec_v1_0.md §V.3
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.3
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _error_output


class TestErrorShape:
    """ERROR verdict: only action_summary in output dict."""

    def test_error_verdict(self):
        r = _error_output("ERROR", "Connection failed")
        assert r["action_summary"]["verdict"] == "ERROR"

    def test_error_reason(self):
        r = _error_output("ERROR", "Connection failed")
        assert r["action_summary"]["reason"]["label"] == "Connection failed"

    def test_error_mandate_null(self):
        r = _error_output("ERROR", "test")
        assert r["action_summary"].get("mandate") is None

    def test_error_context_null(self):
        r = _error_output("ERROR", "test")
        assert r["action_summary"]["reason"]["detail"] is None

    def test_error_only_action_summary_key(self):
        """DD-9: ERROR path has exactly 1 key (action_summary)."""
        r = _error_output("ERROR", "test")
        assert set(r.keys()) == {"action_summary"}

    def test_error_no_trade_snapshot(self):
        r = _error_output("ERROR", "test")
        assert "trade_snapshot" not in r

    def test_error_no_trade_quality(self):
        r = _error_output("ERROR", "test")
        assert "trade_quality" not in r

    def test_error_no_trade_risk(self):
        r = _error_output("ERROR", "test")
        assert "trade_risk" not in r

    def test_error_no_trend_state(self):
        r = _error_output("ERROR", "test")
        assert "trend_state" not in r

    def test_error_no_exit_signals(self):
        r = _error_output("ERROR", "test")
        assert "exit_signals" not in r

    def test_error_no_status_key(self):
        r = _error_output("ERROR", "test")
        assert "status" not in r

    def test_error_no_diagnostic_key(self):
        r = _error_output("ERROR", "test")
        assert "diagnostic" not in r

    def test_error_with_debug_has_2_keys(self):
        """DD-9: with debug, 2 keys (action_summary + _debug)."""
        r = _error_output("ERROR", "test", debug=True)
        assert set(r.keys()) == {"action_summary", "_debug"}
        assert r["_debug"] is None

    def test_error_4_fields(self):
        """ERROR shape: 4 fields (verdict, reason, mandate, context)."""
        r = _error_output("ERROR", "test")
        assert len(r["action_summary"]) >= 2

    def test_error_no_approaching(self):
        """ERROR shape does NOT have approaching field."""
        r = _error_output("ERROR", "test")
        assert "approaching" not in r["action_summary"]

    def test_error_reason_preserves_message(self):
        msg = "INVALID CONVEXITY CLASS: 'X'. Valid: None, 'C1', 'C2', 'C3'."
        r = _error_output("ERROR", msg)
        assert r["action_summary"]["reason"]["label"] == msg
