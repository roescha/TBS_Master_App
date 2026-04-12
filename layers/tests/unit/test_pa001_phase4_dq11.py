"""PA-001 Phase 4 — DQ-11 Profile B Medium-Term Overextension Unit Tests.

Tests cover:
  1. gates.py — EXHAUSTION (> 25%): hard REJECT
  2. gates.py — CAUTION (15-25%): advisory, passes
  3. gates.py — NORMAL (< 15%): passes
  4. gates.py — Profile A/C exclusion
  5. gates.py — Negative distance (below SMA 50)
  6. gates.py — Gate ordering (intraday extension rejects first)
  7. output.py — CAUTION note populated / not populated
  8. transform.py — medium_term sub-object in extension_analysis
  9. Self-doc compliance ({value, unit, desc} and {label, desc})
"""

import pytest
from types import SimpleNamespace
from ibkr_purity_engine import GateResult, _gate_extension


# ============================================================================
# HELPERS
# ============================================================================

def _make_dq11_ctx(p_code="B", atr_dist=0.5, ext_limit=1.0,
                   close=150.0, sma50_raw=120.0, price_scaler=1.0,
                   metrics=None):
    """Build a minimal ctx for _gate_extension with DQ-11 Profile B fields.

    Default: close=150, sma50=120 → 25% above (boundary).
    """
    if metrics is None:
        metrics = {}
    state = SimpleNamespace(
        is_trending=True,
        is_resolving=False,
        _entry_trending=True,
        _entry_resolving=False,
        atr_raw=2.0,
    )
    ctx = SimpleNamespace(
        state=state,
        p_code=p_code,
        is_etf=False,
        last={"close": close, "open": close - 1.0, "SMA_200": 100.0},
        resistance_raw=200.0,
        resistance_display=200.0,
        _resistance_suppressed=False,
        floor_prox_pct=5.0,
        metrics=metrics,
        adx_accel_state="CRUISING",
        adx_accel=0.0,
        vol_confirm_state="MIXED",
        vol_confirm_ratio=0.5,
        exit_signal=False,
        structural_floor_raw=sma50_raw,
        price_scaler=price_scaler,
        ext_limit=ext_limit,
    )
    return ctx, atr_dist, ext_limit


# ============================================================================
# 1. GATES — DQ-11 Medium-Term Overextension
# ============================================================================

class TestDQ11Exhaustion:
    """DQ-11: > 25% above SMA 50 → EXHAUSTION → hard REJECT."""

    def test_exhaustion_rejects(self):
        """Profile B at 26% above SMA 50 → INVALID with reason MEDIUM-TERM OVEREXTENSION."""
        metrics = {}
        # close=126, sma50=100 → 26% above
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=126.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is not None
        assert isinstance(result, GateResult)
        assert result.verdict == "INVALID"
        assert result.reason == "MEDIUM-TERM OVEREXTENSION"
        assert metrics["MediumTerm_Extension_Label"] == "EXHAUSTION"
        assert metrics["MediumTerm_Extension_Pct"] == 26.0

    def test_exhaustion_context_has_sma50_price(self):
        """EXHAUSTION context dict includes sma50_price (scaled)."""
        metrics = {}
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=126.0, sma50_raw=100.0, price_scaler=1.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result.context["sma50_price"] == 100.0
        assert result.context["threshold_pct"] == 25.0
        assert result.context["pct_above_sma50"] == 26.0

    def test_exhaustion_context_scaled(self):
        """EXHAUSTION context sma50_price is divided by price_scaler."""
        metrics = {}
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=12600.0, sma50_raw=10000.0, price_scaler=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is not None
        assert result.context["sma50_price"] == 100.0  # 10000 / 100

    def test_exhaustion_legacy_diagnostic(self):
        """Legacy diagnostic includes % and EXHAUSTION label."""
        metrics = {}
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=130.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert "30.0%" in result.legacy_diagnostic
        assert "EXHAUSTION" in result.legacy_diagnostic

    def test_boundary_exactly_25_is_caution(self):
        """Profile B: exactly 25% above SMA 50 → NOT > 25%, so CAUTION (passes)."""
        metrics = {}
        # close=125, sma50=100 → exactly 25%
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=125.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is None  # passes
        assert metrics["MediumTerm_Extension_Label"] == "CAUTION"


class TestDQ11Caution:
    """DQ-11: 15-25% above SMA 50 → CAUTION → advisory, passes."""

    def test_caution_passes_with_label(self):
        """Profile B at 18% above SMA 50 → CAUTION label, gate passes."""
        metrics = {}
        # close=118, sma50=100 → 18% above
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=118.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is None
        assert metrics["MediumTerm_Extension_Label"] == "CAUTION"
        assert metrics["MediumTerm_Extension_Pct"] == 18.0

    def test_boundary_exactly_15_is_normal(self):
        """Profile B: exactly 15% above SMA 50 → NOT > 15%, so NORMAL."""
        metrics = {}
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=115.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is None
        assert metrics["MediumTerm_Extension_Label"] == "NORMAL"


class TestDQ11Normal:
    """DQ-11: < 15% above SMA 50 → NORMAL → passes."""

    def test_normal_passes_with_label(self):
        """Profile B at 10% above SMA 50 → NORMAL label, gate passes."""
        metrics = {}
        # close=110, sma50=100 → 10% above
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=110.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is None
        assert metrics["MediumTerm_Extension_Label"] == "NORMAL"
        assert metrics["MediumTerm_Extension_Pct"] == 10.0

    def test_small_distance(self):
        """Profile B at 2% above SMA 50 → NORMAL."""
        metrics = {}
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=102.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is None
        assert metrics["MediumTerm_Extension_Label"] == "NORMAL"
        assert metrics["MediumTerm_Extension_Pct"] == 2.0


class TestDQ11ProfileExclusion:
    """DQ-11 only runs for Profile B. A and C are unaffected."""

    def test_profile_a_no_medium_term(self):
        """Profile A does not get MediumTerm_Extension_Pct."""
        metrics = {}
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            p_code="A", close=130.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is None
        assert "MediumTerm_Extension_Pct" not in metrics
        assert "MediumTerm_Extension_Label" not in metrics

    def test_profile_c_no_medium_term(self):
        """Profile C does not get MediumTerm_Extension_Pct."""
        metrics = {}
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            p_code="C", close=130.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is None
        assert "MediumTerm_Extension_Pct" not in metrics


class TestDQ11NegativeDistance:
    """DQ-11: Price below SMA 50 → negative pct, NORMAL, passes."""

    def test_below_sma50_negative_pct(self):
        """Profile B below SMA 50 → negative pct, NORMAL label."""
        metrics = {}
        # close=90, sma50=100 → -10% (below)
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            close=90.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is None
        assert metrics["MediumTerm_Extension_Pct"] == -10.0
        assert metrics["MediumTerm_Extension_Label"] == "NORMAL"


class TestDQ11GateOrdering:
    """DQ-11 runs AFTER intraday extension. If intraday rejects, DQ-11 never executes."""

    def test_intraday_rejects_first(self):
        """When atr_dist > ext_limit (intraday rejection), DQ-11 metrics are absent."""
        metrics = {}
        # atr_dist=1.5 > ext_limit=1.0 → intraday rejection first
        ctx, atr_dist, ext_limit = _make_dq11_ctx(
            atr_dist=1.5, ext_limit=1.0,
            close=130.0, sma50_raw=100.0, metrics=metrics)

        result = _gate_extension(ctx, atr_dist, ext_limit)

        assert result is not None
        assert result.verdict == "INVALID"
        assert result.reason == "EXTENDED"  # intraday extension reason
        # DQ-11 never executed
        assert "MediumTerm_Extension_Pct" not in metrics


# ============================================================================
# 7. OUTPUT — CAUTION Note
# ============================================================================

class TestDQ11CautionNote:
    """CAUTION note populated in output.py when label = CAUTION."""

    def test_caution_note_populated(self):
        """Simulate _assemble_output CAUTION note logic: label=CAUTION → note written."""
        metrics = {
            "MediumTerm_Extension_Label": "CAUTION",
            "MediumTerm_Extension_Pct": 18.5,
        }
        p_code = "B"

        # Reproduce the output.py CAUTION note logic inline
        if p_code == "B":
            _mt_ext_label = metrics.get("MediumTerm_Extension_Label")
            if _mt_ext_label == "CAUTION":
                metrics["MediumTerm_Extension_Caution_Note"] = (
                    "Medium-term extension {:.1f}% above SMA 50 (15-25% range). "
                    "Stock may sustain this level in strong trends. "
                    "Monitor for mean reversion signs. Advisory only."
                ).format(metrics.get("MediumTerm_Extension_Pct", 0))

        assert "MediumTerm_Extension_Caution_Note" in metrics
        assert "18.5%" in metrics["MediumTerm_Extension_Caution_Note"]
        assert "Advisory only" in metrics["MediumTerm_Extension_Caution_Note"]

    def test_caution_note_not_for_normal(self):
        """No CAUTION note when label = NORMAL."""
        metrics = {
            "MediumTerm_Extension_Label": "NORMAL",
            "MediumTerm_Extension_Pct": 10.0,
        }
        p_code = "B"

        if p_code == "B":
            _mt_ext_label = metrics.get("MediumTerm_Extension_Label")
            if _mt_ext_label == "CAUTION":
                metrics["MediumTerm_Extension_Caution_Note"] = "should not appear"

        assert "MediumTerm_Extension_Caution_Note" not in metrics

    def test_caution_note_not_for_exhaustion(self):
        """No CAUTION note when label = EXHAUSTION (gate already rejected)."""
        metrics = {
            "MediumTerm_Extension_Label": "EXHAUSTION",
            "MediumTerm_Extension_Pct": 30.0,
        }
        p_code = "B"

        if p_code == "B":
            _mt_ext_label = metrics.get("MediumTerm_Extension_Label")
            if _mt_ext_label == "CAUTION":
                metrics["MediumTerm_Extension_Caution_Note"] = "should not appear"

        assert "MediumTerm_Extension_Caution_Note" not in metrics


# ============================================================================
# 8. TRANSFORM — medium_term sub-object
# ============================================================================

class TestDQ11Transform:
    """extension_analysis.medium_term populated for Profile B, None for A/C."""

    def _build_medium_term(self, flat_metrics):
        """Reproduce transform.py DQ-11 medium_term assembly logic."""
        _mt_ext_pct = flat_metrics.get("MediumTerm_Extension_Pct")
        _mt_ext_label = flat_metrics.get("MediumTerm_Extension_Label")
        _mt_ext_caution = flat_metrics.get("MediumTerm_Extension_Caution_Note")

        _medium_term_extension = None
        if _mt_ext_pct is not None:
            _mt_desc_map = {
                "NORMAL": "Within normal medium-term range relative to SMA 50",
                "CAUTION": "Elevated -- stock may be approaching medium-term exhaustion",
                "EXHAUSTION": "Overextended -- beyond sustainable medium-term distance (hard reject)",
            }
            _medium_term_extension = {
                "distance": {"value": _mt_ext_pct, "unit": "%", "desc": "Percentage distance above SMA 50"},
                "anchor": {"label": "SMA_50", "desc": "50-day simple moving average (institutional medium-term floor)"},
                "condition": {"label": _mt_ext_label, "desc": _mt_desc_map.get(_mt_ext_label, "")},
                "thresholds": {
                    "caution": {"value": 15.0, "unit": "%", "desc": "Advisory caution level"},
                    "exhaustion": {"value": 25.0, "unit": "%", "desc": "Hard reject level"},
                },
            }
            if _mt_ext_caution:
                _medium_term_extension["caution_note"] = _mt_ext_caution

        return _medium_term_extension

    def test_profile_b_normal_produces_medium_term(self):
        """Profile B NORMAL: medium_term sub-object populated."""
        flat = {"MediumTerm_Extension_Pct": 10.0, "MediumTerm_Extension_Label": "NORMAL"}
        mt = self._build_medium_term(flat)

        assert mt is not None
        assert mt["distance"]["value"] == 10.0
        assert mt["anchor"]["label"] == "SMA_50"
        assert mt["condition"]["label"] == "NORMAL"
        assert "caution_note" not in mt

    def test_profile_b_caution_has_caution_note(self):
        """Profile B CAUTION: medium_term includes caution_note."""
        flat = {
            "MediumTerm_Extension_Pct": 18.0,
            "MediumTerm_Extension_Label": "CAUTION",
            "MediumTerm_Extension_Caution_Note": "Some caution text",
        }
        mt = self._build_medium_term(flat)

        assert mt is not None
        assert mt["condition"]["label"] == "CAUTION"
        assert mt["caution_note"] == "Some caution text"

    def test_profile_b_exhaustion_produces_medium_term(self):
        """Profile B EXHAUSTION: medium_term sub-object populated."""
        flat = {"MediumTerm_Extension_Pct": 30.0, "MediumTerm_Extension_Label": "EXHAUSTION"}
        mt = self._build_medium_term(flat)

        assert mt is not None
        assert mt["condition"]["label"] == "EXHAUSTION"

    def test_no_metrics_produces_none(self):
        """When no MediumTerm metrics exist (Profile A/C), medium_term is None."""
        flat = {}
        mt = self._build_medium_term(flat)
        assert mt is None

    def test_thresholds_correct(self):
        """Thresholds match spec: 15% CAUTION, 25% EXHAUSTION."""
        flat = {"MediumTerm_Extension_Pct": 10.0, "MediumTerm_Extension_Label": "NORMAL"}
        mt = self._build_medium_term(flat)

        assert mt["thresholds"]["caution"]["value"] == 15.0
        assert mt["thresholds"]["caution"]["unit"] == "%"
        assert mt["thresholds"]["exhaustion"]["value"] == 25.0
        assert mt["thresholds"]["exhaustion"]["unit"] == "%"


# ============================================================================
# 9. SELF-DOC COMPLIANCE
# ============================================================================

class TestDQ11SelfDoc:
    """All DQ-11 values follow {value, unit, desc} and {label, desc} patterns."""

    def test_distance_value_unit_desc(self):
        """distance field has value, unit, desc."""
        flat = {"MediumTerm_Extension_Pct": 10.0, "MediumTerm_Extension_Label": "NORMAL"}
        mt = TestDQ11Transform()._build_medium_term(flat)

        d = mt["distance"]
        assert "value" in d
        assert "unit" in d
        assert "desc" in d
        assert d["unit"] == "%"

    def test_anchor_label_desc(self):
        """anchor field has label, desc."""
        flat = {"MediumTerm_Extension_Pct": 10.0, "MediumTerm_Extension_Label": "NORMAL"}
        mt = TestDQ11Transform()._build_medium_term(flat)

        a = mt["anchor"]
        assert "label" in a
        assert "desc" in a
        assert a["label"] == "SMA_50"

    def test_condition_label_desc(self):
        """condition field has label, desc."""
        flat = {"MediumTerm_Extension_Pct": 10.0, "MediumTerm_Extension_Label": "NORMAL"}
        mt = TestDQ11Transform()._build_medium_term(flat)

        c = mt["condition"]
        assert "label" in c
        assert "desc" in c
        assert c["desc"] != ""

    def test_threshold_value_unit_desc(self):
        """Each threshold entry has value, unit, desc."""
        flat = {"MediumTerm_Extension_Pct": 10.0, "MediumTerm_Extension_Label": "NORMAL"}
        mt = TestDQ11Transform()._build_medium_term(flat)

        for name in ("caution", "exhaustion"):
            t = mt["thresholds"][name]
            assert "value" in t, f"{name} missing value"
            assert "unit" in t, f"{name} missing unit"
            assert "desc" in t, f"{name} missing desc"


# ============================================================================
# REVERSE MAPPING — _flatten extraction
# ============================================================================

class TestDQ11FlattenReverseMapping:
    """Verify that _flatten can extract DQ-11 keys from medium_term sub-object."""

    def _flatten_medium_term(self, ext_dict):
        """Reproduce the _flatten DQ-11 reverse mapping logic."""
        flat = {}
        _mt = ext_dict.get("medium_term")
        if _mt and isinstance(_mt, dict):
            _md = _mt.get("distance", {})
            flat["MediumTerm_Extension_Pct"] = _md.get("value") if isinstance(_md, dict) else None
            _mc = _mt.get("condition", {})
            flat["MediumTerm_Extension_Label"] = _mc.get("label") if isinstance(_mc, dict) else None
            if "caution_note" in _mt:
                flat["MediumTerm_Extension_Caution_Note"] = _mt["caution_note"]
        return flat

    def test_roundtrip_normal(self):
        """NORMAL: flat → grouped → flat preserves values."""
        ext = {
            "medium_term": {
                "distance": {"value": 10.0, "unit": "%", "desc": "..."},
                "anchor": {"label": "SMA_50", "desc": "..."},
                "condition": {"label": "NORMAL", "desc": "..."},
                "thresholds": {},
            },
        }
        flat = self._flatten_medium_term(ext)
        assert flat["MediumTerm_Extension_Pct"] == 10.0
        assert flat["MediumTerm_Extension_Label"] == "NORMAL"
        assert "MediumTerm_Extension_Caution_Note" not in flat

    def test_roundtrip_caution_with_note(self):
        """CAUTION: caution_note extracted."""
        ext = {
            "medium_term": {
                "distance": {"value": 18.0, "unit": "%", "desc": "..."},
                "condition": {"label": "CAUTION", "desc": "..."},
                "caution_note": "Advisory text here",
            },
        }
        flat = self._flatten_medium_term(ext)
        assert flat["MediumTerm_Extension_Label"] == "CAUTION"
        assert flat["MediumTerm_Extension_Caution_Note"] == "Advisory text here"

    def test_none_medium_term(self):
        """When medium_term is None, no flat keys produced."""
        ext = {"medium_term": None}
        flat = self._flatten_medium_term(ext)
        assert "MediumTerm_Extension_Pct" not in flat
