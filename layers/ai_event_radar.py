import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client()

async def run_risk_radar(ticker: str, company_name: str = "") -> dict:
    """
    [MAX SPEED VERSION] Conducts the Forensic Risk Radar audit.
    [RADAR-010] Financial Shock category now enforces a 4-pass multi-query search
    mandate and injects explicit high-signal hint terms to improve Gemini search
    grounding discovery for profitability/impairment/executive-statement events
    that do not rank for standard guidance-revision query terms.
    [RADAR-003] Earnings Buffer now includes a post-earnings lookback in addition
    to the existing 10-day forward window:
      - Target ticker: 1-day post-earnings lookback
      - Super 7 members: 2-day post-earnings lookback
    When a post-earnings trigger fires, earnings_event_triggered is set true and
    event_aware_tag is set to "RECENT" (or "FORWARD+RECENT" if both windows fire).
    A 0.5x sizing reduction note is injected into earnings_buffer_event.post_earnings_sizing_note.
    Belt-and-suspenders enforcement is applied in Python after LLM parse.
    """
    # [O-34] Disambiguate ticker from country/entity collisions using IBKR longName
    _company_label = f"{company_name} (ticker: {ticker.upper()})" if company_name else f"ticker {ticker.upper()}"

    today = datetime.now().strftime("%B %d, %Y")  # e.g. "March 03, 2026"
    today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # [RADAR-003] Post-earnings lookback boundaries (used in both prompt and belt-and-suspenders)
    _post_earnings_lookback_ticker = 3   # calendar days back for target ticker
    # NOTE [RADAR-003 FIX]: Extended from 1 → 3 days. A 1-day window missed post-close
    # reporters when checked 2 days later (e.g. CRDO reported March 2 post-close; delta=-2
    # on March 4 fell outside the 1-day window). 3 days also survives the Friday-after-close
    # edge case where the first trading bar reaction doesn't occur until Monday.
    _post_earnings_lookback_super7 = 3   # calendar days back for Super 7 members (aligned)
    _post_ticker_cutoff = (today_dt - timedelta(days=_post_earnings_lookback_ticker)).strftime("%B %d, %Y")
    _post_super7_cutoff = (today_dt - timedelta(days=_post_earnings_lookback_super7)).strftime("%B %d, %Y")

    prompt = f"""
You are the TBS Master Analyst running a Forensic Risk Radar audit on the publicly traded stock {_company_label}.

TODAY'S DATE: {today}

CRITICAL: "{ticker.upper()}" is a STOCK TICKER SYMBOL. All searches must be about the publicly traded company {_company_label}, NOT any country, government, political figure, or other entity that may share similar letters. Always include the company name in your search queries.

[MANDATE: EFFICIENT SEARCH CAPABILITIES]
You are authorized to use the Google Search tool. Gather data strictly for the following parameters:

[TIME WINDOW MANDATE]
Only flag events whose MOST RECENT MATERIAL DEVELOPMENT falls within the specified lookback window.
"Material development" means a new filing, new ruling, new disclosure, new incident, or new price-moving announcement -- NOT the mere continued existence of an unresolved matter.
A case that is technically still open but whose last substantive development (filing, ruling, hearing, disclosure) occurred BEFORE the lookback window = PASS.
Events that have been fully resolved, settled, dismissed, or whose last material development occurred entirely before the lookback window are PASS, not FAIL.
If a lawsuit was settled or an executive departure was followed by a named successor before the window, mark PASS.

[STRICT PROHIBITION -- NO PRICE-ABSORPTION JUDGMENT]
Do NOT assess whether an event has been "priced in", absorbed, or reflected in subsequent price action. That analysis belongs to the Technical Engine and Operator, NOT the Radar. Your sole task is to determine whether a qualifying event occurred within the lookback window. If it did, the status is FAIL -- regardless of how the stock has traded since. Do not reference analyst target revisions, post-event trading stabilization, or market reaction when determining PASS/FAIL.

1. SECURITY & GEOPOLITICAL (30-day lookback from {today}):
   Check news from the last 30 days for {_company_label} related to cartels, blockades, supply chain shocks, or attacks. Only flag if the event is ACTIVE or DEVELOPING within this window. Resolved events = PASS.

2. OPERATIONAL & ENVIRONMENTAL (30-day lookback from {today}):
   Check the last 30 days for suspended operations, strikes, spills, or disasters at {_company_label}. Only flag if the disruption is ONGOING or has NOT been remediated. Resolved events = PASS.
   MATERIALITY THRESHOLD -- Only FAIL for disruptions that are MATERIAL to the company's core operations or revenue:
   (a) FAIL examples: plant/facility shutdowns, worker strikes, environmental spills or disasters, prolonged outages (>48 hrs) affecting core revenue-generating products or services.
   (b) PASS examples (note in details if relevant): brief SaaS component degradations, scheduled maintenance windows, isolated sub-service warnings, StatusPage/StatusGator advisories on non-core ancillary services, outages under 48 hours with no confirmed revenue or customer impact.
   When in doubt, apply this test: would a reasonable analyst consider this event capable of materially impacting quarterly revenue or operations? If no, mark PASS with a brief note.

3. INTEGRITY & LEGAL (30-day lookback from {today}):
   Check the last 30 days for ACTIVE DOJ/SEC investigations, PENDING lawsuits with material financial exposure, fraud allegations, or sudden executive resignations at {_company_label}. Settled cases, dismissed suits, and resignations with named successors before this window = PASS.
   RECENCY TEST: The 30-day window applies to the date of the MOST RECENT SUBSTANTIVE DOCKET EVENT (new filing, ruling, subpoena, indictment, appeal filing, settlement announcement) -- NOT the mere continued existence of open litigation. If a lawsuit or investigation exists but its last material legal development occurred BEFORE the 30-day window, mark PASS even if the matter is technically still pending. Only FAIL if a new material legal development occurred within the last 30 days from {today}.

4. FINANCIAL SHOCK (14-day lookback from {today}):
   Check the last 14 days for any of the following at {_company_label}:
   (a) Formal downward guidance revisions, negative pre-announcements, or defaults.
   (b) Material segment or business-unit profitability disclosures indicating fundamental deterioration (e.g., a segment reporting collapse in margins, sustained operating losses, or disclosure that a major business line is no longer economically viable).
   (c) Asset impairment warnings or write-down signals (e.g., goodwill impairment charges, significant asset revaluations, mine/plant/portfolio write-downs).
   (d) Executive statements explicitly characterizing operations, assets, or business units as uneconomic, unsustainable, or uninvestable (e.g., a senior officer publicly stating that a major operation generates zero or negative returns on invested capital).

   [RADAR-010 -- MULTI-PASS SEARCH MANDATE]
   For this category ONLY, you MUST execute a minimum of FOUR separate Google Search queries using DIFFERENT keyword angles before concluding PASS. A single search is insufficient. Required search passes:
     Pass 1 -- Guidance & defaults: "{company_name} guidance revision OR downgrade OR pre-announcement OR default {today[:4]}"
     Pass 2 -- Impairment & write-downs: "{company_name} impairment OR write-down OR write-off OR asset revaluation OR goodwill charge {today[:4]}"
     Pass 3 -- Profitability deterioration: "{company_name} profitability OR margins OR operating loss OR uninvestable OR uneconomic OR unsustainable OR zero return {today[:4]}"
     Pass 4 -- Cost & commodity pressure: "{company_name} cost pressure OR royalties OR commodity prices OR segment loss OR business unit loss OR economically viable {today[:4]}"
   You MAY run additional passes if any of the above return ambiguous or sparse results.
   Only mark PASS after ALL four passes have returned no qualifying event within the 14-day window.

   [RADAR-010 -- SEARCH HINT TERMS]
   When constructing internal search queries for this category, prioritise the following high-signal terms which are likely to surface qualifying events that standard financial-news queries miss:
   profitability, impairment, write-down, write-off, uneconomic, unsustainable, uninvestable, zero return, negative return on invested capital, cost pressure, royalties, margin collapse, operating losses, economically unviable, business line deterioration, segment loss, mine closure, plant closure, facility write-down.

   RULE: If ANY qualifying financial shock from categories (a)-(d) occurred within the 14-day lookback window, status is FAIL. Do NOT evaluate whether the shock has been "priced in" or absorbed by subsequent trading. Price-impact assessment is the Technical Engine and Operator domain, not yours. The only question is: did a qualifying event occur within the window? If yes = FAIL. Prior-quarter revisions or disclosures whose MOST RECENT material development falls BEFORE the 14-day window = PASS.

5. EARNINGS BUFFER -- FORWARD + POST-EARNINGS WINDOWS (from {today}):
   Search for the exact most-recent AND upcoming Earnings Dates for {_company_label} AND the Super 7 (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA).

   [FORWARD WINDOW -- unchanged]
   - A FORWARD trigger fires if {ticker.upper()} OR any Super 7 member has earnings scheduled within the NEXT 10 calendar days from {today} (i.e., earnings date is between {today} and 10 days ahead).

   [POST-EARNINGS LOOKBACK -- RADAR-003]
   - A RECENT trigger fires if {ticker.upper()} had its earnings release within the past {_post_earnings_lookback_ticker} calendar day(s) from {today} (i.e., earnings date falls on or after {_post_ticker_cutoff}).
   - A RECENT trigger also fires if ANY Super 7 member had its earnings release within the past {_post_earnings_lookback_super7} calendar days from {today} (i.e., earnings date falls on or after {_post_super7_cutoff}).
   - Rationale: The immediate post-earnings window carries elevated risk from analyst revisions, institutional repositioning, and post-earnings announcement drift (PEAD). Technical gates require 2-3 bars to detect damage; the Radar must flag this window proactively.

   [TRIGGER RULES]
   - Set "earnings_event_triggered": true if ANY forward OR post-earnings trigger fires.
   - Set "event_aware_tag" in the "earnings_buffer_event" object to one of:
       "FORWARD"        -- only a forward trigger fired (upcoming earnings within 10 days)
       "RECENT"         -- only a post-earnings trigger fired (earnings just reported)
       "FORWARD+RECENT" -- both a forward AND a post-earnings trigger fired simultaneously
       null             -- no trigger fired
   - When "earnings_event_triggered" is true:
       (a) The "earnings_buffer_event" "details" field MUST list every triggering company, its earnings date, and whether it is a FORWARD or RECENT trigger.
       (b) The "earnings_buffer_event" "post_earnings_sizing_note" field MUST be set to:
           "0.5x SIZING ACTIVE -- immediate post-earnings window. Maintain until post-earnings lookback window expires." when tag is "RECENT" or "FORWARD+RECENT".
           "N/A" when tag is "FORWARD" only.
   - When "earnings_event_triggered" is false, set "event_aware_tag" to null and "post_earnings_sizing_note" to "N/A".

Respond STRICTLY with a raw JSON object containing these keys:
"security_geo_event", "operational_env_event", "integrity_legal_event", "financial_shock_event", "earnings_buffer_event", "threat_event_detected" (bool), "earnings_event_triggered" (bool).
CRITICAL BOOLEAN RULE: "threat_event_detected" is the MASTER threat boolean. Set "threat_event_detected" to true if ANY of the four threat categories (security_geo_event, operational_env_event, integrity_legal_event, financial_shock_event) returns status "FAIL". It is NOT limited to the Integrity & Legal category alone. All four categories feed into this single boolean.
For each of the four threat category fields, use keys:
  "status" ("PASS" or "FAIL"),
  "details" (explanation; if PASS state "No active threats within [N]-day window"),
  "event_date" (ISO date string of the flagged event, or "N/A" if PASS).
For the "earnings_buffer_event" field, use keys:
  "status" ("PASS" or "FAIL"),
  "details" (list of triggering companies with dates and FORWARD/RECENT tags, or "No earnings within forward or post-earnings windows"),
  "event_aware_tag" ("FORWARD", "RECENT", "FORWARD+RECENT", or null),
  "post_earnings_sizing_note" (sizing instruction string per the rules above, or "N/A").
DO NOT wrap the response in markdown.
"""

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                # response_mime_type REMOVED to prevent Search Grounding conflict
            )
        )

        raw_text = response.text.strip()
        if raw_text.startswith('```json'):
            raw_text = raw_text.replace('```json', '').replace('```', '').strip()
        elif raw_text.startswith('```'):
            raw_text = raw_text.replace('```', '').strip()

        result = json.loads(raw_text)

        # [RADAR-004] Belt-and-suspenders: enforce master boolean regardless of LLM output
        _threat_categories = ("security_geo_event", "operational_env_event", "integrity_legal_event", "financial_shock_event")
        if any(result.get(cat, {}).get("status") == "FAIL" for cat in _threat_categories):
            result["threat_event_detected"] = True

        # [RADAR-003] Belt-and-suspenders: post-earnings lookback enforcement.
        # Re-derive FORWARD / RECENT tags from any ISO dates the LLM embedded in
        # earnings_buffer_event.details, then reconcile earnings_event_triggered and event_aware_tag.
        _be = result.get("earnings_buffer_event", {})
        _details_text = str(_be.get("details", ""))
        _forward_fired = False
        _recent_fired  = False

        # Attempt to parse any ISO-8601 dates (YYYY-MM-DD) mentioned by the LLM in the
        # details field and classify them relative to today_dt.
        import re as _re
        _iso_dates_found = _re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', _details_text)
        for _ds in _iso_dates_found:
            try:
                _ed = datetime.strptime(_ds, "%Y-%m-%d")
                _delta = (_ed - today_dt).days  # negative = in the past
                # Determine whether this date was for the target ticker or Super 7.
                # We check proximity: if the date context contains the ticker symbol
                # we apply the tighter 1-day window, otherwise the 2-day Super 7 window.
                _ticker_upper = ticker.upper()
                # Look for the ticker symbol within ~80 chars surrounding the date in details
                _ctx_start = max(0, _details_text.find(_ds) - 80)
                _ctx_end   = min(len(_details_text), _details_text.find(_ds) + 80)
                _ctx       = _details_text[_ctx_start:_ctx_end].upper()
                _lookback  = _post_earnings_lookback_ticker if _ticker_upper in _ctx else _post_earnings_lookback_super7
                if -_lookback <= _delta < 0:          # past: within lookback window
                    _recent_fired = True
                elif 0 <= _delta <= 10:               # future: within 10-day forward window
                    _forward_fired = True
            except ValueError:
                pass

        # Reconcile: if Python detected triggers the LLM missed, override.
        if _forward_fired or _recent_fired:
            result["earnings_event_triggered"] = True

        # Derive canonical tag
        if _forward_fired and _recent_fired:
            _canonical_tag = "FORWARD+RECENT"
        elif _recent_fired:
            _canonical_tag = "RECENT"
        elif _forward_fired:
            _canonical_tag = "FORWARD"
        else:
            # Fall back to whatever the LLM returned (it may have used non-ISO date formats
            # that the regex above couldn't parse -- trust its earnings_event_triggered flag).
            _canonical_tag = _be.get("event_aware_tag", None)
            if result.get("earnings_event_triggered") and _canonical_tag is None:
                # LLM says triggered but gave no tag -- default to FORWARD (conservative)
                _canonical_tag = "FORWARD"

        result.setdefault("earnings_buffer_event", {})["event_aware_tag"] = _canonical_tag

        # Enforce sizing note consistency
        _sizing_note = _be.get("post_earnings_sizing_note", "N/A")
        if _canonical_tag in ("RECENT", "FORWARD+RECENT") and _sizing_note == "N/A":
            result["earnings_buffer_event"]["post_earnings_sizing_note"] = (
                "0.5x SIZING ACTIVE -- immediate post-earnings window. "
                "Maintain until post-earnings lookback window expires."
            )
        elif _canonical_tag == "FORWARD" and not _sizing_note.startswith("0.5x"):
            result["earnings_buffer_event"]["post_earnings_sizing_note"] = "N/A"

        return result

    except Exception as e:
        print(f"\n   [RADAR DIAGNOSTIC] Under-the-hood failure: {str(e)}\n")
        return {
            "security_geo_event": {"status": "FAIL", "details": f"API Error: {str(e)[:40]}"},
            "operational_env_event": {"status": "FAIL", "details": "Verify manually."},
            "integrity_legal_event": {"status": "FAIL", "details": "Verify manually."},
            "financial_shock_event": {"status": "FAIL", "details": "Verify manually."},
            "earnings_buffer_event": {
                "status": "FAIL",
                "details": "Verify manually.",
                "event_aware_tag": "FORWARD",
                "post_earnings_sizing_note": "0.5x SIZING ACTIVE -- API error fallback, verify manually."
            },
            "threat_event_detected": True,
            "earnings_event_triggered": True
        }
