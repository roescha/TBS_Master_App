"""Unit tests for GateResult NamedTuple.

DIAG-001 Phase 2A — §8.1
"""

import pytest
from ibkr_purity_engine import GateResult


class TestGateResultConstruction:
    """GateResult construction with all fields and defaults."""

    def test_full_construction(self):
        """All fields provided explicitly."""
        g = GateResult(
            verdict="VALID",
            reason="PULLBACK",
            mandate="Execute at THIS bar's close.",
            context="Price in pullback zone.",
            legacy_diagnostic="PRE-APPROVED (entry: PULLBACK ...)",
            entry_type="PULLBACK",
            trigger_rule="BAR CLOSE ONLY",
            state="TRENDING",
        )
        assert g.verdict == "VALID"
        assert g.reason == "PULLBACK"
        assert g.mandate == "Execute at THIS bar's close."
        assert g.context == "Price in pullback zone."
        assert g.legacy_diagnostic == "PRE-APPROVED (entry: PULLBACK ...)"
        assert g.entry_type == "PULLBACK"
        assert g.trigger_rule == "BAR CLOSE ONLY"
        assert g.state == "TRENDING"

    def test_construction_with_defaults(self):
        """Only required fields — optional fields default to None."""
        g = GateResult(
            verdict="INVALID",
            reason="FLOOR WARNING",
            mandate="WAIT.",
            context="Floor warning active.",
        )
        assert g.verdict == "INVALID"
        assert g.reason == "FLOOR WARNING"
        assert g.legacy_diagnostic is None
        assert g.entry_type is None
        assert g.trigger_rule is None
        assert g.state is None

    def test_field_access_by_name(self):
        """All fields accessible by attribute name."""
        g = GateResult(
            verdict="INVALID",
            reason="EXTENDED",
            mandate="WAIT.",
            context="Extended.",
            legacy_diagnostic="WAIT (reason: EXTENDED)...",
        )
        assert g.verdict == "INVALID"
        assert g.reason == "EXTENDED"
        assert g.mandate == "WAIT."
        assert g.context == "Extended."
        assert g.legacy_diagnostic == "WAIT (reason: EXTENDED)..."

    def test_truthiness(self):
        """Non-None GateResult instance is truthy (supports `or` pattern)."""
        g = GateResult(
            verdict="INVALID",
            reason="TEST",
            mandate="m",
            context="c",
        )
        assert bool(g) is True
        assert g  # truthy

    def test_or_pattern_with_none(self):
        """None or GateResult returns GateResult (cascade `or` shorthand)."""
        g = GateResult(
            verdict="INVALID",
            reason="TEST",
            mandate="m",
            context="c",
        )
        result = None or g
        assert result is g
        assert result.verdict == "INVALID"

    def test_or_pattern_first_wins(self):
        """First GateResult wins in `or` chain (short-circuit)."""
        g1 = GateResult(verdict="INVALID", reason="FIRST", mandate="m1", context="c1")
        g2 = GateResult(verdict="INVALID", reason="SECOND", mandate="m2", context="c2")
        result = g1 or g2
        assert result is g1
        assert result.reason == "FIRST"

    def test_legacy_diagnostic_preserved(self):
        """legacy_diagnostic field carries the exact old diagnostic string."""
        old_diag = "REJECT (reason: LIQUIDITY FAILED). Liquidity Failed (EQUITY): $0.5M (Req >$5M)"
        g = GateResult(
            verdict="INVALID",
            reason="LIQUIDITY FAILED",
            mandate="Liquidity insufficient.",
            context="Liquidity Failed (EQUITY).",
            legacy_diagnostic=old_diag,
        )
        assert g.legacy_diagnostic == old_diag

    def test_valid_path_fields(self):
        """VALID path carries entry_type, trigger_rule, state."""
        g = GateResult(
            verdict="VALID",
            reason="RECLAIM",
            mandate="Execute.",
            context="Reclaimed.",
            legacy_diagnostic="PRE-APPROVED ...",
            entry_type="RECLAIM",
            trigger_rule="BAR CLOSE ONLY",
            state="TRENDING",
        )
        assert g.entry_type == "RECLAIM"
        assert g.trigger_rule == "BAR CLOSE ONLY"
        assert g.state == "TRENDING"

    def test_invalid_path_no_valid_fields(self):
        """INVALID path: entry_type, trigger_rule, state are None."""
        g = GateResult(
            verdict="INVALID",
            reason="FLOOR WARNING",
            mandate="WAIT.",
            context="Floor warning.",
            legacy_diagnostic="WAIT ...",
        )
        assert g.entry_type is None
        assert g.trigger_rule is None
        assert g.state is None

    def test_named_tuple_immutability(self):
        """GateResult is immutable (NamedTuple)."""
        g = GateResult(verdict="INVALID", reason="TEST", mandate="m", context="c")
        with pytest.raises(AttributeError):
            g.verdict = "VALID"

    def test_fields_tuple(self):
        """GateResult has exactly 8 fields in spec order."""
        expected = ('verdict', 'reason', 'mandate', 'context',
                    'legacy_diagnostic', 'entry_type', 'trigger_rule', 'state')
        assert GateResult._fields == expected
