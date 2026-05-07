"""RALLY-TRIG-001: rally.confluence.trigger -> rally.confluence.trigger_historical.

Disambiguation rename: post-1E refactor, `entry_zone.trigger` reflects the
effective evaluation protocol while `rally.confluence.trigger` continued to
reflect the historical Window_Reset_Event. The two same-named fields with
different semantics caused operator confusion (originating S129 reproducer
on REL.L and 5 other tickers).

Per spec §3.1, the chosen remediation is Option (a): rename the rally-side
field to `trigger_historical`, aligning with the established
`execution_window.trigger_historical` precedent in the same module
(transform.py:~1554).

Test cases per spec §6.2:
    TC-1: field rename (old absent / new present)
    TC-2: value=PULLBACK
    TC-3: value=BREAKOUT
    TC-4: value=RECLAIM
    TC-5: REL.L originating-bug fallback-path pattern (asymmetry — both
          fields populate, but with different semantics, no name collision)
    TC-6: non-fallback BREAKOUT consistency (both fields = "BREAKOUT")
    TC-7: native PULLBACK consistency (both fields = "PULLBACK")
    TC-8: PE-44 invariance regression-witness (label / desc unchanged)

Differential expectation: TC-1 and TC-5 FAIL pre-fix and PASS post-fix
(see hand-back §4 for captured pre-fix failure messages).

Run: pytest tests/unit/test_rallytrig001_rally_confluence_trigger_rename.py -v
"""
import pytest
from tbs_engine.transform import _transform_output


# ---------------------------------------------------------------------------
# Helpers — independent of test_pe44_confluence.py per spec §6.1; same shape
# as the established PE-44 fixture pattern but authored locally so this test
# file is self-contained and does not couple to PE-44's fixture lifecycle.
# ---------------------------------------------------------------------------

def _as(verdict="INVALID"):
    """Build a minimal action_summary dict for _transform_output."""
    return {
        "verdict": verdict,
        "reason": {"label": "EXTENDED", "detail": "n/a"},
        "approaching": False,
        "volume": "NEUTRAL",
        "exit_status": {"active": False, "reason": None},
    }


def _metrics(**overrides):
    """Default flat_metrics dict; overrides applied on top.

    Mirrors test_pe44_confluence.py defaults so the rally object populates
    (Fib_A_382/500 + MM_Target present, Fib_A_Confluence labelled).
    """
    base = {
        "Price": 218.44, "Structural_Floor": 217.0, "Resistance": 225.5,
        "ADV_20": 4353443, "ADV_20_Dollar": 50000000,
        "Is_ETF": False, "Convexity_Class": "C-2",
        "EMA_8": 218.36, "EMA_21": 217.01, "SMA_50": 216.41, "SMA_200": 223.11,
        "ATR": 3.89, "VWAP": 217.0,
        "Engine_State": "TRENDING", "Engine_State_Desc": "ADX > 20",
        "Trend_Age_Bars": 2, "Trend_Age_Max": 30,
        "Active_Modifiers": "None", "Active_Modifiers_List": [],
        "Inst_Churn": "CLEAR (No Churn)",
        "ADX": 28.0, "ADX_Accel": 0.5, "ADX_Accel_State": "ACCELERATING",
        "DI_Plus": 30.0, "DI_Minus": 18.0, "DI_Spread": 12.0, "DI_Bias": "BULLISH",
        "Trend_Health_Score": 65.0, "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 50.0, "THS_Floor_Buffer_Label": "ACCEPTABLE",
        "THS_Dir_Momentum": 60.0, "THS_Dir_Momentum_Label": "HEALTHY",
        "THS_Trend_Age": 80.0, "THS_Trend_Age_Label": "STRONG",
        "THS_Structure": 55.0, "THS_Structure_Label": "ACCEPTABLE",
        "Exit_Signal": "CLEAR", "Exit_Triggers": [], "Exit_Reason": None,
        "Vol_Confirm_Ratio": 0.85, "Vol_Confirm_State": "STRONG ACCUMULATION",
        "Vol_Confirm_Bias": "BULLISH",
        "Vol_PoC_Price": 216.62, "Vol_PoC_Distance_ATR": 0.47,
        "Vol_PoC_Position": "ABOVE_POC", "PoC_Bias": "BULLISH",
        "PoC_Bias_Desc": "In profit at this level -- acts as support",
        "AVWAP_Price": 219.49, "AVWAP_Position": "BELOW",
        "AVWAP_Distance_ATR": -0.53,
        "AVWAP_Bias": "BEARISH", "AVWAP_Bias_Desc": "Price below avg cost -- overhead resistance",
        "Volume_Context_Label": "ACCUMULATION DOMINANT",
        "Vol_Summary_Label": "ACCUMULATION DOMINANT",
        "Vol_Summary_Bias": "BULLISH", "Vol_Summary_Confidence": "SPLIT",
        "Vol_Summary_Detail": "Ratio BULLISH + PoC BULLISH + AVWAP BEARISH",
        "Vol_Histogram_Period": "3 days",
        "RVOL_Value": 1.35, "RVOL_Label": "ELEVATED",
        "Anchor_Label": "VWAP (Baseline Floor)", "Anchor_Type": "Standard",
        "Floor_Anchor_Type": "VWAP", "Floor_Anchor_Label": "Intraday institutional value level",
        "Extension_Anchor_Type": "VWAP", "Extension_Anchor_Label": "Intraday institutional value level",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Failure_Context": None, "Floor_Breach_Dist": None,
        "Floor_Failure_Reclaim": None, "Floor_Failure_Threshold": 8,
        "Context_SMA50_Slope_Bias": "BEARISH",
        "Context_Golden_Cross": True, "Context_Price_vs_SMA200": 60.14,
        "Context_SMA200": 158.3, "Context_Daily_SMA50": 226.71,
        "Context_Daily_SMA50_Slope": -0.2,
        "Context_EMA_8": 220.15, "Context_EMA_21": 218.90,
        "Context_EMA_Stacked": True, "Context_EMA_Bias": "BULLISH",
        "Context_EMA_Bias_Desc": "Daily EMA 8 above Daily EMA 21",
        "Profit_Target": 241.37, "Profit_Target_Source": "DAILY_CTX",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "Hard_Stop": 207.83, "Hard_Stop_Note": None,
        "Original_Hard_Stop": 211.16, "Stop_Adjusted_Flag": True,
        "Stop_Adjusted_Reason": "Hourly low proximity",
        "Pullback_Zone_Upper": 218.94, "Entry_Reference": 217.0,
        "Fib_A_382_Level": 217.94, "Fib_A_500_Level": 216.90,
        "Fib_A_Confluence": "CONFLUENCE_382",
        "MM_Target": 250.12, "MM_Rally_ATR": 2.3,
        "Window_Limit": 4, "Window_Reset_Event": "PULLBACK",
        "window_count": 2,
        "ATR_Dist": 0.38, "ATR_Dist_Anchor": "VWAP",
        "ATR_Dist_Note": None, "Extension_Limit": 1.5,
        "Trend_Quality_Override": None,
        "Psych_Floor": 200.0, "Psych_Ceiling": 225.0,
        "Psych_Floor_Dist_Pct": 8.44, "Psych_Ceiling_Dist_Pct": 3.0,
        "Psych_Floor_Near_Technical": False, "Psych_Floor_Near_Structural": False,
        "Psych_Ceiling_Near_Technical": True, "Psych_Increment": 25.0,
        "RN_Target_Proximity": "CLEAR", "RN_Stop_Proximity": "CLEAR",
        "RN_Floor_Proximity": "CLEAR",
        "Reward_Risk": 3.5, "Reward_Risk_Note": None,
        "Capital_Reward_Risk": 2.15, "Capital_RR_Label": "HEALTHY",
        "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Price R:R 3.50 >= 2.0. Capital R:R 2.15 (HEALTHY).",
        "Expectancy_Threshold": 2.0, "Expectancy_Threshold_Note": None,
        "Data_Basis": "SWING analysis based on completed bar 09:30-10:30 ET.",
    }
    base.update(overrides)
    return base


def _run(metrics_overrides):
    """Build metrics + run _transform_output; return (entry_zone, confluence)."""
    m = _metrics(**metrics_overrides)
    out = _transform_output(_as(), m)
    ts = out.get("trade_setup", {})
    rally = ts.get("rally", {}) or {}
    return ts.get("entry_zone", {}), rally.get("confluence", {})


# ===========================================================================
# TestRallyTrigHistorical — single class per spec §6.1
# ===========================================================================

class TestRallyTrigHistorical:
    """RALLY-TRIG-001 unit tests: rally.confluence.trigger_historical rename."""

    # -- TC-1 ----------------------------------------------------------------

    def test_field_renamed_to_trigger_historical(self):
        """TC-1: rally.confluence carries 'trigger_historical', not 'trigger'."""
        _, conf = _run({"Window_Reset_Event": "PULLBACK",
                        "Fib_A_Confluence": "CONFLUENCE_382"})
        assert "trigger_historical" in conf, \
            "rally.confluence missing required key 'trigger_historical' post-rename"
        assert "trigger" not in conf, \
            "rally.confluence still emits legacy key 'trigger' — rename incomplete"

    # -- TC-2 ----------------------------------------------------------------

    def test_trigger_historical_value_pullback(self):
        """TC-2: trigger_historical == 'PULLBACK' on native PULLBACK trigger."""
        _, conf = _run({"Window_Reset_Event": "PULLBACK",
                        "Fib_A_Confluence": "CONFLUENCE_382"})
        assert conf.get("trigger_historical") == "PULLBACK"

    # -- TC-3 ----------------------------------------------------------------

    def test_trigger_historical_value_breakout(self):
        """TC-3: trigger_historical == 'BREAKOUT' on BREAKOUT historical trigger."""
        # Set BRK_Model_Active=True so this is a non-fallback path; then the
        # historical trigger is also the effective trigger and there is no
        # asymmetry. (The rename target value is still BREAKOUT either way —
        # `_trigger_type` is keyed off `Window_Reset_Event` independent of
        # `_render_as_pullback_fallback`.)
        _, conf = _run({"Window_Reset_Event": "BREAKOUT",
                        "BRK_Model_Active": True,
                        "Fib_A_Confluence": "ABOVE_FIBS"})
        assert conf.get("trigger_historical") == "BREAKOUT"

    # -- TC-4 ----------------------------------------------------------------

    def test_trigger_historical_value_reclaim(self):
        """TC-4: trigger_historical == 'RECLAIM' on RECLAIM historical trigger."""
        _, conf = _run({"Window_Reset_Event": "RECLAIM",
                        "Fib_A_Confluence": "CONFLUENCE_382"})
        assert conf.get("trigger_historical") == "RECLAIM"

    # -- TC-5 — originating-bug REL.L pattern -------------------------------

    def test_asymmetry_fallback_path_REL_L_pattern(self):
        """TC-5: REL.L pattern — entry_zone.trigger='PULLBACK' (effective);
        rally.confluence.trigger_historical='BREAKOUT' (historical). No collision."""
        # Fallback condition per transform.py:1388-1390 —
        # _thesis_failed=True triggers _render_as_pullback_fallback, which
        # makes _effective_trigger='PULLBACK' while _trigger_type stays
        # 'BREAKOUT' (historical Window_Reset_Event).
        ez, conf = _run({"Window_Reset_Event": "BREAKOUT",
                         "Breakout_Thesis_Status": "FAILED",
                         "BRK_Model_Active": False,
                         "Fib_A_Confluence": "ABOVE_FIBS"})
        # Effective trigger reflects the protocol that produced R:R / stop /
        # target on this run (PULLBACK on fallback paths).
        assert ez.get("trigger") == "PULLBACK", \
            f"entry_zone.trigger should be PULLBACK on fallback path, got {ez.get('trigger')!r}"
        # Historical trigger reflects the dormant Window_Reset_Event.
        assert conf.get("trigger_historical") == "BREAKOUT", \
            f"rally.confluence.trigger_historical should be BREAKOUT (historical), got {conf.get('trigger_historical')!r}"
        # No field-name collision: the legacy 'trigger' key must be absent
        # from rally.confluence so the two same-output fields cannot be
        # confused for each other.
        assert "trigger" not in conf, \
            "rally.confluence still emits legacy 'trigger' — collision with entry_zone.trigger"

    # -- TC-6 ----------------------------------------------------------------

    def test_consistency_non_fallback_breakout(self):
        """TC-6: non-fallback BREAKOUT — entry_zone.trigger and
        rally.confluence.trigger_historical agree on 'BREAKOUT'."""
        # No thesis failure + BRK_Model_Active=True → no fallback → effective
        # trigger == historical trigger.
        ez, conf = _run({"Window_Reset_Event": "BREAKOUT",
                         "BRK_Model_Active": True,
                         "Fib_A_Confluence": "ABOVE_FIBS"})
        assert ez.get("trigger") == "BREAKOUT"
        assert conf.get("trigger_historical") == "BREAKOUT"

    # -- TC-7 ----------------------------------------------------------------

    def test_consistency_native_pullback(self):
        """TC-7: native PULLBACK — both fields agree on 'PULLBACK'."""
        ez, conf = _run({"Window_Reset_Event": "PULLBACK",
                         "Fib_A_Confluence": "CONFLUENCE_382"})
        assert ez.get("trigger") == "PULLBACK"
        assert conf.get("trigger_historical") == "PULLBACK"

    # -- TC-8 — PE-44 invariance regression-witness -------------------------

    def test_pe44_existing_assertions_invariant(self):
        """TC-8: rename did not damage adjacent fields — label and desc
        on rally.confluence remain populated correctly (PE-44 contract)."""
        _, conf = _run({"Window_Reset_Event": "PULLBACK",
                        "Fib_A_Confluence": "CONFLUENCE_382"})
        # label mirrors Fib_A_Confluence on non-BREAKOUT triggers (PE-44).
        assert conf.get("label") == "CONFLUENCE_382"
        # desc carries the institutional-floor confluence prose for
        # PULLBACK + CONFLUENCE_382 (PE-44 _confluence_desc_map entry).
        desc = conf.get("desc") or ""
        assert "Institutional floor" in desc
        assert "38.2%" in desc
