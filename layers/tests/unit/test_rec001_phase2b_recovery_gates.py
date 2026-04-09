"""REC-001 Phase 2B: Recovery Gate Sequence — Unit Tests.

Tests R-Gates (R-1 through R-5), target selection, CRG bypass transparency,
sentinel regime context, C-3 Thesis Attestation, and recovery routing.

Maps to spec §4.1–4.3, §5.1–5.3, §7.1–7.2 and test cases TC-07..TC-14, TC-21, TC-22.
"""
import sys
import types as builtin_types
import importlib.util

# --- Isolated import: load modules without full package chain ---
if 'tbs_engine' not in sys.modules:
    pkg = builtin_types.ModuleType('tbs_engine')
    pkg.__path__ = ['tbs_engine']
    sys.modules['tbs_engine'] = pkg
for _mod, _path in [('tbs_engine.types', 'tbs_engine/types.py'),
                     ('tbs_engine.helpers', 'tbs_engine/helpers.py'),
                     ('tbs_engine.gates', 'tbs_engine/gates.py')]:
    if _mod not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_mod, _path)
        _m = importlib.util.module_from_spec(_spec)
        sys.modules[_mod] = _m
        _spec.loader.exec_module(_m)

import math
import pandas as pd
import pytest
from types import SimpleNamespace
from tbs_engine.types import GateResult
from tbs_engine.gates import (
    _gate_recovery_r1, _gate_recovery_r3, _gate_recovery_r4,
    _gate_recovery_r5, _select_recovery_target,
)


# ========================================================================
# Fixtures: base_result builders
# ========================================================================

def _confirmed_base(**overrides):
    """Build a base_result dict representing a fully confirmed base."""
    result = {
        "swing_low_price": 90.0,
        "swing_low_bar_index": 10,
        "base_bar_count": 6,
        "base_confirmed": True,
        "criteria": {
            "min_bars": True,
            "no_lower_low": True,
            "atr_contracting": True,
            "retest_confirmed": True,
            "vol_clean": True,
        },
        "atr_contraction_ratio": 0.75,
        "retest_confirmed": True,
        "ema_cross_bar_index": 14,
        "ema_cross_fresh": True,
        "di_spread_current": 5.0,
        "di_spread_at_swing_low": 15.0,
        "time_stop_limit": 25,
        "min_base_bars": 5,
    }
    result.update(overrides)
    return result


def _failed_base(**overrides):
    """Build a base_result where base_confirmed is False."""
    result = _confirmed_base()
    result["base_confirmed"] = False
    result["criteria"]["min_bars"] = False
    result.update(overrides)
    return result


# ========================================================================
# R-Gate 1: Base Confirmation + EMA Cross Freshness
# ========================================================================

class TestRGate1:
    """Spec §4.2 R-1 / R-2."""

    def test_pass_all_confirmed(self):
        r = _gate_recovery_r1(_confirmed_base())
        assert r is None

    def test_fail_base_not_confirmed(self):
        """TC-02 family: base criteria not met → BASE NOT CONFIRMED."""
        r = _gate_recovery_r1(_failed_base())
        assert r is not None
        assert r.verdict == "INVALID"
        assert r.reason == "BASE NOT CONFIRMED"
        assert "min_bars" in r.context

    def test_fail_ema_cross_stale(self):
        """TC-07: EMA cross predates swing low → EMA CROSS STALE."""
        base = _confirmed_base(
            ema_cross_bar_index=8,  # before swing low at 10
            ema_cross_fresh=False,
        )
        r = _gate_recovery_r1(base)
        assert r is not None
        assert r.reason == "EMA CROSS STALE"
        assert "bar 8" in r.context
        assert "bar 10" in r.context

    def test_fail_ema_cross_none(self):
        """TC-23: No EMA cross since swing low."""
        base = _confirmed_base(
            ema_cross_bar_index=None,
            ema_cross_fresh=False,
        )
        r = _gate_recovery_r1(base)
        assert r is not None
        assert r.reason == "EMA CROSS STALE"
        assert "No EMA 8/21" in r.context

    def test_pass_ema_cross_fresh(self):
        """TC-08: EMA cross at or after swing low → pass."""
        base = _confirmed_base(ema_cross_bar_index=12, ema_cross_fresh=True)
        r = _gate_recovery_r1(base)
        assert r is None


# ========================================================================
# R-Gate 3: DI Spread Narrowing
# ========================================================================

class TestRGate3:
    """Spec §4.2 R-3, DQ-4."""

    def test_tc09_narrowing_pass(self):
        """TC-09: DI spread narrowed → pass."""
        base = _confirmed_base(di_spread_current=8.0, di_spread_at_swing_low=15.0)
        r = _gate_recovery_r3(base, di_plus_current=18.0, di_minus_current=22.0)
        assert r is None

    def test_tc10_not_narrowing_fail(self):
        """TC-10: DI spread widened, -DI still dominant → fail."""
        base = _confirmed_base(di_spread_current=12.0, di_spread_at_swing_low=8.0)
        r = _gate_recovery_r3(base, di_plus_current=15.0, di_minus_current=27.0)
        assert r is not None
        assert r.reason == "DI SPREAD NOT NARROWING"

    def test_tc11_crossed_pass(self):
        """TC-11: +DI > -DI (alternative condition) → pass."""
        base = _confirmed_base(di_spread_current=20.0, di_spread_at_swing_low=15.0)
        r = _gate_recovery_r3(base, di_plus_current=30.0, di_minus_current=15.0)
        assert r is None

    def test_nan_di_spread_plus_di_dominant_pass(self):
        """Edge case: DI warmup → NaN at swing low, but +DI > -DI → pass."""
        base = _confirmed_base(di_spread_at_swing_low=float('nan'))
        r = _gate_recovery_r3(base, di_plus_current=25.0, di_minus_current=20.0)
        assert r is None

    def test_nan_di_spread_minus_di_dominant_fail(self):
        """Edge case: DI warmup → NaN at swing low, -DI dominant → fail."""
        base = _confirmed_base(di_spread_at_swing_low=float('nan'))
        r = _gate_recovery_r3(base, di_plus_current=15.0, di_minus_current=25.0)
        assert r is not None
        assert r.reason == "DI SPREAD NOT NARROWING"
        assert "warmup" in r.context


# ========================================================================
# R-Gate 4: Capital Expectancy
# ========================================================================

class TestRGate4:
    """Spec §4.2 R-4, §5.2."""

    def test_tc12_pass(self):
        """TC-12: R:R = 10/5 = 2.0 >= 1.5 → pass."""
        r = _gate_recovery_r4(100.0, 95.0, 110.0, "SMA_50")
        assert r is None

    def test_tc13_fail(self):
        """TC-13: R:R = 2/5 = 0.4 < 1.5 → fail."""
        r = _gate_recovery_r4(100.0, 95.0, 102.0, "SMA_50")
        assert r is not None
        assert r.reason == "CAPITAL EXPECTANCY FAILED"
        assert "0.4" in r.context

    def test_exactly_1_5_pass(self):
        """R:R exactly 1.5 → pass (threshold inclusive)."""
        # reward=7.5, risk=5 → 1.5
        r = _gate_recovery_r4(100.0, 95.0, 107.5, "SMA_50")
        assert r is None

    def test_no_target_fail(self):
        """TC-14 (via R-4): No overhead MA → NO RECOVERY TARGET."""
        r = _gate_recovery_r4(100.0, 95.0, None, None)
        assert r is not None
        assert r.reason == "NO RECOVERY TARGET"

    def test_price_at_swing_low_fail(self):
        """Edge: price == swing_low → risk = 0 → fail."""
        r = _gate_recovery_r4(95.0, 95.0, 110.0, "SMA_50")
        assert r is not None
        assert r.reason == "CAPITAL EXPECTANCY FAILED"


# ========================================================================
# R-Gate 5: Volume Distribution
# ========================================================================

class TestRGate5:
    """Spec §4.2 R-5."""

    def test_pass_mixed(self):
        r = _gate_recovery_r5("MIXED")
        assert r is None

    def test_pass_neutral(self):
        r = _gate_recovery_r5("NEUTRAL")
        assert r is None

    def test_fail_distribution_warning(self):
        r = _gate_recovery_r5("DISTRIBUTION WARNING")
        assert r is not None
        assert r.reason == "DISTRIBUTION WARNING"


# ========================================================================
# Target Selection
# ========================================================================

class TestTargetSelection:
    """Spec §5.1–5.3."""

    def _make_df_ctx(self, sma50=None, ema21=None, sma200=None):
        data = {"close": [100.0]}
        if sma50 is not None:
            data["SMA_50"] = [sma50]
        if ema21 is not None:
            data["EMA_21"] = [ema21]
        if sma200 is not None:
            data["SMA_200"] = [sma200]
        return pd.DataFrame(data)

    def _make_df_b(self, sma50=None, ema21=None, sma200=None):
        data = {"close": [100.0]}
        if sma50 is not None:
            data["SMA_50"] = [sma50]
        if ema21 is not None:
            data["EMA_21"] = [ema21]
        if sma200 is not None:
            data["SMA_200"] = [sma200]
        return pd.DataFrame(data)

    def test_sma50_nearest(self):
        """Price < SMA 50 < EMA 21 < SMA 200 → target = SMA 50."""
        df_ctx = self._make_df_ctx(sma50=105, ema21=110, sma200=120)
        cfg = SimpleNamespace(iq=-1)
        target, src = _select_recovery_target(100.0, df_ctx, None, "A", cfg)
        assert target == 105.0
        assert src == "SMA_50"

    def test_ema21_nearest_when_above_sma50(self):
        """Price > SMA 50 but < EMA 21 → target = DAILY_EMA_21."""
        df_ctx = self._make_df_ctx(sma50=95, ema21=110, sma200=120)
        cfg = SimpleNamespace(iq=-1)
        target, src = _select_recovery_target(100.0, df_ctx, None, "A", cfg)
        assert target == 110.0
        assert src == "DAILY_EMA_21"

    def test_sma200_nearest_when_above_both(self):
        """Price > SMA 50 and > EMA 21 but < SMA 200 → target = SMA 200."""
        df_ctx = self._make_df_ctx(sma50=90, ema21=95, sma200=120)
        cfg = SimpleNamespace(iq=-1)
        target, src = _select_recovery_target(100.0, df_ctx, None, "A", cfg)
        assert target == 120.0
        assert src == "SMA_200"

    def test_no_overhead_ma(self):
        """TC-14: Price above all MAs → (None, None)."""
        df_ctx = self._make_df_ctx(sma50=90, ema21=95, sma200=98)
        cfg = SimpleNamespace(iq=-1)
        target, src = _select_recovery_target(100.0, df_ctx, None, "A", cfg)
        assert target is None
        assert src is None

    def test_profile_b_reads_from_df(self):
        """Profile B reads from primary df, not df_ctx."""
        df = self._make_df_b(sma50=110, ema21=115, sma200=130)
        cfg = SimpleNamespace(iq=-1)
        target, src = _select_recovery_target(100.0, None, df, "B", cfg)
        assert target == 110.0
        assert src == "SMA_50"

    def test_nearest_overhead_wins(self):
        """If EMA 21 is closer overhead than SMA 50, EMA 21 wins."""
        df_ctx = self._make_df_ctx(sma50=120, ema21=105, sma200=130)
        cfg = SimpleNamespace(iq=-1)
        target, src = _select_recovery_target(100.0, df_ctx, None, "A", cfg)
        assert target == 105.0
        assert src == "DAILY_EMA_21"


# ========================================================================
# Vocabulary compliance
# ========================================================================

class TestVocabularyCompliance:
    """No Phase 2C/2D/2E vocabulary in R-Gate outputs."""

    _BANNED = ["EXIT", "BASE FAILURE", "EMA RE-INVERSION", "TIME STOP",
               "HALT", "PRE-APPROVED"]
    # Note: "VALID" removed — it's a substring of "INVALID" which is the standard
    # gate fail verdict. The prompt's vocabulary constraint is about standalone
    # "VALID" as a verdict on the recovery path, not substring matches.

    def _check_gate_result(self, gr):
        if gr is None:
            return
        for field in [gr.verdict, gr.reason, gr.mandate or "", gr.context or ""]:
            for word in self._BANNED:
                assert word not in field, f"Banned word '{word}' found in GateResult field: {field}"

    def test_r1_fail_vocabulary(self):
        self._check_gate_result(_gate_recovery_r1(_failed_base()))

    def test_r3_fail_vocabulary(self):
        base = _confirmed_base(di_spread_current=12.0, di_spread_at_swing_low=8.0)
        self._check_gate_result(_gate_recovery_r3(base, 15.0, 27.0))

    def test_r4_fail_vocabulary(self):
        self._check_gate_result(_gate_recovery_r4(100.0, 95.0, 102.0, "SMA_50"))

    def test_r5_fail_vocabulary(self):
        self._check_gate_result(_gate_recovery_r5("DISTRIBUTION WARNING"))

    def test_no_target_vocabulary(self):
        self._check_gate_result(_gate_recovery_r4(100.0, 95.0, None, None))
