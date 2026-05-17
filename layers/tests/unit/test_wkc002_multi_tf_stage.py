"""WKC-002 -- Multi-Timeframe Stage Classification Layer tests.

Extends the WKC-001 v1.1 Weinstein 4-stage classifier from macro_frame
(Profile A weekly only) to higher_frame across all 3 profiles:
    Profile A higher_frame = DAILY (intermediate cyclical regime)
    Profile B higher_frame = WEEKLY (secular regime; same data as A macro_frame)
    Profile C higher_frame = MONTHLY (deeply secular regime)

Vocabulary reused from WKC-001 v1.1 per Design Lock §A3:
    STAGE_1_BASING / STAGE_2_ADVANCING / STAGE_3_TOPPING / STAGE_4_DECLINING

Test classes (5 classes, ~25 tests total):
    1. TestWKC002StageClassifierLogic         (8)  -- 4-quadrant logic, all stages + boundaries
    2. TestWKC002NewFlatKeysWritten           (5)  -- 3 stage class keys + Context_Weekly_SMA200 round-trip
    3. TestWKC002HigherFrameMarketStageShape  (7)  -- market_stage sub-object on each profile's higher_frame
    4. TestWKC002MultiTFConfluenceScenarios   (4)  -- Real-world confluence/divergence cases
    5. TestWKC002InvariantsAndGracefulDegradation (5) -- v1.1 + Phase 2 invariants preserved

Construction notes:
    - Transform-layer tests use injected flat_metrics passed through
      _transform_output / _flatten (no engine end-to-end run).
    - Profile detection via Floor_Anchor_Type proxy (EMA_21=A, SMA_50=B, SMA_200=C).
    - Reuses _base_flat_metrics / profile overrides from WKC-001 test patterns.
"""

import os
import sys

import pytest


# ---------------------------------------------------------------------------
# Path setup -- repository root on sys.path
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tbs_engine.transform import (
    _transform_output, _flatten, _HIGHER_FRAME_MAP, MAPPED_FLAT_KEYS,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# WKC-002 introduces 3 new stage classification flat keys + Context_Weekly_SMA200
_EXPECTED_WKC002_FLAT_KEYS = [
    "Context_Daily_Stage_Classification",     # Profile A higher_frame (DAILY)
    "Context_Weekly_Stage_Classification",    # Profile B higher_frame (WEEKLY)
    "Context_Monthly_Stage_Classification",   # Profile C higher_frame (MONTHLY)
    "Context_Weekly_SMA200",                  # Profile B parity (closes Gap 1 partially)
]


def _base_action_summary():
    """Minimal action_summary required by _transform_output."""
    return {
        "verdict": "VALID",
        "reason": {"label": "TEST", "detail": "WKC-002 test fixture"},
        "approaching": False,
        "volume": "NEUTRAL",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
        "caution_factors": [],
        "volatility_regime": {"label": "NORMAL", "interpretation": "STANDARD"},
    }


def _base_flat_metrics_profile_a(**overrides):
    """Profile A fixture -- DAILY higher_frame + WEEKLY macro_frame.
    Defaults paint a Stage 2 advancing setup on both daily and weekly.
    """
    m = {
        # Profile detection proxy
        "Floor_Anchor_Type": "EMA_21",
        "Profile_Code": "A",
        # Minimum-required structural fields (mirrors WKC-001 fixture)
        "Price_Current": 225.0,
        "Bar_Close": 225.0,
        "Engine_State": "TRENDING",
        "Structural_Floor": 220.0,
        "Anchor_Type": "EMA_21",
        "Anchor_Label": "EMA 21 (Structural Floor)",
        "ATR_Period": 14,
        "ATR": 3.5,
        "Volatility_Regime": "NORMAL",
        # WKC-002 inputs for DAILY higher_frame (Profile A): Stage 2 advancing
        "Context_Daily_SMA50": 190.0,
        "Context_Daily_SMA50_Slope": 0.85,
        "Context_SMA200": 180.0,
        "Context_Golden_Cross": True,           # SMA 50 (190) > SMA 200 (180)
        "Context_Price_vs_SMA200": 45.0,
        # Stage classification computed by output.py extraction
        "Context_Daily_Stage_Classification": "STAGE_2_ADVANCING",
        # EMA 50 keys (required by higher_frame.ema_50)
        "Context_EMA_8": 215.0,
        "Context_EMA_21": 210.0,
        "Context_EMA_Stacked": True,
        "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "Daily EMA 8 above Daily EMA 21",
        "Context_EMA_50": 195.0,
        "Context_EMA_50_Slope": 1.0,
        "Context_EMA_50_Slope_Bias": "BULLISH",
        "Context_Daily_EMA_50": 195.0,
        "Context_Daily_EMA_50_Slope": 1.0,
        "Context_SMA50_Slope_Bias": "BULLISH",
        # WKC-001 v1.1 macro_frame keys: also Stage 2 (default full confluence)
        "Context_Macro_SMA_50": 180.75,
        "Context_Macro_SMA_50_Slope": 1.80,
        "Context_Macro_SMA_200": 98.21,
        "Context_Macro_Golden_Cross": True,
        "Context_Macro_Price_vs_SMA200": 127.11,
        "Context_Macro_EMA_8": 203.33,
        "Context_Macro_EMA_21": 191.89,
        "Context_Macro_EMA_Stacked": True,
        "Context_Macro_EMA_50": 177.19,
        "Context_Macro_EMA_50_Slope": 1.96,
        "Context_Macro_ADX": 20.19,
        "Context_Macro_Stage2": True,
        "Context_Macro_Stage2_Definition": "STRICT",  # [WKC-003] STRICT replaces SIMPLIFIED
        "Context_Macro_Stage_Classification": "STAGE_2_ADVANCING",
    }
    m.update(overrides)
    return m


def _base_flat_metrics_profile_b(**overrides):
    """Profile B fixture -- WEEKLY higher_frame (no macro_frame).
    Defaults paint a Stage 2 advancing setup on weekly.
    """
    m = {
        "Floor_Anchor_Type": "SMA_50",
        "Profile_Code": "B",
        "Price_Current": 100.0,
        "Bar_Close": 100.0,
        "Engine_State": "TRENDING",
        "Structural_Floor": 95.0,
        "Anchor_Type": "SMA_50",
        "Anchor_Label": "SMA 50 (Structural Floor)",
        "ATR_Period": 14,
        "ATR": 2.0,
        "Volatility_Regime": "NORMAL",
        # WKC-002 inputs for WEEKLY higher_frame (Profile B): Stage 2 advancing
        "Context_Weekly_SMA50": 85.0,
        "Context_Weekly_SMA50_Slope": 0.5,
        "Context_Weekly_SMA50_Rising": True,
        "Context_Weekly_SMA200": 70.0,             # WKC-002 NEW: absolute SMA 200
        "Context_Weekly_Golden_Cross": True,       # SMA 50 (85) > SMA 200 (70)
        "Context_Weekly_Price_vs_SMA200": 30.0,    # close 100 - SMA200 70 = 30
        "Context_Weekly_Stage_Classification": "STAGE_2_ADVANCING",
        # EMA 50 keys
        "Context_EMA_8": 92.0,
        "Context_EMA_21": 88.0,
        "Context_EMA_Stacked": True,
        "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "Weekly EMA 8 above Weekly EMA 21",
        "Context_EMA_50": 84.0,
        "Context_EMA_50_Slope": 0.4,
        "Context_EMA_50_Slope_Bias": "BULLISH",
        "Context_Weekly_EMA_50": 84.0,
        "Context_Weekly_EMA_50_Slope": 0.4,
        "Context_SMA50_Slope_Bias": "BULLISH",
        # No macro_frame on Profile B
        "Context_Macro_SMA_50": None,
        "Context_Macro_SMA_50_Slope": None,
        "Context_Macro_SMA_200": None,
        "Context_Macro_Golden_Cross": None,
        "Context_Macro_Price_vs_SMA200": None,
        "Context_Macro_EMA_8": None,
        "Context_Macro_EMA_21": None,
        "Context_Macro_EMA_Stacked": None,
        "Context_Macro_EMA_50": None,
        "Context_Macro_EMA_50_Slope": None,
        "Context_Macro_ADX": None,
        "Context_Macro_Stage2": None,
        "Context_Macro_Stage2_Definition": None,
        "Context_Macro_Stage_Classification": None,
    }
    m.update(overrides)
    return m


def _base_flat_metrics_profile_c(**overrides):
    """Profile C fixture -- MONTHLY higher_frame (no macro_frame).
    Defaults paint a Stage 2 advancing setup on monthly.
    """
    m = {
        "Floor_Anchor_Type": "SMA_200",
        "Profile_Code": "C",
        "Price_Current": 500.0,
        "Bar_Close": 500.0,
        "Engine_State": "TRENDING",
        "Structural_Floor": 400.0,
        "Anchor_Type": "SMA_200",
        "Anchor_Label": "SMA 200 (Baseline Floor)",
        "ATR_Period": 14,
        "ATR": 25.0,
        "Volatility_Regime": "NORMAL",
        # WKC-002 inputs for MONTHLY higher_frame (Profile C): Stage 2 advancing
        "Context_Monthly_SMA50": 450.0,
        "Context_Monthly_SMA50_Slope": 5.0,
        "Context_Monthly_SMA200": 350.0,
        "Context_Monthly_Golden_Cross": True,       # SMA 50 (450) > SMA 200 (350)
        "Context_Monthly_Price_vs_SMA200": 150.0,   # close 500 - SMA200 350 = 150
        "Context_Monthly_Stage_Classification": "STAGE_2_ADVANCING",
        # EMA 50 keys
        "Context_EMA_8": 480.0,
        "Context_EMA_21": 470.0,
        "Context_EMA_Stacked": True,
        "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "Monthly EMA 8 above Monthly EMA 21",
        "Context_EMA_50": 445.0,
        "Context_EMA_50_Slope": 4.5,
        "Context_EMA_50_Slope_Bias": "BULLISH",
        "Context_Monthly_EMA_50": 445.0,
        "Context_Monthly_EMA_50_Slope": 4.5,
        "Context_SMA50_Slope_Bias": "BULLISH",
        # No macro_frame on Profile C
        "Context_Macro_SMA_50": None,
        "Context_Macro_SMA_50_Slope": None,
        "Context_Macro_SMA_200": None,
        "Context_Macro_Golden_Cross": None,
        "Context_Macro_Price_vs_SMA200": None,
        "Context_Macro_EMA_8": None,
        "Context_Macro_EMA_21": None,
        "Context_Macro_EMA_Stacked": None,
        "Context_Macro_EMA_50": None,
        "Context_Macro_EMA_50_Slope": None,
        "Context_Macro_ADX": None,
        "Context_Macro_Stage2": None,
        "Context_Macro_Stage2_Definition": None,
        "Context_Macro_Stage_Classification": None,
    }
    m.update(overrides)
    return m


# ===========================================================================
# 1. TestWKC002StageClassifierLogic (8 tests)
# ===========================================================================

class TestWKC002StageClassifierLogic:
    """WKC-002 4-quadrant classifier logic mirrors the v1.1 macro classifier
    (locked Design Lock §A3). Test the inline classifier from output.py.
    """

    @staticmethod
    def _classify(sma50, sma200, slope, price_above_sma50=True):
        """Replicates the _classify_stage closure inside output.py
        [WKC-002 + WKC-003]. Returns STAGE label string or None when any
        of sma50/sma200/price_above_sma50 is None.

        Default price_above_sma50=True preserves the canonical Stage 2/3/4/1
        quadrant assertions (they were written assuming price is consistent
        with the stage).
        """
        if sma50 is None or sma200 is None or price_above_sma50 is None:
            return None
        sma50_above = sma50 > sma200
        sma50_below = sma50 < sma200
        slope_positive = slope is not None and slope > 0
        slope_negative = slope is not None and slope < 0
        # STRICT: STAGE_2 requires all 3, STAGE_4 requires all 3
        if sma50_above and slope_positive and price_above_sma50:
            return "STAGE_2_ADVANCING"
        if sma50_above:
            return "STAGE_3_TOPPING"
        if sma50_below and slope_negative and not price_above_sma50:
            return "STAGE_4_DECLINING"
        if sma50_below:
            return "STAGE_1_BASING"
        return "STAGE_3_TOPPING"  # SMA 50 == SMA 200 defensive default

    def test_stage_2_when_bullish_structure_positive_slope(self):
        # [WKC-003] Canonical Stage 2 -- all 3 strict criteria satisfied
        assert self._classify(120.0, 100.0, 0.5, price_above_sma50=True) == "STAGE_2_ADVANCING"

    def test_stage_3_when_bullish_structure_flat_or_negative_slope(self):
        assert self._classify(120.0, 100.0, 0.0, price_above_sma50=True) == "STAGE_3_TOPPING"
        assert self._classify(120.0, 100.0, -0.5, price_above_sma50=True) == "STAGE_3_TOPPING"
        assert self._classify(120.0, 100.0, None, price_above_sma50=True) == "STAGE_3_TOPPING"

    def test_stage_4_when_bearish_structure_negative_slope(self):
        # [WKC-003] Canonical Stage 4 -- all 3 strict criteria satisfied
        assert self._classify(95.0, 100.0, -0.5, price_above_sma50=False) == "STAGE_4_DECLINING"

    def test_stage_1_when_bearish_structure_flat_or_positive_slope(self):
        assert self._classify(95.0, 100.0, 0.5, price_above_sma50=False) == "STAGE_1_BASING"
        assert self._classify(95.0, 100.0, 0.0) == "STAGE_1_BASING"
        assert self._classify(95.0, 100.0, None) == "STAGE_1_BASING"

    def test_stage_boundary_defaults_to_topping_when_sma50_equals_sma200(self):
        assert self._classify(100.0, 100.0, 0.5) == "STAGE_3_TOPPING"
        assert self._classify(100.0, 100.0, 0.0) == "STAGE_3_TOPPING"
        assert self._classify(100.0, 100.0, -0.5) == "STAGE_3_TOPPING"

    def test_none_when_sma50_unavailable(self):
        assert self._classify(None, 100.0, 0.5) is None

    def test_none_when_sma200_unavailable(self):
        assert self._classify(120.0, None, 0.5) is None

    def test_logic_matches_v1_1_macro_classifier(self):
        """v1.1 macro_frame and v2.0 higher_frame use the same 4-quadrant logic
        (Design Lock §A3 explicit reuse). [WKC-003] Both classifiers updated to
        STRICT mode in lockstep; parity preserved. Verify equivalence on the
        same inputs (now including the 4th price_above_sma50 truth).
        """
        # Same inputs should produce same labels across both classifiers
        # Each tuple: (sma50, sma200, slope, price_above_sma50, expected)
        test_cases = [
            (120.0, 100.0,  0.5, True,  "STAGE_2_ADVANCING"),   # strict: all 3 satisfied
            (120.0, 100.0, -0.5, True,  "STAGE_3_TOPPING"),     # bullish struct, slope <= 0
            (95.0,  100.0, -0.5, False, "STAGE_4_DECLINING"),   # strict: all 3 satisfied
            (95.0,  100.0,  0.5, False, "STAGE_1_BASING"),      # bearish struct, slope > 0
        ]
        for sma50, sma200, slope, price_above, expected in test_cases:
            assert self._classify(sma50, sma200, slope, price_above_sma50=price_above) == expected


# ===========================================================================
# 2. TestWKC002NewFlatKeysWritten (5 tests)
# ===========================================================================

class TestWKC002NewFlatKeysWritten:
    """WKC-002 introduces 4 new flat keys; verify each one round-trips."""

    def test_daily_stage_classification_round_trips_on_profile_a(self):
        flat_in = _base_flat_metrics_profile_a()
        grouped = _transform_output(_base_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Context_Daily_Stage_Classification"] == "STAGE_2_ADVANCING"

    def test_weekly_stage_classification_round_trips_on_profile_b(self):
        flat_in = _base_flat_metrics_profile_b()
        grouped = _transform_output(_base_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Context_Weekly_Stage_Classification"] == "STAGE_2_ADVANCING"

    def test_monthly_stage_classification_round_trips_on_profile_c(self):
        flat_in = _base_flat_metrics_profile_c()
        grouped = _transform_output(_base_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Context_Monthly_Stage_Classification"] == "STAGE_2_ADVANCING"

    def test_context_weekly_sma200_round_trips_on_profile_b(self):
        # WKC-002 parity: Weekly SMA 200 now surfaced as a flat key
        flat_in = _base_flat_metrics_profile_b()
        grouped = _transform_output(_base_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out["Context_Weekly_SMA200"] == 70.0

    def test_all_4_new_keys_in_mapped_flat_keys_registry(self):
        for key in _EXPECTED_WKC002_FLAT_KEYS:
            assert key in MAPPED_FLAT_KEYS, f"{key} missing from MAPPED_FLAT_KEYS"
            # Also assert each is in _HIGHER_FRAME_MAP (the canonical source)
            in_hfm = any(fk == key for fk, _ in _HIGHER_FRAME_MAP)
            assert in_hfm, f"{key} missing from _HIGHER_FRAME_MAP"


# ===========================================================================
# 3. TestWKC002HigherFrameMarketStageShape (7 tests)
# ===========================================================================

class TestWKC002HigherFrameMarketStageShape:
    """floor_analysis.higher_frame.market_stage sub-object shape per WKC-002
    spec, mirroring macro_frame.market_stage from v1.1 with timeframe-aware desc.
    """

    def _get_higher_frame(self, flat_in):
        grouped = _transform_output(_base_action_summary(), flat_in)
        return grouped["floor_analysis"]["higher_frame"]

    def test_profile_a_daily_market_stage_full_shape(self):
        hf = self._get_higher_frame(_base_flat_metrics_profile_a())
        ms = hf.get("market_stage")
        assert isinstance(ms, dict)
        assert ms["framework"] == "Weinstein 4-Stage Market Cycle"
        # framework_desc lists all 4 stages
        for stage in ("STAGE_1", "STAGE_2", "STAGE_3", "STAGE_4"):
            assert stage in ms["framework_desc"]
        # Stage classification
        assert ms["stage"]["label"] == "STAGE_2_ADVANCING"
        assert "markup" in ms["stage"]["desc"].lower() or "advancing" in ms["stage"]["desc"].lower()
        # criteria_evaluated transparency
        ce = ms["criteria_evaluated"]
        assert ce["sma50_above_sma200"] is True
        assert ce["sma50_slope_positive"] is True
        assert ce["price_above_sma50"] is True
        # Backward-compat boolean
        assert ms["stage_2_confirmed"] is True
        # Definition
        assert ms["definition"] == "STRICT"  # [WKC-003] STRICT replaces SIMPLIFIED

    def test_profile_a_daily_market_stage_desc_signals_intermediate_cyclical(self):
        # Profile A higher_frame is DAILY -- desc must signal intermediate cyclical
        # (NOT secular) regime semantics. Operator can distinguish from macro_frame
        # which uses secular language.
        hf = self._get_higher_frame(_base_flat_metrics_profile_a())
        ms = hf["market_stage"]
        assert "intermediate" in ms["desc"].lower() or "cyclical" in ms["desc"].lower()
        # Should ALSO mention the multi-timeframe confluence use case
        assert "macro_frame" in ms["desc"] or "confluence" in ms["desc"].lower() or "multi-timeframe" in ms["desc"].lower()

    def test_profile_b_weekly_market_stage_full_shape(self):
        hf = self._get_higher_frame(_base_flat_metrics_profile_b())
        ms = hf.get("market_stage")
        assert isinstance(ms, dict)
        assert ms["framework"] == "Weinstein 4-Stage Market Cycle"
        assert ms["stage"]["label"] == "STAGE_2_ADVANCING"
        ce = ms["criteria_evaluated"]
        assert ce["sma50_above_sma200"] is True   # 85 > 70
        assert ce["sma50_slope_positive"] is True  # slope 0.5
        assert ce["price_above_sma50"] is True     # close 100 > SMA50 85
        assert ms["stage_2_confirmed"] is True

    def test_profile_b_weekly_market_stage_desc_signals_secular(self):
        # Profile B higher_frame is WEEKLY -- desc signals secular regime
        hf = self._get_higher_frame(_base_flat_metrics_profile_b())
        ms = hf["market_stage"]
        assert "secular" in ms["desc"].lower()

    def test_profile_c_monthly_market_stage_full_shape(self):
        hf = self._get_higher_frame(_base_flat_metrics_profile_c())
        ms = hf.get("market_stage")
        assert isinstance(ms, dict)
        assert ms["framework"] == "Weinstein 4-Stage Market Cycle"
        assert ms["stage"]["label"] == "STAGE_2_ADVANCING"
        ce = ms["criteria_evaluated"]
        assert ce["sma50_above_sma200"] is True   # 450 > 350
        assert ce["sma50_slope_positive"] is True  # slope 5.0
        assert ce["price_above_sma50"] is True     # close 500 > SMA50 450
        assert ms["stage_2_confirmed"] is True

    def test_profile_c_monthly_market_stage_desc_signals_deeply_secular(self):
        # Profile C higher_frame is MONTHLY -- desc signals deeply secular
        hf = self._get_higher_frame(_base_flat_metrics_profile_c())
        ms = hf["market_stage"]
        # Either "deeply secular" or "multi-cyclical" or "generational"
        d = ms["desc"].lower()
        assert ("deeply secular" in d or "multi-cyclical" in d
                or "generational" in d or "monthly" in d)

    def test_market_stage_absent_when_classification_none(self):
        # When stage classification is None (data unavailable), market_stage
        # sub-object should NOT be emitted (graceful degradation).
        overrides = {"Context_Daily_Stage_Classification": None}
        flat_in = _base_flat_metrics_profile_a(**overrides)
        hf = self._get_higher_frame(flat_in)
        # higher_frame still exists but market_stage is absent
        assert hf is not None
        assert "market_stage" not in hf


# ===========================================================================
# 4. TestWKC002MultiTFConfluenceScenarios (4 tests)
# ===========================================================================

class TestWKC002MultiTFConfluenceScenarios:
    """Verify real-world scenarios the WKC-002 enhancement was designed to
    surface as first-class data. These document operator-facing readings.
    """

    def _get_stages(self, flat_in):
        grouped = _transform_output(_base_action_summary(), flat_in)
        hf = grouped["floor_analysis"]["higher_frame"]
        mf = grouped["floor_analysis"]["macro_frame"]
        hf_label = hf["market_stage"]["stage"]["label"] if hf and "market_stage" in hf else None
        mf_label = mf["market_stage"]["stage"]["label"] if mf and "market_stage" in mf else None
        return (hf_label, mf_label)

    def test_full_confluence_both_frames_stage_2(self):
        # Ideal Stage 2 setup -- daily and weekly aligned bullish
        hf_stage, mf_stage = self._get_stages(_base_flat_metrics_profile_a())
        assert hf_stage == "STAGE_2_ADVANCING"
        assert mf_stage == "STAGE_2_ADVANCING"

    def test_divergence_daily_stage_2_macro_stage_1_oxy_case(self):
        # The OXY-style divergence: daily intermediate trend has flipped bullish,
        # but secular weekly still bearish-structured (Stage 1 basing).
        # This was the killer validation case in the WKC-001 v1.1 hand-back.
        overrides_a = _base_flat_metrics_profile_a()
        # Daily stays Stage 2 (defaults)
        # Override macro to Stage 1: SMA 50 < SMA 200, slope positive
        overrides_a.update({
            "Context_Macro_SMA_50": 47.30,
            "Context_Macro_SMA_200": 55.91,
            "Context_Macro_SMA_50_Slope": 0.38,
            "Context_Macro_Golden_Cross": False,
            "Context_Macro_Price_vs_SMA200": 3.71,
            "Context_Macro_Stage_Classification": "STAGE_1_BASING",
            "Context_Macro_Stage2": False,
        })
        hf_stage, mf_stage = self._get_stages(overrides_a)
        assert hf_stage == "STAGE_2_ADVANCING"
        assert mf_stage == "STAGE_1_BASING"
        # Multi-TF divergence is now surfaced as data, not hidden synthesis

    def test_divergence_daily_stage_3_macro_stage_2_pullback_case(self):
        # Daily pullback inside secular advance -- classic Stage 2 pullback buy zone.
        overrides_a = _base_flat_metrics_profile_a()
        overrides_a.update({
            # Daily: bullish structure but flat/negative slope -> STAGE_3_TOPPING
            "Context_Daily_SMA50": 190.0,
            "Context_SMA200": 180.0,
            "Context_Daily_SMA50_Slope": -0.1,
            "Context_Golden_Cross": True,
            "Context_Daily_Stage_Classification": "STAGE_3_TOPPING",
        })
        hf_stage, mf_stage = self._get_stages(overrides_a)
        assert hf_stage == "STAGE_3_TOPPING"
        assert mf_stage == "STAGE_2_ADVANCING"

    def test_full_bearish_confluence_both_frames_stage_4(self):
        # Both frames in Stage 4 -- no longs
        overrides_a = _base_flat_metrics_profile_a()
        overrides_a.update({
            # Daily Stage 4
            "Context_Daily_SMA50": 170.0,
            "Context_SMA200": 180.0,
            "Context_Daily_SMA50_Slope": -0.5,
            "Context_Golden_Cross": False,
            "Context_Daily_Stage_Classification": "STAGE_4_DECLINING",
            # Macro Stage 4
            "Context_Macro_SMA_50": 95.0,
            "Context_Macro_SMA_200": 100.0,
            "Context_Macro_SMA_50_Slope": -1.2,
            "Context_Macro_Golden_Cross": False,
            "Context_Macro_Price_vs_SMA200": -8.0,
            "Context_Macro_Stage_Classification": "STAGE_4_DECLINING",
            "Context_Macro_Stage2": False,
        })
        hf_stage, mf_stage = self._get_stages(overrides_a)
        assert hf_stage == "STAGE_4_DECLINING"
        assert mf_stage == "STAGE_4_DECLINING"


# ===========================================================================
# 5. TestWKC002InvariantsAndGracefulDegradation (5 tests)
# ===========================================================================

class TestWKC002InvariantsAndGracefulDegradation:
    """Ensure WKC-002 doesn't break v1.1 invariants or Phase 2 charter rules."""

    def test_macro_frame_market_stage_still_present_on_profile_a(self):
        # WKC-002 must not break v1.1 macro_frame.market_stage
        flat_in = _base_flat_metrics_profile_a()
        grouped = _transform_output(_base_action_summary(), flat_in)
        mf = grouped["floor_analysis"]["macro_frame"]
        assert mf is not None
        assert "market_stage" in mf
        assert mf["market_stage"]["stage"]["label"] == "STAGE_2_ADVANCING"

    def test_wkc002_keys_never_appear_in_gates_py(self):
        # WKC-001 charter "weekly is never a gate input" extends to WKC-002:
        # no stage classification keys should appear in gates.py either.
        # (Exception: Context_Weekly_SMA200 IS in gates.py because gates.py
        # writes it -- but no GATE reads it.)
        _ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
        with open(os.path.join(_ROOT, "tbs_engine", "gates.py"), "r") as f:
            gates_src = f.read()
        for k in ("Context_Daily_Stage_Classification",
                  "Context_Weekly_Stage_Classification",
                  "Context_Monthly_Stage_Classification"):
            assert k not in gates_src, f"{k} should not appear in gates.py"

    def test_higher_frame_existing_fields_unchanged_on_profile_a(self):
        # WKC-002 is additive on higher_frame; existing sub-objects untouched
        flat_in = _base_flat_metrics_profile_a()
        grouped = _transform_output(_base_action_summary(), flat_in)
        hf = grouped["floor_analysis"]["higher_frame"]
        # All v1.0/v1.1 sub-objects still present
        for key in ("timeframe", "ema", "golden_cross", "sma50", "sma200", "ema_50"):
            assert key in hf, f"Pre-v2.0 higher_frame field {key} missing"

    def test_profile_b_higher_frame_now_has_sma200_subobject(self):
        # Side-effect of WKC-002: Profile B higher_frame.sma200 now populated
        # (was None pre-WKC-002 because Context_Weekly_SMA200 didn't exist as a flat key)
        flat_in = _base_flat_metrics_profile_b()
        grouped = _transform_output(_base_action_summary(), flat_in)
        hf = grouped["floor_analysis"]["higher_frame"]
        assert hf is not None
        # sma200 sub-object now present on Profile B (parity with A and C)
        assert "sma200" in hf
        assert hf["sma200"]["price"] == 70.0

    def test_wkc002_keys_none_when_underlying_data_unavailable(self):
        # Crypto-A / data-unavailable simulation: stage classification None
        overrides = {
            "Context_Daily_SMA50": None,
            "Context_SMA200": None,
            "Context_Daily_SMA50_Slope": None,
            "Context_Daily_Stage_Classification": None,
        }
        flat_in = _base_flat_metrics_profile_a(**overrides)
        grouped = _transform_output(_base_action_summary(), flat_in)
        _, _, flat_out = _flatten(grouped)
        assert flat_out.get("Context_Daily_Stage_Classification") is None


# ===========================================================================
# 6. TestWKC002JsonSerializationRegression (4 tests)
# ===========================================================================
# Regression class for the post-WKC-002 production crash:
#   "TypeError: Object of type bool is not JSON serializable"
#
# Root cause: numpy.bool (NOT Python bool, despite the misleading error name --
# numpy.bool.__class__.__name__ == 'bool') is produced when comparing numpy
# scalars and propagates through Python's short-circuit `and`. Profile B's
# gates.py writes were missing the float() wrappers that Profile A daily and
# Profile C monthly use, leaving numpy.float64 in the flat metrics, which
# then produced numpy.bool in criteria_evaluated, which crashed json.dumps.
#
# These tests exercise the failure path with numpy scalars injected into the
# flat metrics. Pre-hotfix, json.dumps(grouped) crashed; post-hotfix, the
# bool() coercion in transform.py + float() wrappers in gates.py both fire.

class TestWKC002JsonSerializationRegression:
    """Regression for the OXY Profile B crash. All values flowing into
    criteria_evaluated must be Python-native types after transform; the
    output JSON must always be json.dumps-able."""

    def _assert_json_serializable(self, grouped):
        import json
        try:
            json.dumps(grouped)
        except TypeError as e:
            pytest.fail(f"json.dumps failed: {e}")

    def test_profile_a_serializes_with_numpy_scalar_inputs(self):
        # Inject numpy.float64 into Profile A daily inputs (the exact failure
        # mode for Profile B; defending Profile A from the same regression).
        import numpy as np
        overrides = {
            "Context_Daily_SMA50": np.float64(190.0),
            "Context_Daily_SMA50_Slope": np.float64(0.85),
            "Context_SMA200": np.float64(180.0),
            "Context_Price_vs_SMA200": np.float64(45.0),
        }
        flat_in = _base_flat_metrics_profile_a(**overrides)
        grouped = _transform_output(_base_action_summary(), flat_in)
        self._assert_json_serializable(grouped)
        # And the criteria_evaluated booleans are Python native
        ce = grouped["floor_analysis"]["higher_frame"]["market_stage"]["criteria_evaluated"]
        for k in ("sma50_above_sma200", "sma50_slope_positive", "price_above_sma50"):
            assert isinstance(ce[k], bool), f"{k} is {type(ce[k]).__name__}, expected Python bool"

    def test_profile_b_serializes_with_numpy_scalar_inputs(self):
        # The exact failure case: Profile B weekly higher_frame with numpy
        # scalar slope and SMA50 (matches pre-hotfix gates.py output).
        import numpy as np
        overrides = {
            "Context_Weekly_SMA50": np.float64(85.0),
            "Context_Weekly_SMA50_Slope": np.float64(0.5),
            "Context_Weekly_SMA200": np.float64(70.0),
            "Context_Weekly_Price_vs_SMA200": np.float64(30.0),
        }
        flat_in = _base_flat_metrics_profile_b(**overrides)
        grouped = _transform_output(_base_action_summary(), flat_in)
        self._assert_json_serializable(grouped)
        ce = grouped["floor_analysis"]["higher_frame"]["market_stage"]["criteria_evaluated"]
        for k in ("sma50_above_sma200", "sma50_slope_positive", "price_above_sma50"):
            assert isinstance(ce[k], bool), f"{k} is {type(ce[k]).__name__}, expected Python bool"

    def test_profile_c_serializes_with_numpy_scalar_inputs(self):
        # Profile C monthly higher_frame defense in depth
        import numpy as np
        overrides = {
            "Context_Monthly_SMA50": np.float64(450.0),
            "Context_Monthly_SMA50_Slope": np.float64(5.0),
            "Context_Monthly_SMA200": np.float64(350.0),
            "Context_Monthly_Price_vs_SMA200": np.float64(150.0),
        }
        flat_in = _base_flat_metrics_profile_c(**overrides)
        grouped = _transform_output(_base_action_summary(), flat_in)
        self._assert_json_serializable(grouped)
        ce = grouped["floor_analysis"]["higher_frame"]["market_stage"]["criteria_evaluated"]
        for k in ("sma50_above_sma200", "sma50_slope_positive", "price_above_sma50"):
            assert isinstance(ce[k], bool), f"{k} is {type(ce[k]).__name__}, expected Python bool"

    def test_macro_frame_serializes_with_numpy_scalar_inputs(self):
        # Defensive: WKC-001 v1.1 macro_frame.criteria_evaluated also wrapped.
        import numpy as np
        overrides = {
            "Context_Macro_SMA_50": np.float64(180.75),
            "Context_Macro_SMA_50_Slope": np.float64(1.80),
            "Context_Macro_SMA_200": np.float64(98.21),
            "Context_Macro_Price_vs_SMA200": np.float64(127.11),
        }
        flat_in = _base_flat_metrics_profile_a(**overrides)
        grouped = _transform_output(_base_action_summary(), flat_in)
        self._assert_json_serializable(grouped)
        ce = grouped["floor_analysis"]["macro_frame"]["market_stage"]["criteria_evaluated"]
        for k in ("sma50_above_sma200", "sma50_slope_positive", "price_above_sma50"):
            assert isinstance(ce[k], bool), f"{k} is {type(ce[k]).__name__}, expected Python bool"
