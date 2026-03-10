"""
BarSequenceBuilder — Fluent synthetic DataFrame builder for scenario integration tests.
RFT-001 Phase 3 — Fixture Builder (Spec §IV.2.1).

Constructs minimal bar sequences that produce target indicator states after running
the indicator stack. Indicators are computed using the same mathematical formulas
as pandas_ta (Wilder smoothing for ADX/ATR, standard EMA/SMA).

Gate Cascade Harness: run_gate_cascade() invokes the 15 extracted gate functions in
the exact Execution Map v1.9 order, bypassing the data-fetch layer. This is necessary
because _evaluate_gates() does not yet exist as a standalone function (Phase 1 extracted
gates but left the cascade inline in run_tbs_engine). The harness computes all derived
state variables from the DataFrame using the same logic as the engine.
"""

import numpy as np
import pandas as pd
from types import SimpleNamespace

import ibkr_purity_engine
from ibkr_purity_engine import GRACE_BUFFER_ATR_PCT


# ---------------------------------------------------------------------------
# Manual indicator computation (equivalent to pandas_ta output)
# ---------------------------------------------------------------------------

def _compute_ema(series, span):
    """Exponential Moving Average matching pandas_ta: ewm(span=N, adjust=False)."""
    return series.ewm(span=span, adjust=False).mean()


def _compute_sma(series, window):
    """Simple Moving Average matching pandas_ta: rolling(N).mean()."""
    return series.rolling(window=window).mean()


def _compute_atr(df, length=14):
    """Average True Range using Wilder smoothing (alpha=1/length).
    Column name matches pandas_ta: ATRr_14."""
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / length, adjust=False).mean()
    return atr


def _compute_adx(df, length=14):
    """ADX, +DI, -DI using Wilder smoothing.
    Returns columns: ADX_14, DMP_14, DMN_14."""
    high = df['high']
    low = df['low']
    close = df['close']

    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
                        index=df.index, dtype=float)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
                         index=df.index, dtype=float)

    # True Range
    close_prev = close.shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder smoothing (alpha = 1/length)
    alpha = 1.0 / length
    atr_smooth = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=alpha, adjust=False).mean()

    # Directional Indicators
    plus_di = 100.0 * plus_dm_smooth / atr_smooth
    minus_di = 100.0 * minus_dm_smooth / atr_smooth

    # DX and ADX
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = pd.Series(np.where(di_sum > 0, 100.0 * di_diff / di_sum, 0.0),
                   index=df.index, dtype=float)
    adx = dx.ewm(alpha=alpha, adjust=False).mean()

    return adx, plus_di, minus_di


def _compute_indicators(df):
    """Compute full indicator stack on a DataFrame with OHLCV columns.
    Adds columns matching pandas_ta naming: EMA_8, EMA_21, SMA_50, SMA_200,
    ADX_14, DMP_14, DMN_14, ATRr_14, vol_sma_9, vol_sma_20.
    """
    df = df.copy()

    # Moving averages
    df['EMA_8'] = _compute_ema(df['close'], 8)
    df['EMA_21'] = _compute_ema(df['close'], 21)
    df['SMA_50'] = _compute_sma(df['close'], 50)
    df['SMA_200'] = _compute_sma(df['close'], 200)

    # ADX family
    adx, dmp, dmn = _compute_adx(df, 14)
    df['ADX_14'] = adx
    df['DMP_14'] = dmp
    df['DMN_14'] = dmn

    # ATR
    df['ATRr_14'] = _compute_atr(df, 14)

    # Volume SMAs
    df['vol_sma_9'] = _compute_sma(df['volume'], 9)
    df['vol_sma_20'] = _compute_sma(df['volume'], 20)

    # MA Distance and Squeeze (used by engine state classification)
    df['MA_Dist'] = (df['EMA_8'] - df['EMA_21']).abs()
    df['Squeeze'] = df['MA_Dist'] < (0.1 * df['ATRr_14'])

    return df


# ---------------------------------------------------------------------------
# BarSequenceBuilder — Fluent interface
# ---------------------------------------------------------------------------

class BarSequenceBuilder:
    """Constructs synthetic OHLCV bar sequences that produce target indicator states.

    Usage:
        df = (
            BarSequenceBuilder(profile="B", bars=250, is_etf=False)
            .with_uptrend(start=100, end=150, bars=200)
            .with_pullback(bars=8, depth_atr=0.4)
            .with_fresh_window(bars_ago=2)
            .build()
        )

    The is_etf parameter is stored as metadata and used by the gate cascade harness.
    It is NEVER derived from ticker name or exchange metadata (PE-33 awareness).
    """

    def __init__(self, profile="B", bars=250, is_etf=False):
        p_map = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
        self.p_code = p_map.get(profile, profile)
        self.total_bars = bars
        self.is_etf = is_etf

        # Price series parameters (defaults: gentle uptrend)
        self._base_price = 100.0
        self._trend_slope = 0.25  # per bar
        self._noise_scale = 0.5   # OHLC noise amplitude
        self._bar_range = 1.5     # typical high-low range

        # Modifications (applied in order during build)
        self._modifications = []

        # Volume parameters
        self._base_volume = 500_000
        self._volume_noise = 0.2  # relative noise

        # Overrides for specific indicator values
        self._adx_override = None
        self._di_override = None
        self._window_count_override = None

        # Context DataFrame for CRG gate
        self._df_ctx = None
        self._df_ctx_config = None

        # Explicit state overrides (for scenarios that need precise control)
        self._price_scaler = 1.0
        self._adv_override = None

        # Random seed for reproducibility
        self._seed = 42

    # ---- Fluent builder methods ----

    def with_uptrend(self, start=100, end=150, bars=None):
        """Configure an uptrending price series."""
        if bars is None:
            bars = self.total_bars
        self._base_price = start
        self._trend_slope = (end - start) / max(bars, 1)
        return self

    def with_downtrend(self, start=150, end=100, bars=None):
        """Configure a downtrending price series (for -DI dominant scenarios)."""
        if bars is None:
            bars = self.total_bars
        self._base_price = start
        self._trend_slope = (end - start) / max(bars, 1)
        return self

    def with_flat(self, price=100):
        """Configure a flat/range-bound price series (for MID-RANGE/ADX < 20)."""
        self._base_price = price
        self._trend_slope = 0.0
        self._noise_scale = 1.0  # More noise, less trend
        return self

    def with_pullback(self, bars=8, depth_atr=0.4):
        """Apply a pullback at the end of the series.
        Drops price toward the floor over the last N bars."""
        self._modifications.append(('pullback', {'bars': bars, 'depth_atr': depth_atr}))
        return self

    def with_floor_violation(self, bars_below=2, depth_atr=0.3, reclaim=False):
        """Create bars below the structural floor (ANCHOR).
        If reclaim=True, the final bar closes above floor."""
        self._modifications.append(('floor_violation', {
            'bars_below': bars_below,
            'depth_atr': depth_atr,
            'reclaim': reclaim,
        }))
        return self

    def with_floor_failure(self, bars_below=5, depth_atr=0.5, reclaim_bars=0):
        """Create a floor failure (>= threshold bars below floor).
        reclaim_bars: number of bars above floor after the failure (0-2 for recovery)."""
        self._modifications.append(('floor_failure', {
            'bars_below': bars_below,
            'depth_atr': depth_atr,
            'reclaim_bars': reclaim_bars,
        }))
        return self

    def with_climax(self, bars_ago=1):
        """Inject a volume climax bar (vol > 2x SMA9, negative close)."""
        self._modifications.append(('climax', {'bars_ago': bars_ago}))
        return self

    def with_extension(self, atr_multiple=1.5):
        """Push price far above the proximity anchor."""
        self._modifications.append(('extension', {'atr_multiple': atr_multiple}))
        return self

    def with_fresh_window(self, bars_ago=2):
        """Ensure a recent pullback/breakout event for window counting.
        Creates a pullback event bars_ago bars from the end."""
        self._modifications.append(('fresh_window', {'bars_ago': bars_ago}))
        return self

    def with_gap_trap(self):
        """Create a Modifier E gap-trap on the final bar:
        open > prev_high + 0.5*ATR AND close < open."""
        self._modifications.append(('gap_trap', {}))
        return self

    def with_weak_adx(self, target_adx=18):
        """Force ADX below 20 by reducing trend consistency."""
        self._adx_override = target_adx
        return self

    def with_di_dominant_minus(self):
        """Make -DI > +DI (for directional block scenarios)."""
        self._di_override = 'minus'
        return self

    def with_volume(self, base_volume=500_000):
        """Set base volume level."""
        self._base_volume = base_volume
        return self

    def with_high_adv(self, adv=10_000_000):
        """Override ADV to ensure liquidity gate passes."""
        self._adv_override = adv
        return self

    def with_low_adv(self, adv=1_000_000):
        """Override ADV to trigger liquidity gate failure."""
        self._adv_override = adv
        return self

    def with_context(self, regime='bullish'):
        """Configure the context DataFrame for CRG gate.
        regime: 'bullish' (SMA50 > SMA200 rising), 'bearish' (SMA50 < SMA200 or declining)."""
        self._df_ctx_config = regime
        return self

    def with_price_scaler(self, scaler):
        """Set price scaler (for GBP pence conversion testing)."""
        self._price_scaler = scaler
        return self

    def with_expired_window(self, window_count=10):
        """Force window count above limit."""
        self._window_count_override = window_count
        return self

    def with_seed(self, seed):
        """Set random seed for reproducibility."""
        self._seed = seed
        return self

    def with_resolving_adx(self):
        """Configure for RESOLVING state: ADX > 20 with 3-bar positive slope,
        but without full MA stack (so not TRENDING).
        For Profile B: breaks Golden Cross (SMA_200 > SMA_50)."""
        self._modifications.append(('resolving_setup', {}))
        return self

    def with_breakout(self):
        """Push the last bar's close above resistance (10-bar high)."""
        self._modifications.append(('breakout', {}))
        return self

    def with_exit_signal(self):
        """Configure for an EXIT signal (floor failure or VWAP breach)."""
        self._modifications.append(('exit_signal', {}))
        return self

    def with_no_golden_cross(self):
        """Break the Golden Cross (SMA_200 > SMA_50) to prevent TRENDING for Profile B.
        Used to create RESOLVING-only states."""
        self._modifications.append(('no_golden_cross', {}))
        return self

    def with_ensure_resolving(self):
        """Post-indicator patch: ensure RESOLVING state (ADX > 20, 3-bar positive slope).
        Forces ADX slope positive at the query bar."""
        self._modifications.append(('ensure_resolving', {}))
        return self

    def with_ensure_trending(self):
        """Post-indicator patch: ensure TRENDING state (full MA stack + ADX > 20).
        Forces close > EMA_8 > EMA_21 > SMA_50 at query bar."""
        self._modifications.append(('ensure_trending', {}))
        return self

    def with_break_squeeze(self):
        """Post-indicator patch: break MA Squeeze condition.
        Widens EMA_8 / EMA_21 gap so Squeeze is False."""
        self._modifications.append(('break_squeeze', {}))
        return self

    def with_force_squeeze(self):
        """Post-indicator patch: force MA Squeeze condition.
        Narrows EMA_8 / EMA_21 gap so Squeeze is True for 3+ bars
        while keeping ADX > 20."""
        self._modifications.append(('force_squeeze', {}))
        return self

    def with_high_floor_proximity(self, pct=20.0):
        """Push price far from SMA_200 for Profile C floor proximity failure."""
        self._modifications.append(('high_floor_proximity', {'pct': pct}))
        return self

    # ---- Build ----

    def build(self):
        """Build the DataFrame with full indicator stack computed.
        Returns a DataFrame ready for injection into the gate cascade."""
        rng = np.random.RandomState(self._seed)

        # Generate base OHLCV data
        n = self.total_bars
        closes = np.zeros(n)
        opens = np.zeros(n)
        highs = np.zeros(n)
        lows = np.zeros(n)
        volumes = np.zeros(n)

        closes[0] = self._base_price
        opens[0] = self._base_price
        highs[0] = self._base_price + self._bar_range * 0.6
        lows[0] = self._base_price - self._bar_range * 0.4
        volumes[0] = self._base_volume

        for i in range(1, n):
            # Trend + small noise
            trend_price = self._base_price + self._trend_slope * i
            noise = rng.normal(0, self._noise_scale * 0.3)
            closes[i] = trend_price + noise

            opens[i] = closes[i - 1] + rng.normal(0, self._noise_scale * 0.1)
            bar_range = self._bar_range + rng.uniform(-0.3, 0.3)
            highs[i] = max(opens[i], closes[i]) + abs(rng.normal(0, bar_range * 0.4))
            lows[i] = min(opens[i], closes[i]) - abs(rng.normal(0, bar_range * 0.4))
            volumes[i] = self._base_volume * (1.0 + rng.normal(0, self._volume_noise))

        # Ensure highs >= max(open, close) and lows <= min(open, close)
        highs = np.maximum(highs, np.maximum(opens, closes) + 0.01)
        lows = np.minimum(lows, np.minimum(opens, closes) - 0.01)
        volumes = np.maximum(volumes, 1000)  # floor volume

        df = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes,
        })

        # Apply modifications to the raw OHLCV data
        for mod_type, params in self._modifications:
            df = self._apply_modification(df, mod_type, params, rng)

        # Compute indicators
        df = _compute_indicators(df)

        # Handle ADX override (for MID-RANGE scenarios)
        if self._adx_override is not None:
            _iq = -2 if self.p_code == "A" else -1
            current_adx = df['ADX_14'].iloc[_iq]
            if current_adx > 0:
                scale = self._adx_override / current_adx
                df['ADX_14'] = df['ADX_14'] * scale

        # Handle -DI override (for directional block)
        if self._di_override == 'minus':
            # Swap DI columns
            dmp = df['DMP_14'].copy()
            dmn = df['DMN_14'].copy()
            df['DMP_14'] = dmn
            df['DMN_14'] = dmp

        # Set ANCHOR column based on profile
        df = self._set_anchor(df)

        # Post-indicator adjustments: fix scenarios that need precise indicator states
        for mod_type, params in self._modifications:
            df = self._post_indicator_adjust(df, mod_type, params)

        # Re-sync ANCHOR with underlying MA after post-adjustments
        # (post_indicator_adjust may have changed SMA_50/SMA_200/EMA values)
        df = self._set_anchor(df)

        # Store metadata
        df.attrs['p_code'] = self.p_code
        df.attrs['is_etf'] = self.is_etf
        df.attrs['price_scaler'] = self._price_scaler
        df.attrs['_adv_override'] = self._adv_override
        df.attrs['_window_count_override'] = self._window_count_override
        df.attrs['_df_ctx'] = self._build_context_df(rng) if self._df_ctx_config else None

        return df

    def _set_anchor(self, df):
        """Set the ANCHOR column based on profile/state."""
        if self.p_code == "A":
            # Profile A: ANCHOR = VWAP approximation.
            # Use a short rolling VWAP (15-bar window) to simulate intraday VWAP
            # session reset. Hourly bars reset VWAP each session (~7 bars).
            typical = (df['high'] + df['low'] + df['close']) / 3.0
            tp_vol = typical * df['volume']
            window = 15
            rolling_tp_vol = tp_vol.rolling(window=window, min_periods=1).sum()
            rolling_vol = df['volume'].rolling(window=window, min_periods=1).sum()
            df['VWAP_D'] = rolling_tp_vol / rolling_vol
            df['ANCHOR'] = df['VWAP_D']
        elif self.p_code == "C":
            df['ANCHOR'] = df['SMA_200']
        else:
            if self.is_etf:
                df['ANCHOR'] = df['SMA_50']
            else:
                df['ANCHOR'] = df['SMA_50']
        return df

    def _post_indicator_adjust(self, df, mod_type, params):
        """Apply adjustments after indicator computation to ensure target states.
        Some scenarios require precise indicator relationships that can't be
        guaranteed purely from OHLCV manipulation."""
        _iq = -2 if self.p_code == "A" else -1

        if mod_type == 'resolving_setup':
            # Ensure RESOLVING but NOT TRENDING:
            # Break the MA stack by pushing EMA_8 above close
            last_close = df['close'].iloc[_iq]
            ema8 = df['EMA_8'].iloc[_iq]
            if last_close > ema8:
                adjustment = (last_close - ema8) + 0.5
                df.loc[df.index[_iq], 'EMA_8'] = ema8 + adjustment
                for i in range(1, 4):
                    idx = _iq - i
                    if abs(idx) < len(df):
                        df.loc[df.index[idx], 'EMA_8'] = df['EMA_8'].iloc[idx] + adjustment * (0.8 ** i)

        elif mod_type == 'no_golden_cross':
            # Break Golden Cross: set SMA_200 above SMA_50 for recent bars
            # This prevents ma_stack_full for Profile B
            for i in range(10):
                idx = _iq - i
                if abs(idx) >= len(df):
                    break
                sma50 = df['SMA_50'].iloc[idx]
                sma200 = df['SMA_200'].iloc[idx]
                if not pd.isna(sma50) and (pd.isna(sma200) or sma200 <= sma50):
                    df.loc[df.index[idx], 'SMA_200'] = sma50 + 1.0

        elif mod_type == 'floor_violation':
            reclaim = params.get('reclaim', False)
            if reclaim:
                # Ensure the last bar's close is above ANCHOR and above EMA_8
                # (preserving MA stack for TRENDING/RESOLVING state through violation)
                last_anchor = df['ANCHOR'].iloc[_iq]
                last_ema8 = df['EMA_8'].iloc[_iq]
                target_close = max(last_anchor, last_ema8) + 0.5
                last_close = df['close'].iloc[_iq]
                if last_close < target_close:
                    df.loc[df.index[_iq], 'close'] = target_close
                    df.loc[df.index[_iq], 'high'] = max(df['high'].iloc[_iq], target_close + 0.5)
            # Fix DI values: floor violations create -DM spikes
            dmp = df['DMP_14'].iloc[_iq]
            dmn = df['DMN_14'].iloc[_iq]
            if dmn > dmp:
                df.loc[df.index[_iq], 'DMP_14'] = dmn + 2.0
                df.loc[df.index[_iq], 'DMN_14'] = dmp * 0.5

        elif mod_type == 'floor_failure':
            # Ensure bars are properly below/above ANCHOR
            bars_below = params['bars_below']
            reclaim_bars = params.get('reclaim_bars', 0)
            total = bars_below + reclaim_bars
            for i in range(total):
                idx = _iq - (total - 1 - i)
                if abs(idx) >= len(df):
                    continue
                anchor_val = df['ANCHOR'].iloc[idx]
                atr_val = df['ATRr_14'].iloc[idx]
                grace = GRACE_BUFFER_ATR_PCT * atr_val if not pd.isna(atr_val) else 0
                if i < bars_below:
                    if df['close'].iloc[idx] >= (anchor_val - grace):
                        df.loc[df.index[idx], 'close'] = anchor_val - grace - 1.0
                        df.loc[df.index[idx], 'low'] = min(df['low'].iloc[idx], df['close'].iloc[idx] - 0.5)
                else:
                    if df['close'].iloc[idx] < anchor_val:
                        df.loc[df.index[idx], 'close'] = anchor_val + 0.5
                        df.loc[df.index[idx], 'high'] = max(df['high'].iloc[idx], df['close'].iloc[idx] + 0.5)

        elif mod_type == 'breakout':
            # Ensure close is above resistance AND above EMA_8
            resistance = float(
                df['high'].iloc[-12:-2].max() if self.p_code == "A"
                else df['high'].iloc[-11:-1].max()
            )
            ema8 = df['EMA_8'].iloc[_iq]
            target_close = max(resistance, ema8) + 1.0
            df.loc[df.index[_iq], 'close'] = target_close
            df.loc[df.index[_iq], 'high'] = target_close + 1.0
            if df['open'].iloc[_iq] > target_close:
                df.loc[df.index[_iq], 'open'] = target_close - 0.5

        elif mod_type == 'extension':
            # Ensure DI+ > DI- (no DI block on extended scenarios)
            dmp = df['DMP_14'].iloc[_iq]
            dmn = df['DMN_14'].iloc[_iq]
            if dmn > dmp:
                df.loc[df.index[_iq], 'DMP_14'] = dmn + 1.0
                df.loc[df.index[_iq], 'DMN_14'] = dmp
            # Also ensure MA stack for TRENDING
            last_close = df['close'].iloc[_iq]
            ema8 = df['EMA_8'].iloc[_iq]
            ema21 = df['EMA_21'].iloc[_iq]
            sma50 = df['SMA_50'].iloc[_iq]
            if not (last_close > ema8 > ema21 > sma50):
                # Force MA stack by adjusting EMAs
                df.loc[df.index[_iq], 'EMA_8'] = last_close - 0.5
                df.loc[df.index[_iq], 'EMA_21'] = last_close - 1.5
                if sma50 > last_close - 2.0:
                    df.loc[df.index[_iq], 'SMA_50'] = last_close - 3.0

        elif mod_type == 'high_floor_proximity':
            # Push close far from SMA_200 for Profile C
            target_pct = params['pct']
            sma200 = df['SMA_200'].iloc[_iq]
            if not pd.isna(sma200) and sma200 > 0:
                target_close = sma200 * (1 + target_pct / 100)
                df.loc[df.index[_iq], 'close'] = target_close
                df.loc[df.index[_iq], 'high'] = target_close + 1.0

        elif mod_type == 'ensure_resolving':
            # Force ADX to have 3-bar positive slope (ADX > ADX-1 > ADX-2)
            adx = float(df['ADX_14'].iloc[_iq])
            adx1 = float(df['ADX_14'].iloc[_iq - 1])
            adx2 = float(df['ADX_14'].iloc[_iq - 2])
            if not (adx > adx1 > adx2) or adx <= 20:
                # Set ADX values to create positive slope above 20
                base_adx = max(adx, 22.0)
                df.loc[df.index[_iq], 'ADX_14'] = base_adx
                df.loc[df.index[_iq - 1], 'ADX_14'] = base_adx - 1.0
                df.loc[df.index[_iq - 2], 'ADX_14'] = base_adx - 2.0
            # Ensure no squeeze
            atr = df['ATRr_14'].iloc[_iq]
            ema8 = df['EMA_8'].iloc[_iq]
            ema21 = df['EMA_21'].iloc[_iq]
            if abs(ema8 - ema21) < 0.1 * atr:
                df.loc[df.index[_iq], 'EMA_8'] = ema21 + 0.2 * atr
                df.loc[df.index[_iq], 'Squeeze'] = False
                df.loc[df.index[_iq - 1], 'Squeeze'] = False

        elif mod_type == 'ensure_trending':
            # Force MA stack: close > EMA_8 > EMA_21 > SMA_50
            last_close = df['close'].iloc[_iq]
            atr = df['ATRr_14'].iloc[_iq] if not pd.isna(df['ATRr_14'].iloc[_iq]) else 1.0
            # Set EMA_8 just below close
            df.loc[df.index[_iq], 'EMA_8'] = last_close - 0.2 * atr
            df.loc[df.index[_iq], 'EMA_21'] = last_close - 0.5 * atr
            sma50 = df['SMA_50'].iloc[_iq]
            if not pd.isna(sma50) and sma50 >= last_close - 0.5 * atr:
                df.loc[df.index[_iq], 'SMA_50'] = last_close - 1.0 * atr
            # Ensure DI+ > DI-
            dmp = df['DMP_14'].iloc[_iq]
            dmn = df['DMN_14'].iloc[_iq]
            if dmn > dmp:
                df.loc[df.index[_iq], 'DMP_14'] = dmn + 2.0
                df.loc[df.index[_iq], 'DMN_14'] = dmp * 0.5
            # Ensure no squeeze
            df.loc[df.index[_iq], 'Squeeze'] = False
            df.loc[df.index[_iq - 1], 'Squeeze'] = False
            df.loc[df.index[_iq - 2], 'Squeeze'] = False

        elif mod_type == 'break_squeeze':
            # Widen EMA gap so Squeeze condition is False
            atr = df['ATRr_14'].iloc[_iq] if not pd.isna(df['ATRr_14'].iloc[_iq]) else 1.0
            for i in range(3):
                idx = _iq - i
                if abs(idx) >= len(df):
                    break
                ema8 = df['EMA_8'].iloc[idx]
                ema21 = df['EMA_21'].iloc[idx]
                atr_i = df['ATRr_14'].iloc[idx] if not pd.isna(df['ATRr_14'].iloc[idx]) else atr
                if abs(ema8 - ema21) < 0.15 * atr_i:
                    df.loc[df.index[idx], 'EMA_8'] = ema21 + 0.2 * atr_i
                df.loc[df.index[idx], 'MA_Dist'] = abs(df['EMA_8'].iloc[idx] - df['EMA_21'].iloc[idx])
                df.loc[df.index[idx], 'Squeeze'] = df['MA_Dist'].iloc[idx] < (0.1 * atr_i)

        elif mod_type == 'force_squeeze':
            # Force EMA 8/21 gap < 0.1 ATR for 3+ bars → squeeze condition True
            atr = df['ATRr_14'].iloc[_iq] if not pd.isna(df['ATRr_14'].iloc[_iq]) else 1.0
            for i in range(4):  # 4 bars to ensure 3 consecutive at _iq, _iq-1, _iq-2
                idx = _iq - i
                if abs(idx) >= len(df):
                    break
                atr_i = df['ATRr_14'].iloc[idx] if not pd.isna(df['ATRr_14'].iloc[idx]) else atr
                ema21 = df['EMA_21'].iloc[idx]
                # Set EMA_8 very close to EMA_21 (< 0.1 * ATR gap)
                df.loc[df.index[idx], 'EMA_8'] = ema21 + 0.05 * atr_i
                df.loc[df.index[idx], 'MA_Dist'] = abs(df['EMA_8'].iloc[idx] - ema21)
                df.loc[df.index[idx], 'Squeeze'] = True
            # Also ensure ADX > 20 so this is a squeeze halt, not ADX < 20 halt
            if df['ADX_14'].iloc[_iq] < 22:
                current_adx = df['ADX_14'].iloc[_iq]
                scale = 23.0 / current_adx if current_adx > 0 else 1.0
                df['ADX_14'] = df['ADX_14'] * scale

        return df

    def _apply_modification(self, df, mod_type, params, rng):
        """Apply a modification to the raw OHLCV data."""
        n = len(df)

        if mod_type == 'pullback':
            bars = params['bars']
            depth = params['depth_atr']
            # Estimate ATR from recent bars
            recent_ranges = (df['high'].iloc[-50:] - df['low'].iloc[-50:]).mean()
            drop = depth * recent_ranges
            for i in range(bars):
                idx = n - bars + i
                if idx < 0:
                    continue
                frac = (i + 1) / bars
                adjustment = -drop * frac
                df.iloc[idx, df.columns.get_loc('close')] += adjustment
                df.iloc[idx, df.columns.get_loc('open')] += adjustment * 0.8
                df.iloc[idx, df.columns.get_loc('high')] += adjustment * 0.5
                df.iloc[idx, df.columns.get_loc('low')] += adjustment * 1.2
            # Ensure OHLC consistency
            df['high'] = df[['open', 'close', 'high']].max(axis=1) + 0.01
            df['low'] = df[['open', 'close', 'low']].min(axis=1) - 0.01

        elif mod_type == 'floor_violation':
            bars_below = params['bars_below']
            depth = params['depth_atr']
            reclaim = params['reclaim']
            # Push bars below where SMA50 will be
            recent_ranges = (df['high'].iloc[-50:] - df['low'].iloc[-50:]).mean()
            sma50_est = df['close'].iloc[-60:-10].mean()  # rough SMA50
            violation_depth = depth * recent_ranges

            total = bars_below + (1 if reclaim else 0)
            for i in range(total):
                idx = n - total + i
                if idx < 0:
                    continue
                if i < bars_below:
                    # Below floor
                    df.iloc[idx, df.columns.get_loc('close')] = sma50_est - violation_depth
                    df.iloc[idx, df.columns.get_loc('open')] = sma50_est - violation_depth * 0.5
                    df.iloc[idx, df.columns.get_loc('low')] = sma50_est - violation_depth * 1.3
                    df.iloc[idx, df.columns.get_loc('high')] = sma50_est - violation_depth * 0.2
                else:
                    # Reclaim bar: close above floor
                    df.iloc[idx, df.columns.get_loc('close')] = sma50_est + violation_depth * 0.5
                    df.iloc[idx, df.columns.get_loc('open')] = sma50_est - violation_depth * 0.2
                    df.iloc[idx, df.columns.get_loc('low')] = sma50_est - violation_depth * 0.3
                    df.iloc[idx, df.columns.get_loc('high')] = sma50_est + violation_depth * 0.7
            df['high'] = df[['open', 'close', 'high']].max(axis=1) + 0.01
            df['low'] = df[['open', 'close', 'low']].min(axis=1) - 0.01

        elif mod_type == 'floor_failure':
            bars_below = params['bars_below']
            depth = params['depth_atr']
            reclaim_bars = params['reclaim_bars']
            recent_ranges = (df['high'].iloc[-50:] - df['low'].iloc[-50:]).mean()
            sma50_est = df['close'].iloc[-60:-10].mean()
            violation_depth = depth * recent_ranges

            total = bars_below + reclaim_bars
            for i in range(total):
                idx = n - total + i
                if idx < 0:
                    continue
                if i < bars_below:
                    df.iloc[idx, df.columns.get_loc('close')] = sma50_est - violation_depth
                    df.iloc[idx, df.columns.get_loc('open')] = sma50_est - violation_depth * 0.7
                    df.iloc[idx, df.columns.get_loc('low')] = sma50_est - violation_depth * 1.4
                    df.iloc[idx, df.columns.get_loc('high')] = sma50_est - violation_depth * 0.3
                else:
                    # Reclaim bar
                    df.iloc[idx, df.columns.get_loc('close')] = sma50_est + violation_depth * 0.3
                    df.iloc[idx, df.columns.get_loc('open')] = sma50_est - violation_depth * 0.1
                    df.iloc[idx, df.columns.get_loc('low')] = sma50_est - violation_depth * 0.2
                    df.iloc[idx, df.columns.get_loc('high')] = sma50_est + violation_depth * 0.5
            df['high'] = df[['open', 'close', 'high']].max(axis=1) + 0.01
            df['low'] = df[['open', 'close', 'low']].min(axis=1) - 0.01

        elif mod_type == 'climax':
            bars_ago = params['bars_ago']
            idx = n - 1 - bars_ago
            if idx >= 0:
                vol_sma = df['volume'].iloc[max(0, idx - 9):idx].mean()
                df.iloc[idx, df.columns.get_loc('volume')] = vol_sma * 2.5
                # Negative close (close < open)
                current_open = df.iloc[idx]['open']
                current_range = df.iloc[idx]['high'] - df.iloc[idx]['low']
                df.iloc[idx, df.columns.get_loc('close')] = current_open - current_range * 0.6

        elif mod_type == 'extension':
            atr_mult = params['atr_multiple']
            recent_ranges = (df['high'].iloc[-30:] - df['low'].iloc[-30:]).mean()
            # Push last few bars high above MA anchor
            sma50_est = df['close'].iloc[-55:-5].mean()
            target_close = sma50_est + atr_mult * recent_ranges * 1.5
            for i in range(3):
                idx = n - 3 + i
                df.iloc[idx, df.columns.get_loc('close')] = target_close + rng.normal(0, 0.5)
                df.iloc[idx, df.columns.get_loc('open')] = target_close - 0.5
                df.iloc[idx, df.columns.get_loc('high')] = target_close + 1.0
                df.iloc[idx, df.columns.get_loc('low')] = target_close - 1.5

        elif mod_type == 'fresh_window':
            # Create a pullback zone touch (Is_Pullback event) at bars_ago
            bars_ago = params['bars_ago']
            idx = n - 1 - bars_ago
            if idx > 50:
                sma50_est = df['close'].iloc[idx - 50:idx].mean()
                # Touch the floor then bounce
                df.iloc[idx, df.columns.get_loc('close')] = sma50_est + 0.1
                df.iloc[idx, df.columns.get_loc('low')] = sma50_est - 0.5

        elif mod_type == 'gap_trap':
            # Last bar: open > prev_high + 0.5*ATR, close < open
            if n >= 3:
                recent_ranges = (df['high'].iloc[-20:] - df['low'].iloc[-20:]).mean()
                prev_high = df.iloc[-2]['high']
                gap_open = prev_high + 0.6 * recent_ranges
                gap_close = gap_open - 0.3 * recent_ranges
                df.iloc[-1, df.columns.get_loc('open')] = gap_open
                df.iloc[-1, df.columns.get_loc('close')] = gap_close
                df.iloc[-1, df.columns.get_loc('high')] = gap_open + 0.2
                df.iloc[-1, df.columns.get_loc('low')] = gap_close - 0.3

        elif mod_type == 'resolving_setup':
            # Weaken the trend so MA stack isn't fully stacked but ADX has positive slope
            # Make EMA_8 < EMA_21 in some bars to break ma_stack_full
            for i in range(5):
                idx = n - 10 + i
                if idx >= 0:
                    df.iloc[idx, df.columns.get_loc('close')] -= 2.0

        elif mod_type == 'breakout':
            # Push last bar above 10-bar high
            if n > 12:
                ten_bar_high = df['high'].iloc[-12:-2].max() if self.p_code == "A" else df['high'].iloc[-11:-1].max()
                df.iloc[-1, df.columns.get_loc('close')] = ten_bar_high + 1.0
                df.iloc[-1, df.columns.get_loc('high')] = ten_bar_high + 2.0
                df.iloc[-1, df.columns.get_loc('open')] = ten_bar_high - 0.5

        elif mod_type == 'exit_signal':
            # Not used directly - exit_signal is derived in the harness
            pass

        return df

    def _build_context_df(self, rng):
        """Build a context DataFrame for CRG gate testing."""
        n = 60  # enough bars for SMA computations
        regime = self._df_ctx_config

        if regime == 'bullish':
            # Steady uptrend: SMA50 > SMA200, price above SMA200
            base = 100.0
            closes = [base + 0.5 * i + rng.normal(0, 0.3) for i in range(n)]
        elif regime == 'bearish':
            # Downtrend: SMA50 < SMA200 or price below SMA200
            base = 150.0
            closes = [base - 0.5 * i + rng.normal(0, 0.3) for i in range(n)]
        elif regime == 'bearish_weekly':
            # For Profile B CRG-2: weekly SMA50 declining
            base = 150.0
            closes = [base - 0.3 * i + rng.normal(0, 0.2) for i in range(n)]
        elif regime == 'bullish_weekly':
            # For Profile B CRG-2: weekly SMA50 rising
            base = 100.0
            closes = [base + 0.3 * i + rng.normal(0, 0.2) for i in range(n)]
        else:
            base = 100.0
            closes = [base + rng.normal(0, 1.0) for _ in range(n)]

        ctx_df = pd.DataFrame({
            'close': closes,
            'high': [c + abs(rng.normal(0, 0.5)) for c in closes],
            'low': [c - abs(rng.normal(0, 0.5)) for c in closes],
            'open': [closes[max(0, i - 1)] for i in range(n)],
            'volume': [500000 + rng.normal(0, 50000) for _ in range(n)],
        })

        ctx_df['SMA_50'] = _compute_sma(ctx_df['close'], 50)
        ctx_df['SMA_200'] = _compute_sma(ctx_df['close'], min(200, n - 1))
        ctx_df['EMA_8'] = _compute_ema(ctx_df['close'], 8)
        ctx_df['EMA_21'] = _compute_ema(ctx_df['close'], 21)
        ctx_df['vol_sma_9'] = _compute_sma(ctx_df['volume'], 9)

        return ctx_df


# ---------------------------------------------------------------------------
# Gate Cascade Harness
# ---------------------------------------------------------------------------

def run_gate_cascade(df, p_code=None, is_etf=None, df_ctx=None,
                     price_scaler=None, adv_override=None,
                     window_count_override=None):
    """Run the full gate cascade against a synthetic DataFrame.

    Invokes the 15 extracted gate functions in the exact Execution Map v1.9
    order, bypassing the data-fetch layer. Computes all derived state variables
    from the DataFrame using the same logic as the engine.

    Approach rationale: _evaluate_gates() does not yet exist as a standalone
    function. Phase 1 extracted 15 gate functions as top-level functions, but
    the gate cascade is still sequential calls inside run_tbs_engine(). This
    harness replicates that cascade with synthetic data and zero IBKR dependency.

    Returns:
        tuple: (status, diagnostic) where status is "PASS", "HALT", or "WAIT".
               For PASS, diagnostic contains the trigger type.
               For HALT/WAIT, diagnostic contains the rejection reason.
    """

    # Import gate functions from engine
    from ibkr_purity_engine import (
        _gate_context_regime,
        _gate_liquidity,
        _gate_data_integrity,
        _gate_floor_failure,
        _gate_floor_violation,
        _gate_floor_violation_active,
        _gate_climax,
        _gate_midrange,
        _gate_directional,
        _gate_modifier_e,
        _gate_window,
        _gate_extension,
        _gate_floor_proximity_c,
        _gate_expectancy,
        _gate_capital_expectancy,
        check_climax_history,
    )

    # Extract metadata from DataFrame attrs (set by builder)
    if p_code is None:
        p_code = df.attrs.get('p_code', 'B')
    if is_etf is None:
        is_etf = df.attrs.get('is_etf', False)
    if price_scaler is None:
        price_scaler = df.attrs.get('price_scaler', 1.0)
    if adv_override is None:
        adv_override = df.attrs.get('_adv_override', None)
    if window_count_override is None:
        window_count_override = df.attrs.get('_window_count_override', None)
    if df_ctx is None:
        df_ctx = df.attrs.get('_df_ctx', None)

    metrics = {}
    _is_lse_etf = False

    # ---- Indicator query index (Profile A bar-close cadence: PE-9) ----
    _iq = -2 if p_code == "A" else -1

    # ---- Extract indicator values ----
    adx_col = 'ADX_14'
    dmp_col = 'DMP_14'
    dmn_col = 'DMN_14'

    adx_t = float(df[adx_col].iloc[_iq])
    adx_t1 = float(df[adx_col].iloc[_iq - 1])
    adx_t2 = float(df[adx_col].iloc[_iq - 2])
    di_plus = float(df[dmp_col].iloc[_iq])
    di_minus = float(df[dmn_col].iloc[_iq])

    # NaN guard
    if any(pd.isna(v) for v in [adx_t, adx_t1, adx_t2, di_plus, di_minus]):
        return ("HALT", "REJECT (reason: DATA INTEGRITY). ADX/DI values contain NaN.")

    # ---- ADX Slope Acceleration ----
    adx_slope_t = adx_t - adx_t1
    adx_slope_t1 = adx_t1 - adx_t2
    adx_accel = round(adx_slope_t - adx_slope_t1, 2)
    adx_accel_state = (
        "ACCELERATING" if adx_accel > 0.3 else
        "DECELERATING" if adx_accel < -0.3 else
        "CRUISING"
    )

    # ---- MA Squeeze ----
    ma_squeeze = bool(
        df['Squeeze'].iloc[_iq] and df['Squeeze'].iloc[_iq - 1] and df['Squeeze'].iloc[_iq - 2]
    )

    # ---- Reference bar ----
    last = df.iloc[-2] if p_code == "A" else df.iloc[-1]

    # ---- State Classification ----
    is_resolving = (
            (adx_t > 20) and
            (adx_t > adx_t1 > adx_t2) and
            not ma_squeeze
    )

    ma_stack_full = (
            last['close'] > last['EMA_8'] and
            last['EMA_8'] > last['EMA_21'] and
            last['EMA_21'] > last['SMA_50'] and
            (p_code != "B" or (not pd.isna(last['SMA_200']) and last['SMA_50'] > last['SMA_200']))
    )
    is_trending = ma_stack_full and (adx_t > 20) and not ma_squeeze

    ema_stacked = last['EMA_8'] > last['EMA_21']

    # ETF Logic Lock
    _etf_entry_trending = False
    _etf_entry_resolving = False
    if is_etf:
        _etf_entry_trending = is_trending
        _etf_entry_resolving = is_resolving
        is_resolving = False
        is_trending = False
    else:
        _etf_entry_trending = False
        _etf_entry_resolving = False

    _entry_trending = is_trending or _etf_entry_trending
    _entry_resolving = is_resolving or _etf_entry_resolving

    # ---- Scaling, Floor, Stops ----
    atr_raw = float(last['ATRr_14'])
    structural_floor_raw = float(last['ANCHOR'])
    actual_price = last['close'] / price_scaler
    hard_stop_raw = structural_floor_raw - (1.5 * atr_raw)
    floor_raw = structural_floor_raw
    floor_price = round(floor_raw / price_scaler, 2)

    # ---- Resistance ----
    resistance_raw = float(
        df['high'].iloc[-12:-2].max() if p_code == "A"
        else df['high'].iloc[-11:-1].max()
    )
    resistance_display = round(resistance_raw / price_scaler, 2)
    _resistance_suppressed = resistance_display < actual_price

    # ---- Proximity Anchor & Extension ----
    if is_etf:
        if p_code == "A":
            prox_anchor = last.get('VWAP_D', last['ANCHOR'])
        elif p_code == "B":
            prox_anchor = last['SMA_50']
        else:
            prox_anchor = last['SMA_200']
    elif p_code == "A":
        prox_anchor = last.get('VWAP_D', last['ANCHOR'])
    elif p_code == "C":
        prox_anchor = last['SMA_200']
    else:
        prox_anchor = last['EMA_8'] if (is_resolving and not is_trending) else last['EMA_21']

    atr_dist = (last['close'] - prox_anchor) / atr_raw if atr_raw > 0 else 0

    # Extension limit
    if p_code == "A":
        ext_limit = 1.5
    elif p_code == "C":
        ext_limit = 0.5 if is_etf else 1.0
    elif is_etf:
        ext_limit = 0.5
    elif is_trending:
        ext_limit = 1.0
    else:
        ext_limit = 0.5

    # ---- ADV ----
    if adv_override is not None:
        adv_20 = float(adv_override)
    else:
        vol_sma_20 = float(df['vol_sma_20'].iloc[-1])
        bars_per_day = 7  # default for daily
        adv_20 = float((vol_sma_20 * actual_price) * bars_per_day)

    # ---- Morphology / prev_high ----
    prev_high = float(df['high'].iloc[-3] if p_code == "A" else df['high'].iloc[-2])

    # ---- Volume confirmation ----
    _vol_sma9_ref = float(df['vol_sma_9'].iloc[-2] if p_code == "A" else df['vol_sma_9'].iloc[-1])
    vol_confirm_ratio = 0.6  # neutral default
    vol_confirm_state = "NEUTRAL"

    # ---- Floor state computation (main) ----
    _ff_threshold = 8 if p_code == "A" else 4
    _ff_lookback = _ff_threshold + 1
    grace = GRACE_BUFFER_ATR_PCT * atr_raw if atr_raw > 0 else 0

    # Determine floor state from ANCHOR column
    if last['close'] >= last['ANCHOR']:
        # Current bar above floor
        consec_below = 0
        for offset in range(1, _ff_lookback):
            idx = _iq - offset
            if abs(idx) >= len(df):
                break
            bar_anchor = df.iloc[idx]['ANCHOR']
            bar_close = df.iloc[idx]['close']
            if (bar_anchor - bar_close) > grace:
                consec_below += 1
            else:
                break
        is_violated = False
        is_reclaim = (1 <= consec_below <= (_ff_threshold - 1))
        is_floor_failure = (consec_below >= _ff_threshold)
    else:
        # Current bar below floor
        consec_below = 0
        for offset in range(0, _ff_lookback):
            idx = _iq - offset
            if abs(idx) >= len(df):
                break
            bar_anchor = df.iloc[idx]['ANCHOR']
            bar_close = df.iloc[idx]['close']
            if (bar_anchor - bar_close) > grace:
                consec_below += 1
            else:
                break
        is_violated = (1 <= consec_below <= (_ff_threshold - 1))
        is_reclaim = False
        is_floor_failure = (consec_below >= _ff_threshold)

    # ---- Window counting ----
    if window_count_override is not None:
        window_count = window_count_override
    else:
        window_limit = 4 if p_code == "A" else (5 if p_code == "B" else 4)
        # Simplified window counting: look for pullback/breakout events
        _pb_upper = (df['EMA_21'] + 0.5 * df['ATRr_14']) if p_code == "B" else (df['ANCHOR'] + 0.5 * df['ATRr_14'])
        is_pullback = (df['close'] >= df['ANCHOR']) & (df['close'] <= _pb_upper)
        is_breakout = df['close'] > resistance_raw
        is_event = is_pullback | is_breakout
        # Look backward from _iq for most recent event
        recent = is_event.iloc[max(0, _iq - 20):_iq + 1 if _iq != -1 else len(df)]
        recent_list = recent.tolist()
        if any(recent_list):
            window_count = recent_list[::-1].index(True)
        else:
            window_count = 99

    window_limit = 4 if p_code == "A" else (5 if p_code == "B" else 4)

    # ---- Floor proximity (Profile C) ----
    if p_code == "C" and not pd.isna(last['SMA_200']) and last['SMA_200'] > 0:
        floor_prox_pct = round(
            abs(last['close'] - last['SMA_200']) / last['SMA_200'] * 100, 2
        )
    else:
        floor_prox_pct = None

    # ---- Exit signal (simplified) ----
    exit_signal = False

    # ---- Consolidation High (Profile A) ----
    cons_high_raw = None
    if p_code == "A" and df_ctx is not None and len(df_ctx) > 11:
        cons_high_raw = float(df_ctx['high'].iloc[-11:-1].max())
        if cons_high_raw < last['close']:
            cons_high_raw = resistance_raw
    elif p_code == "A":
        cons_high_raw = resistance_raw

    # ---- R:R variables (initialized before gates, computed for Profile A) ----
    risk_a = None
    reward_a = None

    # ==================================================================
    # GATE CASCADE (Execution Map v1.9 order)
    # ==================================================================

    # Gate 1: Context Regime (CRG-1 Profile A, CRG-2 Profile B)
    _result = _gate_context_regime(p_code, df_ctx, price_scaler, metrics)
    if _result is not None:
        return _result

    # Gate 2: Liquidity
    _result = _gate_liquidity(adv_20, is_etf, _is_lse_etf, metrics)
    if _result is not None:
        return _result

    # --- FLOOR VIOLATION PRE-CHECK ---
    # Replicates inline Pre-Check block (engine lines 2770-2861)
    if atr_raw > 0:
        _precheck_i0 = -2 if p_code == "A" else -1
        floor_dist_pre = (df['close'].iloc[_precheck_i0] - df['ANCHOR'].iloc[_precheck_i0]) / atr_raw
        grace_pre = GRACE_BUFFER_ATR_PCT * atr_raw
        consec_pre = 0
        for offset in range(1, _ff_lookback):
            idx = _precheck_i0 - offset
            if abs(idx) > len(df):
                break
            bar_dist = df.iloc[idx]['ANCHOR'] - df.iloc[idx]['close']
            if bar_dist > grace_pre:
                consec_pre += 1
            else:
                break
        _precheck_current_above = df['close'].iloc[_precheck_i0] >= df['ANCHOR'].iloc[_precheck_i0]
        is_floor_failure_pre = consec_pre >= _ff_threshold
        is_violated_pre = 1 <= consec_pre <= (_ff_threshold - 1)
        is_reclaim_pre = is_violated_pre and _precheck_current_above

        if is_floor_failure_pre:
            _pre_reclaim = 1 if _precheck_current_above else 0
            metrics["Exit_Signal"] = "EXIT"
            return ("HALT",
                    f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE"
                    f"{' RECOVERY' if _pre_reclaim > 0 else ''}: "
                    f"{consec_pre} consecutive bars below Floor. "
                    + (f"Reclaim {_pre_reclaim}/3 -- need {3 - _pre_reclaim} more close(s) above floor."
                       if _pre_reclaim > 0 else "Structural break."))

        # Deep scan for hidden floor failure behind reclaim streak
        if not is_floor_failure_pre and _precheck_current_above and not is_violated_pre:
            _pre_reclaim = 0
            for _pr_off in range(0, _ff_threshold + 4):
                idx = _precheck_i0 - _pr_off
                if abs(idx) > len(df):
                    break
                if df['close'].iloc[idx] >= df['ANCHOR'].iloc[idx]:
                    _pre_reclaim += 1
                else:
                    break
            if 1 <= _pre_reclaim <= 2:
                _pre_hist = 0
                for _ph_off in range(_pre_reclaim, _pre_reclaim + _ff_lookback):
                    idx = _precheck_i0 - _ph_off
                    if abs(idx) > len(df):
                        break
                    _ph_dist = df['ANCHOR'].iloc[idx] - df['close'].iloc[idx]
                    if _ph_dist > grace_pre:
                        _pre_hist += 1
                    else:
                        break
                if _pre_hist >= _ff_threshold:
                    metrics["Exit_Signal"] = "EXIT"
                    return ("HALT",
                            f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE RECOVERY: "
                            f"{_pre_hist} bars below Floor. "
                            f"Reclaim {_pre_reclaim}/3 -- need {3 - _pre_reclaim} more close(s) above floor.")

        if is_violated_pre and not is_reclaim_pre:
            return ("HALT",
                    f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION ACTIVE: "
                    f"{consec_pre} bar(s) below Floor ({floor_price}).")

        if floor_dist_pre < -0.15 and not is_violated_pre:
            return ("HALT",
                    f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION: "
                    f"Price {abs(floor_dist_pre):.2f} ATR below Floor.")

    # --- PROFILE A EXPECTANCY PRE-CHECK ---
    if p_code == "A":
        if cons_high_raw is not None:
            reward_a = cons_high_raw - last['close']
            risk_a = last['close'] - last['ANCHOR']
            _exp_grace = GRACE_BUFFER_ATR_PCT * atr_raw if atr_raw > 0 else 0

            if pd.isna(risk_a):
                return ("HALT", "REJECT (reason: DATA INTEGRITY). Invalid Reward/Risk: risk_a is NaN.")

            if risk_a < -_exp_grace:
                return ("HALT",
                        f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION ACTIVE: "
                        f"price is {abs(risk_a / atr_raw):.2f} ATR below floor.")

            if risk_a < 0:
                risk_a = 0
            if risk_a == 0:
                if reward_a <= 0:
                    return ("HALT", "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: no upside reward.")
                risk_a_hardstop = last['close'] - hard_stop_raw
                if risk_a_hardstop <= 0:
                    return ("HALT", "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: hard stop above price.")
                rr_hardstop = reward_a / risk_a_hardstop
                if rr_hardstop < 2.0:
                    metrics["Reward_Risk"] = round(rr_hardstop, 2)
                    return ("HALT",
                            f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY FAILED (FLOOR EXACT): "
                            f"R:R {round(rr_hardstop, 2)}:1 < 2.0")
                metrics["Reward_Risk"] = round(rr_hardstop, 2)
                metrics["Profit_Target"] = round(cons_high_raw / price_scaler, 2)
            elif risk_a < (0.20 * atr_raw):
                risk_a_hardstop = last['close'] - hard_stop_raw
                if risk_a_hardstop <= 0:
                    return ("HALT", "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: hard stop above price.")
                rr_hardstop = reward_a / risk_a_hardstop
                if rr_hardstop < 2.0:
                    metrics["Reward_Risk"] = round(rr_hardstop, 2)
                    return ("HALT",
                            f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY FAILED (FLOOR PROXIMITY): "
                            f"R:R {round(rr_hardstop, 2)}:1 < 2.0")
                metrics["Reward_Risk"] = round(rr_hardstop, 2)
                metrics["Profit_Target"] = round(cons_high_raw / price_scaler, 2)
            else:
                metrics["Reward_Risk"] = round(reward_a / risk_a, 2)
                metrics["Profit_Target"] = round(cons_high_raw / price_scaler, 2)

    # PE-7 Profile A Guard
    if p_code == "A" and exit_signal == "EXIT":
        metrics["Reward_Risk"] = None
        metrics["Profit_Target"] = None

    # --- PHASE 3 GATE EVALUATION ---

    # Gate 3: Data Integrity
    _result = _gate_data_integrity(atr_raw, metrics)
    if _result is not None:
        return _result

    floor_dist = (last['close'] - last['ANCHOR']) / atr_raw if atr_raw > 0 else 0

    # Gate 4: Floor Failure
    _result = _gate_floor_failure(consec_below, is_floor_failure, p_code, metrics)
    if _result is not None:
        return _result

    # Gate 5: Floor Violation
    _result = _gate_floor_violation(floor_dist, is_violated, p_code, metrics)
    if _result is not None:
        return _result

    # Gate 6: Floor Violation Active (no reclaim)
    _result = _gate_floor_violation_active(
        is_violated, is_reclaim, consec_below, floor_price,
        last['close'], price_scaler, metrics)
    if _result is not None:
        return _result

    # Gate 7: Volume Climax
    _result = _gate_climax(df, p_code, is_reclaim, check_climax_history, metrics)
    if _result is not None:
        return _result

    # Gate 8: MID-RANGE
    _result = _gate_midrange(adx_t, ma_squeeze, atr_dist, ext_limit, metrics)
    if _result is not None:
        return _result

    # Gate 9: Directional Dominance
    _result = _gate_directional(
        di_plus, di_minus, p_code, ema_stacked, _entry_trending,
        ma_stack_full, floor_prox_pct, adx_t, adx_t1, metrics)
    if _result is not None:
        return _result

    # Gate 10: Modifier E
    _result = _gate_modifier_e(last['open'], prev_high, atr_raw, last['close'], metrics)
    if _result is not None:
        return _result

    # Gate 11: Window
    _result = _gate_window(window_count, window_limit, metrics)
    if _result is not None:
        return _result

    # Gate 12: Extension
    # [RFT-003 Phase 3] _gate_extension now accepts (ctx, atr_dist, ext_limit)
    _ext_state = SimpleNamespace(
        is_trending=is_trending, is_resolving=is_resolving,
        _entry_trending=_entry_trending, _entry_resolving=_entry_resolving,
        atr_raw=atr_raw,
    )
    _ext_ctx = SimpleNamespace(
        state=_ext_state, p_code=p_code, is_etf=is_etf, last=last,
        resistance_raw=resistance_raw, resistance_display=resistance_display,
        _resistance_suppressed=_resistance_suppressed,
        floor_prox_pct=floor_prox_pct if floor_prox_pct is not None else 0.0,
        metrics=metrics,
        adx_accel_state=adx_accel_state, adx_accel=adx_accel,
        vol_confirm_state=vol_confirm_state, vol_confirm_ratio=vol_confirm_ratio,
        exit_signal=exit_signal, structural_floor_raw=structural_floor_raw,
        price_scaler=price_scaler, ext_limit=ext_limit,
    )
    _result = _gate_extension(_ext_ctx, atr_dist, ext_limit)
    if _result is not None:
        return _result

    # Gate 13: Floor Proximity (Profile C)
    _result = _gate_floor_proximity_c(p_code, last, floor_prox_pct, metrics)
    if _result is not None:
        return _result

    # Gate 14: Expectancy (Profile A)
    _result = _gate_expectancy(
        p_code, risk_a, reward_a, cons_high_raw, last['close'],
        floor_price, price_scaler, metrics)
    if _result is not None:
        return _result

    # Gate 15: Capital Expectancy (CEG-001)
    _result = _gate_capital_expectancy(
        p_code, risk_a, cons_high_raw, last['close'],
        hard_stop_raw, resistance_raw, atr_raw,
        price_scaler, metrics)
    if _result is not None:
        return _result

    # --- PHASE 4: TRIGGER IDENTIFICATION ---
    # Replicate the engine's Phase 4 if/elif/elif/else chain

    # Current-bar position flags
    _pb_upper_cur = (
        (last['EMA_21'] + (0.5 * atr_raw)) if p_code == "B"
        else (last['ANCHOR'] + (0.5 * atr_raw))
    )
    at_pullback_zone = (
            (last['close'] >= last['ANCHOR']) and
            (last['close'] <= _pb_upper_cur)
    )

    _convex_support_level = last['ANCHOR'] if is_etf else last['EMA_8']
    at_breakout = (
            (last['close'] > resistance_raw) and
            (last['close'] > _convex_support_level)
    )

    # Priority 1: RECLAIM
    if is_reclaim and (_entry_trending or _entry_resolving):
        return ("PASS", "RECLAIM: Floor violation recovered. Entry valid on confirmed reclaim.")

    # Priority 1b: RECLAIM but ambiguous
    if is_reclaim and not (_entry_trending or _entry_resolving):
        return ("HALT", "RECLAIM DETECTED but state AMBIGUOUS. Structural bounce, not qualified entry.")

    # Priority 2: TRENDING pullback
    if _entry_trending:
        if at_pullback_zone:
            return ("PASS", f"TRENDING PULLBACK: Price in pullback zone. Entry valid.")
        elif at_breakout:
            return ("PASS", f"TRENDING BREAKOUT: Price above resistance. Entry valid.")
        else:
            # Trending but not in pullback zone or breakout
            return ("PASS", f"TRENDING: Entry valid (state confirmed).")

    # Priority 3: RESOLVING breakout
    if _entry_resolving:
        if at_breakout:
            return ("PASS", f"RESOLVING BREAKOUT: Price above resistance + convex support.")
        elif p_code == "A":
            return ("HALT", "CONVEXITY PROTOCOL BLOCKED (Profile A): Must wait for VWAP pullback.")
        else:
            return ("HALT", f"RESOLVING: No breakout confirmed. Price below resistance.")

    # Priority 4: AMBIGUOUS
    is_ambiguous = not (_entry_trending or _entry_resolving)
    if is_ambiguous:
        return ("HALT", f"AMBIGUOUS: ADX {adx_t:.1f}, no confirmed directional state. HARD WAIT.")

    # Should not reach here
    return ("HALT", "UNKNOWN: Unhandled state in gate cascade.")
