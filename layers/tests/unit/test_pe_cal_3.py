"""Unit tests for PE-CAL-3: Profile A Floor Proximity Expectancy Recalibration.

Tests the reduced R:R threshold (1.2) in the FLOOR_EXACT and FLOOR_PROXIMITY
sentinel zones of _evaluate_precheck(), the new metric fields
(Expectancy_Threshold, Expectancy_Threshold_Note), and diagnostic strings.

12 test functions covering:
    - FLOOR_PROXIMITY zone: PASS, REJECT, boundary at 1.2, boundary at 1.199
    - Profile B isolation (no contamination)
    - FLOOR_EXACT zone: PASS, REJECT
    - Standard path isolation (risk_a >= 0.20 * ATR)
    - Metric field values (1.2 sentinel, 2.0 standard)
    - Expectancy_Threshold_Note string content
    - REJECT diagnostic references PE-CAL-3
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace

from ibkr_purity_engine import (
    GateResult,
    _evaluate_precheck,
    GRACE_BUFFER_ATR_PCT,
)


# ---------------------------------------------------------------------------
# Helpers (copied from test_phase4_extractions.py — no cross-test imports)
# ---------------------------------------------------------------------------

def _make_df(n=60, base=100.0, trend=0.2, seed=42):
    """Build a minimal OHLCV DataFrame with ANCHOR and indicator columns."""
    rng = np.random.RandomState(seed)
    closes = [base + trend * i + rng.normal(0, 0.3) for i in range(n)]
    df = pd.DataFrame({
        'open':   [closes[max(0, i - 1)] + rng.normal(0, 0.1) for i in range(n)],
        'high':   [c + abs(rng.normal(0.5, 0.3)) for c in closes],
        'low':    [c - abs(rng.normal(0.5, 0.3)) for c in closes],
        'close':  closes,
        'volume': [500000 + rng.normal(0, 50000) for _ in range(n)],
    })
    df['high'] = df[['open', 'close', 'high']].max(axis=1) + 0.01
    df['low'] = df[['open', 'close', 'low']].min(axis=1) - 0.01
    df['volume'] = df['volume'].clip(lower=1000)

    # Indicators
    df['EMA_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['SMA_50'] = df['close'].rolling(50).mean()
    df['SMA_200'] = df['close'].rolling(min(200, n - 1)).mean()
    df['ATRr_14'] = (df['high'] - df['low']).ewm(alpha=1 / 14, adjust=False).mean()
    df['vol_sma_9'] = df['volume'].rolling(9).mean()
    df['vol_sma_20'] = df['volume'].rolling(20).mean()
    df['ANCHOR'] = df['SMA_50']
    df['ADX_14'] = 25.0
    return df


def _make_cfg(p_code="B"):
    """Build a minimal ProfileConfig-like namespace."""
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


def _make_state(atr_raw=2.0, **overrides):
    """Build a minimal StateBundle-like namespace."""
    defaults = dict(
        atr_raw=atr_raw, is_resolving=False, is_trending=True,
        ema_stacked=True, is_floor_failure=False, is_violated=False,
        is_reclaim=False, consec_below=0, _reclaim_run=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ctx(p_code="B", df=None, **overrides):
    """Build a minimal RunContext-like namespace."""
    if df is None:
        df = _make_df()
    cfg = _make_cfg(p_code)
    last = df.iloc[cfg.iq]
    state = _make_state(atr_raw=float(last['ATRr_14']))
    defaults = dict(
        state=state, cfg=cfg, p_code=p_code, is_etf=False, _is_c3=False,
        df=df, last=last, metrics={},
        price_scaler=1.0, actual_price=float(last['close']),
        structural_floor_raw=float(last['ANCHOR']),
        hard_stop_raw=float(last['ANCHOR']) - 1.5 * state.atr_raw,
        resistance_raw=float(df['high'].iloc[-11:-1].max()),
        atr_dist=0.5, ext_limit=1.0,
        adx_col='ADX_14', prev_high=0.0,
        vol_confirm_ratio=0.0, vol_confirm_state="",
        window_count=0, window_limit=5,
        exit_signal=False, cons_high_raw=None,
        risk_a=None, reward_a=None,
        _df_ctx=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Helper: build a Profile A ctx positioned in a specific sentinel zone
# ---------------------------------------------------------------------------

def _make_profile_a_sentinel_ctx(risk_a_fraction, rr_target, atr_raw=2.0):
    """Build a Profile A ctx in the sentinel zone with controlled R:R.

    Args:
        risk_a_fraction: fraction of ATR for risk_a (0.0 = floor-exact,
                         0.0 < x < 0.20 = floor-proximity)
        rr_target: desired rr_hardstop = reward / (close - hard_stop)
        atr_raw: ATR value (default 2.0)
    """
    df = _make_df(n=60, base=100.0)
    cfg = _make_cfg("A")
    idx = cfg.iq  # -2

    # Set ATR to a stable known value
    df['ATRr_14'] = atr_raw

    # Set ANCHOR (VWAP floor) to a known value
    anchor = 100.0
    df['ANCHOR'] = anchor

    # Position price at anchor + risk_a_fraction * atr
    close_price = anchor + (risk_a_fraction * atr_raw)
    df.iloc[idx, df.columns.get_loc('close')] = close_price
    df.iloc[idx, df.columns.get_loc('open')] = close_price

    # Hard stop = anchor - 1.5 * ATR
    hard_stop = anchor - (1.5 * atr_raw)

    # risk_a_hardstop = close - hard_stop
    hs_risk = close_price - hard_stop

    # reward = rr_target * hs_risk  (so rr_hardstop = reward / hs_risk = rr_target)
    reward = rr_target * hs_risk
    cons_high = close_price + reward

    last = df.iloc[idx]
    state = _make_state(atr_raw=atr_raw)

    ctx = _make_ctx(
        p_code="A",
        df=df,
        state=state,
        last=last,
        hard_stop_raw=hard_stop,
        cons_high_raw=cons_high,
        price_scaler=1.0,
        exit_signal=False,
    )
    # Re-set last after _make_ctx (it re-reads from df)
    ctx.last = df.iloc[idx]
    return ctx


# ===========================================================================
# FLOOR_PROXIMITY zone tests (risk_a > 0 but < 0.20 * ATR)
# ===========================================================================

class TestPeCAL3FloorProximity:
    """Tests 1–4: FLOOR_PROXIMITY sentinel zone with PE-CAL-3 threshold."""

    def test_1_pass_rr_1_5_between_1_2_and_2_0(self):
        """Test 1: R:R 1.5 — previously REJECTED, now PASSES under PE-CAL-3."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.05,  # 5% ATR — well inside sentinel zone
            rr_target=1.5,
        )
        _result = _evaluate_precheck(ctx, _ff_threshold=8)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        assert status is None, f"Expected PASS (None), got {status}: {diag}"
        assert diag is None
        assert ctx.metrics["Expectancy_Threshold"] == 1.2
        assert "PE-CAL-3" in ctx.metrics["Expectancy_Threshold_Note"]

    def test_2_reject_rr_1_1_below_1_2(self):
        """Test 2: R:R 1.1 — below PE-CAL-3 threshold, REJECTED."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.05,
            rr_target=1.1,
        )
        _result = _evaluate_precheck(ctx, _ff_threshold=8)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        assert status == "INVALID"
        assert diag.startswith("REJECT (reason: EXPECTANCY FAILED)")
        assert "PE-CAL-3" in diag
        assert ctx.metrics["Expectancy_Threshold"] == 1.2

    def test_3_boundary_rr_exactly_1_2_passes(self):
        """Test 3: R:R exactly 1.2 — comparison is <, not <=, so PASSES."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.05,
            rr_target=1.2,
        )
        _result = _evaluate_precheck(ctx, _ff_threshold=8)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        assert status is None, f"Expected PASS (None) at boundary 1.2, got {status}: {diag}"
        assert diag is None

    def test_4_boundary_rr_1_199_rejects(self):
        """Test 4: R:R 1.199 — just below 1.2, REJECTED."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.05,
            rr_target=1.199,
        )
        _result = _evaluate_precheck(ctx, _ff_threshold=8)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        assert status == "INVALID"
        assert diag.startswith("REJECT (reason: EXPECTANCY FAILED)")


# ===========================================================================
# Profile isolation test
# ===========================================================================

class TestPeCAL3ProfileIsolation:
    """Test 5: Profile B is unaffected — no PE-CAL-3 contamination."""

    def test_5_profile_b_no_expectancy_threshold(self):
        """Profile B skips the entire Profile A expectancy block."""
        ctx = _make_ctx(p_code="B")
        _result = _evaluate_precheck(ctx, _ff_threshold=4)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        assert status is None
        assert diag is None
        assert "Expectancy_Threshold" not in ctx.metrics


# ===========================================================================
# FLOOR_EXACT zone tests (risk_a == 0 after grace clamping)
# ===========================================================================

class TestPeCAL3FloorExact:
    """Tests 6–7: FLOOR_EXACT sentinel zone with PE-CAL-3 threshold."""

    def test_6_pass_floor_exact_rr_1_5(self):
        """Test 6: Floor-exact entry with R:R 1.5 — PASSES."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.0,  # Exactly at ANCHOR
            rr_target=1.5,
        )
        _result = _evaluate_precheck(ctx, _ff_threshold=8)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        assert status is None, f"Expected PASS (None), got {status}: {diag}"
        assert diag is None
        assert ctx.metrics["Expectancy_Threshold"] == 1.2

    def test_7_reject_floor_exact_rr_1_1(self):
        """Test 7: Floor-exact entry with R:R 1.1 — REJECTED."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.0,
            rr_target=1.1,
        )
        _result = _evaluate_precheck(ctx, _ff_threshold=8)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        assert status == "INVALID"
        assert "FLOOR EXACT" in diag
        assert "PE-CAL-3" in diag


# ===========================================================================
# Standard path isolation test
# ===========================================================================

class TestPeCAL3StandardPath:
    """Test 8: Standard path (risk_a >= 0.20 * ATR) is unchanged."""

    def test_8_standard_path_passes_precheck_threshold_2_0(self):
        """Standard path: precheck passes, Expectancy_Threshold = 2.0."""
        # Set risk_a well above 0.20 * ATR — standard path
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.50,  # 50% ATR — well above 0.20 threshold
            rr_target=1.5,  # Would fail 2.0 standard gate, but precheck passes
        )
        _result = _evaluate_precheck(ctx, _ff_threshold=8)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        # Precheck passes — the 2.0 rejection happens later in _gate_expectancy()
        assert status is None
        assert diag is None
        assert ctx.metrics["Expectancy_Threshold"] == 2.0
        assert ctx.metrics["Expectancy_Threshold_Note"] is None


# ===========================================================================
# Metric field tests
# ===========================================================================

class TestPeCAL3MetricFields:
    """Tests 9–11: Metric field values and string content."""

    def test_9_expectancy_threshold_1_2_on_sentinel_pass(self):
        """Test 9: Expectancy_Threshold == 1.2 when PE-CAL-3 fires (PASS)."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.05,
            rr_target=1.5,
        )
        _evaluate_precheck(ctx, _ff_threshold=8)
        assert ctx.metrics["Expectancy_Threshold"] == 1.2
        assert isinstance(ctx.metrics["Expectancy_Threshold"], float)

    def test_10_expectancy_threshold_2_0_on_standard_path(self):
        """Test 10: Expectancy_Threshold == 2.0 on standard path."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.50,
            rr_target=3.0,
        )
        _evaluate_precheck(ctx, _ff_threshold=8)
        assert ctx.metrics["Expectancy_Threshold"] == 2.0
        assert isinstance(ctx.metrics["Expectancy_Threshold"], float)

    def test_11_expectancy_threshold_note_content(self):
        """Test 11: Note string content when PE-CAL-3 active vs inactive."""
        # PE-CAL-3 active (sentinel zone)
        ctx_sentinel = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.05,
            rr_target=1.5,
        )
        _evaluate_precheck(ctx_sentinel, _ff_threshold=8)
        assert ctx_sentinel.metrics["Expectancy_Threshold_Note"] == (
            "PE-CAL-3: Floor Proximity threshold 1.2 (Profile A C-1 reliability adjustment)"
        )

        # PE-CAL-3 not active (standard path)
        ctx_standard = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.50,
            rr_target=3.0,
        )
        _evaluate_precheck(ctx_standard, _ff_threshold=8)
        assert ctx_standard.metrics["Expectancy_Threshold_Note"] is None


# ===========================================================================
# Diagnostic string test
# ===========================================================================

class TestPeCAL3DiagnosticString:
    """Test 12: REJECT diagnostic references PE-CAL-3, not old wording."""

    def test_12_reject_diagnostic_references_pe_cal_3(self):
        """REJECT diagnostic contains PE-CAL-3 and 1.2, not old '1:2 minimum'."""
        ctx = _make_profile_a_sentinel_ctx(
            risk_a_fraction=0.05,
            rr_target=1.1,
        )
        _result = _evaluate_precheck(ctx, _ff_threshold=8)
        status = _result.verdict if _result else None
        diag = _result.legacy_diagnostic if _result else None
        assert status == "INVALID"
        assert "PE-CAL-3" in diag
        assert "1.2" in diag
        assert "fails 1:2 minimum" not in diag
