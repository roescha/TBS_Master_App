"""WKC-003 -- STRICT classifier mode tests.

Replaces the SIMPLIFIED 4-quadrant classifier with STRICT, which adds
`price_above_sma50` as a hard requirement for STAGE_2_ADVANCING and
(symmetrically) `not price_above_sma50` for STAGE_4_DECLINING. The
non-canonical cases (bullish structure with price below SMA 50, or
bearish structure with price above SMA 50) now fall through to the
structural counterpart (STAGE_3_TOPPING or STAGE_1_BASING).

Design lock (D1-D6, confirmed inline):
    D1: STRICT replaces SIMPLIFIED (no parallel mode, no toggle).
    D2: Symmetric tightening of STAGE_2 AND STAGE_4.
    D3: STAGE_2 strict-fail -> STAGE_3_TOPPING; STAGE_4 strict-fail -> STAGE_1_BASING.
    D4: Context_Macro_Stage2_Definition flat key name preserved; value flips
        "SIMPLIFIED" -> "STRICT".
    D5: ~15 tests across 4 classes (this module).
    D6: PLTR B is the headline live anchor (flips STAGE_2 -> STAGE_3);
        regression on NVDA A / LIN A / GOOGL C (all stay STAGE_2_ADVANCING).

Engine modules touched: output.py only.
transform.py touched only for the higher_frame `market_stage.definition`
string literal flip (SIMPLIFIED -> STRICT); no logic change.
gates.py untouched (zero verdict-surface impact, confirmed by grep audit).

Test classes (this module, ~17 tests total):
    1. TestWKC003StrictClassifierLogic       (6)  -- Logic replica + symmetric flip cases
    2. TestWKC003StrictClassifierStaticAudit (4)  -- Source-shape regression locks
    3. TestWKC003DefinitionEmissionStrict    (4)  -- `definition` field == "STRICT"
    4. TestWKC003ReclassificationCases       (3)  -- Transform-layer round-trip of strict cases
"""

import inspect
import os
import re
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tbs_engine.transform import _transform_output
from tbs_engine.output import _assemble_output


# ---------------------------------------------------------------------------
# Shared fixtures (mirror WKC-002 patterns)
# ---------------------------------------------------------------------------

def _base_action_summary():
    return {
        "verdict": "INVALID",
        "reason": {"label": "TEST", "detail": "WKC-003 test fixture"},
        "approaching": False,
        "volume": "NEUTRAL",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
        "caution_factors": [],
        "volatility_regime": {"label": "ALIGNED", "interpretation": "STANDARD"},
    }


def _profile_a_strict_fixture(stage_classification, price_above_sma50, **overrides):
    """Profile A higher_frame (DAILY) fixture with explicit strict criteria."""
    m = {
        "Floor_Anchor_Type": "EMA_21",
        "Profile_Code": "A",
        "Price_Current": 110.0,
        "Bar_Close": 110.0,
        "Engine_State": "TRENDING",
        "Structural_Floor": 95.0,
        "Anchor_Type": "EMA_21",
        "Anchor_Label": "EMA 21 (Pullback Floor)",
        "Floor_Anchor_Label": "Short-term floor",
        "ATR_Period": 14,
        "ATR": 2.5,
        "Volatility_Regime": "ALIGNED",
        # WKC-002 inputs for DAILY higher_frame
        "Context_Daily_SMA50": 105.0,
        "Context_Daily_SMA50_Slope": 0.5,
        "Context_SMA200": 98.21,
        "Context_Price_vs_SMA200": 11.79,        # close=110 -> 110-98.21=11.79
        "Context_Daily_Stage_Classification": stage_classification,
        # WKC-001 v1.1 macro_frame keys
        "Context_Macro_SMA_50": 120.0,
        "Context_Macro_SMA_50_Slope": 0.5,
        "Context_Macro_SMA_200": 98.21,
        "Context_Macro_Golden_Cross": True,
        "Context_Macro_Price_vs_SMA200": 11.79,
        "Context_Macro_EMA_8": 122.0,
        "Context_Macro_EMA_21": 118.0,
        "Context_Macro_EMA_Stacked": True,
        "Context_Macro_EMA_50": 119.0,
        "Context_Macro_EMA_50_Slope": 0.3,
        "Context_Macro_ADX": 27.5,
        "Context_Macro_Stage2": (stage_classification == "STAGE_2_ADVANCING"),
        "Context_Macro_Stage2_Definition": "STRICT",
        "Context_Macro_Stage_Classification": stage_classification,
    }
    m.update(overrides)
    return m


def _profile_b_strict_fixture(stage_classification, **overrides):
    """Profile B higher_frame (WEEKLY) fixture."""
    m = {
        "Floor_Anchor_Type": "SMA_50",
        "Profile_Code": "B",
        "Price_Current": 50.0,
        "Bar_Close": 50.0,
        "Engine_State": "TRENDING",
        "Structural_Floor": 45.0,
        "Anchor_Type": "SMA_50",
        "Anchor_Label": "SMA 50 (Pullback Floor)",
        "Floor_Anchor_Label": "Medium-term floor",
        "ATR_Period": 14,
        "ATR": 1.5,
        "Volatility_Regime": "ALIGNED",
        "Context_Weekly_SMA50": 48.0,
        "Context_Weekly_SMA50_Slope": 0.3,
        "Context_Weekly_SMA200": 40.0,
        "Context_Weekly_Price_vs_SMA200": 10.0,  # close=50 -> 50-40=10
        "Context_Weekly_Golden_Cross": True,
        "Context_Weekly_Stage_Classification": stage_classification,
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


def _profile_c_strict_fixture(stage_classification, **overrides):
    """Profile C higher_frame (MONTHLY) fixture."""
    m = {
        "Floor_Anchor_Type": "SMA_200",
        "Profile_Code": "C",
        "Price_Current": 500.0,
        "Bar_Close": 500.0,
        "Engine_State": "TRENDING",
        "Structural_Floor": 400.0,
        "Anchor_Type": "SMA_200",
        "Anchor_Label": "SMA 200 (Baseline Floor)",
        "Floor_Anchor_Label": "Long-term floor",
        "ATR_Period": 14,
        "ATR": 25.0,
        "Volatility_Regime": "ALIGNED",
        "Context_Monthly_SMA50": 450.0,
        "Context_Monthly_SMA50_Slope": 5.0,
        "Context_Monthly_SMA200": 350.0,
        "Context_Monthly_Price_vs_SMA200": 150.0,   # close=500 -> 500-350=150
        "Context_Monthly_Golden_Cross": True,
        "Context_Monthly_Stage_Classification": stage_classification,
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


def _get_higher_frame(flat_metrics):
    grouped = _transform_output(_base_action_summary(), flat_metrics)
    return grouped.get("floor_analysis", {}).get("higher_frame")


def _get_macro_frame(flat_metrics):
    grouped = _transform_output(_base_action_summary(), flat_metrics)
    return grouped.get("floor_analysis", {}).get("macro_frame")


# ===========================================================================
# 1. TestWKC003StrictClassifierLogic (6 tests)
# ===========================================================================

class TestWKC003StrictClassifierLogic:
    """Logic replica of the production _classify_stage helper. Validates
    all stages plus the strict-fail flip transitions (PLTR B style).
    """

    @staticmethod
    def _classify_strict(sma50, sma200, slope, price_above_sma50):
        """4-arg STRICT classifier replica -- mirrors output.py."""
        if sma50 is None or sma200 is None or price_above_sma50 is None:
            return None
        sma50_above = sma50 > sma200
        sma50_below = sma50 < sma200
        slope_positive = slope is not None and slope > 0
        slope_negative = slope is not None and slope < 0
        if sma50_above and slope_positive and price_above_sma50:
            return "STAGE_2_ADVANCING"
        if sma50_above:
            return "STAGE_3_TOPPING"
        if sma50_below and slope_negative and not price_above_sma50:
            return "STAGE_4_DECLINING"
        if sma50_below:
            return "STAGE_1_BASING"
        return "STAGE_3_TOPPING"

    def test_stage_2_requires_all_three_criteria_satisfied(self):
        """Canonical STAGE_2: SMA 50 > SMA 200, slope > 0, price > SMA 50."""
        assert self._classify_strict(120.0, 100.0, 0.5, True) == "STAGE_2_ADVANCING"

    def test_stage_2_strict_fails_to_topping_when_price_below_sma50(self):
        """PLTR B motivating case: bullish structure + positive slope, but
        price has dropped below SMA 50. STRICT reclassifies as STAGE_3_TOPPING.
        Under SIMPLIFIED this was STAGE_2_ADVANCING (the misclassification
        WKC-003 was designed to correct).
        """
        # Same structural inputs as the canonical case above, only price flips
        assert self._classify_strict(120.0, 100.0, 0.5, False) == "STAGE_3_TOPPING"

    def test_stage_4_requires_all_three_criteria_satisfied(self):
        """Canonical STAGE_4: SMA 50 < SMA 200, slope < 0, price < SMA 50."""
        assert self._classify_strict(95.0, 100.0, -0.5, False) == "STAGE_4_DECLINING"

    def test_stage_4_strict_fails_to_basing_when_price_above_sma50(self):
        """Symmetric counterpart of PLTR B: bearish structure + negative slope,
        but price has risen above SMA 50 (early recovery signal). STRICT
        reclassifies as STAGE_1_BASING. Under SIMPLIFIED this was
        STAGE_4_DECLINING.
        """
        assert self._classify_strict(95.0, 100.0, -0.5, True) == "STAGE_1_BASING"

    def test_none_input_returns_none(self):
        """Any of sma50 / sma200 / price_above_sma50 = None -> None return.
        Critical for PCM-001 partial Profile C tickers where Context_Monthly_SMA200
        is absent.
        """
        assert self._classify_strict(None, 100.0, 0.5, True) is None
        assert self._classify_strict(120.0, None, 0.5, True) is None
        assert self._classify_strict(120.0, 100.0, 0.5, None) is None
        # slope=None is tolerated (treated as not positive)
        assert self._classify_strict(120.0, 100.0, None, True) == "STAGE_3_TOPPING"

    def test_boundary_sma50_equals_sma200_defaults_to_topping(self):
        """Mathematical boundary case. Price input is irrelevant at boundary."""
        assert self._classify_strict(100.0, 100.0, 0.5, True) == "STAGE_3_TOPPING"
        assert self._classify_strict(100.0, 100.0, -0.5, False) == "STAGE_3_TOPPING"
        assert self._classify_strict(100.0, 100.0, 0.0, True) == "STAGE_3_TOPPING"


# ===========================================================================
# 2. TestWKC003StrictClassifierStaticAudit (4 tests)
# ===========================================================================

class TestWKC003StrictClassifierStaticAudit:
    """Lock the shape of the production STRICT classifier in output.py via
    source inspection. Guards against accidental untightening regressions
    (e.g., a future refactor that drops the price_above_sma50 requirement).
    """

    def _get_assemble_output_source(self):
        return inspect.getsource(_assemble_output)

    def test_classify_stage_signature_includes_price_above_sma50(self):
        """The 4-arg STRICT signature must be present in output.py."""
        src = self._get_assemble_output_source()
        # The helper must take 4 args including price_above_sma50
        assert re.search(
            r"def _classify_stage\(sma50, sma200, slope, price_above_sma50\):",
            src,
        ), (
            "WKC-003 regression: _classify_stage signature must include "
            "price_above_sma50 as the 4th parameter. Without it the classifier "
            "is back to SIMPLIFIED mode."
        )

    def test_classify_stage_stage_2_branch_requires_price_above_sma50(self):
        """The STAGE_2_ADVANCING branch must include price_above_sma50 as a
        required AND-condition.
        """
        src = self._get_assemble_output_source()
        # Find the STAGE_2 strict assignment (must include price_above_sma50)
        assert re.search(
            r"if sma50_above and slope_positive and price_above_sma50:\s*\n\s*return \"STAGE_2_ADVANCING\"",
            src,
        ), (
            "WKC-003 regression: STAGE_2_ADVANCING branch in _classify_stage "
            "must require price_above_sma50. Without it, STAGE_2 reverts to "
            "SIMPLIFIED behavior (PLTR B-style misclassification returns)."
        )

    def test_macro_frame_inline_classifier_uses_price_above_sma50(self):
        """The macro_frame inline classifier (Profile A weekly) must also use
        _price_above_sma50 in its STAGE_2 decision -- not just compute it
        for criteria_evaluated visibility.
        """
        src = self._get_assemble_output_source()
        # The macro_frame STAGE_2 assignment must AND-in _price_above_sma50
        assert re.search(
            r"if _macro_sma50_above_sma200 and _slope_positive and _price_above_sma50:\s*\n\s*_stage_label = \"STAGE_2_ADVANCING\"",
            src,
        ), (
            "WKC-003 regression: macro_frame STAGE_2 branch must use "
            "_price_above_sma50. The variable is already computed at line ~927 "
            "but must also gate the classification, not just appear in "
            "criteria_evaluated."
        )

    def test_safe_price_above_sma50_helper_exists(self):
        """The _safe_price_above_sma50 reconstruction helper must exist in
        output.py and properly null-guard all 3 inputs.
        """
        src = self._get_assemble_output_source()
        assert "def _safe_price_above_sma50(sma200, price_vs_sma200, sma50):" in src
        # Must null-guard all 3 inputs
        assert re.search(
            r"if sma200 is None or price_vs_sma200 is None or sma50 is None:",
            src,
        ), (
            "WKC-003 regression: _safe_price_above_sma50 must null-guard all "
            "3 inputs. Otherwise sub-17yr Profile C tickers (PCM-001 partial "
            "case) could leak garbage into the classifier."
        )


# ===========================================================================
# 3. TestWKC003DefinitionEmissionStrict (4 tests)
# ===========================================================================

class TestWKC003DefinitionEmissionStrict:
    """Verify the `market_stage.definition` field emits 'STRICT' on every
    sub-object (macro_frame + 3 higher_frame profiles). Per D4, the flat
    key name (Context_Macro_Stage2_Definition) is preserved; only the value
    flips from 'SIMPLIFIED' to 'STRICT'.
    """

    def test_macro_frame_market_stage_definition_is_strict(self):
        flat = _profile_a_strict_fixture(
            stage_classification="STAGE_2_ADVANCING",
            price_above_sma50=True,
        )
        mf = _get_macro_frame(flat)
        assert mf is not None
        ms = mf.get("market_stage")
        assert ms is not None
        assert ms["definition"] == "STRICT", (
            f"macro_frame market_stage.definition must be 'STRICT' "
            f"(got {ms['definition']!r})"
        )

    def test_profile_a_daily_higher_frame_definition_is_strict(self):
        flat = _profile_a_strict_fixture(
            stage_classification="STAGE_2_ADVANCING",
            price_above_sma50=True,
        )
        hf = _get_higher_frame(flat)
        assert hf is not None
        ms = hf.get("market_stage")
        assert ms is not None
        assert ms["definition"] == "STRICT"

    def test_profile_b_weekly_higher_frame_definition_is_strict(self):
        flat = _profile_b_strict_fixture(stage_classification="STAGE_2_ADVANCING")
        hf = _get_higher_frame(flat)
        assert hf is not None
        ms = hf.get("market_stage")
        assert ms is not None
        assert ms["definition"] == "STRICT"

    def test_profile_c_monthly_higher_frame_definition_is_strict(self):
        flat = _profile_c_strict_fixture(stage_classification="STAGE_2_ADVANCING")
        hf = _get_higher_frame(flat)
        assert hf is not None
        ms = hf.get("market_stage")
        assert ms is not None
        assert ms["definition"] == "STRICT"


# ===========================================================================
# 4. TestWKC003ReclassificationCases (3 tests)
# ===========================================================================

class TestWKC003ReclassificationCases:
    """Anchor tests for the strict-fail reclassification surface. These verify
    that when the engine emits a strict-fail classification (e.g., STAGE_3
    instead of STAGE_2 because price < SMA 50), the transform-layer surface
    correctly reflects the strict-fail reason in criteria_evaluated.
    """

    def test_pltr_b_style_stage_3_emitted_when_price_below_sma50(self):
        """PLTR B-style fixture: weekly bullish structure + positive slope,
        but price has dropped below SMA 50. Engine would classify as
        STAGE_3_TOPPING under STRICT. Verify transform.py surfaces:
            - stage.label == "STAGE_3_TOPPING"
            - criteria_evaluated.price_above_sma50 == False
            - criteria_evaluated.sma50_above_sma200 == True
            - criteria_evaluated.sma50_slope_positive == True
        """
        flat = _profile_b_strict_fixture(
            stage_classification="STAGE_3_TOPPING",   # STRICT reclassified
            **{
                # Bullish structure preserved
                "Context_Weekly_SMA50": 48.0,
                "Context_Weekly_SMA200": 40.0,
                "Context_Weekly_SMA50_Slope": 0.3,
                # But price has dropped below SMA 50:
                # close=47, SMA 50=48 -> price_above_sma50 = false
                "Price_Current": 47.0,
                "Bar_Close": 47.0,
                "Context_Weekly_Price_vs_SMA200": 7.0,  # 47 - 40 = 7
            }
        )
        hf = _get_higher_frame(flat)
        assert hf is not None
        ms = hf["market_stage"]
        assert ms["stage"]["label"] == "STAGE_3_TOPPING"
        ce = ms["criteria_evaluated"]
        # The strict-fail signature: 2/3 true, price_above_sma50 false
        assert ce["sma50_above_sma200"] is True
        assert ce["sma50_slope_positive"] is True
        assert ce["price_above_sma50"] is False, (
            "PLTR B-style strict-fail must have price_above_sma50=False "
            "in criteria_evaluated -- this is the operator-visible audit trail"
        )
        # Backward-compat boolean
        assert ms["stage_2_confirmed"] is False
        assert ms["definition"] == "STRICT"

    def test_canonical_stage_2_emits_with_all_three_criteria_true(self):
        """Regression check: canonical STAGE_2 still emits with all 3
        criteria true (NVDA A / LIN A / GOOGL C class).
        """
        flat = _profile_b_strict_fixture(
            stage_classification="STAGE_2_ADVANCING",
            **{
                "Context_Weekly_SMA50": 48.0,
                "Context_Weekly_SMA200": 40.0,
                "Context_Weekly_SMA50_Slope": 0.3,
                "Price_Current": 50.0,    # Above SMA 50 (48)
                "Bar_Close": 50.0,
                "Context_Weekly_Price_vs_SMA200": 10.0,  # 50 - 40 = 10
            }
        )
        hf = _get_higher_frame(flat)
        ms = hf["market_stage"]
        assert ms["stage"]["label"] == "STAGE_2_ADVANCING"
        ce = ms["criteria_evaluated"]
        assert ce["sma50_above_sma200"] is True
        assert ce["sma50_slope_positive"] is True
        assert ce["price_above_sma50"] is True
        assert ms["stage_2_confirmed"] is True

    def test_eog_b_style_bearish_structure_positive_slope_stays_basing(self):
        """EOG B-style fixture: bearish structure (SMA 50 < SMA 200) but
        slope is positive (early recovery). Under both SIMPLIFIED and STRICT
        this is STAGE_1_BASING -- the test confirms WKC-003 does NOT
        accidentally reclassify this case (it's a regression guard).
        """
        flat = _profile_b_strict_fixture(
            stage_classification="STAGE_1_BASING",
            **{
                "Context_Weekly_SMA50": 38.0,   # Below SMA 200
                "Context_Weekly_SMA200": 40.0,
                "Context_Weekly_SMA50_Slope": 0.2,  # But rising
                "Context_Weekly_Golden_Cross": False,   # SMA 50 < SMA 200
                "Price_Current": 42.0,           # Above SMA 50
                "Bar_Close": 42.0,
                "Context_Weekly_Price_vs_SMA200": 2.0,  # 42 - 40 = 2
            }
        )
        hf = _get_higher_frame(flat)
        ms = hf["market_stage"]
        assert ms["stage"]["label"] == "STAGE_1_BASING"
        ce = ms["criteria_evaluated"]
        assert ce["sma50_above_sma200"] is False
        assert ce["sma50_slope_positive"] is True
        assert ce["price_above_sma50"] is True
        assert ms["stage_2_confirmed"] is False
