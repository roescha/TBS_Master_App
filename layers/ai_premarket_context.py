"""
ai_premarket_context.py -- PMC-001 Layer 1: Market Overnight Briefing
Sub-Phase 2C: Pre-session informational overlay. Zero engine impact.

Queries Gemini 2.5 Pro with Google Search grounding for:
  - Index futures direction (ES, NQ)
  - Asian session performance (Nikkei, Hang Seng, Shanghai)
  - European session status (STOXX 600, DAX)
  - Key commodities (WTI, Gold)
  - VIX futures level and direction
  - Major market-moving headlines

Public interface:
  get_overnight_briefing() -> dict

CLI:
  python ai_premarket_context.py
  python ai_premarket_context.py --raw
"""

import argparse
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client()

GEMINI_TIMEOUT = 30  # seconds, consistent with ai_institutional_context.py


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

def _build_overnight_prompt() -> str:
    """Construct date-anchored Gemini prompt per spec Section 3.2."""
    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are a financial market analyst. Today is {today}.

Summarise overnight market developments since the prior US market close that may affect today's US equity session.

Required search passes:
  Pass 1: "S&P 500 futures overnight {today}"
  Pass 2: "Nasdaq futures overnight {today}"
  Pass 3: "Asian markets close {today}" (Nikkei, Hang Seng, Shanghai)
  Pass 4: "European markets {today}" (STOXX 600, DAX, FTSE)
  Pass 5: "crude oil gold VIX overnight {today}"
  Pass 6: "market news headlines {today}"

Return ONLY a JSON object (no markdown, no preamble):
{{
  "index_futures": {{
    "es_direction": "<UP | DOWN | FLAT>",
    "es_change_pct": <float or null>,
    "nq_direction": "<UP | DOWN | FLAT>",
    "nq_change_pct": <float or null>,
    "notable": "<string or null>"
  }},
  "asian_session": {{
    "nikkei_change_pct": <float or null>,
    "hang_seng_change_pct": <float or null>,
    "shanghai_change_pct": <float or null>,
    "notable": "<string or null>"
  }},
  "european_session": {{
    "stoxx600_change_pct": <float or null>,
    "dax_change_pct": <float or null>,
    "notable": "<string or null>"
  }},
  "commodities": {{
    "oil_wti_change_pct": <float or null>,
    "gold_change_pct": <float or null>,
    "notable": "<string or null>"
  }},
  "vix_futures": {{
    "level": <float or null>,
    "direction": "<UP | DOWN | FLAT | UNAVAILABLE>",
    "change_pct": <float or null>
  }},
  "headlines": [
    "<headline 1>", "<headline 2>", ...
  ],
  "overnight_sentiment": "<RISK-ON | RISK-OFF | NEUTRAL | MIXED>"
}}

CRITICAL: Return ONLY the raw JSON object. No markdown, no preamble, no commentary."""

    return prompt


# ---------------------------------------------------------------------------
# Safe Type Helpers
# ---------------------------------------------------------------------------

# Unicode-to-ASCII replacement map (Gemini Search grounding returns these)
_UNICODE_MAP = {
    "\u2013": "--",   # en-dash
    "\u2014": "--",   # em-dash
    "\u2018": "'",    # left single quote
    "\u2019": "'",    # right single quote
    "\u201c": '"',    # left double quote
    "\u201d": '"',    # right double quote
    "\u2026": "...",  # ellipsis
    "\u00a0": " ",    # non-breaking space
    "\u00b7": "-",    # middle dot
    "\u2022": "-",    # bullet
}


def _sanitize_ascii(obj):
    """Recursively replace common Unicode chars with ASCII equivalents."""
    if isinstance(obj, str):
        for uc, repl in _UNICODE_MAP.items():
            obj = obj.replace(uc, repl)
        # Fallback: replace any remaining non-ASCII with '?'
        obj = obj.encode("ascii", "replace").decode("ascii")
        return obj
    elif isinstance(obj, dict):
        return {k: _sanitize_ascii(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_ascii(item) for item in obj]
    return obj

def _safe_float(val):
    """Safely convert to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_str(val, default="UNAVAILABLE"):
    """Safely convert to string with default."""
    if val is None or val == "":
        return default
    return str(val).strip()


# ---------------------------------------------------------------------------
# Sentiment Validation (Belt-and-Suspenders)
# ---------------------------------------------------------------------------

def _validate_sentiment(data: dict) -> dict:
    """Spec Section 3.4: Validate overnight_sentiment against component data."""
    futures = data.get("index_futures") or {}
    vix = data.get("vix_futures") or {}

    es_dir = _safe_str(futures.get("es_direction"), "UNAVAILABLE").upper()
    nq_dir = _safe_str(futures.get("nq_direction"), "UNAVAILABLE").upper()
    vix_dir = _safe_str(vix.get("direction"), "UNAVAILABLE").upper()
    vix_level = _safe_float(vix.get("level"))

    sentiment = _safe_str(data.get("overnight_sentiment"), "MIXED").upper()

    # If all index/futures fields are null/UNAVAILABLE, override to UNAVAILABLE
    es_pct = _safe_float(futures.get("es_change_pct"))
    nq_pct = _safe_float(futures.get("nq_change_pct"))
    all_unavail = (
        es_dir == "UNAVAILABLE"
        and nq_dir == "UNAVAILABLE"
        and es_pct is None
        and nq_pct is None
    )
    if all_unavail:
        data["overnight_sentiment"] = "UNAVAILABLE"
        return data

    # RISK-ON requires: ES and NQ both UP, and VIX direction not UP
    if sentiment == "RISK-ON":
        if not (es_dir == "UP" and nq_dir == "UP" and vix_dir != "UP"):
            data["overnight_sentiment"] = "MIXED"

    # RISK-OFF requires: ES and NQ both DOWN, or VIX direction UP with level >= 20
    if sentiment == "RISK-OFF":
        both_down = (es_dir == "DOWN" and nq_dir == "DOWN")
        vix_elevated = (vix_dir == "UP" and vix_level is not None and vix_level >= 20)
        if not (both_down or vix_elevated):
            data["overnight_sentiment"] = "MIXED"

    return data


# ---------------------------------------------------------------------------
# Field Mapping to Output Schema (Overnight_* prefixed fields)
# ---------------------------------------------------------------------------

def _map_to_output(data: dict, status: str = "AVAILABLE",
                   diagnostic: str = None) -> dict:
    """Map parsed JSON to flat dict with Overnight_* prefixed keys per spec Section 3.3."""
    futures = data.get("index_futures") or {}
    asian = data.get("asian_session") or {}
    europe = data.get("european_session") or {}
    commodities = data.get("commodities") or {}
    vix = data.get("vix_futures") or {}
    headlines_raw = data.get("headlines") or []

    # Ensure headlines is a list of strings, max 5
    if isinstance(headlines_raw, list):
        headlines = [str(h) for h in headlines_raw[:5] if h]
    else:
        headlines = []

    result = {
        "Overnight_ES_Direction": _safe_str(futures.get("es_direction"), "UNAVAILABLE").upper(),
        "Overnight_ES_Change_Pct": _safe_float(futures.get("es_change_pct")),
        "Overnight_NQ_Direction": _safe_str(futures.get("nq_direction"), "UNAVAILABLE").upper(),
        "Overnight_NQ_Change_Pct": _safe_float(futures.get("nq_change_pct")),
        "Overnight_Futures_Notable": futures.get("notable"),
        "Overnight_Nikkei_Pct": _safe_float(asian.get("nikkei_change_pct")),
        "Overnight_HangSeng_Pct": _safe_float(asian.get("hang_seng_change_pct")),
        "Overnight_Shanghai_Pct": _safe_float(asian.get("shanghai_change_pct")),
        "Overnight_Asian_Notable": asian.get("notable"),
        "Overnight_Stoxx600_Pct": _safe_float(europe.get("stoxx600_change_pct")),
        "Overnight_DAX_Pct": _safe_float(europe.get("dax_change_pct")),
        "Overnight_European_Notable": europe.get("notable"),
        "Overnight_Oil_WTI_Pct": _safe_float(commodities.get("oil_wti_change_pct")),
        "Overnight_Gold_Pct": _safe_float(commodities.get("gold_change_pct")),
        "Overnight_Commodities_Notable": commodities.get("notable"),
        "Overnight_VIX_Level": _safe_float(vix.get("level")),
        "Overnight_VIX_Direction": _safe_str(vix.get("direction"), "UNAVAILABLE").upper(),
        "Overnight_VIX_Change_Pct": _safe_float(vix.get("change_pct")),
        "Overnight_Headlines": headlines,
        "Overnight_Sentiment": _safe_str(data.get("overnight_sentiment"), "MIXED").upper(),
        "Overnight_Status": status,
        "Overnight_Diagnostic": diagnostic,
    }

    return result


# ---------------------------------------------------------------------------
# Main Public Interface
# ---------------------------------------------------------------------------

def get_overnight_briefing() -> dict:
    """
    Query Gemini Search grounding for market overnight context.
    Returns dict with all Overnight_* prefixed fields.
    Pipeline-safe: never raises.
    Returns UNAVAILABLE on any failure.
    """
    # Guard: API key
    if not os.environ.get("GEMINI_API_KEY"):
        return _map_to_output(
            {}, status="UNAVAILABLE",
            diagnostic="GEMINI_API_KEY not set."
        )

    try:
        prompt = _build_overnight_prompt()

        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
            )
        )

        raw_text = response.text.strip()
        # Strip markdown fences if Gemini wraps response
        if raw_text.startswith('```json'):
            raw_text = raw_text.replace('```json', '').replace('```', '').strip()
        elif raw_text.startswith('```'):
            raw_text = raw_text.replace('```', '').strip()

        data = json.loads(raw_text)

        # Scrub Unicode chars from Gemini response (Windows cp1252 safety)
        data = _sanitize_ascii(data)

        # Belt-and-suspenders sentiment validation
        data = _validate_sentiment(data)

        return _map_to_output(data, status="AVAILABLE", diagnostic=None)

    except json.JSONDecodeError as je:
        return _map_to_output(
            {}, status="UNAVAILABLE",
            diagnostic="JSON parse error: %s" % str(je)[:80]
        )
    except Exception as e:
        return _map_to_output(
            {}, status="UNAVAILABLE",
            diagnostic="Exception: %s" % str(e)[:80]
        )


# ---------------------------------------------------------------------------
# Dashboard Output Formatting (CLI)
# ---------------------------------------------------------------------------

def _print_dashboard(ctx: dict):
    """Print OVERNIGHT BRIEFING dashboard section per spec Section 3.5."""
    ov_status = ctx.get("Overnight_Status", "UNAVAILABLE")

    if ov_status == "UNAVAILABLE":
        diag = ctx.get("Overnight_Diagnostic") or "Gemini Search error"
        print("\n   ==================================================================")
        print("   OVERNIGHT BRIEFING: UNAVAILABLE (%s)" % diag)
        print("   ==================================================================")
        return

    print("\n   ==================================================================")
    print("   OVERNIGHT BRIEFING (Pre-Session Context)")
    print("   ==================================================================")

    # Futures line
    es_dir = ctx.get("Overnight_ES_Direction", "UNAVAILABLE")
    es_pct = ctx.get("Overnight_ES_Change_Pct")
    nq_dir = ctx.get("Overnight_NQ_Direction", "UNAVAILABLE")
    nq_pct = ctx.get("Overnight_NQ_Change_Pct")
    sentiment = ctx.get("Overnight_Sentiment", "MIXED")

    es_str = "%+.1f%%" % es_pct if es_pct is not None else es_dir
    nq_str = "%+.1f%%" % nq_pct if nq_pct is not None else nq_dir
    print("   Futures:      ES %s | NQ %s | Session bias: %s" % (es_str, nq_str, sentiment))

    # Asia line
    nk_pct = ctx.get("Overnight_Nikkei_Pct")
    hs_pct = ctx.get("Overnight_HangSeng_Pct")
    sh_pct = ctx.get("Overnight_Shanghai_Pct")
    nk_str = "%+.1f%%" % nk_pct if nk_pct is not None else "N/A"
    hs_str = "%+.1f%%" % hs_pct if hs_pct is not None else "N/A"
    sh_str = "%+.1f%%" % sh_pct if sh_pct is not None else "N/A"
    print("   Asia:         Nikkei %s | Hang Seng %s | Shanghai %s" % (nk_str, hs_str, sh_str))

    # Europe line
    stoxx_pct = ctx.get("Overnight_Stoxx600_Pct")
    dax_pct = ctx.get("Overnight_DAX_Pct")
    stoxx_str = "%+.1f%%" % stoxx_pct if stoxx_pct is not None else "N/A"
    dax_str = "%+.1f%%" % dax_pct if dax_pct is not None else "N/A"
    print("   Europe:       STOXX 600 %s | DAX %s" % (stoxx_str, dax_str))

    # Commodities line
    oil_pct = ctx.get("Overnight_Oil_WTI_Pct")
    gold_pct = ctx.get("Overnight_Gold_Pct")
    oil_str = "%+.1f%%" % oil_pct if oil_pct is not None else "N/A"
    gold_str = "%+.1f%%" % gold_pct if gold_pct is not None else "N/A"
    print("   Commodities:  WTI %s | Gold %s" % (oil_str, gold_str))

    # VIX line
    vix_level = ctx.get("Overnight_VIX_Level")
    vix_dir = ctx.get("Overnight_VIX_Direction", "UNAVAILABLE")
    vix_chg = ctx.get("Overnight_VIX_Change_Pct")
    if vix_level is not None:
        vix_str = "%.1f" % vix_level
        if vix_chg is not None:
            vix_str += " (%s %+.1f%%)" % (vix_dir, vix_chg)
        else:
            vix_str += " (%s)" % vix_dir
    else:
        vix_str = "UNAVAILABLE"
    print("   VIX Futures:  %s" % vix_str)

    # Headlines
    headlines = ctx.get("Overnight_Headlines") or []
    if headlines:
        print("   Headlines:    %s" % headlines[0])
        for hl in headlines[1:]:
            print("                 %s" % hl)
    else:
        print("   Headlines:    None reported")

    print("   SOURCE:       Gemini Search (financial news, futures data)")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PMC-001 Layer 1: Market Overnight Briefing (Pre-Session Overlay)"
    )
    parser.add_argument("--raw", action="store_true", default=False,
                        help="Output raw JSON (orchestrator-compatible)")

    args = parser.parse_args()

    ctx = get_overnight_briefing()

    if args.raw:
        print(json.dumps(ctx, indent=2, default=str))
    else:
        print("\n   PMC-001 Layer 1 | OVERNIGHT BRIEFING")
        _print_dashboard(ctx)
