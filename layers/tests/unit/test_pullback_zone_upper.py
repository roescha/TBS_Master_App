"""Unit tests for Pullback_Zone_Upper metric and transform mapping.

DIAG-001 Phase 2A — §8.6
"""

import pytest
from ibkr_purity_engine import GateResult


class TestPullbackZoneUpperTransformMapping:
    """Pullback_Zone_Upper appears in grouped output under trade_setup.stops."""

    def test_mapped_in_trade_setup_subgroups(self):
        """Pullback_Zone_Upper is listed in _TS_STOPS mapping table."""
        from tbs_engine.transform import _TS_STOPS
        flat_keys = [fk for fk, _ in _TS_STOPS]
        assert "Pullback_Zone_Upper" in flat_keys

    def test_mapped_key_name(self):
        """Pullback_Zone_Upper maps to 'pullback_zone_upper' in grouped output."""
        from tbs_engine.transform import _TS_STOPS
        mapping = {fk: gk for fk, gk in _TS_STOPS}
        assert mapping["Pullback_Zone_Upper"] == "pullback_zone_upper"

    def test_in_mapped_flat_keys(self):
        """Pullback_Zone_Upper in MAPPED_FLAT_KEYS (no unmapped audit warning)."""
        from tbs_engine.transform import MAPPED_FLAT_KEYS
        assert "Pullback_Zone_Upper" in MAPPED_FLAT_KEYS

    def test_setup_total_includes_new_key(self):
        """_SETUP_TOTAL count updated to include Pullback_Zone_Upper."""
        from tbs_engine.transform import _TRADE_SETUP_SUBGROUPS
        total = sum(len(t) for _, t in _TRADE_SETUP_SUBGROUPS)
        assert total == 33  # was 32, +1 for Pullback_Zone_Upper

    def test_transform_output_places_in_stops(self):
        """_transform_output places Pullback_Zone_Upper in trade_setup.stops."""
        from tbs_engine.transform import _transform_output

        # Minimal metrics dict with just enough keys for transform
        flat_metrics = {
            "Pullback_Zone_Upper": 189.30,
        }
        # _transform_output requires status and diagnostic
        result = _transform_output("HALT", "WAIT ...", flat_metrics, debug=False)
        # Check the value landed in the right group
        stops = result.get("trade_setup", {}).get("stops", {})
        assert stops.get("pullback_zone_upper") == 189.30

    def test_flatten_roundtrip(self):
        """_flatten correctly recovers Pullback_Zone_Upper from grouped output."""
        from tbs_engine.transform import _transform_output, _flatten

        flat_metrics = {"Pullback_Zone_Upper": 192.50}
        grouped = _transform_output("HALT", "WAIT ...", flat_metrics, debug=False)
        status, diag, recovered = _flatten(grouped)
        assert recovered.get("Pullback_Zone_Upper") == 192.50
