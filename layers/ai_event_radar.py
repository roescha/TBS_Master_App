import json
from google import genai
from google.genai import types

client = genai.Client()

async def run_risk_radar(ticker: str) -> dict:
    """
    [MAX SPEED VERSION] Conducts the Forensic Risk Radar audit.
    """
    prompt = f"""
    You are the TBS Master Analyst running a Forensic Risk Radar audit on the financial asset {ticker.upper()}.
    
    [MANDATE: EFFICIENT SEARCH CAPABILITIES]
    You are authorized to use the Google Search tool to find the required information. Be efficient. Gather data for the following parameters:
    
    1. SECURITY & GEOPOLITICAL: Check recent news for cartels, blockades, or attacks involving the company.
    2. OPERATIONAL & ENVIRONMENTAL: Check for suspended operations, strikes, spills, or disasters.
    3. INTEGRITY & LEGAL: Check for DOJ/SEC investigations, fraud, lawsuits, or sudden executive resignations.
    4. FINANCIAL SHOCK: Check for sudden guidance cuts or defaults.
    5. BINARY EVENTS: Search for the exact upcoming Earnings Date and Ex-Dividend Date for {ticker.upper()}.
       - You MUST set "event_aware_triggered": true ONLY IF the Earnings date is within the next 10 days OR the Ex-Dividend date is within the next 24 hours. Otherwise, set it to false.
    6. SYMPATHY AUDIT: Identify the primary Sector ETF for {ticker.upper()}. Check recent financial news to assess if this ETF is currently in an uptrend or downtrend.
    
    [MANDATE: STRICT RELEVANCE & RECENCY]
    - RELEVANCE: You MUST verify the news explicitly involves {ticker.upper()}. Do not trigger a FAIL for acronym collisions or general macro news.
    - RECENCY: Only flag events that occurred within the last 90 days. 
    - If an event is old, unrelated, or no data is found, classify the status as "PASS" and output "Clear".
    
    SPECIAL MANDATE: If there are major, ongoing high-stakes legal battles, antitrust trials, or CEO testimonies currently in the news (e.g., Meta antitrust or youth mental health trials), you MUST flag them as a FAIL under the integrity_legal category.
    
    Respond STRICTLY with a JSON object matching this EXACT schema:
    {{
        "security_geo": {{"status": "PASS" | "FAIL", "details": "Brief explanation or 'Clear'"}},
        "operational_env": {{"status": "PASS" | "FAIL", "details": "Brief explanation or 'Clear'"}},
        "integrity_legal": {{"status": "PASS" | "FAIL", "details": "Brief explanation or 'Clear'"}},
        "financial_shock": {{"status": "PASS" | "FAIL", "details": "Brief explanation or 'Clear'"}},
        "binary_events": {{"status": "PASS" | "FAIL", "details": "Exact Dates and explanation or 'Clear'"}},
        "sympathy_audit": {{"status": "PASS" | "FAIL", "details": "Sector ETF ticker and general trend explanation."}},
        "integrity_shock_detected": bool,
        "event_aware_triggered": bool
    }}
    Do NOT wrap the response in markdown blocks (```json). Just return the raw JSON string.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
            )
        )
        raw_text = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(raw_text)

    except Exception as e:
        # [MANDATE: INSTANT FAIL-SECURE ON PAID TIER]
        clean_error = "API Connection Error. Operator must verify manually."
        return {
            "security_geo": {"status": "FAIL", "details": clean_error},
            "operational_env": {"status": "FAIL", "details": "Verify manually."},
            "integrity_legal": {"status": "FAIL", "details": "Verify manually."},
            "financial_shock": {"status": "FAIL", "details": "Verify manually."},
            "binary_events": {"status": "FAIL", "details": "Verify manually."},
            "sympathy_audit": {"status": "FAIL", "details": "Verify manually."},
            "integrity_shock_detected": True,
            "event_aware_triggered": True
        }