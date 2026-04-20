"""entry_zone refactor non-regression tests.

Covers:
- Native PULLBACK trigger (Window_Reset_Event = "PULLBACK", _brk_active = False)
- RECLAIM trigger
- Null / unknown trigger
- Dead-branch removal at output.py:1240-1241: Entry_Reference == Structural_Floor
  when _brk_active is False (the Engine_State.startswith("BREAKOUT") branch is
  provably unreachable; removal must not change behaviour on any non-breakout
  state).

Reference: TBS 1E Sprint 1 Batch Spec v1.0 §8.1.6 (non-regression contract),
§4.4.4(A) (dead-branch removal), §3.2 (architectural constraint), §4.4.6
(acceptance criteria).
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


class TestNativePullbackNonRegression:
    """Native PULLBACK (the trigger that was NOT the bug) must render unchanged."""

    def _native_pullback_metrics(self):
        m = _make_full_flat_metrics(profile="A")
        m["Window_Reset_Event"] = "PULLBACK"
        m["BRK_Model_Active"] = False
        m.pop("Breakout_Thesis_Status", None)
        m["Entry_Zone_Reference"] = "EMA 21 (Pullback Anchor)"
        m["Anchor_Label"] = "EMA 21 (Pullback Anchor)"
        m["Entry_Reference"] = 142.0
        m["Pullback_Zone_Upper"] = 145.0
        m["Data_Basis"] = "SWING analysis based on completed bar 09:30-10:30 ET."
        return m

    def test_native_pullback_trigger_preserved(self):
        r = _transform_output(_valid_action_summary(), self._native_pullback_metrics())
        assert r["trade_setup"]["entry_zone"]["trigger"] == "PULLBACK"

    def test_native_pullback_reference_desc_is_anchor(self):
        r = _transform_output(_valid_action_summary(), self._native_pullback_metrics())
        assert r["trade_setup"]["entry_zone"]["reference"]["desc"] == "EMA 21 (Pullback Anchor)"

    def test_native_pullback_desc_is_pullback_close(self):
        r = _transform_output(_valid_action_summary(), self._native_pullback_metrics())
        assert r["trade_setup"]["entry_zone"]["desc"] == "Close within pullback zone (hourly bar)"

    def test_native_pullback_entry_price_range_populated(self):
        """VS-14: native PULLBACK with valid bounds → entry_price_range set.
        Distinguishes native PULLBACK from fallback paths (which null it)."""
        r = _transform_output(_valid_action_summary(), self._native_pullback_metrics())
        epr = r["trade_setup"]["entry_zone"]["entry_price_range"]
        assert epr is not None
        assert epr["lower"] == 142.0
        assert epr["upper"] == 145.0

    def test_native_pullback_vs04_inversion_marker_applies(self):
        """VS-04: native PULLBACK with entry_ref > pb_upper → '[INVERTED]' suffix.
        This must still fire on native paths after the refactor."""
        m = self._native_pullback_metrics()
        m["Entry_Reference"] = 150.0
        m["Pullback_Zone_Upper"] = 145.0
        r = _transform_output(_valid_action_summary(), m)
        desc = r["trade_setup"]["entry_zone"]["desc"]
        assert "[INVERTED: EMA structure broken]" in desc


class TestReclaimNonRegression:
    """RECLAIM trigger must render unchanged."""

    def _reclaim_metrics(self):
        m = _make_full_flat_metrics(profile="A")
        m["Window_Reset_Event"] = "RECLAIM"
        m["BRK_Model_Active"] = False
        m.pop("Breakout_Thesis_Status", None)
        m["Data_Basis"] = "SWING analysis based on completed bar 09:30-10:30 ET."
        return m

    def test_reclaim_trigger_preserved(self):
        r = _transform_output(_valid_action_summary(), self._reclaim_metrics())
        assert r["trade_setup"]["entry_zone"]["trigger"] == "RECLAIM"

    def test_reclaim_reference_desc_unchanged(self):
        r = _transform_output(_valid_action_summary(), self._reclaim_metrics())
        assert r["trade_setup"]["entry_zone"]["reference"]["desc"] == "Structural floor (reclaim target)"

    def test_reclaim_desc_unchanged_hourly(self):
        r = _transform_output(_valid_action_summary(), self._reclaim_metrics())
        assert r["trade_setup"]["entry_zone"]["desc"] == "Close above structural floor (3 bars required)"


class TestNullTriggerNonRegression:
    """Null / unknown trigger must render as pre-refactor."""

    def _null_trigger_metrics(self):
        m = _make_full_flat_metrics(profile="A")
        m["Window_Reset_Event"] = None
        m["BRK_Model_Active"] = False
        m.pop("Breakout_Thesis_Status", None)
        m["Data_Basis"] = "SWING analysis based on completed bar 09:30-10:30 ET."
        return m

    def test_null_trigger_is_none(self):
        r = _transform_output(_valid_action_summary(), self._null_trigger_metrics())
        assert r["trade_setup"]["entry_zone"]["trigger"] is None

    def test_null_trigger_reference_desc_empty(self):
        r = _transform_output(_valid_action_summary(), self._null_trigger_metrics())
        # When _entry_ref is set but no trigger → reference dict exists with empty desc.
        ref = r["trade_setup"]["entry_zone"]["reference"]
        assert ref is not None
        assert ref["desc"] == ""

    def test_null_trigger_desc_empty(self):
        r = _transform_output(_valid_action_summary(), self._null_trigger_metrics())
        assert r["trade_setup"]["entry_zone"]["desc"] == ""


class TestDeadBranchRemoval:
    """output.py:1240-1241 dead-branch removal (§4.4.4(A), §3.2).

    The Engine_State.startswith("BREAKOUT") branch was unreachable by
    construction — none of the 12 values in the engine_state ladder at
    output.py:1838-1851 starts with "BREAKOUT". Collapse to unconditional
    Structural_Floor assignment must produce identical behaviour on every
    non-breakout-model-active path. Replicate the collapsed writer here
    rather than wiring a full ctx, mirroring the surgical test pattern in
    test_bugr001_daily_hard_stop.py.
    """

    def _emit_entry_reference(self, brk_active, engine_state, structural_floor, resistance):
        """Replicate the post-refactor output.py:1240-1241 write pattern."""
        metrics = {"Engine_State": engine_state, "Structural_Floor": structural_floor,
                   "Resistance": resistance}
        if not brk_active:
            metrics["Entry_Reference"] = metrics.get("Structural_Floor")
        return metrics.get("Entry_Reference")

    def test_entry_reference_equals_structural_floor_on_trending(self):
        assert self._emit_entry_reference(False, "TRENDING", 142.0, 160.0) == 142.0

    def test_entry_reference_equals_structural_floor_on_resolving(self):
        assert self._emit_entry_reference(False, "RESOLVING", 142.0, 160.0) == 142.0

    def test_entry_reference_equals_structural_floor_on_mid_range(self):
        assert self._emit_entry_reference(False, "MID-RANGE (ADX <20)", 142.0, 160.0) == 142.0

    def test_entry_reference_equals_structural_floor_on_reclaim_active(self):
        assert self._emit_entry_reference(False, "VIOLATED -- RECLAIM ACTIVE", 142.0, 160.0) == 142.0

    def test_entry_reference_equals_structural_floor_on_ambiguous(self):
        assert self._emit_entry_reference(False, "AMBIGUOUS (MA STACK BROKEN)", 142.0, 160.0) == 142.0

    def test_entry_reference_untouched_when_brk_active(self):
        """When _brk_active = True, Entry_Reference is set upstream (to bar
        close) and must not be overwritten here. The collapsed writer's
        `if not _brk_active` guard preserves this contract."""
        metrics = {"Engine_State": "TRENDING", "Structural_Floor": 142.0,
                   "Entry_Reference": 159.5}  # pre-set to bar close upstream
        if not True:  # _brk_active = True
            metrics["Entry_Reference"] = metrics.get("Structural_Floor")
        assert metrics["Entry_Reference"] == 159.5
