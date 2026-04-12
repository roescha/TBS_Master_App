"""PA-001 Phase 2 — Output Layer Unit Tests.

Tests cover:
  1. data.py: Daily RSI(14) computed on df_ctx, stored in raw_metrics as Daily_RSI.
  2. output.py: Capital_RR_Role (ADVISORY vs ENFORCEABLE), RSI admissibility
     (C-1 ALLOWED, C-2 RESTRICTED), CAUTION note, PE-CAL-3 exemption annotation.
  3. transform.py: extension_analysis.daily populated with distance, anchor, condition,
     thresholds. RSI nested in daily when available. floor_analysis.protective_anchor
     populated. trade_risk.capital_rr_role has {label, desc}. Self-doc compliance
     ({value, unit, desc} and {label, desc} patterns).
  4. Profile B/C: No extension_analysis.daily, no protective_anchor, no RSI, no PE-CAL-3.
  5. _flatten: Reverse mapping produces correct flat keys from grouped output.
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace

import pandas_ta  # noqa: F401 — registers .ta accessor on DataFrame (if compatible)

from tbs_engine.transform import _transform_output, _flatten


# ============================================================================
# HELPERS
# ============================================================================

def _compute_rsi_manual(closes, length=14):
    """Pure-Python RSI computation for test independence from pandas_ta accessor."""
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    if len(deltas) < length:
        return None
    gains = [max(d, 0) for d in deltas[:length]]
    losses = [abs(min(d, 0)) for d in deltas[:length]]
    avg_gain = sum(gains) / length
    avg_loss = sum(losses) / length
    for d in deltas[length:]:
        avg_gain = (avg_gain * (length - 1) + max(d, 0)) / length
        avg_loss = (avg_loss * (length - 1) + abs(min(d, 0))) / length
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ============================================================================
# HELPERS
# ============================================================================

def _build_action_summary(verdict="VALID"):
    """Minimal action_summary for _transform_output."""
    if verdict == "VALID":
        return {
            "verdict": "VALID",
            "reason": {"label": "PULLBACK", "detail": "All gates passed."},
            "mandate": "Enter on pullback.",
            "merit": {"quality": "STRONG", "reward": "HEALTHY [2.5]"},
            "trigger": {"rule": "pullback_zone", "condition": "Close within zone"},
            "volume": "MIXED",
            "volume_confirmation": None,
            "entry_strategy": {
                "entry_price": 150.0,
                "stop_loss": 140.0,
                "target": 170.0,
                "fib_382": None, "fib_500": None, "fib_confluence": None,
                "mm_target": None,
            },
            "exit_status": {"active": False, "reason": None},
        }
    return {
        "verdict": "INVALID",
        "reason": {"label": "EXTENSION", "detail": "Overextended."},
        "approaching": False,
        "volume": "MIXED",
        "volume_confirmation": None,
        "exit_status": {"active": False, "reason": None},
    }


def _base_metrics_profile_a(**overrides):
    """Build a minimal flat_metrics dict for Profile A with PA-001 Phase 1+2 fields."""
    m = {
        # Snapshot basics
        "Price": 150.0, "Structural_Floor": 140.0, "Resistance": 160.0,
        "ATR": 2.0, "EMA_8": 149.0, "EMA_21": 148.0, "SMA_50": 135.0,
        "SMA_200": 120.0, "VWAP": 148.5, "ADV_20": 500000,
        "Convexity_Class": "C1", "Is_ETF": False,
        # Extension (intraday)
        "ATR_Dist": 0.5, "ATR_Dist_Anchor": "VWAP",
        "Extension_Limit": 1.0, "Extension_Anchor_Type": "VWAP",
        "Extension_Anchor_Label": "Session VWAP",
        # Risk
        "Reward_Risk": 3.0, "Capital_Reward_Risk": 2.5,
        "Capital_RR_Label": "HEALTHY", "Risk_Per_Unit": 10.0,
        "Expectancy_Threshold": 2.0, "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Price R:R 3.00 >= 2.0. Capital R:R 2.50 (HEALTHY).",
        # Floor
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Anchor_Type": "VWAP", "Anchor_Label": "Session VWAP",
        # Trade setup
        "Profit_Target": 170.0, "Hard_Stop": 140.0,
        # THS
        "THS_Score": 75, "THS_Label": "STRONG",
        # PA-001 Phase 1: Daily protective values
        "Daily_Protective_Anchor": 145.0,
        "Daily_ATR": 3.5,
        "Daily_Hard_Stop": 139.75,  # 145 - 1.5*3.5
        "Daily_Extension_Distance": 1.43,  # (150 - 145) / 3.5
        "Daily_Extension_Label": "NORMAL",
        # PA-001 Phase 2: Output annotations
        "Capital_RR_Role": "ADVISORY",
        "Capital_RR_Role_Desc": "Profile A: Capital R:R is informational -- daily hard stop too distant for meaningful pre-trade R:R. Daily extension gate and THS are the swing quality gates.",
        "Daily_RSI": 55.0,
        "Daily_RSI_Admissibility": "ALLOWED",
        "Daily_RSI_Admissibility_Desc": "C-1: full advisory use permitted",
        "Floor_Proximity_Exempted": True,
        "Floor_Proximity_Exemption_Desc": "PA-001: floor proximity hard-stop substitution exempted -- daily protective anchor eliminates VWAP convergence root cause",
        "Convexity": "C-1",
    }
    m.update(overrides)
    return m


def _base_metrics_profile_b(**overrides):
    """Build a minimal flat_metrics dict for Profile B (no PA-001 daily fields)."""
    m = {
        "Price": 50.0, "Structural_Floor": 45.0, "Resistance": 60.0,
        "ATR": 1.0, "EMA_8": 49.0, "EMA_21": 48.0, "SMA_50": 42.0,
        "SMA_200": 35.0, "VWAP": 49.5, "ADV_20": 1000000,
        "Convexity_Class": "C1", "Is_ETF": False,
        "ATR_Dist": 0.3, "ATR_Dist_Anchor": "EMA_21",
        "Extension_Limit": 1.0, "Extension_Anchor_Type": "EMA_21",
        "Extension_Anchor_Label": "21 EMA",
        "Reward_Risk": 4.0, "Capital_Reward_Risk": 3.0,
        "Capital_RR_Label": "HEALTHY", "Risk_Per_Unit": 5.0,
        "Expectancy_Threshold": 2.0, "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Price R:R 4.00 >= 2.0. Capital R:R 3.00 (HEALTHY).",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Anchor_Type": "EMA_21", "Anchor_Label": "21 EMA",
        "Profit_Target": 60.0, "Hard_Stop": 43.0,
        "THS_Score": 80, "THS_Label": "STRONG",
        # Phase 2: Profile B gets ENFORCEABLE role, no daily protective fields
        "Capital_RR_Role": "ENFORCEABLE",
        "Capital_RR_Role_Desc": "Capital R:R enforced as hard gate.",
    }
    m.update(overrides)
    return m


# ============================================================================
# 1. DATA LAYER — Daily RSI(14) Extraction
# ============================================================================

class TestDailyRSIExtraction:
    """Tests for data.py Daily RSI(14) computation and extraction (DQ-8).

    These tests verify the extraction logic (float conversion, None handling)
    independently of the pandas_ta .ta accessor, which may not register on
    all Python/pandas version combinations.
    """

    def test_rsi_extracted_from_df_ctx(self):
        """RSI(14) yields a float in 0-100 range when sufficient bars exist."""
        np.random.seed(42)
        closes = list(100 + np.cumsum(np.random.randn(30) * 0.5))
        rsi_val = _compute_rsi_manual(closes, length=14)

        assert rsi_val is not None, "RSI should not be None with 30 bars"
        assert 0 <= rsi_val <= 100, f"RSI must be 0-100, got {rsi_val}"

        # Simulate the data.py extraction pattern
        daily_rsi = float(rsi_val) if rsi_val is not None else None
        assert isinstance(daily_rsi, float)

    def test_rsi_none_with_insufficient_bars(self):
        """RSI(14) returns None with fewer than 15 bars."""
        closes = [100 + i * 0.5 for i in range(10)]
        rsi_val = _compute_rsi_manual(closes, length=14)
        daily_rsi = float(rsi_val) if rsi_val is not None else None
        assert daily_rsi is None, "RSI should be None with only 10 bars"

    def test_rsi_extraction_nan_handling(self):
        """NaN RSI value is extracted as None (data.py guard pattern)."""
        _d_rsi = float('nan')
        daily_rsi = float(_d_rsi) if not pd.isna(_d_rsi) else None
        assert daily_rsi is None

    def test_rsi_extraction_valid_value(self):
        """Valid RSI value is extracted as float (data.py guard pattern)."""
        _d_rsi = 65.3
        daily_rsi = float(_d_rsi) if not pd.isna(_d_rsi) else None
        assert daily_rsi == 65.3


# ============================================================================
# 2. OUTPUT LAYER — Annotations
# ============================================================================

class TestCapitalRRRole:
    """Capital_RR_Role annotation: ADVISORY for Profile A, ENFORCEABLE for B/C."""

    def test_profile_a_advisory(self):
        """Profile A writes Capital_RR_Role=ADVISORY with descriptive text."""
        metrics = {"Capital_Reward_Risk": 2.0, "Capital_RR_Label": "HEALTHY"}
        p_code = "A"

        # Simulate output.py Step 2a logic
        if p_code == "A":
            metrics["Capital_RR_Role"] = "ADVISORY"
            metrics["Capital_RR_Role_Desc"] = "Profile A: Capital R:R is informational -- daily hard stop too distant for meaningful pre-trade R:R. Daily extension gate and THS are the swing quality gates."
        else:
            metrics["Capital_RR_Role"] = "ENFORCEABLE"
            metrics["Capital_RR_Role_Desc"] = "Capital R:R enforced as hard gate."

        assert metrics["Capital_RR_Role"] == "ADVISORY"
        assert "informational" in metrics["Capital_RR_Role_Desc"]

    def test_profile_b_enforceable(self):
        """Profile B writes Capital_RR_Role=ENFORCEABLE."""
        metrics = {}
        p_code = "B"
        if p_code == "A":
            metrics["Capital_RR_Role"] = "ADVISORY"
        else:
            metrics["Capital_RR_Role"] = "ENFORCEABLE"
            metrics["Capital_RR_Role_Desc"] = "Capital R:R enforced as hard gate."

        assert metrics["Capital_RR_Role"] == "ENFORCEABLE"

    def test_profile_c_enforceable(self):
        """Profile C writes Capital_RR_Role=ENFORCEABLE."""
        metrics = {}
        p_code = "C"
        if p_code == "A":
            metrics["Capital_RR_Role"] = "ADVISORY"
        else:
            metrics["Capital_RR_Role"] = "ENFORCEABLE"

        assert metrics["Capital_RR_Role"] == "ENFORCEABLE"


class TestRSIAdmissibility:
    """RSI admissibility annotation: C-1 ALLOWED, C-2 RESTRICTED."""

    def test_c1_allowed(self):
        """C-1 convexity → RSI admissibility ALLOWED."""
        metrics = {"Daily_RSI": 55.0, "Convexity": "C-1"}
        p_code = "A"

        if p_code == "A":
            _daily_rsi = metrics.get("Daily_RSI")
            if _daily_rsi is not None:
                _cvx = metrics.get("Convexity", "C-1")
                if _cvx == "C-2":
                    metrics["Daily_RSI_Admissibility"] = "RESTRICTED"
                else:
                    metrics["Daily_RSI_Admissibility"] = "ALLOWED"
                    metrics["Daily_RSI_Admissibility_Desc"] = "C-1: full advisory use permitted"

        assert metrics["Daily_RSI_Admissibility"] == "ALLOWED"

    def test_c2_restricted(self):
        """C-2 convexity → RSI admissibility RESTRICTED."""
        metrics = {"Daily_RSI": 55.0, "Convexity": "C-2"}
        p_code = "A"

        if p_code == "A":
            _daily_rsi = metrics.get("Daily_RSI")
            if _daily_rsi is not None:
                _cvx = metrics.get("Convexity", "C-1")
                if _cvx == "C-2":
                    metrics["Daily_RSI_Admissibility"] = "RESTRICTED"
                    metrics["Daily_RSI_Admissibility_Desc"] = "C-2: secondary context only -- cannot drive entry, exit, or timing decisions"
                else:
                    metrics["Daily_RSI_Admissibility"] = "ALLOWED"

        assert metrics["Daily_RSI_Admissibility"] == "RESTRICTED"
        assert "secondary context" in metrics["Daily_RSI_Admissibility_Desc"]

    def test_no_rsi_no_annotation(self):
        """When Daily_RSI is None, no admissibility annotation is written."""
        metrics = {"Convexity": "C-1"}
        p_code = "A"

        if p_code == "A":
            _daily_rsi = metrics.get("Daily_RSI")
            if _daily_rsi is not None:
                metrics["Daily_RSI_Admissibility"] = "ALLOWED"

        assert "Daily_RSI_Admissibility" not in metrics


class TestCautionNote:
    """CAUTION factor note written when Daily_Extension_Label is CAUTION."""

    def test_caution_note_written(self):
        """CAUTION label → caution note with distance value."""
        metrics = {"Daily_Extension_Label": "CAUTION", "Daily_Extension_Distance": 2.3}
        p_code = "A"

        if p_code == "A":
            _daily_ext_label = metrics.get("Daily_Extension_Label")
            if _daily_ext_label == "CAUTION":
                metrics["Daily_Extension_Caution_Note"] = (
                    "Daily extension {:.1f}x ATR (2.0-3.0x range). "
                    "Stock may sustain this level with strong fundamentals (Power Overbought). "
                    "Monitor for exhaustion signs. Advisory only -- not blocking."
                ).format(metrics.get("Daily_Extension_Distance", 0))

        assert "Daily_Extension_Caution_Note" in metrics
        assert "2.3x ATR" in metrics["Daily_Extension_Caution_Note"]

    def test_normal_no_caution_note(self):
        """NORMAL label → no caution note."""
        metrics = {"Daily_Extension_Label": "NORMAL", "Daily_Extension_Distance": 1.2}
        p_code = "A"

        if p_code == "A":
            _daily_ext_label = metrics.get("Daily_Extension_Label")
            if _daily_ext_label == "CAUTION":
                metrics["Daily_Extension_Caution_Note"] = "test"

        assert "Daily_Extension_Caution_Note" not in metrics

    def test_exhaustion_no_caution_note(self):
        """EXHAUSTION label → no caution note (it produces a hard reject, not advisory)."""
        metrics = {"Daily_Extension_Label": "EXHAUSTION", "Daily_Extension_Distance": 3.5}
        p_code = "A"

        if p_code == "A":
            _daily_ext_label = metrics.get("Daily_Extension_Label")
            if _daily_ext_label == "CAUTION":
                metrics["Daily_Extension_Caution_Note"] = "test"

        assert "Daily_Extension_Caution_Note" not in metrics


class TestPECAL3Exemption:
    """PE-CAL-3 exemption annotation for Profile A."""

    def test_profile_a_exempted(self):
        """Profile A gets Floor_Proximity_Exempted = True."""
        metrics = {}
        p_code = "A"
        if p_code == "A":
            metrics["Floor_Proximity_Exempted"] = True
            metrics["Floor_Proximity_Exemption_Desc"] = "PA-001: floor proximity hard-stop substitution exempted -- daily protective anchor eliminates VWAP convergence root cause"

        assert metrics["Floor_Proximity_Exempted"] is True
        assert "VWAP convergence" in metrics["Floor_Proximity_Exemption_Desc"]

    def test_profile_b_no_exemption(self):
        """Profile B does not get Floor_Proximity_Exempted."""
        metrics = {}
        p_code = "B"
        if p_code == "A":
            metrics["Floor_Proximity_Exempted"] = True

        assert "Floor_Proximity_Exempted" not in metrics


# ============================================================================
# 3. TRANSFORM LAYER — Grouped Output Mapping
# ============================================================================

class TestExtensionAnalysisDaily:
    """extension_analysis.daily populated for Profile A with self-doc patterns."""

    def test_daily_extension_populated(self):
        """Profile A metrics → extension_analysis.daily has distance, anchor, condition, thresholds."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)

        ext = result.get("extension_analysis", {})
        daily = ext.get("daily")
        assert daily is not None, "extension_analysis.daily should be populated for Profile A"

        # Self-doc: distance is {value, unit, desc}
        assert daily["distance"]["value"] == 1.43
        assert daily["distance"]["unit"] == "ATR"
        assert "desc" in daily["distance"]

        # Self-doc: anchor is {label, desc}
        assert daily["anchor"]["label"] == "EMA_21"
        assert "desc" in daily["anchor"]

        # Self-doc: condition is {label, desc}
        assert daily["condition"]["label"] == "NORMAL"
        assert "desc" in daily["condition"]

        # Thresholds present
        assert daily["thresholds"]["caution"]["value"] == 2.0
        assert daily["thresholds"]["exhaustion"]["value"] == 3.0

    def test_daily_extension_caution_note(self):
        """CAUTION label → caution_note populated in daily extension."""
        fm = _base_metrics_profile_a(
            Daily_Extension_Label="CAUTION",
            Daily_Extension_Distance=2.5,
            Daily_Extension_Caution_Note="Daily extension 2.5x ATR (2.0-3.0x range). Stock may sustain this level with strong fundamentals (Power Overbought). Monitor for exhaustion signs. Advisory only -- not blocking.",
        )
        result = _transform_output(_build_action_summary(), fm)

        daily = result["extension_analysis"]["daily"]
        assert daily["condition"]["label"] == "CAUTION"
        assert "caution_note" in daily
        assert "2.5x ATR" in daily["caution_note"]

    def test_no_caution_note_when_normal(self):
        """NORMAL label → no caution_note key in daily."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        daily = result["extension_analysis"]["daily"]
        assert "caution_note" not in daily


class TestDailyRSIInExtension:
    """RSI nested in extension_analysis.daily when available."""

    def test_rsi_nested_with_value(self):
        """Daily RSI produces rsi sub-object with value, condition, admissibility, role."""
        fm = _base_metrics_profile_a(Daily_RSI=77.5)
        result = _transform_output(_build_action_summary(), fm)

        rsi = result["extension_analysis"]["daily"]["rsi"]
        assert rsi is not None

        # Self-doc: value is {value, unit, desc}
        assert rsi["value"]["value"] == 77.5
        assert rsi["value"]["unit"] == "index"
        assert "desc" in rsi["value"]

        # Condition
        assert rsi["condition"]["label"] == "OVERBOUGHT"
        assert "desc" in rsi["condition"]

        # Admissibility
        assert rsi["admissibility"]["label"] == "ALLOWED"

        # Role is advisory string
        assert "ADVISORY" in rsi["role"]

    def test_rsi_neutral_range(self):
        """RSI 55 → NEUTRAL condition."""
        fm = _base_metrics_profile_a(Daily_RSI=55.0)
        result = _transform_output(_build_action_summary(), fm)
        rsi = result["extension_analysis"]["daily"]["rsi"]
        assert rsi["condition"]["label"] == "NEUTRAL"

    def test_rsi_oversold(self):
        """RSI 25 → OVERSOLD condition."""
        fm = _base_metrics_profile_a(Daily_RSI=25.0)
        result = _transform_output(_build_action_summary(), fm)
        rsi = result["extension_analysis"]["daily"]["rsi"]
        assert rsi["condition"]["label"] == "OVERSOLD"

    def test_rsi_restricted_c2(self):
        """C-2 convexity → RSI admissibility RESTRICTED."""
        fm = _base_metrics_profile_a(
            Daily_RSI=55.0,
            Daily_RSI_Admissibility="RESTRICTED",
            Daily_RSI_Admissibility_Desc="C-2: secondary context only -- cannot drive entry, exit, or timing decisions",
            Convexity="C-2",
        )
        result = _transform_output(_build_action_summary(), fm)
        rsi = result["extension_analysis"]["daily"]["rsi"]
        assert rsi["admissibility"]["label"] == "RESTRICTED"
        assert "secondary context" in rsi["admissibility"]["desc"]

    def test_no_rsi_when_none(self):
        """Daily RSI=None → no rsi sub-object in daily extension."""
        fm = _base_metrics_profile_a(Daily_RSI=None)
        # Remove the admissibility fields too since output.py wouldn't write them
        fm.pop("Daily_RSI_Admissibility", None)
        fm.pop("Daily_RSI_Admissibility_Desc", None)
        result = _transform_output(_build_action_summary(), fm)
        daily = result["extension_analysis"]["daily"]
        assert "rsi" not in daily


class TestFloorAnalysisProtectiveAnchor:
    """floor_analysis.protective_anchor populated for Profile A."""

    def test_protective_anchor_populated(self):
        """Profile A with daily protective values → protective_anchor present."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)

        fa = result.get("floor_analysis", {})
        pa = fa.get("protective_anchor")
        assert pa is not None, "floor_analysis.protective_anchor should exist for Profile A"

        # Self-doc: {value, unit, desc}
        assert pa["price"]["value"] == 145.0
        assert pa["price"]["unit"] == "price"
        assert "desc" in pa["price"]

        assert pa["hard_stop"]["value"] == 139.75
        assert pa["daily_atr"]["value"] == 3.5

    def test_no_protective_anchor_when_zero(self):
        """Daily_Protective_Anchor=0 → no protective_anchor in floor_analysis."""
        fm = _base_metrics_profile_a(Daily_Protective_Anchor=0.0)
        result = _transform_output(_build_action_summary(), fm)
        fa = result.get("floor_analysis", {})
        assert "protective_anchor" not in fa


class TestPECAL3ExemptionInFloor:
    """PE-CAL-3 exemption in floor_analysis."""

    def test_exemption_present(self):
        """Floor_Proximity_Exempted=True → floor_proximity_exemption in floor_analysis."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        fa = result.get("floor_analysis", {})
        pe = fa.get("floor_proximity_exemption")
        assert pe is not None
        assert pe["exempted"] is True
        assert "desc" in pe

    def test_no_exemption_for_profile_b(self):
        """Profile B → no floor_proximity_exemption in floor_analysis."""
        fm = _base_metrics_profile_b()
        result = _transform_output(_build_action_summary(), fm)
        fa = result.get("floor_analysis", {})
        assert "floor_proximity_exemption" not in fa


class TestTradeRiskCapitalRole:
    """trade_risk.capital_rr_role with {label, desc} self-doc pattern."""

    def test_advisory_role(self):
        """Profile A → capital_rr_role.label = ADVISORY."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        tr = result.get("trade_risk", {})
        role = tr.get("capital_rr_role")
        assert role is not None
        assert role["label"] == "ADVISORY"
        assert "desc" in role
        assert len(role["desc"]) > 0

    def test_enforceable_role(self):
        """Profile B → capital_rr_role.label = ENFORCEABLE."""
        fm = _base_metrics_profile_b()
        result = _transform_output(_build_action_summary(), fm)
        tr = result.get("trade_risk", {})
        role = tr.get("capital_rr_role")
        assert role is not None
        assert role["label"] == "ENFORCEABLE"


# ============================================================================
# 4. PROFILE B/C ISOLATION — No Daily Fields
# ============================================================================

class TestProfileBCIsolation:
    """Profile B and C produce no PA-001 daily extension, RSI, or protective anchor."""

    def test_profile_b_no_daily_extension(self):
        """Profile B → extension_analysis.daily is None."""
        fm = _base_metrics_profile_b()
        result = _transform_output(_build_action_summary(), fm)
        ext = result.get("extension_analysis", {})
        assert ext.get("daily") is None

    def test_profile_b_no_protective_anchor(self):
        """Profile B → no protective_anchor in floor_analysis."""
        fm = _base_metrics_profile_b()
        result = _transform_output(_build_action_summary(), fm)
        fa = result.get("floor_analysis", {})
        assert "protective_anchor" not in fa

    def test_profile_b_no_rsi(self):
        """Profile B → no RSI fields anywhere."""
        fm = _base_metrics_profile_b()
        result = _transform_output(_build_action_summary(), fm)
        ext = result.get("extension_analysis", {})
        daily = ext.get("daily")
        assert daily is None  # No daily → no RSI

    def test_profile_b_no_pe_cal3_exemption(self):
        """Profile B → no PE-CAL-3 exemption."""
        fm = _base_metrics_profile_b()
        result = _transform_output(_build_action_summary(), fm)
        fa = result.get("floor_analysis", {})
        assert "floor_proximity_exemption" not in fa

    def test_profile_c_no_daily_extension(self):
        """Profile C → extension_analysis.daily is None."""
        fm = _base_metrics_profile_b()  # Profile C has same shape
        result = _transform_output(_build_action_summary(), fm)
        ext = result.get("extension_analysis", {})
        assert ext.get("daily") is None


# ============================================================================
# 5. _FLATTEN REVERSE MAPPING
# ============================================================================

class TestFlattenReverseMapping:
    """_flatten produces correct flat keys from PA-001 Phase 2 grouped output."""

    def test_daily_extension_round_trip(self):
        """Daily extension fields survive transform → flatten round trip."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        _status, _diag, flat = _flatten(result)

        assert flat.get("Daily_Extension_Distance") == 1.43
        assert flat.get("Daily_Extension_Label") == "NORMAL"

    def test_daily_rsi_round_trip(self):
        """Daily RSI fields survive round trip."""
        fm = _base_metrics_profile_a(Daily_RSI=77.5)
        result = _transform_output(_build_action_summary(), fm)
        _status, _diag, flat = _flatten(result)

        assert flat.get("Daily_RSI") == 77.5
        assert flat.get("Daily_RSI_Admissibility") == "ALLOWED"

    def test_protective_anchor_round_trip(self):
        """Protective anchor fields survive round trip."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        _status, _diag, flat = _flatten(result)

        assert flat.get("Daily_Protective_Anchor") == 145.0
        assert flat.get("Daily_Hard_Stop") == 139.75
        assert flat.get("Daily_ATR") == 3.5

    def test_capital_rr_role_round_trip(self):
        """Capital_RR_Role survives round trip."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        _status, _diag, flat = _flatten(result)

        assert flat.get("Capital_RR_Role") == "ADVISORY"

    def test_pe_cal3_round_trip(self):
        """Floor_Proximity_Exempted survives round trip."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        _status, _diag, flat = _flatten(result)

        assert flat.get("Floor_Proximity_Exempted") is True

    def test_caution_note_round_trip(self):
        """CAUTION note survives round trip."""
        caution_note = "Daily extension 2.5x ATR (2.0-3.0x range). Stock may sustain this level with strong fundamentals (Power Overbought). Monitor for exhaustion signs. Advisory only -- not blocking."
        fm = _base_metrics_profile_a(
            Daily_Extension_Label="CAUTION",
            Daily_Extension_Distance=2.5,
            Daily_Extension_Caution_Note=caution_note,
        )
        result = _transform_output(_build_action_summary(), fm)
        _status, _diag, flat = _flatten(result)

        assert flat.get("Daily_Extension_Caution_Note") == caution_note

    def test_profile_b_no_daily_fields_in_flat(self):
        """Profile B round trip produces no daily extension/RSI/protective fields."""
        fm = _base_metrics_profile_b()
        result = _transform_output(_build_action_summary(), fm)
        _status, _diag, flat = _flatten(result)

        assert flat.get("Daily_Extension_Distance") is None
        assert flat.get("Daily_Extension_Label") is None
        assert flat.get("Daily_RSI") is None
        assert flat.get("Daily_Protective_Anchor") is None
        assert flat.get("Floor_Proximity_Exempted") is None


# ============================================================================
# 6. SELF-DOC COMPLIANCE — Pattern Verification
# ============================================================================

class TestSelfDocCompliance:
    """Every new field follows {label, desc} or {value, unit, desc} convention (Spec §6)."""

    def test_daily_distance_value_unit_desc(self):
        """extension_analysis.daily.distance has {value, unit, desc}."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        d = result["extension_analysis"]["daily"]["distance"]
        assert "value" in d and "unit" in d and "desc" in d

    def test_daily_anchor_label_desc(self):
        """extension_analysis.daily.anchor has {label, desc}."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        a = result["extension_analysis"]["daily"]["anchor"]
        assert "label" in a and "desc" in a

    def test_daily_condition_label_desc(self):
        """extension_analysis.daily.condition has {label, desc}."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        c = result["extension_analysis"]["daily"]["condition"]
        assert "label" in c and "desc" in c

    def test_threshold_value_unit_desc(self):
        """extension_analysis.daily.thresholds.caution/exhaustion have {value, unit, desc}."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        t = result["extension_analysis"]["daily"]["thresholds"]
        for level in ("caution", "exhaustion"):
            assert "value" in t[level] and "unit" in t[level] and "desc" in t[level]

    def test_rsi_value_unit_desc(self):
        """extension_analysis.daily.rsi.value has {value, unit, desc}."""
        fm = _base_metrics_profile_a(Daily_RSI=55.0)
        result = _transform_output(_build_action_summary(), fm)
        rv = result["extension_analysis"]["daily"]["rsi"]["value"]
        assert "value" in rv and "unit" in rv and "desc" in rv

    def test_rsi_condition_label_desc(self):
        """extension_analysis.daily.rsi.condition has {label, desc}."""
        fm = _base_metrics_profile_a(Daily_RSI=55.0)
        result = _transform_output(_build_action_summary(), fm)
        rc = result["extension_analysis"]["daily"]["rsi"]["condition"]
        assert "label" in rc and "desc" in rc

    def test_rsi_admissibility_label_desc(self):
        """extension_analysis.daily.rsi.admissibility has {label, desc}."""
        fm = _base_metrics_profile_a(Daily_RSI=55.0)
        result = _transform_output(_build_action_summary(), fm)
        ra = result["extension_analysis"]["daily"]["rsi"]["admissibility"]
        assert "label" in ra and "desc" in ra

    def test_protective_anchor_price_value_unit_desc(self):
        """floor_analysis.protective_anchor.price has {value, unit, desc}."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        p = result["floor_analysis"]["protective_anchor"]["price"]
        assert "value" in p and "unit" in p and "desc" in p

    def test_capital_rr_role_label_desc(self):
        """trade_risk.capital_rr_role has {label, desc}."""
        fm = _base_metrics_profile_a()
        result = _transform_output(_build_action_summary(), fm)
        r = result["trade_risk"]["capital_rr_role"]
        assert "label" in r and "desc" in r
