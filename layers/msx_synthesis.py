"""
msx_synthesis.py -- MSX-001 Microstructure Synthesis Layer
Sub-Phase 2D: Post-engine informational overlay. Zero engine impact.

Consumes upstream signals from MOD-K (ibkr_options_context.py),
FLOW-001/MOD-M (ai_institutional_context.py), and PMC-001 (Layer 2)
to produce a single regime label, key levels, and conviction narrative.

Public interface:
  synthesize_microstructure(modk_metrics, flow_metrics, insider_metrics,
                            pmc_metrics, gex_metrics=None) -> dict

  merge_narrative(msx_pass1, gemini_narrative) -> dict

CLI:
  python msx_synthesis.py --raw < upstream.json
  echo '{}' | python msx_synthesis.py
"""

import argparse
import json
import re
import sys


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCORE_THRESHOLD_SUPPORTIVE = 0.3
SCORE_THRESHOLD_CAUTIONARY = -0.3
MIN_COMPONENTS = 3
COMPONENTS_TOTAL_BASE = 8  # Components 1-8 (MOD-K + FLOW + MOD-M + PMC)
COMPONENTS_TOTAL_GEX = 9   # Components 1-9 (includes GEX-001 Gamma Regime)


# ---------------------------------------------------------------------------
# Component Signal Mapping (Spec Section 3)
# ---------------------------------------------------------------------------

def _signal_put_wall(modk: dict) -> tuple:
    """Component 1: Put Wall Proximity. Returns (signal, detail) or None if unavailable."""
    dist = modk.get("Options_Put_Wall_Distance")
    if dist is None:
        return None
    if dist < 0:
        return ("CAUTIONARY", "%.1f ATR (price below wall)" % dist)
    if dist <= 0.5:
        return ("SUPPORTIVE", "%.1f ATR (floor reinforced)" % dist)
    return ("NEUTRAL", "+%.1f ATR" % dist)


def _signal_call_wall(modk: dict) -> tuple:
    """Component 2: Call Wall Proximity. Never SUPPORTIVE."""
    dist = modk.get("Options_Call_Wall_Distance")
    if dist is None:
        return None
    if dist <= 0.5:
        return ("CAUTIONARY", "+%.1f ATR (ceiling pressure)" % dist)
    return ("NEUTRAL", "+%.1f ATR (ceiling distant)" % dist)


def _signal_pcr(modk: dict) -> tuple:
    """Component 3: PCR. Contrarian mapping."""
    label = modk.get("Options_PCR_Label")
    pcr_val = modk.get("Options_PCR")
    if label is None:
        return None
    _PCR_ABBREV = {
        "EXTREME BEARISH": "XBEAR",
        "BEARISH": "BEAR",
        "NEUTRAL": "NTRL",
        "BULLISH": "BULL",
    }
    detail = ""
    if pcr_val is not None:
        detail = "%.2f %s" % (pcr_val, _PCR_ABBREV.get(label, label))
    else:
        detail = label
    if label == "EXTREME BEARISH":
        return ("SUPPORTIVE", detail + " (contrarian)")
    if label == "BEARISH":
        return ("CAUTIONARY", detail)
    # NEUTRAL and BULLISH both map to NEUTRAL
    return ("NEUTRAL", detail)


def _signal_dark_pool(flow: dict) -> tuple:
    """Component 4: Dark Pool Sentiment."""
    label = flow.get("Flow_Label")
    if label is None or label == "INSUFFICIENT DATA":
        return None  # excluded from count
    if label in ("STRONG INSTITUTIONAL BUYING", "NET_BUYING"):
        return ("SUPPORTIVE", label)
    if label in ("INSTITUTIONAL SELLING PRESSURE", "NET_SELLING"):
        return ("CAUTIONARY", label)
    # MIXED FLOW, NEUTRAL, anything else
    return ("NEUTRAL", label)


def _signal_block_trades(flow: dict) -> tuple:
    """Component 5: Block Trades. Derive bias from notable text."""
    # Exclude if flow data not available
    if flow.get("Flow_Status") not in ("AVAILABLE",) and not flow.get("Flow_Block_Trades_Notable") and not flow.get("Flow_Block_Trades_Count"):
        return None
    notable = flow.get("Flow_Block_Trades_Notable") or ""
    count = flow.get("Flow_Block_Trades_Count") or 0
    if count == 0 and not notable:
        return ("NEUTRAL", "None reported")
    notable_lower = notable.lower()
    has_buy = "buy" in notable_lower
    has_sell = "sell" in notable_lower
    if has_buy and not has_sell:
        return ("SUPPORTIVE", "BUY-DOMINANT")
    if has_sell and not has_buy:
        return ("CAUTIONARY", "SELL-DOMINANT")
    return ("NEUTRAL", "MIXED" if (has_buy and has_sell) else "---")


def _signal_sweeps(flow: dict) -> tuple:
    """Component 6: Sweeps. 2:1 ratio threshold."""
    bull = flow.get("Flow_Sweep_Bullish_Count")
    bear = flow.get("Flow_Sweep_Bearish_Count")
    if bull is None and bear is None:
        return None
    bull = bull or 0
    bear = bear or 0
    detail = "%d bull / %d bear" % (bull, bear)
    if bull > 0 and bear > 0:
        if bull / bear >= 2.0:
            return ("SUPPORTIVE", detail)
        if bear / bull >= 2.0:
            return ("CAUTIONARY", detail)
    elif bull > 0 and bear == 0:
        return ("SUPPORTIVE", detail)
    elif bear > 0 and bull == 0:
        return ("CAUTIONARY", detail)
    return ("NEUTRAL", detail)


def _signal_insider(insider: dict, is_etf: bool = False) -> tuple:
    """Component 7: Insider Cluster. N/A for ETFs."""
    if is_etf:
        return None  # excluded
    status = insider.get("Insider_Status")
    if status in ("N/A", None):
        return None
    if status == "UNAVAILABLE":
        return None
    cluster = insider.get("Insider_Cluster_Buy")
    if cluster is True:
        buy_c = insider.get("Insider_Buy_Count_30d", 0)
        return ("SUPPORTIVE", "YES (%d buys)" % buy_c)
    bs_ratio = insider.get("Insider_BS_Ratio_30d")
    if bs_ratio is not None and bs_ratio < 0.3:
        return ("CAUTIONARY", "bs_ratio %.2f" % bs_ratio)
    return ("NEUTRAL", "---")


def _signal_premarket(pmc: dict) -> tuple:
    """Component 8: Pre-Market Context."""
    status = pmc.get("PMC_Status")
    if status == "UNAVAILABLE" or status is None:
        return None
    gap_dir = pmc.get("PMC_Gap_Direction", "UNAVAILABLE")
    catalyst = pmc.get("PMC_Catalyst_Flag", False)
    gap_pct = pmc.get("PMC_Gap_Pct")

    if gap_dir == "UP" and catalyst:
        detail = "+%.1f%% gap up [CATALYST]" % (gap_pct or 0)
        return ("SUPPORTIVE", detail)
    if gap_dir == "DOWN" and gap_pct is not None and gap_pct <= -2.0:
        return ("CAUTIONARY", "%.1f%% gap down" % gap_pct)
    # Everything else
    detail = ""
    if gap_pct is not None:
        detail = "%+.1f%% (%s)" % (gap_pct, gap_dir)
    else:
        detail = gap_dir
    return ("NEUTRAL", detail)


# ---------------------------------------------------------------------------
# Scoring Algorithm (Spec Section 4)
# ---------------------------------------------------------------------------

_SIGNAL_SCORE = {"SUPPORTIVE": 1, "NEUTRAL": 0, "CAUTIONARY": -1}


def _compute_score(components: dict) -> tuple:
    """Returns (score, available_count, regime_label, status)."""
    available = {k: v for k, v in components.items() if v is not None}
    n = len(available)
    if n < MIN_COMPONENTS:
        return (None, n, "NEUTRAL", "UNAVAILABLE")

    total = sum(_SIGNAL_SCORE.get(sig, 0) for sig, _ in available.values())
    score = round(total / n, 2)

    if score > SCORE_THRESHOLD_SUPPORTIVE:
        regime = "SUPPORTIVE"
    elif score < SCORE_THRESHOLD_CAUTIONARY:
        regime = "CAUTIONARY"
    else:
        regime = "NEUTRAL"

    return (score, n, regime, "AVAILABLE")


# ---------------------------------------------------------------------------
# Key Levels (Spec Section 5)
# ---------------------------------------------------------------------------

def _derive_key_levels(modk: dict) -> dict:
    status = modk.get("Options_Status")
    if status != "AVAILABLE":
        return {
            "MSX_Support_Level": None,
            "MSX_Support_Source": None,
            "MSX_Resistance_Level": None,
            "MSX_Resistance_Source": None,
        }
    pw = modk.get("Options_Put_Wall")
    pw_oi = modk.get("Options_Put_Wall_OI")
    cw = modk.get("Options_Call_Wall")
    cw_oi = modk.get("Options_Call_Wall_OI")
    return {
        "MSX_Support_Level": pw,
        "MSX_Support_Source": "Put Wall $%s (OI: %s)" % (
            _fmt_price(pw), _fmt_int(pw_oi)) if pw is not None else None,
        "MSX_Resistance_Level": cw,
        "MSX_Resistance_Source": "Call Wall $%s (OI: %s)" % (
            _fmt_price(cw), _fmt_int(cw_oi)) if cw is not None else None,
    }


def _fmt_price(v):
    if v is None:
        return "---"
    return "%.2f" % v


def _fmt_int(v):
    if v is None:
        return "---"
    return "{:,}".format(int(v))


# ---------------------------------------------------------------------------
# Template Fallback Narrative (Spec Section 6.2)
# ---------------------------------------------------------------------------

_TEMPLATE_MAP = {
    "Put Wall Prox.": {
        "SUPPORTIVE": "Put wall reinforces structural floor.",
        "CAUTIONARY": "Price below put wall -- floor breached.",
        "NEUTRAL": "Put wall distance neutral.",
    },
    "Call Wall Prox.": {
        "CAUTIONARY": "Call wall exerting ceiling pressure.",
        "NEUTRAL": "Call wall distant -- no ceiling pressure.",
    },
    "PCR": {
        "SUPPORTIVE": "PCR extreme bearish (contrarian supportive).",
        "CAUTIONARY": "PCR bearish.",
        "NEUTRAL": "PCR neutral.",
    },
    "Dark Pool": {
        "SUPPORTIVE": "Dark pool net buying detected.",
        "CAUTIONARY": "Dark pool net selling detected.",
        "NEUTRAL": "Dark pool activity neutral.",
    },
    "Block Trades": {
        "SUPPORTIVE": "Block trades buy-dominant.",
        "CAUTIONARY": "Block trades sell-dominant.",
        "NEUTRAL": "Block trades mixed or unavailable.",
    },
    "Sweeps": {
        "SUPPORTIVE": "Bullish sweep cluster detected.",
        "CAUTIONARY": "Bearish sweep cluster detected.",
        "NEUTRAL": "Sweep activity balanced.",
    },
    "Insider Cluster": {
        "SUPPORTIVE": "Insider cluster buy active.",
        "CAUTIONARY": "Heavy insider selling detected.",
        "NEUTRAL": "Insider activity neutral.",
    },
    "Pre-Market": {
        "SUPPORTIVE": "Pre-market gap up with catalyst.",
        "CAUTIONARY": "Significant pre-market gap down.",
        "NEUTRAL": "Pre-market activity neutral.",
    },
}


def _build_template_narrative(components: dict, regime: str) -> str:
    """Concatenate per-component sentences for template fallback."""
    parts = []
    for name, val in components.items():
        if val is None:
            continue
        signal, _ = val
        templates = _TEMPLATE_MAP.get(name, {})
        sentence = templates.get(signal)
        if sentence:
            parts.append(sentence)
    if not parts:
        return "No microstructure signal. Rely on engine structural assessment alone."
    env_word = regime.lower()
    parts.append("Near-term microstructure is %s." % env_word)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Belt-and-Suspenders (Spec Section 6.2)
# ---------------------------------------------------------------------------

_CONTRADICTION_PATTERNS = {
    "SUPPORTIVE": ["cautionary", "adverse", "negative", "bearish"],
    "CAUTIONARY": ["supportive", "constructive", "favorable", "bullish"],
}


def _check_narrative_contradiction(regime: str, narrative: str) -> bool:
    """Returns True if narrative contradicts the regime label."""
    if not narrative or not regime:
        return False
    patterns = _CONTRADICTION_PATTERNS.get(regime, [])
    narrative_lower = narrative.lower()
    for pat in patterns:
        if pat in narrative_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Public Interface (Spec Section 9.2)
# ---------------------------------------------------------------------------

def synthesize_microstructure(
    modk_metrics: dict,
    flow_metrics: dict = None,
    insider_metrics: dict = None,
    pmc_metrics: dict = None,
    gex_metrics: dict = None,
    is_etf: bool = False,
) -> dict:
    """
    MSX-001 synthesis. Accepts partial data gracefully (Pass 1 will have
    flow/insider/pmc as empty dicts or None).
    Returns dict with all MSX_ prefixed fields.
    """
    modk = modk_metrics or {}
    flow = flow_metrics or {}
    insider = insider_metrics or {}
    pmc = pmc_metrics or {}

    # --- Component signal mapping ---
    components = {}
    components["Put Wall Prox."] = _signal_put_wall(modk)
    components["Call Wall Prox."] = _signal_call_wall(modk)
    components["PCR"] = _signal_pcr(modk)
    components["Dark Pool"] = _signal_dark_pool(flow)
    components["Block Trades"] = _signal_block_trades(flow)
    components["Sweeps"] = _signal_sweeps(flow)
    components["Insider Cluster"] = _signal_insider(insider, is_etf=is_etf)
    components["Pre-Market"] = _signal_premarket(pmc)
    # GEX-001: Gamma Regime component (activates when gex_metrics populated)
    gex = gex_metrics or {}
    if gex.get("GEX_Status") == "AVAILABLE":
        _gex_regime = gex.get("GEX_Gamma_Regime")
        if _gex_regime == "POSITIVE":
            components["Gamma Regime"] = ("SUPPORTIVE",
                                          "Positive gamma -- dealer hedging dampens moves")
        elif _gex_regime == "NEGATIVE":
            components["Gamma Regime"] = ("CAUTIONARY",
                                          "Negative gamma -- dealer hedging amplifies moves")
        else:
            components["Gamma Regime"] = None  # unknown regime, exclude from count
    else:
        components["Gamma Regime"] = None  # GEX unavailable, exclude from count

    # --- Scoring ---
    score, available, regime, status = _compute_score(components)

    # --- Key levels ---
    levels = _derive_key_levels(modk)

    # --- Component summary for dashboard ---
    summary = {}
    for name, val in components.items():
        if val is not None:
            sig, detail = val
            summary[name] = {"signal": sig, "detail": detail}
        else:
            # Determine if N/A or UNAVAILABLE
            if name == "Insider Cluster" and is_etf:
                summary[name] = {"signal": "N/A", "detail": "N/A (ETF)"}
            else:
                summary[name] = {"signal": "UNAVAILABLE", "detail": "---"}
    # Gamma Regime is now part of components dict — handled by loop above

    # --- Template fallback narrative (placeholder until Gemini) ---
    template_narrative = _build_template_narrative(components, regime)

    result = {
        "MSX_Regime": regime,
        "MSX_Score": score,
        **levels,
        "MSX_Conviction_Note": template_narrative,
        "MSX_Component_Summary": summary,
        "MSX_Components_Available": available,
        "MSX_Components_Total": COMPONENTS_TOTAL_GEX if components.get("Gamma Regime") is not None else COMPONENTS_TOTAL_BASE,
        "MSX_Status": status,
    }
    return result


def merge_narrative(msx_pass1: dict, gemini_narrative: str = None) -> dict:
    """
    Pass 2: Merge Gemini narrative into MSX payload.
    Apply belt-and-suspenders contradiction check.
    If gemini_narrative is None/empty, keep template fallback and set PARTIAL.
    """
    result = dict(msx_pass1)
    regime = result.get("MSX_Regime", "NEUTRAL")

    if not gemini_narrative or not gemini_narrative.strip():
        # Template fallback stays; mark PARTIAL if rule-based succeeded
        if result.get("MSX_Status") == "AVAILABLE":
            result["MSX_Status"] = "PARTIAL"
        # Conviction note already has template fallback
        return result

    narrative = gemini_narrative.strip()

    # Belt-and-suspenders: contradiction check
    contradiction = _check_narrative_contradiction(regime, narrative)
    if contradiction:
        narrative += "\n\nNote: narrative generated by Gemini; rule-based label is authoritative."

    result["MSX_Conviction_Note"] = narrative
    # Status stays AVAILABLE (Gemini succeeded)
    return result


# ---------------------------------------------------------------------------
# Dashboard Output Formatting (Spec Section 8)
# ---------------------------------------------------------------------------

def format_dashboard(msx: dict) -> str:
    """Format MSX payload as dashboard text block."""
    lines = []
    lines.append("   --- MICROSTRUCTURE SYNTHESIS ---")

    regime = msx.get("MSX_Regime", "NEUTRAL")
    status = msx.get("MSX_Status", "UNAVAILABLE")
    score = msx.get("MSX_Score")
    available = msx.get("MSX_Components_Available", 0)
    total = msx.get("MSX_Components_Total", COMPONENTS_TOTAL_BASE)

    # Regime line
    if status == "UNAVAILABLE" and score is None:
        lines.append("   Regime:       %s (insufficient data)" % regime)
    else:
        lines.append("   Regime:       %s" % regime)

    # Score line
    if score is not None:
        lines.append("   Score:        %+.2f (%d/%d components available)" % (score, available, total))
    else:
        lines.append("   Score:        --- ")
        lines.append("   Components available: %d / %d (minimum %d required)" % (available, total, MIN_COMPONENTS))

    # Support / Resistance
    sup = msx.get("MSX_Support_Level")
    sup_src = msx.get("MSX_Support_Source")
    res = msx.get("MSX_Resistance_Level")
    res_src = msx.get("MSX_Resistance_Source")

    if sup is not None:
        lines.append("   Support:      $%s (%s)" % (_fmt_price(sup), sup_src or ""))
    else:
        lines.append("   Support:      --- (MOD-K UNAVAILABLE)")

    if res is not None:
        lines.append("   Resistance:   $%s (%s)" % (_fmt_price(res), res_src or ""))
    else:
        lines.append("   Resistance:   --- (MOD-K UNAVAILABLE)")

    # Component table
    summary = msx.get("MSX_Component_Summary") or {}
    if summary:
        lines.append("")
        lines.append("   %-18s | %-18s | %s" % ("Component", "Signal", "Contribution"))
        _order = [
            "Put Wall Prox.", "Call Wall Prox.", "PCR",
            "Dark Pool", "Block Trades", "Sweeps",
            "Insider Cluster", "Pre-Market", "Gamma Regime",
        ]
        for name in _order:
            entry = summary.get(name)
            if entry:
                sig = entry.get("signal", "---")
                det = entry.get("detail", "---")
                lines.append("   %-18s | %-18s | %s" % (name, det, sig))

    # Conviction note
    note = msx.get("MSX_Conviction_Note", "")
    if note:
        lines.append("")
        lines.append("   CONVICTION NOTE:")
        for nline in note.split("\n"):
            lines.append("   %s" % nline)

    # Status tag
    if status == "PARTIAL":
        lines.append("   [Template fallback; Gemini narrative unavailable]")
    elif "rule-based label is authoritative" not in note:
        if status == "AVAILABLE":
            lines.append("   [Gemini narrative; rule-based label is authoritative]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Entry Point (Spec Section 9.3)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MSX-001: Microstructure Synthesis Layer"
    )
    parser.add_argument("--raw", action="store_true", default=False,
                        help="Output raw JSON (orchestrator-compatible)")
    parser.add_argument("--input", type=str, default=None,
                        help="Path to upstream JSON file (alternative to stdin)")

    args = parser.parse_args()

    # Read upstream data from file or stdin
    if args.input:
        with open(args.input, "r") as f:
            upstream = json.load(f)
    elif not sys.stdin.isatty():
        upstream = json.load(sys.stdin)
    else:
        upstream = {}

    # Split upstream into per-source dicts
    modk = {k: v for k, v in upstream.items() if k.startswith("Options_") or k.startswith("OPEX_")}
    flow = {k: v for k, v in upstream.items() if k.startswith("Flow_")}
    insider = {k: v for k, v in upstream.items() if k.startswith("Insider_")}
    pmc = {k: v for k, v in upstream.items() if k.startswith("PMC_")}
    is_etf = upstream.get("is_etf", False)

    result = synthesize_microstructure(modk, flow, insider, pmc, is_etf=is_etf)

    if args.raw:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_dashboard(result))
