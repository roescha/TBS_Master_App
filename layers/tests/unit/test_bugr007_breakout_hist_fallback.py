"""BUGR-007 — entry_zone breakout-history-without-BRK-active fallback.

When the breakout model confirms (swing_breakout_confirmation.status.label
= CONFIRMED) but the execution window expires without entry, _brk_active
goes False while Breakout_Thesis_Status stays absent / non-FAILED. The
narrow BUGR-005 fix (gated purely on thesis-failure) does not close this
path — only the cleaner-alternative refactor keyed on
(_is_breakout_hist AND NOT _brk_active) does.

Reference: TBS 1E Sprint 1 Batch Spec v1.0 §4.4 (acceptance criteria
§4.4.6), §3.1 (architectural constraint — the narrow BUGR-005 fix in
isolation does not close BUGR-007), §8.1.5 (unit-test contract).
Reference ticker on this path: QXO Profile A C-2 LIVE.
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


def _window_expired_metrics(profile="A"):
    """Profile A construct matching the BUGR-007 reference ticker (QXO):
    historical BREAKOUT trigger, thesis NOT failed, breakout model inactive
    (window expired after confirmation)."""
    m = _make_full_flat_metrics(profile=profile)
    m["Window_Reset_Event"] = "BREAKOUT"
    # Key difference from BUGR-005: thesis did NOT fail on this path.
    m.pop("Breakout_Thesis_Status", None)
    m["BRK_Model_Active"] = False
    m["Engine_State"] = "TRENDING"
    m["Entry_Zone_Reference"] = "EMA 21 (Pullback Anchor)"
    m["Anchor_Label"] = "EMA 21 (Pullback Anchor)"
    m["Data_Basis"] = "SWING analysis based on completed bar 09:30-10:30 ET."
    return m


class TestBUGR007BreakoutHistFallback:
    """BUGR-007: thesis-success + window-expiry → pullback-frame rendering."""

    def test_trigger_renders_as_pullback(self):
        """§4.4.6: entry_zone.trigger == 'PULLBACK' even with thesis non-FAILED."""
        r = _transform_output(_valid_action_summary(), _window_expired_metrics())
        assert r["trade_setup"]["entry_zone"]["trigger"] == "PULLBACK"

    def test_reference_desc_is_structural_anchor(self):
        """§4.4.6: reference.desc is the structural-floor anchor."""
        r = _transform_output(_valid_action_summary(), _window_expired_metrics())
        assert r["trade_setup"]["entry_zone"]["reference"]["desc"] == "EMA 21 (Pullback Anchor)"

    def test_desc_is_pullback_close_profile_a_hourly(self):
        """§4.4.6: desc == 'Close within pullback zone (hourly bar)'."""
        r = _transform_output(_valid_action_summary(), _window_expired_metrics())
        assert r["trade_setup"]["entry_zone"]["desc"] == "Close within pullback zone (hourly bar)"

    def test_thesis_status_non_failed_still_routes_to_fallback(self):
        """Distinct from BUGR-005: thesis-status absent (or anything !=
        'FAILED') must still route to fallback when _brk_active = False
        AND historical trigger was BREAKOUT. This is the discriminating
        test — narrow BUGR-005 fix would fail here."""
        m = _window_expired_metrics()
        m["Breakout_Thesis_Status"] = "PASS"  # any non-FAILED value
        r = _transform_output(_valid_action_summary(), m)
        assert r["trade_setup"]["entry_zone"]["trigger"] == "PULLBACK"
        assert r["trade_setup"]["entry_zone"]["desc"] == "Close within pullback zone (hourly bar)"

    def test_minimum_hold_absent_on_window_expiry(self):
        """Window-expired fallback must not surface minimum_hold."""
        r = _transform_output(_valid_action_summary(), _window_expired_metrics())
        assert "minimum_hold" not in r["trade_setup"]["entry_zone"]


class TestBUGR007BRK001ActiveNonRegression:
    """BRK-001 active case must render unchanged (§4.4.6 non-regression)."""

    def _brk_active_metrics(self):
        m = _make_full_flat_metrics(profile="A")
        m["Window_Reset_Event"] = "BREAKOUT"
        m["BRK_Model_Active"] = True
        m["BRK_New_Support"] = 165.0
        m.pop("Breakout_Thesis_Status", None)
        m["Data_Basis"] = "SWING analysis based on completed bar 09:30-10:30 ET."
        return m

    def test_trigger_remains_breakout(self):
        """BRK-001 active → trigger stays BREAKOUT (§4.4.6 non-regression)."""
        r = _transform_output(_valid_action_summary(), self._brk_active_metrics())
        assert r["trade_setup"]["entry_zone"]["trigger"] == "BREAKOUT"

    def test_reference_desc_is_breakout_evaluation_price(self):
        """§4.4.6 non-regression: reference.desc on BRK-001 active."""
        r = _transform_output(_valid_action_summary(), self._brk_active_metrics())
        assert r["trade_setup"]["entry_zone"]["reference"]["desc"] == (
            "Breakout evaluation price (completed bar close)"
        )

    def test_minimum_hold_populated_from_brk_new_support(self):
        """§4.4.6 non-regression: minimum_hold = BRK_New_Support when active."""
        r = _transform_output(_valid_action_summary(), self._brk_active_metrics())
        assert r["trade_setup"]["entry_zone"]["minimum_hold"] == 165.0

    def test_entry_price_range_nulled_on_brk_active(self):
        """BRK-001: breakout has no bounded zone; entry_price_range = None."""
        r = _transform_output(_valid_action_summary(), self._brk_active_metrics())
        assert r["trade_setup"]["entry_zone"]["entry_price_range"] is None

    def test_desc_contains_hold_above_guidance(self):
        """BRK-001 active with BRK_New_Support → hold-above guidance."""
        r = _transform_output(_valid_action_summary(), self._brk_active_metrics())
        desc = r["trade_setup"]["entry_zone"]["desc"]
        assert "confirmed breakout" in desc
        assert "holds above 165.0" in desc
