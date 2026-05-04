"""BUGR-006 Label Fidelity Bundle — Unit Tests.

Spec: BUGR006_Label_Fidelity_Bundle_Spec_v1_0.md (S140)
Bundle IDs: BUGR-006-LABEL-1 + BUGR-006-LABEL-2 + OUT-002

Implements the nine test classes enumerated in spec §5.2:

    1. T-LABEL1-FRR                  — TestLabel1FrrCoexistence
    2. T-LABEL1-CEG                  — TestLabel1CegBlueSkyTxnB
    3. T-LABEL2-PB                   — TestLabel2OutputDeferProfileB
    4. T-LABEL2-PA                   — TestLabel2ProfileAStandardization
    5. T-LABEL2-NONBRK               — TestLabel2NonBrkRegression  (class 3 structurally empty)
    6. T-OUT002-BRK                  — TestOut002DescBrkActive
    7. T-OUT002-NONBRK               — TestOut002DescNonBrkRegression
    8. T-COEXIST-FULL                — TestBundleCoexistenceFull
    9. T-PROFILE-A-NONBRK-REGRESSION — TestProfileANonBrkRegression

Differential-verification contract (spec §5.4 / SIR §9):
    - T-LABEL1-FRR / T-LABEL1-CEG / T-LABEL2-PB / T-LABEL2-PA / T-COEXIST-FULL
      MUST FAIL on pre-fix code, PASS on post-fix code.
    - T-OUT002-BRK MUST FAIL on pre-fix transform.py, PASS on post-fix.
    - T-OUT002-NONBRK / T-PROFILE-A-NONBRK-REGRESSION MUST PASS both pre-fix
      and post-fix (regression assurance).
    - T-LABEL2-NONBRK is a documented structural-empty test (class 3 unreachable)
      per Phase 1 Step 1.4 verification — _mm_raw is null on non-BRK paths.

Site mapping (spec §4):
    Site 1   compute.py:902-903   FRR-001 ANALYST_CONSENSUS guard
    Site 2   compute.py:968-969   CEG-002 blue-sky ATR_PROJECTION guard
    Site 3   output.py:1166-1171  _assemble_output _mm_raw branch defer
    Site 4   transform.py:1077-84 price_reward_risk.desc conditional
    Edit 1   compute.py:736       Profile A BRK MM target label standardization (§4.3.1)

Import strategy & TEST-HRN-001 hygiene
======================================
Spec §5.1 prescribes the `spec_from_file_location` pattern with no
`sys.modules` registration, citing three reference files:
    test_bugr002_hierarchy_partition.py
    test_eng004_measured_move.py
    test_pa001_phase3_hierarchies.py
All three test transform.py-only or self-contained logic. None tests
compute.py functions, which carry top-level `from tbs_engine.{types, helpers}
import` cross-imports — these dependencies CANNOT be resolved by
`spec_from_file_location` alone (Python's import machinery requires the
parent package + dependency modules to be in `sys.modules` for the
top-level imports inside compute.py to succeed at exec_module time).

This file uses a HYBRID, scope-limited approach:

  * Site 4 tests (T-OUT002-*): pure safe-pattern — load transform.py
    via spec_from_file_location with module name "tbs_engine_transform"
    (NOT "tbs_engine.transform") — no sys.modules entry. transform.py
    has zero internal cross-imports, so this is fully clean.

  * Sites 1 / 2 / 4.3.1 / coexistence / regression tests:
    idempotent sys.modules pattern (matching the closest functional
    precedents test_frr001_fundamental_rr.py and
    test_bugr006_profile_b_brk_rr.py — both exercise compute.py
    functions). The TEST-HRN-001 anti-pattern is the
    OVERWRITE-then-class-identity-replacement pattern; the idempotent
    "if not in sys.modules" guard explicitly avoids it. NO module is
    overwritten if already present.

  * Site 3 test (T-LABEL2-PB): output.py transitively requires
    tbs_engine.charts which imports plotly. Loading output.py in this
    environment would fail. T-LABEL2-PB is implemented as a
    SOURCE-INSPECTION test that asserts the post-fix guard structure
    is present in output.py source — sufficient to detect any
    regression of the Edit 4 change pattern, complementary to the
    live-IBKR validation (spec §5.3) which directly exercises the
    output assembly pipeline end-to-end.

Deviation status: Documented per SIR §1.2 and SIR §7. Flagged in
hand-back. Strictly equivalent to the hygiene of the closest
functional precedents already in the test tree.
"""

import os
import re
import sys
import importlib.util as _ilu
from types import SimpleNamespace

import pytest
import pandas as pd


# ===========================================================================
# Repo paths
# ===========================================================================

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_ENGINE_DIR = os.path.join(_REPO_ROOT, "tbs_engine")
_COMPUTE_PATH = os.path.join(_ENGINE_DIR, "compute.py")
_OUTPUT_PATH = os.path.join(_ENGINE_DIR, "output.py")
_TRANSFORM_PATH = os.path.join(_ENGINE_DIR, "transform.py")


# ===========================================================================
# Pure safe-pattern transform.py loader (Site 4 tests)
# ===========================================================================
# transform.py has zero internal `from tbs_engine.X` imports (verified
# S140); pure spec_from_file_location with a non-package module name and
# no sys.modules write is fully safe. No class identity issues.

_t_spec = _ilu.spec_from_file_location(
    "tbs_engine_transform_bugr006_label_bundle",
    _TRANSFORM_PATH,
)
_transform_mod = _ilu.module_from_spec(_t_spec)
_t_spec.loader.exec_module(_transform_mod)
_transform_output = _transform_mod._transform_output


# ===========================================================================
# Idempotent compute.py loader (Sites 1, 2, 4.3.1, coexistence, regression)
# ===========================================================================
# IDEMPOTENT pattern: only register modules in sys.modules if absent.
# This avoids the TEST-HRN-001 overwrite anti-pattern (replacement of
# tbs_engine.types.GateResult and friends mid-run, which causes
# isinstance() failures in unrelated downstream tests).

def _load_compute_module(name, path):
    """Load engine module by file path; reuse sys.modules entry if present."""
    if name in sys.modules:
        return sys.modules[name]
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub the parent package so compute.py's `from tbs_engine.types import ...`
# resolves without triggering tbs_engine/__init__.py (which transitively
# imports plotly via charts.py).
if "tbs_engine" not in sys.modules:
    import types as _stdlib_types
    sys.modules["tbs_engine"] = _stdlib_types.ModuleType("tbs_engine")

_types_mod = _load_compute_module(
    "tbs_engine.types",
    os.path.join(_ENGINE_DIR, "types.py"),
)
_helpers_mod = _load_compute_module(
    "tbs_engine.helpers",
    os.path.join(_ENGINE_DIR, "helpers.py"),
)
_compute_mod = _load_compute_module(
    "tbs_engine.compute",
    _COMPUTE_PATH,
)

_compute_early_capital_rr = _compute_mod._compute_early_capital_rr


# ===========================================================================
# Verbatim label strings (spec §3.1) — character-for-character per SIR §3
# ===========================================================================

LABEL_BRK_PRIMARY = "MEASURED_MOVE (BRK-001 post-breakout target)"
LABEL_BRK_WEEKLY_FALLBACK = "WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)"
LABEL_BRK_ATR_FALLBACK = "ATR_PROJECTION (BRK-001 §8.1 MM-null fallback)"
LABEL_BRK_EXHAUSTED = "BRK-001 post-breakout (fallbacks exhausted)"

BRK_LABELS_4 = frozenset({
    LABEL_BRK_PRIMARY,
    LABEL_BRK_WEEKLY_FALLBACK,
    LABEL_BRK_ATR_FALLBACK,
    LABEL_BRK_EXHAUSTED,
})

LABEL_ANALYST_CONSENSUS = "ANALYST_CONSENSUS"
LABEL_BLUE_SKY_ATR = "ATR_PROJECTION (blue sky)"

DESC_BRK = (
    "Price R:R -- reward (profit target - price) / risk (price - tight stop). "
    "See trade_setup.target.source for target origin."
)
DESC_NONBRK = (
    "Price R:R -- reward (profit target - price) / risk (price - structural floor). "
    "See trade_setup.target.source for target origin."
)


# ===========================================================================
# Fixtures (mirror test_bugr006_profile_b_brk_rr.py for consistency)
# ===========================================================================

def _make_state(atr_raw=1.0):
    return SimpleNamespace(
        atr_raw=atr_raw,
        di_plus=30.0,
        di_minus=15.0,
        _entry_trending=True,
        floor_raw=0.0,
        is_trending=True,
        is_resolving=False,
        is_reclaim=False,
        is_violated=False,
        is_floor_failure=False,
        adx_t=25.0,
        adx_t1=24.0,
    )


def _make_cfg():
    return SimpleNamespace(
        resistance_slice_start=-11,
        resistance_slice_end=-1,
    )


def _make_df_context(n=15, high_value=105.0, low_value=95.0):
    return pd.DataFrame({
        "high":  [high_value] * n,
        "low":   [low_value]  * n,
        "close": [(high_value + low_value) / 2] * n,
    })


def _make_primary_df(n=30, high_value=105.0, low_value=95.0,
                     close_value=100.0, volume=1_000_000):
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
    breakout_model_active=False,
    brk_tight_stop_raw=None,
    brk_mm_target_raw=None,
    brk_new_support_raw=None,
    daily_atr=0.0,
    daily_hard_stop=None,
    analyst_target_median=None,
    analyst_target_low=None,
    analyst_target_high=None,
    analyst_count=None,
):
    """Minimal ctx for _compute_early_capital_rr.

    BRK flag fields simulate the post-_detect_breakout_model state so
    these direct unit tests do not need to call the BRK detector.
    """
    if primary_df is None:
        primary_df = _make_primary_df(
            close_value=close,
            high_value=max(close + 0.5, resistance_raw + 0.5),
        )

    last = primary_df.iloc[-1].copy()
    last["close"] = close
    last["ANCHOR"] = anchor
    last["volume"] = primary_df.iloc[-1]["volume"]

    ctx = SimpleNamespace(
        p_code=p_code,
        is_etf=is_etf,
        _is_c3=is_c3,
        state=_make_state(atr_raw=atr_raw),
        cfg=_make_cfg(),
        price_scaler=price_scaler,
        actual_price=close / price_scaler,
        structural_floor_raw=anchor,
        hard_stop_raw=hard_stop_raw,
        resistance_raw=resistance_raw,
        df=primary_df,
        last=last,
        metrics={},
        _df_ctx=df_ctx,
        bars_per_day=1.0,
        window_count=0,
        window_limit=10,
        _breakout_model_active=breakout_model_active,
        _brk_tight_stop_raw=brk_tight_stop_raw,
        _brk_mm_target_raw=brk_mm_target_raw,
        _brk_new_support_raw=brk_new_support_raw,
        _brk_catastrophic_stop_raw=None,
        _breakout_thesis_failed=False,
        _brk_failed_new_support=None,
        _analyst_target_median=analyst_target_median,
        _analyst_target_low=analyst_target_low,
        _analyst_target_high=analyst_target_high,
        _analyst_count=analyst_count,
        cons_high_raw=None,
        mm_target_raw=None,
        daily_atr=daily_atr,
    )
    if daily_hard_stop is not None:
        ctx.daily_hard_stop = daily_hard_stop
    return ctx


def _base_action_summary():
    return {
        "verdict": "VALID",
        "reason": {"label": "VALID PULLBACK", "detail": ""},
        "mandate": "ENTER",
        "context": "",
    }


def _base_flat_metrics(brk_model_active=False, **overrides):
    """Minimal flat_metrics for _transform_output to assemble price_reward_risk."""
    m = {
        "Price": 100.0,
        "Structural_Floor": 95.0,
        "Floor_Anchor_Type": "EMA_21",
        "Floor_Anchor_Label": "Intraday institutional value level",
        "Anchor_Label": "VWAP (Baseline Floor)",
        "Anchor_Type": "Standard",
        "Extension_Anchor_Type": "VWAP",
        "Extension_Anchor_Label": "Intraday institutional value level",
        "Hard_Stop": 92.0,
        "Resistance": 110.0,
        "EMA_8": 99.5,
        "EMA_21": 98.0,
        "SMA_50": 95.0,
        "SMA_200": 88.0,
        "VWAP": 97.0,
        "ATR": 1.5,
        "ADV_20": 5_000_000.0,
        "ADV_20_Dollar": 500_000_000.0,
        "Is_ETF": False,
        "Profit_Target": 110.0,
        "Profit_Target_Source": LABEL_BRK_PRIMARY if brk_model_active else "RESISTANCE",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "Reward_Risk": 1.5,
        "Reward_Risk_Note": None,
        "BRK_Model_Active": brk_model_active,
        "Profile_Code": "B",
    }
    m.update(overrides)
    return m


def _extract_price_rr_desc(action_summary, flat_metrics):
    """Run _transform_output and return the trade_risk.price_reward_risk.desc string."""
    grouped = _transform_output(action_summary, flat_metrics)
    return grouped["trade_risk"]["price_reward_risk"]["desc"]


# ===========================================================================
# T-LABEL1-FRR — TestLabel1FrrCoexistence
# ===========================================================================
# BRK-active Profile B + analyst data populated. Pre-fix: FRR-001 site
# (compute.py:901) overwrites BRK label with "ANALYST_CONSENSUS".
# Post-fix (Edit 2): guard skips the overwrite when _breakout_model_active.
# Fundamental_* keys must remain populated; Reward_Risk must remain BRK value.

class TestLabel1FrrCoexistence:
    """[BUGR-006-LABEL-1] FRR-001 + BRK coexistence at compute.py site 1."""

    def _make_brk_plus_fundamental_ctx(self):
        # Profile B, BRK-active, MM target available, plus analyst consensus.
        # _fund_risk = 100 - 95 = 5 > 0; _atm > _atl AND _atl < close required.
        return _make_ctx(
            p_code="B",
            close=100.0,
            anchor=95.0,
            atr_raw=1.0,
            breakout_model_active=True,
            brk_tight_stop_raw=94.0,         # new_support 95 - 1.0 ATR
            brk_mm_target_raw=115.0,          # MM target available → primary BRK label
            analyst_target_median=120.0,      # > _atl, > close
            analyst_target_low=95.0,          # < close=100
            analyst_target_high=130.0,
            analyst_count=10,
        )

    def test_brk_label_survives_frr_overwrite(self):
        """Post-fix: BRK label survives despite FRR-001 fundamental data eligibility."""
        ctx = self._make_brk_plus_fundamental_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics

        # Spec §3.1: must be one of the four BRK labels (MM available → primary)
        assert m["Profit_Target_Source"] == LABEL_BRK_PRIMARY, (
            f"Expected BRK label to survive FRR-001; got {m['Profit_Target_Source']!r}"
        )

    def test_fundamental_keys_populated_unchanged(self):
        """Post-fix: Fundamental_* keys remain populated (only the LABEL write is gated)."""
        ctx = self._make_brk_plus_fundamental_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics

        assert m.get("Fundamental_RR") is not None, "Fundamental_RR must remain populated"
        assert m.get("Fundamental_Target") == 120.0
        assert m.get("Fundamental_Floor") == 95.0
        assert m.get("Fundamental_Target_High") == 130.0
        assert m.get("Fundamental_Analyst_Count") == 10
        assert m.get("Fundamental_RR_Label") in {"STRONG", "MODERATE", "INSUFFICIENT"}

    def test_reward_risk_remains_brk_value(self):
        """Post-fix: Reward_Risk numeric is BRK value (15/6 = 2.5), not fundamental."""
        ctx = self._make_brk_plus_fundamental_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics

        # BRK: reward = 115 - 100 = 15; risk = 100 - 94 = 6; R:R = 2.5
        assert m["Reward_Risk"] == 2.5

    def test_profit_target_role_demoted(self):
        """Post-fix: Profit_Target_Role still demoted to INFORMATIONAL by FRR-001
        (only the SOURCE write is gated; ROLE write is unchanged per spec §4.1)."""
        ctx = self._make_brk_plus_fundamental_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics

        assert m.get("Profit_Target_Role") == "INFORMATIONAL"


# ===========================================================================
# T-LABEL1-CEG — TestLabel1CegBlueSkyTxnB
# ===========================================================================
# TXN-B reproduction: BRK-active + resistance_suppressed + compressed
# headroom + no fundamental data. Pre-fix (compute.py:966) overwrites BRK
# label with "ATR_PROJECTION (blue sky)". Post-fix (Edit 3) guard inert
# on BRK-active path.

class TestLabel1CegBlueSkyTxnB:
    """[BUGR-006-LABEL-1] CEG-002 Profile B blue-sky Tier 3 at compute.py site 2."""

    def _make_txn_b_shaped_ctx(self):
        # Profile B, BRK-active, MM target available.
        # CEG-002 entry conditions:
        #   - p_code == "B"; not _is_c3
        #   - resistance_raw <= last['close']  → resistance suppressed
        #   - df_ctx not None, len >= 11, weekly_ceiling > close
        #   - not _has_fundamental_data       → no analyst data (defaults None)
        #   - _is_blue_sky_b: weekly_ceiling - close < 1.5 * atr_daily
        # close=100, resistance=99 (suppressed), df_ctx high=101 (compressed
        # headroom = 1 < 1.5*ATR=1.5).
        df_ctx = _make_df_context(n=15, high_value=101.0, low_value=98.0)
        return _make_ctx(
            p_code="B",
            close=100.0,
            anchor=95.0,
            resistance_raw=99.0,        # suppressed (<= close)
            atr_raw=1.0,
            df_ctx=df_ctx,
            breakout_model_active=True,
            brk_tight_stop_raw=94.0,
            brk_mm_target_raw=115.0,    # MM available → primary BRK label
        )

    def test_brk_label_survives_ceg_overwrite(self):
        """Post-fix: BRK label survives despite CEG-002 blue-sky eligibility."""
        ctx = self._make_txn_b_shaped_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics

        assert m["Profit_Target_Source"] == LABEL_BRK_PRIMARY, (
            f"Expected BRK label to survive CEG-002; got {m['Profit_Target_Source']!r}"
        )

    def test_blue_sky_intermediate_state_preserved(self):
        """Post-fix: CEG-002's other writes (_rwd001_blue_sky, _rwd001_atr_target_raw,
        _rwd001_headroom_ratio) still happen — only the LABEL write is gated."""
        ctx = self._make_txn_b_shaped_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics

        # Confirm CEG-002 Tier 3 path executed end-to-end (only label write skipped)
        assert m.get("_rwd001_blue_sky") is True, (
            "CEG-002 Tier 3 path must still execute; only the label-write is guarded"
        )
        assert m.get("_rwd001_atr_target_raw") is not None
        assert m.get("_rwd001_headroom_ratio") is not None

    def test_brk_reward_risk_value_unchanged(self):
        """Post-fix: Reward_Risk = 2.5 (BRK formula) preserved per spec §7.1."""
        ctx = self._make_txn_b_shaped_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics
        # Reward = 115 - 100 = 15; Risk = 100 - 94 = 6 → 2.5
        assert m["Reward_Risk"] == 2.5


# ===========================================================================
# T-LABEL2-PB — TestLabel2OutputDeferProfileB  (SOURCE INSPECTION)
# ===========================================================================
# Implemented as source-inspection test because output.py transitively
# requires plotly via tbs_engine.charts and cannot be loaded in this
# environment. Validates the post-fix guard structure exists at
# output.py:1166-1171 per spec §4.3 / ODQ-1 (3a) + ODQ-2 (a).
# End-to-end exercise of the output-layer behaviour is covered by
# live IBKR validation (spec §5.3, Operator-led).

class TestLabel2OutputDeferProfileB:
    """[BUGR-006-LABEL-2] output.py _assemble_output guard structure check."""

    @pytest.fixture(scope="class")
    def output_src(self):
        with open(_OUTPUT_PATH) as f:
            return f.read()

    def test_legacy_unconditional_label_write_removed(self, output_src):
        """Post-fix: the legacy unconditional MEASURED_MOVE (post-breakout
        projection) write at the _mm_raw branch must be GONE."""
        # The pre-fix line was:
        #   metrics["Profit_Target_Source"] = "MEASURED_MOVE (post-breakout projection)"
        # Post-fix: the legacy string survives only as the label written by the
        # Profile A pre-existing path BEFORE this site (now updated by Edit 1)
        # -- so it must NOT be present anywhere in output.py post-fix.
        assert 'metrics["Profit_Target_Source"] = "MEASURED_MOVE (post-breakout projection)"' not in output_src, (
            "Legacy unconditional MEASURED_MOVE (post-breakout projection) write "
            "must be removed from output.py per spec §4.3 / ODQ-2(a)."
        )

    def test_defer_pass_branch_present(self, output_src):
        """Post-fix: the (3a) defer-when-compute-wrote 'pass' branch is present."""
        # Match the post-fix structure: inside `if _mm_raw is not None:`,
        # an inner conditional gating on _brk_active and metrics.get("Profit_Target_Source").
        pat = re.compile(
            r'if\s+_mm_raw\s+is\s+not\s+None:.*?'
            r'if\s+_brk_active\s+and\s+metrics\.get\(\s*"Profit_Target_Source"\s*\)\s*:\s*\n\s*pass',
            re.DOTALL,
        )
        assert pat.search(output_src) is not None, (
            "Defer-pass branch (LABEL-2 (3a)) not found in expected location."
        )

    def test_standardized_label_in_else_branch(self, output_src):
        """Post-fix: the (a) standardized BRK label is written in the else branch."""
        pat = re.compile(
            r'else:\s*\n[^\n]*\n\s*metrics\[\s*"Profit_Target_Source"\s*\]\s*=\s*'
            r'"MEASURED_MOVE \(BRK-001 post-breakout target\)"'
        )
        assert pat.search(output_src) is not None, (
            "Standardized BRK label write (LABEL-2 (a)) not found."
        )

    def test_provenance_marker_present(self, output_src):
        """Provenance discipline per BUGR-002 / BUGR-006 v2.0 precedent."""
        assert "[BUGR-006-LABEL-2 (3a)]" in output_src
        assert "[BUGR-006-LABEL-2 (a)]" in output_src


# ===========================================================================
# T-LABEL2-PA — TestLabel2ProfileAStandardization
# ===========================================================================
# Profile A BRK-active with MM target → exercises Edit 1 (compute.py:736).
# Pre-fix wrote "MEASURED_MOVE (post-breakout projection)" at line 736-739
# on Profile A. Post-fix writes "MEASURED_MOVE (BRK-001 post-breakout
# target)" per ODQ-2(a).

class TestLabel2ProfileAStandardization:
    """[BUGR-006-LABEL-2 / ODQ-2(a)] Profile A BRK MM target label standardization."""

    def _make_profile_a_brk_ctx(self):
        # Profile A, BRK-active, MM target raw populated.
        # Note: Profile A path uses cons_high_raw computation, then BRK MM
        # override at compute.py:733-739 writes Profit_Target_Source.
        df_ctx = _make_df_context(n=20, high_value=105.0, low_value=98.0)
        return _make_ctx(
            p_code="A",
            close=100.0,
            anchor=95.0,
            resistance_raw=99.0,
            atr_raw=1.0,
            df_ctx=df_ctx,
            daily_atr=1.0,
            daily_hard_stop=94.0,
            breakout_model_active=True,
            brk_tight_stop_raw=94.0,
            brk_mm_target_raw=115.0,
        )

    def test_profile_a_brk_label_standardized(self):
        """Post-fix (Edit 1): Profile A BRK MM target writes the standardized label."""
        ctx = self._make_profile_a_brk_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics

        # ODQ-2(a) — single string across both profiles
        assert m["Profit_Target_Source"] == LABEL_BRK_PRIMARY, (
            f"Profile A BRK label must be standardized to {LABEL_BRK_PRIMARY!r}; "
            f"got {m['Profit_Target_Source']!r}"
        )


# ===========================================================================
# T-LABEL2-NONBRK — TestLabel2NonBrkRegression  (class 3 structurally empty)
# ===========================================================================
# Per Phase 1 Step 1.4 verification (hand-back §1.4): _mm_raw is assigned
# at output.py:1150 INSIDE the `if _brk_active:` block at line 1146. The
# `if _mm_raw is not None:` branch at line 1164 is unreachable on non-BRK
# paths. Class 3 (non-BRK paths reaching this branch) is structurally
# empty. ODQ-2(a)'s label-text change has zero non-BRK observable impact.

class TestLabel2NonBrkRegression:
    """[BUGR-006-LABEL-2] Non-BRK class-3 emptiness verification (spec §4.3)."""

    def test_mm_raw_unreachable_on_non_brk(self):
        """SOURCE-INSPECTION: _mm_raw assignment is gated by `if _brk_active:`."""
        with open(_OUTPUT_PATH) as f:
            src = f.read()

        # Find the _mm_raw assignment context. The pre-existing structure is:
        #   if _brk_active:
        #       ...
        #       _mm_raw = ctx._brk_mm_target_raw
        # Verify: the only `_mm_raw =` assignment must be after a `if _brk_active:` line.
        lines = src.split("\n")
        mm_assign_lines = [
            i for i, ln in enumerate(lines)
            if re.match(r'^\s*_mm_raw\s*=', ln)
        ]
        assert len(mm_assign_lines) >= 1, "_mm_raw assignment expected in output.py"

        # For each _mm_raw assignment, walk upward looking for the nearest
        # enclosing `if _brk_active:` opener at strictly lower indent.
        for assign_idx in mm_assign_lines:
            assign_indent = len(lines[assign_idx]) - len(lines[assign_idx].lstrip())
            found_guard = False
            for back_idx in range(assign_idx - 1, max(0, assign_idx - 80), -1):
                stripped = lines[back_idx].lstrip()
                indent = len(lines[back_idx]) - len(stripped)
                if indent < assign_indent and stripped.startswith("if _brk_active"):
                    found_guard = True
                    break
                # Stop walking up if we hit a function definition
                if stripped.startswith("def "):
                    break
            assert found_guard, (
                f"_mm_raw assignment at line {assign_idx + 1} is not "
                "enclosed by `if _brk_active:` — class-3 emptiness violated."
            )

    def test_class_3_empty_documented(self):
        """Documentation marker — class 3 emptiness is a Phase 1 verification result.
        See hand-back document §1.4."""
        # This test always passes — its purpose is to surface the class-3 result
        # in pytest output for traceability.
        pass


# ===========================================================================
# T-OUT002-BRK — TestOut002DescBrkActive
# ===========================================================================
# Site 4 (transform.py:1077-1084). On BRK-active flat_metrics, the
# price_reward_risk.desc must read the "tight stop" variant verbatim.

class TestOut002DescBrkActive:
    """[OUT-002] Conditional desc — BRK-active branch."""

    def test_brk_active_desc_uses_tight_stop_verbatim(self):
        flat = _base_flat_metrics(brk_model_active=True)
        desc = _extract_price_rr_desc(_base_action_summary(), flat)

        # Verbatim per spec §3.1 / §4.4
        assert desc == DESC_BRK, (
            f"BRK-active desc mismatch.\nExpected: {DESC_BRK!r}\nActual:   {desc!r}"
        )

    def test_brk_active_desc_contains_routing_reference(self):
        """BUGR-004 routing reference preserved across both branches per §7.1."""
        flat = _base_flat_metrics(brk_model_active=True)
        desc = _extract_price_rr_desc(_base_action_summary(), flat)
        assert "See trade_setup.target.source for target origin." in desc


# ===========================================================================
# T-OUT002-NONBRK — TestOut002DescNonBrkRegression
# ===========================================================================
# Non-BRK path: BUGR-004 baseline desc unchanged. Pre-fix and post-fix
# both read "structural floor" verbatim.

class TestOut002DescNonBrkRegression:
    """[OUT-002] Conditional desc — non-BRK branch (regression)."""

    def test_non_brk_desc_uses_structural_floor_verbatim(self):
        flat = _base_flat_metrics(brk_model_active=False)
        desc = _extract_price_rr_desc(_base_action_summary(), flat)

        # BUGR-004 baseline preserved verbatim per spec §4.4 / §7.1
        assert desc == DESC_NONBRK, (
            f"Non-BRK desc mismatch.\nExpected: {DESC_NONBRK!r}\nActual:   {desc!r}"
        )

    def test_brk_model_active_missing_falls_to_non_brk(self):
        """If BRK_Model_Active flat key is absent (older fixture), default to
        non-BRK desc (False fallback per `flat_metrics.get('BRK_Model_Active', False)`)."""
        flat = _base_flat_metrics(brk_model_active=False)
        flat.pop("BRK_Model_Active", None)
        desc = _extract_price_rr_desc(_base_action_summary(), flat)
        assert desc == DESC_NONBRK


# ===========================================================================
# T-COEXIST-FULL — TestBundleCoexistenceFull
# ===========================================================================
# Integration: BRK-active Profile B + analyst data + CEG-eligible. All
# three Sites would have overwritten the BRK label pre-fix. Post-fix:
# label is BRK; Reward_Risk is BRK; Profit_Target is BRK; Fundamental_*
# populated; Capital_* untouched on the path; desc is "tight stop" via
# transform layer.

class TestBundleCoexistenceFull:
    """[BUGR-006 BUNDLE] All three sites coexisting on a single BRK-active path."""

    def _make_full_coexist_ctx(self):
        # BRK-active + fundamental + CEG-eligible
        df_ctx = _make_df_context(n=15, high_value=101.0, low_value=98.0)
        return _make_ctx(
            p_code="B",
            close=100.0,
            anchor=95.0,
            resistance_raw=99.0,                # suppressed (CEG-002 entry)
            atr_raw=1.0,
            df_ctx=df_ctx,
            breakout_model_active=True,
            brk_tight_stop_raw=94.0,
            brk_mm_target_raw=115.0,
            analyst_target_median=120.0,
            analyst_target_low=95.0,
            analyst_target_high=130.0,
            analyst_count=10,
        )

    def test_brk_label_survives_both_sites(self):
        """Post-fix: BRK label survives both FRR-001 and CEG-002 overwrites."""
        ctx = self._make_full_coexist_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics
        assert m["Profit_Target_Source"] == LABEL_BRK_PRIMARY

    def test_reward_risk_is_brk_value(self):
        ctx = self._make_full_coexist_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics
        assert m["Reward_Risk"] == 2.5

    def test_profit_target_is_brk_target(self):
        ctx = self._make_full_coexist_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics
        assert m["Profit_Target"] == 115.0

    def test_fundamental_keys_populated(self):
        ctx = self._make_full_coexist_ctx()
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics
        assert m.get("Fundamental_RR") is not None
        assert m.get("Fundamental_Target") == 120.0
        assert m.get("Fundamental_Floor") == 95.0

    def test_desc_via_transform_uses_tight_stop(self):
        """End-to-end desc check: BRK_Model_Active=True flat key → tight stop desc."""
        # Simulate the post-engine flat_metrics state on this BRK-active path.
        flat = _base_flat_metrics(
            brk_model_active=True,
            Profit_Target_Source=LABEL_BRK_PRIMARY,
            Profit_Target=115.0,
            Reward_Risk=2.5,
        )
        desc = _extract_price_rr_desc(_base_action_summary(), flat)
        assert desc == DESC_BRK


# ===========================================================================
# T-PROFILE-A-NONBRK-REGRESSION — TestProfileANonBrkRegression
# ===========================================================================
# Profile A non-BRK paths must produce unchanged labels:
#   - PE-41 escalation:  "WEEKLY_RESISTANCE (price above daily range)"
#   - RWD-001 blue-sky:  "ATR_PROJECTION (blue sky)"
#   - Plain pullback / no escalation: no Profit_Target_Source write at this site
# Plus regression on transform-layer desc (always "structural floor" on non-BRK).

class TestProfileANonBrkRegression:
    """[BUGR-006 BUNDLE] Profile A non-BRK regression assurance per spec §7.1."""

    def test_profile_a_pe41_escalation_label_unchanged(self):
        """Profile A non-BRK + PE-41 escalation: WEEKLY_RESISTANCE preserved."""
        # Build a Profile A ctx where cons_high_raw computes BELOW close
        # (daily Tier 1 fails) but weekly fallback gives a ceiling above close.
        # df_ctx high values < close=100 in the last 10 bars, but high in the
        # last 50 bars > close → triggers PE-41 escalation, no blue-sky.
        primary_df = _make_primary_df(n=30, close_value=100.0, high_value=99.0)
        # Build df_ctx: last 10 bars (iloc[-11:-1]) have max high=99 (< 100),
        # but earlier bars in the 50-bar window have high=120 → escalates,
        # AND headroom = 120 - 100 = 20 > 1.5 * daily_atr=1.0 = 1.5 → no blue sky.
        df_ctx = pd.DataFrame({
            "high":  [120.0] * 40 + [99.0] * 11,   # 51 bars
            "low":   [85.0]  * 51,
            "close": [95.0]  * 51,
        })
        ctx = _make_ctx(
            p_code="A",
            close=100.0,
            anchor=95.0,
            resistance_raw=98.0,
            atr_raw=1.0,
            primary_df=primary_df,
            df_ctx=df_ctx,
            daily_atr=1.0,
            daily_hard_stop=94.0,
            breakout_model_active=False,    # NON-BRK path
        )
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics
        # Per compute.py:660: PE-41 sets _profit_target_source = "WEEKLY_RESISTANCE (price above daily range)"
        # Per compute.py:717: writes metrics["Profit_Target_Source"] = _profit_target_source on Profile A
        assert m.get("Profit_Target_Source") == "WEEKLY_RESISTANCE (price above daily range)"

    def test_profile_a_rwd001_blue_sky_label_unchanged(self):
        """Profile A non-BRK + RWD-001 blue-sky: ATR_PROJECTION (blue sky) preserved."""
        # Setup: close=100, daily Tier 1 fails (last-10-bar high < close), 50-bar
        # window ceiling ABOVE close but compressed (headroom < 1.5 * daily_atr).
        # df_ctx: first 40 bars high=101 (in PE-41 50-bar window only); last 11
        # bars high=99 (drives Tier 1 max=99 < close=100). PE-41 escalation
        # picks up max(101, 99) = 101 → headroom = 1 < 1.5 * daily_atr=1.0 = 1.5.
        primary_df = _make_primary_df(n=30, close_value=100.0, high_value=99.0)
        df_ctx = pd.DataFrame({
            "high":  [101.0] * 40 + [99.0] * 11,
            "low":   [85.0]  * 51,
            "close": [95.0]  * 51,
        })
        ctx = _make_ctx(
            p_code="A",
            close=100.0,
            anchor=95.0,
            resistance_raw=98.0,
            atr_raw=1.0,
            primary_df=primary_df,
            df_ctx=df_ctx,
            daily_atr=1.0,
            daily_hard_stop=94.0,
            breakout_model_active=False,    # NON-BRK
        )
        # No mm_target_raw → ATR projection wins (no MEASURED_MOVE override)
        _compute_early_capital_rr(ctx, exit_signal=None)
        m = ctx.metrics

        # Per spec §7.1: RWD-001 Profile A blue-sky label preserved on non-BRK path.
        assert m.get("Profit_Target_Source") == LABEL_BLUE_SKY_ATR

    def test_non_brk_desc_regression_at_transform(self):
        """Profile A or B non-BRK path: transform desc unchanged from BUGR-004 baseline."""
        # Two probes: Profile A and Profile B non-BRK.
        for p_code in ("A", "B"):
            flat = _base_flat_metrics(brk_model_active=False, Profile_Code=p_code)
            desc = _extract_price_rr_desc(_base_action_summary(), flat)
            assert desc == DESC_NONBRK, (
                f"Non-BRK desc must match BUGR-004 baseline on Profile {p_code}; "
                f"got {desc!r}"
            )
