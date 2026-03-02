import json
import os
from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client()

async def run_vision_audit(ticker: str, profile: str, engine_metrics: dict) -> dict:
    """
    [v8.4 FINAL AUTHORITATIVE] Executes the Triple-Image Visual Audit.
    Spatial extension verification removed to prevent Vision Model hallucination.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    primary_path = os.path.join(project_root, "charts", f"{ticker.upper()}_primary.png")
    context_path = os.path.join(project_root, "charts", f"{ticker.upper()}_context.png")
    focus_path = os.path.join(project_root, "charts", f"{ticker.upper()}_focus.png")

    if not os.path.exists(primary_path) or not os.path.exists(context_path):
        return {
            "verdict": "HALT",
            "reasoning": "AUTO-REJECT: Missing Mandatory Primary or Context charts."
        }

    engine_state = engine_metrics.get("Engine_State", "UNKNOWN")

    prompt = f"""
    You are the TBS Master Analyst. Execute the v8.4 AI-Assisted Visual Audit for {ticker.upper()} (Profile {profile}).
    
    [PURITY ENGINE TELEMETRY]
    Engine State: {engine_state}
    
    [VIEW 1: PRIMARY EXECUTION]
    1. Zero-Markup Rule: Are there manual lines drawn on the chart? If YES, HALT.
    2. Legend Integrity: Are the numerical values in the top-left legend masked (e.g., ***) or illegible? If YES, HALT.
    3. ADX Verification: If the Engine State contains "TRENDING", look at the ADX sub-panel. Did the purple ADX line reach > 25 at any point prior to the current bar? If NO, HALT.
    
    [VIEW 2: CONTEXT VERIFICATION]
    4. Structural Alignment: Does the higher-timeframe trend support the primary execution?
    
    Respond STRICTLY in JSON format:
    {{
        "verdict": "PASS" | "HALT",
        "reasoning": "Concise summary of cross-validation findings."
    }}
    """

    try:
        img_primary = Image.open(primary_path)
        img_context = Image.open(context_path)

        vision_payload = [prompt, img_primary, img_context]
        if os.path.exists(focus_path):
            vision_payload.append(Image.open(focus_path))

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=vision_payload,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )

        raw_text = response.text.strip()
        if raw_text.startswith('```json'):
            raw_text = raw_text.replace('```json', '').replace('```', '').strip()

        return json.loads(raw_text)

    except Exception as e:
        return {
            "verdict": "HALT",
            "reasoning": f"AI Vision Failure: {str(e)}. Operator must verify manually."
        }