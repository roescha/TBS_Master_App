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
    You are authorized to use the Google Search tool. Gather data strictly for the following parameters:
    
    1. SECURITY & GEOPOLITICAL: Check recent news for cartels, blockades, supply chain shocks, or attacks.
    2. OPERATIONAL & ENVIRONMENTAL: Check for suspended operations, strikes, spills, or disasters.
    3. INTEGRITY & LEGAL: Check for DOJ/SEC investigations, fraud, lawsuits, or sudden executive resignations.
    4. FINANCIAL SHOCK: Check for sudden downward guidance revisions or defaults.
    5. EARNINGS BUFFER: Search for the exact upcoming Earnings Date.
       - You MUST set "event_aware_triggered": true ONLY IF the Earnings date is within the next 10 days.
    
    NOTE: Sympathy Audits and Dividend Lockouts are handled deterministically by Layer 1.5. Do not include them.
    
    Respond STRICTLY in JSON format with a brief status/details for each category.
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