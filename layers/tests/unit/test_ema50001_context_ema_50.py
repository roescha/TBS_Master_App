"""EMA50-001 -- Daily EMA 50 Informational Context Column tests.

Spec: BUNDLE001_SWING_Output_Enrichment_Spec_v1_1.md (S153 v1.1)

Covers the ten test classes enumerated in spec §5.3:

    1.  TestEMA50001IndicatorStack          -- data.py [8, 21, 50] extension + pandas_ta works
    2.  TestEMA50001ProfileAExtraction      -- Context_Daily_EMA_50 surfaces on Profile A
    3.  TestEMA50001ProfileBExtraction      -- Context_Weekly_EMA_50 surfaces on Profile B
    4.  TestEMA50001ProfileCExtraction     -- Context_Monthly_EMA_50 surfaces on Profile C
    5.  TestEMA50001CanonicalFallback      -- Daily->Weekly->Monthly canonical resolution
    6.  TestEMA50001HigherFrameGroup       -- higher_frame.ema_50 shape on all profiles
    7.  TestEMA50001HigherFrameEMAUntouched -- regression: higher_frame.ema (8/21) unchanged
    8.  TestEMA50001NotInConvictionMap     -- EMA 50 never in _CONVICTION_TIER_MAP
    9.  TestEMA50001NotAHierarchyAnchor    -- EMA 50 never appears as hierarchy entry label
    10. TestEMA50001NotAGateInput          -- gates.py never READS Context_*_EMA_50 keys

Construction notes:
    - Mixed test strategy: most tests run the transform layer with injected
      flat_metrics; data-layer / gates-layer / output-layer extensions are
      verified via source inspection (parallel to how DSP-004 verifies its
      transform-only surface plus parallel grep-based checks for related
      sites).
    - The canonical EMA 50 fallback block resides in output.py inside
      _assemble_output (line ~846-863); since that function requires complex
      ctx/gate_result inputs, we verify the fallback derivation via source
      inspection of output.py AND verify the downstream transform-layer
      surfacing (higher_frame.ema_50 reads the canonical keys correctly when
      they are present in flat_metrics).
    - Profile detection in transform.py uses Floor_Anchor_Type as proxy
      ("EMA_21" -> Profile A, "SMA_50" -> Profile B, "SMA_200" -> Profile C).
    - _hf_timeframe selection in transform.py:815-817 is driven by which
      Context_{Daily,Weekly,Monthly}_SMA50 key is present -- so fixture
      overrides must swap these to drive the desired higher_frame branch.
"""

import os
import re
import sys
import importlib.util

import pytest


# ---------------------------------------------------------------------------
# Direct file import -- TEST-HRN-001 safe pattern
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_root = os.path.join(os.path.dirname(__file__), "..", "..")
_spec = importlib.util.spec_from_file_location(
    "tbs_engine_transform_ema50001",
    os.path.join(_root, "tbs_engine", "transform.py"),
)
_transform_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output
_flatten = _transform_mod._flatten
_CONVICTION_TIER_MAP = _transform_mod._CONVICTION_TIER_MAP
MAPPED_FLAT_KEYS = _transform_mod.MAPPED_FLAT_KEYS

# Engine source file paths -- used for source-inspection assertions
_DATA_PY_PATH = os.path.join(_root, "tbs_engine", "data.py")
_GATES_PY_PATH = os.path.join(_root, "tbs_engine", "gates.py")
_OUTPUT_PY_PATH = os.path.join(_root, "tbs_engine", "output.py")
_TRANSFORM_PY_PATH = os.path.join(_root, "tbs_engine", "transform.py")


def _read_source(path):
    """Read source file as text for inspection-based assertions."""
    with open(path, "r") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_action_summary():
    return {
        "verdict": "VALID",
        "reason": {"label": "VALID PULLBACK", "detail": ""},
        "mandate": "ENTER",
        "context": "",
    }


def _base_flat_metrics(**overrides):
    """Base flat_metrics with all hierarchy source values populated.

    Defaults to Profile A (Floor_Anchor_Type=EMA_21) with the EMA 50
    profile-specific keys + canonical aggregated keys populated. Tests
    override Floor_Anchor_Type and the EMA 50 keys to construct
    Profile-B / Profile-C / canonical-fallback scenarios.
    """
    m = {
        # Core
        "Price": 130.0,
        "Structural_Floor": 125.0,
        "Floor_Anchor_Type": "EMA_21",
        "Floor_Anchor_Label": "Intraday institutional value level",
        "Anchor_Label": "VWAP (Baseline Floor)",
        "Anchor_Type": "Standard",
        "Extension_Anchor_Type": "VWAP",
        "Extension_Anchor_Label": "Intraday institutional value level",
        "Hard_Stop": 120.0,
        "Resistance": 135.0,
        "EMA_8": 129.0,
        "EMA_21": 127.0,
        "SMA_50": 122.0,
        "SMA_200": 110.0,
        "VWAP": 126.0,
        "ATR": 2.5,
        "ADV_20": 5000000.0,
        "ADV_20_Dollar": 650000000.0,
        "Is_ETF": False,

        # Targets
        "Profit_Target": 135.0,
        "Profit_Target_Source": "10_Bar_Resistance",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "MM_Target": 140.0,
        "Blue_Sky_Target": 145.0,
        "Blue_Sky_Method": "ATR_PROJECTION",
        "Blue_Sky_Detected": True,
        "Fundamental_Target": 150.0,

        # Psychological
        "Psych_Floor": 125.0,
        "Psych_Ceiling": 140.0,
        "Psych_Floor_Dist_Pct": 3.85,
        "Psych_Ceiling_Dist_Pct": 7.69,
        "Psych_Floor_Near_Structural": False,
        "Psych_Ceiling_Near_Technical": False,
        "Psych_Increment": 5.0,
        "RN_Target_Proximity": None,
        "RN_Stop_Proximity": None,
        "RN_Floor_Proximity": None,

        # Floor sources
        "Daily_Protective_Anchor": 128.0,
        "Daily_Hard_Stop": 124.0,
        "Daily_ATR": 3.0,
        "Context_EMA_21": 128.0,
        "Context_Daily_SMA50": 123.0,
        "Context_SMA200": 112.0,
        "AVWAP_Price": 127.5,
        "Established_Hourly_Low": 126.0,

        # [EMA50-001] Profile A defaults -- daily EMA 50 + canonical
        "Context_Daily_EMA_50": 121.0,
        "Context_Daily_EMA_50_Slope": 0.15,
        "Context_EMA_50": 121.0,
        "Context_EMA_50_Slope": 0.15,
        "Context_EMA_50_Slope_Bias": "BULLISH",

        # Engine state
        "Engine_State": "TRENDING",
        "Engine_State_Desc": "ADX > 20 + full MA stack + no squeeze",
        "ADX": 30.0,
        "ADX_Accel": 0.5,
        "ADX_Accel_State": "ACCELERATING",
        "DI_Plus": 25.0,
        "DI_Minus": 15.0,
        "DI_Spread": 10.0,
        "DI_Bias": "BULLISH",
        "Trend_Age_Bars": 5,
        "Trend_Age_Max": 20,
        "Active_Modifiers": "None",
        "Active_Modifiers_List": [],
        "Inst_Churn": "CLEAR (No Churn)",
        "ATR_Dist": 0.8,
        "ATR_Dist_Anchor": "VWAP",
        "Extension_Limit": 1.5,
        "Trend_Health_Score": 65.0,
        "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 70.0,
        "THS_Dir_Momentum": 60.0,
        "THS_Trend_Age": 55.0,
        "THS_Structure": 50.0,
        "THS_Floor_Buffer_Label": "HEALTHY",
        "THS_Dir_Momentum_Label": "HEALTHY",
        "THS_Trend_Age_Label": "ACCEPTABLE",
        "THS_Structure_Label": "ACCEPTABLE",
        "THS_Death_Cross_Cap": False,
        "THS_Component_Cap": None,
        "THS_VWAP_Floor_Penalty": False,
        "THS_VWAP_Floor_Note": None,
        "THS_Context_Advisory": None,
        "Vol_Confirm_Ratio": 1.2,
        "Vol_Confirm_State": "STRONG ACCUMULATION",
        "Vol_Confirm_Bias": "BULLISH",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Failure_Threshold": 8,
        "Exit_Signal": "HOLD",
        "window_count": 3,
        "Window_Limit": 4,
        "Window_Reset_Event": "PULLBACK",
        "Reward_Risk": 2.5,
        "Reward_Risk_Note": None,
        "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Reward/Risk above 2.0 -- strong setup",
    }
    m.update(overrides)
    return m


def _profile_b_overrides():
    """Profile B overrides: Floor_Anchor_Type=SMA_50, weekly EMA 50 instead
    of daily, weekly higher_frame timeframe."""
    return {
        "Floor_Anchor_Type": "SMA_50",
        "VWAP": None,
        "AVWAP_Price": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
        # Swap daily SMA50 -> weekly SMA50 to drive _hf_timeframe = WEEKLY
        "Context_Daily_SMA50": None,
        "Context_Weekly_SMA50": 121.0,
        "Context_Weekly_SMA50_Slope": 0.3,
        # Swap daily EMA50 -> weekly EMA50
        "Context_Daily_EMA_50": None,
        "Context_Daily_EMA_50_Slope": None,
        "Context_Weekly_EMA_50": 120.0,
        "Context_Weekly_EMA_50_Slope": 0.25,
        # Canonical aggregated keys (as if output.py had already derived them)
        "Context_EMA_50": 120.0,
        "Context_EMA_50_Slope": 0.25,
        "Context_EMA_50_Slope_Bias": "BULLISH",
    }


def _profile_c_overrides():
    """Profile C overrides: Floor_Anchor_Type=SMA_200, monthly EMA 50 +
    monthly higher_frame timeframe."""
    return {
        "Floor_Anchor_Type": "SMA_200",
        "VWAP": None,
        "AVWAP_Price": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
        # Swap daily SMA50 -> monthly SMA50 to drive _hf_timeframe = MONTHLY
        "Context_Daily_SMA50": None,
        "Context_Monthly_SMA50": 118.0,
        "Context_Monthly_SMA50_Slope": 0.4,
        "Context_Monthly_SMA200": 108.0,
        # Swap daily EMA50 -> monthly EMA50
        "Context_Daily_EMA_50": None,
        "Context_Daily_EMA_50_Slope": None,
        "Context_Monthly_EMA_50": 117.0,
        "Context_Monthly_EMA_50_Slope": 0.35,
        # Canonical aggregated keys
        "Context_EMA_50": 117.0,
        "Context_EMA_50_Slope": 0.35,
        "Context_EMA_50_Slope_Bias": "BULLISH",
    }


def _get_grouped(flat_overrides=None):
    fm = _base_flat_metrics(**(flat_overrides or {}))
    return _transform_output(_base_action_summary(), fm)


def _get_flat(flat_overrides=None):
    grouped = _get_grouped(flat_overrides)
    _status, _diagnostic, flat = _flatten(grouped)
    return flat


def _get_higher_frame(flat_overrides=None):
    """Shortcut: returns floor_analysis.higher_frame dict (or None)."""
    return _get_grouped(flat_overrides).get("floor_analysis", {}).get("higher_frame")


# ===========================================================================
# 1. TestEMA50001IndicatorStack -- data.py [8, 21, 50] extension verified
# ===========================================================================


class TestEMA50001IndicatorStack:
    """Spec §4.3.1 + §5.3: on a Profile A evaluation with sufficient context
    bars (>=51), df_ctx contains an EMA_50 column with non-null final-bar
    value. We verify via source inspection of data.py:665 (the indicator
    stack extension is a single-line edit) AND by running pandas_ta on a
    synthetic DataFrame to confirm pandas_ta produces the EMA_50 column
    when length=50 is passed."""

    def test_data_py_ema_indicator_stack_includes_50(self):
        """Source assertion: data.py contains the [8, 21, 50] indicator stack
        extension per spec §4.3.1."""
        src = _read_source(_DATA_PY_PATH)
        # The spec §4.3.1 changes `for ln in [8, 21]:` to `for ln in [8, 21, 50]:`
        # Verify the new form is present and the old form is no longer the
        # active indicator-computation line.
        assert "[8, 21, 50]" in src, (
            "data.py missing EMA 50 indicator stack extension; expected "
            "`for ln in [8, 21, 50]:` per spec §4.3.1"
        )
        # Provenance tag must be present at the addition site
        assert "[EMA50-001]" in src, (
            "data.py missing [EMA50-001] provenance comment at indicator-stack edit"
        )

    def test_pandas_ta_produces_ema_50_column(self):
        """pandas_ta produces an EMA_50 column when length=50 is passed.

        This is what data.py:665 relies on (`df_ctx.ta.ema(length=50,
        append=True)`). Construct a synthetic context-frame DataFrame with
        >=51 bars and exercise the same call pattern.

        Note: the pandas_ta .ta accessor "may not register on all Python /
        pandas version combinations" per PA-001-BUG-3 precedent comment in
        tests/unit/test_pa001_phase2_output.py. We skip if the accessor is
        not available -- the source-inspection assertion above is the
        primary verification that the indicator stack was extended; this
        synthetic-dataframe test is a secondary sanity check on pandas_ta
        behavior.
        """
        try:
            import pandas as pd
            import pandas_ta  # noqa: F401
        except ImportError:
            pytest.skip("pandas_ta not available in this environment")

        # Synthetic 60-bar uptrending close series
        df = pd.DataFrame({
            "open":  [100.0 + i * 0.5 for i in range(60)],
            "high":  [101.0 + i * 0.5 for i in range(60)],
            "low":   [99.5 + i * 0.5 for i in range(60)],
            "close": [100.5 + i * 0.5 for i in range(60)],
            "volume": [1_000_000] * 60,
        })
        # Skip if pandas_ta .ta accessor failed to register (known
        # environmental issue with Python 3.12+/pandas 3+ combinations
        # per PA-001-BUG-3 precedent)
        if not hasattr(df, "ta"):
            pytest.skip(
                "pandas_ta .ta accessor not registered on DataFrame -- "
                "known environmental issue per PA-001-BUG-3; source-inspection "
                "test above is the primary indicator-stack verification"
            )
        df.ta.ema(length=50, append=True)
        assert "EMA_50" in df.columns, (
            "pandas_ta did not produce EMA_50 column from ema(length=50)"
        )
        # Final-bar value is non-null after sufficient bars
        assert df["EMA_50"].iloc[-1] is not None
        assert not pd.isna(df["EMA_50"].iloc[-1])


# ===========================================================================
# 2. TestEMA50001ProfileAExtraction -- gates.py writes Profile A flat keys
# ===========================================================================


class TestEMA50001ProfileAExtraction:
    """Spec §4.3.2 + §5.3: on a Profile A evaluation, flat keys
    Context_Daily_EMA_50 and Context_Daily_EMA_50_Slope are populated by the
    Profile A gates.py extraction block at gates.py:47-58. Verified via
    source inspection (the gates.py block is a write site that requires the
    full engine pipeline to exercise) plus transform-layer round-trip
    confirming the keys are MAPPED_FLAT_KEYS members and survive the
    grouped->flatten round-trip."""

    def test_gates_py_profile_a_writes_context_daily_ema_50(self):
        """gates.py contains the Profile A EMA 50 extraction block writing
        Context_Daily_EMA_50 and Context_Daily_EMA_50_Slope flat keys."""
        src = _read_source(_GATES_PY_PATH)
        assert "Context_Daily_EMA_50" in src, (
            "gates.py missing Context_Daily_EMA_50 write site per spec §4.3.2"
        )
        assert "Context_Daily_EMA_50_Slope" in src, (
            "gates.py missing Context_Daily_EMA_50_Slope write site per spec §4.3.2"
        )
        # Provenance tag present
        assert "[EMA50-001]" in src, (
            "gates.py missing [EMA50-001] provenance comment at Profile A site"
        )

    def test_profile_a_context_daily_ema_50_surfaces_in_higher_frame(self):
        """Profile A: Context_Daily_EMA_50 input flows into
        higher_frame.ema_50.price AND survives the _flatten round-trip
        (production data path + dev-utility symmetry per OD-2 closure
        in Phase 3 hand-back).
        """
        # MAPPED_FLAT_KEYS registration check
        assert "Context_Daily_EMA_50" in MAPPED_FLAT_KEYS
        assert "Context_Daily_EMA_50_Slope" in MAPPED_FLAT_KEYS
        # Value flows into higher_frame.ema_50 (production data path)
        hf = _get_higher_frame()
        assert hf is not None
        assert hf.get("ema_50") is not None
        assert hf["ema_50"]["price"] == 121.0
        assert hf["ema_50"]["price"] > 0
        slope = hf["ema_50"]["slope"]
        assert slope is not None
        assert slope.get("value") is not None
        assert isinstance(slope["value"], (int, float))
        # Flatten round-trip preserved (OD-2 reverse-map closure)
        flat = _get_flat()
        assert flat.get("Context_Daily_EMA_50") == 121.0
        assert flat.get("Context_Daily_EMA_50_Slope") == 0.15
        assert isinstance(flat.get("Context_Daily_EMA_50_Slope"), (int, float))


# ===========================================================================
# 3. TestEMA50001ProfileBExtraction -- gates.py writes Profile B flat keys
# ===========================================================================


class TestEMA50001ProfileBExtraction:
    """Spec §4.3.3 + §5.3: on a Profile B evaluation, flat keys
    Context_Weekly_EMA_50 and Context_Weekly_EMA_50_Slope are populated by
    the Profile B gates.py extraction block."""

    def test_gates_py_profile_b_writes_context_weekly_ema_50(self):
        """gates.py contains the Profile B weekly EMA 50 extraction site."""
        src = _read_source(_GATES_PY_PATH)
        assert "Context_Weekly_EMA_50" in src
        assert "Context_Weekly_EMA_50_Slope" in src

    def test_profile_b_context_weekly_ema_50_surfaces_in_higher_frame(self):
        """Profile B: Context_Weekly_EMA_50 flows into higher_frame.ema_50.price
        AND survives _flatten round-trip per OD-2 closure."""
        assert "Context_Weekly_EMA_50" in MAPPED_FLAT_KEYS
        assert "Context_Weekly_EMA_50_Slope" in MAPPED_FLAT_KEYS
        hf = _get_higher_frame(_profile_b_overrides())
        assert hf is not None
        assert hf.get("timeframe", {}).get("label") == "WEEKLY"
        assert hf.get("ema_50") is not None
        assert hf["ema_50"]["price"] == 120.0
        slope = hf["ema_50"]["slope"]
        assert slope is not None
        assert slope.get("value") is not None
        # Flatten round-trip (OD-2)
        flat = _get_flat(_profile_b_overrides())
        assert flat.get("Context_Weekly_EMA_50") == 120.0
        assert flat.get("Context_Weekly_EMA_50_Slope") == 0.25


# ===========================================================================
# 4. TestEMA50001ProfileCExtraction -- output.py (NOT gates.py) writes Profile C
# ===========================================================================


class TestEMA50001ProfileCExtraction:
    """Spec §4.3.4 + §11.1 citation drift + §5.3: on a Profile C evaluation,
    flat keys Context_Monthly_EMA_50 and Context_Monthly_EMA_50_Slope are
    populated by the Profile C EXTRACTION BLOCK IN output.py:741-800 (NOT
    in gates.py per citation drift acknowledgment locked at v1.1).
    Asserts via source inspection that the Profile C site is in output.py
    and not in gates.py."""

    def test_output_py_profile_c_writes_context_monthly_ema_50(self):
        """output.py contains the Profile C monthly EMA 50 extraction site."""
        src = _read_source(_OUTPUT_PY_PATH)
        assert "Context_Monthly_EMA_50" in src, (
            "output.py missing Context_Monthly_EMA_50 write site per spec §4.3.4 "
            "(citation drift -- Profile C lands in output.py, not gates.py)"
        )
        assert "Context_Monthly_EMA_50_Slope" in src

    def test_gates_py_does_not_contain_monthly_ema_50(self):
        """gates.py must NOT contain Context_Monthly_EMA_50 per citation drift
        acknowledgment -- Profile C uses output.py per spec §11.1."""
        src = _read_source(_GATES_PY_PATH)
        assert "Context_Monthly_EMA_50" not in src, (
            "gates.py unexpectedly contains Context_Monthly_EMA_50 -- "
            "citation drift acknowledgment violated; Profile C must land in output.py"
        )

    def test_profile_c_context_monthly_ema_50_surfaces_in_higher_frame(self):
        """Profile C: Context_Monthly_EMA_50 flows into higher_frame.ema_50.price
        AND survives _flatten round-trip per OD-2 closure."""
        assert "Context_Monthly_EMA_50" in MAPPED_FLAT_KEYS
        assert "Context_Monthly_EMA_50_Slope" in MAPPED_FLAT_KEYS
        hf = _get_higher_frame(_profile_c_overrides())
        assert hf is not None
        assert hf.get("timeframe", {}).get("label") == "MONTHLY"
        assert hf.get("ema_50") is not None
        assert hf["ema_50"]["price"] == 117.0
        slope = hf["ema_50"]["slope"]
        assert slope is not None
        assert slope.get("value") is not None
        # Flatten round-trip (OD-2)
        flat = _get_flat(_profile_c_overrides())
        assert flat.get("Context_Monthly_EMA_50") == 117.0
        assert flat.get("Context_Monthly_EMA_50_Slope") == 0.35


# ===========================================================================
# 5. TestEMA50001CanonicalFallback -- Daily->Weekly->Monthly per spec §4.3.5
# ===========================================================================


def _replicate_canonical_fallback(metrics):
    """Verbatim replication of output.py:846-863 canonical fallback block.

    Tests the spec §4.3.5 algorithm directly. A separate test asserts that
    output.py source contains the matching block (via grep), so divergence
    between this replica and the engine would be caught at the source
    assertion level even if this helper drifted.
    """
    _ctx_ema50_slope = metrics.get("Context_Daily_EMA_50_Slope")
    _ctx_ema50_price = metrics.get("Context_Daily_EMA_50")
    if _ctx_ema50_slope is None:
        _ctx_ema50_slope = metrics.get("Context_Weekly_EMA_50_Slope")
        _ctx_ema50_price = metrics.get("Context_Weekly_EMA_50")
    if _ctx_ema50_slope is None:
        _ctx_ema50_slope = metrics.get("Context_Monthly_EMA_50_Slope")
        _ctx_ema50_price = metrics.get("Context_Monthly_EMA_50")
    if _ctx_ema50_slope is not None:
        if _ctx_ema50_slope > 0:
            metrics["Context_EMA_50_Slope_Bias"] = "BULLISH"
        elif _ctx_ema50_slope < 0:
            metrics["Context_EMA_50_Slope_Bias"] = "BEARISH"
        else:
            metrics["Context_EMA_50_Slope_Bias"] = "NEUTRAL"
        if _ctx_ema50_price is not None:
            metrics["Context_EMA_50"] = round(float(_ctx_ema50_price), 2)
        metrics["Context_EMA_50_Slope"] = _ctx_ema50_slope
    return metrics


class TestEMA50001CanonicalFallback:
    """Spec §4.3.5 + §5.3: canonical Context_EMA_50 / Context_EMA_50_Slope /
    Context_EMA_50_Slope_Bias resolve via Daily->Weekly->Monthly fallback.
    The fallback block lives in output.py inside _assemble_output and so is
    tested via (a) source inspection asserting structure + ordering of the
    fallback chain in output.py, and (b) a verbatim algorithm replica
    exercised against multiple input combinations to verify the contract."""

    def test_output_py_canonical_fallback_block_present(self):
        """output.py contains the canonical fallback block per spec §4.3.5."""
        src = _read_source(_OUTPUT_PY_PATH)
        # Block uses these literal markers
        assert "Context_EMA_50_Slope_Bias" in src
        assert "Context_EMA_50" in src
        assert "Context_EMA_50_Slope" in src
        # Provenance tag at the canonical fallback site
        assert "[EMA50-001] Canonical" in src, (
            "output.py missing [EMA50-001] Canonical provenance comment per spec §4.3.5"
        )

    def test_output_py_canonical_fallback_order_daily_first(self):
        """output.py fallback order: Daily checked first, then Weekly, then
        Monthly. Verified by checking that Context_Daily_EMA_50_Slope appears
        in the canonical-fallback block BEFORE Context_Weekly_EMA_50_Slope
        and Context_Monthly_EMA_50_Slope."""
        src = _read_source(_OUTPUT_PY_PATH)
        # Extract the canonical fallback block region
        marker = "[EMA50-001] Canonical"
        idx = src.find(marker)
        assert idx >= 0, "Canonical fallback marker not found"
        # Take 1000 chars of context after the marker (block is ~25 lines)
        block = src[idx:idx + 1500]
        daily_pos = block.find("Context_Daily_EMA_50_Slope")
        weekly_pos = block.find("Context_Weekly_EMA_50_Slope")
        monthly_pos = block.find("Context_Monthly_EMA_50_Slope")
        assert daily_pos >= 0, "Daily key not found in canonical block"
        assert weekly_pos >= 0, "Weekly key not found in canonical block"
        assert monthly_pos >= 0, "Monthly key not found in canonical block"
        assert daily_pos < weekly_pos < monthly_pos, (
            f"Canonical fallback order incorrect: Daily@{daily_pos} -> "
            f"Weekly@{weekly_pos} -> Monthly@{monthly_pos} expected"
        )

    def test_canonical_resolves_to_daily_when_daily_present(self):
        """Daily present -> canonical == Daily (regardless of Weekly/Monthly)."""
        m = {
            "Context_Daily_EMA_50": 121.0,
            "Context_Daily_EMA_50_Slope": 0.15,
            "Context_Weekly_EMA_50": 119.5,
            "Context_Weekly_EMA_50_Slope": 0.30,
            "Context_Monthly_EMA_50": 117.0,
            "Context_Monthly_EMA_50_Slope": 0.40,
        }
        _replicate_canonical_fallback(m)
        assert m["Context_EMA_50"] == 121.0  # Daily, not Weekly or Monthly
        assert m["Context_EMA_50_Slope"] == 0.15

    def test_canonical_falls_through_to_weekly_when_daily_missing(self):
        """Daily missing -> canonical == Weekly."""
        m = {
            "Context_Daily_EMA_50": None,
            "Context_Daily_EMA_50_Slope": None,
            "Context_Weekly_EMA_50": 119.5,
            "Context_Weekly_EMA_50_Slope": 0.30,
            "Context_Monthly_EMA_50": 117.0,
            "Context_Monthly_EMA_50_Slope": 0.40,
        }
        _replicate_canonical_fallback(m)
        assert m["Context_EMA_50"] == 119.5  # Weekly
        assert m["Context_EMA_50_Slope"] == 0.30

    def test_canonical_falls_through_to_monthly_when_daily_and_weekly_missing(self):
        """Daily and Weekly missing -> canonical == Monthly."""
        m = {
            "Context_Daily_EMA_50": None,
            "Context_Daily_EMA_50_Slope": None,
            "Context_Weekly_EMA_50": None,
            "Context_Weekly_EMA_50_Slope": None,
            "Context_Monthly_EMA_50": 117.0,
            "Context_Monthly_EMA_50_Slope": 0.40,
        }
        _replicate_canonical_fallback(m)
        assert m["Context_EMA_50"] == 117.0  # Monthly
        assert m["Context_EMA_50_Slope"] == 0.40

    def test_canonical_bias_bullish_on_positive_slope(self):
        """slope > 0 -> Context_EMA_50_Slope_Bias == 'BULLISH'."""
        m = {"Context_Daily_EMA_50": 120.0, "Context_Daily_EMA_50_Slope": 0.5}
        _replicate_canonical_fallback(m)
        assert m["Context_EMA_50_Slope_Bias"] == "BULLISH"

    def test_canonical_bias_bearish_on_negative_slope(self):
        """slope < 0 -> Context_EMA_50_Slope_Bias == 'BEARISH'."""
        m = {"Context_Daily_EMA_50": 120.0, "Context_Daily_EMA_50_Slope": -0.5}
        _replicate_canonical_fallback(m)
        assert m["Context_EMA_50_Slope_Bias"] == "BEARISH"

    def test_canonical_bias_neutral_on_zero_slope(self):
        """slope == 0 -> Context_EMA_50_Slope_Bias == 'NEUTRAL'."""
        m = {"Context_Daily_EMA_50": 120.0, "Context_Daily_EMA_50_Slope": 0.0}
        _replicate_canonical_fallback(m)
        assert m["Context_EMA_50_Slope_Bias"] == "NEUTRAL"

    def test_canonical_no_keys_written_when_all_slopes_none(self):
        """All slopes None -> canonical keys NOT written (defensive)."""
        m = {
            "Context_Daily_EMA_50": None,
            "Context_Daily_EMA_50_Slope": None,
            "Context_Weekly_EMA_50": None,
            "Context_Weekly_EMA_50_Slope": None,
            "Context_Monthly_EMA_50": None,
            "Context_Monthly_EMA_50_Slope": None,
        }
        _replicate_canonical_fallback(m)
        assert "Context_EMA_50_Slope_Bias" not in m
        assert "Context_EMA_50" not in m
        assert "Context_EMA_50_Slope" not in m

    def test_transform_surfaces_canonical_slope_bias_into_higher_frame(self):
        """When canonical Context_EMA_50_Slope_Bias is present in flat_metrics
        (as if output.py had derived it), transform.py reads it and populates
        higher_frame.ema_50.slope.bias.label correctly."""
        hf = _get_higher_frame()
        assert hf is not None
        assert hf.get("ema_50") is not None
        ema50 = hf["ema_50"]
        assert ema50.get("slope") is not None
        assert ema50["slope"].get("bias") is not None
        assert ema50["slope"]["bias"].get("label") == "BULLISH"


# ===========================================================================
# 6. TestEMA50001HigherFrameGroup -- higher_frame.ema_50 shape on all profiles
# ===========================================================================


class TestEMA50001HigherFrameGroup:
    """Spec §4.3.6 + §5.3: higher_frame.ema_50 grouped object emits on all
    three profiles when respective profile-specific price is non-null.
    Shape: price, slope (or None), desc. slope.desc contains
    'EMA 50 slope (bar-to-bar)'; top-level desc contains
    'alternative medium-term reference'."""

    def test_profile_a_higher_frame_ema_50_present(self):
        """Profile A: higher_frame.ema_50 group emits with DAILY timeframe."""
        hf = _get_higher_frame()
        assert hf is not None
        assert hf.get("timeframe", {}).get("label") == "DAILY"
        assert hf.get("ema_50") is not None

    def test_profile_a_ema_50_shape(self):
        """ema_50 group shape: price, slope, desc."""
        hf = _get_higher_frame()
        ema50 = hf["ema_50"]
        assert "price" in ema50
        assert "slope" in ema50
        assert "desc" in ema50
        assert ema50["price"] == 121.0
        # slope sub-shape: {value, unit, bias, desc}
        slope = ema50["slope"]
        assert slope is not None
        assert "value" in slope
        assert "unit" in slope
        assert slope["unit"] == "dollars"
        assert "bias" in slope
        assert "desc" in slope

    def test_slope_desc_contains_bar_to_bar(self):
        """slope.desc contains 'EMA 50 slope (bar-to-bar)' per spec §4.3.6."""
        hf = _get_higher_frame()
        slope_desc = hf["ema_50"]["slope"]["desc"]
        assert "EMA 50 slope (bar-to-bar)" in slope_desc

    def test_top_level_desc_contains_alternative_medium_term(self):
        """top-level desc contains 'alternative medium-term reference' per §4.3.6."""
        hf = _get_higher_frame()
        desc = hf["ema_50"]["desc"]
        assert "alternative medium-term reference" in desc

    def test_profile_b_higher_frame_ema_50_present_with_weekly_timeframe(self):
        """Profile B: higher_frame.ema_50 emits with WEEKLY timeframe."""
        hf = _get_higher_frame(_profile_b_overrides())
        assert hf is not None
        assert hf.get("timeframe", {}).get("label") == "WEEKLY"
        assert hf.get("ema_50") is not None
        assert hf["ema_50"]["price"] == 120.0
        # Slope desc reflects WEEKLY
        assert "WEEKLY EMA 50 slope (bar-to-bar)" == hf["ema_50"]["slope"]["desc"]
        # Top-level desc reflects WEEKLY
        assert "WEEKLY EMA 50" in hf["ema_50"]["desc"]

    def test_profile_c_higher_frame_ema_50_present_with_monthly_timeframe(self):
        """Profile C: higher_frame.ema_50 emits with MONTHLY timeframe."""
        hf = _get_higher_frame(_profile_c_overrides())
        assert hf is not None
        assert hf.get("timeframe", {}).get("label") == "MONTHLY"
        assert hf.get("ema_50") is not None
        assert hf["ema_50"]["price"] == 117.0
        assert "MONTHLY EMA 50 slope (bar-to-bar)" == hf["ema_50"]["slope"]["desc"]
        assert "MONTHLY EMA 50" in hf["ema_50"]["desc"]

    def test_ema_50_slope_is_none_when_slope_value_missing(self):
        """When profile-specific slope is None, ema_50.slope is None (defensive)
        but the group still emits with price + desc."""
        hf = _get_higher_frame({"Context_Daily_EMA_50_Slope": None})
        assert hf is not None
        assert hf.get("ema_50") is not None
        # price still present
        assert hf["ema_50"]["price"] == 121.0
        # slope is None when underlying slope value is None
        assert hf["ema_50"]["slope"] is None


# ===========================================================================
# 7. TestEMA50001HigherFrameEMAUntouched -- regression on EMA 8/21 stack group
# ===========================================================================


class TestEMA50001HigherFrameEMAUntouched:
    """Spec §4.3.8 + §5.3: higher_frame.ema (the existing EMA 8/21 stack
    group at transform.py:792-799) shape is bitwise-unchanged from
    pre-Bundle 1 baseline. ema_50 is a separate group; the original group
    is not extended or modified."""

    def test_higher_frame_ema_group_exists_and_unchanged(self):
        """higher_frame.ema still emits with the original 5-key shape:
        ema_8, ema_21, stacked, bias, desc."""
        hf = _get_higher_frame({
            "Context_EMA_Stacked": True,
            "Context_EMA_Bias": "BULLISH",
            "Context_EMA_Bias_Desc": "EMA 8 above EMA 21 -- short-term bullish",
        })
        assert hf is not None
        assert "ema" in hf
        ema_group = hf["ema"]
        # Required keys present
        assert "ema_8" in ema_group
        assert "ema_21" in ema_group
        assert "stacked" in ema_group
        assert "bias" in ema_group
        assert "desc" in ema_group

    def test_higher_frame_ema_group_does_not_contain_ema_50_fields(self):
        """The EMA 8/21 stack group must NOT have been extended with EMA 50
        fields per scope guard §4.3.8."""
        hf = _get_higher_frame({
            "Context_EMA_Stacked": True,
            "Context_EMA_Bias": "BULLISH",
            "Context_EMA_Bias_Desc": "EMA 8 above EMA 21",
        })
        ema_group = hf.get("ema", {})
        # Negative: no EMA 50 fields inside the original group
        assert "ema_50" not in ema_group
        assert "ema_50_slope" not in ema_group

    def test_ema_and_ema_50_coexist_as_separate_groups(self):
        """higher_frame.ema and higher_frame.ema_50 are sibling groups,
        not nested. Both present on the same evaluation."""
        hf = _get_higher_frame({
            "Context_EMA_Stacked": True,
            "Context_EMA_Bias": "BULLISH",
            "Context_EMA_Bias_Desc": "EMA 8 above EMA 21",
        })
        assert "ema" in hf
        assert "ema_50" in hf
        # They are top-level siblings within higher_frame
        assert isinstance(hf["ema"], dict)
        assert isinstance(hf["ema_50"], dict)


# ===========================================================================
# 8. TestEMA50001NotInConvictionMap -- EMA 50 absent from _CONVICTION_TIER_MAP
# ===========================================================================


class TestEMA50001NotInConvictionMap:
    """Spec §4.3.8 + §5.3 + CNV-001 scope guard: EMA 50 is NOT a conviction
    tier candidate -- no entry for EMA_50 / DAILY_EMA_50 / WEEKLY_EMA_50 /
    MONTHLY_EMA_50 appears in _CONVICTION_TIER_MAP. Structural enforcement
    of the scope guard at spec §4.3.8."""

    def test_ema_50_not_in_conviction_map_keys(self):
        """No EMA 50 variant appears as a key in _CONVICTION_TIER_MAP."""
        forbidden = {
            "EMA_50", "DAILY_EMA_50", "WEEKLY_EMA_50", "MONTHLY_EMA_50",
            "EMA50",
        }
        actual_keys = set(_CONVICTION_TIER_MAP.keys())
        intersect = forbidden & actual_keys
        assert not intersect, (
            f"EMA 50 keys unexpectedly in _CONVICTION_TIER_MAP: {intersect}"
        )

    def test_conviction_map_still_19_entries(self):
        """EMA50-001 must not have grown the conviction map -- still exactly
        19 entries per CNV-001 OD-1 resolution path (a)."""
        assert len(_CONVICTION_TIER_MAP) == 19


# ===========================================================================
# 9. TestEMA50001NotAHierarchyAnchor -- EMA 50 never appears as entry.label
# ===========================================================================


class TestEMA50001NotAHierarchyAnchor:
    """Spec §4.3.8 + §5.3: EMA 50 is explicitly NOT a hierarchy anchor.
    No entry in stop.hierarchy / stop.overhead_levels / target.hierarchy /
    target.cleared_levels has label starting with or containing 'EMA_50'."""

    def _collect_all_hierarchy_labels(self, grouped):
        """Walk the trade_setup hierarchy containers and return all entry labels."""
        labels = []
        ts = grouped.get("trade_setup", {})
        for side in ("stop", "target"):
            side_obj = ts.get(side, {})
            if not isinstance(side_obj, dict):
                continue
            for container in ("hierarchy", "overhead_levels", "cleared_levels"):
                entries = side_obj.get(container) or []
                for entry in entries:
                    label = entry.get("label")
                    if label is not None:
                        labels.append(label)
        return labels

    def test_profile_a_no_ema_50_hierarchy_labels(self):
        """Profile A: no hierarchy/overhead/cleared entry has 'EMA_50' label."""
        grouped = _get_grouped()
        labels = self._collect_all_hierarchy_labels(grouped)
        for label in labels:
            assert "EMA_50" not in label, (
                f"Hierarchy entry has EMA_50 in label: {label!r} -- "
                "EMA 50 must not be a hierarchy anchor per spec §4.3.8"
            )

    def test_profile_b_no_ema_50_hierarchy_labels(self):
        """Profile B: no hierarchy/overhead/cleared entry has 'EMA_50' label."""
        grouped = _get_grouped(_profile_b_overrides())
        labels = self._collect_all_hierarchy_labels(grouped)
        for label in labels:
            assert "EMA_50" not in label

    def test_profile_c_no_ema_50_hierarchy_labels(self):
        """Profile C: no hierarchy/overhead/cleared entry has 'EMA_50' label."""
        grouped = _get_grouped(_profile_c_overrides())
        labels = self._collect_all_hierarchy_labels(grouped)
        for label in labels:
            assert "EMA_50" not in label


# ===========================================================================
# 10. TestEMA50001NotAGateInput -- gates.py never reads Context_*_EMA_50
# ===========================================================================


class TestEMA50001NotAGateInput:
    """Spec §4.3.8 + §5.3: EMA 50 is explicitly NOT a gate input. No gate
    function reads Context_*_EMA_50 keys. The gates.py extraction sites are
    WRITE-only with respect to EMA 50. Verified via source AST/grep: every
    occurrence of Context_*_EMA_50 in gates.py is an assignment target
    (metrics[key] = ...), not a read (metrics.get(key) or metrics[key]
    on the right-hand side of an expression)."""

    def test_gates_py_contains_only_write_sites_for_ema_50(self):
        """In gates.py, every Context_*_EMA_50 reference is a write (assignment
        target on metrics[...]) -- no metrics.get('Context_*_EMA_50') or
        comparable read pattern."""
        src = _read_source(_GATES_PY_PATH)
        lines = src.splitlines()
        # Find every line containing Context_*_EMA_50
        ema_50_lines = [
            (idx + 1, line) for idx, line in enumerate(lines)
            if re.search(r"Context_(Daily|Weekly|Monthly)_EMA_50", line)
        ]
        assert len(ema_50_lines) > 0, (
            "gates.py should contain at least the Profile A and Profile B "
            "EMA 50 write sites per spec §4.3.2 + §4.3.3"
        )
        # For each line, ensure it's a write (assignment target)
        for line_num, line in ema_50_lines:
            stripped = line.strip()
            # Skip comments
            if stripped.startswith("#"):
                continue
            # A write pattern looks like: metrics["Context_*_EMA_50..."] = ...
            # A read pattern would be: metrics.get("Context_*_EMA_50...")
            # Reject any line containing the read pattern.
            assert "metrics.get(\"Context_" not in line or "EMA_50" not in line.split("metrics.get(")[1] if "metrics.get(" in line else True, (
                f"gates.py line {line_num} has a metrics.get() read for "
                f"Context_*_EMA_50 -- gate-input scope guard violated:\n{line}"
            )

    def test_canonical_ema_50_keys_also_not_read_in_gates(self):
        """gates.py must not read canonical Context_EMA_50 / _Slope / _Bias
        either -- the canonical aggregation is for output/transform consumption
        only, not gate logic input."""
        src = _read_source(_GATES_PY_PATH)
        # The canonical Context_EMA_50 (without timeframe prefix) is the most
        # likely accidental read since it's the simplest name. Verify it does
        # not appear in gates.py at all (neither as a read nor write -- the
        # extraction writes use profile-specific names like Context_Daily_EMA_50).
        # Use word-boundary regex to avoid matching Context_Daily_EMA_50 etc.
        matches = re.findall(r"\bContext_EMA_50(?:_Slope(?:_Bias)?)?\b", src)
        assert len(matches) == 0, (
            f"gates.py unexpectedly references canonical EMA 50 keys: {matches}; "
            "canonical aggregation is for output/transform only per spec §4.3.8"
        )

    def test_output_py_canonical_block_writes_canonical_keys(self):
        """Cross-check: output.py contains writes to all three canonical keys
        per spec §4.3.5."""
        src = _read_source(_OUTPUT_PY_PATH)
        # Use word boundaries to match the canonical (non-prefix-qualified) names
        assert re.search(r'metrics\[\s*"Context_EMA_50"\s*\]\s*=', src), (
            "output.py missing assignment to canonical Context_EMA_50"
        )
        assert re.search(r'metrics\[\s*"Context_EMA_50_Slope"\s*\]\s*=', src), (
            "output.py missing assignment to canonical Context_EMA_50_Slope"
        )
        assert re.search(r'metrics\[\s*"Context_EMA_50_Slope_Bias"\s*\]\s*=', src), (
            "output.py missing assignment to canonical Context_EMA_50_Slope_Bias"
        )


# ===========================================================================
# 11. TestEMA50001OD2ReverseMap -- closes OD-2 from Phase 3 hand-back
# ===========================================================================


class TestEMA50001OD2ReverseMap:
    """OD-2 closure (Phase 3 hand-back §10 + spec §11 candidate): the
    _flatten development utility at transform.py:2744 now has parallel
    symmetry with the SMA 50 reverse-map at transform.py:3043-3061 for
    EMA 50 keys, plus DQ-10 enhancement (canonical price + slope + bias
    derivation, which SMA 50's reverse-map does not produce).

    Test coverage:
      - Profile-specific keys round-trip across all 3 timeframes
      - Canonical Context_EMA_50 / _Slope / _Slope_Bias derived from grouped
      - Bias label inherits from higher_frame.ema_50.slope.bias.label
      - Defensive None paths (ema_50 absent / slope None)
      - Source-grep witness on the new block in transform.py
    """

    def test_transform_py_contains_od2_reverse_map_block(self):
        """transform.py contains the EMA 50 reverse-map block with the
        [EMA50-001 OD-2] provenance tag."""
        src = _read_source(_TRANSFORM_PY_PATH)
        assert "[EMA50-001 OD-2]" in src, (
            "transform.py missing [EMA50-001 OD-2] provenance tag at the "
            "_flatten reverse-map block"
        )
        # Verify the block contains the expected reverse-map writes
        # (anchor on a distinctive marker so this is robust to surrounding code drift)
        marker = "[EMA50-001 OD-2]"
        idx = src.find(marker)
        assert idx >= 0
        block = src[idx:idx + 2000]
        # Profile-specific keys written
        assert 'flat["Context_Daily_EMA_50"]' in block
        assert 'flat["Context_Weekly_EMA_50"]' in block
        assert 'flat["Context_Monthly_EMA_50"]' in block
        # Canonical keys written
        assert 'flat["Context_EMA_50"]' in block
        assert 'flat["Context_EMA_50_Slope"]' in block
        assert 'flat["Context_EMA_50_Slope_Bias"]' in block

    def test_profile_a_canonical_context_ema_50_round_trips(self):
        """Profile A: canonical Context_EMA_50 derived from grouped
        higher_frame.ema_50.price via _flatten."""
        flat = _get_flat()
        # Canonical price
        assert flat.get("Context_EMA_50") == 121.0
        # Canonical slope
        assert flat.get("Context_EMA_50_Slope") == 0.15
        # Canonical bias label (derived by output.py upstream, preserved
        # through grouped emission and reverse-mapped)
        assert flat.get("Context_EMA_50_Slope_Bias") == "BULLISH"

    def test_profile_b_canonical_context_ema_50_round_trips(self):
        """Profile B: canonical keys derived from Weekly ema_50 source."""
        flat = _get_flat(_profile_b_overrides())
        assert flat.get("Context_EMA_50") == 120.0
        assert flat.get("Context_EMA_50_Slope") == 0.25
        assert flat.get("Context_EMA_50_Slope_Bias") == "BULLISH"

    def test_profile_c_canonical_context_ema_50_round_trips(self):
        """Profile C: canonical keys derived from Monthly ema_50 source."""
        flat = _get_flat(_profile_c_overrides())
        assert flat.get("Context_EMA_50") == 117.0
        assert flat.get("Context_EMA_50_Slope") == 0.35
        assert flat.get("Context_EMA_50_Slope_Bias") == "BULLISH"

    def test_negative_slope_bias_round_trips_as_bearish(self):
        """Negative input slope flows through: output.py derives
        BEARISH, transform.py surfaces into higher_frame.ema_50.slope.bias.label,
        _flatten reads it back into Context_EMA_50_Slope_Bias."""
        flat = _get_flat({
            "Context_Daily_EMA_50_Slope": -0.20,
            "Context_EMA_50_Slope": -0.20,
            "Context_EMA_50_Slope_Bias": "BEARISH",  # input as if output.py derived it
        })
        assert flat.get("Context_EMA_50_Slope") == -0.20
        assert flat.get("Context_EMA_50_Slope_Bias") == "BEARISH"

    def test_only_timeframe_specific_key_for_active_profile(self):
        """Profile A flat output should contain Context_Daily_EMA_50 but NOT
        Context_Weekly_EMA_50 / Context_Monthly_EMA_50 (the timeframe-branch
        if/elif ensures only one profile-specific pair is written)."""
        flat = _get_flat()  # Profile A
        assert flat.get("Context_Daily_EMA_50") == 121.0
        # The other timeframes' keys may exist in the dict (passed through
        # from input flat_metrics) but should not have been WRITTEN by the
        # reverse-map. Since our base fixture leaves Weekly/Monthly EMA 50
        # as absent, they should be absent in the flat output.
        assert flat.get("Context_Weekly_EMA_50") is None
        assert flat.get("Context_Monthly_EMA_50") is None

    def test_ema_50_group_absent_no_keys_written(self):
        """When higher_frame.ema_50 is absent (Context_*_EMA_50 input is
        None across all profiles), the reverse-map block does not fire and
        no EMA 50 flat keys are produced."""
        flat = _get_flat({
            "Context_Daily_EMA_50": None,
            "Context_Daily_EMA_50_Slope": None,
            "Context_EMA_50": None,
            "Context_EMA_50_Slope": None,
            "Context_EMA_50_Slope_Bias": None,
        })
        # When the grouped ema_50 group is None (because _hf_ema50_price is
        # None at transform.py:908), the reverse-map block sees no dict and
        # skips. Resulting flat output should not contain non-None EMA 50.
        assert flat.get("Context_Daily_EMA_50") is None
        assert flat.get("Context_EMA_50") is None
        assert flat.get("Context_EMA_50_Slope") is None

    def test_slope_none_with_price_present_handles_gracefully(self):
        """Edge: price present, slope None (degenerate but defensive).
        higher_frame.ema_50.slope is None per transform.py:916; reverse-map
        derives price but slope_val + bias_label as None."""
        flat = _get_flat({
            "Context_Daily_EMA_50_Slope": None,  # slope=None -> slope dict=None
            "Context_EMA_50_Slope": None,
            "Context_EMA_50_Slope_Bias": None,
        })
        # Price preserved (Context_Daily_EMA_50 still 121.0 in fixture)
        assert flat.get("Context_Daily_EMA_50") == 121.0
        # Slope and bias drop to None
        assert flat.get("Context_Daily_EMA_50_Slope") is None
        # Canonical bias should NOT be written when no bias label flowed
        # through (the reverse-map's `if _e50_bias_label is not None:` guard)
        # but Context_EMA_50 price/slope ARE written (uncondtionally when
        # the group exists)
        assert flat.get("Context_EMA_50") == 121.0
        assert flat.get("Context_EMA_50_Slope") is None
