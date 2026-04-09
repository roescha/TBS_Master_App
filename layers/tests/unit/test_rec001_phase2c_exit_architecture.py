"""REC-001 Phase 2C: Exit Architecture — Unit Tests.

Tests recovery-specific exits (base failure, EMA re-inversion, time stop),
priority ordering, edge cases, and time_stop_bars_remaining countdown.

Maps to spec §6.1–6.5 and test cases for each exit condition.
"""
import sys
import types as builtin_types
import importlib.util

# --- Isolated import: load exit module without full package chain ---
if 'tbs_engine' not in sys.modules:
    pkg = builtin_types.ModuleType('tbs_engine')
    pkg.__path__ = ['tbs_engine']
    sys.modules['tbs_engine'] = pkg
for _mod, _path in [('tbs_engine.types', 'tbs_engine/types.py'),
                     ('tbs_engine.helpers', 'tbs_engine/helpers.py'),
                     ('tbs_engine.exit', 'tbs_engine/exit.py')]:
    if _mod not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_mod, _path)
        _m = importlib.util.module_from_spec(_spec)
        sys.modules[_mod] = _m
        _spec.loader.exec_module(_m)

import pytest
from tbs_engine.exit import _exit_recovery


# ═══════════════════════════════════════════════════════════════════════
#  BASELINE PARAMETERS (reused across tests)
# ═══════════════════════════════════════════════════════════════════════

BASE = dict(
    current_low=100.0,
    current_price=105.0,
    ema_8=106.0,
    ema_21=104.0,       # EMA 8 > EMA 21 (no re-inversion)
    swing_low_price=95.0,
    entry_price=102.0,
    recovery_target=115.0,
    time_stop_limit=25,  # Profile A
    bars_since_entry=5,
)


# ═══════════════════════════════════════════════════════════════════════
#  §6.2: BASE FAILURE EXIT (Priority 1)
# ═══════════════════════════════════════════════════════════════════════

class TestBaseFailureExit:
    """Spec §6.2: current bar low < swing_low_price → EXIT, BASE FAILURE."""

    def test_base_failure_fires_when_low_below_swing_low(self):
        result = _exit_recovery(**{**BASE, "current_low": 94.99})
        assert result["exit_signal"] == "EXIT"
        assert result["exit_reason"] == "BASE FAILURE"

    def test_base_failure_does_not_fire_when_low_equals_swing_low(self):
        """Spec says strictly less than: low < swing_low_price."""
        result = _exit_recovery(**{**BASE, "current_low": 95.0})
        assert result["exit_signal"] is None

    def test_base_failure_does_not_fire_when_low_above_swing_low(self):
        result = _exit_recovery(**{**BASE, "current_low": 96.0})
        assert result["exit_signal"] is None


# ═══════════════════════════════════════════════════════════════════════
#  §6.3: EMA RE-INVERSION EXIT (Priority 2)
# ═══════════════════════════════════════════════════════════════════════

class TestEmaReInversionExit:
    """Spec §6.3: EMA 8 < EMA 21 at current bar → EXIT, EMA RE-INVERSION."""

    def test_ema_reinversion_fires(self):
        result = _exit_recovery(**{**BASE, "ema_8": 103.0, "ema_21": 104.0})
        assert result["exit_signal"] == "EXIT"
        assert result["exit_reason"] == "EMA RE-INVERSION"

    def test_ema_equal_does_not_fire(self):
        """EMA 8 == EMA 21 is NOT less than, so no re-inversion."""
        result = _exit_recovery(**{**BASE, "ema_8": 104.0, "ema_21": 104.0})
        assert result["exit_signal"] is None

    def test_ema_bullish_does_not_fire(self):
        result = _exit_recovery(**{**BASE, "ema_8": 106.0, "ema_21": 104.0})
        assert result["exit_signal"] is None


# ═══════════════════════════════════════════════════════════════════════
#  §6.4: TIME STOP EXIT (Priority 3)
# ═══════════════════════════════════════════════════════════════════════

class TestTimeStopExit:
    """Spec §6.4: bars_since_entry >= limit AND progress < 0.50 → EXIT, TIME STOP."""

    def test_time_stop_fires_profile_a(self):
        """Profile A: 25 bar limit, progress below 50%."""
        result = _exit_recovery(**{
            **BASE,
            "time_stop_limit": 25,
            "bars_since_entry": 25,
            "current_price": 104.0,   # progress = (104-102)/(115-102) = 0.154
            "entry_price": 102.0,
            "recovery_target": 115.0,
        })
        assert result["exit_signal"] == "EXIT"
        assert result["exit_reason"] == "TIME STOP"
        assert result["time_stop_bars_remaining"] == 0

    def test_time_stop_fires_profile_b(self):
        """Profile B: 12 bar limit."""
        result = _exit_recovery(**{
            **BASE,
            "time_stop_limit": 12,
            "bars_since_entry": 12,
            "current_price": 104.0,
            "entry_price": 102.0,
            "recovery_target": 115.0,
        })
        assert result["exit_signal"] == "EXIT"
        assert result["exit_reason"] == "TIME STOP"

    def test_time_stop_does_not_fire_when_progress_above_threshold(self):
        """Progress >= 0.50 means time stop does not fire even at limit."""
        result = _exit_recovery(**{
            **BASE,
            "time_stop_limit": 25,
            "bars_since_entry": 25,
            "current_price": 110.0,   # progress = (110-102)/(115-102) = 0.615
            "entry_price": 102.0,
            "recovery_target": 115.0,
        })
        assert result["exit_signal"] is None

    def test_time_stop_does_not_fire_before_limit(self):
        """bars_since_entry < limit → no time stop regardless of progress."""
        result = _exit_recovery(**{
            **BASE,
            "time_stop_limit": 25,
            "bars_since_entry": 24,
            "current_price": 103.0,   # low progress
        })
        assert result["exit_signal"] is None

    def test_time_stop_exact_50_percent_does_not_fire(self):
        """progress == 0.50 is NOT < 0.50, so time stop should NOT fire."""
        # progress = (entry + 0.5*(target-entry) - entry) / (target - entry) = 0.5
        entry = 100.0
        target = 120.0
        price_at_50 = entry + 0.5 * (target - entry)  # 110.0
        result = _exit_recovery(**{
            **BASE,
            "time_stop_limit": 25,
            "bars_since_entry": 30,
            "current_price": price_at_50,
            "entry_price": entry,
            "recovery_target": target,
        })
        assert result["exit_signal"] is None


# ═══════════════════════════════════════════════════════════════════════
#  §6.1: PRIORITY ORDERING
# ═══════════════════════════════════════════════════════════════════════

class TestPriorityOrdering:
    """Spec §6.1: base failure > EMA re-inversion > time stop."""

    def test_base_failure_takes_priority_over_ema_reinversion(self):
        """Both base failure AND EMA re-inversion conditions true → BASE FAILURE wins."""
        result = _exit_recovery(**{
            **BASE,
            "current_low": 94.0,      # base failure
            "ema_8": 103.0,           # EMA re-inversion
            "ema_21": 105.0,
            "bars_since_entry": 5,
        })
        assert result["exit_reason"] == "BASE FAILURE"

    def test_base_failure_takes_priority_over_time_stop(self):
        """Base failure AND time stop conditions true → BASE FAILURE wins."""
        result = _exit_recovery(**{
            **BASE,
            "current_low": 94.0,
            "bars_since_entry": 30,
            "current_price": 103.0,
            "time_stop_limit": 25,
        })
        assert result["exit_reason"] == "BASE FAILURE"

    def test_ema_reinversion_takes_priority_over_time_stop(self):
        """EMA re-inversion AND time stop both true → EMA RE-INVERSION wins."""
        result = _exit_recovery(**{
            **BASE,
            "ema_8": 103.0,
            "ema_21": 105.0,
            "bars_since_entry": 30,
            "current_price": 103.0,
            "time_stop_limit": 25,
        })
        assert result["exit_reason"] == "EMA RE-INVERSION"

    def test_all_three_conditions_true_base_failure_wins(self):
        """All three exit conditions true → BASE FAILURE (highest priority)."""
        result = _exit_recovery(**{
            **BASE,
            "current_low": 94.0,
            "ema_8": 103.0,
            "ema_21": 105.0,
            "bars_since_entry": 30,
            "current_price": 103.0,
            "time_stop_limit": 25,
        })
        assert result["exit_reason"] == "BASE FAILURE"


# ═══════════════════════════════════════════════════════════════════════
#  ENTRY BAR: bars_since_entry = 0
# ═══════════════════════════════════════════════════════════════════════

class TestEntryBar:
    """On entry bar (bars_since_entry = 0), no exit fires."""

    def test_no_exit_on_entry_bar_even_with_bad_conditions(self):
        """Even if conditions would trigger exits, bars_since_entry=0 blocks all."""
        result = _exit_recovery(**{
            **BASE,
            "current_low": 94.0,      # would trigger base failure
            "ema_8": 103.0,           # would trigger EMA re-inversion
            "ema_21": 105.0,
            "bars_since_entry": 0,
            "time_stop_limit": 0,     # extreme: limit=0
        })
        assert result["exit_signal"] is None
        assert result["exit_reason"] is None

    def test_countdown_on_entry_bar(self):
        result = _exit_recovery(**{**BASE, "bars_since_entry": 0, "time_stop_limit": 25})
        assert result["time_stop_bars_remaining"] == 25


# ═══════════════════════════════════════════════════════════════════════
#  EDGE CASES
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Division by zero, negative progress, countdown floor."""

    def test_division_by_zero_target_equals_entry(self):
        """recovery_target == entry_price → progress = 0.0, no crash."""
        result = _exit_recovery(**{
            **BASE,
            "entry_price": 100.0,
            "recovery_target": 100.0,
            "bars_since_entry": 5,
        })
        assert result["progress"] == 0.0
        assert result["exit_signal"] is None  # no base/EMA trigger in BASE params

    def test_negative_progress(self):
        """Price below entry → negative progress. Valid, still uses 0.50 threshold."""
        result = _exit_recovery(**{
            **BASE,
            "current_price": 98.0,    # below entry of 102
            "entry_price": 102.0,
            "recovery_target": 115.0,
            "bars_since_entry": 5,
        })
        assert result["progress"] < 0.0

    def test_negative_progress_with_time_stop(self):
        """Negative progress + at limit → TIME STOP fires (progress < 0.50)."""
        result = _exit_recovery(**{
            **BASE,
            "current_price": 98.0,
            "entry_price": 102.0,
            "recovery_target": 115.0,
            "bars_since_entry": 25,
            "time_stop_limit": 25,
        })
        assert result["exit_signal"] == "EXIT"
        assert result["exit_reason"] == "TIME STOP"

    def test_countdown_floors_at_zero(self):
        """time_stop_bars_remaining never goes negative."""
        result = _exit_recovery(**{
            **BASE,
            "bars_since_entry": 30,
            "time_stop_limit": 25,
            "current_price": 112.0,   # progress > 0.50, no time stop
            "entry_price": 102.0,
            "recovery_target": 115.0,
        })
        assert result["time_stop_bars_remaining"] == 0

    def test_countdown_correct_mid_window(self):
        """Countdown = limit - bars_since_entry when positive."""
        result = _exit_recovery(**{**BASE, "bars_since_entry": 10, "time_stop_limit": 25})
        assert result["time_stop_bars_remaining"] == 15


# ═══════════════════════════════════════════════════════════════════════
#  RETURN STRUCTURE
# ═══════════════════════════════════════════════════════════════════════

class TestReturnStructure:
    """Verify return dict always has the required keys."""

    @pytest.mark.parametrize("bars", [0, 5, 25, 30])
    def test_all_keys_present(self, bars):
        result = _exit_recovery(**{**BASE, "bars_since_entry": bars})
        assert "exit_signal" in result
        assert "exit_reason" in result
        assert "time_stop_bars_remaining" in result
        assert "progress" in result
        assert "bars_since_entry" in result

    def test_no_exit_returns_none_signal_and_reason(self):
        result = _exit_recovery(**BASE)
        assert result["exit_signal"] is None
        assert result["exit_reason"] is None

    def test_progress_is_rounded(self):
        result = _exit_recovery(**{
            **BASE,
            "current_price": 103.333333,
            "entry_price": 102.0,
            "recovery_target": 115.0,
        })
        # (103.333333 - 102) / (115 - 102) = 0.102564...
        assert result["progress"] == round(result["progress"], 4)

    def test_bars_since_entry_echoed(self):
        result = _exit_recovery(**{**BASE, "bars_since_entry": 17})
        assert result["bars_since_entry"] == 17
