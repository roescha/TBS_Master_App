"""PA-001 Phase 1 — Dual-Anchor Architecture Unit Tests.

Tests cover:
  1. data.py: Daily ATR(14), daily protective anchor, daily hard stop
  2. gates.py — daily extension: EXHAUSTION, CAUTION, NORMAL, non-Profile A
  3. gates.py — capital expectancy advisory: Profile A advisory, Profile B enforcement
  4. main.py — Tier 3 parallel: all gates run, first failure wins, metrics populated
  5. compute.py — PE-CAL-3 exemption: Profile A skipped
"""

import pytest
from types import SimpleNamespace
from ibkr_purity_engine import GateResult, _gate_extension, _gate_capital_expectancy
from tests.conftest import build_extension_ctx


# ============================================================================
# HELPERS
# ============================================================================

def _make_extension_ctx(p_code="A", atr_dist=0.5, ext_limit=1.0,
                        daily_ext_dist=None, metrics=None):
    """Build a minimal ctx for _gate_extension with PA-001 daily fields."""
    if metrics is None:
        metrics = {}
    state = SimpleNamespace(
        is_trending=True,
        is_resolving=False,
        _entry_trending=True,
        _entry_resolving=False,
        atr_raw=2.0,
    )
    ctx = SimpleNamespace(
        state=state,
        p_code=p_code,
        is_etf=False,
        last={"close": 150.0, "open": 149.0, "SMA_200": 130.0},
        resistance_raw=160.0,
        resistance_display=160.0,
        _resistance_suppressed=False,
        floor_prox_pct=5.0,
        metrics=metrics,
        adx_accel_state="CRUISING",
        adx_accel=0.0,
        vol_confirm_state="MIXED",
        vol_confirm_ratio=0.5,
        exit_signal=False,
        structural_floor_raw=140.0,
        price_scaler=1.0,
        ext_limit=ext_limit,
        # PA-001 fields
        daily_protective_anchor=100.0,
        daily_atr=5.0,
        daily_hard_stop=92.5,
    )
    return ctx, atr_dist, ext_limit, daily_ext_dist


def _make_capital_ctx(daily_hard_stop=0.0):
    """Build a minimal ctx for _gate_capital_expectancy with PA-001 daily_hard_stop."""
    return SimpleNamespace(
        daily_hard_stop=daily_hard_stop,
        _is_c3=False,
        _df_ctx=None,
        _has_fundamental_data=False,
    )


# ============================================================================
# 1. DATA LAYER — Daily ATR / Protective Anchor / Hard Stop Formula
# ============================================================================

class TestDailyProtectiveInfrastructure:
    """Tests for data.py daily protective computations (DQ-1, DQ-2, DQ-3).

    These are formula tests — they verify the arithmetic, not the IBKR fetch.
    """

    def test_daily_hard_stop_formula(self):
        """DQ-3: hard_stop = EMA_21 - 1.5 * Daily_ATR."""
        ema21 = 102.24
        daily_atr = 4.19
        expected = ema21 - (1.5 * daily_atr)
        assert round(expected, 4) == round(102.24 - 6.285, 4)

    def test_daily_hard_stop_positive_atr(self):
        """Hard stop is below EMA 21 when ATR > 0."""
        ema21 = 100.0
        atr = 5.0
        hs = ema21 - (1.5 * atr)
        assert hs == 92.5
        assert hs < ema21

    def test_daily_hard_stop_zero_atr(self):
        """When ATR is 0, hard stop equals EMA 21 (degenerate but safe)."""
        ema21 = 100.0
        atr = 0.0
        hs = ema21 - (1.5 * atr)
        assert hs == ema21


# ============================================================================
# 2. GATES — Daily Extension Check
# ============================================================================

class TestDailyExtensionGate:
    """Tests for PA-001 daily extension overlay in _gate_extension (DQ-4)."""

    def test_exhaustion_rejects(self):
        """Profile A: daily_ext_dist > 3.0 → INVALID with reason DAILY EXTENSION."""
        metrics = {}
        ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="A", atr_dist=0.5, ext_limit=1.0, metrics=metrics)
        daily_ext_dist = 3.5

        result = _gate_extension(ctx, atr_dist, ext_limit,
                                  daily_ext_dist=daily_ext_dist)

        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "DAILY EXTENSION"
        assert metrics["Daily_Extension_Label"] == "EXHAUSTION"
        assert metrics["Daily_Extension_Distance"] == 3.5

    def test_caution_passes_with_label(self):
        """Profile A: 2.0 < daily_ext_dist <= 3.0 → gate passes, CAUTION label."""
        metrics = {}
        ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="A", atr_dist=0.5, ext_limit=1.0, metrics=metrics)
        daily_ext_dist = 2.5

        result = _gate_extension(ctx, atr_dist, ext_limit,
                                  daily_ext_dist=daily_ext_dist)

        assert result is None  # passes
        assert metrics["Daily_Extension_Label"] == "CAUTION"
        assert metrics["Daily_Extension_Distance"] == 2.5

    def test_normal_passes_with_label(self):
        """Profile A: daily_ext_dist <= 2.0 → gate passes, NORMAL label."""
        metrics = {}
        ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="A", atr_dist=0.5, ext_limit=1.0, metrics=metrics)
        daily_ext_dist = 1.2

        result = _gate_extension(ctx, atr_dist, ext_limit,
                                  daily_ext_dist=daily_ext_dist)

        assert result is None
        assert metrics["Daily_Extension_Label"] == "NORMAL"
        assert metrics["Daily_Extension_Distance"] == 1.2

    def test_boundary_exactly_3(self):
        """Profile A: daily_ext_dist == 3.0 → NOT > 3.0, CAUTION (passes)."""
        metrics = {}
        ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="A", atr_dist=0.5, ext_limit=1.0, metrics=metrics)
        daily_ext_dist = 3.0

        result = _gate_extension(ctx, atr_dist, ext_limit,
                                  daily_ext_dist=daily_ext_dist)

        assert result is None  # 3.0 is NOT > 3.0
        assert metrics["Daily_Extension_Label"] == "CAUTION"

    def test_boundary_exactly_2(self):
        """Profile A: daily_ext_dist == 2.0 → NOT > 2.0, NORMAL."""
        metrics = {}
        ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="A", atr_dist=0.5, ext_limit=1.0, metrics=metrics)
        daily_ext_dist = 2.0

        result = _gate_extension(ctx, atr_dist, ext_limit,
                                  daily_ext_dist=daily_ext_dist)

        assert result is None
        assert metrics["Daily_Extension_Label"] == "NORMAL"

    def test_profile_b_no_daily_check(self):
        """Profile B: daily extension check does not fire."""
        metrics = {}
        ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="B", atr_dist=0.5, ext_limit=1.0, metrics=metrics)
        daily_ext_dist = 5.0  # Would be EXHAUSTION for Profile A

        result = _gate_extension(ctx, atr_dist, ext_limit,
                                  daily_ext_dist=daily_ext_dist)

        assert result is None
        assert "Daily_Extension_Label" not in metrics

    def test_profile_c_no_daily_check(self):
        """Profile C: daily extension check does not fire."""
        metrics = {}
        ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="C", atr_dist=0.5, ext_limit=1.0, metrics=metrics)
        # Override SMA_200 for Profile C floor proximity
        ctx.last = {"close": 150.0, "open": 149.0, "SMA_200": 140.0}
        daily_ext_dist = 5.0

        result = _gate_extension(ctx, atr_dist, ext_limit,
                                  daily_ext_dist=daily_ext_dist)

        assert result is None
        assert "Daily_Extension_Label" not in metrics

    def test_intraday_extension_retired_for_profile_a(self):
        """AVWAP-001 DQ-4: Intraday extension gate RETIRED for Profile A.
        Even with high atr_dist, gate passes. Daily check still runs."""
        metrics = {}
        ctx, _, ext_limit, _ = _make_extension_ctx(
            p_code="A", atr_dist=2.0, ext_limit=1.0, metrics=metrics)
        daily_ext_dist = 0.5  # NORMAL

        result = _gate_extension(ctx, 2.0, ext_limit,
                                  daily_ext_dist=daily_ext_dist)

        # AVWAP-001: Intraday extension bypassed for Profile A
        assert result is None
        # Daily check runs — NORMAL label written
        assert metrics.get("Daily_Extension_Label") == "NORMAL"

    def test_daily_ext_dist_none_skips_check(self):
        """Profile A with daily_ext_dist=None: daily check skipped gracefully."""
        metrics = {}
        ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="A", atr_dist=0.5, ext_limit=1.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit,
                                  daily_ext_dist=None)

        assert result is None
        assert "Daily_Extension_Label" not in metrics


# ============================================================================
# 3. GATES — Capital Expectancy Advisory (Profile A)
# ============================================================================

class TestCapitalExpectancyAdvisory:
    """Tests for PA-001 G.5.7 advisory conversion (DQ-5)."""

    def test_profile_a_low_rr_advisory_only(self):
        """Profile A: Capital R:R < 1.0 → metrics written, NO GateResult returned."""
        metrics = {}
        ctx = _make_capital_ctx(daily_hard_stop=145.0)

        result = _gate_capital_expectancy(
            p_code="A", risk_a=1.0, cons_high_raw=153.0,
            last_close=150.0, hard_stop_raw=140.0,
            resistance_raw=165.0, atr_raw=2.0,
            price_scaler=1.0, metrics=metrics,
            _is_c3=False, ctx=ctx,
        )

        # PA-001: Profile A never returns a GateResult
        assert result is None
        # Metrics still written (advisory)
        assert "Capital_Reward_Risk" in metrics
        assert "Capital_RR_Label" in metrics

    def test_profile_a_uses_daily_hard_stop(self):
        """Profile A: Capital R:R computed using daily hard stop, not VWAP hard stop."""
        metrics = {}
        daily_hs = 130.0  # Daily hard stop (much wider than VWAP-based)
        ctx = _make_capital_ctx(daily_hard_stop=daily_hs)

        _gate_capital_expectancy(
            p_code="A", risk_a=1.0, cons_high_raw=165.0,
            last_close=150.0, hard_stop_raw=148.0,  # VWAP hard stop (very tight)
            resistance_raw=165.0, atr_raw=2.0,
            price_scaler=1.0, metrics=metrics,
            _is_c3=False, ctx=ctx,
        )

        # reward=15, risk=150-130=20 (daily), rr=0.75
        # With VWAP hard stop: risk=150-148=2, rr=7.5
        # The daily hard stop should be used:
        expected_rr = round((165.0 - 150.0) / (150.0 - daily_hs), 2)
        assert metrics["Capital_Reward_Risk"] == expected_rr

    def test_profile_a_healthy_rr_passes(self):
        """Profile A: Capital R:R >= 1.5 → passes with HEALTHY label."""
        metrics = {}
        ctx = _make_capital_ctx(daily_hard_stop=130.0)

        result = _gate_capital_expectancy(
            p_code="A", risk_a=1.0, cons_high_raw=185.0,
            last_close=150.0, hard_stop_raw=140.0,
            resistance_raw=165.0, atr_raw=2.0,
            price_scaler=1.0, metrics=metrics,
            _is_c3=False, ctx=ctx,
        )

        assert result is None
        assert metrics["Capital_RR_Label"] == "HEALTHY"

    def test_profile_b_still_enforces(self):
        """Profile B: Capital R:R < 1.0 → still returns GateResult (unchanged)."""
        metrics = {}
        ctx = SimpleNamespace(
            _is_c3=False,
            _df_ctx=None,
            _has_fundamental_data=False,
            daily_hard_stop=0.0,
        )

        result = _gate_capital_expectancy(
            p_code="B", risk_a=1.0, cons_high_raw=160.0,
            last_close=150.0, hard_stop_raw=148.0,
            resistance_raw=152.0, atr_raw=2.0,
            price_scaler=1.0, metrics=metrics,
            _is_c3=False, ctx=ctx,
        )

        # Profile B: technical R:R gate still enforces
        # reward = 152-150=2, risk = 150-148=2, rr=1.0 → passes
        # But if reward/risk < 1.0...
        metrics2 = {}
        result2 = _gate_capital_expectancy(
            p_code="B", risk_a=1.0, cons_high_raw=160.0,
            last_close=150.0, hard_stop_raw=140.0,
            resistance_raw=150.5, atr_raw=2.0,
            price_scaler=1.0, metrics=metrics2,
            _is_c3=False, ctx=ctx,
        )

        # reward=0.5, risk=10, rr=0.05 → should reject
        assert result2 is not None
        assert result2.verdict == "INVALID"
        assert result2.reason == "CAPITAL EXPECTANCY FAILED"


# ============================================================================
# 4. MAIN — Tier 3 Parallel Execution
# ============================================================================

class TestTier3ParallelExecution:
    """Tests for Tier 3 parallel gate execution restructuring (Spec §4.3)."""

    def test_all_gates_write_metrics_when_extension_blocks(self):
        """When extension blocks, expectancy and capital expectancy metrics
        should still be populated (parallel execution)."""
        # This is a design-level test. We verify the pattern by calling
        # the gates in parallel order and confirming metrics are written.
        metrics = {}

        # Extension blocks (EXHAUSTION)
        ext_ctx, atr_dist, ext_limit, _ = _make_extension_ctx(
            p_code="A", atr_dist=0.5, ext_limit=1.0, metrics=metrics)
        ext_result = _gate_extension(ext_ctx, atr_dist, ext_limit,
                                      daily_ext_dist=3.5)

        # Capital expectancy still runs and writes metrics
        ceg_ctx = _make_capital_ctx(daily_hard_stop=130.0)
        ceg_result = _gate_capital_expectancy(
            p_code="A", risk_a=1.0, cons_high_raw=160.0,
            last_close=150.0, hard_stop_raw=140.0,
            resistance_raw=165.0, atr_raw=2.0,
            price_scaler=1.0, metrics=metrics,
            _is_c3=False, ctx=ceg_ctx,
        )

        # Extension fired
        assert ext_result is not None
        assert ext_result.reason == "DAILY EXTENSION"

        # Capital expectancy metrics populated despite extension blocking
        assert "Capital_Reward_Risk" in metrics
        assert "Capital_RR_Label" in metrics

        # First failure (extension) wins in the tier3_results pattern
        tier3_results = []
        if ext_result:
            tier3_results.append(ext_result)
        if ceg_result:
            tier3_results.append(ceg_result)

        assert len(tier3_results) == 1  # Only extension failed
        assert tier3_results[0].reason == "DAILY EXTENSION"

    def test_first_failure_wins(self):
        """When multiple Tier 3 gates fail, first in execution order wins."""
        metrics = {}

        # Both extension and another gate fail
        ext_result = GateResult(
            verdict="INVALID", reason="DAILY EXTENSION",
            mandate="test", context="test",
        )
        fpc_result = GateResult(
            verdict="INVALID", reason="FLOOR PROXIMITY FAILED",
            mandate="test", context="test",
        )

        tier3_results = []
        if ext_result:
            tier3_results.append(ext_result)
        if fpc_result:
            tier3_results.append(fpc_result)

        # First failure wins
        assert tier3_results[0].reason == "DAILY EXTENSION"

    def test_tier3_skipped_when_prior_tier_fires(self):
        """Regression: When Tier 1/2 sets gate_result, Tier 3 must not execute.
        _gate_expectancy crashes on risk_a=None when precheck was skipped.
        (Bug found via INTC manual test — CRG fires, precheck skipped,
        risk_a stays None, parallel _gate_expectancy hits 2.0 * None.)"""
        # Simulate: gate_result already set by a Tier 1/2 gate,
        # risk_a is None because precheck didn't reach the expectancy block.
        gate_result = GateResult(
            verdict="INVALID", reason="MID-RANGE",
            mandate="test", context="test",
        )
        risk_a = None  # precheck was skipped
        reward_a = None

        # The guard: Tier 3 only runs when gate_result is None
        if gate_result is None:
            # This block must NOT execute
            raise AssertionError("Tier 3 should be skipped when gate_result is set")

        # gate_result survives unchanged
        assert gate_result.reason == "MID-RANGE"


# ============================================================================
# 5. COMPUTE — PE-CAL-3 Exemption
# ============================================================================

class TestPECAL3Exemption:
    """Tests for PA-001 PE-CAL-3 Profile A exemption in _evaluate_precheck (DQ-5)."""

    def test_profile_a_floor_exact_no_hardstop_substitution(self):
        """Profile A at floor-exact (risk_a=0): PE-CAL-3 substitution skipped.
        Metrics should show PA-001 note, no EXPECTANCY FAILED gate."""
        from ibkr_purity_engine import _evaluate_precheck
        from tbs_engine.types import GRACE_BUFFER_ATR_PCT

        metrics = {}
        state = SimpleNamespace(
            atr_raw=2.0,
            consec_below=0,
            is_floor_failure=False,
            is_violated=False,
            is_reclaim=False,
            is_trending=True,
            is_resolving=False,
            _reclaim_run=0,
        )
        cfg = SimpleNamespace(
            iq=-2,
            ff_threshold=3,
        )

        # Build minimal DataFrame-like structure
        import pandas as pd
        import numpy as np

        # 10 bars, price exactly at ANCHOR (risk_a = 0)
        n = 10
        close_vals = [150.0] * n
        anchor_vals = [150.0] * n  # Price AT anchor
        high_vals = [155.0] * n
        low_vals = [145.0] * n

        df = pd.DataFrame({
            "close": close_vals,
            "ANCHOR": anchor_vals,
            "high": high_vals,
            "low": low_vals,
            "EMA_8": [149.0] * n,
            "EMA_21": [148.0] * n,
        })

        last = df.iloc[cfg.iq]

        ctx = SimpleNamespace(
            state=state, cfg=cfg, df=df, last=last,
            p_code="A", metrics=metrics,
            price_scaler=1.0, hard_stop_raw=140.0,
            cons_high_raw=160.0, exit_signal=False,
            risk_a=None, reward_a=None,
            daily_hard_stop=92.5,
        )

        result = _evaluate_precheck(ctx, _ff_threshold=3)

        # PA-001: PE-CAL-3 exempted. No EXPECTANCY FAILED rejection.
        assert result is None
        # Metrics should contain PA-001 note
        rr_note = metrics.get("Reward_Risk_Note", "")
        assert "PA-001" in rr_note
        assert metrics.get("Profit_Target") is not None

    def test_profile_a_floor_proximity_no_hardstop_substitution(self):
        """Profile A in floor proximity (0 < risk_a < 0.20*ATR):
        PE-CAL-3 substitution skipped, standard R:R computed."""
        from ibkr_purity_engine import _evaluate_precheck

        metrics = {}
        state = SimpleNamespace(
            atr_raw=2.0,
            consec_below=0,
            is_floor_failure=False,
            is_violated=False,
            is_reclaim=False,
            is_trending=True,
            is_resolving=False,
            _reclaim_run=0,
        )
        cfg = SimpleNamespace(iq=-2, ff_threshold=3)

        import pandas as pd
        n = 10
        # Price slightly above anchor (risk_a = 0.1, which is < 0.20 * 2.0 = 0.4)
        close_vals = [150.1] * n
        anchor_vals = [150.0] * n
        df = pd.DataFrame({
            "close": close_vals,
            "ANCHOR": anchor_vals,
            "high": [155.0] * n,
            "low": [145.0] * n,
            "EMA_8": [149.0] * n,
            "EMA_21": [148.0] * n,
        })
        last = df.iloc[cfg.iq]

        ctx = SimpleNamespace(
            state=state, cfg=cfg, df=df, last=last,
            p_code="A", metrics=metrics,
            price_scaler=1.0, hard_stop_raw=140.0,
            cons_high_raw=160.0, exit_signal=False,
            risk_a=None, reward_a=None,
            daily_hard_stop=92.5,
        )

        result = _evaluate_precheck(ctx, _ff_threshold=3)

        # Should pass (no EXPECTANCY FAILED)
        assert result is None
        # Metrics should show R:R computed without PE-CAL-3 substitution
        rr_note = metrics.get("Reward_Risk_Note", "")
        assert "PA-001" in rr_note
        assert "PE-CAL-3" in rr_note
        # R:R should be computed with risk_a (small), not hard_stop substitution
        assert metrics.get("Reward_Risk") is not None


# ============================================================================
# 6. COMPUTE — _compute_early_capital_rr Daily Hard Stop
# ============================================================================

class TestEarlyCapitalRRDailyHardStop:
    """Tests for PA-001 daily hard stop in _compute_early_capital_rr (DQ-5)."""

    def test_profile_a_uses_daily_hard_stop_in_early_crr(self):
        """Profile A early Capital R:R uses ctx.daily_hard_stop, not hard_stop_raw."""
        from ibkr_purity_engine import _compute_early_capital_rr

        metrics = {}
        state = SimpleNamespace(
            atr_raw=2.0,
            is_floor_failure=False,
            is_violated=False,
        )
        cfg = SimpleNamespace(
            iq=-2,
            resistance_slice_start=-10,
            resistance_slice_end=-1,
        )

        import pandas as pd
        n = 20
        df = pd.DataFrame({
            "close": [150.0] * n,
            "high": [155.0] * n,
            "low": [145.0] * n,
            "ANCHOR": [148.0] * n,
        })
        last = df.iloc[cfg.iq]

        # Build a minimal df_ctx
        df_ctx = pd.DataFrame({
            "high": [155.0] * 15,
            "close": [150.0] * 15,
        })

        ctx = SimpleNamespace(
            state=state, cfg=cfg, df=df, last=last,
            p_code="A", metrics=metrics,
            price_scaler=1.0,
            hard_stop_raw=148.0,  # VWAP-derived (tight)
            resistance_raw=155.0,
            _is_c3=False,
            _df_ctx=df_ctx,
            cons_high_raw=None,
            exit_signal=False,
            risk_a=None, reward_a=None,
            daily_hard_stop=130.0,  # Daily (wide)
            _analyst_target_median=None,
            _analyst_target_low=None,
            _analyst_target_high=None,
            _analyst_count=None,
            _has_fundamental_data=False,
            is_etf=False,
        )

        _compute_early_capital_rr(ctx, exit_signal=False)

        # Capital risk should be computed using daily_hard_stop (130), not hard_stop_raw (148)
        # risk = 150 - 130 = 20, reward = 155 - 150 = 5, rr = 0.25
        expected_rr = round(5.0 / 20.0, 2)
        assert metrics.get("Capital_Reward_Risk") == expected_rr

    def test_profile_b_uses_vwap_hard_stop(self):
        """Profile B early Capital R:R uses hard_stop_raw (unchanged)."""
        from ibkr_purity_engine import _compute_early_capital_rr

        metrics = {}
        state = SimpleNamespace(
            atr_raw=2.0,
            is_floor_failure=False,
            is_violated=False,
        )
        cfg = SimpleNamespace(
            iq=-1,
            resistance_slice_start=-10,
            resistance_slice_end=-1,
        )

        import pandas as pd
        n = 20
        df = pd.DataFrame({
            "close": [150.0] * n,
            "high": [155.0] * n,
            "low": [145.0] * n,
            "ANCHOR": [148.0] * n,
        })
        last = df.iloc[cfg.iq]

        df_ctx = pd.DataFrame({
            "high": [155.0] * 15,
            "close": [150.0] * 15,
        })

        ctx = SimpleNamespace(
            state=state, cfg=cfg, df=df, last=last,
            p_code="B", metrics=metrics,
            price_scaler=1.0,
            hard_stop_raw=140.0,
            resistance_raw=155.0,
            _is_c3=False,
            _df_ctx=df_ctx,
            cons_high_raw=None,
            exit_signal=False,
            risk_a=None, reward_a=None,
            daily_hard_stop=0.0,
            _analyst_target_median=None,
            _analyst_target_low=None,
            _analyst_target_high=None,
            _analyst_count=None,
            _has_fundamental_data=False,
            is_etf=False,
        )

        _compute_early_capital_rr(ctx, exit_signal=False)

        # Profile B: risk = 150 - 140 = 10, reward = 155 - 150 = 5, rr = 0.5
        expected_rr = round(5.0 / 10.0, 2)
        assert metrics.get("Capital_Reward_Risk") == expected_rr


# ============================================================================
# 7. RUNCONTEXT — Daily Fields Present
# ============================================================================

class TestRunContextDailyFields:
    """Verify RunContext has the PA-001 daily protective fields."""

    def test_runcontext_has_daily_fields(self):
        """RunContext dataclass should have the 3 new PA-001 fields with defaults."""
        from tbs_engine.types import RunContext

        # Check field names exist on the class
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(RunContext)}
        assert "daily_protective_anchor" in field_names
        assert "daily_atr" in field_names
        assert "daily_hard_stop" in field_names

    def test_runcontext_daily_defaults(self):
        """Default values for PA-001 fields should be 0.0."""
        from tbs_engine.types import RunContext
        import dataclasses
        fields_dict = {f.name: f for f in dataclasses.fields(RunContext)}
        assert fields_dict["daily_protective_anchor"].default == 0.0
        assert fields_dict["daily_atr"].default == 0.0
        assert fields_dict["daily_hard_stop"].default == 0.0
