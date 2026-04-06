"""PE-41: Resistance Ceiling Escalation — Unit Tests.

Covers all nine verification criteria (V1–V9) from the PE-41 spec v1.1.

V1: Price ≤ daily 10-bar high → Profit_Target uses daily high (regression).
V2: Price > daily 10-bar high, Profile A → daily 50-bar high. WEEKLY_RESISTANCE.
V3: Price > daily 10-bar high, Profile A, df_ctx < 51 bars → max(df_ctx). WEEKLY_RESISTANCE.
V4: Price > daily 10-bar high, Profile B TRENDING C-1/C-2 → weekly 10-bar high.
V5: Profile B BREAKOUT entries unaffected (CEG-001-OBS-1 N/A preserved).
V6: Profile B C-3 entries unaffected (expectancy gate bypass preserved).
V7: Profile C output identical (zero change).
V8: Existing snapshot tests pass (covered by running the full test suite).
V9: Mathematical equivalence: daily 50-bar max ≈ weekly 10-bar max.
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace

from ibkr_purity_engine import _compute_early_capital_rr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_daily_df_ctx(n=252, base=100.0, spike_at=None, spike_val=None, seed=42):
    """Build a daily-resolution df_ctx (Profile A context chart).

    Args:
        n: Number of bars (default 252 ≈ 12 months).
        base: Base price level.
        spike_at: If set, inject a high at this iloc position.
        spike_val: The value for the injected spike.
    """
    rng = np.random.RandomState(seed)
    closes = [base + 0.05 * i + rng.normal(0, 0.3) for i in range(n)]
    df = pd.DataFrame({
        'open':  [closes[max(0, i - 1)] for i in range(n)],
        'high':  [c + abs(rng.normal(0.8, 0.2)) for c in closes],
        'low':   [c - abs(rng.normal(0.8, 0.2)) for c in closes],
        'close': closes,
    })
    if spike_at is not None and spike_val is not None:
        df.iloc[spike_at, df.columns.get_loc('high')] = spike_val
    return df


def _make_weekly_df_ctx(n=260, base=100.0, spike_at=None, spike_val=None, seed=42):
    """Build a weekly-resolution df_ctx (Profile B context chart)."""
    rng = np.random.RandomState(seed)
    closes = [base + 0.2 * i + rng.normal(0, 0.5) for i in range(n)]
    df = pd.DataFrame({
        'open':  [closes[max(0, i - 1)] for i in range(n)],
        'high':  [c + abs(rng.normal(1.5, 0.5)) for c in closes],
        'low':   [c - abs(rng.normal(1.5, 0.5)) for c in closes],
        'close': closes,
    })
    if spike_at is not None and spike_val is not None:
        df.iloc[spike_at, df.columns.get_loc('high')] = spike_val
    return df


def _make_hourly_df(n=60, base=100.0, seed=42):
    """Build a minimal primary DataFrame with indicators."""
    rng = np.random.RandomState(seed)
    closes = [base + 0.1 * i + rng.normal(0, 0.2) for i in range(n)]
    df = pd.DataFrame({
        'open':   [closes[max(0, i - 1)] for i in range(n)],
        'high':   [c + abs(rng.normal(0.3, 0.1)) for c in closes],
        'low':    [c - abs(rng.normal(0.3, 0.1)) for c in closes],
        'close':  closes,
        'volume': [500000 + rng.normal(0, 50000) for _ in range(n)],
    })
    df['EMA_8']   = df['close'].ewm(span=8, adjust=False).mean()
    df['EMA_21']  = df['close'].ewm(span=21, adjust=False).mean()
    df['SMA_50']  = df['close'].rolling(50).mean()
    df['SMA_200'] = df['close'].rolling(min(200, n - 1)).mean()
    df['ATRr_14'] = (df['high'] - df['low']).ewm(alpha=1/14, adjust=False).mean()
    df['ANCHOR']  = df['SMA_50']
    return df


def _make_state(**overrides):
    defaults = dict(
        atr_raw=2.0, is_resolving=False, is_trending=True,
        ema_stacked=True, is_floor_failure=False, is_violated=False,
        is_reclaim=False, consec_below=0, _reclaim_run=0,
        floor_raw=95.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_cfg(p_code="A"):
    if p_code == "A":
        return SimpleNamespace(
            iq=-2, prev_bar_offset=3,
            resistance_slice_start=-12, resistance_slice_end=-2,
            window_limit=4, ff_threshold=8,
        )
    elif p_code == "C":
        return SimpleNamespace(
            iq=-1, prev_bar_offset=2,
            resistance_slice_start=-11, resistance_slice_end=-1,
            window_limit=4, ff_threshold=4,
        )
    else:  # B
        return SimpleNamespace(
            iq=-1, prev_bar_offset=2,
            resistance_slice_start=-11, resistance_slice_end=-1,
            window_limit=5, ff_threshold=4,
        )


def _make_ctx(p_code="A", df=None, df_ctx=None, _is_c3=False, **overrides):
    """Build a minimal RunContext-like namespace for _compute_early_capital_rr."""
    if df is None:
        df = _make_hourly_df()
    cfg = _make_cfg(p_code)
    last = df.iloc[cfg.iq]
    state = _make_state(atr_raw=float(last['ATRr_14']))
    defaults = dict(
        state=state, cfg=cfg, p_code=p_code, is_etf=False, _is_c3=_is_c3,
        df=df, last=last, metrics={},
        price_scaler=1.0,
        actual_price=float(last['close']),
        structural_floor_raw=float(last.get('ANCHOR', 95.0)),
        hard_stop_raw=float(last.get('ANCHOR', 95.0)) - 1.5 * state.atr_raw,
        resistance_raw=float(df['high'].iloc[-11:-1].max()),
        cons_high_raw=None,
        _df_ctx=df_ctx,
    )
    defaults.update(overrides)
    # Ensure PE-31 notes exist to avoid KeyError
    ctx = SimpleNamespace(**defaults)
    ctx.metrics["Resistance_Note"] = None
    ctx.metrics["Reward_Risk_Note"] = None
    return ctx


# ===========================================================================
# V1: Price ≤ daily 10-bar high → Profit_Target uses daily high (regression)
# ===========================================================================

class TestV1_DailyHighRegression:
    """V1: When price ≤ daily 10-bar high, Profit_Target uses daily high."""

    def test_profile_a_uses_daily_10bar_when_below(self):
        """Profile A: price below daily 10-bar high → DAILY_CTX source."""
        df_ctx = _make_daily_df_ctx(n=252, base=100.0)
        # Ensure last close is below df_ctx 10-bar high
        daily_10_high = df_ctx['high'].iloc[-11:-1].max()
        df = _make_hourly_df(base=90.0)  # price well below daily range
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)
        # Force last close below daily 10-bar high
        assert ctx.last['close'] < daily_10_high, "Test setup: price must be below daily 10-bar high"

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.metrics["Profit_Target_Source"] == "DAILY_CTX"
        assert ctx.cons_high_raw == pytest.approx(daily_10_high)

    def test_profile_a_daily_ctx_value_is_10bar_max(self):
        """Profile A: cons_high_raw equals the daily 10-bar high exactly."""
        df_ctx = _make_daily_df_ctx(n=252, base=80.0)
        daily_10_high = df_ctx['high'].iloc[-11:-1].max()
        df = _make_hourly_df(base=70.0)
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(daily_10_high)


# ===========================================================================
# V2: Price > daily 10-bar high, Profile A → daily 50-bar high
# ===========================================================================

class TestV2_ProfileA_WeeklyEquivalent:
    """V2: Profile A escalates to daily 50-bar high when price above daily range."""

    def test_escalation_fires_when_price_above_daily(self):
        """Profile A: price > daily 10-bar high → WEEKLY_RESISTANCE source."""
        df_ctx = _make_daily_df_ctx(n=252, base=100.0)
        daily_10_high = df_ctx['high'].iloc[-11:-1].max()
        # Set price well above the daily 10-bar high
        price = daily_10_high + 5.0
        # Inject a spike in 50-bar window so Tier 2 has > 1.5 ATR headroom
        # (prevents RWD-001 Tier 3 from activating)
        df_ctx.iloc[-30, df_ctx.columns.get_loc('high')] = price + 20.0
        df = _make_hourly_df(base=price - 3.0)
        # Force the last close to be above daily 10-bar high
        idx = -2  # cfg.iq for Profile A
        df.iloc[idx, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)
        ctx.last = df.iloc[idx]

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.metrics["Profit_Target_Source"] == "WEEKLY_RESISTANCE (price above daily range)"

    def test_escalation_uses_50bar_window(self):
        """Profile A: escalated ceiling is df_ctx['high'].iloc[-51:-1].max()."""
        df_ctx = _make_daily_df_ctx(n=252, base=100.0)
        # Inject a spike in the 50-bar window but outside 10-bar window
        spike_pos = -30  # within 50-bar, outside 10-bar
        spike_val = 999.0
        df_ctx.iloc[spike_pos, df_ctx.columns.get_loc('high')] = spike_val

        daily_10_high = df_ctx['high'].iloc[-11:-1].max()
        daily_50_high = df_ctx['high'].iloc[-51:-1].max()
        assert daily_50_high == spike_val  # spike is in 50-bar window
        assert daily_10_high < spike_val   # spike is outside 10-bar window

        # Price above 10-bar but below 50-bar
        price = daily_10_high + 1.0
        df = _make_hourly_df(base=price - 3.0)
        df.iloc[-2, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)
        ctx.last = df.iloc[-2]

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(spike_val)
        assert ctx.metrics["Profit_Target_Source"] == "WEEKLY_RESISTANCE (price above daily range)"

    def test_hourly_resistance_string_removed(self):
        """Profile A: HOURLY_RESISTANCE label is never produced."""
        df_ctx = _make_daily_df_ctx(n=252, base=100.0)
        daily_10_high = df_ctx['high'].iloc[-11:-1].max()
        price = daily_10_high + 5.0
        df = _make_hourly_df(base=price - 3.0)
        df.iloc[-2, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)
        ctx.last = df.iloc[-2]

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert "HOURLY" not in ctx.metrics["Profit_Target_Source"]


# ===========================================================================
# V3: Profile A, df_ctx < 51 bars → max(df_ctx['high'])
# ===========================================================================

class TestV3_ProfileA_ReducedWindow:
    """V3: Profile A with < 51 bars uses all available df_ctx highs."""

    def test_reduced_window_uses_full_max(self):
        """df_ctx has only 30 bars: uses df_ctx['high'].max()."""
        df_ctx = _make_daily_df_ctx(n=30, base=100.0)
        # Inject a spike at the start
        df_ctx.iloc[0, df_ctx.columns.get_loc('high')] = 500.0
        full_max = df_ctx['high'].max()
        assert full_max == 500.0

        daily_10_high = df_ctx['high'].iloc[-11:-1].max()
        price = daily_10_high + 1.0
        df = _make_hourly_df(base=price - 3.0)
        df.iloc[-2, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)
        ctx.last = df.iloc[-2]

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(500.0)
        assert ctx.metrics["Profit_Target_Source"] == "WEEKLY_RESISTANCE (price above daily range)"

    def test_exactly_50_bars_uses_full_max(self):
        """df_ctx has exactly 50 bars (< 51): uses df_ctx['high'].max()."""
        df_ctx = _make_daily_df_ctx(n=50, base=100.0)
        daily_10_high = df_ctx['high'].iloc[-11:-1].max()
        price = daily_10_high + 1.0
        # Inject spike so Tier 2 ceiling >> price (prevents RWD-001 Tier 3)
        df_ctx.iloc[0, df_ctx.columns.get_loc('high')] = price + 50.0
        df = _make_hourly_df(base=price - 3.0)
        df.iloc[-2, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)
        ctx.last = df.iloc[-2]

        _compute_early_capital_rr(ctx, exit_signal=False)

        # With < 51 bars, should use df_ctx['high'].max()
        expected = df_ctx['high'].max()
        assert ctx.cons_high_raw == pytest.approx(expected)

    def test_exactly_51_bars_uses_50bar_slice(self):
        """df_ctx has exactly 51 bars: uses iloc[-51:-1].max()."""
        df_ctx = _make_daily_df_ctx(n=51, base=100.0)
        daily_10_high = df_ctx['high'].iloc[-11:-1].max()
        price = daily_10_high + 1.0
        # Inject spike in 50-bar window so Tier 2 ceiling >> price (prevents RWD-001 Tier 3)
        df_ctx.iloc[5, df_ctx.columns.get_loc('high')] = price + 50.0
        daily_50_high = df_ctx['high'].iloc[-51:-1].max()  # all 50 non-last bars
        df = _make_hourly_df(base=price - 3.0)
        df.iloc[-2, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)
        ctx.last = df.iloc[-2]

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw == pytest.approx(daily_50_high)


# ===========================================================================
# V4: Profile B TRENDING C-1/C-2 → weekly 10-bar high
# ===========================================================================

class TestV4_ProfileB_WeeklyCeiling:
    """V4: Profile B C-1/C-2 TRENDING escalates to weekly 10-bar ceiling."""

    def _make_profile_b_ctx(self, price, resistance_raw, df_ctx=None,
                            _is_c3=False, is_trending=True, **kw):
        """Helper for Profile B contexts."""
        df = _make_hourly_df(n=60, base=price - 3.0)
        df.iloc[-1, df.columns.get_loc('close')] = price
        if df_ctx is None:
            df_ctx = _make_weekly_df_ctx(n=260, base=price - 10.0)
        cfg = _make_cfg("B")
        state = _make_state(is_trending=is_trending, floor_raw=price - 5.0)
        ctx = SimpleNamespace(
            state=state, cfg=cfg, p_code="B", is_etf=False, _is_c3=_is_c3,
            df=df, last=df.iloc[-1], metrics={},
            price_scaler=1.0, actual_price=price,
            structural_floor_raw=price - 5.0,
            hard_stop_raw=price - 8.0,
            resistance_raw=resistance_raw,
            cons_high_raw=None,
            _df_ctx=df_ctx,
        )
        ctx.metrics["Resistance_Note"] = None
        ctx.metrics["Reward_Risk_Note"] = None
        for k, v in kw.items():
            setattr(ctx, k, v)
        return ctx

    def test_early_capital_escalates_for_c1_trending(self):
        """Profile B C-1: price above resistance → weekly ceiling used in early R:R."""
        price = 150.0
        resistance = 145.0  # below price
        df_ctx = _make_weekly_df_ctx(n=260, base=140.0)
        # Ensure weekly 10-bar high is above price
        df_ctx.iloc[-5, df_ctx.columns.get_loc('high')] = 160.0
        weekly_10_high = df_ctx['high'].iloc[-11:-1].max()
        assert weekly_10_high >= 160.0

        ctx = self._make_profile_b_ctx(price, resistance, df_ctx=df_ctx)
        _compute_early_capital_rr(ctx, exit_signal=False)

        # Early capital target should be the weekly ceiling, not resistance
        crr = ctx.metrics.get("Capital_Reward_Risk")
        assert crr is not None, "Capital_Reward_Risk should not be suppressed"
        assert crr > 0

    def test_early_capital_no_escalation_for_c3(self):
        """Profile B C-3: weekly escalation does NOT fire (expectancy bypass)."""
        price = 150.0
        resistance = 145.0
        df_ctx = _make_weekly_df_ctx(n=260, base=140.0)
        df_ctx.iloc[-5, df_ctx.columns.get_loc('high')] = 160.0

        ctx = self._make_profile_b_ctx(price, resistance, df_ctx=df_ctx, _is_c3=True)
        _compute_early_capital_rr(ctx, exit_signal=False)

        # With C-3, early_capital_target remains resistance_raw (≤ price),
        # so Capital_Reward_Risk should be suppressed
        assert ctx.metrics.get("Capital_Reward_Risk") is None

    def test_weekly_ceiling_below_price_falls_through(self):
        """Profile B: weekly ceiling also below price → suppressed."""
        price = 200.0
        resistance = 190.0
        df_ctx = _make_weekly_df_ctx(n=260, base=50.0)
        # All weekly highs well below price
        assert df_ctx['high'].iloc[-11:-1].max() < price

        ctx = self._make_profile_b_ctx(price, resistance, df_ctx=df_ctx)
        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.metrics.get("Capital_Reward_Risk") is None


# ===========================================================================
# V5: Profile B BREAKOUT entries unaffected
# ===========================================================================

class TestV5_ProfileB_BreakoutUnaffected:
    """V5: BREAKOUT entries are not changed by PE-41.

    BREAKOUT entries produce N/A reward by design (CEG-001-OBS-1).
    PE-41 only fires when _resistance_suppressed is True (price above
    resistance), but BREAKOUT entry logic and the OBS-1 N/A are
    downstream in gates/trigger and are unchanged.

    This test verifies that the compute.py change does not alter the
    early capital R:R path for BREAKOUT scenarios.
    """

    def test_breakout_resistance_above_price_unchanged(self):
        """BREAKOUT: resistance above price → no escalation path triggered."""
        price = 150.0
        resistance = 155.0  # above price (BREAKOUT has resistance as target)
        df_ctx = _make_weekly_df_ctx(n=260, base=140.0)
        df = _make_hourly_df(base=price - 3.0)
        df.iloc[-1, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="B", df=df, df_ctx=df_ctx)
        ctx.last = df.iloc[-1]
        ctx.resistance_raw = resistance
        ctx.hard_stop_raw = price - 8.0
        ctx.state.floor_raw = price - 5.0

        _compute_early_capital_rr(ctx, exit_signal=False)

        # resistance > price → _early_capital_target = resistance_raw (unchanged)
        crr = ctx.metrics.get("Capital_Reward_Risk")
        assert crr is not None
        expected = (resistance - price) / (price - ctx.hard_stop_raw)
        assert crr == pytest.approx(expected, rel=0.01)


# ===========================================================================
# V6: Profile B C-3 entries unaffected
# ===========================================================================

class TestV6_ProfileB_C3Unaffected:
    """V6: C-3 expectancy gate bypass is preserved."""

    def test_c3_early_capital_unchanged_when_above_resistance(self):
        """C-3 with price above resistance: escalation does NOT fire."""
        price = 150.0
        resistance = 145.0
        df_ctx = _make_weekly_df_ctx(n=260, base=140.0)
        df_ctx.iloc[-5, df_ctx.columns.get_loc('high')] = 200.0  # high weekly ceiling

        df = _make_hourly_df(base=price - 3.0)
        df.iloc[-1, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="B", df=df, df_ctx=df_ctx, _is_c3=True)
        ctx.last = df.iloc[-1]
        ctx.resistance_raw = resistance
        ctx.hard_stop_raw = price - 8.0
        ctx.state.floor_raw = price - 5.0

        _compute_early_capital_rr(ctx, exit_signal=False)

        # C-3 skips weekly escalation → target remains resistance_raw (< price)
        # → suppressed
        assert ctx.metrics.get("Capital_Reward_Risk") is None

    def test_c3_below_resistance_uses_resistance_raw(self):
        """C-3 with price below resistance: normal path, no escalation."""
        price = 140.0
        resistance = 150.0
        df = _make_hourly_df(base=price - 3.0)
        df.iloc[-1, df.columns.get_loc('close')] = price
        ctx = _make_ctx(p_code="B", df=df, _is_c3=True)
        ctx.last = df.iloc[-1]
        ctx.resistance_raw = resistance
        ctx.hard_stop_raw = price - 8.0

        _compute_early_capital_rr(ctx, exit_signal=False)

        crr = ctx.metrics.get("Capital_Reward_Risk")
        assert crr is not None
        assert crr > 0


# ===========================================================================
# V7: Profile C output identical
# ===========================================================================

class TestV7_ProfileC_ZeroChange:
    """V7: Profile C is completely untouched by PE-41."""

    def test_profile_c_no_cons_high(self):
        """Profile C: cons_high_raw remains None."""
        df = _make_hourly_df()
        ctx = _make_ctx(p_code="C", df=df)

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.cons_high_raw is None

    def test_profile_c_no_profit_target_source(self):
        """Profile C: no Profit_Target_Source set by compute."""
        df = _make_hourly_df()
        ctx = _make_ctx(p_code="C", df=df)

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert "Profit_Target_Source" not in ctx.metrics

    def test_profile_c_no_capital_rr(self):
        """Profile C: Capital_Reward_Risk is None."""
        df = _make_hourly_df()
        ctx = _make_ctx(p_code="C", df=df)

        _compute_early_capital_rr(ctx, exit_signal=False)

        assert ctx.metrics.get("Capital_Reward_Risk") is None


# ===========================================================================
# V9: Mathematical equivalence — daily 50-bar ≈ weekly 10-bar
# ===========================================================================

class TestV9_MathematicalEquivalence:
    """V9: Daily 50-bar max equals weekly 10-bar max for equivalent periods.

    A weekly bar's high IS the maximum daily high within that week.
    Therefore max(daily_highs[-50:]) == max(weekly_highs[-10:]) when
    daily bars are aligned to calendar weeks.

    We construct aligned daily and weekly data for 3 tickers and verify.
    """

    @staticmethod
    def _build_aligned_data(daily_highs):
        """Build aligned daily (5-bar weeks) and weekly DataFrames.

        Each group of 5 consecutive daily highs collapses to one weekly
        bar whose high is the max of those 5 days.
        """
        n = len(daily_highs)
        assert n % 5 == 0, "daily_highs length must be multiple of 5"
        df_daily = pd.DataFrame({'high': daily_highs})

        # Build weekly bars: each week = max of 5 daily bars
        weekly_highs = []
        for i in range(0, n, 5):
            weekly_highs.append(max(daily_highs[i:i+5]))
        df_weekly = pd.DataFrame({'high': weekly_highs})

        return df_daily, df_weekly

    @pytest.mark.parametrize("label,seed", [
        ("LRCX", 100),
        ("AAPL", 200),
        ("MSFT", 300),
    ])
    def test_daily_50bar_equals_weekly_10bar(self, label, seed):
        """For ticker '{label}': daily 50-bar max == weekly 10-bar max."""
        rng = np.random.RandomState(seed)
        # Generate 100 daily bars (= 20 weekly bars), enough for 50-bar/10-bar
        daily_highs = [100.0 + rng.normal(0, 3.0) for _ in range(100)]

        df_daily, df_weekly = self._build_aligned_data(daily_highs)

        # Last 50 daily bars (excluding current bar) → iloc[-51:-1]
        # Last 10 weekly bars (excluding current bar) → iloc[-11:-1]
        daily_50_max = df_daily['high'].iloc[-51:-1].max()
        weekly_10_max = df_weekly['high'].iloc[-11:-1].max()

        assert daily_50_max == pytest.approx(weekly_10_max), (
            f"{label}: daily 50-bar max ({daily_50_max:.4f}) != "
            f"weekly 10-bar max ({weekly_10_max:.4f})"
        )

    def test_equivalence_with_spike(self):
        """Equivalence holds when a spike exists within the window."""
        rng = np.random.RandomState(42)
        daily_highs = [100.0 + rng.normal(0, 2.0) for _ in range(100)]
        # Inject a spike at bar -25 (within 50-bar daily, within 10-bar weekly)
        daily_highs[-25] = 200.0

        df_daily, df_weekly = self._build_aligned_data(daily_highs)

        daily_50_max = df_daily['high'].iloc[-51:-1].max()
        weekly_10_max = df_weekly['high'].iloc[-11:-1].max()

        assert daily_50_max == pytest.approx(weekly_10_max)
        assert daily_50_max == 200.0
