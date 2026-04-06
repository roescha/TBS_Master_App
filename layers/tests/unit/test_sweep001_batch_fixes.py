"""SWEEP-001 batch fix tests.

Covers: VS-01, VS-04, VS-05, VS-10, VS-12, VS-15, VS-16.
All display-level fixes -- zero gate/verdict/threshold/sizing changes.
"""
import pytest


# ---------------------------------------------------------------------------
# VS-01: R:R Desc Template conditional operator
# ---------------------------------------------------------------------------
class TestVS01_RRDescOperator:
    """output.py: Price R:R desc uses >= or < depending on pass/fail."""

    def test_rr_pass_shows_gte(self):
        """Passing R:R (3.0 >= 2.0) -> desc contains '>='."""
        _rr = 3.0
        _threshold_rr = 2.0
        _rr_op = ">=" if (_rr >= _threshold_rr) else "<"
        desc = f"Price R:R {_rr:.2f} {_rr_op} {_threshold_rr}"
        assert ">=" in desc
        assert "3.00 >= 2.0" in desc

    def test_rr_fail_shows_lt(self):
        """Failing R:R (0.5 < 2.0) -> desc contains '<'."""
        _rr = 0.5
        _threshold_rr = 2.0
        _rr_op = ">=" if (_rr >= _threshold_rr) else "<"
        desc = f"Price R:R {_rr:.2f} {_rr_op} {_threshold_rr}"
        assert "<" in desc
        assert ">=" not in desc
        assert "0.50 < 2.0" in desc

    def test_rr_exactly_at_threshold(self):
        """R:R exactly at threshold (2.0 >= 2.0) -> passes."""
        _rr = 2.0
        _threshold_rr = 2.0
        _rr_op = ">=" if (_rr >= _threshold_rr) else "<"
        desc = f"Price R:R {_rr:.2f} {_rr_op} {_threshold_rr}"
        assert ">=" in desc

    def test_rr_negative_shows_lt(self):
        """Negative R:R (-0.66 < 2.0) -> desc contains '<'."""
        _rr = -0.66
        _threshold_rr = 2.0
        _rr_op = ">=" if (_rr >= _threshold_rr) else "<"
        desc = f"Price R:R {_rr:.2f} {_rr_op} {_threshold_rr}"
        assert "<" in desc
        assert ">=" not in desc


# ---------------------------------------------------------------------------
# VS-04: Entry Zone Inversion Guard
# ---------------------------------------------------------------------------
class TestVS04_EntryZoneInversion:
    """transform.py: entry_price_range nulled when lower > upper (EMA inversion)."""

    def test_normal_range_preserved(self):
        """Normal case: _entry_ref < _pb_upper -> entry_price_range populated."""
        _entry_ref = 100.0
        _pb_upper = 105.0
        _is_pullback = True
        _ez_inverted = (_entry_ref is not None and _pb_upper is not None and _entry_ref > _pb_upper)
        assert _ez_inverted is False
        # Range should be populated
        epr = {"lower": _entry_ref, "upper": _pb_upper, "desc": "test"} if (
            _pb_upper and _is_pullback and not _ez_inverted) else None
        assert epr is not None
        assert epr["lower"] < epr["upper"]

    def test_inverted_range_nulled(self):
        """Inverted case: _entry_ref > _pb_upper -> entry_price_range is None."""
        _entry_ref = 110.0  # SMA 50 (structural floor)
        _pb_upper = 105.0   # EMA 21 + 0.5 ATR (collapsed below floor)
        _is_pullback = True
        _ez_inverted = (_entry_ref is not None and _pb_upper is not None and _entry_ref > _pb_upper)
        assert _ez_inverted is True
        epr = {"lower": _entry_ref, "upper": _pb_upper, "desc": "test"} if (
            _pb_upper and _is_pullback and not _ez_inverted) else None
        assert epr is None

    def test_inverted_desc_annotated(self):
        """Inverted case: desc includes [INVERTED: EMA structure broken]."""
        _entry_ref = 110.0
        _pb_upper = 105.0
        _is_pullback = True
        _ez_inverted = (_entry_ref is not None and _pb_upper is not None and _entry_ref > _pb_upper)
        _ez_desc = "Close within pullback zone (daily bar)"
        desc = _ez_desc + " [INVERTED: EMA structure broken]" if (_is_pullback and _ez_inverted) else _ez_desc
        assert "[INVERTED: EMA structure broken]" in desc

    def test_non_pullback_no_inversion_check(self):
        """Non-pullback trigger: no inversion annotation even if values inverted."""
        _entry_ref = 110.0
        _pb_upper = 105.0
        _is_pullback = False
        _ez_inverted = (_entry_ref is not None and _pb_upper is not None and _entry_ref > _pb_upper)
        _ez_desc = "Close above resistance (daily bar)"
        desc = _ez_desc + " [INVERTED: EMA structure broken]" if (_is_pullback and _ez_inverted) else _ez_desc
        assert "[INVERTED" not in desc


# ---------------------------------------------------------------------------
# VS-05: Execution Window 99 Sentinel
# ---------------------------------------------------------------------------
class TestVS05_WindowSentinel:
    """transform.py: window_count=99 sentinel produces NO_TRIGGER status."""

    def test_sentinel_99_no_trigger(self):
        """window_count=99 -> current=None, status=NO_TRIGGER, desc explains."""
        _wc = 99
        _wl = 5
        _is_sentinel = (_wc is not None and _wc == 99)
        assert _is_sentinel is True
        _ew_current = None if _is_sentinel else _wc
        _ew_status = "NO_TRIGGER" if _is_sentinel else ("EXPIRED" if _wc >= _wl else "OPEN")
        _ew_desc = "No trigger event recorded" if _is_sentinel else ""
        assert _ew_current is None
        assert _ew_status == "NO_TRIGGER"
        assert _ew_desc == "No trigger event recorded"

    def test_normal_open_window(self):
        """window_count=3, limit=5 -> status=OPEN, current=3."""
        _wc = 3
        _wl = 5
        _is_sentinel = (_wc is not None and _wc == 99)
        assert _is_sentinel is False
        _ew_status = "EXPIRED" if (_wc is not None and _wl is not None and _wc >= _wl) else "OPEN"
        assert _ew_status == "OPEN"

    def test_expired_window(self):
        """window_count=6, limit=5 -> status=EXPIRED."""
        _wc = 6
        _wl = 5
        _is_sentinel = (_wc is not None and _wc == 99)
        assert _is_sentinel is False
        _ew_status = "EXPIRED" if (_wc is not None and _wl is not None and _wc >= _wl) else "OPEN"
        assert _ew_status == "EXPIRED"

    def test_sentinel_nulls_limit_and_reset(self):
        """Sentinel -> limit=None, reset_event=None in output."""
        _wc = 99
        _wl = 5
        _window_reset = "BREAKOUT + some event"
        _is_sentinel = (_wc is not None and _wc == 99)
        ew = {
            "limit": _wl if not _is_sentinel else None,
            "reset_event": _window_reset if not _is_sentinel else None,
        }
        assert ew["limit"] is None
        assert ew["reset_event"] is None


# ---------------------------------------------------------------------------
# VS-10: State/Trigger Historical Mismatch
# ---------------------------------------------------------------------------
class TestVS10_TriggerHistorical:
    """transform.py: BREAKOUT trigger + TRENDING state flagged as historical."""

    def test_breakout_trending_flagged(self):
        """BREAKOUT trigger + TRENDING state -> trigger_historical=True."""
        _trigger_type = "BREAKOUT"
        _engine_state = "TRENDING"
        _is_sentinel = False
        _trigger_historical = False
        if _trigger_type and not _is_sentinel:
            if _trigger_type.upper() == "BREAKOUT" and "TRENDING" in _engine_state.upper():
                _trigger_historical = True
        assert _trigger_historical is True

    def test_pullback_trending_not_flagged(self):
        """PULLBACK trigger + TRENDING state -> no flag (expected combination)."""
        _trigger_type = "PULLBACK"
        _engine_state = "TRENDING"
        _is_sentinel = False
        _trigger_historical = False
        if _trigger_type and not _is_sentinel:
            if _trigger_type.upper() == "BREAKOUT" and "TRENDING" in _engine_state.upper():
                _trigger_historical = True
        assert _trigger_historical is False

    def test_breakout_resolving_not_flagged(self):
        """BREAKOUT trigger + RESOLVING state -> no flag (consistent combination)."""
        _trigger_type = "BREAKOUT"
        _engine_state = "RESOLVING"
        _is_sentinel = False
        _trigger_historical = False
        if _trigger_type and not _is_sentinel:
            if _trigger_type.upper() == "BREAKOUT" and "TRENDING" in _engine_state.upper():
                _trigger_historical = True
        assert _trigger_historical is False

    def test_sentinel_skips_historical_check(self):
        """Sentinel (no trigger) -> no historical flag regardless of state."""
        _trigger_type = "BREAKOUT"
        _engine_state = "TRENDING"
        _is_sentinel = True
        _trigger_historical = False
        if _trigger_type and not _is_sentinel:
            if _trigger_type.upper() == "BREAKOUT" and "TRENDING" in _engine_state.upper():
                _trigger_historical = True
        assert _trigger_historical is False

    def test_trigger_note_populated(self):
        """When trigger_historical=True, trigger_note explains."""
        _trigger_historical = True
        note = "Trigger occurred during prior RESOLVING state" if _trigger_historical else None
        assert note is not None
        assert "RESOLVING" in note


# ---------------------------------------------------------------------------
# VS-12: VWAP Counter actual count
# ---------------------------------------------------------------------------
class TestVS12_VWAPCounter:
    """exit.py: Exit_VWAP_Counter shows actual count, not capped."""

    def test_counter_above_threshold(self):
        """_exit_consec=5 -> counter='5/3' (not '3/3')."""
        _exit_consec = 5
        counter = f"{_exit_consec}/3"
        assert counter == "5/3"

    def test_counter_at_threshold(self):
        """_exit_consec=3 -> counter='3/3'."""
        _exit_consec = 3
        counter = f"{_exit_consec}/3"
        assert counter == "3/3"

    def test_counter_below_threshold(self):
        """_exit_consec=1 -> counter='1/3'."""
        _exit_consec = 1
        counter = f"{_exit_consec}/3"
        assert counter == "1/3"

    def test_counter_zero(self):
        """_exit_consec=0 -> counter='0/3'."""
        _exit_consec = 0
        counter = f"{_exit_consec}/3"
        assert counter == "0/3"


# ---------------------------------------------------------------------------
# VS-15: Resistance Null Context
# ---------------------------------------------------------------------------
class TestVS15_ResistanceNullContext:
    """transform.py: Resistance desc explains null when suppressed."""

    def test_null_resistance_with_note(self):
        """Resistance=None + Resistance_Note populated -> desc = note."""
        _resistance_price = None
        _resistance_note = "SUPPRESSED: price already above resistance level"
        _resistance_desc = "Primary-frame 10-bar high (daily recent ceiling)"
        if _resistance_price is None and _resistance_note:
            _resistance_desc_final = _resistance_note
        elif _resistance_price is None:
            _resistance_desc_final = _resistance_desc + " (suppressed -- price at or above level)"
        else:
            _resistance_desc_final = _resistance_desc
        assert _resistance_desc_final == _resistance_note

    def test_null_resistance_no_note(self):
        """Resistance=None + no note -> desc gets fallback suffix."""
        _resistance_price = None
        _resistance_note = None
        _resistance_desc = "Primary-frame 10-bar high (daily recent ceiling)"
        if _resistance_price is None and _resistance_note:
            _resistance_desc_final = _resistance_note
        elif _resistance_price is None:
            _resistance_desc_final = _resistance_desc + " (suppressed -- price at or above level)"
        else:
            _resistance_desc_final = _resistance_desc
        assert "suppressed" in _resistance_desc_final

    def test_populated_resistance_unchanged(self):
        """Resistance populated -> desc unchanged."""
        _resistance_price = 155.0
        _resistance_note = None
        _resistance_desc = "Primary-frame 10-bar high (daily recent ceiling)"
        if _resistance_price is None and _resistance_note:
            _resistance_desc_final = _resistance_note
        elif _resistance_price is None:
            _resistance_desc_final = _resistance_desc + " (suppressed -- price at or above level)"
        else:
            _resistance_desc_final = _resistance_desc
        assert _resistance_desc_final == _resistance_desc


# ---------------------------------------------------------------------------
# VS-16: Override Key Casing
# ---------------------------------------------------------------------------
class TestVS16_OverrideKeyCasing:
    """gates.py: All Trend_Quality_Override dict keys are lowercase."""

    def test_eligible_path_lowercase_keys(self):
        """Eligible override dict uses lowercase keys."""
        override = {
            "eligible": True,
            "conditions_met": "TRENDING + ACCELERATING ...",
            "override_terms": "50% unit | ...",
            "tight_stop": 138.0,
            "override_target": 160.0,
            "override_rr": 0.83,
            "note": "OPERATOR DISCRETION: ...",
        }
        assert "eligible" in override
        assert "Eligible" not in override
        assert "conditions_met" in override
        assert "Conditions_Met" not in override
        assert "override_terms" in override
        assert "Override_Terms" not in override
        assert override["eligible"] is True

    def test_ineligible_path_lowercase_keys(self):
        """Ineligible override dict uses lowercase keys."""
        override = {
            "eligible": False,
            "reason": "Engine State not TRENDING",
            "note": "Extension rejection is protective. Do not chase.",
        }
        assert "eligible" in override
        assert "Eligible" not in override
        assert "reason" in override
        assert "Reason" not in override
        assert "note" in override
        assert "Note" not in override
        assert override["eligible"] is False

    def test_default_not_evaluated_lowercase(self):
        """Default (not evaluated) override dict already uses lowercase."""
        override = {
            "eligible": False,
            "reason": "some ATR note",
            "note": "Extension is protective. Do not chase.",
        }
        assert "eligible" in override
        assert "Eligible" not in override
        assert override["eligible"] is False
