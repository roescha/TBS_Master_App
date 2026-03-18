"""FFD-001: Floor Failure Differentiation — Composite Function Unit Tests.

Covers:
  - All three profiles (A, B, C) on the BREACH path (all 3 conditions pass)
  - FAILURE path with each condition failing independently (min 3 tests per profile)
  - GOOGL edge case: conditions 1+2 pass, condition 3 fails (strong HF, bearish DI)
  - Null guard: Floor_Failure_Context is None on non-floor-failure paths
  - Higher-frame context enrichment: fields present on PASS outputs
  - BREACH routes to WAIT/WARNING, FAILURE routes to REJECT/EXIT

FFD-001 Spec §III, §V, §XI (Verification Criteria V2–V7, V9).
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace
from tbs_engine.gates import _evaluate_floor_failure_context, _gate_floor_failure
from tbs_engine.types import GateResult


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(adx=15.0, di_plus=25.0, di_minus=20.0):
    """Build a minimal state object for composite evaluation."""
    return SimpleNamespace(
        adx_t=adx,
        di_plus=di_plus,
        di_minus=di_minus,
    )


def _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0, n=10):
    """Build a minimal context DataFrame with SMA_50 and SMA_200."""
    closes = [close] * n
    df = pd.DataFrame({
        'close': closes,
        'high': [c + 1.0 for c in closes],
        'low': [c - 1.0 for c in closes],
        'open': closes,
        'volume': [500000] * n,
    })
    df['SMA_50'] = sma50
    df['SMA_200'] = sma200
    return df


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: BREACH PATH — All 3 conditions pass (per profile)
# ══════════════════════════════════════════════════════════════════════════════


class TestBreachPath:
    """All three composite conditions pass → FLOOR BREACH (CONSOLIDATION)."""

    def test_profile_b_breach_all_pass(self):
        """V2-like: Profile B, weekly GC present, price > SMA200, ADX < 20 (MID-RANGE)."""
        state = _make_state(adx=15.0, di_plus=20.0, di_minus=22.0)  # ADX < 20 → passes cond 3
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)  # GC + above SMA200
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is True
        assert label == "CONSOLIDATION"
        assert conds == []

    def test_profile_b_breach_bullish_di(self):
        """Profile B: ADX >= 20 but +DI >= -DI → non-directional-bearish passes."""
        state = _make_state(adx=25.0, di_plus=28.0, di_minus=22.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is True
        assert label == "CONSOLIDATION"

    def test_profile_a_breach_all_pass(self):
        """V9: Profile A, daily GC present, price > daily SMA200, hourly ADX < 20."""
        state = _make_state(adx=18.0, di_plus=19.0, di_minus=21.0)  # ADX < 20
        df_ctx = _make_ctx_df(sma50=115.0, sma200=105.0, close=120.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "A")
        assert is_breach is True
        assert label == "CONSOLIDATION"

    def test_profile_c_breach_all_pass(self):
        """V9: Profile C, monthly GC present, price > monthly SMA200, weekly ADX < 20."""
        state = _make_state(adx=12.0, di_plus=18.0, di_minus=20.0)  # ADX < 20
        df_ctx = _make_ctx_df(sma50=200.0, sma200=180.0, close=210.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "C")
        assert is_breach is True
        assert label == "CONSOLIDATION"

    def test_profile_b_breach_meta_like(self):
        """V2: META-like case — ADX 9.72 < 20, weekly GC intact."""
        state = _make_state(adx=9.72, di_plus=24.35, di_minus=23.65)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is True
        assert label == "CONSOLIDATION"

    def test_profile_b_breach_aapl_like(self):
        """V2: AAPL-like case — ADX 15.92 < 20, -DI leads but ADX below 20."""
        state = _make_state(adx=15.92, di_plus=19.55, di_minus=25.94)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is True  # ADX < 20 exempts DI check
        assert label == "CONSOLIDATION"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: FAILURE PATH — Each condition failing independently
# ══════════════════════════════════════════════════════════════════════════════


class TestFailurePathProfileB:
    """Profile B: FAILURE when any single condition fails."""

    def test_cond1_fail_no_golden_cross(self):
        """Condition 1 fails: weekly SMA 50 < SMA 200 (no Golden Cross)."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=95.0, sma200=100.0, close=130.0)  # SMA50 < SMA200
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert "STRUCTURAL_BREAKDOWN" in label
        assert any("Golden Cross absent" in c for c in conds)

    def test_cond2_fail_price_below_sma200(self):
        """Condition 2 fails: price below weekly SMA 200."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=140.0, close=130.0)  # close < SMA200
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert "STRUCTURAL_BREAKDOWN" in label
        assert any("price below" in c for c in conds)

    def test_cond3_fail_bearish_di(self):
        """Condition 3 fails: ADX >= 20 AND -DI > +DI (bearish directional regime)."""
        state = _make_state(adx=25.0, di_plus=18.0, di_minus=28.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert "STRUCTURAL_BREAKDOWN" in label
        assert any("bearish DI regime" in c for c in conds)

    def test_msft_like_failure(self):
        """V3: MSFT-like — ADX 23.54 >= 20, -DI 27.82 > +DI 22.20."""
        state = _make_state(adx=23.54, di_plus=22.20, di_minus=27.82)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert "bearish DI regime" in label

    def test_crh_like_failure(self):
        """CRH.L-like — ADX 34.65, massive -DI dominance."""
        state = _make_state(adx=34.65, di_plus=13.51, di_minus=39.14)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert any("bearish DI regime" in c for c in conds)


class TestFailurePathProfileA:
    """Profile A: FAILURE when any single condition fails."""

    def test_cond1_fail_no_daily_golden_cross(self):
        """Condition 1 fails: daily SMA 50 < SMA 200."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=98.0, sma200=100.0, close=120.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "A")
        assert is_breach is False
        assert any("Golden Cross absent" in c for c in conds)

    def test_cond2_fail_price_below_daily_sma200(self):
        """Condition 2 fails: price below daily SMA 200."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=135.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "A")
        assert is_breach is False
        assert any("price below" in c for c in conds)

    def test_cond3_fail_hourly_bearish_di(self):
        """Condition 3 fails: hourly ADX >= 20 AND -DI > +DI."""
        state = _make_state(adx=22.0, di_plus=16.0, di_minus=24.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "A")
        assert is_breach is False
        assert any("bearish DI regime" in c for c in conds)


class TestFailurePathProfileC:
    """Profile C: FAILURE when any single condition fails."""

    def test_cond1_fail_no_monthly_golden_cross(self):
        """V9: Condition 1 fails: monthly SMA 50 < SMA 200."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=170.0, sma200=180.0, close=190.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "C")
        assert is_breach is False
        assert any("Golden Cross absent" in c for c in conds)

    def test_cond2_fail_price_below_monthly_sma200(self):
        """V9: Condition 2 fails: price below monthly SMA 200."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=200.0, sma200=210.0, close=190.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "C")
        assert is_breach is False
        assert any("price below" in c for c in conds)

    def test_cond3_fail_weekly_bearish_di(self):
        """V9: Condition 3 fails: weekly ADX >= 20 AND -DI > +DI."""
        state = _make_state(adx=42.06, di_plus=20.05, di_minus=36.49)
        df_ctx = _make_ctx_df(sma50=200.0, sma200=180.0, close=210.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "C")
        assert is_breach is False
        assert any("bearish DI regime" in c for c in conds)

    def test_rel_l_wealth_failure(self):
        """REL.L WEALTH: ADX 42.06, heavy -DI dominance."""
        state = _make_state(adx=42.06, di_plus=20.05, di_minus=36.49)
        df_ctx = _make_ctx_df(sma50=200.0, sma200=180.0, close=210.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "C")
        assert is_breach is False


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: GOOGL EDGE CASE (V4)
# ══════════════════════════════════════════════════════════════════════════════


class TestGOOGLEdgeCase:
    """V4: GOOGL — conditions 1+2 pass, condition 3 fails (strong weekly, bearish DI)."""

    def test_googl_pattern(self):
        """ADX 29.9, -DI 25.4 > +DI 19.08. Weekly GC intact, strongest slope (+3.12)."""
        state = _make_state(adx=29.90, di_plus=19.08, di_minus=25.40)
        df_ctx = _make_ctx_df(sma50=280.0, sma200=255.0, close=310.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert "STRUCTURAL_BREAKDOWN" in label
        assert any("bearish DI regime" in c for c in conds)
        # Verify the exact DI values appear in the failing condition
        assert any("-DI 25.40 > +DI 19.08" in c for c in conds)

    def test_googl_weekly_context_visible(self):
        """GOOGL: even when FAILURE, the weekly context data is computable."""
        # The composite correctly returns FAILURE, but the context enrichment
        # fields (written separately in _gate_context_regime) ensure the
        # Operator sees the strong weekly context.
        state = _make_state(adx=29.90, di_plus=19.08, di_minus=25.40)
        df_ctx = _make_ctx_df(sma50=280.0, sma200=255.0, close=310.0)
        _, _, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        # Only condition 3 fails — conditions 1 and 2 pass
        assert len(conds) == 1
        assert "bearish DI regime" in conds[0]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: NULL GUARD (V6)
# ══════════════════════════════════════════════════════════════════════════════


class TestNullGuard:
    """V6: Floor_Failure_Context is None on non-floor-failure paths."""

    def test_gate_passes_when_no_floor_failure(self):
        """Floor failure gate returns None when is_floor_failure is False."""
        result = _gate_floor_failure(
            consec_below=2, is_floor_failure=False, p_code="B",
            state=_make_state(), df_ctx=_make_ctx_df(), metrics={}
        )
        assert result is None

    def test_gate_no_ffd_field_on_non_failure(self):
        """Floor_Failure_Context not written by gate when threshold not reached."""
        metrics = {}
        _gate_floor_failure(
            consec_below=2, is_floor_failure=False, p_code="B",
            state=_make_state(), df_ctx=_make_ctx_df(), metrics=metrics
        )
        assert "Floor_Failure_Context" not in metrics

    def test_gate_writes_ffd_on_breach(self):
        """Floor_Failure_Context = CONSOLIDATION when BREACH path."""
        metrics = {}
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        result = _gate_floor_failure(
            consec_below=5, is_floor_failure=True, p_code="B",
            state=state, df_ctx=df_ctx, metrics=metrics
        )
        assert result is not None
        assert metrics["Floor_Failure_Context"] == "CONSOLIDATION"

    def test_gate_writes_ffd_on_failure(self):
        """Floor_Failure_Context = STRUCTURAL_BREAKDOWN when FAILURE path."""
        metrics = {}
        state = _make_state(adx=25.0, di_plus=18.0, di_minus=28.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        result = _gate_floor_failure(
            consec_below=5, is_floor_failure=True, p_code="B",
            state=state, df_ctx=df_ctx, metrics=metrics
        )
        assert result is not None
        assert "STRUCTURAL_BREAKDOWN" in metrics["Floor_Failure_Context"]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: GATE VERDICT ROUTING (V2, V3)
# ══════════════════════════════════════════════════════════════════════════════


class TestGateVerdictRouting:
    """BREACH routes to WAIT/WARNING, FAILURE routes to REJECT/EXIT."""

    def test_breach_routes_to_wait(self):
        """V2: BREACH → INVALID with FLOOR BREACH reason."""
        metrics = {}
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        _gr = _gate_floor_failure(
            consec_below=5, is_floor_failure=True, p_code="B",
            state=state, df_ctx=df_ctx, metrics=metrics
        )
        assert isinstance(_gr, GateResult)
        assert _gr.verdict == "INVALID"
        assert "WAIT (reason: FLOOR BREACH)" in _gr.legacy_diagnostic
        assert "higher-frame intact" in _gr.legacy_diagnostic
        assert metrics["Exit_Signal"] == "WARNING"

    def test_failure_routes_to_reject(self):
        """V3: FAILURE → INVALID with FLOOR FAILURE reason."""
        metrics = {}
        state = _make_state(adx=25.0, di_plus=18.0, di_minus=28.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        _gr = _gate_floor_failure(
            consec_below=5, is_floor_failure=True, p_code="B",
            state=state, df_ctx=df_ctx, metrics=metrics
        )
        assert isinstance(_gr, GateResult)
        assert _gr.verdict == "INVALID"
        assert "REJECT (reason: FLOOR FAILURE)" in _gr.legacy_diagnostic
        assert "Structural break" in _gr.legacy_diagnostic

    def test_breach_preserves_rr_via_warning(self):
        """V2: BREACH sets EXIT_Signal = WARNING (PE-28: R:R remains visible)."""
        metrics = {}
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        _gate_floor_failure(
            consec_below=5, is_floor_failure=True, p_code="B",
            state=state, df_ctx=df_ctx, metrics=metrics
        )
        assert metrics["Exit_Signal"] == "WARNING"

    def test_breach_bar_note_profile_a(self):
        """Profile A BREACH diagnostic includes 'evaluated on last completed bar'."""
        metrics = {}
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        _gr = _gate_floor_failure(
            consec_below=9, is_floor_failure=True, p_code="A",
            state=state, df_ctx=df_ctx, metrics=metrics
        )
        assert "evaluated on last completed bar" in _gr.legacy_diagnostic


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: DATA GUARD CASES
# ══════════════════════════════════════════════════════════════════════════════


class TestDataGuards:
    """Composite function handles missing/null data gracefully."""

    def test_none_df_ctx(self):
        """df_ctx is None → FAILURE with data unavailable note."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, None, "B")
        assert is_breach is False
        assert "STRUCTURAL_BREAKDOWN" in label
        assert any("unavailable" in c for c in conds)

    def test_empty_df_ctx(self):
        """df_ctx has < 2 rows → FAILURE with data unavailable note."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = pd.DataFrame({'close': [100], 'SMA_50': [105], 'SMA_200': [95]})
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False

    def test_nan_sma200(self):
        """SMA_200 is NaN → FAILURE with SMA data insufficient."""
        state = _make_state(adx=15.0, di_plus=25.0, di_minus=20.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        df_ctx['SMA_200'] = float('nan')
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert "insufficient" in label.lower() or "STRUCTURAL_BREAKDOWN" in label

    def test_backward_compat_no_extra_params(self):
        """Gate called without FFD-001 params (backward compatibility)."""
        result = _gate_floor_failure(consec_below=5, is_floor_failure=True, p_code="B")
        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert "REJECT" in result.legacy_diagnostic or "FLOOR FAILURE" in result.legacy_diagnostic


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: MULTIPLE CONDITIONS FAILING
# ══════════════════════════════════════════════════════════════════════════════


class TestMultipleFailures:
    """Multiple conditions can fail simultaneously."""

    def test_all_three_fail(self):
        """All 3 conditions fail: no GC, price below SMA200, bearish DI."""
        state = _make_state(adx=30.0, di_plus=15.0, di_minus=35.0)
        df_ctx = _make_ctx_df(sma50=90.0, sma200=100.0, close=95.0)  # GC absent, below SMA200
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert len(conds) == 3
        assert "STRUCTURAL_BREAKDOWN" in label

    def test_two_conditions_fail(self):
        """Two conditions fail: GC absent + bearish DI."""
        state = _make_state(adx=25.0, di_plus=18.0, di_minus=28.0)
        df_ctx = _make_ctx_df(sma50=95.0, sma200=100.0, close=130.0)  # GC absent
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert len(conds) == 2

    def test_shop_trend_failure(self):
        """SHOP TREND: ADX 19.08 < 20 → condition 3 passes. But need cond 1+2 check."""
        state = _make_state(adx=19.08, di_plus=21.07, di_minus=18.85)
        # If weekly GC is absent → FAILURE despite cond 3 passing
        df_ctx = _make_ctx_df(sma50=95.0, sma200=100.0, close=130.0)
        is_breach, label, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False  # GC absent


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: CONDITION 3 BOUNDARY CASES
# ══════════════════════════════════════════════════════════════════════════════


class TestCondition3Boundaries:
    """Condition 3: ADX < 20 OR (ADX >= 20 AND +DI >= -DI)."""

    def test_adx_exactly_20_di_equal(self):
        """ADX = 20.0, +DI = -DI → non-directional-bearish passes."""
        state = _make_state(adx=20.0, di_plus=22.0, di_minus=22.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, _, _ = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is True

    def test_adx_19_99_di_minus_leads(self):
        """ADX = 19.99 < 20 → passes regardless of DI direction."""
        state = _make_state(adx=19.99, di_plus=15.0, di_minus=30.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, _, _ = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is True

    def test_adx_20_01_di_minus_leads(self):
        """ADX = 20.01 >= 20, -DI > +DI → bearish, condition 3 fails."""
        state = _make_state(adx=20.01, di_plus=18.0, di_minus=25.0)
        df_ctx = _make_ctx_df(sma50=120.0, sma200=100.0, close=130.0)
        is_breach, _, conds = _evaluate_floor_failure_context(state, df_ctx, "B")
        assert is_breach is False
        assert any("bearish DI regime" in c for c in conds)
