"""STRUCT-001-TFR-1: Transform layer tests for 5 Phase 3 advisory metrics.

12 test cases verifying advisory sub-object in grouped output,
round-trip via _flatten(), and MAPPED_FLAT_KEYS coverage.
"""

import sys, os, pytest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

for _mod in ('ib_insync', 'ib_insync.util', 'plotly', 'plotly.graph_objects',
             'plotly.subplots', 'pandas_ta', 'yfinance', 'finnhub',
             'google.genai', 'google'):
    if _mod not in sys.modules:
        sys.modules[_mod] = mock.MagicMock()

from tbs_engine.transform import _transform_output, _flatten, MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_action_summary():
    return {
        "verdict": "VALID",
        "reason": "Test",
        "mandate": "Test mandate.",
        "context": "Test context.",
    }


def _minimal_flat(**overrides):
    """Flat metrics dict with THS keys + minimum for transform to run."""
    m = {
        "Trend_Health_Score": 65.0,
        "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 70.0,
        "THS_Dir_Momentum": 55.0,
        "THS_Trend_Age": 80.0,
        "THS_Structure": 60.0,
        "THS_Floor_Buffer_Label": "HEALTHY",
        "THS_Dir_Momentum_Label": "ACCEPTABLE",
        "THS_Trend_Age_Label": "STRONG",
        "THS_Structure_Label": "HEALTHY",
        # STRUCT-001 Phase 3 advisory keys (defaults: all inactive)
        "THS_Death_Cross_Cap": False,
        "THS_Component_Cap": None,
        "THS_VWAP_Floor_Penalty": False,
        "THS_VWAP_Floor_Note": None,
        "THS_Context_Advisory": None,
    }
    m.update(overrides)
    return m


def _get_advisory(flat_overrides=None):
    """Run transform and return the advisory sub-object."""
    fm = _minimal_flat(**(flat_overrides or {}))
    grouped = _transform_output(_minimal_action_summary(), fm)
    tq = grouped.get("trade_quality", {})
    th = tq.get("trend_health", {})
    return th.get("advisory", {})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSTRUCT001TFR1:

    def test_01_advisory_present(self):
        """Advisory sub-object exists with all 4 sub-objects."""
        adv = _get_advisory()
        assert "death_cross_cap" in adv
        assert "component_cap" in adv
        assert "vwap_penalty" in adv
        assert "context_warning" in adv

    def test_02_death_cross_active(self):
        adv = _get_advisory({"THS_Death_Cross_Cap": True})
        assert adv["death_cross_cap"]["active"] is True

    def test_03_death_cross_inactive(self):
        adv = _get_advisory({"THS_Death_Cross_Cap": False})
        assert adv["death_cross_cap"]["active"] is False

    def test_04_component_cap_active(self):
        adv = _get_advisory({"THS_Component_Cap": "Dir_Momentum 13 < 40"})
        assert adv["component_cap"]["active"] is True
        assert adv["component_cap"]["trigger"] == "Dir_Momentum 13 < 40"

    def test_05_component_cap_inactive(self):
        adv = _get_advisory({"THS_Component_Cap": None})
        assert adv["component_cap"]["active"] is False
        assert adv["component_cap"]["trigger"] is None

    def test_06_vwap_penalty_active(self):
        note = "VWAP floor resets at next session open -- overnight protection relies on hard stop only"
        adv = _get_advisory({"THS_VWAP_Floor_Penalty": True, "THS_VWAP_Floor_Note": note})
        assert adv["vwap_penalty"]["active"] is True
        assert adv["vwap_penalty"]["note"] == note

    def test_07_vwap_penalty_inactive(self):
        adv = _get_advisory({"THS_VWAP_Floor_Penalty": False, "THS_VWAP_Floor_Note": None})
        assert adv["vwap_penalty"]["active"] is False
        assert adv["vwap_penalty"]["note"] is None

    def test_08_context_advisory_with_message(self):
        msg = "Daily EMA 8 < EMA 21 (bearish context)"
        adv = _get_advisory({"THS_Context_Advisory": msg})
        assert adv["context_warning"]["message"] == msg

    def test_09_context_advisory_null(self):
        adv = _get_advisory({"THS_Context_Advisory": None})
        assert adv["context_warning"]["message"] is None

    def test_10_roundtrip_flatten(self):
        """Transform -> flatten recovers all 5 original flat values."""
        originals = {
            "THS_Death_Cross_Cap": True,
            "THS_Component_Cap": "Structure 22 < 40",
            "THS_VWAP_Floor_Penalty": True,
            "THS_VWAP_Floor_Note": "VWAP floor resets at next session open -- overnight protection relies on hard stop only",
            "THS_Context_Advisory": "Daily EMA 8 < EMA 21 (bearish context) | Daily SMA 50 slope declining (-0.42)",
        }
        fm = _minimal_flat(**originals)
        grouped = _transform_output(_minimal_action_summary(), fm)
        _status, _diag, recovered = _flatten(grouped)
        for key, expected in originals.items():
            assert recovered.get(key) == expected, f"{key}: {recovered.get(key)} != {expected}"

    def test_11_mapped_flat_keys(self):
        """All 5 advisory keys in MAPPED_FLAT_KEYS."""
        for k in ("THS_Death_Cross_Cap", "THS_Component_Cap",
                   "THS_VWAP_Floor_Penalty", "THS_VWAP_Floor_Note",
                   "THS_Context_Advisory"):
            assert k in MAPPED_FLAT_KEYS, f"{k} not in MAPPED_FLAT_KEYS"

    def test_12_desc_fields_nonempty(self):
        """All desc fields are non-empty strings."""
        adv = _get_advisory()
        for sub_key in ("death_cross_cap", "component_cap", "vwap_penalty", "context_warning"):
            desc = adv[sub_key]["desc"]
            assert isinstance(desc, str) and len(desc) > 0, f"{sub_key}.desc invalid: {desc!r}"
