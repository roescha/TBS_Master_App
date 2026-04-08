"""
test_msx_synthesis.py -- MSX-001 Unit Tests (Spec Section 14: TC-01 through TC-20)
"""

import json
import pytest
from msx_synthesis import (
    synthesize_microstructure, merge_narrative, format_dashboard,
    _signal_put_wall, _signal_call_wall, _signal_pcr,
    _signal_dark_pool, _signal_block_trades, _signal_sweeps,
    _signal_insider, _signal_premarket,
)


# ---------------------------------------------------------------------------
# Helper: build a full SUPPORTIVE modk set
# ---------------------------------------------------------------------------

def _full_modk_supportive():
    return {
        "Options_Status": "AVAILABLE",
        "Options_Put_Wall": 185.0, "Options_Put_Wall_OI": 12450,
        "Options_Put_Wall_Distance": 0.3,
        "Options_Call_Wall": 195.0, "Options_Call_Wall_OI": 8200,
        "Options_Call_Wall_Distance": 1.8,
        "Options_PCR": 1.35, "Options_PCR_Label": "EXTREME BEARISH",
    }

def _full_flow_supportive():
    return {
        "Flow_Label": "STRONG INSTITUTIONAL BUYING",
        "Flow_Block_Trades_Count": 3,
        "Flow_Block_Trades_Notable": "2x buy-side blocks at $192",
        "Flow_Sweep_Bullish_Count": 5, "Flow_Sweep_Bearish_Count": 1,
        "Flow_Status": "AVAILABLE",
    }

def _full_insider_supportive():
    return {
        "Insider_Status": "AVAILABLE",
        "Insider_Cluster_Buy": True, "Insider_Buy_Count_30d": 4,
        "Insider_BS_Ratio_30d": 0.8,
    }

def _full_pmc_supportive():
    return {
        "PMC_Status": "AVAILABLE",
        "PMC_Gap_Direction": "UP", "PMC_Gap_Pct": 1.2,
        "PMC_Catalyst_Flag": True,
    }


# ---------------------------------------------------------------------------
# TC-01: All SUPPORTIVE
# ---------------------------------------------------------------------------
def test_tc01_all_supportive():
    r = synthesize_microstructure(
        _full_modk_supportive(), _full_flow_supportive(),
        _full_insider_supportive(), _full_pmc_supportive(),
    )
    assert r["MSX_Regime"] == "SUPPORTIVE"
    assert r["MSX_Score"] is not None and r["MSX_Score"] > 0.3
    assert r["MSX_Components_Available"] == 8
    assert r["MSX_Status"] == "AVAILABLE"


# ---------------------------------------------------------------------------
# TC-02: All CAUTIONARY
# ---------------------------------------------------------------------------
def test_tc02_all_cautionary():
    modk = {
        "Options_Status": "AVAILABLE",
        "Options_Put_Wall": 185.0, "Options_Put_Wall_OI": 12450,
        "Options_Put_Wall_Distance": -0.5,  # price below wall
        "Options_Call_Wall": 195.0, "Options_Call_Wall_OI": 8200,
        "Options_Call_Wall_Distance": 0.3,  # ceiling pressure
        "Options_PCR": 1.10, "Options_PCR_Label": "BEARISH",
    }
    flow = {
        "Flow_Label": "NET_SELLING",
        "Flow_Block_Trades_Count": 2,
        "Flow_Block_Trades_Notable": "sell-side block at $188",
        "Flow_Sweep_Bullish_Count": 1, "Flow_Sweep_Bearish_Count": 5,
        "Flow_Status": "AVAILABLE",
    }
    insider = {
        "Insider_Status": "AVAILABLE",
        "Insider_Cluster_Buy": False, "Insider_Buy_Count_30d": 0,
        "Insider_BS_Ratio_30d": 0.15,
    }
    pmc = {
        "PMC_Status": "AVAILABLE",
        "PMC_Gap_Direction": "DOWN", "PMC_Gap_Pct": -3.1,
        "PMC_Catalyst_Flag": False,
    }
    r = synthesize_microstructure(modk, flow, insider, pmc)
    assert r["MSX_Regime"] == "CAUTIONARY"
    assert r["MSX_Score"] < -0.3
    assert r["MSX_Components_Available"] == 8


# ---------------------------------------------------------------------------
# TC-03: Mixed signals
# ---------------------------------------------------------------------------
def test_tc03_mixed():
    modk = _full_modk_supportive()
    flow = {
        "Flow_Label": "NET_SELLING",
        "Flow_Block_Trades_Count": 0,
        "Flow_Sweep_Bullish_Count": 2, "Flow_Sweep_Bearish_Count": 2,
        "Flow_Status": "AVAILABLE",
    }
    r = synthesize_microstructure(modk, flow, {}, {})
    # Score should be in [-0.3, +0.3] range roughly
    assert r["MSX_Score"] is not None


# ---------------------------------------------------------------------------
# TC-04: Score near +0.3 boundary (3S, 2N, 1C out of 6 = +0.33)
# ---------------------------------------------------------------------------
def test_tc04_boundary_positive():
    # 6 components: put_wall(S), call_wall(N), pcr(S), dark_pool(C), sweeps(S), insider(N)
    # No flow block trades (Flow_Status not set -> excluded), no PMC
    modk = {
        "Options_Status": "AVAILABLE",
        "Options_Put_Wall": 185.0, "Options_Put_Wall_OI": 12450,
        "Options_Put_Wall_Distance": 0.3,  # SUPPORTIVE
        "Options_Call_Wall": 195.0, "Options_Call_Wall_OI": 8200,
        "Options_Call_Wall_Distance": 1.8,  # NEUTRAL
        "Options_PCR": 1.35, "Options_PCR_Label": "EXTREME BEARISH",  # SUPPORTIVE
    }
    flow = {
        "Flow_Label": "NET_SELLING",  # CAUTIONARY
        "Flow_Sweep_Bullish_Count": 5, "Flow_Sweep_Bearish_Count": 1,  # SUPPORTIVE (5:1)
    }
    insider = {
        "Insider_Status": "AVAILABLE",
        "Insider_Cluster_Buy": False,
        "Insider_BS_Ratio_30d": 0.5,  # NEUTRAL
        "Insider_Buy_Count_30d": 1,
    }
    r = synthesize_microstructure(modk, flow, insider, {})
    # 3S + 2N + 1C = (3-1)/6 = 0.33 -> SUPPORTIVE
    assert r["MSX_Components_Available"] == 6
    assert r["MSX_Score"] == pytest.approx(0.33, abs=0.01)
    assert r["MSX_Regime"] == "SUPPORTIVE"


# ---------------------------------------------------------------------------
# TC-05: Score near -0.3 boundary (1S, 2N, 3C out of 6 = -0.33)
# ---------------------------------------------------------------------------
def test_tc05_boundary_negative():
    # 6 components: put_wall(C), call_wall(C), pcr(N), dark_pool(N), sweeps(C), insider(S)
    modk = {
        "Options_Status": "AVAILABLE",
        "Options_Put_Wall": 185.0, "Options_Put_Wall_OI": 12450,
        "Options_Put_Wall_Distance": -0.5,  # CAUTIONARY
        "Options_Call_Wall": 195.0, "Options_Call_Wall_OI": 8200,
        "Options_Call_Wall_Distance": 0.3,  # CAUTIONARY
        "Options_PCR": 0.65, "Options_PCR_Label": "NEUTRAL",  # NEUTRAL
    }
    flow = {
        "Flow_Label": "MIXED FLOW",  # NEUTRAL
        "Flow_Sweep_Bullish_Count": 1, "Flow_Sweep_Bearish_Count": 5,  # CAUTIONARY
    }
    insider = {
        "Insider_Status": "AVAILABLE",
        "Insider_Cluster_Buy": True, "Insider_Buy_Count_30d": 3,  # SUPPORTIVE
        "Insider_BS_Ratio_30d": 0.8,
    }
    r = synthesize_microstructure(modk, flow, insider, {})
    assert r["MSX_Components_Available"] == 6
    assert r["MSX_Score"] == pytest.approx(-0.33, abs=0.01)
    assert r["MSX_Regime"] == "CAUTIONARY"


# ---------------------------------------------------------------------------
# TC-06: Score exactly at boundary (2S, 4N out of 6 = +0.33 > +0.3)
# ---------------------------------------------------------------------------
def test_tc06_exact_boundary():
    # 6 components: put_wall(S), call_wall(N), pcr(N), dark_pool(N), sweeps(S), insider(N)
    modk = {
        "Options_Status": "AVAILABLE",
        "Options_Put_Wall": 185.0, "Options_Put_Wall_OI": 12450,
        "Options_Put_Wall_Distance": 0.3,  # SUPPORTIVE
        "Options_Call_Wall": 195.0, "Options_Call_Wall_OI": 8200,
        "Options_Call_Wall_Distance": 1.8,  # NEUTRAL
        "Options_PCR": 0.65, "Options_PCR_Label": "NEUTRAL",  # NEUTRAL
    }
    flow = {
        "Flow_Label": "MIXED FLOW",  # NEUTRAL
        "Flow_Sweep_Bullish_Count": 5, "Flow_Sweep_Bearish_Count": 1,  # SUPPORTIVE (5:1)
    }
    insider = {
        "Insider_Status": "AVAILABLE",
        "Insider_Cluster_Buy": False,
        "Insider_BS_Ratio_30d": 0.5,  # NEUTRAL
        "Insider_Buy_Count_30d": 1,
    }
    r = synthesize_microstructure(modk, flow, insider, {})
    assert r["MSX_Components_Available"] == 6
    assert r["MSX_Score"] == pytest.approx(0.33, abs=0.01)
    assert r["MSX_Regime"] == "SUPPORTIVE"


# ---------------------------------------------------------------------------
# TC-07: Below minimum (only 2 components available)
# ---------------------------------------------------------------------------
def test_tc07_below_minimum():
    modk = {
        "Options_Status": "AVAILABLE",
        "Options_Put_Wall": 185.0, "Options_Put_Wall_OI": 12450,
        "Options_Put_Wall_Distance": 0.3,
        "Options_Call_Wall": 195.0, "Options_Call_Wall_OI": 8200,
        "Options_Call_Wall_Distance": 1.8,
        # No PCR
    }
    r = synthesize_microstructure(modk, {}, {}, {})
    assert r["MSX_Regime"] == "NEUTRAL"
    assert r["MSX_Score"] is None
    assert r["MSX_Status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# TC-08: Exactly at minimum (3 components)
# ---------------------------------------------------------------------------
def test_tc08_at_minimum():
    modk = {
        "Options_Status": "AVAILABLE",
        "Options_Put_Wall": 185.0, "Options_Put_Wall_OI": 12450,
        "Options_Put_Wall_Distance": 0.3,
        "Options_Call_Wall": 195.0, "Options_Call_Wall_OI": 8200,
        "Options_Call_Wall_Distance": 1.8,
        "Options_PCR": 0.65, "Options_PCR_Label": "NEUTRAL",
    }
    r = synthesize_microstructure(modk, {}, {}, {})
    assert r["MSX_Components_Available"] == 3
    assert r["MSX_Score"] is not None
    assert r["MSX_Status"] in ("AVAILABLE", "PARTIAL")


# ---------------------------------------------------------------------------
# TC-09: ETF handling (insider excluded)
# ---------------------------------------------------------------------------
def test_tc09_etf():
    r = synthesize_microstructure(
        _full_modk_supportive(), _full_flow_supportive(),
        {"Insider_Status": "N/A"}, _full_pmc_supportive(),
        is_etf=True,
    )
    summary = r["MSX_Component_Summary"]
    assert summary["Insider Cluster"]["signal"] == "N/A"
    # Component count should be 7 max (8 minus insider)
    assert r["MSX_Components_Available"] == 7


# ---------------------------------------------------------------------------
# TC-10: MOD-K UNAVAILABLE
# ---------------------------------------------------------------------------
def test_tc10_modk_unavailable():
    modk = {"Options_Status": "UNAVAILABLE"}
    r = synthesize_microstructure(modk, _full_flow_supportive(),
                                  _full_insider_supportive(), _full_pmc_supportive())
    assert r["MSX_Support_Level"] is None
    assert r["MSX_Resistance_Level"] is None
    summary = r["MSX_Component_Summary"]
    assert summary["Put Wall Prox."]["signal"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# TC-11: Gemini narrative failure (template fallback)
# ---------------------------------------------------------------------------
def test_tc11_gemini_failure():
    r = synthesize_microstructure(
        _full_modk_supportive(), _full_flow_supportive(),
        _full_insider_supportive(), _full_pmc_supportive(),
    )
    # Pass 2: merge with None narrative -> template fallback, PARTIAL
    merged = merge_narrative(r, None)
    assert merged["MSX_Status"] == "PARTIAL"
    assert len(merged["MSX_Conviction_Note"]) > 0


# ---------------------------------------------------------------------------
# TC-12: Gemini contradicts label
# ---------------------------------------------------------------------------
def test_tc12_gemini_contradiction():
    r = synthesize_microstructure(
        _full_modk_supportive(), _full_flow_supportive(),
        _full_insider_supportive(), _full_pmc_supportive(),
    )
    assert r["MSX_Regime"] == "SUPPORTIVE"
    merged = merge_narrative(r, "The microstructure environment is cautionary with adverse flow.")
    assert "rule-based label is authoritative" in merged["MSX_Conviction_Note"]


# ---------------------------------------------------------------------------
# TC-13: GEX NOT IMPLEMENTED
# ---------------------------------------------------------------------------
def test_tc13_gex_not_implemented():
    r = synthesize_microstructure(_full_modk_supportive(), {}, {}, {})
    summary = r["MSX_Component_Summary"]
    assert "Gamma Regime" in summary
    assert summary["Gamma Regime"]["signal"] == "NOT IMPLEMENTED"
    assert r["MSX_Components_Total"] == 8


# ---------------------------------------------------------------------------
# TC-14: All upstream fail
# ---------------------------------------------------------------------------
def test_tc14_all_fail():
    r = synthesize_microstructure({}, {}, {}, {})
    assert r["MSX_Status"] == "UNAVAILABLE"
    assert r["MSX_Components_Available"] == 0


# ---------------------------------------------------------------------------
# TC-15: FLOW-001 partial (dark pool available, sweeps unavailable)
# ---------------------------------------------------------------------------
def test_tc15_flow_partial():
    flow = {
        "Flow_Label": "NET_BUYING",
        "Flow_Block_Trades_Count": 0,
        "Flow_Status": "AVAILABLE",
        # No sweep data
    }
    r = synthesize_microstructure(_full_modk_supportive(), flow, {}, {})
    summary = r["MSX_Component_Summary"]
    assert summary["Dark Pool"]["signal"] == "SUPPORTIVE"
    # Sweeps should still get a value (0/0 -> NEUTRAL)


# ---------------------------------------------------------------------------
# TC-16: PCR BULLISH maps to NEUTRAL
# ---------------------------------------------------------------------------
def test_tc16_pcr_bullish():
    sig = _signal_pcr({"Options_PCR": 0.65, "Options_PCR_Label": "BULLISH"})
    assert sig is not None
    assert sig[0] == "NEUTRAL"


# ---------------------------------------------------------------------------
# TC-17: Insider heavy selling (bs_ratio < 0.3)
# ---------------------------------------------------------------------------
def test_tc17_insider_heavy_selling():
    sig = _signal_insider({
        "Insider_Status": "AVAILABLE",
        "Insider_Cluster_Buy": False,
        "Insider_BS_Ratio_30d": 0.15,
    })
    assert sig is not None
    assert sig[0] == "CAUTIONARY"


# ---------------------------------------------------------------------------
# TC-18: Gap down >= 2%
# ---------------------------------------------------------------------------
def test_tc18_gap_down():
    sig = _signal_premarket({
        "PMC_Status": "AVAILABLE",
        "PMC_Gap_Direction": "DOWN", "PMC_Gap_Pct": -3.1,
        "PMC_Catalyst_Flag": False,
    })
    assert sig is not None
    assert sig[0] == "CAUTIONARY"


# ---------------------------------------------------------------------------
# TC-19: Gap up without catalyst
# ---------------------------------------------------------------------------
def test_tc19_gap_up_no_catalyst():
    sig = _signal_premarket({
        "PMC_Status": "AVAILABLE",
        "PMC_Gap_Direction": "UP", "PMC_Gap_Pct": 1.5,
        "PMC_Catalyst_Flag": False,
    })
    assert sig is not None
    assert sig[0] == "NEUTRAL"


# ---------------------------------------------------------------------------
# TC-20: CLI --raw output (JSON structure)
# ---------------------------------------------------------------------------
def test_tc20_raw_output():
    r = synthesize_microstructure(
        _full_modk_supportive(), _full_flow_supportive(),
        _full_insider_supportive(), _full_pmc_supportive(),
    )
    raw = json.dumps(r, default=str)
    parsed = json.loads(raw)
    required_keys = [
        "MSX_Regime", "MSX_Score", "MSX_Support_Level", "MSX_Resistance_Level",
        "MSX_Conviction_Note", "MSX_Component_Summary",
        "MSX_Components_Available", "MSX_Components_Total", "MSX_Status",
    ]
    for k in required_keys:
        assert k in parsed, f"Missing key: {k}"


# ---------------------------------------------------------------------------
# Additional: Dashboard formatting smoke test
# ---------------------------------------------------------------------------
def test_dashboard_format():
    r = synthesize_microstructure(
        _full_modk_supportive(), _full_flow_supportive(),
        _full_insider_supportive(), _full_pmc_supportive(),
    )
    text = format_dashboard(r)
    assert "MICROSTRUCTURE SYNTHESIS" in text
    assert "Regime:" in text
    assert "Score:" in text
    assert "Gamma Regime" in text
    assert "NOT IMPLEMENTED" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
