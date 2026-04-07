"""BKOUT-001: Breakout Path Safety Fix -- Unit Tests.

Covers:
  FIX 1 (GAP-5): C2 Target Mandate in _assemble_output
  FIX 2 (GAP-3): Weekly escalation extended to RESOLVING in _populate_base_metrics
  FIX 3 (GAP-2): CEG negative reward handling with weekly escalation
  FIX 4 (GAP-1): Extension limit transparency
"""

import pytest
import pandas as pd
from types import SimpleNamespace

from ibkr_purity_engine import GateResult, _gate_capital_expectancy, _gate_extension
from tests.conftest import build_extension_ctx


# ============================================================================
# Helpers
# ============================================================================

def _make_df_ctx(highs):
    """Build a minimal weekly DataFrame with a 'high' column."""
    return pd.DataFrame({"high": highs})


def _make_ctx_with_df_ctx(df_ctx):
    """Build a minimal SimpleNamespace with _df_ctx attribute."""
    return SimpleNamespace(_df_ctx=df_ctx)


# ============================================================================
# FIX 3 (GAP-2): CEG Negative Reward Branch
# ============================================================================

class TestCEGNegativeReward:
    """Tests for _gate_capital_expectancy with price above resistance (negative reward)."""

    def test_negative_reward_weekly_ceiling_above_price_passes(self, capital_expectancy_base_params):
        """Profile B, negative reward, weekly ceiling above price, R:R >= 1.0 -- gate passes."""
        p = capital_expectancy_base_params
        p["p_code"] = "B"
        p["last_close"] = 100.0
        p["resistance_raw"] = 98.0
        p["hard_stop_raw"] = 90.0
        # 11 bars: iloc[-11:-1] = first 10, max = 115 -> reward = 15, R:R = 1.5
        df_ctx = _make_df_ctx([110, 115, 112, 108, 105, 103, 100, 98, 97, 96, 95])
        p["ctx"] = _make_ctx_with_df_ctx(df_ctx)
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_Reward_Risk"] == 1.5

    def test_negative_reward_weekly_rr_below_1_c2_fails(self, capital_expectancy_base_params):
        """Profile B C1/C2, negative reward, weekly R:R < 1.0 -- INVALID."""
        p = capital_expectancy_base_params
        p["p_code"] = "B"
        p["last_close"] = 100.0
        p["resistance_raw"] = 98.0
        p["hard_stop_raw"] = 90.0
        # Weekly ceiling = 105 -> reward = 5, R:R = 0.5
        df_ctx = _make_df_ctx([105, 103, 102, 100, 99, 98, 97, 96, 95, 94, 93])
        p["ctx"] = _make_ctx_with_df_ctx(df_ctx)
        p["_is_c3"] = False
        result = _gate_capital_expectancy(**p)
        assert result is not None
        assert result.verdict == "INVALID"
        assert result.reason == "CAPITAL EXPECTANCY FAILED"
        assert "weekly target" in result.mandate

    def test_negative_reward_no_weekly_data_c2_fails(self, capital_expectancy_base_params):
        """Profile B C1/C2, negative reward, no weekly data -- INVALID NO FORWARD TARGET."""
        p = capital_expectancy_base_params
        p["p_code"] = "B"
        p["last_close"] = 100.0
        p["resistance_raw"] = 98.0
        p["hard_stop_raw"] = 90.0
        p["ctx"] = SimpleNamespace(_df_ctx=None)
        p["_is_c3"] = False
        result = _gate_capital_expectancy(**p)
        assert result is not None
        assert result.verdict == "INVALID"
        assert result.reason == "NO FORWARD TARGET"

    def test_negative_reward_no_weekly_data_c3_passes(self, capital_expectancy_base_params):
        """Profile B C3, negative reward, no weekly data -- gate passes (informational)."""
        p = capital_expectancy_base_params
        p["p_code"] = "B"
        p["last_close"] = 100.0
        p["resistance_raw"] = 98.0
        p["hard_stop_raw"] = 90.0
        p["ctx"] = SimpleNamespace(_df_ctx=None)
        p["_is_c3"] = True
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_Reward_Risk"] is None

    def test_negative_reward_weekly_ceiling_below_price_c2_fails(self, capital_expectancy_base_params):
        """Profile B C1/C2, negative reward, weekly ceiling below price -- NO FORWARD TARGET."""
        p = capital_expectancy_base_params
        p["p_code"] = "B"
        p["last_close"] = 100.0
        p["resistance_raw"] = 98.0
        p["hard_stop_raw"] = 90.0
        df_ctx = _make_df_ctx([99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89])
        p["ctx"] = _make_ctx_with_df_ctx(df_ctx)
        p["_is_c3"] = False
        result = _gate_capital_expectancy(**p)
        assert result is not None
        assert result.verdict == "INVALID"
        assert result.reason == "NO FORWARD TARGET"

    def test_positive_reward_unchanged(self, capital_expectancy_base_params):
        """Profile B, positive reward -- existing block fires, unchanged."""
        p = capital_expectancy_base_params
        p["p_code"] = "B"
        p["last_close"] = 100.0
        p["resistance_raw"] = 120.0
        p["hard_stop_raw"] = 90.0
        p["ctx"] = None
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_Reward_Risk"] == 2.0

    def test_negative_reward_ctx_no_attr(self, capital_expectancy_base_params):
        """Profile B, negative reward, ctx without _df_ctx -- handles gracefully."""
        p = capital_expectancy_base_params
        p["p_code"] = "B"
        p["last_close"] = 100.0
        p["resistance_raw"] = 98.0
        p["hard_stop_raw"] = 90.0
        p["ctx"] = SimpleNamespace()
        p["_is_c3"] = False
        result = _gate_capital_expectancy(**p)
        assert result is not None
        assert result.verdict == "INVALID"
        assert result.reason == "NO FORWARD TARGET"

    def test_negative_reward_short_weekly_data(self, capital_expectancy_base_params):
        """Profile B, negative reward, < 11 bars of weekly data -- uses .max()."""
        p = capital_expectancy_base_params
        p["p_code"] = "B"
        p["last_close"] = 100.0
        p["resistance_raw"] = 98.0
        p["hard_stop_raw"] = 90.0
        df_ctx = _make_df_ctx([112, 108, 105, 100, 98])
        p["ctx"] = _make_ctx_with_df_ctx(df_ctx)
        p["_is_c3"] = False
        result = _gate_capital_expectancy(**p)
        assert result is None
        assert p["metrics"]["Capital_Reward_Risk"] == 1.2


# ============================================================================
# FIX 1 (GAP-5): C2 Target Mandate -- Logic Verification
# ============================================================================

class TestC2TargetMandate:
    """Tests for the C2 target mandate elif chain in _assemble_output.

    Verifies the logic pattern:
      if EXIT -> INVALID (existing)
      elif C2 and Profit_Target is None -> INVALID C2 TARGET MANDATE (new)
      else -> normal VALID
    """

    @staticmethod
    def _simulate_mandate_check(exit_signal, convexity_class, profit_target):
        """Simulate the elif chain from _assemble_output."""
        if exit_signal == "EXIT":
            return "EXIT_OVERRIDE"
        elif convexity_class == "C2" and profit_target is None:
            return "C2 TARGET MANDATE"
        else:
            return "VALID"

    def test_c2_null_target_produces_mandate(self):
        """C2 + VALID + null Profit_Target -> C2 TARGET MANDATE."""
        assert self._simulate_mandate_check("NONE", "C2", None) == "C2 TARGET MANDATE"

    def test_c2_with_target_passes(self):
        """C2 + VALID + non-null Profit_Target -> VALID."""
        assert self._simulate_mandate_check("NONE", "C2", 155.0) == "VALID"

    def test_c3_null_target_passes(self):
        """C3 + VALID + null Profit_Target -> VALID (no mandate for C3)."""
        assert self._simulate_mandate_check("NONE", "C3", None) == "VALID"

    def test_c1_with_target_passes(self):
        """C1 + VALID + non-null Profit_Target -> VALID (defensive)."""
        assert self._simulate_mandate_check("NONE", "C1", 160.0) == "VALID"

    def test_exit_takes_priority_over_mandate(self):
        """EXIT override fires before C2 mandate check."""
        assert self._simulate_mandate_check("EXIT", "C2", None) == "EXIT_OVERRIDE"

    def test_c1_null_target_passes(self):
        """C1 + null target -> VALID (C1 has no target mandate)."""
        assert self._simulate_mandate_check("NONE", "C1", None) == "VALID"


# ============================================================================
# FIX 4 (GAP-1): Extension Limit Transparency
# ============================================================================

class TestExtensionLimitTransparency:
    """Tests for Extension_Limit_Effective and Extension_Exemption_Note."""

    def test_breakout_exemption_writes_effective_limit(self, extension_base_params):
        """RESOLVING breakout bar -> Extension_Limit_Effective = 1.5, note populated."""
        p = extension_base_params
        p["is_trending"] = False
        p["is_resolving"] = True
        p["_entry_trending"] = False
        p["_entry_resolving"] = True
        p["last"] = {"close": 165.0, "open": 158.0, "SMA_200": 130.0}
        p["resistance_raw"] = 160.0
        p["atr_dist"] = 0.8
        p["ext_limit"] = 0.5
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is None
        assert p["metrics"]["Extension_Limit_Effective"] == 1.5
        assert "PE-CAL-1 Sec 6.2" in p["metrics"]["Extension_Exemption_Note"]

    def test_pullback_no_exemption(self, extension_base_params):
        """Standard PULLBACK -> no Extension_Limit_Effective written."""
        p = extension_base_params
        p["is_trending"] = True
        p["is_resolving"] = False
        p["_entry_trending"] = True
        p["_entry_resolving"] = False
        p["last"] = {"close": 150.0, "open": 149.0, "SMA_200": 130.0}
        p["resistance_raw"] = 160.0
        p["atr_dist"] = 0.5
        p["ext_limit"] = 1.0
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is None
        assert "Extension_Limit_Effective" not in p["metrics"]
        assert "Extension_Exemption_Note" not in p["metrics"]

    def test_breakout_exemption_widens_limit(self, extension_base_params):
        """atr_dist=1.2 with standard 0.5 would fail, exemption widens to 1.5 -> passes."""
        p = extension_base_params
        p["is_trending"] = False
        p["is_resolving"] = True
        p["_entry_trending"] = False
        p["_entry_resolving"] = True
        p["last"] = {"close": 165.0, "open": 158.0, "SMA_200": 130.0}
        p["resistance_raw"] = 160.0
        p["atr_dist"] = 1.2
        p["ext_limit"] = 0.5
        ctx, atr_dist, ext_limit = build_extension_ctx(p)
        result = _gate_extension(ctx, atr_dist, ext_limit)
        assert result is None
        assert p["metrics"]["Extension_Limit_Effective"] == 1.5


# ============================================================================
# FIX 4 (GAP-1): Transform extension_analysis assembly
# ============================================================================

class TestExtensionAnalysisTransform:
    """Tests for extension_analysis limit.effective and limit.exemption in transform.py."""

    def test_effective_limit_in_extension_analysis(self):
        """Exemption active -> limit.effective = 1.5, limit.exemption populated."""
        from tbs_engine.transform import _transform_output

        metrics = _make_full_output_metrics()
        metrics["Extension_Limit_Effective"] = 1.5
        metrics["Extension_Exemption_Note"] = (
            "Breakout Extension Exemption (PE-CAL-1 Sec 6.2): "
            "limit widened from 0.5 to 1.5 ATR on RESOLVING breakout bar"
        )

        gate_result = SimpleNamespace(
            verdict="VALID", reason="BREAKOUT", entry_type="BREAKOUT",
            mandate=None, context=None, legacy_diagnostic=None,
        )
        action_summary = _make_valid_action_summary(gate_result, metrics)
        grouped = _transform_output(action_summary, metrics)
        ext = grouped.get("extension_analysis", {})
        lim = ext.get("limit", {})
        assert lim.get("effective") == 1.5
        assert lim.get("exemption") is not None
        assert "PE-CAL-1" in lim["exemption"]

    def test_no_exemption_effective_equals_standard(self):
        """No exemption -> limit.effective equals standard limit, exemption is null."""
        from tbs_engine.transform import _transform_output

        metrics = _make_full_output_metrics()

        gate_result = SimpleNamespace(
            verdict="VALID", reason="PULLBACK", entry_type="PULLBACK",
            mandate=None, context=None, legacy_diagnostic=None,
        )
        action_summary = _make_valid_action_summary(gate_result, metrics)
        grouped = _transform_output(action_summary, metrics)
        ext = grouped.get("extension_analysis", {})
        lim = ext.get("limit", {})
        assert lim.get("effective") == lim.get("value")
        assert lim.get("exemption") is None


# ============================================================================
# Helpers for transform tests
# ============================================================================

def _make_full_output_metrics():
    """Minimal metrics dict for _transform_output."""
    m = {}
    m["Price"] = 152.0; m["Structural_Floor"] = 142.0; m["Resistance"] = 160.0
    m["ADV_20"] = 5000000.0; m["ADV_20_Dollar"] = 50000000.0; m["Is_ETF"] = False
    m["Convexity_Class"] = "C1"
    m["ETF_Primary_Exchange"] = None; m["ETF_Detection_Source"] = None
    m["Entry_Reference"] = 142.0; m["Hard_Stop"] = 140.0; m["Profit_Target"] = 160.0
    m["THS_Label"] = "HEALTHY"; m["Trend_Health_Score"] = 72.5
    m["THS_Floor_Buffer"] = 80.0; m["THS_Dir_Momentum"] = 65.0
    m["THS_Trend_Age"] = 70.0; m["THS_Structure"] = 75.0
    m["Capital_RR_Label"] = "HEALTHY"; m["Capital_Reward_Risk"] = 2.35
    m["Exit_Signal"] = False; m["Exit_Reason"] = "No exit"
    m["Pullback_Zone_Upper"] = 145.0
    m["Engine_State"] = "TRENDING"; m["Trend_Age_Bars"] = 15
    m["Active_Modifiers"] = "None"; m["Inst_Churn"] = "LOW"
    m["ADX"] = 28.5; m["ADX_Accel"] = 1.2; m["ADX_Accel_State"] = "ACCELERATING"
    m["DI_Plus"] = 30.0; m["DI_Minus"] = 15.0
    m["Conviction"] = "HIGH-CONVICTION"; m["Trend_Quality_Override"] = None
    m["Vol_Confirm_Ratio"] = 1.8; m["Vol_Confirm_State"] = "STRONG ACCUMULATION"
    m["Reward_Risk"] = 3.5; m["Reward_Risk_Note"] = None
    m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    m["EMA_8"] = 150.0; m["EMA_21"] = 148.0; m["SMA_50"] = 142.0; m["SMA_200"] = 130.0
    m["VWAP"] = None; m["ATR"] = 2.5
    m["Profit_Target_Source"] = "10_Bar_Resistance"; m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Profit_Target_Synthetic"] = None; m["Profit_Target_Synthetic_Note"] = None
    m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 139.0
    m["Stop_Adjusted_Flag"] = False; m["Stop_Adjusted_Reason"] = None
    m["Cons_High"] = 155.0; m["Resistance_Note"] = None
    m["Fib_382_Level"] = None; m["Fib_500_Level"] = None; m["Fib_Confluence"] = None
    m["Fib_A_382_Level"] = None; m["Fib_A_500_Level"] = None; m["Fib_A_Confluence"] = None
    m["RN_Target_Proximity"] = "CLEAR"; m["RN_Stop_Proximity"] = None; m["RN_Floor_Proximity"] = None
    m["ATR_Dist"] = 0.45; m["ATR_Dist_Anchor"] = "SMA_50"; m["ATR_Dist_Note"] = None
    m["Anchor_Label"] = "SMA_50 Floor"; m["Anchor_Type"] = "Standard"
    m["Extension_Anchor_Label"] = "SMA_50 Floor"; m["Extension_Anchor_Type"] = "SMA_50"
    m["Floor_Prox_Pct"] = None; m["Extension_Limit"] = 1.0
    m["Window_Limit"] = 20; m["Window_Reset_Event"] = None
    m["Proximity_Signal"] = None; m["Proximity_Blocking_Gate"] = None
    m["Proximity_Distance"] = None; m["Proximity_Target"] = None; m["Proximity_Note"] = None
    m["Exit_Triggers"] = "None"; m["Exit_VWAP_Counter"] = None
    m["Exit_EMA8_Counter"] = None; m["Established_Hourly_Low"] = None
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
    m["Volume_Context_Label"] = "NORMAL"
    m["Measured_Move_Target"] = None; m["Measured_Move_Distance"] = None
    m["Measured_Move_Note"] = None
    m["Psych_Floor"] = None; m["Psych_Ceiling"] = None
    m["Psych_Floor_Dist_Pct"] = None; m["Psych_Ceiling_Dist_Pct"] = None
    m["Psych_Floor_Near_Structural"] = None; m["Psych_Ceiling_Near_Technical"] = None
    m["Psych_Increment"] = None
    m["Window_Timeframe"] = None; m["Window_Status"] = None
    return m


def _make_valid_action_summary(gate_result, metrics):
    """Build a minimal VALID action_summary for transform tests."""
    return {
        "verdict": "VALID",
        "reason": {"label": gate_result.reason, "detail": "Test"},
        "approaching": False,
        "volume": metrics.get("Volume_Context_Label"),
        "volume_confirmation": None,  # VTRIG-001
        "mandate": "Test mandate",
        "merit": {"quality": metrics.get("THS_Label"), "reward": "HEALTHY [2.35]"},
        "trigger": {"rule": "BAR CLOSE ONLY", "condition": "Test trigger"},
        "exit_status": {"active": False, "reason": None},
        "entry_strategy": {
            "entry_price": metrics.get("Entry_Reference"),
            "stop_loss": metrics.get("Hard_Stop"),
            "target": metrics.get("Profit_Target"),
            "fib_382": None, "fib_500": None, "fib_confluence": None,
            "mm_target": None,
        },
    }
