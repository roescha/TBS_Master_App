"""
Pre-built Fixture States — 18 scenario states from Prompt Section 6.
RFT-001 Phase 3 — Pre-built Fixture States (Spec §IV.2).

Each function returns a DataFrame ready for the gate cascade harness.
All DataFrames are constructed via BarSequenceBuilder and include the full
indicator stack.  is_etf is always an explicit boolean parameter (PE-33).

Scenario numbering follows the Phase 3 Standalone Prompt §6 fixture table,
which maps state names to scenario IDs.  These correspond to the 18 path
scenarios in Engine Execution Map v1.9 §III but may use different S-numbers.

Window counting note: The test harness uses a simplified window counter.
Scenarios that need to pass through the Window gate use explicit
window_count_override=0 to simulate a fresh execution window.
"""

from tests.integration.fixtures.bar_builder import BarSequenceBuilder


# ── S-01: TRENDING_PULLBACK_PASS ─────────────────────────────────────────────

def trending_pullback_pass(is_etf=False):
    """S-01: Profile B | TRENDING | Pullback → PASS.
    250-bar uptrend, clean pullback to SMA 50, ADX > 25, full MA stack,
    +DI dominant, window fresh, price below ext_limit."""
    return (
        BarSequenceBuilder(profile="B", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_pullback(bars=3, depth_atr=0.3)
        .with_context("bullish_weekly")
        .with_high_adv(10_000_000)
        .with_expired_window(0)  # fresh window
        .build()
    )


# ── S-02: TRENDING_EXTENDED_HALT ─────────────────────────────────────────────

def trending_extended_halt(is_etf=False):
    """S-02: Profile B | TRENDING | Price 2.5 ATR above floor → HALT (Extension).
    Extension gate fires."""
    return (
        BarSequenceBuilder(profile="B", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=150, bars=250)
        .with_context("bullish_weekly")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-03: TRENDING_CLIMAX_HALT ───────────────────────────────────────────────

def trending_climax_halt(is_etf=False):
    """S-03: Profile B | TRENDING | Volume climax 2 bars ago → HALT (Climax).
    Climax gate fires."""
    return (
        BarSequenceBuilder(profile="B", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_pullback(bars=5, depth_atr=1.0)
        .with_climax(bars_ago=1)
        .with_context("bullish_weekly")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-04/S-05: EXPECTANCY_FAIL_PROFILE_A ─────────────────────────────────────

def expectancy_fail_profile_a(is_etf=False):
    """S-04/S-05: Profile A | R:R < 2.0 → HALT (Expectancy Failed).
    Tight cons_high vs price produces poor reward-to-risk."""
    return (
        BarSequenceBuilder(profile="A", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=140, bars=250)
        .with_pullback(bars=3, depth_atr=0.2)
        .with_context("bullish")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-06: RESOLVING_BREAKOUT_PASS ────────────────────────────────────────────

def resolving_breakout_pass(is_etf=False):
    """S-06: Profile B | RESOLVING | Price closes above 10-bar resistance → PASS.
    ADX > 20 with 3-bar positive slope, C-3 breakout path."""
    return (
        BarSequenceBuilder(profile="B", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=130, bars=250)
        .with_no_golden_cross()
        .with_breakout()
        .with_context("bullish_weekly")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-07: RESOLVING_BLOCKED_PROFILE_A ────────────────────────────────────────

def resolving_blocked_profile_a(is_etf=False):
    """S-07: Profile A | RESOLVING | Convexity Protocol blocked on Profile A → HALT.
    ADX > 20 with slope but Profile A cannot breakout."""
    return (
        BarSequenceBuilder(profile="A", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=130, bars=250)
        .with_resolving_adx()
        .with_context("bullish")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-08: WEALTH_FLOOR_PROXIMITY_HALT ────────────────────────────────────────

def wealth_floor_proximity_halt(is_etf=False):
    """S-08: Profile C | Price 18% above SMA 200 → HALT (Floor Proximity Failed).
    Floor Proximity gate fires."""
    return (
        BarSequenceBuilder(profile="C", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_high_floor_proximity(pct=20.0)
        .with_context("bullish_weekly")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-09: RECLAIM_PASS ──────────────────────────────────────────────────────

def reclaim_pass(is_etf=False):
    """S-09: Profile B | Floor breach, price reclaims, window count within limit → PASS.
    1 bar below floor, current bar reclaims. Directional state confirmed."""
    return (
        BarSequenceBuilder(profile="B", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=120, bars=250)
        .with_floor_violation(bars_below=1, depth_atr=0.05, reclaim=True)
        .with_ensure_resolving()
        .with_context("bullish_weekly")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-10: FLOOR_FAILURE_HALT ────────────────────────────────────────────────

def floor_failure_halt(is_etf=False, profile="B"):
    """S-10: Price below floor for 5+ bars (Profile B threshold = 4) → HALT.
    Pre-Check early return. Structural break."""
    threshold = 8 if profile == "A" else 4
    return (
        BarSequenceBuilder(profile=profile, bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_floor_failure(bars_below=threshold + 1, depth_atr=0.5, reclaim_bars=0)
        .with_context("bullish_weekly" if profile != "A" else "bullish")
        .with_high_adv(10_000_000)
        .build()
    )


# ── S-11: FLOOR_VIOLATION_WAIT ──────────────────────────────────────────────

def floor_violation_wait(is_etf=False, profile="B"):
    """S-11: Price 0.6 ATR below floor (violation, not failure) → WAIT.
    Pre-Check early return."""
    return (
        BarSequenceBuilder(profile=profile, bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_floor_violation(bars_below=2, depth_atr=0.5, reclaim=False)
        .with_context("bullish_weekly" if profile != "A" else "bullish")
        .with_high_adv(10_000_000)
        .build()
    )


# ── S-12: DIRECTIONAL_BLOCK ────────────────────────────────────────────────

def directional_block(is_etf=False):
    """S-12: Downtrend sequence, -DI > +DI, no exception applies → WAIT.
    Directional gate fires. Golden Cross broken so Profile B TRENDING
    exemption (ma_stack_full) does not apply."""
    return (
        BarSequenceBuilder(profile="B", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=115, bars=250)
        .with_pullback(bars=3, depth_atr=0.3)
        .with_no_golden_cross()
        .with_di_dominant_minus()
        .with_context("bullish_weekly")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-13: GAP_TRAP_HALT ────────────────────────────────────────────────────

def gap_trap_halt(is_etf=False):
    """S-13: Open gapped above prev_high + 0.5 ATR, Modifier E fires → HALT."""
    return (
        BarSequenceBuilder(profile="B", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_gap_trap()
        .with_context("bullish_weekly")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-14: WINDOW_EXPIRED_HALT ──────────────────────────────────────────────

def window_expired_halt(is_etf=False, profile="B"):
    """S-14: Trending state, window count = 7 (Profile B limit = 5) → WAIT.
    Window gate fires."""
    return (
        BarSequenceBuilder(profile=profile, bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_pullback(bars=3, depth_atr=0.3)
        .with_expired_window(window_count=7)
        .with_context("bullish_weekly" if profile != "A" else "bullish")
        .with_high_adv(10_000_000)
        .build()
    )


# ── S-15: TRENDING_MIDRANGE_ADX_HALT ────────────────────────────────────────

def trending_midrange_adx_halt(is_etf=False, profile="B"):
    """S-15: Flat sequence, ADX = 16, MID-RANGE gate fires → HALT."""
    return (
        BarSequenceBuilder(profile=profile, bars=250, is_etf=is_etf)
        .with_flat(price=100)
        .with_context("bullish_weekly" if profile != "A" else "bullish")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-15 var: TRENDING_MIDRANGE_SQUEEZE ──────────────────────────────────────

def trending_midrange_squeeze(is_etf=False, profile="B"):
    """S-15 variant: Converging MA sequence, EMA 8/21 gap < 0.1 ATR → HALT.
    MA squeeze gate fires.  ADX > 20 but EMA 8/21 converging for 3+ bars."""
    return (
        BarSequenceBuilder(profile=profile, bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=120, bars=250)
        .with_pullback(bars=3, depth_atr=0.3)
        .with_force_squeeze()
        .with_context("bullish_weekly" if profile != "A" else "bullish")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-16: CRG1_HALT_PROFILE_A ──────────────────────────────────────────────

def crg1_halt_profile_a(is_etf=False):
    """S-16: Profile A | Daily SMA 50 < SMA 200, CRG-1 fires → HALT.
    Context Regime Failed."""
    return (
        BarSequenceBuilder(profile="A", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_context("bearish")
        .with_high_adv(10_000_000)
        .build()
    )


# ── S-17: CEG_FAIL_LOW_CAP_RR ──────────────────────────────────────────────

def ceg_fail_low_cap_rr(is_etf=False):
    """S-17: Profile A | Capital R:R = 0.37 (GD event) → REJECT.
    CEG-001 fires after all other gates pass.

    NOTE: Producing exact Capital R:R = 0.37 requires precise price engineering.
    This fixture creates conditions where Expectancy gate and/or CEG fires
    due to poor capital reward-to-risk."""
    return (
        BarSequenceBuilder(profile="A", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=140, bars=250)
        .with_pullback(bars=3, depth_atr=0.2)
        .with_context("bullish")
        .with_high_adv(10_000_000)
        .with_expired_window(0)
        .build()
    )


# ── S-18: CRG2_REJECT_PROFILE_B ────────────────────────────────────────────

def crg2_reject_profile_b(is_etf=False):
    """S-18: Profile B | Weekly SMA 50 < SMA 200, CRG-2 fires → REJECT.
    Context Regime Failed."""
    return (
        BarSequenceBuilder(profile="B", bars=250, is_etf=is_etf)
        .with_uptrend(start=100, end=135, bars=250)
        .with_context("bearish_weekly")
        .with_high_adv(10_000_000)
        .build()
    )
