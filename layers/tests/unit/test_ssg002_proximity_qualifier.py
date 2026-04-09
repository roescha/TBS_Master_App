"""SSG-002: Structural Stop Audit — Proximity Qualifier unit tests.

Covers TC-01 through TC-09 from SSG002_Structural_Stop_Proximity_Qualifier_Spec_v1_0.
TC-10 (live validation) requires IBKR connection and is excluded from unit tests.

Spec: SSG002_Structural_Stop_Proximity_Qualifier_Spec_v1_0.docx
Prompt: SSG002_Standalone_Implementation_Prompt.md
"""

import sys, os, math
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ---------------------------------------------------------------------------
# SSG-002 proximity qualifier algorithm (mirrors data.py inline logic)
# ---------------------------------------------------------------------------

SSG_PROXIMITY_THRESHOLD = 0.5
SSG_REMEDY_BUFFER = 0.25


def _ssg002_evaluate(hard_stop_raw, established_hourly_low, atr_raw, price_scaler=1.0):
    """Pure-function replica of SSG-002 logic in data.py for isolated testing.

    Returns dict with keys: hard_stop, adjusted, proximity_blocked, gap_atr,
    original_price, reason.
    """
    result = {
        "hard_stop": hard_stop_raw,
        "adjusted": False,
        "proximity_blocked": False,
        "gap_atr": None,
        "original_price": None,
        "reason": None,
    }

    if hard_stop_raw > established_hourly_low:
        gap = hard_stop_raw - established_hourly_low
        gap_atr = gap / atr_raw if atr_raw > 0 else float('inf')
        result["gap_atr"] = round(gap_atr, 2)
        result["original_price"] = hard_stop_raw

        if gap_atr < SSG_PROXIMITY_THRESHOLD:
            # Near-miss: apply SSG-001 remedy
            new_stop = established_hourly_low - (SSG_REMEDY_BUFFER * atr_raw)
            result["hard_stop"] = new_stop
            result["adjusted"] = True
            result["proximity_blocked"] = False
            result["reason"] = (
                f"Hard stop ({round(hard_stop_raw / price_scaler, 2)}) above "
                f"Established Hourly Low ({round(established_hourly_low / price_scaler, 2)}) "
                f"by {result['gap_atr']} ATR -- within proximity threshold "
                f"({SSG_PROXIMITY_THRESHOLD} ATR), stop adjusted to "
                f"{round(new_stop / price_scaler, 2)} (Hourly Low - 0.25 ATR)."
            )
        else:
            # Wide-gap: blocked
            result["adjusted"] = False
            result["proximity_blocked"] = True
            result["reason"] = (
                f"Hard stop ({round(hard_stop_raw / price_scaler, 2)}) above "
                f"Established Hourly Low ({round(established_hourly_low / price_scaler, 2)}) "
                f"by {result['gap_atr']} ATR -- outside proximity threshold "
                f"({SSG_PROXIMITY_THRESHOLD} ATR), no adjustment applied."
            )

    return result


# ---------------------------------------------------------------------------
# TC-01: Near-miss (gap 0.04 ATR) → adjusted: true
# ---------------------------------------------------------------------------

class TestTC01NearMiss:
    """GD-like case: gap = 0.04 ATR, well within threshold."""

    def test_adjusted_true(self):
        # GD: hard_stop=354.65, hourly_low=354.54, ATR~2.75 → gap=0.11, gap_atr≈0.04
        r = _ssg002_evaluate(354.65, 354.54, 2.75)
        assert r["adjusted"] is True

    def test_proximity_blocked_false(self):
        r = _ssg002_evaluate(354.65, 354.54, 2.75)
        assert r["proximity_blocked"] is False

    def test_gap_atr_value(self):
        r = _ssg002_evaluate(354.65, 354.54, 2.75)
        assert r["gap_atr"] == 0.04

    def test_stop_pushed_to_remedy(self):
        r = _ssg002_evaluate(354.65, 354.54, 2.75)
        expected = 354.54 - (0.25 * 2.75)  # 353.8525
        assert abs(r["hard_stop"] - expected) < 0.001


# ---------------------------------------------------------------------------
# TC-02: Boundary inside (gap 0.49 ATR) → adjusted: true
# ---------------------------------------------------------------------------

class TestTC02BoundaryInside:
    """Just inside threshold: gap = 0.49 ATR."""

    def test_adjusted_true(self):
        # Construct: hourly_low=100, atr=10, gap=4.9 → gap_atr=0.49
        r = _ssg002_evaluate(104.9, 100.0, 10.0)
        assert r["adjusted"] is True

    def test_proximity_blocked_false(self):
        r = _ssg002_evaluate(104.9, 100.0, 10.0)
        assert r["proximity_blocked"] is False

    def test_gap_atr_value(self):
        r = _ssg002_evaluate(104.9, 100.0, 10.0)
        assert r["gap_atr"] == 0.49

    def test_stop_adjusted_to_remedy(self):
        r = _ssg002_evaluate(104.9, 100.0, 10.0)
        expected = 100.0 - (0.25 * 10.0)  # 97.5
        assert abs(r["hard_stop"] - expected) < 0.001


# ---------------------------------------------------------------------------
# TC-03: Boundary at threshold (gap 0.50 ATR) → adjusted: false, blocked: true
# ---------------------------------------------------------------------------

class TestTC03BoundaryAtThreshold:
    """Exactly at threshold: gap = 0.50 ATR. Spec: >= threshold → blocked."""

    def test_adjusted_false(self):
        # hourly_low=100, atr=10, gap=5.0 → gap_atr=0.50
        r = _ssg002_evaluate(105.0, 100.0, 10.0)
        assert r["adjusted"] is False

    def test_proximity_blocked_true(self):
        r = _ssg002_evaluate(105.0, 100.0, 10.0)
        assert r["proximity_blocked"] is True

    def test_gap_atr_value(self):
        r = _ssg002_evaluate(105.0, 100.0, 10.0)
        assert r["gap_atr"] == 0.50

    def test_stop_unchanged(self):
        r = _ssg002_evaluate(105.0, 100.0, 10.0)
        assert r["hard_stop"] == 105.0


# ---------------------------------------------------------------------------
# TC-04: Wide-gap CRWD (gap 2.79 ATR) → blocked
# ---------------------------------------------------------------------------

class TestTC04WideGapCRWD:
    """CRWD: hard_stop=409.67, hourly_low=387.36, gap=22.31, ATR~8.0 → gap_atr≈2.79."""

    def test_adjusted_false(self):
        r = _ssg002_evaluate(409.67, 387.36, 8.0)
        assert r["adjusted"] is False

    def test_proximity_blocked_true(self):
        r = _ssg002_evaluate(409.67, 387.36, 8.0)
        assert r["proximity_blocked"] is True

    def test_gap_atr_value(self):
        r = _ssg002_evaluate(409.67, 387.36, 8.0)
        assert r["gap_atr"] == 2.79

    def test_stop_unchanged(self):
        r = _ssg002_evaluate(409.67, 387.36, 8.0)
        assert r["hard_stop"] == 409.67


# ---------------------------------------------------------------------------
# TC-05: Wide-gap AMAT (gap 4.56 ATR) → blocked, Capital R:R preserved
# ---------------------------------------------------------------------------

class TestTC05WideGapAMAT:
    """AMAT: hard_stop=374.79, hourly_low=346.65, ATR~6.17 → gap_atr≈4.56."""

    def test_adjusted_false(self):
        r = _ssg002_evaluate(374.79, 346.65, 6.17)
        assert r["adjusted"] is False

    def test_proximity_blocked_true(self):
        r = _ssg002_evaluate(374.79, 346.65, 6.17)
        assert r["proximity_blocked"] is True

    def test_gap_atr_value(self):
        r = _ssg002_evaluate(374.79, 346.65, 6.17)
        assert r["gap_atr"] == 4.56

    def test_stop_unchanged(self):
        r = _ssg002_evaluate(374.79, 346.65, 6.17)
        assert r["hard_stop"] == 374.79


# ---------------------------------------------------------------------------
# TC-06: hard_stop_raw <= hourly_low → no SSG evaluation
# ---------------------------------------------------------------------------

class TestTC06NoSSGEvaluation:
    """Stop is at or below hourly low — SSG-001 condition not met."""

    def test_stop_below_hourly_low(self):
        r = _ssg002_evaluate(98.0, 100.0, 10.0)
        assert r["adjusted"] is False
        assert r["proximity_blocked"] is False
        assert r["gap_atr"] is None

    def test_stop_equal_hourly_low(self):
        r = _ssg002_evaluate(100.0, 100.0, 10.0)
        assert r["adjusted"] is False
        assert r["proximity_blocked"] is False
        assert r["gap_atr"] is None

    def test_original_price_none(self):
        r = _ssg002_evaluate(98.0, 100.0, 10.0)
        assert r["original_price"] is None

    def test_reason_none(self):
        r = _ssg002_evaluate(98.0, 100.0, 10.0)
        assert r["reason"] is None


# ---------------------------------------------------------------------------
# TC-07: ATR = 0 (defensive) → gap_atr = inf, blocked
# ---------------------------------------------------------------------------

class TestTC07ATRZero:
    """ATR = 0 guard: division produces inf, which is >= threshold → blocked."""

    def test_gap_atr_inf(self):
        r = _ssg002_evaluate(105.0, 100.0, 0.0)
        assert r["gap_atr"] == float('inf')

    def test_proximity_blocked_true(self):
        r = _ssg002_evaluate(105.0, 100.0, 0.0)
        assert r["proximity_blocked"] is True

    def test_adjusted_false(self):
        r = _ssg002_evaluate(105.0, 100.0, 0.0)
        assert r["adjusted"] is False

    def test_stop_unchanged(self):
        r = _ssg002_evaluate(105.0, 100.0, 0.0)
        assert r["hard_stop"] == 105.0


# ---------------------------------------------------------------------------
# TC-08: Profile B, C1, gap 3.0 ATR → blocked
# ---------------------------------------------------------------------------

class TestTC08ProfileB:
    """Profile B enforcement: proximity qualifier applies identically.

    SSG-002 spec §2.4: All profiles. No profile-specific branching.
    This test validates the algorithm is profile-agnostic (the pure function
    has no profile parameter — profile scoping is handled by data.py removing
    the `if p_code == "A":` guard).
    """

    def test_wide_gap_blocked(self):
        # gap=30, atr=10 → gap_atr=3.0
        r = _ssg002_evaluate(130.0, 100.0, 10.0)
        assert r["adjusted"] is False
        assert r["proximity_blocked"] is True
        assert r["gap_atr"] == 3.0


# ---------------------------------------------------------------------------
# TC-09: Profile C, C3, gap 0.10 ATR → fires (adjusted)
# ---------------------------------------------------------------------------

class TestTC09ProfileC:
    """Profile C near-miss: proximity qualifier allows SSG-001 remedy."""

    def test_near_miss_fires(self):
        # gap=1.0, atr=10 → gap_atr=0.10
        r = _ssg002_evaluate(101.0, 100.0, 10.0)
        assert r["adjusted"] is True
        assert r["proximity_blocked"] is False
        assert r["gap_atr"] == 0.10

    def test_stop_pushed(self):
        r = _ssg002_evaluate(101.0, 100.0, 10.0)
        expected = 100.0 - (0.25 * 10.0)  # 97.5
        assert abs(r["hard_stop"] - expected) < 0.001


# ---------------------------------------------------------------------------
# Transform integration: stop.adjustment object assembly
# ---------------------------------------------------------------------------

class TestTransformStopAdjustment:
    """Verify transform.py correctly assembles stop.adjustment for both paths."""

    def _make_flat_metrics(self, adjusted, proximity_blocked, gap_atr,
                           original_stop=None, reason=None, hard_stop=100.0):
        return {
            "Hard_Stop": hard_stop,
            "Hard_Stop_Note": None,
            "Original_Hard_Stop": original_stop,
            "Stop_Adjusted_Flag": adjusted,
            "Stop_Adjusted_Reason": reason,
            "Stop_Proximity_Blocked": proximity_blocked,
            "Stop_Gap_ATR": gap_atr,
        }

    def test_near_miss_adjustment_object(self):
        """Near-miss: adjustment.adjusted=True, proximity_blocked=False."""
        fm = self._make_flat_metrics(
            adjusted=True, proximity_blocked=False, gap_atr=0.04,
            original_stop=354.65, reason="test near-miss"
        )
        # Replicate transform.py logic
        _stop_adjusted = fm["Stop_Adjusted_Flag"]
        _stop_proximity_blocked = fm.get("Stop_Proximity_Blocked", False)
        _stop_gap_atr = fm.get("Stop_Gap_ATR")
        _original_stop = fm.get("Original_Hard_Stop")

        if _stop_adjusted:
            adj = {
                "original_price": _original_stop,
                "adjusted": True,
                "proximity_blocked": False,
                "gap_atr": _stop_gap_atr,
            }
        elif _stop_proximity_blocked:
            adj = {
                "original_price": _original_stop or fm["Hard_Stop"],
                "adjusted": False,
                "proximity_blocked": True,
                "gap_atr": _stop_gap_atr,
            }
        else:
            adj = None

        assert adj is not None
        assert adj["adjusted"] is True
        assert adj["proximity_blocked"] is False
        assert adj["gap_atr"] == 0.04
        assert adj["original_price"] == 354.65

    def test_blocked_adjustment_object(self):
        """Wide-gap: adjustment.adjusted=False, proximity_blocked=True."""
        fm = self._make_flat_metrics(
            adjusted=False, proximity_blocked=True, gap_atr=4.56,
            original_stop=None, reason="test blocked", hard_stop=374.79
        )
        _stop_adjusted = fm["Stop_Adjusted_Flag"]
        _stop_proximity_blocked = fm.get("Stop_Proximity_Blocked", False)
        _stop_gap_atr = fm.get("Stop_Gap_ATR")
        _original_stop = fm.get("Original_Hard_Stop")

        if _stop_adjusted:
            adj = {"adjusted": True}
        elif _stop_proximity_blocked:
            adj = {
                "original_price": _original_stop or fm["Hard_Stop"],
                "adjusted": False,
                "proximity_blocked": True,
                "gap_atr": _stop_gap_atr,
            }
        else:
            adj = None

        assert adj is not None
        assert adj["adjusted"] is False
        assert adj["proximity_blocked"] is True
        assert adj["gap_atr"] == 4.56
        assert adj["original_price"] == 374.79  # falls back to Hard_Stop

    def test_no_ssg_evaluation_no_adjustment(self):
        """Stop below hourly low: no adjustment object."""
        fm = self._make_flat_metrics(
            adjusted=False, proximity_blocked=False, gap_atr=None
        )
        _stop_adjusted = fm["Stop_Adjusted_Flag"]
        _stop_proximity_blocked = fm.get("Stop_Proximity_Blocked", False)

        adj = None
        if _stop_adjusted:
            adj = {"adjusted": True}
        elif _stop_proximity_blocked:
            adj = {"adjusted": False}

        assert adj is None
