import asyncio
import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from the .env file
load_dotenv()
# Ensure you have your GEMINI_API_KEY set in your environment
client = genai.Client()

async def fetch_metric_from_network(ticker: str, metric_name: str) -> dict:
    """
    Dynamically searches the network for the requested fundamental metric.
    Authorized Sources: Morningstar, SEC filings, Macrotrends, GuruFocus.
    """
    prompt = f"""
    You are the TBS Master Analyst. You are executing the 'Override and Retrieve Data' clause [Doc 6 Sec 3.5].
    Your objective is to find the current {metric_name} for the ticker {ticker.upper()}.
    
    SPECIAL INSTRUCTION FOR MOAT RATING:
    If {metric_name} is 'Moat Rating', you MUST return one of these three strings: "WIDE", "NARROW", or "NONE".
    If the source describes it as 'Great', 'Sustainable', or 'High Barrier', map it to "WIDE".
    If the source describes it as 'Moderate' or 'Average', map it to "NARROW".
    If the source says 'No Moat' or 'Low', map it to "NONE".
    
    Respond STRICTLY with a raw JSON object:
    - "value": The numerical float (for ROIC/WACC/Yield) OR "WIDE"/"NARROW"/"NONE" (for Moat).
    - "source": The URL or source name.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}], # Network Search Enabled
            )
        )

        # Guard: Gemini returns None or empty string when no data is found (e.g. pre-revenue, small-cap)
        if response.text is None or not response.text.strip():
            return None

        # Safely strip markdown if the model accidentally includes it
        raw_text = response.text.strip()
        if raw_text.startswith('```json'):
            raw_text = raw_text.replace('```json', '').replace('```', '').strip()

        data = json.loads(raw_text)
        return data
    except Exception as e:
        raise Exception(f"AI Retrieval Failed for {metric_name}: {str(e)}")

# [UPDATED] Added 'timeout' parameter to the function signature
async def run_retriever_with_timeout(ticker: str, metric_name: str, timeout: float = 120.0) -> dict:
    """
    Enforces the deterministic timeout guard [Doc 6 Sec 3.5].
    Default is 120s, but can be overridden by the Orchestrator/API.
    """
    try:
        # Use the passed-in timeout value here
        result = await asyncio.wait_for(fetch_metric_from_network(ticker, metric_name), timeout=timeout)
        return {"metric": metric_name, "data": result}
    except asyncio.TimeoutError:
        return {
            "metric": metric_name,
            "data": {"value": None, "source": "TIMEOUT", "error": f"{timeout}-second retrieval timeout exceeded."}
        }
    except Exception as e:
        return {
            "metric": metric_name,
            "data": {"value": None, "source": "ERROR", "error": str(e)}
        }