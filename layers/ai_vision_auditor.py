import json
import os
from PIL import Image
from google import genai
from google.genai import types

client = genai.Client()

async def run_vision_audit(ticker: str, profile: str) -> dict:
    """
    [v8.3 FINAL AUTHORITATIVE] Executes the Triple-Image Visual Audit.
    Synchronizes Visual Evidence with Document 2, 4, and 5 Mandates.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # v8.3 Mandate: Three distinct files [Doc 4 Sec II]
    primary_path = os.path.join(project_root, "charts", f"{ticker.upper()}_primary.png")
    context_path = os.path.join(project_root, "charts", f"{ticker.upper()}_context.png")
    focus_path = os.path.join(project_root, "charts", f"{ticker.upper()}_focus.png")

    # [MANDATE: AUTO-REJECT - DOC 4 SEC 451]
    if not os.path.exists(primary_path) or not os.path.exists(context_path) or not os.path.exists(focus_path):
        return {
            "verdict": "HALT",
            "reasoning": "AUTO-REJECT: Missing Mandatory Visual Evidence. Ensure Primary, Context, and Focus charts exist."
        }

    prompt = f"""
    You are the TBS Master Analyst. Execute the v8.3 AI-Assisted Visual Audit for {ticker.upper()} ({profile}).
    
    [VIEW 1: PRIMARY EXECUTION]
    1. Zero-Markup Rule: Are there manual lines? If YES, HALT.
    2. Floor Verification: Are SMA 50 and SMA 200 visible?
    3. ADX Verification (TRENDING ONLY): Look at the ADX sub-panel. Did the ADX line reach > 25 at any point prior to the current bar? If NO, and state is TRENDING, HALT.
    
    [VIEW 2: CONTEXT VERIFICATION]
    4. Structural Alignment: Does the higher-timeframe trend support the primary execution?
    
    [VIEW 3: FOCUS VIEW]
    5. Range Break: Is the current price breaking the 10-bar resistance ceiling?
    
    Respond STRICTLY in JSON format:
    {{
        "verdict": "PASS" | "HALT",
        "reasoning": "Concise summary of findings."
    }}
    """

    try:
        # Open all three images
        img_primary = Image.open(primary_path)
        img_context = Image.open(context_path)
        img_focus = Image.open(focus_path)

        # SSoT: Locked to gemini-2.5-flash
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img_primary, img_context, img_focus], # Correctly passing all 3 images
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )

        raw_text = response.text.strip()
        # Failsafe clean in case model ignores mime_type
        if raw_text.startswith('```json'):
            raw_text = raw_text.replace('```json', '').replace('```', '').strip()

        return json.loads(raw_text)

    except Exception as e:
        return {
            "verdict": "HALT",
            "reasoning": f"AI Vision Failure: {str(e)}. Operator must verify manually."
        }