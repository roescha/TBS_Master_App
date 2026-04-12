"""SFR-001: Signal Freshness Recognition unit tests.

Tests _classify_signal_freshness() for all trigger types, edge cases,
and the transform.py integration (action_summary mapping + _flatten round-trip).

Spec: SFR001_Signal_Freshness_Recognition_Spec_v1_0.docx §2.1–§3.2
Prompt: SFR-001_Standalone_Implementation_Prompt.md §Test Expectations
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd
import numpy as np
from types import SimpleNamespace

from tbs_engine.output import _classify_signal_freshness
from tbs_engine.transform import _transform_output, _flatten


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gate_result(verdict="VALID", entry_type="PULLBACK", reason=None):
    """Build a minimal GateResult-like object for freshness tests."""
    return SimpleNamespace(
        verdict=verdict,
        entry_type=entry_type,
        reason=reason or entry_type or verdict,
        mandate="Execute at THIS bar's close.",
        context="Test context.",
        trigger_rule="BAR CLOSE ONLY",
        state="TRENDING",
    )


def _make_cfg(iq, pb_upper_col="EMA_21"):
    """Build a minimal ProfileConfig-like object."""
    return SimpleNamespace(iq=iq, pb_upper_col=pb_upper_col)


def _make_ctx(is_etf=False, resistance_raw=160.0, recovery_base_result=None):
    """Build a minimal RunContext-like object."""
    ctx = SimpleNamespace(
        is_etf=is_etf,
        resistance_raw=resistance_raw,
        _recovery_base_result=recovery_base_result,
    )
    return ctx


def _build_df(rows):
    """Build a DataFrame from a list of row dicts.

    Each row should have at minimum: close, ANCHOR, EMA_21, ATRr_14.
    Missing columns are filled with defaults.
    """
    defaults = {
        "close": 150.0, "ANCHOR": 140.0, "EMA_21": 145.0,
        "EMA_8": 148.0, "ATRr_14": 2.0, "high": 152.0,
        "low": 148.0, "open": 149.0, "volume": 1000000,
    }
    complete_rows = []
    for r in rows:
        row = {**defaults, **r}
        complete_rows.append(row)
    return pd.DataFrame(complete_rows)


# ---------------------------------------------------------------------------
# PULLBACK Trigger Tests
# ---------------------------------------------------------------------------

class TestPullbackFreshness:
    """§2.2 PULLBACK: close >= ANCHOR AND close <= pb_upper + 0.5 * ATR."""

    def test_pullback_arrival_prior_outside_zone(self):
        """Prior bar close above pullback zone → ARRIVAL."""
        # Bar 0 (N-2): outside zone (high close)
        # Bar 1 (N-1): outside zone (close > pb_upper + 0.5*ATR = 145 + 1.0 = 146)
        # Bar 2 (N):   current bar (in zone)
        df = _build_df([
            {"close": 155.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 155.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 143.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="PULLBACK")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_pullback_continuation_prior_in_zone(self):
        """Prior bar also in pullback zone → CONTINUATION."""
        # Bar 1 (N-1): close=143 in [140, 146] → qualifies
        # Bar 2 (N): current
        df = _build_df([
            {"close": 155.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 143.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 142.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="PULLBACK")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "CONTINUATION"

    def test_pullback_reentry_n2_in_zone_n1_outside(self):
        """N-2 in zone, N-1 outside → RE-ENTRY."""
        # Bar 0 (N-2): close=143 in zone → qualifies
        # Bar 1 (N-1): close=155 outside zone → doesn't qualify
        # Bar 2 (N): current
        df = _build_df([
            {"close": 143.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 155.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 142.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="PULLBACK")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "RE-ENTRY"

    def test_pullback_prior_below_anchor_is_arrival(self):
        """Prior bar close below ANCHOR → not in zone → ARRIVAL."""
        df = _build_df([
            {"close": 138.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 138.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 143.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="PULLBACK")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"


# ---------------------------------------------------------------------------
# BREAKOUT Trigger Tests
# ---------------------------------------------------------------------------

class TestBreakoutFreshness:
    """§2.2 BREAKOUT: close > resistance_raw AND close > EMA_8 (or ANCHOR for ETF)."""

    def test_breakout_arrival_prior_below_resistance(self):
        """Prior bar below resistance → ARRIVAL."""
        df = _build_df([
            {"close": 155.0, "EMA_8": 150.0},
            {"close": 155.0, "EMA_8": 153.0},  # below resistance 160
            {"close": 162.0, "EMA_8": 158.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx(resistance_raw=160.0)
        gr = _make_gate_result(entry_type="BREAKOUT")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_breakout_continuation_prior_above_resistance(self):
        """Prior bar also above resistance and EMA_8 → CONTINUATION."""
        df = _build_df([
            {"close": 155.0, "EMA_8": 150.0},
            {"close": 162.0, "EMA_8": 158.0},  # above resistance 160 and EMA_8
            {"close": 163.0, "EMA_8": 159.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx(resistance_raw=160.0)
        gr = _make_gate_result(entry_type="BREAKOUT")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "CONTINUATION"

    def test_breakout_reentry(self):
        """N-2 above resistance, N-1 below, N above → RE-ENTRY."""
        df = _build_df([
            {"close": 162.0, "EMA_8": 158.0},  # above
            {"close": 158.0, "EMA_8": 156.0},  # below resistance
            {"close": 163.0, "EMA_8": 159.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx(resistance_raw=160.0)
        gr = _make_gate_result(entry_type="BREAKOUT")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "RE-ENTRY"

    def test_breakout_etf_uses_anchor_not_ema8(self):
        """ETF breakout uses ANCHOR as convex support instead of EMA_8."""
        # Prior bar: close=162 > resistance=160, close=162 > ANCHOR=155 → qualifies
        # But EMA_8=165 (above close) — would fail non-ETF check
        df = _build_df([
            {"close": 155.0, "ANCHOR": 150.0, "EMA_8": 165.0},
            {"close": 162.0, "ANCHOR": 155.0, "EMA_8": 165.0},
            {"close": 163.0, "ANCHOR": 156.0, "EMA_8": 165.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx(is_etf=True, resistance_raw=160.0)
        gr = _make_gate_result(entry_type="BREAKOUT")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "CONTINUATION"


# ---------------------------------------------------------------------------
# SWING_BREAKOUT Trigger Tests
# ---------------------------------------------------------------------------

class TestSwingBreakoutFreshness:
    """§2.2 SWING_BREAKOUT: same conditions as BREAKOUT."""

    def test_swing_breakout_arrival(self):
        """Prior bar below resistance → ARRIVAL."""
        df = _build_df([
            {"close": 155.0, "EMA_8": 150.0},
            {"close": 155.0, "EMA_8": 153.0},
            {"close": 162.0, "EMA_8": 158.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx(resistance_raw=160.0)
        gr = _make_gate_result(entry_type="SWING_BREAKOUT")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_swing_breakout_continuation(self):
        """Prior bar also above resistance → CONTINUATION."""
        df = _build_df([
            {"close": 155.0, "EMA_8": 150.0},
            {"close": 162.0, "EMA_8": 158.0},
            {"close": 163.0, "EMA_8": 159.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx(resistance_raw=160.0)
        gr = _make_gate_result(entry_type="SWING_BREAKOUT")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "CONTINUATION"


# ---------------------------------------------------------------------------
# RECLAIM Trigger Tests
# ---------------------------------------------------------------------------

class TestReclaimFreshness:
    """§2.2 RECLAIM: close(N-1) >= ANCHOR(N-1).

    §2.3: RECLAIM will almost always classify as ARRIVAL because by
    definition the prior bar was below the floor.
    """

    def test_reclaim_arrival_prior_below_floor(self):
        """Prior bar below ANCHOR (canonical case) → ARRIVAL."""
        df = _build_df([
            {"close": 135.0, "ANCHOR": 140.0},  # below floor
            {"close": 138.0, "ANCHOR": 140.0},  # below floor
            {"close": 142.0, "ANCHOR": 140.0},  # reclaim bar
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="RECLAIM")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_reclaim_continuation_prior_also_above_floor(self):
        """Prior bar also above ANCHOR (missed reclaim, floor holding) → CONTINUATION."""
        df = _build_df([
            {"close": 138.0, "ANCHOR": 140.0},
            {"close": 141.0, "ANCHOR": 140.0},  # also above floor
            {"close": 142.0, "ANCHOR": 140.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="RECLAIM")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "CONTINUATION"

    def test_reclaim_reentry(self):
        """N-2 above floor, N-1 dipped below, N reclaims → RE-ENTRY."""
        df = _build_df([
            {"close": 141.0, "ANCHOR": 140.0},  # above floor
            {"close": 138.0, "ANCHOR": 140.0},  # dipped below
            {"close": 142.0, "ANCHOR": 140.0},  # reclaim
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="RECLAIM")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "RE-ENTRY"


# ---------------------------------------------------------------------------
# RECOVERY CANDIDATE Trigger Tests
# ---------------------------------------------------------------------------

class TestRecoveryCandidateFreshness:
    """§2.2 / §2.4 RECOVERY CANDIDATE: ema_cross_bar_index < bar_index."""

    def test_recovery_arrival_cross_on_prior_bar(self):
        """EMA cross on bar N-1 → current bar is first evaluation → ARRIVAL."""
        df = _build_df([{"close": 100.0}] * 5)
        cfg = _make_cfg(iq=4)
        ctx = _make_ctx(recovery_base_result={"ema_cross_bar_index": 3})  # cross on N-1
        gr = _make_gate_result(verdict="RECOVERY CANDIDATE", entry_type=None, reason="RECOVERY CANDIDATE")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_recovery_continuation_cross_well_before(self):
        """EMA cross 3 bars ago → N-1 was also a candidate → CONTINUATION."""
        df = _build_df([{"close": 100.0}] * 5)
        cfg = _make_cfg(iq=4)
        ctx = _make_ctx(recovery_base_result={"ema_cross_bar_index": 1})  # cross well before N-1
        gr = _make_gate_result(verdict="RECOVERY CANDIDATE", entry_type=None, reason="RECOVERY CANDIDATE")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "CONTINUATION"

    def test_recovery_reentry_cross_before_n2(self):
        """EMA cross before N-2 but not before N-1 is impossible for recovery
        (cross index is fixed), so test the pattern:
        cross < N-2 (N-2 qualifies), cross == N-1 (N-1 doesn't qualify) → RE-ENTRY."""
        df = _build_df([{"close": 100.0}] * 5)
        cfg = _make_cfg(iq=4)
        # Cross at bar 2 → bar 2 (N-2): cross < 2? No (2 < 2 is False) → doesn't qualify
        # Actually for RE-ENTRY: N-1 doesn't qualify but N-2 does.
        # N-1 = bar 3: ema_cross_bar_index=2 < 3? Yes → N-1 qualifies → CONTINUATION
        # To get RE-ENTRY, we need N-1 not to qualify and N-2 to qualify.
        # N-1 doesn't qualify: ema_cross_bar_index >= N-1 → cross >= 3
        # N-2 qualifies: ema_cross_bar_index < N-2 → cross < 2
        # These are contradictory (cross can't be both >= 3 and < 2).
        # RE-ENTRY is structurally impossible for RECOVERY CANDIDATE
        # (the cross index is a single fixed value that either is or isn't before a bar).
        # So verify this returns ARRIVAL when N-1 doesn't qualify and N-2 doesn't either.
        ctx = _make_ctx(recovery_base_result={"ema_cross_bar_index": 4})  # cross on current bar
        gr = _make_gate_result(verdict="RECOVERY CANDIDATE", entry_type=None, reason="RECOVERY CANDIDATE")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_recovery_no_base_result(self):
        """No recovery_base_result → ARRIVAL (conservative default)."""
        df = _build_df([{"close": 100.0}] * 3)
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx(recovery_base_result=None)
        gr = _make_gate_result(verdict="RECOVERY CANDIDATE", entry_type=None, reason="RECOVERY CANDIDATE")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """§2.5 edge cases."""

    def test_first_bar_underflow(self):
        """cfg.iq = 0 → cfg.iq - 1 < 0 → ARRIVAL."""
        df = _build_df([{"close": 143.0, "ANCHOR": 140.0}])
        cfg = _make_cfg(iq=0)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="PULLBACK")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_no_entry_type_returns_arrival(self):
        """gate_result with no entry_type and non-recovery verdict → ARRIVAL."""
        df = _build_df([{"close": 143.0}] * 3)
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(verdict="VALID", entry_type=None)
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_nan_data_returns_arrival(self):
        """NaN in prior bar data → conservative ARRIVAL."""
        df = _build_df([
            {"close": float('nan'), "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": float('nan'), "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 143.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
        ])
        cfg = _make_cfg(iq=2)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="PULLBACK")
        # NaN >= 140 is False → doesn't qualify → ARRIVAL
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"

    def test_n2_underflow_no_reentry(self):
        """cfg.iq = 1 → N-2 underflows → cannot be RE-ENTRY, only ARRIVAL or CONTINUATION."""
        # N-1 (bar 0) outside zone → ARRIVAL (not RE-ENTRY since no N-2)
        df = _build_df([
            {"close": 155.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
            {"close": 143.0, "ANCHOR": 140.0, "EMA_21": 145.0, "ATRr_14": 2.0},
        ])
        cfg = _make_cfg(iq=1)
        ctx = _make_ctx()
        gr = _make_gate_result(entry_type="PULLBACK")
        assert _classify_signal_freshness(df, cfg, ctx, gr) == "ARRIVAL"


# ---------------------------------------------------------------------------
# INVALID Verdict — Signal_Freshness NOT emitted
# ---------------------------------------------------------------------------

class TestInvalidVerdictExclusion:
    """§2.5: INVALID verdict → Signal_Freshness not emitted.

    This is enforced at the call site in _assemble_output (only called
    for VALID / RECOVERY CANDIDATE). We test indirectly via transform.
    """

    def test_invalid_verdict_no_signal_freshness_in_transform(self):
        """INVALID action_summary with no Signal_Freshness in metrics → no signal_freshness in output."""
        metrics = {"Price": 150.0, "Engine_State": "TRENDING"}
        action_summary = {
            "verdict": "INVALID",
            "reason": {"label": "NOT IN PULLBACK ZONE", "detail": "Price outside zone."},
            "approaching": False,
            "volume": None,
            "volume_confirmation": None,
            "exit_status": {"active": False, "reason": None},
        }
        result = _transform_output(action_summary, metrics)
        assert "signal_freshness" not in result["action_summary"]

    def test_valid_verdict_has_signal_freshness_in_transform(self):
        """VALID action_summary with Signal_Freshness in metrics → signal_freshness present."""
        metrics = {"Signal_Freshness": "ARRIVAL", "Price": 150.0, "Engine_State": "TRENDING"}
        action_summary = {
            "verdict": "VALID",
            "reason": {"label": "PULLBACK", "detail": "All gates passed."},
            "mandate": "Execute at THIS bar's close.",
            "merit": {"quality": "HEALTHY", "reward": "HEALTHY [2.35]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Close within [140 -- 146]"},
            "volume": None,
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
            "exit_status": {"active": False, "reason": None},
        }
        result = _transform_output(action_summary, metrics)
        sfr = result["action_summary"]["signal_freshness"]
        assert sfr["label"] == "ARRIVAL"
        assert "new entry opportunity" in sfr["desc"]


# ---------------------------------------------------------------------------
# Transform Integration Tests
# ---------------------------------------------------------------------------

class TestTransformMapping:
    """§3.2: signal_freshness mapped to action_summary with {label, desc}."""

    def _make_valid_action_summary(self):
        return {
            "verdict": "VALID",
            "reason": {"label": "PULLBACK", "detail": "All gates passed."},
            "mandate": "Execute at THIS bar's close.",
            "merit": {"quality": "HEALTHY", "reward": "HEALTHY [2.35]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Close within [140 -- 146]"},
            "volume": None,
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
            "exit_status": {"active": False, "reason": None},
        }

    def test_arrival_desc(self):
        """ARRIVAL description mapping."""
        metrics = {"Signal_Freshness": "ARRIVAL"}
        result = _transform_output(self._make_valid_action_summary(), metrics)
        sfr = result["action_summary"]["signal_freshness"]
        assert sfr["label"] == "ARRIVAL"
        assert sfr["desc"] == "First qualifying bar -- new entry opportunity"

    def test_continuation_desc(self):
        """CONTINUATION description mapping."""
        metrics = {"Signal_Freshness": "CONTINUATION"}
        result = _transform_output(self._make_valid_action_summary(), metrics)
        sfr = result["action_summary"]["signal_freshness"]
        assert sfr["label"] == "CONTINUATION"
        assert sfr["desc"] == "Signal persists from prior bar"

    def test_reentry_desc(self):
        """RE-ENTRY description mapping."""
        metrics = {"Signal_Freshness": "RE-ENTRY"}
        result = _transform_output(self._make_valid_action_summary(), metrics)
        sfr = result["action_summary"]["signal_freshness"]
        assert sfr["label"] == "RE-ENTRY"
        assert sfr["desc"] == "Signal re-qualified after brief lapse"

    def test_recovery_candidate_gets_signal_freshness(self):
        """RECOVERY CANDIDATE verdict also gets signal_freshness."""
        metrics = {"Signal_Freshness": "ARRIVAL"}
        action_summary = {
            "verdict": "RECOVERY CANDIDATE",
            "reason": {"label": "RECOVERY CANDIDATE", "detail": "Recovery gates passed."},
            "mandate": "Execute recovery entry.",
            "merit": {"quality": "RECOVERY", "reward": "N/A"},
            "volume": None,
            "volume_confirmation": None,
            "exit_status": {"active": False, "reason": None},
        }
        result = _transform_output(action_summary, metrics)
        sfr = result["action_summary"]["signal_freshness"]
        assert sfr["label"] == "ARRIVAL"


# ---------------------------------------------------------------------------
# _flatten Round-Trip Tests
# ---------------------------------------------------------------------------

class TestFlattenRoundTrip:
    """Signal_Freshness must survive flatten → flat dict."""

    def test_signal_freshness_in_flat_output(self):
        """Signal_Freshness key present in flattened output."""
        metrics = {"Signal_Freshness": "CONTINUATION"}
        action_summary = {
            "verdict": "VALID",
            "reason": {"label": "PULLBACK", "detail": "All gates passed."},
            "mandate": "Execute at THIS bar's close.",
            "merit": {"quality": "HEALTHY", "reward": "HEALTHY [2.35]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Close within [140 -- 146]"},
            "volume": None,
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
            "exit_status": {"active": False, "reason": None},
        }
        grouped = _transform_output(action_summary, metrics)
        _status, _diag, flat = _flatten(grouped)
        assert flat.get("Signal_Freshness") == "CONTINUATION"

    def test_no_signal_freshness_in_flat_when_invalid(self):
        """INVALID verdict → no Signal_Freshness in flat output."""
        metrics = {}  # no Signal_Freshness key
        action_summary = {
            "verdict": "INVALID",
            "reason": {"label": "NOT IN PULLBACK ZONE", "detail": "Price outside."},
            "approaching": False,
            "volume": None,
            "volume_confirmation": None,
            "exit_status": {"active": False, "reason": None},
        }
        grouped = _transform_output(action_summary, metrics)
        _status, _diag, flat = _flatten(grouped)
        assert "Signal_Freshness" not in flat
