"""IVR-001: IV/HV Volatility Regime Context — Unit Tests.

Covers:
  T01-T04:  All 4 regime bands (COMPLACENT, ALIGNED, ELEVATED, EXTREME)
  T05-T06:  UNAVAILABLE paths (IV null, HV null, HV zero)
  T07-T10:  All 5 context interpretations × at least 1 regime each
  T11-T12:  High-HV and low-HV stock cases
  T13-T15:  Boundary values exactly (0.8, 1.2, 1.5)
  T16:      VALID path with ALIGNED
  T17:      INVALID path with EXTREME — Tier 3 parallel confirmation
  T18:      ETF evaluation
  T20:      Regression (existing test compatibility — separate)

Spec: IVR001_Volatility_Regime_Context_Spec_v1_0
"""

import pytest
from types import SimpleNamespace

from tbs_engine.gates import (
    _gate_volatility_regime,
    IVR_COMPLACENT_THRESHOLD,
    IVR_ELEVATED_THRESHOLD,
    IVR_EXTREME_THRESHOLD,
    _IVR_REGIME_DESC,
    _IVR_INTERPRETATION,
)
from tbs_engine.transform import _transform_output, MAPPED_FLAT_KEYS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_ctx(iv=None, hv=None, engine_state="TRENDING", trigger="",
              daily_ext_label=None, recovery_active=False, extra_metrics=None):
    """Build a minimal RunContext-like namespace for _gate_volatility_regime."""
    metrics = {
        "IV_Current": iv,
        "HV_30D": hv,
        "Engine_State": engine_state,
        "Trigger": trigger,
    }
    if daily_ext_label:
        metrics["Daily_Extension_Label"] = daily_ext_label
    if extra_metrics:
        metrics.update(extra_metrics)

    ctx = SimpleNamespace(
        metrics=metrics,
        _recovery_base_result={"base_confirmed": True} if recovery_active else None,
    )
    return ctx


# ── T01-T04: All 4 regime bands ─────────────────────────────────────────────

class TestRegimeBands:
    """Spec §3.3: Regime classification from IV/HV ratio."""

    def test_t01_complacent_regime(self):
        """T01: IV=18%, HV=25%, ratio=0.72 → COMPLACENT. No caution factor."""
        ctx = _make_ctx(iv=18.0, hv=25.0)
        result = _gate_volatility_regime(ctx)
        assert result is None  # PASS unconditionally
        m = ctx.metrics
        assert m["Volatility_Regime"] == "COMPLACENT"
        assert abs(m["IV_HV_Ratio"] - 0.72) < 0.01
        assert m["Volatility_Caution_Factor"] is None

    def test_t02_aligned_regime(self):
        """T02: IV=33%, HV=30%, ratio=1.10 → ALIGNED. No caution factor."""
        ctx = _make_ctx(iv=33.0, hv=30.0)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "ALIGNED"
        assert abs(m["IV_HV_Ratio"] - 1.1) < 0.01
        assert m["Volatility_Caution_Factor"] is None

    def test_t03_elevated_regime(self):
        """T03: IV=42%, HV=30%, ratio=1.40 → ELEVATED. Caution factor present."""
        ctx = _make_ctx(iv=42.0, hv=30.0)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "ELEVATED"
        assert abs(m["IV_HV_Ratio"] - 1.4) < 0.01
        assert m["Volatility_Caution_Factor"] is not None
        assert "VOLATILITY REGIME: ELEVATED" in m["Volatility_Caution_Factor"]

    def test_t04_extreme_regime(self):
        """T04: IV=55%, HV=30%, ratio=1.83 → EXTREME. Caution factor present."""
        ctx = _make_ctx(iv=55.0, hv=30.0)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "EXTREME"
        assert abs(m["IV_HV_Ratio"] - 1.8333) < 0.01
        assert m["Volatility_Caution_Factor"] is not None
        assert "VOLATILITY REGIME: EXTREME" in m["Volatility_Caution_Factor"]


# ── T05-T06: UNAVAILABLE paths ──────────────────────────────────────────────

class TestUnavailable:
    """Spec §5.4: Graceful degradation when data is missing."""

    def test_t05_iv_null(self):
        """T05: IV=null, HV=25% → UNAVAILABLE. All fields null. No caution."""
        ctx = _make_ctx(iv=None, hv=25.0)
        result = _gate_volatility_regime(ctx)
        assert result is None  # PASS
        m = ctx.metrics
        assert m["Volatility_Regime"] == "UNAVAILABLE"
        assert m["IV_HV_Ratio"] is None
        assert m["Volatility_Interpretation"] is None
        assert m["Volatility_Caution_Factor"] is None

    def test_t06_hv_zero(self):
        """T06: IV=30%, HV=0% → UNAVAILABLE (division by zero guarded)."""
        ctx = _make_ctx(iv=30.0, hv=0)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "UNAVAILABLE"
        assert m["IV_HV_Ratio"] is None

    def test_hv_null(self):
        """HV=None, IV present → UNAVAILABLE."""
        ctx = _make_ctx(iv=30.0, hv=None)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "UNAVAILABLE"

    def test_both_null(self):
        """Both IV and HV null → UNAVAILABLE."""
        ctx = _make_ctx(iv=None, hv=None)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "UNAVAILABLE"


# ── T07-T10: Context interpretation matrix ───────────────────────────────────

class TestContextInterpretation:
    """Spec §4: All 5 contexts × at least 1 regime each."""

    def test_t07_complacent_at_breakout(self):
        """T07: COMPLACENT + BREAKOUT → HIGH QUALITY BREAKOUT."""
        ctx = _make_ctx(iv=18.0, hv=25.0, trigger="BREAKOUT")
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Interpretation"] == "HIGH QUALITY BREAKOUT"

    def test_t08_extreme_at_extension_caution(self):
        """T08: EXTREME + extension CAUTION → DANGER AT EXTENSION. Caution factor."""
        ctx = _make_ctx(iv=55.0, hv=30.0, daily_ext_label="CAUTION")
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Interpretation"] == "DANGER AT EXTENSION"
        assert m["Volatility_Caution_Factor"] is not None
        assert "DANGER AT EXTENSION" in m["Volatility_Caution_Factor"]

    def test_t09_elevated_at_pullback(self):
        """T09: ELEVATED + PULLBACK → CAPITULATION SUPPORT."""
        ctx = _make_ctx(iv=42.0, hv=30.0, trigger="PULLBACK")
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Interpretation"] == "CAPITULATION SUPPORT"

    def test_t10_extreme_at_recovery(self):
        """T10: EXTREME + recovery active → MAXIMUM ASYMMETRY."""
        ctx = _make_ctx(iv=55.0, hv=30.0, recovery_active=True)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Interpretation"] == "MAXIMUM ASYMMETRY"

    def test_default_trending_aligned(self):
        """Default trending + ALIGNED → STANDARD REGIME."""
        ctx = _make_ctx(iv=33.0, hv=30.0, engine_state="TRENDING")
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Interpretation"] == "STANDARD REGIME"

    def test_swing_breakout_trigger(self):
        """SWING_BREAKOUT trigger routes to BREAKOUT context."""
        ctx = _make_ctx(iv=33.0, hv=30.0, trigger="SWING_BREAKOUT")
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Interpretation"] == "ORDERLY BREAKOUT"

    def test_extension_exhaustion(self):
        """Extension EXHAUSTION routes to EXTENSION context."""
        ctx = _make_ctx(iv=42.0, hv=30.0, daily_ext_label="EXHAUSTION")
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Interpretation"] == "REVERSAL RISK AT EXTENSION"


# ── T11-T12: High-HV and low-HV stock cases ─────────────────────────────────

class TestAbsoluteVolatility:
    """Ratio-based assessment handles extreme absolute HV values correctly."""

    def test_t11_high_hv_stock(self):
        """T11: IV=118%, HV=109%, ratio=1.08 → ALIGNED despite high absolute vol."""
        ctx = _make_ctx(iv=118.0, hv=109.0)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "ALIGNED"
        assert abs(m["IV_HV_Ratio"] - 1.0826) < 0.01

    def test_t12_low_hv_stock(self):
        """T12: IV=22%, HV=15%, ratio=1.47 → ELEVATED. 7-point spread is significant."""
        ctx = _make_ctx(iv=22.0, hv=15.0)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "ELEVATED"
        assert abs(m["IV_HV_Ratio"] - 1.4667) < 0.01


# ── T13-T15: Boundary values ────────────────────────────────────────────────

class TestBoundaries:
    """Spec §3.4: Exact boundary values."""

    def test_t13_boundary_exactly_0_8(self):
        """T13: ratio=0.80 → ALIGNED (0.8 is inclusive lower bound of ALIGNED)."""
        # IV/HV = 0.80 → IV = 0.80 * HV. With HV=25: IV=20
        ctx = _make_ctx(iv=20.0, hv=25.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "ALIGNED"
        assert ctx.metrics["IV_HV_Ratio"] == 0.8

    def test_t14_boundary_exactly_1_2(self):
        """T14: ratio=1.20 → ELEVATED (1.2 is inclusive lower bound of ELEVATED)."""
        ctx = _make_ctx(iv=30.0, hv=25.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "ELEVATED"
        assert ctx.metrics["IV_HV_Ratio"] == 1.2

    def test_t15_boundary_exactly_1_5(self):
        """T15: ratio=1.50 → EXTREME (1.5 is inclusive lower bound of EXTREME)."""
        ctx = _make_ctx(iv=37.5, hv=25.0)
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "EXTREME"
        assert ctx.metrics["IV_HV_Ratio"] == 1.5

    def test_just_below_0_8(self):
        """ratio=0.799 → COMPLACENT (below 0.8)."""
        ctx = _make_ctx(iv=19.975, hv=25.0)  # 19.975/25 = 0.799
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "COMPLACENT"

    def test_just_below_1_2(self):
        """ratio=1.199 → ALIGNED (below 1.2)."""
        ctx = _make_ctx(iv=29.975, hv=25.0)  # 29.975/25 = 1.199
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "ALIGNED"

    def test_just_below_1_5(self):
        """ratio=1.499 → ELEVATED (below 1.5)."""
        ctx = _make_ctx(iv=37.475, hv=25.0)  # 37.475/25 = 1.499
        _gate_volatility_regime(ctx)
        assert ctx.metrics["Volatility_Regime"] == "ELEVATED"


# ── T16-T17: VALID/INVALID path integration ─────────────────────────────────

class TestPathIntegration:
    """Spec §5.1: Tier 3 parallel execution on both paths."""

    def test_t16_valid_path_aligned(self):
        """T16: VALID verdict + ALIGNED → volatility_regime populated, no caution."""
        ctx = _make_ctx(iv=26.25, hv=25.0)  # ratio ~1.05
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "ALIGNED"
        assert m["Volatility_Caution_Factor"] is None
        # All fields populated
        assert m["IV_Current"] == 26.25
        assert m["HV_30D"] == 25.0
        assert m["IV_HV_Ratio"] is not None

    def test_t17_invalid_path_extreme(self):
        """T17: Simulated INVALID path + EXTREME → metrics still written (Tier 3 parallel)."""
        ctx = _make_ctx(iv=45.0, hv=25.0, daily_ext_label="EXHAUSTION")  # ratio=1.8
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "EXTREME"
        assert m["Volatility_Caution_Factor"] is not None
        # EXTENSION context because EXHAUSTION
        assert m["Volatility_Interpretation"] == "DANGER AT EXTENSION"


# ── T18: ETF evaluation ─────────────────────────────────────────────────────

class TestETF:
    """Spec §7.2: Profile-independent computation confirmed for ETF."""

    def test_t18_etf_evaluation(self):
        """T18: SPY-like ETF, IV=15%, HV=12% → ELEVATED. Profile-independent."""
        ctx = _make_ctx(iv=15.0, hv=12.0)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "ELEVATED"
        assert abs(m["IV_HV_Ratio"] - 1.25) < 0.01


# ── Gate always returns PASS ─────────────────────────────────────────────────

class TestAdvisoryOnly:
    """Spec §5.2, Vocabulary §10: Gate NEVER returns HALT or REJECT."""

    def test_returns_none_complacent(self):
        assert _gate_volatility_regime(_make_ctx(iv=18.0, hv=25.0)) is None

    def test_returns_none_extreme(self):
        assert _gate_volatility_regime(_make_ctx(iv=55.0, hv=30.0)) is None

    def test_returns_none_unavailable(self):
        assert _gate_volatility_regime(_make_ctx(iv=None, hv=None)) is None

    def test_no_forbidden_vocabulary_in_metrics(self):
        """No output string contains REJECT, HALT, BLOCK, GATE FAILURE, or INVALID."""
        for regime in ("COMPLACENT", "ALIGNED", "ELEVATED", "EXTREME"):
            # Manufacture inputs that produce each regime
            ratios = {"COMPLACENT": (15, 25), "ALIGNED": (28, 25), "ELEVATED": (35, 25), "EXTREME": (50, 25)}
            iv, hv = ratios[regime]
            ctx = _make_ctx(iv=float(iv), hv=float(hv))
            _gate_volatility_regime(ctx)
            for k, v in ctx.metrics.items():
                if k.startswith("Volatility_") and isinstance(v, str):
                    for forbidden in ("REJECT", "HALT", "BLOCK", "GATE FAILURE", "INVALID"):
                        assert forbidden not in v, f"Forbidden word '{forbidden}' found in {k}={v}"


# ── Metrics completeness ────────────────────────────────────────────────────

class TestMetricsCompleteness:
    """All required metrics are written in all scenarios."""

    @pytest.mark.parametrize("iv,hv,expected_regime", [
        (18.0, 25.0, "COMPLACENT"),
        (33.0, 30.0, "ALIGNED"),
        (42.0, 30.0, "ELEVATED"),
        (55.0, 30.0, "EXTREME"),
    ])
    def test_all_metrics_present(self, iv, hv, expected_regime):
        ctx = _make_ctx(iv=iv, hv=hv)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        required = [
            "IV_Current", "HV_30D", "IV_HV_Ratio",
            "Volatility_Regime", "Volatility_Interpretation",
            "Volatility_Regime_Desc", "Volatility_Interpretation_Desc",
            "Volatility_Caution_Factor",
        ]
        for key in required:
            assert key in m, f"Missing metric: {key}"
        assert m["Volatility_Regime"] == expected_regime
        assert m["Volatility_Regime_Desc"] != ""
        assert m["Volatility_Interpretation"] is not None
        assert m["Volatility_Interpretation_Desc"] != ""

    def test_unavailable_metrics_complete(self):
        ctx = _make_ctx(iv=None, hv=25.0)
        _gate_volatility_regime(ctx)
        m = ctx.metrics
        assert m["Volatility_Regime"] == "UNAVAILABLE"
        assert m["Volatility_Regime_Desc"] != ""
        assert m["IV_HV_Ratio"] is None
        assert m["Volatility_Interpretation"] is None
        assert m["Volatility_Interpretation_Desc"] is None
        assert m["Volatility_Caution_Factor"] is None


# ── Interpretation matrix completeness ───────────────────────────────────────

class TestInterpretationMatrix:
    """Verify all 20 interpretation labels match spec Section 4."""

    EXPECTED_LABELS = {
        ("EXTENSION", "COMPLACENT"): "CONTINUATION SUPPORT",
        ("EXTENSION", "ALIGNED"): "ORDERLY EXTENSION",
        ("EXTENSION", "ELEVATED"): "REVERSAL RISK AT EXTENSION",
        ("EXTENSION", "EXTREME"): "DANGER AT EXTENSION",
        ("PULLBACK", "COMPLACENT"): "CALM PULLBACK",
        ("PULLBACK", "ALIGNED"): "NORMAL CONDITIONS",
        ("PULLBACK", "ELEVATED"): "CAPITULATION SUPPORT",
        ("PULLBACK", "EXTREME"): "STRONG CAPITULATION",
        ("BREAKOUT", "COMPLACENT"): "HIGH QUALITY BREAKOUT",
        ("BREAKOUT", "ALIGNED"): "ORDERLY BREAKOUT",
        ("BREAKOUT", "ELEVATED"): "PARTIALLY PRICED IN",
        ("BREAKOUT", "EXTREME"): "HEAVILY PRICED IN",
        ("RECOVERY", "COMPLACENT"): "ORDERLY BASE",
        ("RECOVERY", "ALIGNED"): "STANDARD REGIME",
        ("RECOVERY", "ELEVATED"): "ELEVATED ASYMMETRY",
        ("RECOVERY", "EXTREME"): "MAXIMUM ASYMMETRY",
        ("DEFAULT", "COMPLACENT"): "LOW VOLATILITY PREMIUM",
        ("DEFAULT", "ALIGNED"): "STANDARD REGIME",
        ("DEFAULT", "ELEVATED"): "ELEVATED UNCERTAINTY",
        ("DEFAULT", "EXTREME"): "EXTREME UNCERTAINTY",
    }

    def test_all_20_labels_present(self):
        """Spec §4: All 20 interpretation labels exist in the matrix."""
        assert len(_IVR_INTERPRETATION) == 20
        for key, expected_label in self.EXPECTED_LABELS.items():
            assert key in _IVR_INTERPRETATION, f"Missing interpretation: {key}"
            assert _IVR_INTERPRETATION[key]["label"] == expected_label, \
                f"Mismatch for {key}: expected '{expected_label}', got '{_IVR_INTERPRETATION[key]['label']}'"

    def test_all_interpretations_have_desc(self):
        """Every interpretation has a non-empty desc string."""
        for key, interp in _IVR_INTERPRETATION.items():
            assert interp.get("desc"), f"Missing desc for {key}"
            assert len(interp["desc"]) > 20, f"Desc too short for {key}"


# ── Threshold constants ──────────────────────────────────────────────────────

class TestThresholdConstants:
    """Spec §3.4: Tuneable constants match spec values."""

    def test_complacent_threshold(self):
        assert IVR_COMPLACENT_THRESHOLD == 0.8

    def test_elevated_threshold(self):
        assert IVR_ELEVATED_THRESHOLD == 1.2

    def test_extreme_threshold(self):
        assert IVR_EXTREME_THRESHOLD == 1.5


# ── Regime descriptions ──────────────────────────────────────────────────────

class TestRegimeDescriptions:
    """Spec §3.3: All regime labels have descriptions."""

    def test_all_regimes_have_desc(self):
        for label in ("COMPLACENT", "ALIGNED", "ELEVATED", "EXTREME", "UNAVAILABLE"):
            assert label in _IVR_REGIME_DESC, f"Missing regime desc: {label}"
            assert len(_IVR_REGIME_DESC[label]) > 20, f"Desc too short for {label}"


# ── MAPPED_FLAT_KEYS registration ────────────────────────────────────────────

class TestFlatKeys:
    """Spec §6.3: Flat keys registered in MAPPED_FLAT_KEYS."""

    def test_ivr001_flat_keys_registered(self):
        required_keys = [
            "IV_Current", "HV_30D", "IV_HV_Ratio",
            "Volatility_Regime", "Volatility_Interpretation",
        ]
        for key in required_keys:
            assert key in MAPPED_FLAT_KEYS, f"Missing flat key: {key}"


# ── Transform integration ───────────────────────────────────────────────────

class TestTransformIntegration:
    """Verify volatility_regime appears in grouped output from _transform_output."""

    def _build_action_summary(self, verdict="VALID"):
        return {
            "verdict": verdict,
            "reason": {"label": "TRENDING", "detail": ""},
            "mandate": "Enter on pullback.",
        }

    def _build_flat_metrics(self, iv=33.0, hv=30.0, regime="ALIGNED",
                            interp="STANDARD REGIME"):
        return {
            "IV_Current": iv,
            "HV_30D": hv,
            "IV_HV_Ratio": round(iv / hv, 4) if hv else None,
            "Volatility_Regime": regime,
            "Volatility_Interpretation": interp,
            "Volatility_Regime_Desc": "Test desc",
            "Volatility_Interpretation_Desc": "Test interp desc",
            "Volatility_Caution_Factor": None,
            "Engine_State": "TRENDING",
            "Trigger": "PULLBACK",
            # Minimum required keys for _transform_output to not crash
            "Price": 150.0,
            "Bar_Close_Price": 150.0,
            "Price_Source": "BAR",
            "Structural_Floor": 140.0,
            "Hard_Stop": 138.0,
            "ATR": 2.0,
            "ADV_20": 1000000,
            "ADV_20_Dollar": 150000000,
            "Is_ETF": False,
            "Convexity_Class": "C-1",
            "ETF_Primary_Exchange": "",
            "ETF_Detection_Source": "NONE",
            "Resistance": 160.0,
            "EMA_8": 149.0,
            "EMA_21": 147.0,
            "SMA_50": 145.0,
            "SMA_200": 135.0,
            "Floor_Anchor_Label": "EMA_21",
            "Floor_Anchor_Type": "EMA_21",
            "Engine_State": "TRENDING",
            "Trend_Health_Score": 75,
            "THS_Label": "STRONG",
            "THS_Floor_Buffer": 80,
            "THS_Dir_Momentum": 70,
            "THS_Trend_Age": 60,
            "THS_Structure": 90,
            "Trend_Age_Bars": 5,
        }

    def test_volatility_regime_in_grouped_output(self):
        """volatility_regime top-level section appears in grouped output."""
        action_summary = self._build_action_summary()
        flat_metrics = self._build_flat_metrics()
        result = _transform_output(action_summary, flat_metrics)
        assert "volatility_regime" in result
        vr = result["volatility_regime"]
        assert vr["iv"]["value"] == 33.0
        assert vr["hv"]["value"] == 30.0
        assert vr["regime"]["label"] == "ALIGNED"
        assert vr["thresholds"]["complacent"]["value"] == 0.8
        assert vr["thresholds"]["elevated"]["value"] == 1.2
        assert vr["thresholds"]["extreme"]["value"] == 1.5

    def test_action_summary_volatility_regime_present(self):
        """action_summary.volatility_regime appears when regime is not UNAVAILABLE."""
        action_summary = self._build_action_summary()
        flat_metrics = self._build_flat_metrics()
        _transform_output(action_summary, flat_metrics)
        assert "volatility_regime" in action_summary
        assert action_summary["volatility_regime"]["label"] == "ALIGNED"
        assert action_summary["volatility_regime"]["interpretation"] == "STANDARD REGIME"

    def test_action_summary_omitted_when_unavailable(self):
        """action_summary.volatility_regime omitted when UNAVAILABLE."""
        action_summary = self._build_action_summary()
        flat_metrics = self._build_flat_metrics()
        flat_metrics["Volatility_Regime"] = "UNAVAILABLE"
        flat_metrics["Volatility_Interpretation"] = None
        _transform_output(action_summary, flat_metrics)
        assert "volatility_regime" not in action_summary

    def test_caution_factor_appended_elevated(self):
        """Caution factor appended to action_summary when ELEVATED."""
        action_summary = self._build_action_summary()
        flat_metrics = self._build_flat_metrics(iv=42.0, hv=30.0, regime="ELEVATED",
                                                 interp="ELEVATED UNCERTAINTY")
        flat_metrics["IV_HV_Ratio"] = 1.4
        flat_metrics["Volatility_Caution_Factor"] = "VOLATILITY REGIME: ELEVATED -- ELEVATED UNCERTAINTY. Test."
        _transform_output(action_summary, flat_metrics)
        cf = action_summary.get("caution_factors", [])
        vol_factors = [f for f in cf if f.get("factor") == "VOLATILITY_REGIME"]
        assert len(vol_factors) == 1
        assert "ELEVATED" in vol_factors[0]["desc"]
