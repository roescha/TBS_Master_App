import asyncio
import json
import os
import re

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

        # Safely strip markdown code blocks (handles ```json, ```, and variants)
        raw_text = response.text.strip()
        if raw_text.startswith('```'):
            # Remove opening ``` line (with or without language tag) and closing ```
            lines = raw_text.split('\n')
            # Drop first line (```json or ```) and last line if it's ```)
            if len(lines) >= 2:
                if lines[-1].strip() == '```':
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                raw_text = '\n'.join(lines).strip()

        # Attempt 1: Standard JSON parse
        try:
            data = json.loads(raw_text)
            return data
        except (json.JSONDecodeError, ValueError):
            pass

        # Attempt 2: Extract JSON object from mixed text (Gemini sometimes wraps JSON in prose)
        json_match = re.search(r'\{[^{}]*\}', raw_text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data
            except (json.JSONDecodeError, ValueError):
                pass

        # Attempt 3: Fallback text extraction for known metric types
        # [FHB-001-BUG-6] Gemini systematically returns non-JSON for Moat Rating queries.
        # Extract value from natural language response rather than losing the metric.
        upper_text = raw_text.upper()

        if metric_name == "Moat Rating":
            # Priority order: most specific match first
            for moat_val in ("WIDE", "NARROW", "NONE", "NO MOAT"):
                if moat_val in upper_text:
                    resolved = "NONE" if moat_val == "NO MOAT" else moat_val
                    return {"value": resolved, "source": "Gemini (text extraction)"}
            # Morningstar descriptor mapping (same as prompt instructions)
            for desc, mapped in [("GREAT", "WIDE"), ("SUSTAINABLE", "WIDE"),
                                 ("HIGH BARRIER", "WIDE"), ("MODERATE", "NARROW"),
                                 ("AVERAGE", "NARROW"), ("LOW", "NONE")]:
                if desc in upper_text:
                    return {"value": mapped, "source": "Gemini (text extraction)"}
            return None

        # For numeric metrics (ROIC, WACC, Revenue Growth, EPS Growth, D/E, FCF Yield):
        # Try to extract a float from the response text
        num_match = re.search(r'-?\d+\.?\d*', raw_text)
        if num_match:
            try:
                val = float(num_match.group())
                return {"value": val, "source": "Gemini (text extraction)"}
            except ValueError:
                pass

        # All extraction attempts failed
        return None
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