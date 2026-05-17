"""PCM-001 -- Profile C Monthly higher_frame eligibility softening tests.

Softens the all-or-nothing gate at output.py:_assemble_output (Profile C
monthly higher-frame enrichment block). Previously, Context_Monthly_*
flat keys were populated only when BOTH monthly SMA 50 AND monthly SMA 200
were non-NaN -- ~17 years of monthly history required. Tickers in the
4-17yr range (CRWD C, LIN C class) emitted higher_frame: null entirely.

Post-PCM-001:
    - Outer gate requires only monthly SMA 50 (~4yr history).
    - SMA 200 family (Context_Monthly_SMA200, Context_Monthly_Golden_Cross,
      Context_Monthly_Price_vs_SMA200) is computed in a nested block iff
      SMA 200 column exists AND last bar is non-NaN.
    - Partial higher_frame emission self-documents via sub-object absence:
      {timeframe, ema, sma50, ema_50} populated; sma200, golden_cross,
      market_stage absent. No new flat keys, no new vocabulary (D3/D4).

Charter compliance:
    - Engine modules touched: output.py only (transform.py and gates.py
      need no changes -- already null-handle the SMA 200 family).
    - Zero verdict-surface impact: no gate in gates.py consumes
      Context_Monthly_SMA200 family for decision-making.

Test classes (per design lock D5):
    1. TestPCM001GateConditionStaticAudit (3) -- Output.py source lock
    2. TestPCM001PartialEmissionShape     (4) -- Sub-17yr ticker emission
    3. TestPCM001FullEmissionRegression   (3) -- Full-history ticker unchanged
    4. TestPCM001NoHistoryRegression      (2) -- Total-blackout case unchanged

Total: 12 tests.
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
# Fixtures
# ---------------------------------------------------------------------------

def _base_action_summary():
    return {
        "verdict": "INVALID",
        "reason": {"label": "TEST", "detail": "PCM-001 fixture"},
        "approaching": False,
        "volume": "NEUTRAL",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
        "caution_factors": [],
        "volatility_regime": {"label": "ALIGNED", "interpretation": "STANDARD"},
    }


def _profile_c_partial_history_flat_metrics():
    """Simulates a 4-17yr Profile C ticker post-PCM-001:
    Monthly SMA 50 is populated; SMA 200 family is None; EMA family present.
    This is the state the softened output.py block now produces for tickers
    like LIN C, CRWD C.
    """
    return {
        "Floor_Anchor_Type": "SMA_200",
        "Profile_Code": "C",
        "Price_Current": 500.0,
        "Bar_Close": 500.0,
        "Engine_State": "MID-RANGE (ADX <20)",
        "Engine_State_Desc": "ADX < 20",
        "Structural_Floor": 400.0,
        "Anchor_Type": "SMA_200",
        "Anchor_Label": "SMA 200 (Baseline Floor)",
        "Floor_Anchor_Label": "Long-term floor",
        "ATR_Period": 14,
        "ATR": 25.0,
        "Volatility_Regime": "ALIGNED",
        # PCM-001 partial-history surface: SMA 50 present, SMA 200 absent
        "Context_Monthly_SMA50": 450.0,
        "Context_Monthly_SMA50_Slope": 5.0,
        "Context_Monthly_SMA200": None,
        "Context_Monthly_Golden_Cross": None,
        "Context_Monthly_Price_vs_SMA200": None,
        # Stage classification is None when SMA 200 is None (output.py:971)
        "Context_Monthly_Stage_Classification": None,
        # EMA family is populated independently of SMA 200
        "Context_EMA_8": 480.0,
        "Context_EMA_21": 470.0,
        "Context_EMA_Stacked": True,
        "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "Monthly EMA 8 above Monthly EMA 21",
        "Context_Monthly_EMA_50": 445.0,
        "Context_Monthly_EMA_50_Slope": 4.5,
        "Context_EMA_50": 445.0,
        "Context_EMA_50_Slope": 4.5,
        "Context_EMA_50_Slope_Bias": "BULLISH",
        "Context_SMA50_Slope_Bias": "BULLISH",
    }


def _profile_c_full_history_flat_metrics():
    """Simulates a 17+yr Profile C ticker (GOOGL C, MSFT C class).
    All Context_Monthly_* keys populated. Post-PCM-001 behavior MUST be
    identical to pre-PCM-001 for this case (regression guard).
    """
    m = _profile_c_partial_history_flat_metrics()
    m.update({
        "Context_Monthly_SMA200": 350.0,
        "Context_Monthly_Golden_Cross": True,
        "Context_Monthly_Price_vs_SMA200": 150.0,
        "Context_Monthly_Stage_Classification": "STAGE_2_ADVANCING",
    })
    return m


def _profile_c_no_history_flat_metrics():
    """Simulates a Profile C ticker with no monthly bars at all (<4yr).
    All Context_Monthly_* keys None. Post-PCM-001 behavior MUST be
    identical to pre-PCM-001 (regression guard for the total-blackout path).
    """
    m = _profile_c_partial_history_flat_metrics()
    m.update({
        "Context_Monthly_SMA50": None,
        "Context_Monthly_SMA50_Slope": None,
        "Context_Monthly_EMA_50": None,
        "Context_Monthly_EMA_50_Slope": None,
        "Context_EMA_8": None,
        "Context_EMA_21": None,
        "Context_EMA_Stacked": None,
        "Context_EMA_Bias": None,
        "Context_EMA_Bias_Desc": None,
        "Context_EMA_50": None,
        "Context_EMA_50_Slope": None,
        "Context_EMA_50_Slope_Bias": None,
        "Context_SMA50_Slope_Bias": None,
    })
    return m


def _get_higher_frame(flat_metrics):
    grouped = _transform_output(_base_action_summary(), flat_metrics)
    return grouped.get("floor_analysis", {}).get("higher_frame")


# ===========================================================================
# 1. TestPCM001GateConditionStaticAudit (3 tests)
# ===========================================================================

class TestPCM001GateConditionStaticAudit:
    """Lock the shape of the softened gate in output.py via source inspection.

    These tests fail if a future refactor accidentally re-tightens the gate
    (e.g., re-introduces 'SMA_200' in _df_ctx.columns to the OUTER condition).
    They are intentionally brittle to changes in the PCM-001 block specifically.
    """

    def _get_assemble_output_source(self):
        return inspect.getsource(_assemble_output)

    def test_outer_gate_does_not_require_sma_200_column(self):
        """The outer Profile C gate must NOT require SMA_200 column existence.
        Pre-PCM-001 it did; post-softening it does not.
        """
        src = self._get_assemble_output_source()
        # Find the Profile C block
        pc_block_match = re.search(
            r"if p_code == \"C\":(.+?)(?=\n    # ==|\Z)",
            src, re.DOTALL,
        )
        assert pc_block_match, "Could not locate Profile C enrichment block"
        pc_block = pc_block_match.group(1)
        # Locate the OUTER gate -- first `if (_df_ctx is not None ...` after `if p_code == "C":`
        outer_gate_match = re.search(
            r"if \(_df_ctx is not None.+?\):",
            pc_block, re.DOTALL,
        )
        assert outer_gate_match, "Could not locate outer gate"
        outer_gate = outer_gate_match.group(0)
        # The OUTER gate must check SMA_50 but NOT SMA_200
        assert "'SMA_50' in _df_ctx.columns" in outer_gate
        assert "'SMA_200' in _df_ctx.columns" not in outer_gate, (
            "PCM-001 regression: outer gate has been re-tightened to require "
            "SMA_200 column. The softening intends only SMA_50 to gate the "
            "outer block; SMA_200 should be a nested check."
        )
        assert "not pd.isna(_df_ctx['SMA_50'].iloc[-1])" in outer_gate
        # The OUTER gate must NOT pre-require SMA_200 to be non-NaN
        assert "not pd.isna(_df_ctx['SMA_200'].iloc[-1])" not in outer_gate, (
            "PCM-001 regression: outer gate has been re-tightened to require "
            "non-NaN SMA_200 on the last bar."
        )

    def test_sma_200_family_lives_in_nested_block(self):
        """The SMA 200 family (SMA200 / Golden_Cross / Price_vs_SMA200) MUST
        be inside a nested if-block that checks for SMA_200 column + non-NaN.
        """
        src = self._get_assemble_output_source()
        # Find the nested SMA 200 gate inside the Profile C block
        nested_gate_match = re.search(
            r"if \('SMA_200' in _df_ctx\.columns\s*\n\s*and not pd\.isna\(_ctx_last_c\['SMA_200'\]\)\):",
            src,
        )
        assert nested_gate_match, (
            "PCM-001 regression: nested SMA_200 gate not found. The SMA 200 "
            "family must live inside a nested if-block of the form "
            "`if ('SMA_200' in _df_ctx.columns and not pd.isna(...['SMA_200'])):`"
        )

    def test_blackout_else_branch_preserved(self):
        """When monthly SMA 50 itself is unavailable (sub-4yr ticker), all 12
        Context_Monthly_* keys MUST still be set to None (no flat-key drops).
        """
        src = self._get_assemble_output_source()
        # Confirm the blackout-else assigns all 7 SMA-family + 5 EMA-family keys to None
        for required_null_assignment in [
            'metrics["Context_Monthly_SMA50_Slope"]       = None',
            'metrics["Context_Monthly_SMA50"]             = None',
            'metrics["Context_Monthly_Golden_Cross"]      = None',
            'metrics["Context_Monthly_Price_vs_SMA200"]   = None',
            'metrics["Context_Monthly_SMA200"]            = None',
            'metrics["Context_EMA_8"]                     = None',
            'metrics["Context_EMA_21"]                    = None',
            'metrics["Context_EMA_Stacked"]               = None',
            'metrics["Context_EMA_Bias"]                  = None',
            'metrics["Context_EMA_Bias_Desc"]             = None',
            'metrics["Context_Monthly_EMA_50_Slope"]      = None',
            'metrics["Context_Monthly_EMA_50"]            = None',
        ]:
            assert required_null_assignment in src, (
                f"PCM-001 regression: blackout-else missing assignment: "
                f"{required_null_assignment}"
            )


# ===========================================================================
# 2. TestPCM001PartialEmissionShape (4 tests)
# ===========================================================================

class TestPCM001PartialEmissionShape:
    """Verify Profile C higher_frame emission for the PCM-001 partial-history
    case (SMA 50 present, SMA 200 absent). Key behaviors:
        - higher_frame is NOT null
        - timeframe, ema, sma50, ema_50 sub-objects are PRESENT
        - sma200, golden_cross, market_stage sub-objects are ABSENT
    """

    def test_higher_frame_is_not_null_when_sma_50_present(self):
        """The biggest behavioral promise of PCM-001: sub-17yr tickers get a
        partial higher_frame instead of the old null.
        """
        hf = _get_higher_frame(_profile_c_partial_history_flat_metrics())
        assert hf is not None, (
            "PCM-001: higher_frame must not be null when monthly SMA 50 is "
            "populated. Pre-softening behavior (null) is now obsolete."
        )

    def test_partial_higher_frame_emits_4_expected_subobjects(self):
        """Sub-17yr ticker emits: timeframe, ema, sma50, ema_50. No others."""
        hf = _get_higher_frame(_profile_c_partial_history_flat_metrics())
        assert "timeframe" in hf, "timeframe should always emit when populated"
        assert hf["timeframe"]["label"] == "MONTHLY"
        assert "ema" in hf, "ema sub-object should emit (EMA 8/21 populated)"
        assert "sma50" in hf, "sma50 sub-object should emit (SMA 50 populated)"
        assert hf["sma50"]["price"] == 450.0
        assert "ema_50" in hf, "ema_50 sub-object should emit (EMA 50 populated)"
        assert hf["ema_50"]["price"] == 445.0

    def test_partial_higher_frame_omits_sma_200_and_golden_cross(self):
        """The SMA 200 family is correctly absent in the partial-history case."""
        hf = _get_higher_frame(_profile_c_partial_history_flat_metrics())
        # sma200 sub-object is gated on _hf_sma200_price is not None (transform.py)
        # When SMA 200 is None, the whole sma200 key should be absent from higher_frame
        assert "sma200" not in hf, (
            "PCM-001: sma200 sub-object must be absent when "
            "Context_Monthly_SMA200 is None"
        )
        # golden_cross is gated on _hf_golden_cross is not None (transform.py)
        assert "golden_cross" not in hf, (
            "PCM-001: golden_cross sub-object must be absent when "
            "Context_Monthly_Golden_Cross is None"
        )

    def test_partial_higher_frame_omits_market_stage(self):
        """market_stage requires Context_Monthly_Stage_Classification, which
        is None when SMA 200 is None (output.py:_classify_stage returns None).
        """
        hf = _get_higher_frame(_profile_c_partial_history_flat_metrics())
        assert "market_stage" not in hf, (
            "PCM-001: market_stage sub-object must be absent when "
            "Context_Monthly_Stage_Classification is None"
        )


# ===========================================================================
# 3. TestPCM001FullEmissionRegression (3 tests)
# ===========================================================================

class TestPCM001FullEmissionRegression:
    """For full-history Profile C tickers (GOOGL C, MSFT C class), post-PCM-001
    behavior MUST be byte-identical to pre-PCM-001. Regression guards.
    """

    def test_full_history_higher_frame_has_all_subobjects(self):
        hf = _get_higher_frame(_profile_c_full_history_flat_metrics())
        assert hf is not None
        # All 7 sub-objects (timeframe, ema, sma50, ema_50, sma200, golden_cross, market_stage)
        for sub in ("timeframe", "ema", "sma50", "ema_50",
                    "sma200", "golden_cross", "market_stage"):
            assert sub in hf, f"Full-history higher_frame missing: {sub}"

    def test_full_history_sma200_emits_hfi001b_shape(self):
        """Verifies PCM-001 doesn't break HFI-001-B's sma200 emission shape
        on the full-history path."""
        hf = _get_higher_frame(_profile_c_full_history_flat_metrics())
        sma200 = hf["sma200"]
        assert sma200["price"] == 350.0
        pd_obj = sma200["price_distance"]
        assert pd_obj is not None
        # 150 / 350 * 100 = 42.857... -> 42.86
        assert pd_obj["pct"] == 42.86
        assert pd_obj["condition"]["label"] == "ESTABLISHED_DECADAL_ELEVATION"
        assert "multi-decade structural reference" in pd_obj["desc"]

    def test_full_history_market_stage_emits(self):
        hf = _get_higher_frame(_profile_c_full_history_flat_metrics())
        ms = hf["market_stage"]
        assert ms["stage"]["label"] == "STAGE_2_ADVANCING"


# ===========================================================================
# 4. TestPCM001NoHistoryRegression (2 tests)
# ===========================================================================

class TestPCM001NoHistoryRegression:
    """For Profile C tickers with no monthly bars at all (sub-4yr listings),
    higher_frame should still be effectively null (or fully absent). PCM-001
    only softens the middle band (4-17yr); the bottom band (<4yr) is
    unchanged.
    """

    def test_no_history_higher_frame_is_null(self):
        """With Context_Monthly_SMA50 also None, the transform-layer
        timeframe-detection at transform.py:1379 falls through to
        _has_monthly = False, and higher_frame is built from null inputs.
        """
        hf = _get_higher_frame(_profile_c_no_history_flat_metrics())
        # transform.py builds higher_frame = {} when _hf_timeframe is None
        # and only adds keys when sub-inputs are present. With no monthly
        # data at all, the dict ends up empty or absent.
        if hf is None:
            # Acceptable: whole higher_frame absent
            pass
        else:
            # Acceptable alternative: empty dict, or dict with no
            # PCM-001-relevant sub-objects
            assert "sma50" not in hf
            assert "sma200" not in hf
            assert "ema" not in hf

    def test_no_history_emits_no_pcm001_subobjects(self):
        """Belt-and-braces: regardless of the exact null/empty representation,
        none of the PCM-001-relevant sub-objects should leak through.
        """
        hf = _get_higher_frame(_profile_c_no_history_flat_metrics())
        if hf:
            for sub in ("sma50", "ema_50", "sma200", "golden_cross",
                        "market_stage", "ema"):
                assert sub not in hf, (
                    f"No-history Profile C should not emit {sub!r}; "
                    "PCM-001 only softens the 4-17yr middle band, not the "
                    "sub-4yr bottom band."
                )
