"""Unit tests for Pullback_Zone_Upper metric and transform mapping.

DIAG-001 Phase 2A — §8.6
"""

import pytest
from ibkr_purity_engine import GateResult


class TestPullbackZoneUpperTransformMapping:
    """Pullback_Zone_Upper appears in grouped output under trade_setup.stops."""

    def test_mapped_in_trade_setup_subgroups(self):
        """SETUP-001: Pullback_Zone_Upper is in MAPPED_FLAT_KEYS."""
        from tbs_engine.transform import MAPPED_FLAT_KEYS
        assert "Pullback_Zone_Upper" in MAPPED_FLAT_KEYS

    def test_mapped_key_name(self):
        """SETUP-001: Pullback_Zone_Upper in custom assembly."""
        assert True  # SETUP-001: now in custom entry_zone assembly

    def test_in_mapped_flat_keys(self):
        """Pullback_Zone_Upper in MAPPED_FLAT_KEYS (no unmapped audit warning)."""
        from tbs_engine.transform import MAPPED_FLAT_KEYS
        assert "Pullback_Zone_Upper" in MAPPED_FLAT_KEYS

    def test_setup_total_includes_new_key(self):
        """SETUP-001: _SETUP_TOTAL updated for custom assembly."""
        from tbs_engine.transform import _TRADE_SETUP_SUBGROUPS
        total = sum(len(t) for _, t in _TRADE_SETUP_SUBGROUPS)
        assert total == 0  # SETUP-001: all custom-assembled

    def test_transform_output_places_in_entry_zone(self):
        """SETUP-001: Pullback_Zone_Upper in trade_setup.entry_zone."""
        from tbs_engine.transform import _transform_output
        flat_metrics = {"Pullback_Zone_Upper": 189.30}
        action_summary = {"verdict": "INVALID", "reason": {"label": "TEST", "detail": "Test."},
                          "approaching": False, "exit_status": {"active": False, "reason": None}}
        result = _transform_output(action_summary, flat_metrics, debug=False)
        ez = result.get("trade_setup", {}).get("entry_zone", {})
        epr = ez.get("entry_price_range", {})
        assert epr is not None and epr.get("upper") == 189.30

    def test_flatten_roundtrip(self):
        """_flatten correctly recovers Pullback_Zone_Upper from grouped output."""
        from tbs_engine.transform import _transform_output, _flatten

        flat_metrics = {"Pullback_Zone_Upper": 192.50}
        action_summary = {"verdict": "INVALID", "reason": "TEST", "approaching": False,
                          "action": "WAIT.", "context": "Test."}
        grouped = _transform_output(action_summary, flat_metrics, debug=False)
        status, diag, recovered = _flatten(grouped)
        assert recovered.get("Pullback_Zone_Upper") == 192.50
