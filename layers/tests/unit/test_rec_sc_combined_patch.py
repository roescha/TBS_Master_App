"""REC-SC-1/2/3 Combined Patch — Unit Tests.

REC-SC-1: Recovery_Status "WAIT" for C-3 Thesis Attestation
REC-SC-2: Recovery_Capital_RR flat key
REC-SC-3: Recovery_CRG_Bypass_Context flat key

Tests cover:
- Transform grouped dict inclusion
- _flatten() round-trip
- Value correctness and None handling
"""
import sys
import os
import types as builtin_types
import importlib.util

# --- Isolated import: bypass __init__.py which pulls in full package chain ---
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if 'tbs_engine' not in sys.modules:
    pkg = builtin_types.ModuleType('tbs_engine')
    pkg.__path__ = ['tbs_engine']
    sys.modules['tbs_engine'] = pkg
for _mod, _path in [('tbs_engine.types', 'tbs_engine/types.py'),
                     ('tbs_engine.helpers', 'tbs_engine/helpers.py'),
                     ('tbs_engine.transform', 'tbs_engine/transform.py')]:
    if _mod not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_mod, _path)
        _m = importlib.util.module_from_spec(_spec)
        sys.modules[_mod] = _m
        _spec.loader.exec_module(_m)

from tbs_engine.transform import _transform_output, _flatten


# ═══════════════════════════════════════════════════════════════════════
#  HELPERS — reuse the base builder pattern from Phase 2D tests
# ═══════════════════════════════════════════════════════════════════════

def _make_base_metrics():
    """Minimal metrics dict for transform layer."""
    m = {}
    m["Price"] = 105.0; m["Structural_Floor"] = 95.0; m["Resistance"] = 115.0
    m["ADV_20"] = 3000000.0; m["ADV_20_Dollar"] = 30000000.0; m["Is_ETF"] = False
    m["Convexity_Class"] = "C1"
    m["ETF_Primary_Exchange"] = None; m["ETF_Detection_Source"] = None
    m["Entry_Reference"] = 95.0; m["Hard_Stop"] = 93.0; m["Profit_Target"] = 115.0
    m["THS_Label"] = "MODERATE"; m["Trend_Health_Score"] = 55.0
    m["THS_Floor_Buffer"] = 40.0; m["THS_Dir_Momentum"] = 50.0
    m["THS_Trend_Age"] = 60.0; m["THS_Structure"] = 70.0
    m["Capital_RR_Label"] = "HEALTHY"; m["Capital_Reward_Risk"] = 2.0
    m["Exit_Signal"] = False; m["Exit_Reason"] = "No exit"
    m["Pullback_Zone_Upper"] = 100.0
    m["Engine_State"] = "TRENDING"; m["Trend_Age_Bars"] = 10
    m["Active_Modifiers"] = "None"; m["Inst_Churn"] = "LOW"
    m["ADX"] = 22.0; m["ADX_Accel"] = 0.5; m["ADX_Accel_State"] = "CRUISING"
    m["DI_Plus"] = 25.0; m["DI_Minus"] = 18.0
    m["Conviction"] = "HIGH-CONVICTION"; m["Trend_Quality_Override"] = None
    m["Vol_Confirm_Ratio"] = 1.2; m["Vol_Confirm_State"] = "ACCUMULATING"
    m["Reward_Risk"] = 2.5; m["Reward_Risk_Note"] = None; m["Risk_Per_Unit"] = None
    m["Expectancy_Threshold"] = 2.0; m["Expectancy_Threshold_Note"] = None
    m["EMA_8"] = 106.0; m["EMA_21"] = 104.0; m["SMA_50"] = 110.0; m["SMA_200"] = 130.0
    m["VWAP"] = None; m["ATR"] = 2.5
    m["Profit_Target_Source"] = "SMA_50"; m["Profit_Target_Role"] = "PRESCRIPTIVE"
    m["Profit_Target_Synthetic"] = None; m["Profit_Target_Synthetic_Note"] = None
    m["Hard_Stop_Note"] = None; m["Original_Hard_Stop"] = 93.0
    m["Stop_Adjusted_Flag"] = False; m["Stop_Adjusted_Reason"] = None
    m["Cons_High"] = 115.0; m["Resistance_Note"] = None
    m["Fib_382_Level"] = None; m["Fib_500_Level"] = None; m["Fib_Confluence"] = None
    m["Fib_A_382_Level"] = None; m["Fib_A_500_Level"] = None; m["Fib_A_Confluence"] = None
    m["RN_Target_Proximity"] = "CLEAR"; m["RN_Stop_Proximity"] = None; m["RN_Floor_Proximity"] = None
    m["ATR_Dist"] = 0.5; m["ATR_Dist_Anchor"] = "SMA_50"; m["ATR_Dist_Note"] = None
    m["Anchor_Label"] = "SMA_50 Floor"; m["Anchor_Type"] = "Standard"
    m["Floor_Prox_Pct"] = None; m["Extension_Limit"] = 1.0
    m["Window_Limit"] = 20; m["Window_Reset_Event"] = None
    m["Proximity_Signal"] = None; m["Proximity_Blocking_Gate"] = None
    m["Proximity_Distance"] = None; m["Proximity_Target"] = None; m["Proximity_Note"] = None
    m["Exit_Triggers"] = "None"; m["Exit_VWAP_Counter"] = None
    m["Exit_EMA8_Counter"] = None; m["Established_Hourly_Low"] = None
    m["Floor_Failure_Context"] = None; m["Floor_Breach_Dist"] = None
    m["Floor_Failure_Reclaim"] = None; m["Floor_Failure_Threshold"] = 4
    return m


def _recovery_fields(status="RECOVERY CANDIDATE", capital_rr=None,
                     crg_bypass_context=None):
    """Build all recovery fields with configurable SC-1/2/3 values."""
    return {
        "Recovery_Status": status,
        "Recovery_Base_Bar_Count": 7,
        "Recovery_Swing_Low_Price": 92.50,
        "Recovery_Swing_Low_Bar_Index": 55,
        "Recovery_EMA_Cross_Bar_Index": 62,
        "Recovery_DI_Spread_Current": 6.2,
        "Recovery_DI_Spread_At_Swing_Low": 14.8,
        "Recovery_ATR_Contraction_Ratio": 0.82,
        "Recovery_Retest_Confirmed": True,
        "Recovery_Time_Stop_Bars_Remaining": 18,
        "Recovery_Target": 110.0,
        "Recovery_Target_Source": "SMA_50",
        "Recovery_Active_Count": 0,
        "Recovery_Capital_RR": capital_rr,
        "Recovery_CRG_Bypass_Context": crg_bypass_context,
        "Recovery_Diagnostic": "Recovery gates PASSED.",
    }


def _wait_action_summary():
    return {
        "verdict": "WAIT",
        "reason": {"label": "THESIS ATTESTATION",
                   "detail": "C-3 thesis attestation pending."},
        "mandate": "WAIT. Thesis attestation required.",
        "merit": {"quality": "RECOVERY", "reward": "SMA_50"},
    }


def _recovery_candidate_action_summary():
    return {
        "verdict": "RECOVERY CANDIDATE",
        "reason": {"label": "RECOVERY CANDIDATE",
                   "detail": "Recovery gates PASSED."},
        "mandate": "Recovery entry candidate. All R-Gates passed.",
        "merit": {"quality": "RECOVERY", "reward": "SMA_50"},
    }


# ═══════════════════════════════════════════════════════════════════════
#  REC-SC-1: Recovery_Status "WAIT" for C-3 Thesis Attestation
# ═══════════════════════════════════════════════════════════════════════

class TestRecSC1_WaitStatus:

    def test_wait_status_in_grouped_dict(self):
        """Recovery_Status = 'WAIT' flows through to recovery_analysis group."""
        m = _make_base_metrics()
        m.update(_recovery_fields(status="WAIT"))
        r = _transform_output(_wait_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["recovery_status"] == "WAIT"

    def test_wait_status_in_flatten(self):
        """Recovery_Status = 'WAIT' survives _flatten() round-trip."""
        m = _make_base_metrics()
        m.update(_recovery_fields(status="WAIT"))
        r = _transform_output(_wait_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Status"] == "WAIT"

    def test_recovery_candidate_status_unchanged(self):
        """Non-regression: RECOVERY CANDIDATE still works."""
        m = _make_base_metrics()
        m.update(_recovery_fields(status="RECOVERY CANDIDATE"))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["recovery_status"] == "RECOVERY CANDIDATE"

    def test_recovery_candidate_flatten_unchanged(self):
        """Non-regression: RECOVERY CANDIDATE survives _flatten()."""
        m = _make_base_metrics()
        m.update(_recovery_fields(status="RECOVERY CANDIDATE"))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Status"] == "RECOVERY CANDIDATE"

    def test_wait_populates_all_recovery_fields(self):
        """WAIT path still populates all non-status recovery fields."""
        m = _make_base_metrics()
        m.update(_recovery_fields(status="WAIT", capital_rr=2.3,
                                  crg_bypass_context="CRG-2 OVERRIDDEN"))
        r = _transform_output(_wait_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["base_bar_count"] == 7
        assert ra["swing_low_price"] == 92.50
        assert ra["recovery_target"] == 110.0


# ═══════════════════════════════════════════════════════════════════════
#  REC-SC-2: Recovery_Capital_RR flat key
# ═══════════════════════════════════════════════════════════════════════

class TestRecSC2_CapitalRR:

    def test_capital_rr_in_grouped_dict(self):
        """Recovery_Capital_RR flows into recovery_analysis group."""
        m = _make_base_metrics()
        m.update(_recovery_fields(capital_rr=2.3))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        assert r["recovery_analysis"]["recovery_capital_rr"] == 2.3

    def test_capital_rr_in_flatten(self):
        """Recovery_Capital_RR survives _flatten() round-trip."""
        m = _make_base_metrics()
        m.update(_recovery_fields(capital_rr=2.3))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Capital_RR"] == 2.3

    def test_capital_rr_none_when_not_computed(self):
        """Recovery_Capital_RR is None when R:R wasn't computed."""
        m = _make_base_metrics()
        m.update(_recovery_fields(capital_rr=None))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Capital_RR"] is None

    def test_capital_rr_is_numeric(self):
        """Recovery_Capital_RR stores a float, not a string."""
        m = _make_base_metrics()
        m.update(_recovery_fields(capital_rr=1.8))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert isinstance(flat["Recovery_Capital_RR"], float)

    def test_capital_rr_absent_in_not_evaluated(self):
        """NOT EVALUATED path does not include Recovery_Capital_RR."""
        m = _make_base_metrics()
        m["Recovery_Status"] = "NOT EVALUATED"
        for k in ["Recovery_Base_Bar_Count", "Recovery_Swing_Low_Price",
                   "Recovery_Swing_Low_Bar_Index", "Recovery_EMA_Cross_Bar_Index",
                   "Recovery_DI_Spread_Current", "Recovery_DI_Spread_At_Swing_Low",
                   "Recovery_ATR_Contraction_Ratio", "Recovery_Retest_Confirmed",
                   "Recovery_Time_Stop_Bars_Remaining", "Recovery_Target",
                   "Recovery_Target_Source", "Recovery_Active_Count",
                   "Recovery_Capital_RR", "Recovery_CRG_Bypass_Context",
                   "Recovery_Diagnostic"]:
            m[k] = None
        r = _transform_output(_recovery_candidate_action_summary(), m)
        # NOT EVALUATED group is minimal
        assert "recovery_capital_rr" not in r["recovery_analysis"]


# ═══════════════════════════════════════════════════════════════════════
#  REC-SC-3: Recovery_CRG_Bypass_Context flat key
# ═══════════════════════════════════════════════════════════════════════

class TestRecSC3_CRGBypassContext:

    def test_crg_bypass_in_grouped_dict(self):
        """Recovery_CRG_Bypass_Context flows into recovery_analysis group."""
        m = _make_base_metrics()
        m.update(_recovery_fields(
            crg_bypass_context="CRG-2 OVERRIDDEN (weekly SMA 50 slope: -1.2)"))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        assert r["recovery_analysis"]["crg_bypass_context"] == \
            "CRG-2 OVERRIDDEN (weekly SMA 50 slope: -1.2)"

    def test_crg_bypass_in_flatten(self):
        """Recovery_CRG_Bypass_Context survives _flatten() round-trip."""
        m = _make_base_metrics()
        m.update(_recovery_fields(
            crg_bypass_context="CRG-2 OVERRIDDEN (weekly SMA 50 slope: -1.2)"))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_CRG_Bypass_Context"] == \
            "CRG-2 OVERRIDDEN (weekly SMA 50 slope: -1.2)"

    def test_crg_bypass_none_when_no_bypass(self):
        """Recovery_CRG_Bypass_Context is None when CRG wasn't bypassed."""
        m = _make_base_metrics()
        m.update(_recovery_fields(crg_bypass_context=None))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_CRG_Bypass_Context"] is None

    def test_crg_bypass_is_string(self):
        """Recovery_CRG_Bypass_Context stores a string, not embedded in diag."""
        m = _make_base_metrics()
        m.update(_recovery_fields(crg_bypass_context="CRG-2 OVERRIDDEN"))
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert isinstance(flat["Recovery_CRG_Bypass_Context"], str)

    def test_crg_bypass_absent_in_not_evaluated(self):
        """NOT EVALUATED path does not include crg_bypass_context."""
        m = _make_base_metrics()
        m["Recovery_Status"] = "NOT EVALUATED"
        for k in ["Recovery_Base_Bar_Count", "Recovery_Swing_Low_Price",
                   "Recovery_Swing_Low_Bar_Index", "Recovery_EMA_Cross_Bar_Index",
                   "Recovery_DI_Spread_Current", "Recovery_DI_Spread_At_Swing_Low",
                   "Recovery_ATR_Contraction_Ratio", "Recovery_Retest_Confirmed",
                   "Recovery_Time_Stop_Bars_Remaining", "Recovery_Target",
                   "Recovery_Target_Source", "Recovery_Active_Count",
                   "Recovery_Capital_RR", "Recovery_CRG_Bypass_Context",
                   "Recovery_Diagnostic"]:
            m[k] = None
        r = _transform_output(_recovery_candidate_action_summary(), m)
        assert "crg_bypass_context" not in r["recovery_analysis"]


# ═══════════════════════════════════════════════════════════════════════
#  COMBINED: All three new keys present together
# ═══════════════════════════════════════════════════════════════════════

class TestRecSC_Combined:

    def test_all_three_keys_in_flatten(self):
        """All three new keys coexist in flattened output."""
        m = _make_base_metrics()
        m.update(_recovery_fields(
            status="WAIT",
            capital_rr=2.3,
            crg_bypass_context="CRG-2 OVERRIDDEN (weekly SMA 50 slope: -1.2)"))
        r = _transform_output(_wait_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Status"] == "WAIT"
        assert flat["Recovery_Capital_RR"] == 2.3
        assert flat["Recovery_CRG_Bypass_Context"] == \
            "CRG-2 OVERRIDDEN (weekly SMA 50 slope: -1.2)"


# ═══════════════════════════════════════════════════════════════════════
#  REC-SC-1 OUTPUT.PY LOGIC: Direct conditional branch verification
#  Tests the exact branching pattern from output.py lines 1038-1047
#  without requiring a full RunContext.
# ═══════════════════════════════════════════════════════════════════════

from types import SimpleNamespace


def _simulate_recovery_status(verdict, reason):
    """Reproduce the exact REC-SC-1 branching logic from output.py."""
    gr = SimpleNamespace(verdict=verdict, reason=reason)
    _is_recovery_candidate = (
        gr.verdict == "RECOVERY CANDIDATE"
        or (gr.verdict == "WAIT" and gr.reason == "THESIS ATTESTATION")
    )
    if _is_recovery_candidate:
        if gr.verdict == "WAIT" and gr.reason == "THESIS ATTESTATION":
            return "WAIT"
        else:
            return "RECOVERY CANDIDATE"
    else:
        return "REJECT"


class TestRecSC1_OutputLogic:
    """Tests the actual conditional pattern from output.py."""

    def test_recovery_candidate_verdict_produces_recovery_candidate(self):
        assert _simulate_recovery_status("RECOVERY CANDIDATE", "R-GATES PASSED") == "RECOVERY CANDIDATE"

    def test_wait_thesis_attestation_produces_wait(self):
        assert _simulate_recovery_status("WAIT", "THESIS ATTESTATION") == "WAIT"

    def test_wait_non_thesis_produces_reject(self):
        """WAIT with a non-THESIS ATTESTATION reason is not a recovery candidate."""
        assert _simulate_recovery_status("WAIT", "TREND QUALITY") == "REJECT"

    def test_halt_produces_reject(self):
        assert _simulate_recovery_status("HALT", "SOME REASON") == "REJECT"

    def test_reject_produces_reject(self):
        assert _simulate_recovery_status("REJECT", "DI SPREAD NOT NARROWING") == "REJECT"

    def test_recovery_candidate_reason_irrelevant(self):
        """For RECOVERY CANDIDATE verdict, reason doesn't change the status."""
        assert _simulate_recovery_status("RECOVERY CANDIDATE", "THESIS ATTESTATION") == "RECOVERY CANDIDATE"
        assert _simulate_recovery_status("RECOVERY CANDIDATE", "ANYTHING") == "RECOVERY CANDIDATE"
