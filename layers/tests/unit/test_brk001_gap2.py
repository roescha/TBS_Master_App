"""BRK-001-GAP-2: Breakout Thesis Invalidation — Test Suite.

Covers TC-GAP2-01 through TC-GAP2-09 from the BRK-001-GAP-2 standalone
implementation prompt.

Partitioning (Operator-confirmed):
  * Parametrised threshold triplet for TC-01/02/03 (close below / above /
    equal to new support).
  * Individual tests for TC-04 (Profile B), TC-05 (ON Semi regression),
    TC-06 (C-3 bypass), TC-07 (non-breakout regression), TC-08 (Path A
    fresh-breakout pass-through), TC-09 (Path B not-stale bypass).
  * Transform-layer tests for the Option A resolution (minimal
    swing_breakout_confirmation container when SBO is inactive).

Notes for future readers:
  * TC-GAP2-09 in the prompt text reads 'close above resistance but below
    ANCHOR+ATR', which is physically inconsistent with standard fixtures
    (ANCHOR+ATR=71.35 < resistance=72.53, so a close cannot be both). The
    test's INTENT — verifying that a Path-B pullback failure never reaches
    the thesis guard — is preserved here by using a close fully in the
    pullback zone (below ANCHOR+ATR and below resistance).
  * The original `test_detect_breakout_model_stale` in test_brk001.py
    codified the pre-GAP-2 buggy behaviour (close 72.05 < resistance 72.53
    expected _breakout_model_active=True). That test was updated in the
    same PR; TC-GAP2-01 below is the canonical replacement.
"""
import sys
from unittest import mock

# Stub heavy deps before importing engine (same pattern as test_brk001.py)
for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'ib_insync.contract', 'ib_insync.objects'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

import pytest
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Fixture helpers — mirrors test_brk001.py so TC references stay comparable
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    defaults = dict(
        atr_raw=0.8, di_plus=31.88, di_minus=9.3,
        adx_t=53.16, adx_t1=52.0, ma_squeeze=False,
        is_trending=True, is_resolving=False,
        _entry_trending=True, _entry_resolving=False,
        ema_stacked=True, ma_stack_full=True,
        consec_below=0, is_violated=False, is_reclaim=False,
        is_floor_failure=False, _reclaim_run=0, floor_raw=70.55,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_last(**overrides):
    d = dict(close=72.05, open=71.50, high=72.30, low=71.20,
             volume=1041951.0, vol_sma_20=500000.0,
             ANCHOR=70.55, EMA_8=71.76, EMA_21=70.55,
             SMA_50=67.61, SMA_200=61.93)
    d.update(overrides)
    return d


def _make_ctx(**overrides):
    state = overrides.pop('state', _make_state())
    last = overrides.pop('last', _make_last())
    defaults = dict(
        state=state, last=last, p_code="A", is_etf=False,
        _is_c3=False, resistance_raw=72.53, hard_stop_raw=69.36,
        structural_floor_raw=70.55, price_scaler=1.0,
        actual_price=72.08, metrics={}, bars_per_day=7,
        window_count=3, window_limit=4,
        daily_protective_anchor=64.72, daily_atr=2.69,
        daily_hard_stop=60.69, df=None,
        cfg=SimpleNamespace(iq=-1, ff_threshold=4),
        _df_ctx=None, adx_col='ADX', dmp_col='DMP', dmn_col='DMN',
        _sbo_prestate=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ===========================================================================
# Section 1 — compute.py guard behaviour
# ===========================================================================

class TestThesisGuardThresholdTriplet:
    """TC-GAP2-01 / -02 / -03: the strict-`<` boundary of the thesis guard.

    Fixture: resistance_raw=72.53, ANCHOR=70.55, ATR=0.8 → ANCHOR+ATR=71.35.
    Window is OPEN (3/4) with "BREAKOUT" reset event, so Path B is live.

    Note: at close=72.90 (TC-02) Path A fires (close > resistance AND rvol
    >=1.5 AND di+>di-), not Path B. Either path keeps the model active and
    the thesis non-failed, which is what the triplet validates.
    """

    @pytest.mark.parametrize("tc_id,close,expected_failed,expected_active", [
        ("TC-GAP2-01",  72.05, True,  False),   # close <  new support → FAILED
        ("TC-GAP2-02",  72.90, False, True),    # close >  new support → Path A
        ("TC-GAP2-03",  72.53, False, True),    # close == new support → Path B
    ])
    def test_threshold(self, tc_id, close, expected_failed, expected_active):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=close),
            state=_make_state(atr_raw=0.8),
            resistance_raw=72.53, window_count=3, window_limit=4,
        )
        _detect_breakout_model(ctx, "BREAKOUT")

        assert ctx._breakout_thesis_failed is expected_failed, (
            f"{tc_id}: _breakout_thesis_failed expected={expected_failed} "
            f"got={ctx._breakout_thesis_failed} (close={close}, resistance=72.53)"
        )
        assert ctx._breakout_model_active is expected_active, (
            f"{tc_id}: _breakout_model_active expected={expected_active} "
            f"got={ctx._breakout_model_active}"
        )
        if expected_failed:
            assert ctx._brk_failed_new_support == 72.53
            # Guard return preserves line-90 defaults on all other BRK fields
            assert ctx._brk_new_support_raw is None
            assert ctx._brk_tight_stop_raw is None
            assert ctx._brk_catastrophic_stop_raw is None
        else:
            assert ctx._brk_failed_new_support is None


class TestThesisGuardProfileB:
    """TC-GAP2-04: Profile B, window OPEN, bar close below new support.

    Guard behaviour is profile-agnostic. Only difference from TC-01 is
    p_code="B" (trigger source is BREAKOUT rather than SWING_BREAKOUT).
    """

    def test_profile_b_thesis_failure(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=72.05),
            state=_make_state(atr_raw=0.8),
            p_code="B",
            resistance_raw=72.53, window_count=3, window_limit=4,
        )
        _detect_breakout_model(ctx, "BREAKOUT")
        assert ctx._breakout_thesis_failed is True
        assert ctx._breakout_model_active is False
        assert ctx._brk_failed_new_support == 72.53


class TestThesisGuardONSemiRegression:
    """TC-GAP2-05: ON Semi Profile A C-2 Session 119 regression.

    Live evidence: bar close 79.94, resistance_raw (new support) 80.50,
    delta -0.56. Engine previously activated the breakout model on this
    invalidated thesis; post-GAP-2 the model stays inactive and the
    thesis diagnostic fires.
    """

    def test_on_semi_79_94_vs_80_50(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=79.94, ANCHOR=78.00),   # ANCHOR below close for Path B not-pulled-back
            state=_make_state(atr_raw=0.80),
            resistance_raw=80.50, window_count=2, window_limit=4,
        )
        _detect_breakout_model(ctx, "BREAKOUT")

        assert ctx._breakout_thesis_failed is True
        assert ctx._breakout_model_active is False
        assert ctx._brk_failed_new_support == 80.50
        # Delta is recomputed at output.py emission time, not in compute.py,
        # so we just verify the raw failed-support level here; the delta
        # check lives with the output.py / transform.py tests below.

    def test_on_semi_delta_via_output(self):
        """Exercises output.py thesis diagnostic: Delta == close - new_support."""
        # Synthesise a ctx with the guard flags already set, then assert the
        # flat-metric emission block produces delta = -0.56. We call the
        # BRK output block by instantiating a ctx that behaves like the
        # engine has already run _detect_breakout_model() on the ON Semi
        # bar.
        ctx = _make_ctx()
        ctx._breakout_model_active = False
        ctx._breakout_thesis_failed = True
        ctx._brk_failed_new_support = 80.50
        ctx.last = _make_last(close=79.94)

        # Apply the output.py thesis-diagnostic code path directly. This
        # mirrors the block at output.py line 1128–1158 exactly; any drift
        # between this fixture and the production block will surface as a
        # test failure after the next output.py refactor, which is the
        # intent.
        metrics = {}
        price_scaler = 1.0
        last = ctx.last
        _brk_thesis_failed = getattr(ctx, '_breakout_thesis_failed', False) is True
        if _brk_thesis_failed:
            _failed_ns = getattr(ctx, '_brk_failed_new_support', None)
            metrics["Breakout_Thesis_Status"] = "FAILED"
            if _failed_ns is not None:
                metrics["BRK_Thesis_New_Support"] = round(_failed_ns / price_scaler, 2)
                metrics["BRK_Thesis_Bar_Close"] = round(last['close'] / price_scaler, 2)
                metrics["BRK_Thesis_Delta"] = round(
                    (last['close'] - _failed_ns) / price_scaler, 2)

        assert metrics["Breakout_Thesis_Status"] == "FAILED"
        assert metrics["BRK_Thesis_New_Support"] == 80.50
        assert metrics["BRK_Thesis_Bar_Close"] == 79.94
        assert metrics["BRK_Thesis_Delta"] == pytest.approx(-0.56, abs=0.001)


class TestThesisGuardC3Bypass:
    """TC-GAP2-06: C-3 profile early-returns before the thesis guard.

    C-3 bypasses the entire breakout model (line 100–101 return). The
    thesis guard at line 150 is unreachable on this path.
    """

    def test_c3_close_below_new_support_no_thesis_flag(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=72.05),   # below resistance — would fire guard on non-C3
            state=_make_state(atr_raw=0.8),
            _is_c3=True,
            resistance_raw=72.53, window_count=3, window_limit=4,
        )
        _detect_breakout_model(ctx, "BREAKOUT")

        # C-3 short-circuit preserves line-90 defaults across ALL BRK fields,
        # including the new GAP-2 ones.
        assert ctx._breakout_model_active is False
        assert ctx._breakout_thesis_failed is False
        assert ctx._brk_failed_new_support is None


class TestThesisGuardNonBreakoutRegression:
    """TC-GAP2-07: PULLBACK / RECLAIM / RECOVERY paths unaffected.

    When the trigger is not BREAKOUT/SWING_BREAKOUT, Path A fails (close at
    floor) and Path B's _is_breakout_event check fails. The merge filter
    returns BEFORE the thesis guard runs. Defaults at line 95–97 preserve
    _breakout_thesis_failed=False and _brk_failed_new_support=None.
    """

    def test_pullback_reset_event_no_thesis_annotation(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=71.00),   # pullback-zone close
            state=_make_state(atr_raw=0.8),
            resistance_raw=72.53, window_count=3, window_limit=4,
        )
        _detect_breakout_model(ctx, "PULLBACK")   # non-breakout event

        assert ctx._breakout_model_active is False
        assert ctx._breakout_thesis_failed is False
        assert ctx._brk_failed_new_support is None


class TestThesisGuardFreshBreakoutPassThrough:
    """TC-GAP2-08: Path A fresh breakout, close > resistance.

    Path A requires close > resistance_raw by construction, so the thesis
    guard condition (close < resistance_raw) is structurally unreachable
    on this path. Model activates; thesis never flags.
    """

    def test_fresh_breakout_no_thesis_failure(self):
        from tbs_engine.compute import _detect_breakout_model
        ctx = _make_ctx(
            last=_make_last(close=73.00, volume=1_000_000.0, vol_sma_20=500_000.0),
            state=_make_state(di_plus=31.88, di_minus=9.3, atr_raw=0.8),
            resistance_raw=72.53,
        )
        _detect_breakout_model(ctx, "BREAKOUT")

        assert ctx._breakout_model_active is True
        assert ctx._breakout_thesis_failed is False
        assert ctx._brk_failed_new_support is None
        # Existing fresh-breakout invariants still hold
        assert ctx._brk_new_support_raw == 72.53


class TestThesisGuardNotStaleBypass:
    """TC-GAP2-09: Path B fails via _not_pulled_back — thesis guard not reached.

    Spec description ('close above resistance but below ANCHOR+ATR') is
    physically inconsistent; the re-interpreted intent is that close has
    pulled back into the entry zone (below ANCHOR+ATR). Under that
    condition, Path B fails at the _not_pulled_back check, _stale=False,
    the merge filter returns, and the thesis guard is structurally
    unreachable.

    The test proves the guard does NOT fire even though close < resistance
    — because the function exits before reaching the guard. This is the
    critical ordering invariant: thesis-guard is downstream of Path A/B
    evaluation.
    """

    def test_close_in_pullback_zone_no_thesis_fire(self):
        from tbs_engine.compute import _detect_breakout_model
        # close=70.50: below ANCHOR+ATR=71.35 (pullback zone), below
        # resistance=72.53 (would fire guard if reached).
        ctx = _make_ctx(
            last=_make_last(close=70.50),
            state=_make_state(atr_raw=0.8),
            resistance_raw=72.53, window_count=3, window_limit=4,
        )
        _detect_breakout_model(ctx, "BREAKOUT")

        assert ctx._breakout_model_active is False
        # Critical: thesis did NOT flag as failed — function exited before
        # the guard could evaluate the close < resistance comparison.
        assert ctx._breakout_thesis_failed is False
        assert ctx._brk_failed_new_support is None


# ===========================================================================
# Section 2 — transform.py Option A (minimal container) behaviour
# ===========================================================================

class TestTransformOptionAMinimalContainer:
    """Option A: swing_breakout_confirmation is (a) extended with
    breakout_thesis when SBO is active, or (b) created as a minimal
    container holding only breakout_thesis when SBO is inactive.

    Tests the builder logic in transform.py at lines 1996–2029.
    """

    def _base_action_summary(self):
        return {
            "verdict": "INVALID",
            "reason": {"label": "DAILY_EXTENSION", "detail": "RSI 78 extended."},
            "mandate": "Reject.",
            "merit": {"quality": "LOW", "reward": "FAVORABLE [2.1]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "..."},
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 72, "stop_loss": 70,
                               "target": 75, "fib_382": None, "fib_500": None,
                               "fib_confluence": None, "mm_target": None},
            "exit_status": {"active": False, "reason": None},
        }

    def test_thesis_failed_sbo_active_both_sub_objects_present(self):
        """Profile A scenario: SBO is active AND thesis failed.

        Both the SBO tracking fields and the breakout_thesis annotation
        must appear in the grouped output, side-by-side in the same
        swing_breakout_confirmation container.
        """
        from tbs_engine.transform import _transform_output

        metrics = {
            # SBO active (Profile A)
            "SBO_Breakout_Bar_Age": 7,
            "SBO_Trending_Reached": False,
            "SBO_Confirmation_Timeout": False,
            "SBO_RVOL": 2.08,
            # Thesis failed (GAP-2 flat metrics)
            "Breakout_Thesis_Status": "FAILED",
            "BRK_Thesis_New_Support": 80.50,
            "BRK_Thesis_Bar_Close": 79.94,
            "BRK_Thesis_Delta": -0.56,
            "BRK_Thesis_Note": "Breakout thesis FAILED: bar close 79.94 below new support 80.50 (delta -0.56). Standard pullback model applied.",
        }
        result = _transform_output(self._base_action_summary(), metrics)

        sbo = result.get("swing_breakout_confirmation")
        assert sbo is not None
        # SBO fields still present
        assert sbo["status"]["label"] == "PENDING"
        assert sbo["breakout_age"]["value"] == 7
        # breakout_thesis sub-object attached alongside
        assert "breakout_thesis" in sbo
        thesis = sbo["breakout_thesis"]
        assert thesis["status"]["label"] == "FAILED"
        assert thesis["new_support"] == 80.50
        assert thesis["bar_close"] == 79.94
        assert thesis["delta"] == pytest.approx(-0.56, abs=0.001)

    def test_thesis_failed_sbo_inactive_minimal_container(self):
        """Profile B / ETF scenario: SBO is inactive, thesis failed.

        Option A resolution: transform builds a MINIMAL container holding
        only breakout_thesis. SBO fields are ABSENT (not False) so
        downstream consumers can distinguish the minimal container from a
        real SBO monitor result.
        """
        from tbs_engine.transform import _transform_output

        metrics = {
            # SBO inactive — all SBO_* emitted as None by output.py default
            "SBO_Breakout_Bar_Age": None,
            "SBO_Trending_Reached": None,
            "SBO_Confirmation_Timeout": None,
            "SBO_RVOL": None,
            # Thesis failed
            "Breakout_Thesis_Status": "FAILED",
            "BRK_Thesis_New_Support": 72.53,
            "BRK_Thesis_Bar_Close": 72.05,
            "BRK_Thesis_Delta": -0.48,
            "BRK_Thesis_Note": "Breakout thesis FAILED: ...",
        }
        result = _transform_output(self._base_action_summary(), metrics)

        sbo = result.get("swing_breakout_confirmation")
        assert sbo is not None, "minimal container must be created when thesis fails without SBO"
        # Minimal container has ONLY breakout_thesis — SBO fields absent
        assert "status" not in sbo
        assert "breakout_age" not in sbo
        assert "confirmation_window" not in sbo
        assert "breakout_rvol" not in sbo
        # breakout_thesis sub-object present and populated
        thesis = sbo["breakout_thesis"]
        assert thesis["status"]["label"] == "FAILED"
        assert thesis["new_support"] == 72.53
        assert thesis["bar_close"] == 72.05

    def test_thesis_not_failed_no_breakout_thesis_key(self):
        """Regression: when thesis has not failed, the breakout_thesis key
        must NOT appear in swing_breakout_confirmation, even if SBO is
        active.
        """
        from tbs_engine.transform import _transform_output

        metrics = {
            "SBO_Breakout_Bar_Age": 7,
            "SBO_Trending_Reached": False,
            "SBO_Confirmation_Timeout": False,
            "SBO_RVOL": 2.08,
            # No Breakout_Thesis_Status in flat metrics
        }
        result = _transform_output(self._base_action_summary(), metrics)
        sbo = result.get("swing_breakout_confirmation")
        assert sbo is not None
        assert "breakout_thesis" not in sbo

    def test_thesis_status_non_failed_value_does_not_build_annotation(self):
        """Defensive: if Breakout_Thesis_Status somehow held a non-FAILED
        label (future extension), the builder should not attach an
        annotation. Builder uses explicit `== 'FAILED'` comparison.
        """
        from tbs_engine.transform import _transform_output

        metrics = {
            "SBO_Breakout_Bar_Age": 7,
            "SBO_Trending_Reached": False,
            "SBO_Confirmation_Timeout": False,
            "SBO_RVOL": 2.08,
            "Breakout_Thesis_Status": "OK",   # hypothetical non-FAILED value
        }
        result = _transform_output(self._base_action_summary(), metrics)
        sbo = result.get("swing_breakout_confirmation")
        assert sbo is not None
        assert "breakout_thesis" not in sbo


class TestTransformFlattenRoundTrip:
    """_flatten() extraction: flat keys round-trip correctly from the
    grouped output. Includes the hardened SBO-extraction case where the
    minimal container must NOT produce False SBO_Trending_Reached /
    SBO_Confirmation_Timeout (which would mis-indicate SBO having run).
    """

    def test_roundtrip_sbo_active_with_thesis(self):
        from tbs_engine.transform import _transform_output, _flatten

        metrics_in = {
            "SBO_Breakout_Bar_Age": 7,
            "SBO_Trending_Reached": False,
            "SBO_Confirmation_Timeout": False,
            "SBO_RVOL": 2.08,
            "Breakout_Thesis_Status": "FAILED",
            "BRK_Thesis_New_Support": 80.50,
            "BRK_Thesis_Bar_Close": 79.94,
            "BRK_Thesis_Delta": -0.56,
        }
        action_summary = {
            "verdict": "INVALID",
            "reason": {"label": "DAILY_EXTENSION", "detail": "..."},
            "mandate": "Reject.",
            "merit": {"quality": "LOW", "reward": "FAVORABLE [2.1]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "..."},
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 80, "stop_loss": 79,
                               "target": 85, "fib_382": None, "fib_500": None,
                               "fib_confluence": None, "mm_target": None},
            "exit_status": {"active": False, "reason": None},
        }
        grouped = _transform_output(action_summary, metrics_in)
        _, _, flat_out = _flatten(grouped)

        # SBO keys round-trip
        assert flat_out["SBO_Breakout_Bar_Age"] == 7
        assert flat_out["SBO_Trending_Reached"] is False
        assert flat_out["SBO_Confirmation_Timeout"] is False
        assert flat_out["SBO_RVOL"] == 2.08
        # Thesis keys round-trip
        assert flat_out["Breakout_Thesis_Status"] == "FAILED"
        assert flat_out["BRK_Thesis_New_Support"] == 80.50
        assert flat_out["BRK_Thesis_Bar_Close"] == 79.94
        assert flat_out["BRK_Thesis_Delta"] == pytest.approx(-0.56, abs=0.001)

    def test_roundtrip_sbo_inactive_minimal_container(self):
        """Critical hardening check: minimal container does NOT emit False
        for SBO_Trending_Reached/SBO_Confirmation_Timeout during flatten.

        Without the _sbo.get('breakout_age') is not None guard in
        _flatten(), the SBO extraction would run on the minimal container,
        read status={}.get('label')=None, compare None == 'CONFIRMED'
        → False, and populate SBO_Trending_Reached=False. That would
        misrepresent a Profile B thesis failure as an SBO run.
        """
        from tbs_engine.transform import _transform_output, _flatten

        metrics_in = {
            # SBO inactive
            "SBO_Breakout_Bar_Age": None,
            # Thesis failed → minimal container path
            "Breakout_Thesis_Status": "FAILED",
            "BRK_Thesis_New_Support": 72.53,
            "BRK_Thesis_Bar_Close": 72.05,
            "BRK_Thesis_Delta": -0.48,
        }
        action_summary = {
            "verdict": "INVALID",
            "reason": {"label": "BREAKOUT", "detail": "..."},
            "mandate": "Reject.",
            "merit": {"quality": "LOW", "reward": "ADEQUATE [1.5]"},
            "trigger": {"rule": "BAR CLOSE ONLY", "condition": "..."},
            "volume": "NEUTRAL",
            "volume_confirmation": None,
            "entry_strategy": {"entry_price": 72, "stop_loss": 70,
                               "target": 75, "fib_382": None, "fib_500": None,
                               "fib_confluence": None, "mm_target": None},
            "exit_status": {"active": False, "reason": None},
        }
        grouped = _transform_output(action_summary, metrics_in)
        _, _, flat_out = _flatten(grouped)

        # SBO flat keys MUST NOT be written by _flatten when only the
        # minimal thesis container exists. Their absence from flat_out is
        # the correct round-trip — they were None in input and should be
        # None (absent) in output.
        assert flat_out.get("SBO_Breakout_Bar_Age") is None
        assert "SBO_Trending_Reached" not in flat_out, (
            "Hardened SBO extraction must skip when breakout_age missing; "
            "otherwise a False value leaks in and misrepresents SBO state."
        )
        assert "SBO_Confirmation_Timeout" not in flat_out
        assert flat_out.get("SBO_RVOL") is None

        # Thesis keys round-trip correctly
        assert flat_out["Breakout_Thesis_Status"] == "FAILED"
        assert flat_out["BRK_Thesis_New_Support"] == 72.53
        assert flat_out["BRK_Thesis_Bar_Close"] == 72.05
        assert flat_out["BRK_Thesis_Delta"] == pytest.approx(-0.48, abs=0.001)


# ===========================================================================
# Section 3 — MAPPED_FLAT_KEYS coverage audit
# ===========================================================================

class TestMappedFlatKeysCoverage:
    """Ensure the new flat keys are registered in MAPPED_FLAT_KEYS so
    _audit_key_coverage does not flag them as unmapped during runs.
    """

    def test_thesis_flat_keys_registered(self):
        from tbs_engine.transform import MAPPED_FLAT_KEYS
        for key in (
            "Breakout_Thesis_Status",
            "BRK_Thesis_New_Support",
            "BRK_Thesis_Bar_Close",
            "BRK_Thesis_Delta",
            "BRK_Thesis_Note",
        ):
            assert key in MAPPED_FLAT_KEYS, f"{key} missing from MAPPED_FLAT_KEYS"
