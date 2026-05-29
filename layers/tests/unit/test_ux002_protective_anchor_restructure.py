"""UX-002 — Protective Anchor Output Restructuring (Spec v1.0 §6 cohort).

Six classes per spec §6:
  1. TestUX002HigherFrameDailyAtr     -- Change 1: daily_atr relocated to higher_frame (Profile A only)
  2. TestUX002ProtectiveAnchorRemoved -- Change 3a: floor_analysis.protective_anchor group retired
  3. TestUX002FlattenSymmetry         -- Change 3b: _flatten() reverse-map re-homing recovers all 3 flat keys
  4. TestUX002ProfileBCInvariance     -- Profile B/C grouped output unaffected
  5. TestUX002VerdictInvariance       -- transform preserves the action_summary verdict (no accidental rewrite)
  6. TestUX002NotInGatesFile          -- no gate function reads any of the 3 affected flat keys (output-shape only)

Module loading follows the TEST-HRN-001 idempotent guard pattern -- safe to
co-run with other unit tests that load tbs_engine.transform under different
strategies (direct import vs spec_from_file_location).
"""
import sys
import os
import types as _types
import importlib.util
import inspect

import pytest


# ---------------------------------------------------------------------------
# TEST-HRN-001 idempotent module loading
# ---------------------------------------------------------------------------
_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _root not in sys.path:
    sys.path.insert(0, _root)

if "tbs_engine" not in sys.modules:
    _pkg = _types.ModuleType("tbs_engine")
    _pkg.__path__ = [os.path.join(_root, "tbs_engine")]
    sys.modules["tbs_engine"] = _pkg

if "tbs_engine.types" not in sys.modules:
    _types_spec = importlib.util.spec_from_file_location(
        "tbs_engine.types", os.path.join(_root, "tbs_engine", "types.py"))
    _types_mod = importlib.util.module_from_spec(_types_spec)
    sys.modules["tbs_engine.types"] = _types_mod
    _types_spec.loader.exec_module(_types_mod)

if "tbs_engine.helpers" not in sys.modules:
    _helpers_stub = _types.ModuleType("tbs_engine.helpers")
    _helpers_stub._check_round_number_proximity = lambda *a, **k: None
    _helpers_stub.check_climax_history = lambda *a, **k: None
    _helpers_stub._evaluate_floor_failure_context = lambda *a, **k: None
    sys.modules["tbs_engine.helpers"] = _helpers_stub

if "tbs_engine.transform" not in sys.modules:
    _transform_spec = importlib.util.spec_from_file_location(
        "tbs_engine.transform", os.path.join(_root, "tbs_engine", "transform.py"))
    _transform_mod = importlib.util.module_from_spec(_transform_spec)
    sys.modules["tbs_engine.transform"] = _transform_mod
    _transform_spec.loader.exec_module(_transform_mod)
else:
    _transform_mod = sys.modules["tbs_engine.transform"]

_transform_output = _transform_mod._transform_output
_flatten = _transform_mod._flatten


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _action_summary_valid():
    """Minimal VALID action_summary for _transform_output."""
    return {
        "verdict": "VALID",
        "reason": {"label": "PULLBACK", "detail": "All gates passed."},
        "mandate": "Enter on pullback.",
        "merit": {"quality": "STRONG", "reward": "HEALTHY [2.5]"},
        "trigger": {"rule": "pullback_zone", "condition": "Close within zone"},
        "volume": "MIXED",
        "volume_confirmation": None,
        "entry_strategy": {
            "entry_price": 150.0, "stop_loss": 140.0, "target": 170.0,
            "fib_382": None, "fib_500": None, "fib_confluence": None, "mm_target": None,
        },
        "exit_status": {"active": False, "reason": None},
    }


def _profile_a_metrics(**overrides):
    """Profile A flat_metrics with higher_frame DAILY context populated.

    DQ-4 invariant: Daily_Protective_Anchor == Context_EMA_21 on Profile A (both
    reduce to round(df_ctx['EMA_21'].iloc[-1] / price_scaler, 2)). The fixture
    holds them equal so the round-trip in TestUX002FlattenSymmetry mirrors the
    production invariant.
    """
    m = {
        "Price": 150.0, "Structural_Floor": 140.0, "Resistance": 160.0,
        "ATR": 2.0, "EMA_8": 149.0, "EMA_21": 148.0, "SMA_50": 135.0,
        "SMA_200": 120.0, "VWAP": 148.5, "ADV_20": 500000,
        "Convexity_Class": "C1", "Is_ETF": False,
        "ATR_Dist": 0.5, "ATR_Dist_Anchor": "VWAP",
        "Extension_Limit": 1.0, "Extension_Anchor_Type": "VWAP",
        "Extension_Anchor_Label": "Session VWAP",
        "Reward_Risk": 3.0, "Capital_Reward_Risk": 2.5,
        "Capital_RR_Label": "HEALTHY", "Risk_Per_Unit": 10.0,
        "Expectancy_Threshold": 2.0, "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Price R:R 3.00 >= 2.0. Capital R:R 2.50 (HEALTHY).",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Anchor_Type": "VWAP", "Anchor_Label": "Session VWAP",
        "Profit_Target": 170.0, "Hard_Stop": 140.0,
        "THS_Score": 75, "THS_Label": "STRONG",
        "Convexity": "C-1",
        # PA-001 daily fields
        "Daily_Protective_Anchor": 145.0,
        "Daily_ATR": 3.5,
        "Daily_Hard_Stop": 139.75,  # 145 - 1.5*3.5
        "Daily_Extension_Distance": 1.43,
        "Daily_Extension_Label": "NORMAL",
        "Capital_RR_Role": "ADVISORY",
        "Capital_RR_Role_Desc": "Profile A: advisory.",
        # higher_frame DAILY context (drives _hf_timeframe = "DAILY")
        "Context_EMA_8": 149.0,
        "Context_EMA_21": 145.0,           # equal to Daily_Protective_Anchor per DQ-4
        "Context_EMA_Stacked": True,
        "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "8 > 21 (DAILY)",
        "Context_Daily_SMA50": 135.0,
        "Context_Daily_SMA50_Slope": 0.10,
        "Context_SMA200": 120.0,
        "Context_Golden_Cross": True,
        "Context_Price_vs_SMA200": 30.0,
        "Context_Daily_EMA_50": 138.0,
        "Context_Daily_EMA_50_Slope": 0.08,
    }
    m.update(overrides)
    return m


def _profile_b_metrics(**overrides):
    """Profile B fixture: higher_frame WEEKLY context, no PA-001 daily fields.

    data.py defaults Daily_ATR / Daily_Protective_Anchor / Daily_Hard_Stop to
    0.0 on B/C (see data.py:683-693); the fixture omits them entirely to match
    the "absent" pre-state (B/C never had the protective_anchor group, per
    spec §2 and the existing PA-001 Phase 2 isolation tests).
    """
    m = {
        "Price": 50.0, "Structural_Floor": 45.0, "Resistance": 60.0,
        "ATR": 1.0, "EMA_8": 49.0, "EMA_21": 48.0, "SMA_50": 42.0,
        "SMA_200": 35.0, "VWAP": 49.5, "ADV_20": 1000000,
        "Convexity_Class": "C1", "Is_ETF": False,
        "ATR_Dist": 0.3, "ATR_Dist_Anchor": "EMA_21",
        "Extension_Limit": 1.0, "Extension_Anchor_Type": "EMA_21",
        "Extension_Anchor_Label": "21 EMA",
        "Reward_Risk": 4.0, "Capital_Reward_Risk": 3.0,
        "Capital_RR_Label": "HEALTHY", "Risk_Per_Unit": 5.0,
        "Expectancy_Threshold": 2.0, "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Price R:R 4.00 >= 2.0. Capital R:R 3.00 (HEALTHY).",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Anchor_Type": "SMA_50", "Anchor_Label": "Daily SMA 50",
        "Profit_Target": 60.0, "Hard_Stop": 43.0,
        "THS_Score": 80, "THS_Label": "STRONG",
        "Capital_RR_Role": "ENFORCEABLE",
        "Capital_RR_Role_Desc": "Capital R:R enforced as hard gate.",
        # higher_frame WEEKLY context
        "Context_EMA_8": 49.0, "Context_EMA_21": 48.0,
        "Context_EMA_Stacked": True, "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "8 > 21 (WEEKLY)",
        "Context_Weekly_SMA50": 42.0, "Context_Weekly_SMA50_Slope": 0.05,
        "Context_Weekly_SMA200": 35.0, "Context_Weekly_Golden_Cross": True,
        "Context_Weekly_Price_vs_SMA200": 15.0,
    }
    m.update(overrides)
    return m


def _profile_c_metrics(**overrides):
    """Profile C fixture: higher_frame MONTHLY context."""
    m = {
        "Price": 80.0, "Structural_Floor": 70.0, "Resistance": 90.0,
        "ATR": 2.5, "EMA_8": 79.0, "EMA_21": 78.0, "SMA_50": 68.0,
        "SMA_200": 50.0, "VWAP": 79.0, "ADV_20": 800000,
        "Convexity_Class": "C1", "Is_ETF": False,
        "ATR_Dist": 0.5, "ATR_Dist_Anchor": "SMA_200",
        "Extension_Limit": 1.0, "Extension_Anchor_Type": "WEEKLY_SMA_200",
        "Extension_Anchor_Label": "Weekly SMA 200",
        "Reward_Risk": 2.0, "Capital_Reward_Risk": 1.5,
        "Capital_RR_Label": "HEALTHY", "Risk_Per_Unit": 8.0,
        "Expectancy_Threshold": 1.5, "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Profile C summary.",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Anchor_Type": "SMA_200", "Anchor_Label": "Daily SMA 200",
        "Profit_Target": 90.0, "Hard_Stop": 70.0,
        "THS_Score": 70, "THS_Label": "ADEQUATE",
        "Capital_RR_Role": "ENFORCEABLE",
        "Capital_RR_Role_Desc": "Capital R:R enforced as hard gate.",
        # higher_frame MONTHLY context
        "Context_EMA_8": 79.0, "Context_EMA_21": 78.0,
        "Context_EMA_Stacked": True, "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "8 > 21 (MONTHLY)",
        "Context_Monthly_SMA50": 68.0, "Context_Monthly_SMA50_Slope": 0.10,
        "Context_Monthly_SMA200": 50.0, "Context_Monthly_Golden_Cross": True,
        "Context_Monthly_Price_vs_SMA200": 30.0,
    }
    m.update(overrides)
    return m


# ===========================================================================
# 1. Change 1 -- daily_atr relocated to higher_frame (Profile A only)
# ===========================================================================

class TestUX002HigherFrameDailyAtr:
    """`higher_frame.daily_atr` sub-object emitted on Profile A; absent on B/C."""

    def test_profile_a_daily_atr_present(self):
        result = _transform_output(_action_summary_valid(), _profile_a_metrics())
        hf = result["floor_analysis"]["higher_frame"]
        assert "daily_atr" in hf, "higher_frame.daily_atr required on Profile A"
        d = hf["daily_atr"]
        assert d["value"] == 3.5
        assert d["unit"] == "price"
        assert "desc" in d and "Daily ATR(14)" in d["desc"]

    def test_profile_a_value_matches_flat_daily_atr(self):
        fm = _profile_a_metrics(Daily_ATR=2.71)
        result = _transform_output(_action_summary_valid(), fm)
        assert result["floor_analysis"]["higher_frame"]["daily_atr"]["value"] == 2.71

    def test_profile_a_absent_when_daily_atr_zero(self):
        """data.py:684 defaults Daily_ATR to 0.0 -- > 0 guard suppresses emission."""
        fm = _profile_a_metrics(Daily_ATR=0.0)
        result = _transform_output(_action_summary_valid(), fm)
        hf = result["floor_analysis"]["higher_frame"]
        assert "daily_atr" not in hf

    def test_profile_a_absent_when_daily_atr_none(self):
        fm = _profile_a_metrics()
        del fm["Daily_ATR"]
        result = _transform_output(_action_summary_valid(), fm)
        hf = result["floor_analysis"]["higher_frame"]
        assert "daily_atr" not in hf

    def test_profile_b_absent(self):
        result = _transform_output(_action_summary_valid(), _profile_b_metrics())
        hf = result["floor_analysis"].get("higher_frame") or {}
        assert "daily_atr" not in hf, "higher_frame.daily_atr is Profile A only"

    def test_profile_c_absent(self):
        result = _transform_output(_action_summary_valid(), _profile_c_metrics())
        hf = result["floor_analysis"].get("higher_frame") or {}
        assert "daily_atr" not in hf, "higher_frame.daily_atr is Profile A only"


# ===========================================================================
# 2. Change 3a -- floor_analysis.protective_anchor group retired
# ===========================================================================

class TestUX002ProtectiveAnchorRemoved:
    """`floor_analysis.protective_anchor` key is never emitted post-UX-002."""

    def test_profile_a_no_protective_anchor_key(self):
        result = _transform_output(_action_summary_valid(), _profile_a_metrics())
        fa = result["floor_analysis"]
        assert "protective_anchor" not in fa, \
            "protective_anchor group retired by UX-002 spec §4.3a"

    def test_profile_b_no_protective_anchor_key(self):
        result = _transform_output(_action_summary_valid(), _profile_b_metrics())
        fa = result["floor_analysis"]
        assert "protective_anchor" not in fa

    def test_profile_c_no_protective_anchor_key(self):
        result = _transform_output(_action_summary_valid(), _profile_c_metrics())
        fa = result["floor_analysis"]
        assert "protective_anchor" not in fa


# ===========================================================================
# 3. Change 3b -- _flatten reverse-map symmetry
# ===========================================================================

class TestUX002FlattenSymmetry:
    """All three flat keys recoverable via re-homed reverse-map sources."""

    def test_daily_atr_round_trip(self):
        """Daily_ATR recovered from higher_frame.daily_atr.value."""
        fm = _profile_a_metrics()
        result = _transform_output(_action_summary_valid(), fm)
        _status, _diag, flat = _flatten(result)
        assert flat.get("Daily_ATR") == 3.5

    def test_daily_protective_anchor_round_trip(self):
        """Daily_Protective_Anchor recovered from higher_frame.ema.ema_21 (DQ-4)."""
        fm = _profile_a_metrics()  # fixture holds DPA == Context_EMA_21 == 145.0
        result = _transform_output(_action_summary_valid(), fm)
        _status, _diag, flat = _flatten(result)
        assert flat.get("Daily_Protective_Anchor") == 145.0

    def test_daily_hard_stop_round_trip(self):
        """Daily_Hard_Stop recovered from stop-hierarchy DAILY_HARD_STOP entry."""
        fm = _profile_a_metrics()
        result = _transform_output(_action_summary_valid(), fm)
        _status, _diag, flat = _flatten(result)
        assert flat.get("Daily_Hard_Stop") == 139.75

    def test_legacy_protective_anchor_branch_not_relied_on(self):
        """Removal of the protective_anchor key from grouped output must NOT
        zero the three flat keys -- the new reverse-map sources cover them."""
        fm = _profile_a_metrics()
        result = _transform_output(_action_summary_valid(), fm)
        # Confirm the legacy source is genuinely gone
        assert "protective_anchor" not in result["floor_analysis"]
        # And yet all three flat keys still round-trip
        _status, _diag, flat = _flatten(result)
        assert flat.get("Daily_ATR") is not None
        assert flat.get("Daily_Protective_Anchor") is not None
        assert flat.get("Daily_Hard_Stop") is not None


# ===========================================================================
# 4. Profile B/C invariance
# ===========================================================================

class TestUX002ProfileBCInvariance:
    """Profile B/C grouped output unaffected by UX-002 -- no new keys, no
    accidental emission, idempotent re-runs.
    """

    def test_profile_b_no_daily_atr(self):
        result = _transform_output(_action_summary_valid(), _profile_b_metrics())
        hf = result["floor_analysis"].get("higher_frame") or {}
        assert "daily_atr" not in hf

    def test_profile_b_no_protective_anchor(self):
        result = _transform_output(_action_summary_valid(), _profile_b_metrics())
        assert "protective_anchor" not in result["floor_analysis"]

    def test_profile_c_no_daily_atr(self):
        result = _transform_output(_action_summary_valid(), _profile_c_metrics())
        hf = result["floor_analysis"].get("higher_frame") or {}
        assert "daily_atr" not in hf

    def test_profile_c_no_protective_anchor(self):
        result = _transform_output(_action_summary_valid(), _profile_c_metrics())
        assert "protective_anchor" not in result["floor_analysis"]

    def test_profile_b_flat_keys_unaffected(self):
        """Round-trip on B does not produce Daily_* flat keys (B has no daily group)."""
        result = _transform_output(_action_summary_valid(), _profile_b_metrics())
        _status, _diag, flat = _flatten(result)
        # The three keys must NOT appear (or appear as None) on B
        assert flat.get("Daily_ATR") is None
        assert flat.get("Daily_Hard_Stop") is None
        # Daily_Protective_Anchor: B's higher_frame.ema.ema_21 is the WEEKLY EMA
        # 21, NOT the daily protective anchor. The re-homed reverse-map keys it
        # off the DAILY branch (_tf_label == "DAILY"), so it is never written on
        # Profile B. Verifying that contract here.
        assert flat.get("Daily_Protective_Anchor") is None


# ===========================================================================
# 5. Verdict invariance
# ===========================================================================

class TestUX002VerdictInvariance:
    """The action_summary verdict is preserved through the transform on the
    same fixture -- UX-002 is an output-shape change with zero verdict path
    impact (spec §2: "Zero gate, verdict, threshold, sizing, or numeric change").
    """

    def test_profile_a_verdict_preserved(self):
        result = _transform_output(_action_summary_valid(), _profile_a_metrics())
        assert result["action_summary"]["verdict"] == "VALID"

    def test_profile_a_verdict_idempotent(self):
        """Two transform runs on the same fixture yield the same verdict."""
        fm = _profile_a_metrics()
        r1 = _transform_output(_action_summary_valid(), fm)
        r2 = _transform_output(_action_summary_valid(), fm)
        assert r1["action_summary"]["verdict"] == r2["action_summary"]["verdict"]

    def test_verdict_independent_of_daily_atr_emission(self):
        """Removing Daily_ATR (suppressing the new sub-object) must not
        alter the verdict -- the transform layer is downstream of all gates."""
        fm_with = _profile_a_metrics()
        fm_without = _profile_a_metrics(Daily_ATR=0.0)
        r_with = _transform_output(_action_summary_valid(), fm_with)
        r_without = _transform_output(_action_summary_valid(), fm_without)
        assert r_with["action_summary"]["verdict"] == r_without["action_summary"]["verdict"]


# ===========================================================================
# 6. No gate function reads any of the three affected flat keys
# ===========================================================================

class TestUX002NotInGatesFile:
    """Negative assertion: spec §2 + §12 mandate -- no gate function reads
    Daily_Protective_Anchor, Daily_ATR, or Daily_Hard_Stop. EEM §II bitwise-
    invariant follows directly. Uses inspect.getsource so the assertion
    survives future renames of individual gate functions.
    """

    @staticmethod
    def _load_gates_source():
        """Load gates.py source via spec_from_file_location to avoid the
        helpers import chain that bare `import tbs_engine.gates` would pull in.
        """
        path = os.path.join(_root, "tbs_engine", "gates.py")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_no_gate_reads_daily_protective_anchor(self):
        src = self._load_gates_source()
        assert "Daily_Protective_Anchor" not in src, \
            "spec §2 violated -- Daily_Protective_Anchor read in gates.py"

    def test_no_gate_reads_daily_atr(self):
        src = self._load_gates_source()
        assert "Daily_ATR" not in src, \
            "spec §2 violated -- Daily_ATR read in gates.py"

    def test_no_gate_reads_daily_hard_stop(self):
        src = self._load_gates_source()
        assert "Daily_Hard_Stop" not in src, \
            "spec §2 violated -- Daily_Hard_Stop read in gates.py"
