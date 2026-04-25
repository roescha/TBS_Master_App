"""Unit tests for BUGR-006 v2.0: Profile B Breakout R:R Fix.

Test matrix per BUGR-006 v2.0 Spec §5.2 (16 categories total):
  1.              BRK-active + MM available                                              (FAIL/PASS)
  2.              BRK-active + MM null + weekly fallback                                 (FAIL/PASS)
  3.              BRK-active + MM null + weekly null + ATR fallback                      (FAIL/PASS)
  4.              BRK-active + all fallbacks exhausted                                   (FAIL/PASS)
  5.              BRK-active + target at/below entry                                     (FAIL/PASS)
  6.              BRK-active + price at/below tight stop                                 (FAIL/PASS)
  7.              BRK-active + C-3 conjunction                                           (PASS/PASS: C-3 never activates BRK)
  8.              BRK-inactive + resistance suppressed (regression)                      (PASS/PASS)
  9.              BRK-inactive + standard pullback (regression)                          (PASS/PASS)
  10.             BRK-inactive + floor-broken (regression)                               (PASS/PASS)
  11.             BRK-inactive + floor-exact (regression)                                (PASS/PASS)
  12.             Profile A BRK (regression)                                             (PASS/PASS)
  13.             Profile C regression                                                   (PASS/PASS)
  14.             TXN-B reproduction                                                     (FAIL/PASS: 0.06 → spec-compliant)
  T-REACH:       End-to-end reachability test (MANDATORY, NEW in v2.0)                  (FAIL/PASS)
  T-FRR-COEXIST: FRR-001 coexistence (MANDATORY, NEW in v2.0)                           (FAIL/PASS)

Differential-verification contract:
  - Classes 1-6, T-REACH, T-FRR-COEXIST must FAIL against pre-fix code, PASS against post-fix.
  - Classes 8-13 must PASS both pre-fix and post-fix (regression assurance).
  - Class 7 is dead-code-by-design (C-3 never activates BRK per compute.py:99-100).
  - Class 14 reproduces the S125 TXN-B 0.06 emission.

Implementation: Calls the REAL _compute_early_capital_rr function in tbs_engine.compute.
T-REACH additionally calls _detect_breakout_model first (matching main.py:334 → main.py:348
pipeline call-order) to verify reachability through the writer-reader contract.
"""

import sys
import os as _os
import importlib.util as _ilu
from types import SimpleNamespace

import pytest
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Direct module load (avoids ib_insync dependency chain via tbs_engine/__init__.py)
# Mirrors the pattern used by test_frr001_fundamental_rr.py.
# ---------------------------------------------------------------------------
_engine_dir = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "tbs_engine",
)


def _load_mod(name, path):
    # Idempotent: if an earlier test already imported this module normally,
    # reuse the existing sys.modules entry instead of overwriting it. Overwriting
    # replaces class identities (e.g., tbs_engine.types.GateResult), causing
    # isinstance() checks in later-running test files to return False against
    # objects created by code paths that captured the original class reference.
    # This pattern was introduced to prevent test_ffd001_floor_failure_context.py
    # and similar downstream tests from failing with `isinstance(X, type(X)) == False`
    # due to sys.modules pollution from this file's dynamic module loading.
    if name in sys.modules:
        return sys.modules[name]
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-register a stub for tbs_engine package so compute.py's
# `from tbs_engine.types import ...` works without triggering __init__.py.
if "tbs_engine" not in sys.modules:
    import types as _types_mod
    sys.modules["tbs_engine"] = _types_mod.ModuleType("tbs_engine")

_types = _load_mod("tbs_engine.types", _os.path.join(_engine_dir, "types.py"))
_helpers = _load_mod("tbs_engine.helpers", _os.path.join(_engine_dir, "helpers.py"))
_compute = _load_mod("tbs_engine.compute", _os.path.join(_engine_dir, "compute.py"))

_compute_early_capital_rr = _compute._compute_early_capital_rr
_detect_breakout_model = _compute._detect_breakout_model


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_state(
    atr_raw=1.0,
    di_plus=30.0,
    di_minus=15.0,
    entry_trending=True,
    floor_raw=0.0,
):
    """Build a minimal StateBundle-like namespace."""
    return SimpleNamespace(
        atr_raw=atr_raw,
        di_plus=di_plus,
        di_minus=di_minus,
        _entry_trending=entry_trending,
        floor_raw=floor_raw,
        # Extra fields that _compute_early_capital_rr may touch via state.*
        is_trending=True,
        is_resolving=False,
        is_reclaim=False,
        is_violated=False,
        is_floor_failure=False,
        adx_t=25.0,
        adx_t1=24.0,
    )


def _make_cfg():
    """Build a minimal ProfileConfig-like namespace."""
    return SimpleNamespace(
        resistance_slice_start=-11,
        resistance_slice_end=-1,
    )


def _make_df_context(n=15, high_value=105.0, low_value=95.0):
    """Build a minimal daily context DataFrame (used for PE-41 weekly ceiling)."""
    return pd.DataFrame({
        "high": [high_value] * n,
        "low":  [low_value] * n,
        "close": [(high_value + low_value) / 2] * n,
    })


def _make_primary_df(n=30, high_value=105.0, low_value=95.0, close_value=100.0, volume=1_000_000):
    """Build a minimal primary-frame DataFrame for MM target + general ctx."""
    return pd.DataFrame({
        "high":   [high_value]  * n,
        "low":    [low_value]   * n,
        "close":  [close_value] * n,
        "open":   [close_value] * n,
        "volume": [volume]      * n,
    })


def _make_ctx(
    p_code="B",
    is_etf=False,
    is_c3=False,
    close=100.0,
    anchor=95.0,
    resistance_raw=99.0,
    hard_stop_raw=92.0,
    price_scaler=1.0,
    atr_raw=1.0,
    df_ctx=None,
    primary_df=None,
    # BRK flags (simulating post-_detect_breakout_model state for direct unit tests)
    breakout_model_active=False,
    brk_tight_stop_raw=None,
    brk_mm_target_raw=None,
    brk_new_support_raw=None,
    # Volume for Path A fresh-breakout detection
    volume=1_000_000,
    vol_sma_20=500_000,  # RVOL = 2.0, above _BRK_SBO_VOLUME_THRESHOLD of 1.5
    # Analyst consensus (for T-FRR-COEXIST)
    analyst_target_median=None,
    analyst_target_low=None,
    analyst_target_high=None,
    analyst_count=None,
):
    """Build a minimal ctx for _compute_early_capital_rr + _detect_breakout_model.

    The BRK flag params (breakout_model_active, brk_tight_stop_raw, brk_mm_target_raw)
    are used for direct unit tests of the BUGR-006 v2.0 block. Tests that exercise
    the full pipeline (T-REACH) leave them at defaults and call _detect_breakout_model
    explicitly so the real writer populates them.
    """
    if primary_df is None:
        primary_df = _make_primary_df(close_value=close, high_value=max(close + 0.5, resistance_raw + 0.5))

    last = primary_df.iloc[-1].copy()
    last["close"] = close
    last["ANCHOR"] = anchor
    last["volume"] = volume
    last["vol_sma_20"] = vol_sma_20

    ctx = SimpleNamespace(
        # Identity / profile
        p_code=p_code,
        is_etf=is_etf,
        _is_c3=is_c3,
        # State
        state=_make_state(atr_raw=atr_raw),
        cfg=_make_cfg(),
        # Price fields
        price_scaler=price_scaler,
        actual_price=close / price_scaler,
        structural_floor_raw=anchor,
        hard_stop_raw=hard_stop_raw,
        resistance_raw=resistance_raw,
        # Data frames
        df=primary_df,
        last=last,
        metrics={},
        _df_ctx=df_ctx,
        # BRK detector needs these
        bars_per_day=1.0,
        window_count=0,
        window_limit=10,
        # BRK writer fields (pre-populated for direct unit tests; overwritten by
        # _detect_breakout_model when called explicitly)
        _breakout_model_active=breakout_model_active,
        _brk_tight_stop_raw=brk_tight_stop_raw,
        _brk_mm_target_raw=brk_mm_target_raw,
        _brk_new_support_raw=brk_new_support_raw,
        _brk_catastrophic_stop_raw=None,
        _breakout_thesis_failed=False,
        _brk_failed_new_support=None,
        # FRR-001 analyst data
        _analyst_target_median=analyst_target_median,
        _analyst_target_low=analyst_target_low,
        _analyst_target_high=analyst_target_high,
        _analyst_count=analyst_count,
        # Misc fields potentially touched
        cons_high_raw=None,
        mm_target_raw=None,
        daily_atr=0.0,
    )
    return ctx


# ===========================================================================
# CATEGORY 1: BRK-active + MM available  (FAIL/PASS)
# ===========================================================================

def test_01_brk_active_mm_available():
    """Spec §4.4 default path: Reward = MM - entry, Risk = entry - tight_stop.
    Expected: Profit_Target_Source = 'MEASURED_MOVE (BRK-001 post-breakout target)'.

    Reward_Risk_Note is nulled in metrics by PE-31 (L1022) and returned as the
    2nd tuple element; Phase 4 in main.py restores it downstream.
    """
    ctx = _make_ctx(
        close=100.0,
        anchor=95.0,
        atr_raw=1.0,
        breakout_model_active=True,
        brk_tight_stop_raw=94.0,      # new_support 95 - 1.0 * ATR
        brk_mm_target_raw=115.0,       # MM target
    )
    _resistance_note, _reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    assert m["Profit_Target"] == 115.0
    assert m["Profit_Target_Source"] == "MEASURED_MOVE (BRK-001 post-breakout target)"
    # Reward = 115 - 100 = 15;  Risk = 100 - 94 = 6;  R:R = 2.5
    assert m["Reward_Risk"] == 2.5
    assert m["Expectancy_Threshold"] == 2.0
    assert _reward_risk_note is not None and _reward_risk_note.startswith("BREAKOUT MODEL (BRK-001 §4.4):")
    assert "Fallback:" not in _reward_risk_note


# ===========================================================================
# CATEGORY 2: BRK-active + MM null + weekly fallback  (FAIL/PASS)
# ===========================================================================

def test_02_brk_active_mm_null_weekly_fallback():
    """Spec §8.1 weekly-ceiling fallback: MM null → weekly 10-bar high.
    Reward = weekly_ceiling - entry, Risk still uses tight_stop.
    """
    df_ctx = _make_df_context(n=15, high_value=110.0, low_value=95.0)
    ctx = _make_ctx(
        close=100.0,
        anchor=95.0,
        atr_raw=1.0,
        df_ctx=df_ctx,
        breakout_model_active=True,
        brk_tight_stop_raw=94.0,
        brk_mm_target_raw=None,        # MM null → fallback to weekly
    )
    _resistance_note, _reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    assert m["Profit_Target"] == 110.0
    assert m["Profit_Target_Source"] == "WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)"
    # Reward = 110 - 100 = 10;  Risk = 100 - 94 = 6;  R:R ≈ 1.67
    assert m["Reward_Risk"] == 1.67
    assert _reward_risk_note is not None
    assert "Fallback: MM target unavailable; using weekly 10-bar high" in _reward_risk_note


# ===========================================================================
# CATEGORY 3: BRK-active + MM null + weekly null + ATR fallback  (FAIL/PASS)
# ===========================================================================

def test_03_brk_active_mm_null_weekly_null_atr_fallback():
    """Spec §8.1 ATR projection fallback: Reward = last['ANCHOR'] + 3.0 * daily_atr - entry.
    Weekly ceiling ≤ close triggers fallback to ATR; risk denominator unchanged.
    """
    # Weekly ceiling below close → skip weekly fallback
    df_ctx = _make_df_context(n=15, high_value=99.0, low_value=95.0)
    ctx = _make_ctx(
        close=100.0,
        anchor=95.0,
        atr_raw=2.0,
        df_ctx=df_ctx,
        breakout_model_active=True,
        brk_tight_stop_raw=93.0,
        brk_mm_target_raw=None,
    )
    _resistance_note, _reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    # Expected ATR target: 95 + 3.0 * 2.0 = 101.0
    assert m["Profit_Target"] == 101.0
    assert m["Profit_Target_Source"] == "ATR_PROJECTION (BRK-001 §8.1 MM-null fallback)"
    # Reward = 101 - 100 = 1;  Risk = 100 - 93 = 7;  R:R ≈ 0.14
    assert m["Reward_Risk"] == 0.14
    assert _reward_risk_note is not None
    assert "Fallback: MM + weekly unavailable; using RWD-001 ATR projection" in _reward_risk_note


# ===========================================================================
# CATEGORY 4: BRK-active + all fallbacks exhausted  (FAIL/PASS)
# ===========================================================================

def test_04_brk_active_all_fallbacks_exhausted():
    """Spec §8.1 terminal case: MM null, weekly ≤ close, daily_atr unavailable.
    Expected: Reward_Risk = None, Profit_Target = None, explanatory note.
    """
    df_ctx = _make_df_context(n=15, high_value=99.0, low_value=95.0)
    ctx = _make_ctx(
        close=100.0,
        anchor=95.0,
        atr_raw=0.0,   # <- ATR unavailable kills fallback 2
        df_ctx=df_ctx,
        breakout_model_active=True,
        brk_tight_stop_raw=94.0,
        brk_mm_target_raw=None,
    )
    _resistance_note, _reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    assert m["Profit_Target"] is None
    assert m["Profit_Target_Source"] == "BRK-001 post-breakout (fallbacks exhausted)"
    assert m["Reward_Risk"] is None
    assert _reward_risk_note is not None
    assert "fallback exhaustion" in _reward_risk_note


# ===========================================================================
# CATEGORY 5: BRK-active + target at/below entry  (FAIL/PASS)
# ===========================================================================

def test_05_brk_active_target_at_or_below_entry():
    """Upside-exhausted handling: target ≤ entry → Reward_Risk = None with 'no upside' note."""
    ctx = _make_ctx(
        close=100.0,
        anchor=95.0,
        atr_raw=1.0,
        breakout_model_active=True,
        brk_tight_stop_raw=94.0,
        brk_mm_target_raw=99.0,        # below entry
    )
    _resistance_note, _reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    assert m["Profit_Target"] is None
    assert m["Profit_Target_Source"] == "MEASURED_MOVE (BRK-001 post-breakout target)"
    assert m["Reward_Risk"] is None
    assert _reward_risk_note is not None
    assert "no upside reward available" in _reward_risk_note


# ===========================================================================
# CATEGORY 6: BRK-active + price at/below tight stop (risk ≤ 0)  (FAIL/PASS)
# ===========================================================================

def test_06_brk_active_price_at_or_below_tight_stop():
    """Thesis-stress handling: close ≤ tight_stop → risk ≤ 0 → Reward_Risk = None.

    Reward_Risk_Note is nulled in metrics by PE-31 (compute.py:~937-940) and returned
    as the 2nd tuple element; read from the return value, not from metrics.
    """
    ctx = _make_ctx(
        close=100.0,
        anchor=95.0,
        atr_raw=1.0,
        breakout_model_active=True,
        brk_tight_stop_raw=100.0,      # equal to close → risk = 0
        brk_mm_target_raw=115.0,
    )
    _resistance_note, _reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    assert m["Profit_Target"] is None
    assert m["Reward_Risk"] is None
    assert _reward_risk_note is not None
    assert "price at or below tight stop" in _reward_risk_note
    assert "risk denominator ≤ 0" in _reward_risk_note


# ===========================================================================
# CATEGORY 7: BRK-active + C-3 conjunction  (PASS/PASS: C-3 never activates BRK)
# ===========================================================================

def test_07_c3_bypass_never_activates_brk():
    """C-3 precedence: _detect_breakout_model returns early on C-3 (compute.py:99-100).
    _breakout_model_active stays False → BUGR-006 block does not fire."""
    ctx = _make_ctx(
        p_code="B",
        is_c3=True,                    # C-3 bypass
        close=105.0,
        anchor=95.0,
        atr_raw=1.0,
        resistance_raw=100.0,
    )
    # Run the REAL detector — must early-return on C-3
    _detect_breakout_model(ctx, _window_reset_event="")
    assert ctx._breakout_model_active is False, (
        "C-3 must never activate breakout model (compute.py:99-100 early return)"
    )

    # Now run _compute_early_capital_rr — new block should not fire
    _compute_early_capital_rr(ctx, exit_signal=None)
    # Neither Reward_Risk_Note nor Profit_Target_Source should carry BREAKOUT MODEL strings
    note = ctx.metrics.get("Reward_Risk_Note")
    if note is not None:
        assert not note.startswith("BREAKOUT MODEL"), (
            "C-3 fixture must not produce a BREAKOUT MODEL note"
        )


# ===========================================================================
# CATEGORY 8: BRK-inactive + resistance suppressed (regression)  (PASS/PASS)
# ===========================================================================

def test_08_brk_inactive_resistance_suppressed_regression():
    """Regression: BRK-inactive Profile B path — new block must not fire.
    The output.py PE-41 weekly-escalation branch is outside this function's scope;
    we verify that the BUGR-006 v2.0 block itself leaves metrics alone."""
    ctx = _make_ctx(
        p_code="B",
        breakout_model_active=False,   # BRK inactive
        brk_tight_stop_raw=None,
        brk_mm_target_raw=None,
    )
    _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    # Nothing from the new BRK block should have been written
    note = m.get("Reward_Risk_Note")
    if note is not None:
        assert not note.startswith("BREAKOUT MODEL")


# ===========================================================================
# CATEGORY 9: BRK-inactive + standard pullback (regression)  (PASS/PASS)
# ===========================================================================

def test_09_brk_inactive_standard_pullback_regression():
    """Regression: standard pullback on Profile B (no BRK, no suppression)."""
    ctx = _make_ctx(
        p_code="B",
        close=100.0,
        anchor=95.0,
        resistance_raw=105.0,
        breakout_model_active=False,
    )
    _compute_early_capital_rr(ctx, exit_signal=None)
    note = ctx.metrics.get("Reward_Risk_Note")
    if note is not None:
        assert not note.startswith("BREAKOUT MODEL")


# ===========================================================================
# CATEGORY 10: BRK-inactive + floor-broken (regression)  (PASS/PASS)
# ===========================================================================

def test_10_brk_inactive_floor_broken_regression():
    """Regression: floor-broken path (close < SMA_50). BUGR-006 block must not fire."""
    ctx = _make_ctx(
        p_code="B",
        close=90.0,   # below anchor
        anchor=95.0,
        breakout_model_active=False,
    )
    _compute_early_capital_rr(ctx, exit_signal=None)
    note = ctx.metrics.get("Reward_Risk_Note")
    if note is not None:
        assert not note.startswith("BREAKOUT MODEL")


# ===========================================================================
# CATEGORY 11: BRK-inactive + floor-exact (regression)  (PASS/PASS)
# ===========================================================================

def test_11_brk_inactive_floor_exact_regression():
    """Regression: floor-exact path (risk_b == 0). BUGR-006 block must not fire."""
    ctx = _make_ctx(
        p_code="B",
        close=95.0,   # exactly equal to anchor
        anchor=95.0,
        breakout_model_active=False,
    )
    _compute_early_capital_rr(ctx, exit_signal=None)
    note = ctx.metrics.get("Reward_Risk_Note")
    if note is not None:
        assert not note.startswith("BREAKOUT MODEL")


# ===========================================================================
# CATEGORY 12: Profile A BRK (regression)  (PASS/PASS)
# ===========================================================================

def test_12_profile_a_brk_regression():
    """Regression: Profile A BRK — the new BUGR-006 block's top-level guard
    (p_code == 'B') gates A out, so compute.py:1215 (Profile A's own BRK block
    in _evaluate_precheck) remains the sole writer for Profile A."""
    ctx = _make_ctx(
        p_code="A",                    # Profile A, not B
        close=100.0,
        anchor=95.0,
        breakout_model_active=True,
        brk_tight_stop_raw=94.0,
        brk_mm_target_raw=115.0,
    )
    _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    # BUGR-006 block must NOT have fired on Profile A — its guard is p_code == "B"
    note = m.get("Reward_Risk_Note")
    if note is not None:
        assert not note.startswith("BREAKOUT MODEL (BRK-001 §4.4)")


# ===========================================================================
# CATEGORY 13: Profile C regression  (PASS/PASS)
# ===========================================================================

def test_13_profile_c_regression():
    """Regression: Profile C — BUGR-006 block must not fire (p_code == 'C' fails guard)."""
    ctx = _make_ctx(
        p_code="C",
        close=100.0,
        anchor=95.0,
        breakout_model_active=True,    # even if somehow flag were True, p_code guard stops us
        brk_tight_stop_raw=94.0,
        brk_mm_target_raw=115.0,
    )
    _compute_early_capital_rr(ctx, exit_signal=None)
    note = ctx.metrics.get("Reward_Risk_Note")
    if note is not None:
        assert not note.startswith("BREAKOUT MODEL")


# ===========================================================================
# CATEGORY 14: TXN-B reproduction  (FAIL/PASS: 0.06 → spec-compliant)
# ===========================================================================

def test_14_txn_b_reproduction():
    """Reproduces S125 TXN-B defect: Profile B BREAKOUT with resistance suppressed.
    Pre-fix output.py pullback-fallback emitted 0.06 (close - SMA_50 denominator).
    Post-fix BUGR-006 v2.0 block emits spec-compliant post-breakout R:R.

    BUGR-006-LABEL-1 (Addendum #1 §2.3; IDENTIFIED S137; Low severity; OUT OF SCOPE for v2.0):
    The TXN-B fixture (resistance suppressed + weekly headroom + no fundamental) triggers
    CEG-002 blue-sky Tier 3 (compute.py:~884), which overwrites Profit_Target_Source to
    "ATR_PROJECTION (blue sky)" AFTER the BUGR-006 v2.0 write. The actual Profit_Target
    VALUE remains the BRK MM (110.0) — only the label is clobbered. Per Addendum #1 §2.5,
    we do NOT assert on Profit_Target_Source here. A future BUGR-006-LABEL-1 fix will
    restore label consistency, at which point this comment can be removed and the
    `Profit_Target_Source == "MEASURED_MOVE (BRK-001 post-breakout target)"` assertion
    re-added.
    """
    # Scenario: price slightly above old resistance; MM target available; tight stop close.
    # SMA_50 (pullback floor) is far below, which produces the 0.06-style small R:R pre-fix.
    df_ctx = _make_df_context(n=15, high_value=100.5, low_value=90.0)  # weekly high only marginally above close
    ctx = _make_ctx(
        p_code="B",
        close=100.0,
        anchor=80.0,                   # far structural floor (SMA_50)
        atr_raw=2.0,
        resistance_raw=99.5,
        df_ctx=df_ctx,
        breakout_model_active=True,
        brk_tight_stop_raw=97.5,       # new_support 99.5 - 1.0*ATR(2.0)
        brk_mm_target_raw=110.0,       # measured move target
    )
    _resistance_note, _reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    # Post-fix: Reward = 110 - 100 = 10; Risk = 100 - 97.5 = 2.5; R:R = 4.0
    # Pre-fix would have emitted ≈ (0.5 / 20.0) ≈ 0.03 (output.py pullback fallback)
    assert m["Reward_Risk"] == 4.0, (
        f"Post-fix TXN-B should emit R:R=4.0 (post-breakout), got {m['Reward_Risk']}"
    )
    # Gate-crossing assertion: pre-fix 0.06 was below the 2:1 threshold; post-fix must clear it.
    assert m["Reward_Risk"] > 2.0, (
        "Post-fix must exceed the 2:1 threshold (pre-fix 0.06 was below)"
    )
    # Profit_Target VALUE is preserved (BRK MM). Only the LABEL is overwritten downstream
    # by CEG-002 blue-sky — see BUGR-006-LABEL-1 docstring note.
    assert m["Profit_Target"] == 110.0
    # Profit_Target_Source assertion deliberately omitted per Addendum #1 §2.5 (BUGR-006-LABEL-1).
    assert _reward_risk_note is not None
    assert _reward_risk_note.startswith("BREAKOUT MODEL (BRK-001 §4.4):")


# ===========================================================================
# T-REACH: End-to-end reachability test (MANDATORY, NEW in v2.0)  (FAIL/PASS)
# ===========================================================================

def test_T_REACH_bugr006_v2_reachability():
    """T-REACH: verifies BUGR-006 v2.0 block is reachable in the main.py pipeline.

    Exercises the main.py call-order contract (L334 → L348) by invoking
    _detect_breakout_model (writer) followed by _compute_early_capital_rr (reader),
    in that exact order, on a Profile B fresh-breakout fixture.

    This test would have caught v1.0's Phase 5 failure in Phase 4:
    - v1.0 placed the block in _populate_base_metrics (called at main.py:254 — BEFORE
      detection). A test calling _compute_early_capital_rr after _detect_breakout_model
      would have observed _p1_reward_risk_note as None (block never fired in the reader)
      or not starting with "BREAKOUT MODEL", and failed.
    - v2.0 places the block inside _compute_early_capital_rr (the reader). Post-detection
      invocation of the reader must emit the BREAKOUT MODEL note.

    Addendum #1 §1.3 OPTION CHOSEN: Option B (direct call, capture return tuple).
    Rationale: Option A (end-to-end run_tbs_engine) requires mocking IBKR/Finnhub/yfinance
    data fetch in this unit-test environment; Option B reuses the existing direct-call
    scaffolding with minimal overhead. Both options are authoritatively acceptable per
    the addendum; both catch the v1.0 dead-code-branch failure mode.

    Per Addendum #1 §1.3, the sibling INVALID-verdict sanity test is skipped when Option B
    is used (it would exercise the same call-chain — diminished marginal coverage).

    If this test ever fails in the future, the v2.0 block has been moved to a function
    not called by the reader, OR the writer-reader ordering has been broken in main.py.
    """
    # Fresh breakout fixture: close > resistance, DI+ > DI-, volume confirmed, trending.
    # Primary df must have at least 11 bars (MM target uses last 10 via iloc[-11:-1]).
    primary_df = pd.DataFrame({
        "high":   [95.0] * 8 + [96.0, 98.0, 100.5],    # 11 bars
        "low":    [85.0] * 11,
        "close":  [90.0] * 8 + [94.0, 98.0, 100.0],
        "open":   [90.0] * 11,
        "volume": [500_000] * 10 + [1_500_000],        # RVOL final = 3.0
    })
    ctx = _make_ctx(
        p_code="B",
        is_c3=False,
        close=100.0,
        anchor=95.0,
        atr_raw=1.0,
        resistance_raw=99.0,           # close 100 > resistance 99 → Path A fresh breakout
        primary_df=primary_df,
        volume=1_500_000,
        vol_sma_20=500_000,            # RVOL = 3.0 > 1.5 threshold
    )
    # Ensure _entry_trending is True so MM target computes
    ctx.state._entry_trending = True
    # DI+ > DI- (already set by _make_state defaults: 30 > 15)

    # ------------------------------------------------------------------
    # Mirror main.py:334 — WRITER
    # ------------------------------------------------------------------
    _detect_breakout_model(ctx, _window_reset_event="")

    # Writer must have activated the breakout model
    assert ctx._breakout_model_active is True, (
        "T-REACH prerequisite failed: _detect_breakout_model did not activate BRK "
        "on a fresh-breakout fixture. Fixture is wrong, not the reader."
    )
    assert ctx._brk_tight_stop_raw is not None

    # ------------------------------------------------------------------
    # Mirror main.py:348 — READER (contains BUGR-006 v2.0 block)
    # PE-31 saves-and-nulls metrics["Reward_Risk_Note"] before return; the
    # BRK note is carried in the 2nd tuple element (_p1_reward_risk_note).
    # See Addendum #1 §1.3 Option B.
    # ------------------------------------------------------------------
    _p1_resistance_note, _p1_reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)

    # ------------------------------------------------------------------
    # Reachability assertion — the v2.0 failure mode sentinel
    # ------------------------------------------------------------------
    assert _p1_reward_risk_note is not None, (
        "T-REACH FAILED: _p1_reward_risk_note (return tuple) was None. "
        "The BUGR-006 v2.0 block did not fire in the reader. "
        "Likely causes: block moved out of _compute_early_capital_rr, "
        "or call-order in main.py was inverted (writer must run before reader)."
    )
    assert _p1_reward_risk_note.startswith("BREAKOUT MODEL"), (
        f"T-REACH FAILED: Expected _p1_reward_risk_note to start with 'BREAKOUT MODEL', "
        f"got: {_p1_reward_risk_note!r}. The BUGR-006 v2.0 block is not reachable in the "
        f"writer→reader pipeline — this is the v1.0 failure mode."
    )


# ===========================================================================
# T-FRR-COEXIST: FRR-001 coexistence (MANDATORY, NEW in v2.0)  (FAIL/PASS)
# ===========================================================================

def test_T_FRR_COEXIST_bugr006_v2_fundamental_coexistence():
    """T-FRR-COEXIST: BRK + fundamental data coexist on same output.

    Per BUGR-006 v2.0 spec §7.6 (DQ-2 S137 resolution): when a Profile B ticker has
    _breakout_model_active == True AND analyst consensus populated, the BUGR-006 block
    writes Reward_Risk with BRK technical value; FRR-001 block writes Fundamental_*
    keys only. Neither overwrites the other. Both metric sets coexist.

    Asserts:
      - metrics["Reward_Risk"]    carries BRK value (from BUGR-006 v2.0 block)
      - metrics["Fundamental_RR"] carries FRR-001 value (from unchanged L849-909 block)
      - _reward_risk_note (return tuple) is BRK-authored
      - Both keys present, neither is None

    NOTE on Profit_Target_Source (Addendum #1 §2.5, spec §7.6): on FRR-active paths
    (fundamental data present), FRR-001 at compute.py:819 INTENTIONALLY overwrites
    Profit_Target_Source to "ANALYST_CONSENSUS" as part of the technical-target
    demotion to INFORMATIONAL. This is the correct, spec-compliant behaviour — NOT
    a regression. Do NOT assert Profit_Target_Source == "MEASURED_MOVE (BRK-001...)"
    on FRR-active paths; that assertion would spuriously fail against correct behaviour.
    """
    ctx = _make_ctx(
        p_code="B",
        close=100.0,
        anchor=95.0,
        atr_raw=1.0,
        resistance_raw=99.0,
        breakout_model_active=True,
        brk_tight_stop_raw=94.0,
        brk_mm_target_raw=115.0,
        # Analyst consensus populated (consistent with FRR-001 conventions)
        analyst_target_median=120.0,
        analyst_target_low=90.0,
        analyst_target_high=140.0,
        analyst_count=8,
    )
    _resistance_note, _reward_risk_note = _compute_early_capital_rr(ctx, exit_signal=None)
    m = ctx.metrics

    # --- BRK technical R:R (BUGR-006 v2.0 block) ---
    # Reward = 115 - 100 = 15;  Risk = 100 - 94 = 6;  R:R = 2.5
    assert m["Reward_Risk"] == 2.5, (
        f"BRK technical R:R should be 2.5, got {m.get('Reward_Risk')}. "
        "If FRR-001 overwrote it, the DQ-2 coexistence resolution is broken."
    )
    assert _reward_risk_note is not None and _reward_risk_note.startswith("BREAKOUT MODEL"), (
        "_reward_risk_note (return tuple) should be BRK-authored; "
        "FRR-001 must not overwrite it."
    )

    # --- FRR-001 fundamental R:R (unchanged block, present but in its own keys) ---
    assert "Fundamental_RR" in m, (
        "FRR-001 block did not execute. Possible causes: BUGR-006 v2.0 block "
        "accidentally short-circuits FRR-001, or fixture's analyst fields are wrong."
    )
    # Fund reward = 120 - 100 = 20;  Fund risk = 100 - 90 = 10;  Fund R:R = 2.0
    assert m["Fundamental_RR"] == 2.0, (
        f"FRR-001 Fundamental_RR should be 2.0, got {m.get('Fundamental_RR')}"
    )
    assert m.get("Fundamental_Target") == 120.0
    assert m.get("Fundamental_Floor") == 90.0

    # --- Coexistence guarantee: both sets of keys present, neither null ---
    assert m["Reward_Risk"] is not None
    assert m["Fundamental_RR"] is not None
    # Profit_Target_Source assertion deliberately omitted — "ANALYST_CONSENSUS" on
    # FRR-active paths is the correct spec §7.6 demotion behaviour (see docstring).
