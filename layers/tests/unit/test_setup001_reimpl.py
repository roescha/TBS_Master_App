"""SETUP-001 Re-Implementation Tests.

Covers: VS-13 (execution_window timeframe + status),
        VS-14 (trigger-aware entry_price_range),
        VS-17 (entry_zone.desc and reference.desc population),
        VS-09 (profile-aware entry_price_range.desc),
        _flatten() round-trip for new keys.

Run: pytest tests/unit/test_setup001_reimpl.py -v
"""
import pytest
from tbs_engine.transform import _transform_output, _flatten


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action_summary():
    return {
        "verdict": "INVALID",
        "reason": {"label": "TEST", "detail": "Test scaffold."},
        "approaching": False,
        "exit_status": {"active": False, "reason": None},
    }


def _base_metrics(**overrides):
    """Minimal flat_metrics for SETUP-001 entry_zone + execution_window tests."""
    m = {
        "Entry_Reference": 217.0,
        "Pullback_Zone_Upper": 218.94,
        "Window_Reset_Event": "PULLBACK",
        "window_count": 2,
        "Window_Limit": 4,
        "Anchor_Label": "VWAP (Baseline Floor)",
        "Data_Basis": "SWING analysis based on completed bar 09:30-10:30 ET.",
        "Hard_Stop": 207.83,
    }
    m.update(overrides)
    return m


def _get_entry_zone(**overrides):
    r = _transform_output(_action_summary(), _base_metrics(**overrides))
    return r["trade_setup"]["entry_zone"]


def _get_exec_window(**overrides):
    r = _transform_output(_action_summary(), _base_metrics(**overrides))
    return r["trade_setup"]["execution_window"]


# ===========================================================================
# VS-13: execution_window.timeframe + status
# ===========================================================================

class TestVS13_ExecutionWindowTimeframe:
    """execution_window.timeframe derived from Data_Basis profile."""

    def test_profile_a_swing_hour(self):
        ew = _get_exec_window(Data_Basis="SWING analysis based on completed bar 09:30-10:30 ET.")
        assert ew["timeframe"] == "hour"

    def test_profile_b_trend_day(self):
        ew = _get_exec_window(Data_Basis="TREND analysis with data up to 2026-04-04.")
        assert ew["timeframe"] == "day"

    def test_profile_c_wealth_week(self):
        ew = _get_exec_window(Data_Basis="WEALTH analysis with weekly data up to 2026-04-04.")
        assert ew["timeframe"] == "week"

    def test_empty_data_basis_defaults_day(self):
        ew = _get_exec_window(Data_Basis="")
        assert ew["timeframe"] == "day"

    def test_seven_keys_present(self):
        ew = _get_exec_window()
        expected = {"current", "limit", "unit", "timeframe", "status", "reset_event", "desc",
                    "trigger_historical", "trigger_note"}
        assert set(ew.keys()) == expected


class TestVS13_ExecutionWindowStatus:
    """execution_window.status: OPEN when count < limit, EXPIRED when >= limit."""

    def test_open_2_of_4(self):
        ew = _get_exec_window(window_count=2, Window_Limit=4)
        assert ew["status"] == "OPEN"

    def test_expired_4_of_4(self):
        ew = _get_exec_window(window_count=4, Window_Limit=4)
        assert ew["status"] == "EXPIRED"

    def test_expired_5_of_4(self):
        ew = _get_exec_window(window_count=5, Window_Limit=4)
        assert ew["status"] == "EXPIRED"

    def test_open_0_of_4(self):
        ew = _get_exec_window(window_count=0, Window_Limit=4)
        assert ew["status"] == "OPEN"

    def test_open_none_count(self):
        ew = _get_exec_window(window_count=None, Window_Limit=4)
        assert ew["status"] == "OPEN"

    def test_open_none_limit(self):
        ew = _get_exec_window(window_count=2, Window_Limit=None)
        assert ew["status"] == "OPEN"

    def test_expired_3_of_3(self):
        ew = _get_exec_window(window_count=3, Window_Limit=3)
        assert ew["status"] == "EXPIRED"


# ===========================================================================
# VS-14: trigger-aware entry_price_range
# ===========================================================================

class TestVS14_TriggerAwareEntryPriceRange:
    """entry_price_range populated only for PULLBACK trigger."""

    def test_pullback_populated(self):
        ez = _get_entry_zone(Window_Reset_Event="PULLBACK")
        assert ez["entry_price_range"] is not None
        assert ez["entry_price_range"]["lower"] == 217.0
        assert ez["entry_price_range"]["upper"] == 218.94

    def test_breakout_null(self):
        ez = _get_entry_zone(Window_Reset_Event="BREAKOUT")
        assert ez["entry_price_range"] is None

    def test_reclaim_null(self):
        ez = _get_entry_zone(Window_Reset_Event="RECLAIM")
        assert ez["entry_price_range"] is None

    def test_adx_cross_null(self):
        ez = _get_entry_zone(Window_Reset_Event="ADX_CROSS_20")
        assert ez["entry_price_range"] is None

    def test_empty_trigger_null(self):
        ez = _get_entry_zone(Window_Reset_Event="")
        assert ez["entry_price_range"] is None

    def test_compound_pullback_breakout_populated(self):
        """PULLBACK + BREAKOUT: first component is PULLBACK, so range populated."""
        ez = _get_entry_zone(Window_Reset_Event="PULLBACK + BREAKOUT")
        assert ez["entry_price_range"] is not None

    def test_compound_breakout_pullback_null(self):
        """BREAKOUT + PULLBACK: first component is BREAKOUT, so range null."""
        ez = _get_entry_zone(Window_Reset_Event="BREAKOUT + PULLBACK")
        assert ez["entry_price_range"] is None

    def test_trigger_field_preserved(self):
        # BUGR-007 contract update (spec §4.4.4(B), §4.4.6): historical
        # Window_Reset_Event="BREAKOUT" without BRK_Model_Active is the
        # thesis-success + window-expiry fallback path; effective trigger
        # renders as "PULLBACK". Pre-refactor this asserted "BREAKOUT"
        # (the bug symptom). BRK-001-active preservation is tested in
        # TestVS14_TriggerAwareEntryPriceRange::test_breakout_null and in
        # test_bugr007_breakout_hist_fallback.py.
        ez = _get_entry_zone(Window_Reset_Event="BREAKOUT")
        assert ez["trigger"] == "PULLBACK"

    def test_reference_still_populated_on_breakout(self):
        ez = _get_entry_zone(Window_Reset_Event="BREAKOUT")
        assert ez["reference"] is not None
        assert ez["reference"]["price"] == 217.0


# ===========================================================================
# VS-17: entry_zone.desc and reference.desc population
# ===========================================================================

class TestVS17_ReferenceDesc:
    """reference.desc populated per trigger type."""

    def test_pullback_uses_anchor_label(self):
        ez = _get_entry_zone(
            Window_Reset_Event="PULLBACK",
            Anchor_Label="VWAP (Baseline Floor)",
        )
        assert ez["reference"]["desc"] == "VWAP (Baseline Floor)"

    def test_pullback_sma_anchor(self):
        ez = _get_entry_zone(
            Window_Reset_Event="PULLBACK",
            Anchor_Label="50-SMA (Baseline Floor)",
        )
        assert ez["reference"]["desc"] == "50-SMA (Baseline Floor)"

    def test_breakout_resistance_level(self):
        # BUGR-005/007 contract update (spec §4.4.4(B), §4.4.6): the
        # "Resistance level" desc was the bug symptom quoted in spec §4.4.1.
        # Without BRK_Model_Active, the historical BREAKOUT trigger is a
        # fallback path that renders as pullback-frame; reference.desc reads
        # the Entry_Zone_Reference / Anchor_Label value (the structural
        # anchor actually used for R:R, stop, and target).
        ez = _get_entry_zone(Window_Reset_Event="BREAKOUT")
        assert ez["reference"]["desc"] == "VWAP (Baseline Floor)"

    def test_reclaim_structural_floor(self):
        ez = _get_entry_zone(Window_Reset_Event="RECLAIM")
        assert ez["reference"]["desc"] == "Structural floor (reclaim target)"

    def test_no_trigger_empty_desc(self):
        ez = _get_entry_zone(Window_Reset_Event="")
        # No reference when no entry_ref -- but if entry_ref exists with no trigger
        assert ez["reference"] is not None
        assert ez["reference"]["desc"] == ""

    def test_adx_cross_empty_desc(self):
        ez = _get_entry_zone(Window_Reset_Event="ADX_CROSS_20")
        assert ez["reference"]["desc"] == ""


class TestVS17_EntryZoneDesc:
    """entry_zone.desc populated per trigger and profile."""

    def test_pullback_profile_a_hourly(self):
        ez = _get_entry_zone(
            Window_Reset_Event="PULLBACK",
            Data_Basis="SWING analysis based on completed bar 09:30-10:30 ET.",
        )
        assert ez["desc"] == "Close within pullback zone (hourly bar)"

    def test_pullback_profile_b_daily(self):
        ez = _get_entry_zone(
            Window_Reset_Event="PULLBACK",
            Data_Basis="TREND analysis with data up to 2026-04-04.",
        )
        assert ez["desc"] == "Close within pullback zone (daily bar)"

    def test_pullback_profile_c_weekly(self):
        ez = _get_entry_zone(
            Window_Reset_Event="PULLBACK",
            Data_Basis="WEALTH analysis with weekly data up to 2026-04-04.",
        )
        assert ez["desc"] == "Close within pullback zone (weekly bar)"

    def test_breakout_profile_a(self):
        # BUGR-005/007 contract update (spec §4.4.4(B), §4.4.6): BREAKOUT
        # history without BRK_Model_Active = fallback → pullback-frame desc.
        # §4.4.6: 'entry_zone.desc == "Close within pullback zone (hourly bar)"'.
        ez = _get_entry_zone(
            Window_Reset_Event="BREAKOUT",
            Data_Basis="SWING analysis based on completed bar 09:30-10:30 ET.",
        )
        assert ez["desc"] == "Close within pullback zone (hourly bar)"

    def test_breakout_profile_b(self):
        # BUGR-005/007 contract update (spec §4.4.4(B), §4.4.6): fallback
        # path, Profile B → daily bar label.
        ez = _get_entry_zone(
            Window_Reset_Event="BREAKOUT",
            Data_Basis="TREND analysis with data up to 2026-04-04.",
        )
        assert ez["desc"] == "Close within pullback zone (daily bar)"

    def test_breakout_profile_c_empty(self):
        # BUGR-005/007 contract update (spec §4.4.4(B), §4.4.6): fallback
        # path, Profile C → weekly bar label. Pre-refactor the pre-BRK-active
        # BREAKOUT branch suppressed the desc on weekly bar ('"" if weekly');
        # the fallback-to-pullback-frame path has no such suppression and
        # emits the pullback desc consistently across profiles. Test name
        # retained for minimal diff; assertion updated to the new contract.
        ez = _get_entry_zone(
            Window_Reset_Event="BREAKOUT",
            Data_Basis="WEALTH analysis with weekly data up to 2026-04-04.",
        )
        assert ez["desc"] == "Close within pullback zone (weekly bar)"

    def test_reclaim_profile_a(self):
        ez = _get_entry_zone(
            Window_Reset_Event="RECLAIM",
            Data_Basis="SWING analysis based on completed bar 09:30-10:30 ET.",
        )
        assert ez["desc"] == "Close above structural floor (3 bars required)"

    def test_reclaim_profile_b(self):
        ez = _get_entry_zone(
            Window_Reset_Event="RECLAIM",
            Data_Basis="TREND analysis with data up to 2026-04-04.",
        )
        assert ez["desc"] == "Close above structural floor (3 bars required)"

    def test_reclaim_profile_c_empty(self):
        ez = _get_entry_zone(
            Window_Reset_Event="RECLAIM",
            Data_Basis="WEALTH analysis with weekly data up to 2026-04-04.",
        )
        assert ez["desc"] == ""

    def test_no_trigger_empty_desc(self):
        ez = _get_entry_zone(Window_Reset_Event="")
        assert ez["desc"] == ""


# ===========================================================================
# VS-09: profile-aware entry_price_range.desc
# ===========================================================================

class TestVS09_ProfileAwareEPRDesc:
    """entry_price_range.desc varies by profile."""

    def test_profile_a_floor_to_floor(self):
        """AVWAP-001 Phase 3 T6: Profile A uses Daily EMA 21 Action Zone desc."""
        ez = _get_entry_zone(
            Window_Reset_Event="PULLBACK",
            Data_Basis="SWING analysis based on completed bar 09:30-10:30 ET.",
        )
        assert ez["entry_price_range"]["desc"] == "Daily EMA 21 ± 0.5 daily ATR (Action Zone)"

    def test_profile_b_floor_to_ema21(self):
        ez = _get_entry_zone(
            Window_Reset_Event="PULLBACK",
            Data_Basis="TREND analysis with data up to 2026-04-04.",
        )
        assert ez["entry_price_range"]["desc"] == "Floor to EMA 21 + 0.5 ATR"

    def test_profile_c_floor_to_floor(self):
        ez = _get_entry_zone(
            Window_Reset_Event="PULLBACK",
            Data_Basis="WEALTH analysis with weekly data up to 2026-04-04.",
        )
        assert ez["entry_price_range"]["desc"] == "Floor to floor + 0.5 ATR"


# ===========================================================================
# _flatten() round-trip tests
# ===========================================================================

class TestFlattenRoundTrip:
    """_flatten() extracts new and existing keys from grouped output."""

    def _roundtrip(self, **overrides):
        grouped = _transform_output(_action_summary(), _base_metrics(**overrides))
        _, _, flat = _flatten(grouped)
        return flat

    def test_window_timeframe_extracts(self):
        flat = self._roundtrip(Data_Basis="SWING analysis ...")
        assert flat.get("Window_Timeframe") == "hour"

    def test_window_timeframe_day(self):
        flat = self._roundtrip(Data_Basis="TREND analysis ...")
        assert flat.get("Window_Timeframe") == "day"

    def test_window_status_open(self):
        flat = self._roundtrip(window_count=2, Window_Limit=4)
        assert flat.get("Window_Status") == "OPEN"

    def test_window_status_expired(self):
        flat = self._roundtrip(window_count=4, Window_Limit=4)
        assert flat.get("Window_Status") == "EXPIRED"

    def test_existing_window_count(self):
        flat = self._roundtrip(window_count=2)
        assert flat.get("window_count") == 2

    def test_existing_window_limit(self):
        flat = self._roundtrip(Window_Limit=4)
        assert flat.get("Window_Limit") == 4

    def test_existing_window_reset_event(self):
        flat = self._roundtrip(Window_Reset_Event="PULLBACK")
        assert flat.get("Window_Reset_Event") == "PULLBACK"

    def test_existing_entry_reference(self):
        flat = self._roundtrip(Entry_Reference=217.0, Window_Reset_Event="PULLBACK")
        assert flat.get("Entry_Reference") == 217.0

    def test_existing_pullback_zone_upper(self):
        flat = self._roundtrip(
            Pullback_Zone_Upper=218.94,
            Window_Reset_Event="PULLBACK",
        )
        assert flat.get("Pullback_Zone_Upper") == 218.94

    def test_pullback_zone_upper_none_on_breakout(self):
        """VS-14: Pullback_Zone_Upper not recoverable on non-PULLBACK (entry_price_range is None)."""
        flat = self._roundtrip(
            Pullback_Zone_Upper=218.94,
            Window_Reset_Event="BREAKOUT",
        )
        assert flat.get("Pullback_Zone_Upper") is None
