import asyncio
import json
import os
from google import genai
from google.genai import types

# Ensure you have your GEMINI_API_KEY set in your environment
client = genai.Client()

async def fetch_wacc_from_network(ticker: str) -> dict:
    prompt = f"""
    You are the TBS Master Analyst. You are executing the 'Override and Retrieve Data' clause.
    Your objective is to find the current Weighted Average Cost of Capital (WACC) for the ticker {ticker.upper()}.
    Search trusted financial networks (e.g., Morningstar, Finbox, GuruFocus, or SEC filings).
    
    CRITICAL MANDATE: You are strictly forbidden from guessing or calculating this value yourself. If you cannot find a explicitly published WACC from a reputable source, you MUST return null for the wacc field.
    
    Respond STRICTLY with a raw JSON object containing:
    - "wacc": The numerical float value of the WACC (e.g., 9.5), or null if verifiable data is not found.
    - "source": The primary source/URL where you found this estimate, or "NOT FOUND".
    Do NOT wrap the response in markdown blocks (```json). Just return the raw JSON string.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}], # Network Search Enabled
                # NOTE: response_mime_type REMOVED due to Tool conflict
            )
        )

        # Safely strip markdown if the model accidentally includes it
        raw_text = response.text.strip().replace('```json', '').replace('```', '')
        data = json.loads(raw_text)
        return data
    except Exception as e:
        raise Exception(f"AI Retrieval Failed: {str(e)}")

async def run_wacc_estimator_with_timeout(ticker: str) -> dict:
    """
    Enforces the deterministic 60-second timeout guard.
    """
    try:
        # [MANDATE: DOC 6 SEC 3.5] 60-second timeout enforcement
        result = await asyncio.wait_for(fetch_wacc_from_network(ticker), timeout=60.0)
        return result
    except asyncio.TimeoutError:
        # [MANDATE: DOC 6 SEC 3.5] Return HALT if timeout exceeded
        return {"wacc": None, "source": "TIMEOUT", "error": "HALT (Missing Data): 60-second Network Search timeout exceeded. Operator must use --override."}
    except Exception as e:
        return {"wacc": None, "source": "ERROR", "error": str(e)}