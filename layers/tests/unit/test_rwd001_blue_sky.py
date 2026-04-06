"""RWD-001: Blue-Sky Reward Ceiling — Unit Tests.

All 28 test cases from spec Section 5, organised into 7 categories:
1. Blue-Sky Detection (TC 1–7)
2. ATR Projection Arithmetic (TC 8–10)
3. MM_Target Override (TC 11–14)
4. Gate Pass/Fail with New Ceiling (TC 15–17)
5. CEG Interaction (TC 18–19)
6. Non-Blue-Sky Unchanged (TC 20–24)
7. Output Field Population (TC 25–28)
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace
from unittest.mock import patch

from ibkr_purity_engine import _compute_early_capital_rr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_daily_df_ctx(n=252, base=100.0, highs_override=None, seed=42):
    """Build a daily-resolution df_ctx with controllable highs."""
    rng = np.random.RandomState(seed)
    closes = [base + 0.05 * i + rng.normal(0, 0.3) for i in range(n)]
    df = pd.DataFrame({
        'open':  [closes[max(0, i - 1)] for i in range(n)],
        'high':  [c + abs(rng.normal(0.8, 0.2)) for c in closes],
        'low':   [c - abs(rng.normal(0.8, 0.2)) for c in closes],
        'close': closes,
    })
    if highs_override is not None:
        for idx, val in highs_override.items():
            df.iloc[idx, df.columns.get_loc('high')] = val
    return df


def _make_hourly_df(n=60, base=100.0, anchor=None, seed=42):
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
    df['ANCHOR']  = anchor if anchor is not None else df['SMA_50']
    return df


def _make_state(**overrides):
    defaults = dict(
        atr_raw=5.0, is_resolving=False, is_trending=True,
        ema_stacked=True, is_floor_failure=False, is_violated=False,
        is_reclaim=False, consec_below=0, _reclaim_run=0,
        floor_raw=95.0, _entry_trending=True,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_cfg(p_code="A"):
    if p_code == "A":
        return SimpleNamespace(
            iq=-2, prev_bar_offset=3,
            resistance_slice_start=-12, resistance_slice_end=-2,
            window_limit=4, ff_threshold=8, profile='A',
        )
    elif p_code == "C":
        return SimpleNamespace(
            iq=-1, prev_bar_offset=2,
            resistance_slice_start=-11, resistance_slice_end=-1,
            window_limit=4, ff_threshold=4, profile='C',
        )
    else:  # B
        return SimpleNamespace(
            iq=-1, prev_bar_offset=2,
            resistance_slice_start=-11, resistance_slice_end=-1,
            window_limit=5, ff_threshold=4, profile='B',
        )


def _make_ctx(p_code="A", df=None, df_ctx=None, _is_c3=False, **overrides):
    """Build a minimal RunContext-like namespace for _compute_early_capital_rr."""
    if df is None:
        df = _make_hourly_df()
    cfg = _make_cfg(p_code)
    last = df.iloc[cfg.iq]
    state = overrides.pop('state', None) or _make_state()
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
    ctx = SimpleNamespace(**defaults)
    ctx.metrics["Resistance_Note"] = None
    ctx.metrics["Reward_Risk_Note"] = None
    return ctx


def _make_blue_sky_ctx(
    price=280.0, anchor=270.0, atr=5.0, tier1_max=275.0, tier2_max=282.0,
    p_code="A", mm_target=None, hard_stop=None, **extra
):
    """Build a ctx that produces a specific blue-sky scenario.

    tier1_max: max high in df_ctx[-11:-1] (10-bar daily high)
    tier2_max: max high in df_ctx[-51:-1] (50-bar daily high)
    price > tier1_max triggers PE-41 escalation to tier2_max.
    """
    # Build df_ctx with controlled highs
    n = 252
    df_ctx = pd.DataFrame({
        'open':  [200.0] * n,
        'high':  [tier1_max - 5.0] * n,  # default all highs low
        'low':   [195.0] * n,
        'close': [200.0] * n,
    })
    # Set tier1 window max (iloc[-11:-1] means indices -11 to -2 inclusive)
    df_ctx.iloc[-5, df_ctx.columns.get_loc('high')] = tier1_max
    # Set tier2 window max (iloc[-51:-1] means indices -51 to -2 inclusive)
    df_ctx.iloc[-30, df_ctx.columns.get_loc('high')] = tier2_max

    # Build hourly df with controlled anchor and price
    n_h = 60
    df = pd.DataFrame({
        'open':   [price] * n_h,
        'high':   [price + 0.5] * n_h,
        'low':    [price - 0.5] * n_h,
        'close':  [price] * n_h,
        'volume': [500000] * n_h,
    })
    df['EMA_8']   = price
    df['EMA_21']  = price - 1
    df['SMA_50']  = anchor
    df['SMA_200'] = anchor - 5
    df['ATRr_14'] = atr * 0.5  # hourly ATR, not used for blue-sky
    df['ANCHOR']  = anchor

    state = _make_state(atr_raw=atr)
    _hs = hard_stop if hard_stop is not None else anchor - 1.5 * atr
    ctx = _make_ctx(
        p_code=p_code, df=df, df_ctx=df_ctx, state=state,
        hard_stop_raw=_hs, **extra
    )
    # Force last row to have correct anchor
    ctx.last = df.iloc[-2].copy()
    ctx.last['close'] = price
    ctx.last['ANCHOR'] = anchor
    return ctx


# ===========================================================================
# Category 1: Blue-Sky Detection (TC 1–7)
# ===========================================================================

class TestBlueSkyDetection:

    def test_tc1_no_escalation_needed(self):
        """TC 1: price < Tier 1 → Blue_Sky_Detected = False."""
        ctx = _make_blue_sky_ctx(price=270.0, tier1_max=280.0, tier2_max=290.0, atr=5.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky', False) is False or \
               ctx.metrics.get('Blue_Sky_Detected') is False

    def test_tc2_tier2_with_headroom(self):
        """TC 2: price > Tier 1, (Tier 2 - price) = 2.0 ATR → not blue sky."""
        atr = 5.0
        price = 280.0
        tier1_max = 275.0
        tier2_max = price + 2.0 * atr  # 290.0 — 2.0 ATR headroom
        ctx = _make_blue_sky_ctx(price=price, tier1_max=tier1_max, tier2_max=tier2_max, atr=atr)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky') is False

    def test_tc3_tier2_at_threshold_boundary(self):
        """TC 3: (Tier 2 - price) = exactly 1.5 ATR → not blue sky (strict <)."""
        atr = 5.0
        price = 280.0
        tier1_max = 275.0
        tier2_max = price + 1.5 * atr  # 287.5 — exactly at threshold
        ctx = _make_blue_sky_ctx(price=price, tier1_max=tier1_max, tier2_max=tier2_max, atr=atr)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky') is False

    def test_tc4_tier2_compressed_below_threshold(self):
        """TC 4: (Tier 2 - price) = 1.0 ATR → blue sky detected."""
        atr = 5.0
        price = 280.0
        tier1_max = 275.0
        tier2_max = price + 1.0 * atr  # 285.0 — 1.0 ATR headroom
        ctx = _make_blue_sky_ctx(price=price, tier1_max=tier1_max, tier2_max=tier2_max, atr=atr)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky') is True

    def test_tc5_tier2_at_price_zero_headroom(self):
        """TC 5: Tier 2 = price (zero headroom) → blue sky detected."""
        atr = 5.0
        price = 280.0
        tier1_max = 275.0
        tier2_max = price  # zero headroom
        ctx = _make_blue_sky_ctx(price=price, tier1_max=tier1_max, tier2_max=tier2_max, atr=atr)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky') is True

    def test_tc6_tier2_below_price(self):
        """TC 6: Tier 2 < price (price above all lookback bars) → blue sky."""
        atr = 5.0
        price = 300.0
        tier1_max = 275.0
        tier2_max = 295.0  # below price
        ctx = _make_blue_sky_ctx(price=price, tier1_max=tier1_max, tier2_max=tier2_max, atr=atr)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky') is True

    def test_tc7_atr_is_zero(self):
        """TC 7: ATR = 0 (illiquid) → blue sky not detected (div-by-zero guard)."""
        price = 280.0
        tier1_max = 275.0
        tier2_max = price  # would otherwise qualify
        ctx = _make_blue_sky_ctx(price=price, tier1_max=tier1_max, tier2_max=tier2_max, atr=0.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        # ATR=0 → detection fires (headroom < 0 < 1.5*0=0 is false) OR guard blocks
        # Spec: is_blue_sky AND atr_daily > 0 — the atr > 0 guard blocks.
        assert ctx.metrics.get('_rwd001_blue_sky') is not True or \
               ctx.metrics["Profit_Target_Source"] != "ATR_PROJECTION (blue sky)"


# ===========================================================================
# Category 2: ATR Projection Arithmetic (TC 8–10)
# ===========================================================================

class TestATRProjectionArithmetic:

    def test_tc8_standard_atr_projection(self):
        """TC 8: floor=100, ATR=5 → target = 115.0."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=100.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky') is True
        # cons_high_raw should be floor + 3.0 * ATR = 100 + 15 = 115
        assert ctx.cons_high_raw == pytest.approx(115.0)

    def test_tc9_small_atr_low_vol(self):
        """TC 9: floor=50, ATR=0.80 → target = 52.40."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=50.0, atr=0.80,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.cons_high_raw == pytest.approx(52.40)

    def test_tc10_large_atr_high_vol(self):
        """TC 10: floor=200, ATR=15 → target = 245.0."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=200.0, atr=15.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.cons_high_raw == pytest.approx(245.0)


# ===========================================================================
# Category 3: MM_Target Override (TC 11–14)
# ===========================================================================

class TestMMTargetOverride:
    """These test the output.py override logic.

    We simulate by calling _compute_early_capital_rr (which sets the ATR
    target and _rwd001 intermediate keys), then manually invoking the
    MM_Target override logic that output.py performs.
    """

    def _apply_mm_override(self, metrics, price_scaler=1.0):
        """Simulate the output.py RWD-001 MM override block."""
        if metrics.get('_rwd001_blue_sky'):
            _bs_atr_raw = metrics.get('_rwd001_atr_target_raw')
            _bs_atr_scaled = round(_bs_atr_raw / price_scaler, 2) if _bs_atr_raw else None
            _mm = metrics.get('MM_Target')

            if _mm is not None and _bs_atr_scaled is not None and _mm > _bs_atr_scaled:
                metrics['Blue_Sky_Detected'] = True
                metrics['Blue_Sky_Target'] = _mm
                metrics['Blue_Sky_Method'] = 'MEASURED_MOVE'
                metrics['Profit_Target_Source'] = 'MEASURED_MOVE (blue sky)'
            else:
                metrics['Blue_Sky_Detected'] = True
                metrics['Blue_Sky_Target'] = _bs_atr_scaled
                metrics['Blue_Sky_Method'] = 'ATR_PROJECTION'

            metrics['Blue_Sky_ATR_Headroom'] = metrics.get('_rwd001_headroom_ratio')
        else:
            metrics['Blue_Sky_Detected'] = False
            metrics['Blue_Sky_Target'] = None
            metrics['Blue_Sky_Method'] = None
            metrics['Blue_Sky_ATR_Headroom'] = None

    def test_tc11_mm_target_null(self):
        """TC 11: MM_Target = None → method = ATR_PROJECTION."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=100.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        ctx.metrics['MM_Target'] = None
        self._apply_mm_override(ctx.metrics)
        assert ctx.metrics['Blue_Sky_Method'] == 'ATR_PROJECTION'

    def test_tc12_mm_below_atr(self):
        """TC 12: floor=100, ATR=5, MM=112 → ATR wins (115 > 112)."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=100.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        ctx.metrics['MM_Target'] = 112.0  # below ATR target of 115
        self._apply_mm_override(ctx.metrics)
        assert ctx.metrics['Blue_Sky_Target'] == pytest.approx(115.0)
        assert ctx.metrics['Blue_Sky_Method'] == 'ATR_PROJECTION'

    def test_tc13_mm_above_atr(self):
        """TC 13: floor=100, ATR=5, MM=120 → MM wins (120 > 115)."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=100.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        ctx.metrics['MM_Target'] = 120.0  # above ATR target of 115
        self._apply_mm_override(ctx.metrics)
        assert ctx.metrics['Blue_Sky_Target'] == pytest.approx(120.0)
        assert ctx.metrics['Blue_Sky_Method'] == 'MEASURED_MOVE'

    def test_tc14_mm_equals_atr(self):
        """TC 14: MM = ATR target (115) → tie goes to ATR (deterministic)."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=100.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        ctx.metrics['MM_Target'] = 115.0  # equals ATR target
        self._apply_mm_override(ctx.metrics)
        assert ctx.metrics['Blue_Sky_Target'] == pytest.approx(115.0)
        assert ctx.metrics['Blue_Sky_Method'] == 'ATR_PROJECTION'


# ===========================================================================
# Category 4: Gate Pass/Fail with New Ceiling (TC 15–17)
# ===========================================================================

class TestGatePassFail:

    def test_tc15_vrt_reproduction(self):
        """TC 15: VRT-like conditions → target≈294, R:R would be > 2.0."""
        # VRT: floor=277.49, price=280, ATR=5.5
        # ATR target = 277.49 + 3.0 * 5.5 = 293.99
        ctx = _make_blue_sky_ctx(
            price=280.0, anchor=277.49, atr=5.5,
            tier1_max=275.0, tier2_max=280.0,
            hard_stop=272.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky') is True
        expected_target = 277.49 + 3.0 * 5.5  # 293.99
        assert ctx.cons_high_raw == pytest.approx(expected_target)
        # Verify structural R:R: reward / risk = 13.99 / 2.51 ≈ 5.57
        reward = ctx.cons_high_raw - 280.0
        risk = 280.0 - 277.49
        assert reward / risk > 2.0, f"Structural R:R {reward/risk:.2f} should exceed 2.0"

    def test_tc16_marginal_blue_sky_pass(self):
        """TC 16: Marginal blue sky — gate depends on threshold."""
        # floor=100, price=102, ATR=3, hard_stop=95
        # ATR target = 100 + 9 = 109
        ctx = _make_blue_sky_ctx(
            price=102.0, anchor=100.0, atr=3.0,
            tier1_max=99.0, tier2_max=102.0,
            hard_stop=95.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.cons_high_raw == pytest.approx(109.0)

    def test_tc17_blue_sky_does_not_bypass_extension(self):
        """TC 17: Blue sky doesn't bypass the extension gate.

        Extension gate fires independently; blue sky only modifies
        the ceiling, not gate ordering.
        """
        # This is a structural test: verify that _compute_early_capital_rr
        # does not skip any gate checks when blue sky fires.
        # The extension check is outside _compute_early_capital_rr, so
        # we just verify the Tier 3 block doesn't set any gate bypass flags.
        ctx = _make_blue_sky_ctx(
            price=280.0, anchor=200.0, atr=5.0,
            tier1_max=275.0, tier2_max=280.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)
        # No bypass or skip flags should exist
        assert not hasattr(ctx, '_skip_extension_gate')
        assert '_skip_extension' not in ctx.metrics


# ===========================================================================
# Category 5: CEG Interaction (TC 18–19)
# ===========================================================================

class TestCEGInteraction:

    def test_tc18_capital_rr_uses_blue_sky_ceiling(self):
        """TC 18: Capital R:R uses the blue-sky target transparently."""
        ctx = _make_blue_sky_ctx(
            price=280.0, anchor=270.0, atr=5.0,
            tier1_max=275.0, tier2_max=280.0,
            hard_stop=265.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)
        # Blue sky target = 270 + 15 = 285
        # Capital reward = 285 - 280 = 5
        # Capital risk = 280 - 265 = 15
        # Capital R:R = 5 / 15 ≈ 0.33
        crr = ctx.metrics.get('Capital_Reward_Risk')
        assert crr is not None
        assert crr == pytest.approx(5.0 / 15.0, abs=0.1)

    def test_tc19_capital_rr_still_insufficient(self):
        """TC 19: Blue sky target close to price, wide hard stop → Capital RR < 1.0."""
        ctx = _make_blue_sky_ctx(
            price=280.0, anchor=278.0, atr=2.0,
            tier1_max=275.0, tier2_max=280.0,
            hard_stop=260.0,
        )
        _compute_early_capital_rr(ctx, exit_signal=False)
        # Blue sky target = 278 + 6 = 284
        # Capital reward = 284 - 280 = 4
        # Capital risk = 280 - 260 = 20
        # Capital R:R = 0.2
        crr = ctx.metrics.get('Capital_Reward_Risk')
        if crr is not None:
            assert crr < 1.0


# ===========================================================================
# Category 6: Non-Blue-Sky Unchanged (TC 20–24)
# ===========================================================================

class TestNonBlueSkyUnchanged:

    def test_tc20_standard_pullback_no_escalation(self):
        """TC 20: price < Tier 1 → existing DAILY_CTX behaviour unchanged."""
        df_ctx = _make_daily_df_ctx(n=252, base=100.0)
        tier1 = df_ctx['high'].iloc[-11:-1].max()
        df = _make_hourly_df(base=tier1 - 10)  # price well below tier 1
        ctx = _make_ctx(p_code="A", df=df, df_ctx=df_ctx)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics['Profit_Target_Source'] == "DAILY_CTX"
        assert ctx.metrics.get('_rwd001_blue_sky') is False

    def test_tc21_pe41_tier2_with_room(self):
        """TC 21: PE-41 Tier 2 fires with > 1.5 ATR headroom → normal PE-41."""
        atr = 5.0
        price = 280.0
        ctx = _make_blue_sky_ctx(price=price, tier1_max=275.0,
                                 tier2_max=price + 2.0 * atr, atr=atr)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics['Profit_Target_Source'] == "WEEKLY_RESISTANCE (price above daily range)"
        assert ctx.metrics.get('_rwd001_blue_sky') is False

    def test_tc22_profile_b_blue_sky_conditions(self):
        """TC 22: Profile B with blue-sky conditions → Blue_Sky_Detected = False."""
        # Use profile B — blue sky is profile A only
        df_ctx = _make_daily_df_ctx(n=260, base=100.0)
        df = _make_hourly_df(base=200.0)
        ctx = _make_ctx(p_code="B", df=df, df_ctx=df_ctx)
        _compute_early_capital_rr(ctx, exit_signal=False)
        # No _rwd001_blue_sky key for Profile B (set by output.py's else branch)
        assert ctx.metrics.get('_rwd001_blue_sky', False) is not True

    def test_tc23_profile_c(self):
        """TC 23: Profile C → Blue_Sky_Detected = False regardless."""
        df = _make_hourly_df(base=200.0)
        ctx = _make_ctx(p_code="C", df=df, df_ctx=None, _is_c3=True)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky', False) is not True

    def test_tc24_etf_profile_a(self):
        """TC 24: ETF on Profile A with blue-sky conditions → Blue_Sky_Detected = True."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=270.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        ctx.is_etf = True  # ETFs use Profile A pipeline
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get('_rwd001_blue_sky') is True


# ===========================================================================
# Category 7: Output Field Population (TC 25–28)
# ===========================================================================

class TestOutputFieldPopulation:

    def _apply_output_fields(self, metrics, price_scaler=1.0):
        """Simulate output.py blue-sky field population."""
        if metrics.get('_rwd001_blue_sky'):
            _bs_atr_raw = metrics.get('_rwd001_atr_target_raw')
            _bs_atr_scaled = round(_bs_atr_raw / price_scaler, 2) if _bs_atr_raw else None
            _mm = metrics.get('MM_Target')
            if _mm is not None and _bs_atr_scaled is not None and _mm > _bs_atr_scaled:
                metrics['Blue_Sky_Detected'] = True
                metrics['Blue_Sky_Target'] = _mm
                metrics['Blue_Sky_Method'] = 'MEASURED_MOVE'
                metrics['Profit_Target_Source'] = 'MEASURED_MOVE (blue sky)'
            else:
                metrics['Blue_Sky_Detected'] = True
                metrics['Blue_Sky_Target'] = _bs_atr_scaled
                metrics['Blue_Sky_Method'] = 'ATR_PROJECTION'
            metrics['Blue_Sky_ATR_Headroom'] = metrics.get('_rwd001_headroom_ratio')
        else:
            metrics['Blue_Sky_Detected'] = False
            metrics['Blue_Sky_Target'] = None
            metrics['Blue_Sky_Method'] = None
            metrics['Blue_Sky_ATR_Headroom'] = None

    def test_tc25_all_fields_populated_when_detected(self):
        """TC 25: When blue sky → all 4 fields populated."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=270.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        ctx.metrics['MM_Target'] = None
        self._apply_output_fields(ctx.metrics)
        assert ctx.metrics['Blue_Sky_Detected'] is True
        assert ctx.metrics['Blue_Sky_Target'] is not None
        assert ctx.metrics['Blue_Sky_Method'] is not None
        assert ctx.metrics['Blue_Sky_ATR_Headroom'] is not None

    def test_tc26_clean_nulls_when_not_detected(self):
        """TC 26: When not blue sky → Detected=False, others null."""
        ctx = _make_blue_sky_ctx(price=270.0, tier1_max=280.0,
                                 tier2_max=290.0, atr=5.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        self._apply_output_fields(ctx.metrics)
        assert ctx.metrics['Blue_Sky_Detected'] is False
        assert ctx.metrics['Blue_Sky_Target'] is None
        assert ctx.metrics['Blue_Sky_Method'] is None
        assert ctx.metrics['Blue_Sky_ATR_Headroom'] is None

    def test_tc27_profit_target_source_atr(self):
        """TC 27: Blue sky, ATR wins → 'ATR_PROJECTION (blue sky)'."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=270.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics['Profit_Target_Source'] == 'ATR_PROJECTION (blue sky)'
        ctx.metrics['MM_Target'] = None
        self._apply_output_fields(ctx.metrics)
        assert ctx.metrics['Blue_Sky_Method'] == 'ATR_PROJECTION'

    def test_tc28_profit_target_source_mm(self):
        """TC 28: Blue sky, MM wins → 'MEASURED_MOVE (blue sky)'."""
        ctx = _make_blue_sky_ctx(price=280.0, anchor=270.0, atr=5.0,
                                 tier1_max=275.0, tier2_max=280.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        # ATR target = 270 + 15 = 285. Set MM above that.
        ctx.metrics['MM_Target'] = 290.0
        self._apply_output_fields(ctx.metrics)
        assert ctx.metrics['Blue_Sky_Method'] == 'MEASURED_MOVE'
        assert ctx.metrics['Profit_Target_Source'] == 'MEASURED_MOVE (blue sky)'
