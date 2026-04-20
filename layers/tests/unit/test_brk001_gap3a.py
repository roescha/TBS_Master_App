"""BRK-001-GAP-3a: Stale Reward_Risk Numerator After RWD-001 Blue-Sky MM
Override — Test Suite.

Covers TC-GAP3A-01 through TC-GAP3A-05 from the BRK-001-GAP-3a spec
§7.1.  The fix relocates the MM-vs-ATR comparison from output.py into
compute.py::_compute_early_capital_rr per RWD-001 §4.1.1, so that the
Reward_Risk numerator computed at compute.py lines 1205 / 1281 / 1288
consumes the final cons_high_raw (post-MM override) rather than the
pre-override ATR projection.

Fix architecture (Option B from Phase 1 DQ-2 verification):
  - types.py::RunContext carries `mm_target_raw` (default None).
  - main.py populates ctx.mm_target_raw between _detect_breakout_model
    and _compute_early_capital_rr (reusing ctx._brk_mm_target_raw when
    the breakout model already computed it, else calling
    _compute_mm_target_early directly).
  - compute.py reads `getattr(ctx, 'mm_target_raw', None)` inside the
    blue-sky branch and overrides cons_high_raw when the raw MM_Target
    strictly exceeds the ATR projection.

Test design notes
-----------------
* Each case exercises _compute_early_capital_rr in isolation with a
  minimal SimpleNamespace ctx.  MM_Target is stubbed by setting
  ctx.mm_target_raw directly — this matches the real field compute.py
  reads and mirrors how main.py populates it in production.  Simpler
  than mock.patch and faithful to the fix surface.

* The spec's expected "Reward_Risk = (Profit_Target - close) / (close
  - floor)" is asserted via mathematical derivation from the final
  ctx.cons_high_raw.  Reward_Risk itself is written later in
  _evaluate_precheck (compute.py:1205 / 1281 / 1288), using exactly
  this identity (reward_a = cons_high_raw - close, risk_a = close -
  ANCHOR), so asserting the derived R:R validates the fix end-to-end
  without pulling in _evaluate_precheck's floor-state fixture surface.

* Boundary case TC-GAP3A-05 (MM_Target == ATR_projection) depends on
  the strict-`>` override condition in compute.py.  Relaxing to `>=`
  would flip this test to MEASURED_MOVE, which the spec rejects.

* TC-GAP3A-04 exercises the non-blue-sky path via tier1 >= close
  (PE-41 escalation never fires, Profit_Target_Source = "DAILY_CTX",
  _rwd001_blue_sky = False).  ctx.mm_target_raw is set to a sentinel
  (999.0) to prove the blue-sky code path is the only site that reads
  it — a non-blue-sky run must leave cons_high_raw at tier1 regardless.
"""
import sys
from unittest import mock

# Stub heavy deps before importing engine (same pattern as test_brk001_gap2.py)
for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'ib_insync.contract', 'ib_insync.objects'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

import pandas as pd
import pytest
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Fixture helpers
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
    """11-bar context frame where all highs are well below CLOSE, so
    PE-41 Tier 2 escalates and blue-sky activates (negative headroom
    < 1.5 * ATR for any positive ATR).
    """
    return pd.DataFrame({
        'high': [85.0] * 11,
        'low':  [80.0] * 11,
    })


def _df_ctx_not_blue_sky():
    """11-bar context frame where tier1 (= 100) > CLOSE, so PE-41 never
    fires; Profit_Target_Source lands on DAILY_CTX and _rwd001_blue_sky
    is False.
    """
    return pd.DataFrame({
        'high': [100.0] * 11,
        'low':  [95.0] * 11,
    })


def _make_ctx(atr_raw, df_ctx, mm_target_raw=None, daily_atr=None):
    """Minimal RunContext-shaped SimpleNamespace for isolated tests.

    mm_target_raw stubs the field compute.py reads for the RWD-001
    blue-sky MM-vs-ATR override (BRK-001-GAP-3a).  None → no override.

    daily_atr stubs ctx.daily_atr for BRK-001-GAP-3b (compute.py now
    reads ctx.daily_atr at the Profile A blue-sky block).  When None,
    defaults to atr_raw so pre-existing GAP-3a assertions remain exact
    (old code used state.atr_raw; new code uses ctx.daily_atr; with
    daily_atr := atr_raw the call-site value is identical).
    """
    return SimpleNamespace(
        p_code="A",
        last=_make_last(),
        metrics={},
        state=_make_state(atr_raw),
        price_scaler=PRICE_SCALER,
        resistance_raw=100.0,      # unused on Profile A blue-sky path
        hard_stop_raw=85.0,        # feeds Capital R:R suppression guard, non-blocking
        df=None,                   # unused when _df_ctx is valid
        cfg=SimpleNamespace(resistance_slice_start=0, resistance_slice_end=0),
        _df_ctx=df_ctx,
        _is_c3=False,
        # Breakout-model fields: False so the post-BRK-001 override block
        # at compute.py (after the blue-sky block) does not clobber the
        # blue-sky MM override under test.
        _breakout_model_active=False,
        _brk_mm_target_raw=None,
        # BRK-001-GAP-3a: direct stub of the RunContext field compute.py reads.
        mm_target_raw=mm_target_raw,
        # BRK-001-GAP-3b: daily_atr stub.  Default mirrors atr_raw so existing
        # GAP-3a tests remain exact under the fix (they did not differentiate
        # hourly vs daily ATR).
        daily_atr=atr_raw if daily_atr is None else daily_atr,
    )


def _derived_rr(ctx):
    """Reward_Risk as the downstream precheck will compute it:
    reward_a = cons_high_raw - close, risk_a = close - ANCHOR.
    Matches compute.py lines 1218-1219 / 1223-1224 / 1227-1228.
    """
    reward = ctx.cons_high_raw - ctx.last['close']
    risk = ctx.last['close'] - ctx.last['ANCHOR']
    return round(reward / risk, 2)


# ---------------------------------------------------------------------------
# TC-GAP3A-01 — MM wins comparison
# ---------------------------------------------------------------------------

class TestGap3aMMWins:
    """TC-GAP3A-01: blue-sky = True, ATR_projection = 100, MM_Target = 150.

    floor + 3*ATR = 90 + 3*(10/3) = 100 (ATR projection).
    Stubbed ctx.mm_target_raw = 150 > 100 → MM wins.
    Expected: cons_high_raw = 150, source = MEASURED_MOVE (blue sky),
    implied R:R = (150-95)/(95-90) = 11.0.
    """

    def test_mm_wins(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx(
            atr_raw=10.0 / 3.0, df_ctx=_df_ctx_blue_sky(), mm_target_raw=150.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(150.0, abs=1e-6), (
            "TC-GAP3A-01: cons_high_raw should be overridden to MM_Target=150, "
            f"got {ctx.cons_high_raw}"
        )
        assert ctx.metrics["Profit_Target_Source"] == "MEASURED_MOVE (blue sky)"
        assert ctx.metrics.get("_rwd001_blue_sky") is True
        assert _derived_rr(ctx) == pytest.approx(11.0, abs=0.01)
        assert ctx.metrics["Cons_High"] == pytest.approx(150.0, abs=0.01)


# ---------------------------------------------------------------------------
# TC-GAP3A-02 — MM loses comparison
# ---------------------------------------------------------------------------

class TestGap3aMMLoses:
    """TC-GAP3A-02: blue-sky = True, ATR_projection = 150, MM_Target = 100.

    floor + 3*ATR = 90 + 3*20 = 150 (ATR projection).
    Stubbed ctx.mm_target_raw = 100 < 150 → ATR wins, no override.
    Expected: cons_high_raw = 150, source = ATR_PROJECTION (blue sky),
    implied R:R = (150-95)/(95-90) = 11.0.
    """

    def test_mm_loses(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx(
            atr_raw=20.0, df_ctx=_df_ctx_blue_sky(), mm_target_raw=100.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(150.0, abs=1e-6), (
            "TC-GAP3A-02: cons_high_raw should stay at ATR projection=150, "
            f"got {ctx.cons_high_raw}"
        )
        assert ctx.metrics["Profit_Target_Source"] == "ATR_PROJECTION (blue sky)"
        assert ctx.metrics.get("_rwd001_blue_sky") is True
        assert _derived_rr(ctx) == pytest.approx(11.0, abs=0.01)
        assert ctx.metrics["Cons_High"] == pytest.approx(150.0, abs=0.01)


# ---------------------------------------------------------------------------
# TC-GAP3A-03 — MM_Target is None
# ---------------------------------------------------------------------------

class TestGap3aMMNone:
    """TC-GAP3A-03: blue-sky = True, ATR_projection = 100, MM_Target = None.

    Stubbed ctx.mm_target_raw = None → no override branch taken.
    Expected: cons_high_raw = 100, source = ATR_PROJECTION (blue sky),
    implied R:R = (100-95)/(95-90) = 1.0.
    """

    def test_mm_none(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx(
            atr_raw=10.0 / 3.0, df_ctx=_df_ctx_blue_sky(), mm_target_raw=None,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(100.0, abs=1e-6), (
            "TC-GAP3A-03: cons_high_raw should be ATR projection=100 with MM=None, "
            f"got {ctx.cons_high_raw}"
        )
        assert ctx.metrics["Profit_Target_Source"] == "ATR_PROJECTION (blue sky)"
        assert ctx.metrics.get("_rwd001_blue_sky") is True
        assert _derived_rr(ctx) == pytest.approx(1.0, abs=0.01)
        assert ctx.metrics["Cons_High"] == pytest.approx(100.0, abs=0.01)


# ---------------------------------------------------------------------------
# TC-GAP3A-04 — Not blue sky, RWD-001 path inactive
# ---------------------------------------------------------------------------

class TestGap3aNotBlueSky:
    """TC-GAP3A-04: tier1 >= close, so PE-41 never fires and the RWD-001
    block is not entered at all.  No '(blue sky)' in source,
    _rwd001_blue_sky = False.  Sentinel mm_target_raw = 999.0 is NEVER
    read because the override site is inside the blue-sky branch; this
    proves the override only fires when blue-sky is active.
    """

    def test_not_blue_sky(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx(
            atr_raw=5.0, df_ctx=_df_ctx_not_blue_sky(), mm_target_raw=999.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        # Tier1 was 100 >= close=95, PE-41 never fired; cons_high_raw stays at tier1.
        assert ctx.cons_high_raw == pytest.approx(100.0, abs=1e-6), (
            f"TC-GAP3A-04: cons_high_raw should remain tier1=100, got {ctx.cons_high_raw}"
        )
        assert ctx.metrics["Profit_Target_Source"] == "DAILY_CTX"
        assert "blue sky" not in ctx.metrics["Profit_Target_Source"]
        assert ctx.metrics.get("_rwd001_blue_sky") is False
        # The sentinel mm_target_raw=999 must NOT have caused an override;
        # cons_high_raw < 999 confirms the blue-sky branch never ran.
        assert ctx.cons_high_raw != pytest.approx(999.0), (
            "TC-GAP3A-04: mm_target_raw sentinel was applied even though blue-sky "
            "was inactive — override site is not properly guarded by the blue-sky branch"
        )


# ---------------------------------------------------------------------------
# TC-GAP3A-05 — Boundary: MM_Target equal to ATR projection
# ---------------------------------------------------------------------------

class TestGap3aBoundary:
    """TC-GAP3A-05: blue-sky = True, ATR_projection = 100, MM_Target = 100.

    Strict `>` in the override condition (mm_target_raw > cons_high_raw)
    means the tie goes to ATR.  Relaxing to `>=` would flip source to
    MEASURED_MOVE and regress this test.
    Expected: cons_high_raw = 100, source = ATR_PROJECTION (blue sky).
    """

    def test_boundary_tie_goes_to_atr(self):
        from tbs_engine.compute import _compute_early_capital_rr
        ctx = _make_ctx(
            atr_raw=10.0 / 3.0, df_ctx=_df_ctx_blue_sky(), mm_target_raw=100.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)

        # ATR projection = floor + 3*(10/3) = 100; MM_Target = 100; tie → ATR keeps.
        assert ctx.cons_high_raw == pytest.approx(100.0, abs=1e-6), (
            "TC-GAP3A-05: cons_high_raw should stay at ATR projection=100 on tie, "
            f"got {ctx.cons_high_raw}"
        )
        assert ctx.metrics["Profit_Target_Source"] == "ATR_PROJECTION (blue sky)", (
            "TC-GAP3A-05: strict-> boundary — MM_Target == ATR_projection should "
            "NOT flip source to MEASURED_MOVE; got "
            f"{ctx.metrics['Profit_Target_Source']!r}"
        )
        assert ctx.metrics.get("_rwd001_blue_sky") is True
