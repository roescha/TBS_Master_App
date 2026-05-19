"""RLY-001 -- Rally Age and Streak Primitive -- unit tests.

Spec: RLY001_Rally_Age_Streak_Primitive_Spec_v1_0.md (v1.0, S158)

Covers 10 test classes per spec §6.1 (~58 tests target):

     1. TestRLY001HelperCorrectness     (12) -- _compute_rally_state numeric correctness
     2. TestRLY001DefensiveBehaviour     (6) -- INSUFFICIENT_BARS / ATR_UNAVAILABLE / NAN_IN_WINDOW
     3. TestRLY001MaturityClassification(10) -- output-layer label thresholding
     4. TestRLY001OutputShape            (6) -- _assemble_rally_state schema
     5. TestRLY001FlatKeyRoundTrip       (4) -- 8 flat keys via _flatten/_unflatten
     6. TestRLY001IVRMatrix              (8) -- 4 regime x 2 maturity matrix lookup
     7. TestRLY001NotInGatesFile         (1) -- negative: no Rally_* in non-IVR gates
     8. TestRLY001VocabularyHygiene      (1) -- negative: no vocabulary collisions
     9. TestRLY001VerdictInvariance      (4) -- negative: gate returns PASS unconditionally
    10. TestRLY001ProfileMatrix          (6) -- D5 frame mapping (A/B/C primary+context)

Construction notes:
    - Direct module load (TEST-HRN-001 idempotent pattern) to avoid the
      tbs_engine.__init__ import-chain pulling in ib_insync.
    - Helper-isolation tests where possible (no full engine end-to-end);
      synthetic ctx via SimpleNamespace for output/gate-layer tests.
"""

import inspect
import os as _os
import sys
import importlib.util as _ilu
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Path setup + safe module loaders (TEST-HRN-001 idempotent pattern,
# mirrors test_bugr006_profile_b_brk_rr.py to avoid ib_insync via __init__).
# ---------------------------------------------------------------------------
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_LAYERS_ROOT = _os.path.abspath(_os.path.join(_HERE, "..", ".."))
_ENGINE_DIR = _os.path.join(_LAYERS_ROOT, "tbs_engine")

if _LAYERS_ROOT not in sys.path:
    sys.path.insert(0, _LAYERS_ROOT)


def _load_mod(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


if "tbs_engine" not in sys.modules:
    import types as _types_mod
    sys.modules["tbs_engine"] = _types_mod.ModuleType("tbs_engine")

_types = _load_mod("tbs_engine.types", _os.path.join(_ENGINE_DIR, "types.py"))
_helpers = _load_mod("tbs_engine.helpers", _os.path.join(_ENGINE_DIR, "helpers.py"))
_compute = _load_mod("tbs_engine.compute", _os.path.join(_ENGINE_DIR, "compute.py"))
_transform = _load_mod("tbs_engine.transform", _os.path.join(_ENGINE_DIR, "transform.py"))

# Stub tbs_engine.charts to skip the plotly dependency chain when loading
# output.py. output.py only references _build_focus_chart at runtime in the
# trigger/exit assembly path; not exercised by RLY-001 helper tests.
if "tbs_engine.charts" not in sys.modules:
    import types as _types_mod
    _charts_stub = _types_mod.ModuleType("tbs_engine.charts")
    _charts_stub._build_focus_chart = lambda *a, **kw: None
    _charts_stub._build_primary_chart = lambda *a, **kw: None
    _charts_stub._build_context_chart = lambda *a, **kw: None
    sys.modules["tbs_engine.charts"] = _charts_stub

try:
    _output = _load_mod("tbs_engine.output", _os.path.join(_ENGINE_DIR, "output.py"))
except Exception:
    _output = None

# gates.py imports tbs_engine.helpers and tbs_engine.types only -- load directly.
_gates = _load_mod("tbs_engine.gates", _os.path.join(_ENGINE_DIR, "gates.py"))

# --- Symbols under test ---
_compute_rally_state = _compute._compute_rally_state
_compute_rally_state_for_ctx = _compute._compute_rally_state_for_ctx
_classify_rally_maturity = _compute._classify_rally_maturity
RLY_WINDOW_BARS = _compute.RLY_WINDOW_BARS
RLY_MATURE_RATIO_THRESHOLD = _compute.RLY_MATURE_RATIO_THRESHOLD
RLY_MATURE_MAGNITUDE_ATR_THRESHOLD = _compute.RLY_MATURE_MAGNITUDE_ATR_THRESHOLD

_assemble_rally_state_group = _transform._assemble_rally_state_group
MAPPED_FLAT_KEYS = _transform.MAPPED_FLAT_KEYS

_RLY_MATURITY_MATRIX = _gates._RLY_MATURITY_MATRIX
_gate_volatility_regime = _gates._gate_volatility_regime

if _output is not None:
    _assemble_rally_state = _output._assemble_rally_state
else:
    _assemble_rally_state = None


# ---------------------------------------------------------------------------
# Helpers for synthetic close-series construction
# ---------------------------------------------------------------------------

def _series_from_ups(up_pattern, start=100.0, step=1.0):
    """Build a 16-bar (window+1) close series matching a 15-bar up-pattern.

    up_pattern: iterable of 15 booleans; True => close > prior_close.
    Returns a pd.Series of length 16 (bar 0 anchor + 15 in-window bars).
    """
    closes = [start]
    cur = start
    for is_up in up_pattern:
        cur = cur + step if is_up else cur - step
        closes.append(cur)
    return pd.Series(closes, dtype=float)


# ===========================================================================
# 1. TestRLY001HelperCorrectness (12 tests)
# ===========================================================================

class TestRLY001HelperCorrectness:
    """Spec §3.1 + §6.1: _compute_rally_state numeric correctness."""

    def test_full_streak_15_of_15(self):
        s = _series_from_ups([True] * 15)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        assert r["up_bar_count"] == 15
        assert r["ratio"] == pytest.approx(1.0)
        assert r["window_bars"] == 15
        assert "reason" not in r

    def test_zero_streak_0_of_15(self):
        s = _series_from_ups([False] * 15)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        assert r["up_bar_count"] == 0
        assert r["ratio"] == pytest.approx(0.0)

    def test_threshold_exact_10_of_15(self):
        s = _series_from_ups([True] * 10 + [False] * 5)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Context")
        assert r["up_bar_count"] == 10
        assert r["ratio"] == pytest.approx(10.0 / 15.0)
        assert r["ratio"] >= RLY_MATURE_RATIO_THRESHOLD

    def test_threshold_minus_one_9_of_15(self):
        s = _series_from_ups([True] * 9 + [False] * 6)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Context")
        assert r["up_bar_count"] == 9
        assert r["ratio"] < RLY_MATURE_RATIO_THRESHOLD

    def test_eight_of_fifteen_below_threshold(self):
        s = _series_from_ups([True] * 8 + [False] * 7)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        assert r["up_bar_count"] == 8
        assert r["ratio"] == pytest.approx(8.0 / 15.0)

    def test_strict_inequality_no_inside_bar_grace(self):
        # close == prior_close should NOT count as up-bar.
        # Build series: bars[0]=100, bars[1]=100 (flat), bars[2..15]=up
        closes = [100.0, 100.0] + [100.0 + (i + 1) for i in range(14)]
        s = pd.Series(closes, dtype=float)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        # 14 strict ups (bars 2..15), bar 1 is flat (close==prior).
        assert r["up_bar_count"] == 14

    def test_magnitude_atr_positive_rally(self):
        # close[-15]=100, close[-1]=130, atr=2.0 -> magnitude = 30/2 = 15.0
        s = pd.Series([100.0] + [100.0 + 2.0 * i for i in range(1, 16)], dtype=float)
        # build so close[-15]=100, close[-1]=130. Pattern: i=1..15
        # iloc -16 = 100 (the prior bar before window)
        # iloc -15 = 102 (window start)
        # iloc -1 = 130 (latest)
        r = _compute_rally_state(s, current_atr=2.0, frame_label="Primary")
        assert r["anchor_price"] == pytest.approx(102.0)
        assert r["current_price"] == pytest.approx(130.0)
        assert r["magnitude_atr"] == pytest.approx((130.0 - 102.0) / 2.0)

    def test_magnitude_atr_negative_rally(self):
        s = pd.Series([100.0 - 1.0 * i for i in range(17)], dtype=float)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        # All down. anchor > current => negative magnitude.
        assert r["magnitude_atr"] < 0
        assert r["up_bar_count"] == 0

    def test_anchor_current_atr_value_echo(self):
        s = _series_from_ups([True] * 15, start=200.0, step=2.0)
        r = _compute_rally_state(s, current_atr=3.5, frame_label="Primary")
        assert r["atr_value"] == pytest.approx(3.5)
        assert r["frame_label"] == "Primary"
        # anchor = bar 1 (after prior bar 0). bar 0 = 200; bar 1 = 202; bar 15 = 230.
        assert r["anchor_price"] == pytest.approx(202.0)
        assert r["current_price"] == pytest.approx(230.0)

    def test_window_bars_constant(self):
        s = _series_from_ups([True] * 15)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        assert r["window_bars"] == 15
        assert r["window_bars"] == RLY_WINDOW_BARS

    def test_helper_pure_no_side_effects_on_series(self):
        s = _series_from_ups([True] * 15)
        snapshot = list(s.values)
        _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        assert list(s.values) == snapshot

    def test_long_series_uses_only_last_window(self):
        # 100-bar all-down except final 16 bars which are all-up.
        downs = [100.0 - 0.5 * i for i in range(84)]
        ups_anchor = downs[-1]
        # Build the last 16 bars: 15 strict-up after the anchor (84-1=83 anchor, then 84..98 step up)
        ups = [ups_anchor + 0.5 * (i + 1) for i in range(16)]
        s = pd.Series(downs + ups, dtype=float)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        # The trailing 15-bar window-with-anchor sees only up-closes.
        assert r["up_bar_count"] == 15


# ===========================================================================
# 2. TestRLY001DefensiveBehaviour (6 tests)
# ===========================================================================

class TestRLY001DefensiveBehaviour:
    """Spec §3.1 defensive contract: defensive returns include 'reason'."""

    def test_insufficient_bars_short_series(self):
        s = pd.Series([100.0] * 5, dtype=float)
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        assert r["reason"] == "INSUFFICIENT_BARS"
        assert r["up_bar_count"] is None
        assert r["ratio"] is None
        assert r["magnitude_atr"] is None
        assert r["window_bars"] == RLY_WINDOW_BARS  # constant still echoed

    def test_insufficient_bars_none_series(self):
        r = _compute_rally_state(None, current_atr=1.0, frame_label="Primary")
        assert r["reason"] == "INSUFFICIENT_BARS"

    def test_atr_unavailable_none(self):
        s = _series_from_ups([True] * 15)
        r = _compute_rally_state(s, current_atr=None, frame_label="Primary")
        assert r["reason"] == "ATR_UNAVAILABLE"

    def test_atr_unavailable_zero(self):
        s = _series_from_ups([True] * 15)
        r = _compute_rally_state(s, current_atr=0.0, frame_label="Primary")
        assert r["reason"] == "ATR_UNAVAILABLE"

    def test_atr_unavailable_nan(self):
        s = _series_from_ups([True] * 15)
        r = _compute_rally_state(s, current_atr=float("nan"), frame_label="Primary")
        assert r["reason"] == "ATR_UNAVAILABLE"

    def test_nan_in_window(self):
        s = _series_from_ups([True] * 15)
        s.iloc[-3] = float("nan")
        r = _compute_rally_state(s, current_atr=1.0, frame_label="Primary")
        assert r["reason"] == "NAN_IN_WINDOW"


# ===========================================================================
# 3. TestRLY001MaturityClassification (10 tests)
# ===========================================================================

class TestRLY001MaturityClassification:
    """Spec §4.2: output-layer maturity-label thresholding."""

    def _ctx_result(self, ratio, mag):
        return {"ratio": ratio, "magnitude_atr": mag}

    def test_both_thresholds_clear_yields_rally_mature(self):
        r = self._ctx_result(11.0 / 15.0, 6.0)
        assert _classify_rally_maturity(r) == "RALLY_MATURE"

    def test_threshold_exact_ratio_clears(self):
        r = self._ctx_result(10.0 / 15.0, 5.0)
        # >= on both axes
        assert _classify_rally_maturity(r) == "RALLY_MATURE"

    def test_ratio_below_threshold_yields_normal(self):
        r = self._ctx_result(9.0 / 15.0, 6.0)
        assert _classify_rally_maturity(r) == "NORMAL"

    def test_magnitude_below_threshold_yields_normal(self):
        r = self._ctx_result(11.0 / 15.0, 4.9)
        assert _classify_rally_maturity(r) == "NORMAL"

    def test_both_below_threshold_yields_normal(self):
        r = self._ctx_result(8.0 / 15.0, 4.0)
        assert _classify_rally_maturity(r) == "NORMAL"

    def test_magnitude_threshold_exact_5_yields_rally_mature(self):
        r = self._ctx_result(12.0 / 15.0, 5.0)
        assert _classify_rally_maturity(r) == "RALLY_MATURE"

    def test_high_magnitude_low_ratio_yields_normal(self):
        r = self._ctx_result(5.0 / 15.0, 12.0)
        assert _classify_rally_maturity(r) == "NORMAL"

    def test_null_ratio_yields_none(self):
        r = self._ctx_result(None, 6.0)
        assert _classify_rally_maturity(r) is None

    def test_null_magnitude_yields_none(self):
        r = self._ctx_result(10.0 / 15.0, None)
        assert _classify_rally_maturity(r) is None

    def test_classify_uses_context_ratio_not_primary(self):
        # Verify the classifier reads 'ratio' (context.ratio per spec §3.3 note).
        r = self._ctx_result(11.0 / 15.0, 5.5)
        assert _classify_rally_maturity(r) == "RALLY_MATURE"


# ===========================================================================
# 4. TestRLY001OutputShape (6 tests)
# ===========================================================================

@pytest.mark.skipif(_assemble_rally_state is None,
                    reason="output.py could not be loaded (charts/plotly dependency)")
class TestRLY001OutputShape:
    """Spec §3.2: _assemble_rally_state block shape contract."""

    def _make_ctx(self, primary_dict, context_dict, label, price_scaler=1.0):
        return SimpleNamespace(
            _rly_primary=primary_dict,
            _rly_context=context_dict,
            _rly_maturity_label=label,
            price_scaler=price_scaler,
        )

    def _valid_primary(self, ratio=0.8, frame="hourly"):
        return {
            "up_bar_count": 12, "window_bars": 15, "ratio": ratio,
            "magnitude_atr": 4.0, "anchor_price": 100.0, "current_price": 120.0,
            "atr_value": 2.5, "frame_label": "Primary", "frame": frame,
        }

    def _valid_context(self, ratio=0.733, mag=6.0, frame="daily"):
        return {
            "up_bar_count": 11, "window_bars": 15, "ratio": ratio,
            "magnitude_atr": mag, "anchor_price": 410.55, "current_price": 437.20,
            "atr_value": 4.16, "frame_label": "Context", "frame": frame,
        }

    def test_rally_mature_block_has_four_sub_objects(self):
        ctx = self._make_ctx(self._valid_primary(), self._valid_context(), "RALLY_MATURE")
        block, flat = _assemble_rally_state(ctx, "A")
        assert block is not None
        assert set(block.keys()) == {"primary", "context", "magnitude", "maturity"}

    def test_primary_sub_object_schema(self):
        ctx = self._make_ctx(self._valid_primary(), self._valid_context(), "RALLY_MATURE")
        block, _ = _assemble_rally_state(ctx, "A")
        primary = block["primary"]
        assert set(primary.keys()) == {"up_bar_count", "window_bars", "ratio", "frame", "desc"}
        assert primary["up_bar_count"] == 12
        assert primary["window_bars"] == 15
        assert primary["frame"] == "hourly"

    def test_magnitude_sub_object_schema(self):
        ctx = self._make_ctx(self._valid_primary(), self._valid_context(), "RALLY_MATURE")
        block, _ = _assemble_rally_state(ctx, "A")
        mag = block["magnitude"]
        assert set(mag.keys()) == {"atr_widths", "anchor_price", "current_price", "atr_value", "desc"}
        assert mag["atr_widths"] == pytest.approx(6.0)

    def test_maturity_trigger_sub_object_schema_rally_mature(self):
        ctx = self._make_ctx(self._valid_primary(), self._valid_context(), "RALLY_MATURE")
        block, _ = _assemble_rally_state(ctx, "A")
        trigger = block["maturity"]["trigger"]
        expected_keys = {
            "context_ratio_threshold", "context_ratio_actual", "context_ratio_met",
            "magnitude_atr_threshold", "magnitude_atr_actual", "magnitude_atr_met",
            "both_met",
        }
        assert set(trigger.keys()) == expected_keys
        assert trigger["context_ratio_met"] is True
        assert trigger["magnitude_atr_met"] is True
        assert trigger["both_met"] is True
        assert block["maturity"]["label"] == "RALLY_MATURE"

    def test_normal_block_still_populated(self):
        # NORMAL: trigger sub-object exists with both_met=False
        normal_ctx = self._make_ctx(
            self._valid_primary(),
            self._valid_context(ratio=0.5, mag=3.0),  # neither threshold clears
            "NORMAL",
        )
        block, flat = _assemble_rally_state(normal_ctx, "B")
        assert block is not None
        assert block["maturity"]["label"] == "NORMAL"
        assert block["maturity"]["trigger"]["both_met"] is False

    def test_defensive_null_yields_none_block_and_null_flat_keys(self):
        defensive = {"reason": "INSUFFICIENT_BARS", "up_bar_count": None,
                     "window_bars": 15, "ratio": None, "magnitude_atr": None,
                     "anchor_price": None, "current_price": None, "atr_value": None,
                     "frame_label": "Context", "frame": "daily"}
        ctx = self._make_ctx(self._valid_primary(), defensive, None)
        block, flat = _assemble_rally_state(ctx, "A")
        assert block is None
        for k in ("Rally_Up_Bar_Count_Primary", "Rally_Up_Bar_Count_Context",
                  "Rally_Up_Bar_Ratio_Primary", "Rally_Up_Bar_Ratio_Context",
                  "Rally_Window_Bars", "Rally_Magnitude_ATR",
                  "Rally_Anchor_Price", "Rally_Maturity_Label"):
            assert flat[k] is None


# ===========================================================================
# 5. TestRLY001FlatKeyRoundTrip (4 tests)
# ===========================================================================

class TestRLY001FlatKeyRoundTrip:
    """Spec §6.1: 8 flat keys round-trip via _flatten/_unflatten via the
    grouped rally_state sub-object."""

    def test_eight_keys_registered_in_mapped_flat_keys(self):
        for k in (
            "Rally_Up_Bar_Count_Primary", "Rally_Up_Bar_Count_Context",
            "Rally_Up_Bar_Ratio_Primary", "Rally_Up_Bar_Ratio_Context",
            "Rally_Window_Bars", "Rally_Magnitude_ATR",
            "Rally_Anchor_Price", "Rally_Maturity_Label",
        ):
            assert k in MAPPED_FLAT_KEYS, f"flat key {k} not in MAPPED_FLAT_KEYS"

    def test_assemble_group_returns_none_when_label_null(self):
        block = _assemble_rally_state_group({
            "Rally_Maturity_Label": None,
            "Rally_Up_Bar_Count_Primary": 12,
            "Rally_Up_Bar_Count_Context": 11,
            "Rally_Up_Bar_Ratio_Primary": 0.8,
            "Rally_Up_Bar_Ratio_Context": 0.733,
            "Rally_Window_Bars": 15,
            "Rally_Magnitude_ATR": 6.0,
            "Rally_Anchor_Price": 410.55,
        })
        assert block is None

    def test_round_trip_rally_mature(self):
        flat_in = {
            "Rally_Maturity_Label": "RALLY_MATURE",
            "Rally_Up_Bar_Count_Primary": 12,
            "Rally_Up_Bar_Count_Context": 11,
            "Rally_Up_Bar_Ratio_Primary": 0.80,
            "Rally_Up_Bar_Ratio_Context": 0.73,
            "Rally_Window_Bars": 15,
            "Rally_Magnitude_ATR": 6.42,
            "Rally_Anchor_Price": 410.55,
            "Price": 437.20,
            "Floor_Anchor_Type": "EMA_21",  # Profile A
        }
        block = _assemble_rally_state_group(flat_in)
        assert block is not None
        # Reverse-map: simulate the _flatten extractor for rally_state.
        _re = {}
        _re["Rally_Up_Bar_Count_Primary"] = block["primary"]["up_bar_count"]
        _re["Rally_Up_Bar_Count_Context"] = block["context"]["up_bar_count"]
        _re["Rally_Up_Bar_Ratio_Primary"] = block["primary"]["ratio"]
        _re["Rally_Up_Bar_Ratio_Context"] = block["context"]["ratio"]
        _re["Rally_Window_Bars"] = block["primary"]["window_bars"]
        _re["Rally_Magnitude_ATR"] = block["magnitude"]["atr_widths"]
        _re["Rally_Anchor_Price"] = block["magnitude"]["anchor_price"]
        _re["Rally_Maturity_Label"] = block["maturity"]["label"]

        assert _re["Rally_Up_Bar_Count_Primary"] == 12
        assert _re["Rally_Up_Bar_Count_Context"] == 11
        assert _re["Rally_Window_Bars"] == 15
        assert _re["Rally_Maturity_Label"] == "RALLY_MATURE"
        # ratios/magnitudes can be re-rounded to 2dp on reconstruction.
        assert abs(_re["Rally_Up_Bar_Ratio_Primary"] - 0.80) < 0.01
        assert abs(_re["Rally_Magnitude_ATR"] - 6.42) < 0.01

    def test_round_trip_normal(self):
        flat_in = {
            "Rally_Maturity_Label": "NORMAL",
            "Rally_Up_Bar_Count_Primary": 6,
            "Rally_Up_Bar_Count_Context": 5,
            "Rally_Up_Bar_Ratio_Primary": 0.40,
            "Rally_Up_Bar_Ratio_Context": 0.33,
            "Rally_Window_Bars": 15,
            "Rally_Magnitude_ATR": 2.10,
            "Rally_Anchor_Price": 50.00,
            "Price": 52.10,
            "Floor_Anchor_Type": "SMA_50",  # Profile B
        }
        block = _assemble_rally_state_group(flat_in)
        assert block is not None
        assert block["maturity"]["label"] == "NORMAL"
        assert block["maturity"]["trigger"]["both_met"] is False


# ===========================================================================
# 6. TestRLY001IVRMatrix (8 tests)
# ===========================================================================

class TestRLY001IVRMatrix:
    """Spec §5.1 / §5.2: 4 regime x 2 maturity matrix lookup."""

    def _make_ctx(self, iv, hv, maturity_label, context_ratio, context_mag,
                  trigger=""):
        metrics = {"IV_Current": iv, "HV_30D": hv, "Trigger": trigger}
        return SimpleNamespace(
            metrics=metrics,
            _rly_maturity_label=maturity_label,
            _rly_context={"ratio": context_ratio, "magnitude_atr": context_mag},
            _recovery_base_result=None,
        )

    # --- 4 regimes x RALLY_MATURE = §4.5 active ---

    def test_complacent_rally_mature_emits_delayed_climax_risk(self):
        ctx = self._make_ctx(iv=14.0, hv=20.0, maturity_label="RALLY_MATURE",
                             context_ratio=11.0 / 15.0, context_mag=6.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "COMPLACENT"
        assert ctx.metrics["Volatility_Interpretation"] == "DELAYED CLIMAX RISK"
        assert ctx.metrics["Volatility_Caution_Factor"] is not None
        assert "DELAYED CLIMAX RISK" in ctx.metrics["Volatility_Caution_Factor"]
        # §5.2 deviation: COMPLACENT x RALLY_MATURE DOES emit caution_factor.

    def test_aligned_rally_mature_mature_trend_null_caution(self):
        ctx = self._make_ctx(iv=20.0, hv=20.0, maturity_label="RALLY_MATURE",
                             context_ratio=11.0 / 15.0, context_mag=6.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "ALIGNED"
        assert ctx.metrics["Volatility_Interpretation"] == "MATURE TREND"
        # §5.2: ALIGNED emits NO caution_factor.
        assert ctx.metrics["Volatility_Caution_Factor"] is None

    def test_elevated_rally_mature_emits_climax_risk(self):
        ctx = self._make_ctx(iv=28.0, hv=20.0, maturity_label="RALLY_MATURE",
                             context_ratio=11.0 / 15.0, context_mag=6.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "ELEVATED"
        assert ctx.metrics["Volatility_Interpretation"] == "CLIMAX RISK"
        assert ctx.metrics["Volatility_Caution_Factor"] is not None
        assert "CLIMAX RISK" in ctx.metrics["Volatility_Caution_Factor"]

    def test_extreme_rally_mature_emits_exhaustion_signal(self):
        ctx = self._make_ctx(iv=40.0, hv=20.0, maturity_label="RALLY_MATURE",
                             context_ratio=11.0 / 15.0, context_mag=6.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "EXTREME"
        assert ctx.metrics["Volatility_Interpretation"] == "EXHAUSTION SIGNAL"
        assert ctx.metrics["Volatility_Caution_Factor"] is not None
        assert "EXHAUSTION SIGNAL" in ctx.metrics["Volatility_Caution_Factor"]

    # --- 4 regimes x NORMAL = §4.5 inactive, existing §4.1-§4.4 lookup ---

    def test_complacent_normal_uses_existing_matrix(self):
        ctx = self._make_ctx(iv=14.0, hv=20.0, maturity_label="NORMAL",
                             context_ratio=5.0 / 15.0, context_mag=2.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "COMPLACENT"
        # §4.1/§4.2/§4.3/§4.4 default-context interpretation: NOT "DELAYED CLIMAX RISK".
        assert ctx.metrics["Volatility_Interpretation"] != "DELAYED CLIMAX RISK"
        # COMPLACENT in default context emits no caution (existing IVR convention).
        assert ctx.metrics["Volatility_Caution_Factor"] is None

    def test_aligned_normal_uses_existing_matrix(self):
        ctx = self._make_ctx(iv=20.0, hv=20.0, maturity_label="NORMAL",
                             context_ratio=5.0 / 15.0, context_mag=2.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "ALIGNED"
        assert ctx.metrics["Volatility_Interpretation"] != "MATURE TREND"

    def test_elevated_normal_uses_existing_matrix(self):
        ctx = self._make_ctx(iv=28.0, hv=20.0, maturity_label="NORMAL",
                             context_ratio=5.0 / 15.0, context_mag=2.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "ELEVATED"
        assert ctx.metrics["Volatility_Interpretation"] != "CLIMAX RISK"
        # Existing ELEVATED emits a (different) caution_factor per existing matrix.
        assert ctx.metrics["Volatility_Caution_Factor"] is not None
        assert "CLIMAX RISK" not in ctx.metrics["Volatility_Caution_Factor"]

    def test_extreme_normal_uses_existing_matrix(self):
        ctx = self._make_ctx(iv=40.0, hv=20.0, maturity_label="NORMAL",
                             context_ratio=5.0 / 15.0, context_mag=2.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "EXTREME"
        assert ctx.metrics["Volatility_Interpretation"] != "EXHAUSTION SIGNAL"


# ===========================================================================
# 7. TestRLY001NotInGatesFile (1 test, negative assertion)
# ===========================================================================

class TestRLY001NotInGatesFile:
    """Spec §6.1: RLY-001 is NOT a gate input on any gate other than the
    §4.5 caution_factor write inside _gate_volatility_regime."""

    def test_no_rally_references_in_other_gate_function_bodies(self):
        offenders = []
        for name in dir(_gates):
            if not name.startswith("_gate_"):
                continue
            if name == "_gate_volatility_regime":
                continue  # exempt: §4.5 lookup lives here by design
            obj = getattr(_gates, name)
            if not callable(obj):
                continue
            try:
                src = inspect.getsource(obj)
            except (TypeError, OSError):
                continue
            for token in ("Rally_", "RLY_", "_rly_"):
                if token in src:
                    offenders.append((name, token))
        assert not offenders, (
            f"RLY-001 vocabulary leaked into non-IVR gate functions: {offenders}"
        )


# ===========================================================================
# 8. TestRLY001VocabularyHygiene (1 test, negative assertion)
# ===========================================================================

class TestRLY001VocabularyHygiene:
    """Spec §6.1: New flat keys + §4.5 labels do not collide with existing
    engine vocabulary."""

    def test_no_collision_of_new_vocabulary(self):
        # The 8 flat keys are registered (positive containment) and the four
        # §4.5 interpretation labels appear only inside _RLY_MATURITY_MATRIX.
        rly_labels = {
            "DELAYED CLIMAX RISK", "MATURE TREND",
            "CLIMAX RISK", "EXHAUSTION SIGNAL",
        }
        existing_ivr_labels = set()
        for entry in _gates._IVR_INTERPRETATION.values():
            if isinstance(entry, dict) and "label" in entry:
                existing_ivr_labels.add(entry["label"])
        collisions = rly_labels & existing_ivr_labels
        assert not collisions, (
            f"§4.5 labels collide with existing IVR interpretation labels: {collisions}"
        )
        # Confirm matrix carries exactly the four documented regime keys.
        assert set(_RLY_MATURITY_MATRIX.keys()) == {
            "COMPLACENT", "ALIGNED", "ELEVATED", "EXTREME"
        }


# ===========================================================================
# 9. TestRLY001VerdictInvariance (4 tests, negative assertion)
# ===========================================================================

class TestRLY001VerdictInvariance:
    """Spec §6.1 + D7: _gate_volatility_regime returns PASS unconditionally
    across all 4 regime cells regardless of RALLY_MATURE state. Verdict
    impact is zero; only caution_factors[] differs per spec §5.2.

    The full pre/post fixture comparison lives in live-validation Phase 3.
    Here we verify the gate return contract (None == PASS in this engine)
    holds for the 8 regime x maturity combinations."""

    def _run(self, iv, hv, label):
        ctx = SimpleNamespace(
            metrics={"IV_Current": iv, "HV_30D": hv, "Trigger": ""},
            _rly_maturity_label=label,
            _rly_context={"ratio": 11.0 / 15.0, "magnitude_atr": 6.0},
            _recovery_base_result=None,
        )
        return _gate_volatility_regime(ctx)

    def test_complacent_returns_pass_both_maturities(self):
        assert self._run(14.0, 20.0, "RALLY_MATURE") is None
        assert self._run(14.0, 20.0, "NORMAL") is None
        assert self._run(14.0, 20.0, None) is None  # defensive null path

    def test_aligned_returns_pass_both_maturities(self):
        assert self._run(20.0, 20.0, "RALLY_MATURE") is None
        assert self._run(20.0, 20.0, "NORMAL") is None

    def test_elevated_returns_pass_both_maturities(self):
        assert self._run(28.0, 20.0, "RALLY_MATURE") is None
        assert self._run(28.0, 20.0, "NORMAL") is None

    def test_extreme_returns_pass_both_maturities(self):
        assert self._run(40.0, 20.0, "RALLY_MATURE") is None
        assert self._run(40.0, 20.0, "NORMAL") is None


# ===========================================================================
# 10. TestRLY001ProfileMatrix (6 tests)
# ===========================================================================

class TestRLY001ProfileMatrix:
    """Spec D5: A hourly/daily, B daily/weekly, C weekly/monthly frame map."""

    def _make_ctx(self, p_code, iq, df, df_ctx):
        cfg = SimpleNamespace(iq=iq)
        state = SimpleNamespace(atr_raw=1.0)
        return SimpleNamespace(
            p_code=p_code, cfg=cfg, state=state, df=df, _df_ctx=df_ctx,
            _rly_primary=None, _rly_context=None, _rly_maturity_label=None,
        )

    def _df_with_atr(self, n=30, start=100.0, step=1.0, atr=1.0):
        closes = [start + step * i for i in range(n)]
        df = pd.DataFrame({"close": closes, "ATRr_14": [atr] * n})
        return df

    def test_profile_a_frame_map(self):
        df = self._df_with_atr(n=30)
        df_ctx = self._df_with_atr(n=30)
        ctx = self._make_ctx("A", iq=-2, df=df, df_ctx=df_ctx)
        _compute_rally_state_for_ctx(ctx)
        assert ctx._rly_primary["frame"] == "hourly"
        assert ctx._rly_context["frame"] == "daily"

    def test_profile_b_frame_map(self):
        df = self._df_with_atr(n=30)
        df_ctx = self._df_with_atr(n=30)
        ctx = self._make_ctx("B", iq=-1, df=df, df_ctx=df_ctx)
        _compute_rally_state_for_ctx(ctx)
        assert ctx._rly_primary["frame"] == "daily"
        assert ctx._rly_context["frame"] == "weekly"

    def test_profile_c_frame_map(self):
        df = self._df_with_atr(n=30)
        df_ctx = self._df_with_atr(n=30)
        ctx = self._make_ctx("C", iq=-1, df=df, df_ctx=df_ctx)
        _compute_rally_state_for_ctx(ctx)
        assert ctx._rly_primary["frame"] == "weekly"
        assert ctx._rly_context["frame"] == "monthly"

    def test_profile_a_iq_minus_2_drops_in_progress_bar(self):
        # If iq=-2 isn't honoured, the rally would see one extra bar.
        # Build a series where bar -1 is anomalous (would change up_bar_count).
        n = 30
        closes = [100.0 + i for i in range(n - 1)] + [50.0]  # final bar plunges
        df = pd.DataFrame({"close": closes, "ATRr_14": [1.0] * n})
        df_ctx = self._df_with_atr(n=30)
        ctx = self._make_ctx("A", iq=-2, df=df, df_ctx=df_ctx)
        _compute_rally_state_for_ctx(ctx)
        # Primary window should NOT see the iloc[-1] plunge; up_bar_count
        # should reflect the strict-up trail of the preceding 15 bars.
        assert ctx._rly_primary["up_bar_count"] == 15

    def test_profile_c_insufficient_monthly_bars_yields_defensive(self):
        # PCM-001 partial-tier: monthly context with < 16 bars -> INSUFFICIENT_BARS.
        df = self._df_with_atr(n=30)
        df_ctx_short = self._df_with_atr(n=10)
        ctx = self._make_ctx("C", iq=-1, df=df, df_ctx=df_ctx_short)
        _compute_rally_state_for_ctx(ctx)
        assert ctx._rly_context.get("reason") == "INSUFFICIENT_BARS"
        assert ctx._rly_maturity_label is None

    def test_null_df_ctx_yields_defensive_context(self):
        df = self._df_with_atr(n=30)
        ctx = self._make_ctx("B", iq=-1, df=df, df_ctx=None)
        _compute_rally_state_for_ctx(ctx)
        assert ctx._rly_context.get("reason") == "INSUFFICIENT_BARS"
        assert ctx._rly_maturity_label is None
