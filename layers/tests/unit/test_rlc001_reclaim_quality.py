"""RLC-001 -- Reclaim Quality Score (Tennis Ball Action) -- unit tests.

Spec: RLC001_Reclaim_Quality_Score_Spec_v1_0.md (v1.0, S160)

Covers the 10 test classes per spec §5 (~35-45 tests target):

     1. TestRLC001Formula                  -- formula correctness, 4dp storage
     2. TestRLC001Banding                  -- threshold boundary inclusivity (>=)
     3. TestRLC001VocabularyDiscipline     -- exact label literals + desc substrings
     4. TestRLC001NullDefensive            -- 6 null/edge paths (Spec §3.2)
     5. TestRLC001VerdictGuard             -- verdict / entry_type guard matrix
     6. TestRLC001VerdictInvariance        -- helper does not mutate gate_result
     7. TestRLC001SchemaStability          -- block shape invariants
     8. TestRLC001FlatKeyRegistration      -- MAPPED_FLAT_KEYS membership
     9. TestRLC001PositiveOnly             -- absence-as-signal (KeyError on access)
    10. TestRLC001ActionSummaryAttachment  -- call-site attachment integration

Construction notes:
    - Helper-isolation pattern (mirrors VTRIG-001 / SFR-001 sibling tests).
      output.py is loaded via spec_from_file_location with tbs_engine sub-
      modules stubbed (TEST-HRN-001 compatible idempotent pattern).
    - GateResult is constructed via SimpleNamespace; ctx is a SimpleNamespace
      carrying only the `last` attribute the helper reads.
    - Test 10 mirrors the attachment idiom from the output.py call site --
      the helper return value plus the action_summary verdict guard.
"""

import os
import sys
import types
import importlib.util
import math
from types import SimpleNamespace

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Module loading -- mirrors VTRIG-001 isolation pattern.
# Stubs only what's not already loaded so the file is suite-friendly.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(__file__)
_LAYERS_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _LAYERS_ROOT not in sys.path:
    sys.path.insert(0, _LAYERS_ROOT)

if "tbs_engine" not in sys.modules:
    _pkg = types.ModuleType("tbs_engine")
    _pkg.__path__ = [os.path.join(_LAYERS_ROOT, "tbs_engine")]
    sys.modules["tbs_engine"] = _pkg

# Stub sibling modules only if not already present (e.g. when running the
# full suite alongside tests that do exercise them, the real modules are
# already in sys.modules and we should leave them alone).
for _mod_name in [
    "tbs_engine.types", "tbs_engine.helpers",
    "tbs_engine.charts", "tbs_engine.transform", "tbs_engine.compute",
]:
    if _mod_name not in sys.modules:
        _m = types.ModuleType(_mod_name)
        _m.GRACE_BUFFER_ATR_PCT = 0.0
        _m.MetricsResult = type("MetricsResult", (), {})
        _m.GateResult = type("GateResult", (), {})
        _m._clamp = lambda *a, **k: None
        _m.check_climax_history = lambda *a, **k: None
        _m._build_focus_chart = lambda *a, **k: None
        _m._transform_output = lambda *a, **k: None
        _m._flatten = lambda *a, **k: None
        _m._audit_key_coverage = lambda *a, **k: None
        _m._error_output = lambda *a, **k: None
        _m.BRK_STOP_BUFFER_ATR = 0.0
        _m.BRK_CATASTROPHIC_MULTIPLIER = 0.0
        _m.RLY_WINDOW_BARS = 15
        _m.RLY_MATURE_RATIO_THRESHOLD = 10.0 / 15.0
        _m.RLY_MATURE_MAGNITUDE_ATR_THRESHOLD = 5.0
        sys.modules[_mod_name] = _m

if "tbs_engine.output" in sys.modules:
    _output = sys.modules["tbs_engine.output"]
else:
    _spec = importlib.util.spec_from_file_location(
        "tbs_engine.output",
        os.path.join(_LAYERS_ROOT, "tbs_engine", "output.py"))
    _output = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_output)
    # Don't register in sys.modules globally -- TEST-HRN-001 idempotent path.

_assemble_reclaim_quality = _output._assemble_reclaim_quality
RLC_STRONG_THRESHOLD = _output.RLC_STRONG_THRESHOLD
RLC_MODERATE_THRESHOLD = _output.RLC_MODERATE_THRESHOLD
_RLC_THRESHOLDS = _output._RLC_THRESHOLDS
_RLC_NULL_FLAT_KEYS = _output._RLC_NULL_FLAT_KEYS


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_gate_result(verdict="VALID", entry_type="RECLAIM", reason=None,
                     mandate=None, context=None, trigger_rule=None, state=None):
    return SimpleNamespace(
        verdict=verdict,
        entry_type=entry_type,
        reason=reason or entry_type or verdict,
        mandate=mandate or "Execute at THIS bar's close.",
        context=context or "Test context.",
        trigger_rule=trigger_rule or "BAR CLOSE ONLY",
        state=state or "TRENDING",
    )


def _make_ctx(close, high, low, open_=None):
    """Build a minimal ctx with last attribute the helper reads."""
    last = {"close": close, "high": high, "low": low,
            "open": open_ if open_ is not None else close}
    return SimpleNamespace(last=last)


# ===========================================================================
# 1. TestRLC001Formula -- formula correctness across STRONG / MODERATE / WEAK
# ===========================================================================

class TestRLC001Formula:
    """Spec §3.1 + §8.1: Formula (close - low) / (high - low)."""

    def test_strong_example_A(self):
        # Spec §8.1 Example A: close=103.80, high=104.00, low=100.00
        ctx = _make_ctx(close=103.80, high=104.00, low=100.00)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert flat["Reclaim_Quality_Pct"] == pytest.approx(0.9500, abs=1e-6)
        assert block["value"] == pytest.approx(0.9500, abs=1e-6)
        assert block["condition"]["label"] == "STRONG_RECLAIM"

    def test_moderate_example_B(self):
        # Spec §8.1 Example B: close=102.10, high=103.00, low=100.00
        ctx = _make_ctx(close=102.10, high=103.00, low=100.00)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert flat["Reclaim_Quality_Pct"] == pytest.approx(0.7000, abs=1e-6)
        assert block["condition"]["label"] == "MODERATE_RECLAIM"

    def test_weak_example_C(self):
        # Spec §8.1 Example C: close=101.20, high=103.00, low=100.00
        ctx = _make_ctx(close=101.20, high=103.00, low=100.00)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert flat["Reclaim_Quality_Pct"] == pytest.approx(0.4000, abs=1e-6)
        assert block["condition"]["label"] == "WEAK_RECLAIM"

    def test_pct_clamped_at_one_when_close_equals_high(self):
        ctx = _make_ctx(close=110.0, high=110.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert flat["Reclaim_Quality_Pct"] == pytest.approx(1.0, abs=1e-6)
        assert block["condition"]["label"] == "STRONG_RECLAIM"

    def test_pct_zero_when_close_equals_low(self):
        ctx = _make_ctx(close=100.0, high=110.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert flat["Reclaim_Quality_Pct"] == pytest.approx(0.0, abs=1e-6)
        assert block["condition"]["label"] == "WEAK_RECLAIM"

    def test_storage_is_4dp(self):
        # 5.0 / 7.0 = 0.71428571... -> rounds to 0.7143
        ctx = _make_ctx(close=107.0, high=107.0, low=100.0)
        # close=107, low=100, high=107 -> range=7, (close-low)/range = 1.0
        # Use a non-clean ratio instead:
        ctx = _make_ctx(close=105.0, high=107.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        # (105-100)/(107-100) = 5/7 = 0.714285...
        assert flat["Reclaim_Quality_Pct"] == 0.7143
        assert block["value"] == 0.7143

    def test_above_high_anomaly_passes_through(self):
        # Data corruption: close > high. Spec §3.2 says no clamp -- fail loud.
        ctx = _make_ctx(close=115.0, high=110.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        # (115-100)/(110-100) = 1.5 -- surfaces > 1.0
        assert flat["Reclaim_Quality_Pct"] == 1.5
        # >=0.75 -> STRONG_RECLAIM (no clamp on banding either)
        assert block["condition"]["label"] == "STRONG_RECLAIM"


# ===========================================================================
# 2. TestRLC001Banding -- exact threshold boundary inclusivity (Spec §3.3)
# ===========================================================================

class TestRLC001Banding:
    """Spec §3.3: STRONG `>=0.75`, MODERATE `>=0.60`, WEAK `<0.60`."""

    def test_boundary_0_750_inclusive_strong(self):
        # Spec §8.1 Example E: pct = 0.75 exact -> STRONG (inclusive)
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["value"] == pytest.approx(0.75, abs=1e-6)
        assert block["condition"]["label"] == "STRONG_RECLAIM"

    def test_boundary_0_749_below_strong(self):
        # 0.7499 exact via 7499/10000
        ctx = _make_ctx(close=107499.0, high=110000.0, low=100000.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["value"] == pytest.approx(0.7499, abs=1e-6)
        assert block["condition"]["label"] == "MODERATE_RECLAIM"

    def test_boundary_0_600_inclusive_moderate(self):
        # Spec §8.1 Example F: pct = 0.60 exact -> MODERATE (inclusive)
        ctx = _make_ctx(close=103.0, high=105.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["value"] == pytest.approx(0.60, abs=1e-6)
        assert block["condition"]["label"] == "MODERATE_RECLAIM"

    def test_boundary_0_599_below_moderate(self):
        # close=105999, high=110000, low=100000 -> 5999/10000 = 0.5999
        ctx = _make_ctx(close=105999.0, high=110000.0, low=100000.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["value"] == pytest.approx(0.5999, abs=1e-6)
        assert block["condition"]["label"] == "WEAK_RECLAIM"

    def test_far_below_moderate_is_weak(self):
        ctx = _make_ctx(close=101.0, high=110.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["value"] == pytest.approx(0.10, abs=1e-6)
        assert block["condition"]["label"] == "WEAK_RECLAIM"

    def test_far_above_strong_threshold(self):
        ctx = _make_ctx(close=109.99, high=110.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["condition"]["label"] == "STRONG_RECLAIM"


# ===========================================================================
# 3. TestRLC001VocabularyDiscipline -- exact label literals (Spec §3.3, DQ-2b)
# ===========================================================================

class TestRLC001VocabularyDiscipline:
    """Spec DQ-2b: STRONG_RECLAIM / MODERATE_RECLAIM / WEAK_RECLAIM only."""

    def test_strong_label_literal(self):
        ctx = _make_ctx(close=103.80, high=104.00, low=100.00)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["condition"]["label"] == "STRONG_RECLAIM"
        # No drift to bare STRONG / STRONG_ACCUM / etc.
        assert block["condition"]["label"] not in {"STRONG", "STRONG_ACCUM",
                                                    "STRONG_RECOVERY"}

    def test_moderate_label_literal(self):
        ctx = _make_ctx(close=102.10, high=103.00, low=100.00)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["condition"]["label"] == "MODERATE_RECLAIM"

    def test_weak_label_literal(self):
        ctx = _make_ctx(close=101.20, high=103.00, low=100.00)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["condition"]["label"] == "WEAK_RECLAIM"

    def test_strong_desc_contains_75pct_substring(self):
        ctx = _make_ctx(close=103.80, high=104.00, low=100.00)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert ">=75%" in block["condition"]["desc"]
        assert "decisive" in block["condition"]["desc"]

    def test_moderate_desc_contains_band_substring(self):
        ctx = _make_ctx(close=102.10, high=103.00, low=100.00)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert "60-75%" in block["condition"]["desc"]
        assert "moderate" in block["condition"]["desc"]

    def test_weak_desc_contains_band_substring(self):
        ctx = _make_ctx(close=101.20, high=103.00, low=100.00)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert "<60%" in block["condition"]["desc"]
        assert "weak" in block["condition"]["desc"]

    def test_desc_uses_integer_percent_formatting(self):
        # 0.83333... -> "83%" not "83.33%"
        ctx = _make_ctx(close=105.0, high=106.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert "83%" in block["condition"]["desc"]
        assert "83.33" not in block["condition"]["desc"]


# ===========================================================================
# 4. TestRLC001NullDefensive -- 6 null / edge paths (Spec §3.2)
# ===========================================================================

class TestRLC001NullDefensive:
    """Spec §3.2: helper returns (None, {Reclaim_Quality_Pct: None}) on null."""

    def test_gate_result_is_none(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, None)
        assert block is None
        assert flat == {"Reclaim_Quality_Pct": None}

    def test_close_is_none(self):
        ctx = _make_ctx(close=None, high=104.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None
        assert flat["Reclaim_Quality_Pct"] is None

    def test_high_is_none(self):
        ctx = _make_ctx(close=103.0, high=None, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None
        assert flat["Reclaim_Quality_Pct"] is None

    def test_low_is_none(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=None)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None

    def test_close_is_nan(self):
        ctx = _make_ctx(close=float("nan"), high=104.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None
        assert flat["Reclaim_Quality_Pct"] is None

    def test_high_is_nan(self):
        ctx = _make_ctx(close=103.0, high=float("nan"), low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None

    def test_low_is_nan(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=float("nan"))
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None

    def test_degenerate_range_doji(self):
        # Spec §8.1 Example D: high == low -> bar_range == 0 -> null
        ctx = _make_ctx(close=100.0, high=100.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None
        assert flat["Reclaim_Quality_Pct"] is None

    def test_inverted_range_high_below_low(self):
        # Data corruption: high < low -> bar_range < 0 -> null-defensive
        ctx = _make_ctx(close=102.0, high=99.0, low=100.0)
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None

    def test_missing_close_key_raises_handled(self):
        ctx = SimpleNamespace(last={"high": 104.0, "low": 100.0})
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None
        assert flat["Reclaim_Quality_Pct"] is None

    def test_non_numeric_close_raises_handled(self):
        ctx = SimpleNamespace(last={"close": "abc", "high": 104.0, "low": 100.0})
        block, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block is None


# ===========================================================================
# 5. TestRLC001VerdictGuard -- verdict / entry_type guard matrix
# ===========================================================================

class TestRLC001VerdictGuard:
    """Spec §2.2: helper returns null on every non-VALID-x-RECLAIM path."""

    @pytest.mark.parametrize("verdict", ["WAIT", "INVALID", "RECOVERY CANDIDATE",
                                         "ERROR"])
    def test_non_valid_verdicts(self, verdict):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict=verdict, entry_type="RECLAIM")
        block, flat = _assemble_reclaim_quality(ctx, gr)
        assert block is None
        assert flat["Reclaim_Quality_Pct"] is None

    @pytest.mark.parametrize("entry_type", ["PULLBACK", "BREAKOUT",
                                            "SWING_BREAKOUT", None])
    def test_non_reclaim_entry_types(self, entry_type):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type=entry_type)
        block, flat = _assemble_reclaim_quality(ctx, gr)
        assert block is None
        assert flat["Reclaim_Quality_Pct"] is None

    def test_valid_reclaim_does_emit(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="RECLAIM")
        block, flat = _assemble_reclaim_quality(ctx, gr)
        assert block is not None
        assert flat["Reclaim_Quality_Pct"] is not None


# ===========================================================================
# 6. TestRLC001VerdictInvariance -- helper does not mutate inputs (DQ-1 lock)
# ===========================================================================

class TestRLC001VerdictInvariance:
    """SIR §11.2 Track 2: zero verdict-cascade impact.

    The helper must be read-only on gate_result and ctx -- pre/post field
    snapshot must be bit-identical.
    """

    def _snapshot_gate_result(self, gr):
        return {
            "verdict": gr.verdict,
            "entry_type": gr.entry_type,
            "reason": gr.reason,
            "mandate": gr.mandate,
            "context": gr.context,
            "trigger_rule": getattr(gr, "trigger_rule", None),
            "state": getattr(gr, "state", None),
        }

    def test_gate_result_unchanged_on_valid_reclaim(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="RECLAIM")
        before = self._snapshot_gate_result(gr)
        _assemble_reclaim_quality(ctx, gr)
        after = self._snapshot_gate_result(gr)
        assert before == after

    def test_gate_result_unchanged_on_non_reclaim(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="PULLBACK")
        before = self._snapshot_gate_result(gr)
        _assemble_reclaim_quality(ctx, gr)
        after = self._snapshot_gate_result(gr)
        assert before == after

    def test_ctx_last_unchanged(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        # ctx.last is a dict -- snapshot keys + values.
        before = dict(ctx.last)
        _assemble_reclaim_quality(ctx, _make_gate_result())
        after = dict(ctx.last)
        assert before == after

    def test_helper_is_pure_repeatable(self):
        """Calling twice yields identical results -- no hidden state."""
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result()
        a_block, a_flat = _assemble_reclaim_quality(ctx, gr)
        b_block, b_flat = _assemble_reclaim_quality(ctx, gr)
        assert a_block == b_block
        assert a_flat == b_flat


# ===========================================================================
# 7. TestRLC001SchemaStability -- block shape invariants
# ===========================================================================

class TestRLC001SchemaStability:
    """Spec §4.6: block has value / condition / thresholds, never half-pop'd."""

    def test_block_keys_present_on_valid_reclaim(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert set(block.keys()) == {"value", "condition", "thresholds"}

    def test_condition_has_label_and_desc(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert set(block["condition"].keys()) == {"label", "desc"}
        assert block["condition"]["label"] is not None
        assert block["condition"]["desc"] is not None
        assert block["condition"]["desc"] != ""

    def test_thresholds_exact_keys(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert set(block["thresholds"].keys()) == {
            "strong_at_or_above", "moderate_at_or_above", "weak_below"}

    def test_thresholds_exact_values(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert block["thresholds"]["strong_at_or_above"] == 0.75
        assert block["thresholds"]["moderate_at_or_above"] == 0.60
        assert block["thresholds"]["weak_below"] == 0.60

    def test_thresholds_is_independent_copy(self):
        """Mutating the returned thresholds must not affect the module const."""
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        block, _ = _assemble_reclaim_quality(ctx, _make_gate_result())
        block["thresholds"]["strong_at_or_above"] = 99.9
        assert _RLC_THRESHOLDS["strong_at_or_above"] == 0.75

    def test_flat_keys_always_one_key(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        _, flat = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert set(flat.keys()) == {"Reclaim_Quality_Pct"}

    def test_flat_key_null_dict_independent_copy(self):
        """Mutating one defensive return must not affect later returns."""
        ctx = _make_ctx(close=None, high=104.0, low=100.0)
        _, flat_a = _assemble_reclaim_quality(ctx, _make_gate_result())
        flat_a["Reclaim_Quality_Pct"] = "POISONED"
        _, flat_b = _assemble_reclaim_quality(ctx, _make_gate_result())
        assert flat_b["Reclaim_Quality_Pct"] is None


# ===========================================================================
# 8. TestRLC001FlatKeyRegistration -- MAPPED_FLAT_KEYS membership
# ===========================================================================

class TestRLC001FlatKeyRegistration:
    """Spec §4.4: Reclaim_Quality_Pct registered for coverage audit."""

    def test_flat_key_in_mapped_flat_keys(self):
        # Load transform.py directly to avoid pulling stubs.
        spec = importlib.util.spec_from_file_location(
            "_rlc001_transform_under_test",
            os.path.join(_LAYERS_ROOT, "tbs_engine", "transform.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "Reclaim_Quality_Pct" in mod.MAPPED_FLAT_KEYS

    def test_flat_key_only_one_rlc_key(self):
        """Spec §4.1: only one backing flat key registered for RLC-001."""
        spec = importlib.util.spec_from_file_location(
            "_rlc001_transform_under_test_b",
            os.path.join(_LAYERS_ROOT, "tbs_engine", "transform.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rlc_keys = [k for k in mod.MAPPED_FLAT_KEYS
                    if k.startswith("Reclaim_Quality")]
        assert rlc_keys == ["Reclaim_Quality_Pct"]


# ===========================================================================
# 9. TestRLC001PositiveOnly -- absence-as-signal (CFL-001 precedent)
# ===========================================================================

class TestRLC001PositiveOnly:
    """Spec §2.2 + DQ-6: reclaim_quality key ABSENT (not None) on non-RECLAIM.

    Mirrors the call-site idiom in output.py:
        if _rlc_block is not None and action_summary.get('verdict') == 'VALID':
            action_summary['reclaim_quality'] = _rlc_block
    """

    def _simulate_attachment(self, ctx, gate_result, action_summary):
        """Mirror the output.py call-site conditional attachment idiom."""
        block, flat = _assemble_reclaim_quality(ctx, gate_result)
        metrics = {}
        metrics.update(flat)
        if block is not None and action_summary.get("verdict") == "VALID":
            action_summary["reclaim_quality"] = block
        return action_summary, metrics

    def test_absent_on_pullback(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="PULLBACK")
        action_summary = {"verdict": "VALID", "reason": "PULLBACK"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "reclaim_quality" not in _as
        with pytest.raises(KeyError):
            _as["reclaim_quality"]

    def test_absent_on_breakout(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="BREAKOUT")
        action_summary = {"verdict": "VALID", "reason": "BREAKOUT"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "reclaim_quality" not in _as
        with pytest.raises(KeyError):
            _as["reclaim_quality"]

    def test_absent_on_swing_breakout(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="SWING_BREAKOUT")
        action_summary = {"verdict": "VALID", "reason": "SWING_BREAKOUT"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "reclaim_quality" not in _as

    def test_absent_on_invalid(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="INVALID", entry_type="RECLAIM")
        action_summary = {"verdict": "INVALID", "reason": "RECLAIM WITHOUT REGIME"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "reclaim_quality" not in _as
        with pytest.raises(KeyError):
            _as["reclaim_quality"]

    def test_absent_on_wait(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="WAIT", entry_type="RECLAIM")
        action_summary = {"verdict": "WAIT", "reason": "TREND QUALITY"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "reclaim_quality" not in _as

    def test_absent_on_recovery_candidate(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="RECOVERY CANDIDATE", entry_type="RECLAIM")
        action_summary = {"verdict": "RECOVERY CANDIDATE",
                          "reason": "RECOVERY CANDIDATE"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "reclaim_quality" not in _as

    def test_absent_when_action_summary_overridden_to_invalid(self):
        """DD-2 EXIT / BKOUT-001 GAP-5 paths: gate_result.verdict==VALID,
        entry_type==RECLAIM, but action_summary.verdict overridden to INVALID.
        Per Spec §2.2 the sub-object MUST NOT emit.
        """
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="RECLAIM")
        # Simulate override: action_summary.verdict is INVALID despite gr.verdict==VALID.
        action_summary = {"verdict": "INVALID",
                          "reason": "EXIT_OVERRIDE"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "reclaim_quality" not in _as

    def test_flat_key_null_on_non_reclaim(self):
        """Spec §11.7: flat key is None (not absent, not zero) on non-RECLAIM."""
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="PULLBACK")
        action_summary = {"verdict": "VALID"}
        _, metrics = self._simulate_attachment(ctx, gr, action_summary)
        # Flat key is registered (present in metrics dict) but None-valued.
        assert "Reclaim_Quality_Pct" in metrics
        assert metrics["Reclaim_Quality_Pct"] is None


# ===========================================================================
# 10. TestRLC001ActionSummaryAttachment -- positive integration path
# ===========================================================================

class TestRLC001ActionSummaryAttachment:
    """Spec §5 Test 10: on VALID x RECLAIM, sub-object is attached and
    its `value` field equals the flat-key value (4dp consistent)."""

    def _simulate_attachment(self, ctx, gate_result, action_summary):
        block, flat = _assemble_reclaim_quality(ctx, gate_result)
        metrics = {}
        metrics.update(flat)
        if block is not None and action_summary.get("verdict") == "VALID":
            action_summary["reclaim_quality"] = block
        return action_summary, metrics

    def test_reclaim_quality_attached_on_valid_reclaim(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="RECLAIM")
        action_summary = {"verdict": "VALID", "reason": "RECLAIM", "entry_type": "RECLAIM"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "reclaim_quality" in _as
        assert _as["reclaim_quality"]["value"] == 0.75
        assert _as["reclaim_quality"]["condition"]["label"] == "STRONG_RECLAIM"

    def test_attached_value_matches_flat_key(self):
        ctx = _make_ctx(close=102.10, high=103.00, low=100.00)
        gr = _make_gate_result(verdict="VALID", entry_type="RECLAIM")
        action_summary = {"verdict": "VALID", "reason": "RECLAIM"}
        _as, metrics = self._simulate_attachment(ctx, gr, action_summary)
        # Spec §5 Test 10: sub-object .value == metrics[Reclaim_Quality_Pct]
        assert _as["reclaim_quality"]["value"] == metrics["Reclaim_Quality_Pct"]

    def test_attached_label_matches_band_for_value(self):
        ctx = _make_ctx(close=101.20, high=103.00, low=100.00)
        gr = _make_gate_result(verdict="VALID", entry_type="RECLAIM")
        action_summary = {"verdict": "VALID", "reason": "RECLAIM"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        # 0.40 -> WEAK band
        assert _as["reclaim_quality"]["condition"]["label"] == "WEAK_RECLAIM"

    def test_attached_thresholds_dict_present(self):
        ctx = _make_ctx(close=103.0, high=104.0, low=100.0)
        gr = _make_gate_result(verdict="VALID", entry_type="RECLAIM")
        action_summary = {"verdict": "VALID", "reason": "RECLAIM"}
        _as, _ = self._simulate_attachment(ctx, gr, action_summary)
        assert "thresholds" in _as["reclaim_quality"]
        assert _as["reclaim_quality"]["thresholds"]["strong_at_or_above"] == 0.75
