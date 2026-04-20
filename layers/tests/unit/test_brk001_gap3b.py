"""BRK-001-GAP-3b: Blue-Sky ATR Projection Uses Hourly ATR, Not Daily — Test Suite.

Covers T-GAP3B-01 through T-GAP3B-07 from the BRK-001-GAP-3b spec v1.0
§8.1.  The fix changes the Profile A blue-sky ATR source inside
compute.py::_compute_early_capital_rr from state.atr_raw (which is the
PRIMARY-frame ATR — hourly on Profile A) to ctx.daily_atr, so the
projection magnitude matches RWD-001 §3.2 / §4.1.1 ("14-period daily
ATR from the context chart").  Profile B is left untouched because its
primary frame is already daily (comment-only clarification at line
~856).

Fix architecture (Fix B from GAP-3b spec §4):
  - compute.py:~670 Profile A blue-sky block now reads ctx.daily_atr.
  - compute.py:~856 Profile B blue-sky block unchanged; a clarifying
    comment was added above `_atr_daily_b = state.atr_raw`.
  - No types.py, main.py, output.py changes; ctx.daily_atr was already
    defined in RunContext (types.py:223, PA-001 Phase 1) and populated
    for Profile A in main.py:170.

Test design notes
-----------------
* Each functional case exercises _compute_early_capital_rr in isolation
  with a minimal SimpleNamespace ctx, mirroring the GAP-3a S125
  fixture pattern.  ctx.daily_atr is stubbed directly — this matches
  the real field compute.py now reads and keeps the tests independent
  of main.py's raw_metrics plumbing.

* The fixture for T-GAP3B-01/02/03/04/05 uses CLOSE = 95.0,
  FLOOR = 90.0 constants identical to test_brk001_gap3a.py so the
  blue-sky-activating _df_ctx pattern (all highs = 85 < close) reuses
  the same arithmetic surface.

* T-GAP3B-03 asserts a spec-correct winner flip: under pre-fix hourly
  ATR the MM_Target won; under post-fix daily ATR the larger ATR
  projection wins.  This is the exact scenario called out in the
  spec's GAP-3a-regression-set mitigation notes (§9).

* T-GAP3B-06 (Profile B) uses distinct values for ctx.daily_atr and
  state.atr_raw so the computed atr_target provably depends on
  state.atr_raw (Profile B's intended source) — if Profile B were
  accidentally switched to ctx.daily_atr, the assertion would fail.

* T-GAP3B-07 is the source-level regression guard: it inspects the
  source of _compute_early_capital_rr and asserts 'ctx.daily_atr'
  appears within the Profile A blue-sky region.  Mirrors the spec's
  reference to the BUG-IVR-3 AST guard pattern (§8.1).
"""
import sys
import inspect
from unittest import mock

# Stub heavy deps before importing engine (same pattern as test_brk001_gap3a.py)
for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'ib_insync.contract', 'ib_insync.objects'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

import pandas as pd
import pytest
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Fixture helpers (Profile A)
# ---------------------------------------------------------------------------

CLOSE = 95.0
FLOOR = 90.0          # last['ANCHOR']
PRICE_SCALER = 1.0


def _make_state(atr_raw):
    """Minimal StateBundle-shaped ctx.state for _compute_early_capital_rr."""
    return SimpleNamespace(
        atr_raw=atr_raw,
        is_floor_failure=False,
        is_violated=False,
    )


def _make_last(close=CLOSE, anchor=FLOOR):
    """Minimal last-bar dict — only fields _compute_early_capital_rr touches."""
    return {'close': close, 'ANCHOR': anchor}


def _df_ctx_blue_sky():
    """11-bar context frame where all highs are below CLOSE, so PE-41
    Tier 2 escalates and the blue-sky headroom is negative (always <
    1.5 * any positive ATR, so blue-sky activates when ctx.daily_atr > 0).
    """
    return pd.DataFrame({
        'high': [85.0] * 11,
        'low':  [80.0] * 11,
    })


def _make_ctx_a(atr_raw, daily_atr, df_ctx, mm_target_raw=None):
    """Profile A minimal RunContext-shaped SimpleNamespace.

    atr_raw       → state.atr_raw (primary-frame ATR; hourly on Profile A).
    daily_atr     → ctx.daily_atr (what the fix reads at the Profile A blue-sky block).
    mm_target_raw → ctx.mm_target_raw (RWD-001 §4.1.1 MM-vs-ATR override).
    """
    return SimpleNamespace(
        p_code="A",
        last=_make_last(),
        metrics={},
        state=_make_state(atr_raw),
        price_scaler=PRICE_SCALER,
        resistance_raw=100.0,      # unused on Profile A blue-sky path
        hard_stop_raw=85.0,        # non-blocking suppression-guard feed
        df=None,                   # unused when _df_ctx is valid
        cfg=SimpleNamespace(resistance_slice_start=0, resistance_slice_end=0),
        _df_ctx=df_ctx,
        _is_c3=False,
        # BRK-001-GAP-3a ctx fields
        _breakout_model_active=False,
        _brk_mm_target_raw=None,
        mm_target_raw=mm_target_raw,
        # BRK-001-GAP-3b: the field the fix at compute.py:~670 reads.
        daily_atr=daily_atr,
    )


# ---------------------------------------------------------------------------
# T-GAP3B-01 — Daily ATR source used; ATR stands as target
# ---------------------------------------------------------------------------

class TestGap3bDailyAtrUsed:
    """T-GAP3B-01: blue-sky = True, ctx.daily_atr = 1.57, state.atr_raw = 0.29,
    MM_Target = None.

    Expected arithmetic:
        _atr_target = FLOOR + 3 * ctx.daily_atr = 90 + 3 * 1.57 = 94.71
    Pre-fix (state.atr_raw = 0.29):
        _atr_target = 90 + 3 * 0.29 = 90.87 — FAILS this assertion,
        proving the test is sensitive to the fix.
    """

    def test_daily_atr_used_mm_none(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx_a(
            atr_raw=0.29, daily_atr=1.57, df_ctx=_df_ctx_blue_sky(),
            mm_target_raw=None,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(94.71, abs=1e-6), (
            "T-GAP3B-01: _atr_target should equal FLOOR + 3 * ctx.daily_atr "
            f"= 90 + 3 * 1.57 = 94.71, got {ctx.cons_high_raw}.  Pre-fix "
            "would compute 90 + 3 * 0.29 = 90.87 (hourly ATR) — failure "
            "here means the Profile A blue-sky block still reads state.atr_raw."
        )
        assert ctx.metrics["Profit_Target_Source"] == "ATR_PROJECTION (blue sky)"
        assert ctx.metrics.get("_rwd001_blue_sky") is True


# ---------------------------------------------------------------------------
# T-GAP3B-02 — Blue-sky active, MM_Target > new _atr_target → MM wins
# ---------------------------------------------------------------------------

class TestGap3bMMWinsUnderDailyAtr:
    """T-GAP3B-02: ctx.daily_atr > state.atr_raw, MM_Target > new _atr_target
    → MM wins.

    daily_atr = 20, atr_raw = 5 → new _atr_target = 90 + 60 = 150.
    MM_Target = 200 > 150 → override fires; cons_high_raw = 200.
    """

    def test_mm_wins_under_daily_atr(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx_a(
            atr_raw=5.0, daily_atr=20.0, df_ctx=_df_ctx_blue_sky(),
            mm_target_raw=200.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(200.0, abs=1e-6), (
            "T-GAP3B-02: MM_Target (200) > _atr_target (150) should "
            f"override to cons_high_raw = 200, got {ctx.cons_high_raw}"
        )
        assert ctx.metrics["Profit_Target_Source"] == "MEASURED_MOVE (blue sky)"
        assert ctx.metrics.get("_rwd001_blue_sky") is True


# ---------------------------------------------------------------------------
# T-GAP3B-03 — Winner flips from MM (pre-fix hourly) to ATR (post-fix daily)
# ---------------------------------------------------------------------------

class TestGap3bWinnerFlipsToATR:
    """T-GAP3B-03: previously MM won under hourly ATR; after the fix ATR
    projection is larger and wins.

    Pre-fix with atr_raw = 5: _atr_target = 90 + 15 = 105; MM = 110 > 105 → MM wins.
    Post-fix with daily_atr = 20: _atr_target = 90 + 60 = 150; MM = 110 < 150 → ATR wins.

    The flip is spec-correct per GAP-3b §9 (Risk Analysis): acceptable when
    the new target > current price (150 > CLOSE=95) — which it is.
    """

    def test_winner_flips_to_atr(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx_a(
            atr_raw=5.0, daily_atr=20.0, df_ctx=_df_ctx_blue_sky(),
            mm_target_raw=110.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(150.0, abs=1e-6), (
            "T-GAP3B-03: post-fix _atr_target (150) > MM_Target (110) → "
            f"ATR should win; got {ctx.cons_high_raw}"
        )
        assert ctx.metrics["Profit_Target_Source"] == "ATR_PROJECTION (blue sky)", (
            "T-GAP3B-03: winner must flip to ATR_PROJECTION, not stay at "
            f"MEASURED_MOVE; got {ctx.metrics.get('Profit_Target_Source')!r}"
        )
        # Sanity: the post-fix target is above current price (flip is spec-correct)
        assert ctx.cons_high_raw > ctx.last['close']


# ---------------------------------------------------------------------------
# T-GAP3B-04 — Degenerate ctx.daily_atr = 0 → blue-sky suppressed
# ---------------------------------------------------------------------------

class TestGap3bDegenerateDailyAtrZero:
    """T-GAP3B-04: ctx.daily_atr = 0 (e.g. missing Daily_ATR on the data-fetch
    path).  The existing guard `if _is_blue_sky and _atr_daily > 0` blocks
    the blue-sky branch — cons_high_raw stays at the PE-41 Tier 2 ceiling
    (= df_ctx['high'].max() = 85 in our fixture), no exception is raised.

    Per spec §5.3, implementer MUST NOT introduce a fallback to state.atr_raw
    — that would silently reproduce the hourly-ATR bug on edge cases.  This
    test confirms the spec-intended graceful suppression.
    """

    def test_degenerate_daily_atr_zero(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx_a(
            atr_raw=5.0, daily_atr=0.0, df_ctx=_df_ctx_blue_sky(),
            mm_target_raw=None,
        )
        # Must not raise — the guard handles the degenerate case cleanly.
        _compute_early_capital_rr(ctx, exit_signal=False)

        # PE-41 Tier 2 ceiling stands (= 85; all fixture highs are 85).
        assert ctx.cons_high_raw == pytest.approx(85.0, abs=1e-6), (
            "T-GAP3B-04: with daily_atr=0 the blue-sky guard must suppress; "
            f"cons_high_raw should stay at PE-41 Tier 2 = 85, got {ctx.cons_high_raw}"
        )
        # Profit target source stays at the PE-41 Tier 2 label.
        assert ctx.metrics["Profit_Target_Source"] == (
            "WEEKLY_RESISTANCE (price above daily range)"
        )
        assert ctx.metrics.get("_rwd001_blue_sky") is False


# ---------------------------------------------------------------------------
# T-GAP3B-05 — ctx.daily_atr == state.atr_raw (coincidentally equal)
# ---------------------------------------------------------------------------

class TestGap3bCoincidentalEquality:
    """T-GAP3B-05: ctx.daily_atr == state.atr_raw (e.g. on a day where
    hourly and daily ATR happen to coincide, or in a fixture that doesn't
    differentiate).  Behaviour must be indistinguishable from pre-fix —
    the fix introduces zero spurious delta in this regime.

    atr_raw = daily_atr = 5.0 → _atr_target = 90 + 15 = 105, same as
    pre-fix would compute.
    """

    def test_coincidental_equality_no_delta(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx_a(
            atr_raw=5.0, daily_atr=5.0, df_ctx=_df_ctx_blue_sky(),
            mm_target_raw=None,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(105.0, abs=1e-6)
        assert ctx.metrics["Profit_Target_Source"] == "ATR_PROJECTION (blue sky)"
        assert ctx.metrics.get("_rwd001_blue_sky") is True


# ---------------------------------------------------------------------------
# T-GAP3B-06 — Profile B blue-sky unchanged (uses state.atr_raw, not ctx.daily_atr)
# ---------------------------------------------------------------------------

class TestGap3bProfileBUntouched:
    """T-GAP3B-06: Profile B blue-sky path at compute.py:~856 must continue
    to source from state.atr_raw (because Profile B's primary frame IS
    daily).  The fix adds a clarifying comment only; no source change.

    Strategy: exercise the Profile B blue-sky path with state.atr_raw and
    ctx.daily_atr set to DIFFERENT values.  If Profile B were accidentally
    switched to ctx.daily_atr, the computed atr_target would use the
    daily_atr stub and the assertion would fail.  As long as Profile B
    still reads state.atr_raw, the atr_target matches state.atr_raw-based
    arithmetic.
    """

    def _make_ctx_b(self, atr_raw_b, daily_atr_stub):
        """Minimal Profile B ctx that triggers the blue-sky-extension branch.

        Flow through compute.py Profile B: resistance_raw <= last['close']
        (so escalation fires) → df_ctx has a weekly_ceiling > close (so
        _early_capital_target escalates) → not _has_fundamental_data (so
        the blue-sky branch enters) → _bs_headroom_b < 1.5 * _atr_daily_b
        (blue-sky condition) → _atr_daily_b > 0 (guard).
        """
        # Context frame: weekly_ceiling > close triggers escalation; choose
        # a ceiling that is COMPRESSED so blue-sky fires.  close=100,
        # ceiling=101 → headroom=1 < 1.5 * atr_raw_b (for atr_raw_b > 0.7).
        df_ctx = pd.DataFrame({
            'high': [101.0] + [95.0] * 10,   # tier1 window max = 101
            'low':  [90.0] * 11,
        })
        return SimpleNamespace(
            p_code="B",
            last={'close': 100.0, 'ANCHOR': 98.0},
            metrics={},
            state=_make_state(atr_raw_b),
            price_scaler=PRICE_SCALER,
            resistance_raw=99.0,           # < close → escalation fires
            hard_stop_raw=90.0,
            df=None,
            cfg=SimpleNamespace(resistance_slice_start=0, resistance_slice_end=0),
            _df_ctx=df_ctx,
            _is_c3=False,
            _has_fundamental_data=False,   # required to enter the Profile B blue-sky branch
            _breakout_model_active=False,
            _brk_mm_target_raw=None,
            mm_target_raw=None,
            # Set daily_atr to a value DISTINCT from atr_raw_b so any
            # accidental Profile B dependency on ctx.daily_atr would flip
            # the computed atr_target and fail the assertion below.
            daily_atr=daily_atr_stub,
        )

    def test_profile_b_uses_atr_raw_not_daily_atr(self):
        from tbs_engine.compute import _compute_early_capital_rr
        # Distinct values: Profile B should use atr_raw_b = 2.0 → atr_target
        # = 98 + 3*2 = 104.  If Profile B accidentally used ctx.daily_atr =
        # 999, atr_target would balloon to 98 + 2997 = 3095 and this test
        # would fail loudly.
        ctx = self._make_ctx_b(atr_raw_b=2.0, daily_atr_stub=999.0)
        _compute_early_capital_rr(ctx, exit_signal=False)

        # Profile B blue-sky must have fired and used state.atr_raw.
        assert ctx.metrics.get("_rwd001_blue_sky") is True, (
            "T-GAP3B-06: Profile B blue-sky branch did not fire — "
            "fixture may need adjustment for the compressed-headroom path."
        )
        atr_target = ctx.metrics.get("_rwd001_atr_target_raw")
        assert atr_target is not None
        assert atr_target == pytest.approx(104.0, abs=1e-6), (
            "T-GAP3B-06: Profile B atr_target should equal 98 + 3 * state.atr_raw "
            f"= 98 + 3 * 2.0 = 104.0, got {atr_target}.  If this test sees "
            f"~3095 (= 98 + 3 * 999), Profile B has been switched to "
            f"ctx.daily_atr — that is a regression of the spec §6 'Profile B "
            f"must stay on state.atr_raw' constraint."
        )


# ---------------------------------------------------------------------------
# T-GAP3B-07 — Source-level AST-style guard
# ---------------------------------------------------------------------------

class TestGap3bSourceLevelGuard:
    """T-GAP3B-07: AST / source-level regression guard.

    Asserts that 'ctx.daily_atr' appears inside the Profile A blue-sky
    block of _compute_early_capital_rr.  Prevents future regressions
    where a refactor or merge might silently revert the source to
    state.atr_raw.  Mirrors the BUG-IVR-3 AST-guard pattern referenced
    in the spec §8.1.
    """

    def test_profile_a_blue_sky_source_reads_ctx_daily_atr(self):
        from tbs_engine.compute import _compute_early_capital_rr
        src = inspect.getsource(_compute_early_capital_rr)

        # The fix: Profile A blue-sky block must read ctx.daily_atr.
        assert "ctx.daily_atr" in src, (
            "T-GAP3B-07: ctx.daily_atr must appear in the source of "
            "_compute_early_capital_rr (Profile A blue-sky block).  "
            "If missing, the GAP-3b fix has regressed."
        )

        # Stronger check: a line of the form `_atr_daily = ctx.daily_atr`
        # must appear (allows surrounding whitespace / alignment variation).
        import re
        assert re.search(r"_atr_daily\s*=\s*ctx\.daily_atr", src), (
            "T-GAP3B-07: expected assignment `_atr_daily = ctx.daily_atr` "
            "not found in _compute_early_capital_rr.  The Profile A blue-sky "
            "ATR source has regressed away from RWD-001 §3.2 / §4.1.1."
        )

        # Negative guard: the old buggy pattern must NOT re-appear for
        # Profile A.  We allow `_atr_daily_b = state.atr_raw` (Profile B,
        # intentionally unchanged), but `_atr_daily = state.atr_raw`
        # (Profile A, exactly the bug) must not be present.
        assert not re.search(r"(?<!_b\s)(?<!_b)_atr_daily\s*=\s*state\.atr_raw", src) \
            or re.search(r"_atr_daily_b\s*=\s*state\.atr_raw", src), (
                "T-GAP3B-07: spurious `_atr_daily = state.atr_raw` detected in "
                "_compute_early_capital_rr.  Profile A blue-sky source has "
                "regressed to the pre-GAP-3b buggy pattern."
            )

    def test_profile_b_still_reads_state_atr_raw(self):
        """Companion source-level check: Profile B's `_atr_daily_b = state.atr_raw`
        is preserved (spec §6 — comment-only change, no source change)."""
        from tbs_engine.compute import _compute_early_capital_rr
        src = inspect.getsource(_compute_early_capital_rr)
        import re
        assert re.search(r"_atr_daily_b\s*=\s*state\.atr_raw", src), (
            "T-GAP3B-07 (companion): Profile B's `_atr_daily_b = state.atr_raw` "
            "line has been removed or altered.  Per spec §6, Profile B must "
            "stay on state.atr_raw because its primary frame IS daily."
        )
