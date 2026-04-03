"""DIAG-001 Phase 2B: _flatten reverse-transform tests.

Verifies:
- Reverse-transform reads action_summary.verdict → maps VALID→PASS, INVALID→HALT, ERROR→ERROR
- entry_strategy extracted from action_summary, not trade_snapshot
- Best-effort diagnostic string reconstructed from reason + context + mandate

Spec: DIAG_001_Action_Summary_Spec_v1_0.md
Prompt: DIAG_001_Phase_2B_Implementation_Prompt.md §8.9
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _transform_output, _flatten, _error_output


class TestFlattenVerdictMapping:
    """Verdict → legacy status mapping."""

    def test_valid_maps_to_pass(self):
        r = _transform_output({"verdict": "VALID", "reason": "PULLBACK"}, {})
        status, _, _ = _flatten(r)
        assert status == "PASS"

    def test_invalid_maps_to_halt(self):
        r = _transform_output({"verdict": "INVALID", "reason": "EXTENDED",
                                "approaching": False, "action": "WAIT.", "context": "Test."}, {})
        status, _, _ = _flatten(r)
        assert status == "HALT"

    def test_error_maps_to_error(self):
        r = _error_output("ERROR", "test")
        status, _, _ = _flatten(r)
        assert status == "ERROR"


class TestFlattenDiagnosticReconstruction:
    """Best-effort diagnostic from action_summary fields."""

    def test_diagnostic_contains_reason(self):
        r = _transform_output({"verdict": "INVALID", "reason": "EXTENDED",
                                "approaching": False, "action": "WAIT.",
                                "context": "2.35 ATR above limit."}, {})
        _, diag, _ = _flatten(r)
        assert "EXTENDED" in diag

    def test_diagnostic_contains_context(self):
        r = _transform_output({"verdict": "INVALID", "reason": "EXTENDED",
                                "approaching": False, "action": "WAIT.",
                                "context": "2.35 ATR above limit."}, {})
        _, diag, _ = _flatten(r)
        assert "2.35 ATR above limit" in diag

    def test_diagnostic_contains_mandate(self):
        r = _transform_output({"verdict": "INVALID", "reason": "EXTENDED",
                                "approaching": False, "action": "WAIT.",
                                "context": "2.35 ATR above limit."}, {})
        _, diag, _ = _flatten(r)
        assert "WAIT" in diag


class TestFlattenEntryStrategy:
    """entry_strategy extracted from action_summary, not trade_snapshot."""

    def test_entry_reference_from_action_summary(self):
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        }
        r = _transform_output(a, {"Price": 152.0, "Structural_Floor": 142.0,
                                   "Hard_Stop": 140.0, "Profit_Target": 160.0})
        _, _, flat = _flatten(r)
        assert flat["Entry_Reference"] == 142.0

    def test_hard_stop_from_action_summary(self):
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        }
        r = _transform_output(a, {"Hard_Stop": 140.0, "Profit_Target": 160.0})
        _, _, flat = _flatten(r)
        assert flat["Hard_Stop"] == 140.0

    def test_profit_target_from_action_summary(self):
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        }
        r = _transform_output(a, {"Hard_Stop": 140.0, "Profit_Target": 160.0})
        _, _, flat = _flatten(r)
        assert flat["Profit_Target"] == 160.0

    def test_no_entry_strategy_on_invalid(self):
        a = {"verdict": "INVALID", "reason": "EXTENDED", "approaching": False,
             "action": "WAIT.", "context": "Test."}
        r = _transform_output(a, {})
        _, _, flat = _flatten(r)
        assert "Entry_Reference" not in flat

    def test_action_summary_entry_strategy_overrides_trade_setup(self):
        """action_summary entry_strategy values take precedence."""
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "entry_strategy": {"entry_price": 999.0, "stop_loss": 998.0, "target": 1000.0},
        }
        # trade_setup will have different values from flat_metrics
        r = _transform_output(a, {"Hard_Stop": 140.0, "Profit_Target": 160.0, "Entry_Reference": 142.0})
        _, _, flat = _flatten(r)
        # action_summary values override trade_setup values
        assert flat["Entry_Reference"] == 999.0
        assert flat["Hard_Stop"] == 998.0
        assert flat["Profit_Target"] == 1000.0


class TestFlattenRoundTrip:
    """Round-trip through _transform_output → _flatten preserves key metrics."""

    def test_roundtrip_metrics(self):
        a = {
            "verdict": "VALID", "reason": "PULLBACK",
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        }
        flat_in = {
            "Price": 152.0, "Structural_Floor": 142.0, "Resistance": 160.0,
            "ADV_20": 5000000.0, "ADV_20_Dollar": 50000000.0, "Is_ETF": False, "Convexity_Class": "C1",
            "Engine_State": "TRENDING", "ADX": 28.5,
            "EMA_8": 150.0, "Hard_Stop": 140.0, "Profit_Target": 160.0,
            "Entry_Reference": 142.0,
        }
        r = _transform_output(a, flat_in)
        _, _, flat_out = _flatten(r)
        assert flat_out["Engine_State"] == "TRENDING"
        assert flat_out["ADX"] == 28.5
        assert flat_out["EMA_8"] == 150.0
        assert flat_out["Price"] == 152.0
        assert flat_out["Entry_Reference"] == 142.0
