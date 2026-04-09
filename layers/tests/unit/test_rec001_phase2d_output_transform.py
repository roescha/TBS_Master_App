"""REC-001 Phase 2D: Output Schema + Transform Layer — Unit Tests.

Tests all 13 recovery-specific output fields, diagnostic strings,
action_summary RECOVERY CANDIDATE / WAIT (THESIS ATTESTATION) branches,
recovery_analysis transform group, and _flatten() Recovery_ prefix.

Maps to spec §7.1–7.3, §8.1–8.3.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _transform_output, _flatten


# ═══════════════════════════════════════════════════════════════════════
#  HELPERS — metrics and action_summary builders
# ═══════════════════════════════════════════════════════════════════════

def _make_base_metrics():
    """Minimal metrics dict shared across all paths."""
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


def _add_recovery_candidate_fields(m):
    """Populate all 13 recovery fields for a RECOVERY CANDIDATE path."""
    m["Recovery_Status"]                   = "RECOVERY CANDIDATE"
    m["Recovery_Base_Bar_Count"]            = 7
    m["Recovery_Swing_Low_Price"]           = 92.50
    m["Recovery_Swing_Low_Bar_Index"]       = 55
    m["Recovery_EMA_Cross_Bar_Index"]       = 62
    m["Recovery_DI_Spread_Current"]         = 6.2
    m["Recovery_DI_Spread_At_Swing_Low"]    = 14.8
    m["Recovery_ATR_Contraction_Ratio"]     = 0.82
    m["Recovery_Retest_Confirmed"]          = True
    m["Recovery_Time_Stop_Bars_Remaining"]  = 18
    m["Recovery_Target"]                    = 110.0
    m["Recovery_Target_Source"]             = "SMA_50"
    m["Recovery_Active_Count"]             = 0
    m["Recovery_Diagnostic"]               = (
        "Recovery gates PASSED. Base confirmed: 7 bars, no lower low, "
        "ATR ratio 0.82, retest confirmed, vol clean. "
        "EMA cross fresh: bar 62 >= swing low bar 55. "
        "DI spread narrowed: 6.2 < 14.8. "
        "Capital R:R 2.3 >= 1.5. Target: SMA_50 (110.00). "
        "context: CRG-2 OVERRIDDEN."
    )
    return m


def _add_reject_fields(m):
    """Populate recovery fields for a REJECT path (R-Gate 3 failure)."""
    m["Recovery_Status"]                   = "REJECT"
    m["Recovery_Base_Bar_Count"]            = 7
    m["Recovery_Swing_Low_Price"]           = 92.50
    m["Recovery_Swing_Low_Bar_Index"]       = 55
    m["Recovery_EMA_Cross_Bar_Index"]       = 62
    m["Recovery_DI_Spread_Current"]         = 16.1
    m["Recovery_DI_Spread_At_Swing_Low"]    = 14.8
    m["Recovery_ATR_Contraction_Ratio"]     = 0.82
    m["Recovery_Retest_Confirmed"]          = True
    m["Recovery_Time_Stop_Bars_Remaining"]  = None
    m["Recovery_Target"]                    = 110.0
    m["Recovery_Target_Source"]             = "SMA_50"
    m["Recovery_Active_Count"]             = 0
    m["Recovery_Diagnostic"]               = (
        "Recovery gates FAILED. DI SPREAD NOT NARROWING. "
        "DI spread not narrowing: 16.1 vs 14.8 at swing low."
    )
    return m


def _add_not_evaluated_fields(m):
    """Populate NOT EVALUATED stub."""
    m["Recovery_Status"]                   = "NOT EVALUATED"
    m["Recovery_Base_Bar_Count"]            = None
    m["Recovery_Swing_Low_Price"]           = None
    m["Recovery_Swing_Low_Bar_Index"]       = None
    m["Recovery_EMA_Cross_Bar_Index"]       = None
    m["Recovery_DI_Spread_Current"]         = None
    m["Recovery_DI_Spread_At_Swing_Low"]    = None
    m["Recovery_ATR_Contraction_Ratio"]     = None
    m["Recovery_Retest_Confirmed"]          = None
    m["Recovery_Time_Stop_Bars_Remaining"]  = None
    m["Recovery_Target"]                    = None
    m["Recovery_Target_Source"]             = None
    m["Recovery_Active_Count"]             = 0
    m["Recovery_Diagnostic"]               = None
    return m


def _recovery_candidate_action_summary():
    """Action summary for RECOVERY CANDIDATE verdict."""
    return {
        "verdict": "RECOVERY CANDIDATE",
        "reason": {"label": "RECOVERY CANDIDATE",
                   "detail": "Recovery gates PASSED. Base confirmed."},
        "mandate": "Recovery entry candidate. All R-Gates passed.",
        "merit": {"quality": "RECOVERY", "reward": "SMA_50"},
        "volume": "ACCUMULATING",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
    }


def _thesis_attestation_action_summary():
    """Action summary for C-3 WAIT (THESIS ATTESTATION) verdict."""
    return {
        "verdict": "WAIT",
        "reason": {"label": "THESIS ATTESTATION",
                   "detail": "context: CRG-2 OVERRIDDEN; context: SENTINEL DEFENSIVE"},
        "approaching": False,
        "volume": "ACCUMULATING",
        "volume_confirmation": None,
        "mandate": "C-3 recovery candidate requires Thesis Attestation before entry.",
        "exit_status": {"active": False, "reason": None},
    }


def _invalid_action_summary():
    """Standard INVALID path (non-recovery)."""
    return {
        "verdict": "INVALID",
        "reason": {"label": "CRG-2", "detail": "Weekly SMA 50 slope negative."},
        "approaching": False,
        "volume": None,
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
    }


def _recovery_exit_active_action_summary():
    """RECOVERY CANDIDATE with an active exit signal."""
    return {
        "verdict": "RECOVERY CANDIDATE",
        "reason": {"label": "RECOVERY CANDIDATE",
                   "detail": "Recovery gates PASSED. EXIT ACTIVE: BASE FAILURE."},
        "mandate": "Recovery entry candidate. All R-Gates passed.",
        "merit": {"quality": "RECOVERY", "reward": "SMA_50"},
        "volume": "ACCUMULATING",
        "volume_confirmation": None,
        "exit_status": {"active": True, "reason": "BASE FAILURE"},
    }


# ═══════════════════════════════════════════════════════════════════════
#  §8.3: recovery_analysis GROUP IN TRANSFORM OUTPUT
# ═══════════════════════════════════════════════════════════════════════

class TestRecoveryAnalysisGroup:
    """Spec §8.3: recovery_analysis is a top-level group in grouped output."""

    def test_recovery_analysis_present_in_output(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        assert "recovery_analysis" in r

    def test_recovery_candidate_group_has_all_13_fields(self):
        """Spec §8.1: All 13 recovery-specific fields present."""
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        ra = r["recovery_analysis"]
        expected_keys = {
            "recovery_status", "base_bar_count", "swing_low_price",
            "swing_low_bar_index", "ema_cross_bar_index", "di_spread_current",
            "di_spread_at_swing_low", "atr_contraction_ratio", "retest_confirmed",
            "time_stop_bars_remaining", "recovery_target", "recovery_target_source",
            "recovery_active_count", "recovery_capital_rr", "crg_bypass_context",
            "diagnostic",
        }
        assert set(ra.keys()) == expected_keys

    def test_recovery_candidate_field_values(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["recovery_status"] == "RECOVERY CANDIDATE"
        assert ra["base_bar_count"] == 7
        assert ra["swing_low_price"] == 92.50
        assert ra["swing_low_bar_index"] == 55
        assert ra["ema_cross_bar_index"] == 62
        assert ra["di_spread_current"] == 6.2
        assert ra["di_spread_at_swing_low"] == 14.8
        assert ra["atr_contraction_ratio"] == 0.82
        assert ra["retest_confirmed"] is True
        assert ra["time_stop_bars_remaining"] == 18
        assert ra["recovery_target"] == 110.0
        assert ra["recovery_target_source"] == "SMA_50"
        assert ra["recovery_active_count"] == 0

    def test_reject_group_populated(self):
        m = _add_reject_fields(_make_base_metrics())
        r = _transform_output(_invalid_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["recovery_status"] == "REJECT"
        assert ra["base_bar_count"] == 7
        assert ra["di_spread_current"] == 16.1
        assert "FAILED" in ra["diagnostic"]

    def test_not_evaluated_stub(self):
        """Spec §8.1: Standard-path tickers get recovery_status: NOT EVALUATED."""
        m = _add_not_evaluated_fields(_make_base_metrics())
        r = _transform_output(_invalid_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["recovery_status"] == "NOT EVALUATED"
        # Stub only has recovery_status
        assert len(ra) == 1

    def test_not_evaluated_when_no_recovery_fields(self):
        """When no Recovery_ fields in metrics, group defaults to NOT EVALUATED."""
        m = _make_base_metrics()
        # No Recovery_ fields added
        r = _transform_output(_invalid_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["recovery_status"] == "NOT EVALUATED"


# ═══════════════════════════════════════════════════════════════════════
#  §8.3: _flatten() Recovery_ PREFIX EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

class TestFlattenRecoveryPrefix:
    """Spec §8.3: _flatten() produces Recovery_ prefixed keys."""

    def test_flatten_recovery_candidate_has_all_recovery_keys(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        status, diag, flat = _flatten(r)
        recovery_keys = {k for k in flat if k.startswith("Recovery_")}
        expected = {
            "Recovery_Status", "Recovery_Base_Bar_Count", "Recovery_Swing_Low_Price",
            "Recovery_Swing_Low_Bar_Index", "Recovery_EMA_Cross_Bar_Index",
            "Recovery_DI_Spread_Current", "Recovery_DI_Spread_At_Swing_Low",
            "Recovery_ATR_Contraction_Ratio", "Recovery_Retest_Confirmed",
            "Recovery_Time_Stop_Bars_Remaining", "Recovery_Target",
            "Recovery_Target_Source", "Recovery_Active_Count",
            "Recovery_Capital_RR", "Recovery_CRG_Bypass_Context",
            "Recovery_Diagnostic",
        }
        assert recovery_keys == expected

    def test_flatten_recovery_candidate_values_roundtrip(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Status"] == "RECOVERY CANDIDATE"
        assert flat["Recovery_Swing_Low_Price"] == 92.50
        assert flat["Recovery_Target"] == 110.0
        assert flat["Recovery_Target_Source"] == "SMA_50"
        assert flat["Recovery_Active_Count"] == 0
        assert flat["Recovery_Retest_Confirmed"] is True

    def test_flatten_not_evaluated_has_recovery_status(self):
        m = _add_not_evaluated_fields(_make_base_metrics())
        r = _transform_output(_invalid_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Status"] == "NOT EVALUATED"

    def test_flatten_reject_has_recovery_keys(self):
        m = _add_reject_fields(_make_base_metrics())
        r = _transform_output(_invalid_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Status"] == "REJECT"
        assert flat["Recovery_DI_Spread_Current"] == 16.1

    def test_flatten_recovery_candidate_verdict_maps_to_pass(self):
        """RECOVERY CANDIDATE is actionable — maps to PASS status."""
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        status, _, _ = _flatten(r)
        assert status == "PASS"


# ═══════════════════════════════════════════════════════════════════════
#  RECOVERY CANDIDATE ACTION SUMMARY (Crash Fix)
# ═══════════════════════════════════════════════════════════════════════

class TestRecoveryCandidateActionSummary:
    """Critical: engine must survive RECOVERY CANDIDATE verdict."""

    def test_recovery_candidate_does_not_crash(self):
        """Crash fix: _transform_output must accept RECOVERY CANDIDATE verdict."""
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        assert r["action_summary"]["verdict"] == "RECOVERY CANDIDATE"

    def test_recovery_candidate_has_merit(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        merit = r["action_summary"]["merit"]
        assert merit["quality"] == "RECOVERY"
        assert merit["reward"] == "SMA_50"

    def test_recovery_candidate_has_mandate(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        assert "mandate" in r["action_summary"]
        assert "R-Gates passed" in r["action_summary"]["mandate"]

    def test_recovery_candidate_exit_status_inactive(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        es = r["action_summary"]["exit_status"]
        assert es["active"] is False
        assert es["reason"] is None

    def test_recovery_candidate_exit_status_active(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        m["Recovery_Diagnostic"] = "Recovery gates PASSED. EXIT ACTIVE: BASE FAILURE."
        r = _transform_output(_recovery_exit_active_action_summary(), m)
        es = r["action_summary"]["exit_status"]
        assert es["active"] is True
        assert es["reason"] == "BASE FAILURE"

    def test_recovery_candidate_has_reason_structure(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        reason = r["action_summary"]["reason"]
        assert isinstance(reason, dict)
        assert reason["label"] == "RECOVERY CANDIDATE"
        assert reason["detail"] is not None


# ═══════════════════════════════════════════════════════════════════════
#  C-3 THESIS ATTESTATION (WAIT PATH)
# ═══════════════════════════════════════════════════════════════════════

class TestThesisAttestationWaitPath:
    """Spec: C-3 THESIS ATTESTATION uses WAIT verdict with recovery context."""

    def test_thesis_attestation_verdict_is_wait(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_thesis_attestation_action_summary(), m)
        assert r["action_summary"]["verdict"] == "WAIT"

    def test_thesis_attestation_reason_label(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_thesis_attestation_action_summary(), m)
        assert r["action_summary"]["reason"]["label"] == "THESIS ATTESTATION"

    def test_thesis_attestation_has_mandate(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_thesis_attestation_action_summary(), m)
        assert "mandate" in r["action_summary"]
        assert "Thesis Attestation" in r["action_summary"]["mandate"]

    def test_thesis_attestation_recovery_group_populated(self):
        """C-3 THESIS ATTESTATION still populates recovery_analysis."""
        m = _add_recovery_candidate_fields(_make_base_metrics())
        # Override status to RECOVERY CANDIDATE (C-3 recovery path)
        r = _transform_output(_thesis_attestation_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["recovery_status"] == "RECOVERY CANDIDATE"
        assert ra["base_bar_count"] == 7

    def test_thesis_attestation_flatten_maps_to_halt(self):
        """WAIT verdict maps to HALT in flattened output."""
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_thesis_attestation_action_summary(), m)
        status, _, _ = _flatten(r)
        assert status == "HALT"


# ═══════════════════════════════════════════════════════════════════════
#  §8.2: DIAGNOSTIC STRING PATTERNS
# ═══════════════════════════════════════════════════════════════════════

class TestDiagnosticStrings:
    """Spec §8.2: Diagnostic strings for R-Gate pass/fail."""

    def test_pass_diagnostic_contains_base_confirmed(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        diag = m["Recovery_Diagnostic"]
        assert "Base confirmed" in diag

    def test_pass_diagnostic_contains_ema_cross_fresh(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        assert "EMA cross fresh" in m["Recovery_Diagnostic"]

    def test_pass_diagnostic_contains_di_spread(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        assert "DI spread narrowed" in m["Recovery_Diagnostic"]

    def test_pass_diagnostic_contains_capital_rr(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        assert "Capital R:R" in m["Recovery_Diagnostic"]

    def test_pass_diagnostic_contains_target(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        assert "SMA_50" in m["Recovery_Diagnostic"]

    def test_pass_diagnostic_contains_crg_overridden(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        assert "CRG-2 OVERRIDDEN" in m["Recovery_Diagnostic"]

    def test_reject_diagnostic_contains_failed(self):
        m = _add_reject_fields(_make_base_metrics())
        assert "FAILED" in m["Recovery_Diagnostic"]

    def test_reject_diagnostic_contains_gate_reason(self):
        m = _add_reject_fields(_make_base_metrics())
        assert "DI SPREAD NOT NARROWING" in m["Recovery_Diagnostic"]

    def test_not_evaluated_diagnostic_is_none(self):
        m = _add_not_evaluated_fields(_make_base_metrics())
        assert m["Recovery_Diagnostic"] is None


# ═══════════════════════════════════════════════════════════════════════
#  §7.1/§7.2: SENTINEL & CRG BYPASS CONTEXT IN DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════

class TestContextTransparency:
    """Spec §7.1 (Sentinel) and §7.2 (CRG bypass) surfaced in diagnostic."""

    def test_crg_bypass_in_diagnostic(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        assert "CRG-2 OVERRIDDEN" in m["Recovery_Diagnostic"]

    def test_sentinel_context_in_thesis_attestation_detail(self):
        """Sentinel regime surfaced in action_summary detail for C-3."""
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_thesis_attestation_action_summary(), m)
        detail = r["action_summary"]["reason"]["detail"]
        assert "SENTINEL DEFENSIVE" in detail

    def test_crg_context_in_thesis_attestation_detail(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_thesis_attestation_action_summary(), m)
        detail = r["action_summary"]["reason"]["detail"]
        assert "CRG-2 OVERRIDDEN" in detail


# ═══════════════════════════════════════════════════════════════════════
#  §7.3: Recovery_Active_Count
# ═══════════════════════════════════════════════════════════════════════

class TestRecoveryActiveCount:
    """Spec §7.3: Informational integer, default 0."""

    def test_active_count_default_zero(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        assert r["recovery_analysis"]["recovery_active_count"] == 0

    def test_active_count_passes_through(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        m["Recovery_Active_Count"] = 2
        r = _transform_output(_recovery_candidate_action_summary(), m)
        assert r["recovery_analysis"]["recovery_active_count"] == 2

    def test_active_count_in_flatten(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        m["Recovery_Active_Count"] = 1
        r = _transform_output(_recovery_candidate_action_summary(), m)
        _, _, flat = _flatten(r)
        assert flat["Recovery_Active_Count"] == 1


# ═══════════════════════════════════════════════════════════════════════
#  SCOPE DISCIPLINE — no Phase 2E vocabulary
# ═══════════════════════════════════════════════════════════════════════

class TestScopeDiscipline:
    """No scanner section names, no gate logic, no exit logic in output."""

    def test_no_candidates_section_in_output(self):
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        r_str = str(r)
        assert "RECOVERY CANDIDATES" not in r_str  # scanner section name
        assert "NEAR-MISS" not in r_str

    def test_no_halt_in_recovery_output(self):
        """HALT is deprecated — never used in recovery vocabulary."""
        m = _add_recovery_candidate_fields(_make_base_metrics())
        r = _transform_output(_recovery_candidate_action_summary(), m)
        ra = r["recovery_analysis"]
        assert ra["recovery_status"] != "HALT"
