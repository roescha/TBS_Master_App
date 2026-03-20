"""DIAG-001 Phase 2B: _error_output tests.

ERROR verdict: only action_summary in output (DD-9).
INVALID verdict (data layer HALT): full grouped output with action_summary.
Both: verify action_summary has correct verdict and reason.

Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.10
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _error_output


class TestErrorVerdict:
    """ERROR verdict: only action_summary in output dict (DD-9)."""

    def test_error_only_action_summary(self):
        r = _error_output("ERROR", "Connection failed")
        assert set(r.keys()) == {"action_summary"}

    def test_error_verdict_field(self):
        r = _error_output("ERROR", "test")
        assert r["action_summary"]["verdict"] == "ERROR"

    def test_error_reason_field(self):
        r = _error_output("ERROR", "Connection failed")
        assert r["action_summary"]["reason"] == "Connection failed"

    def test_error_mandate_null(self):
        r = _error_output("ERROR", "test")
        assert r["action_summary"]["action"] is None

    def test_error_context_null(self):
        r = _error_output("ERROR", "test")
        assert r["action_summary"]["context"] is None

    def test_error_no_approaching(self):
        r = _error_output("ERROR", "test")
        assert "approaching" not in r["action_summary"]

    def test_error_4_fields(self):
        r = _error_output("ERROR", "test")
        assert len(r["action_summary"]) == 4

    def test_error_debug_adds_debug_key(self):
        r = _error_output("ERROR", "test", debug=True)
        assert set(r.keys()) == {"action_summary", "_debug"}


class TestInvalidVerdict:
    """INVALID verdict (data layer HALT): full grouped output."""

    def test_invalid_has_full_groups(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert "trade_snapshot" in r
        assert "trade_quality" in r
        assert "trade_risk" in r
        assert "exit_signals" in r

    def test_invalid_verdict_field(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert r["action_summary"]["verdict"] == "INVALID"

    def test_invalid_reason_field(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert r["action_summary"]["reason"] == "DATA INTEGRITY"

    def test_invalid_approaching_false(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert r["action_summary"]["approaching"] is False

    def test_invalid_mandate_null(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert r["action_summary"]["action"] is None

    def test_invalid_context_null(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert r["action_summary"]["context"] is None

    def test_invalid_5_fields(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert len(r["action_summary"]) == 5

    def test_invalid_no_status_key(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert "status" not in r

    def test_invalid_no_diagnostic_key(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        assert "diagnostic" not in r

    def test_invalid_action_summary_first(self):
        r = _error_output("INVALID", "DATA INTEGRITY")
        keys = list(r.keys())
        assert keys[0] == "data_basis"       # PE-42: data_basis before action_summary
        assert keys[1] == "action_summary"

    def test_invalid_with_metrics(self):
        """Data layer INVALID with flat_metrics → groups populated."""
        r = _error_output("INVALID", "DATA INTEGRITY",
                          flat_metrics={"Price": 152.0, "Structural_Floor": 142.0})
        assert r["trade_snapshot"]["current_price"] == 152.0
        assert r["trade_snapshot"]["support"] == 142.0


class TestErrorOutputPreservesMessage:
    """Both paths preserve the full reason string."""

    def test_error_long_message(self):
        msg = "ValueError: Unable to connect to IBKR\nTraceback: ..."
        r = _error_output("ERROR", msg)
        assert r["action_summary"]["reason"] == msg

    def test_invalid_legacy_diagnostic(self):
        msg = "REJECT (reason: DATA INTEGRITY). Insufficient data for SMA computation."
        r = _error_output("INVALID", msg)
        assert r["action_summary"]["reason"] == msg
