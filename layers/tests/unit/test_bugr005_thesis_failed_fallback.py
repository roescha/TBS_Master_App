"""BUGR-005 — entry_zone thesis-failure fallback rendering.

After the BRK-001-GAP-2 thesis guard fires, the breakout model is
deactivated (_brk_active = False) and standard pullback evaluation
produces R:R, stop, and target. Pre-refactor, entry_zone kept rendering
BREAKOUT vocabulary because it keyed off Window_Reset_Event (the
historical trigger). These tests verify the cleaner-alternative refactor
routes thesis-failure cases to pullback-frame rendering.

Reference: TBS 1E Sprint 1 Batch Spec v1.0 §4.4 (acceptance criteria
§4.4.6), §3.1 (architectural constraint), §8.1.4 (unit-test contract).
Reference tickers on this path: REL.L, VWRP.L, RR..L, AAPL (Profile A).
"""

import sys
import os
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'google.genai', 'google'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

from tbs_engine.transform import _transform_output  # noqa: E402

from test_transform_output_diag001 import (  # noqa: E402
    _make_full_flat_metrics,
    _valid_action_summary,
)


def _thesis_failed_metrics(profile="A"):
    """Profile A construct matching the BUGR-005 reference ticker state:
    historical BREAKOUT trigger, thesis has failed, breakout model inactive.
    """
    m = _make_full_flat_metrics(profile=profile)
    m["Window_Reset_Event"] = "BREAKOUT"
    m["Breakout_Thesis_Status"] = "FAILED"
    m["BRK_Model_Active"] = False
    m["Entry_Zone_Reference"] = "EMA 21 (Pullback Anchor)"
    m["Anchor_Label"] = "EMA 21 (Pullback Anchor)"
    # Make Data_Basis unambiguously SWING for Profile A so bar label = hourly.
    m["Data_Basis"] = "SWING analysis based on completed bar 09:30-10:30 ET."
    return m


class TestBUGR005ThesisFailedFallback:
    """BUGR-005: thesis-failure fallback → pullback-frame rendering."""

    def test_trigger_renders_as_pullback(self):
        """§4.4.6: entry_zone.trigger == 'PULLBACK'."""
        r = _transform_output(_valid_action_summary(), _thesis_failed_metrics())
        assert r["trade_setup"]["entry_zone"]["trigger"] == "PULLBACK"

    def test_reference_desc_is_structural_anchor(self):
        """§4.4.6: reference.desc is the Entry_Zone_Reference / Anchor_Label."""
        r = _transform_output(_valid_action_summary(), _thesis_failed_metrics())
        assert r["trade_setup"]["entry_zone"]["reference"]["desc"] == "EMA 21 (Pullback Anchor)"

    def test_desc_is_pullback_close_profile_a_hourly(self):
        """§4.4.6: desc == 'Close within pullback zone (hourly bar)' on Profile A."""
        r = _transform_output(_valid_action_summary(), _thesis_failed_metrics())
        assert r["trade_setup"]["entry_zone"]["desc"] == "Close within pullback zone (hourly bar)"

    def test_reference_price_unchanged(self):
        """§4.4.6: reference.price unchanged (already correct pre-refactor)."""
        m = _thesis_failed_metrics()
        m["Entry_Reference"] = 142.0
        r = _transform_output(_valid_action_summary(), m)
        assert r["trade_setup"]["entry_zone"]["reference"]["price"] == 142.0

    def test_vs14_entry_price_range_suppressed_on_fallback(self):
        """VS-14 guard preserved: entry_price_range only populated on NATIVE
        PULLBACK trigger, not on thesis-failure fallback. Spec §4.4.4(B)."""
        r = _transform_output(_valid_action_summary(), _thesis_failed_metrics())
        assert r["trade_setup"]["entry_zone"]["entry_price_range"] is None

    def test_vs04_inversion_marker_not_applied_on_fallback(self):
        """VS-04 inversion marker is gated on _is_pullback (native), not
        fallback. A fallback path with inverted EMA stack must not get the
        '[INVERTED: EMA structure broken]' suffix because the native-PULLBACK
        bounds contract does not apply. Spec §4.4.4(B)."""
        m = _thesis_failed_metrics()
        m["Entry_Reference"] = 150.0
        m["Pullback_Zone_Upper"] = 145.0  # upper < ref → inverted
        r = _transform_output(_valid_action_summary(), m)
        desc = r["trade_setup"]["entry_zone"]["desc"]
        assert "INVERTED" not in desc
        assert desc == "Close within pullback zone (hourly bar)"

    def test_minimum_hold_absent_on_fallback(self):
        """minimum_hold only applies when BRK-001 is active. Fallback paths
        must not surface it (Spec §4.10 contract preserved)."""
        r = _transform_output(_valid_action_summary(), _thesis_failed_metrics())
        assert "minimum_hold" not in r["trade_setup"]["entry_zone"]
