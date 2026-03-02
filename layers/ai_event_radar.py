import json
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client()

async def run_risk_radar(ticker: str) -> dict:
    """
    [MAX SPEED VERSION] Conducts the Forensic Risk Radar audit.
    """
    prompt = f"""
    You are the TBS Master Analyst running a Forensic Risk Radar audit on {ticker.upper()}.
    
    [MANDATE: EFFICIENT SEARCH CAPABILITIES]
    You are authorized to use the Google Search tool. Gather data strictly for the following parameters:
    
    1. SECURITY & GEOPOLITICAL: Check recent news for cartels, blockades, supply chain shocks, or attacks.
    2. OPERATIONAL & ENVIRONMENTAL: Check for suspended operations, strikes, spills, or disasters.
    3. INTEGRITY & LEGAL: Check for DOJ/SEC investigations, fraud, lawsuits, or sudden executive resignations.
    4. FINANCIAL SHOCK: Check for sudden downward guidance revisions or defaults.
    5. EARNINGS BUFFER: Search for the exact upcoming Earnings Date for {ticker.upper()} AND the Super 7 (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA).
       - You MUST set "event_aware_triggered": true ONLY IF {ticker.upper()} OR the Super 7 have earnings within the next 10 days.
    
    Respond STRICTLY with a raw JSON object containing these keys: 
    "security_geo", "operational_env", "integrity_legal", "financial_shock", "binary_events", "integrity_shock_detected" (bool), "event_aware_triggered" (bool).
    For the text fields, use keys "status" ("PASS" or "FAIL") and "details".
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

        return json.loads(raw_text)

    except Exception as e:
        print(f"\n   [RADAR DIAGNOSTIC] Under-the-hood failure: {str(e)}\n")
        return {
            "security_geo": {"status": "FAIL", "details": f"API Error: {str(e)[:40]}"},
            "operational_env": {"status": "FAIL", "details": "Verify manually."},
            "integrity_legal": {"status": "FAIL", "details": "Verify manually."},
            "financial_shock": {"status": "FAIL", "details": "Verify manually."},
            "binary_events": {"status": "FAIL", "details": "Verify manually."},
            "sympathy_audit": {"status": "FAIL", "details": "Verify manually."},
            "integrity_shock_detected": True,
            "event_aware_triggered": True
        }