import json
import os
from PIL import Image
from google import genai
from google.genai import types

client = genai.Client()

async def run_vision_audit(ticker: str, profile: str) -> dict:
    """
    [v8.2 FINAL AUTHORITATIVE] Executes the Dual-Image Visual Audit.
    Synchronizes Visual Evidence with Document 2, 4, and 5 Mandates.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    chart_path = os.path.join(project_root, "charts", f"{ticker.upper()}_triple_view.png")
    focus_path = os.path.join(project_root, "charts", f"{ticker.upper()}_focus.png")

    # [MANDATE: AUTO-REJECT - DOC 4 SEC 451]
    if not os.path.exists(chart_path) or not os.path.exists(focus_path):
        return {
            "verdict": "HALT",
            "reasoning": "AUTO-REJECT: Missing Mandatory Visual Evidence (Triple-View or Focus Chart)."
        }

    prompt = f"""
    You are the TBS Master Analyst. Execute the v8.2 AI-Assisted Visual Audit for {ticker.upper()} ({profile}).
    
    [VIEW 1: TRIPLE-VIEW] - Structural Verification
    1. Zero-Markup Rule: Any manual drawings (lines/text)? If YES, HALT [Doc 4 Sec 417].
    2. Numerical Legend: Any masked values (***)? If YES, HALT [Doc 4 Sec 421].
    3. Floor Verification: Are SMA 50 (Red) and SMA 200 (White) visible and stacked? [Doc 4 Sec 426].
    4. Ambiguity Check: Is price currently within 0.1 ATR of the Structural Floor? If YES, the signal is AMBIGUOUS; return HALT [Doc 5 Sec 31, 57].
    
    [VIEW 2: FOCUS VIEW] - Range & Timing [Doc 4 Sec 442]
    5. Consolidation Range: Is the current price breaking the 10-bar resistance ceiling? [Doc 2 Sec 96].
    6. Window Binding: Is this event within 2 bars of the initial break? [Doc 2 Sec 81].
    
    [DETERMINISTIC RULE]
    In this system, "Maybe" is a FAIL. If indicators are unclear, return HALT [Doc 5 Sec 55].
    
    Respond STRICTLY in JSON format:
    {{
        "verdict": "PASS" | "HALT",
        "reasoning": "Concise summary of Floor Alignment, Ambiguity Buffer, and Window status."
    }}
    """

    try:
        img_triple = Image.open(chart_path)
        img_focus = Image.open(focus_path)

        # SSoT: Locked to gemini-2.5-flash per ai_vision_auditor.py source
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img_triple, img_focus],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        return json.loads(response.text)

    except Exception as e:
        return { "verdict": "HALT", "reasoning": f"AI Vision Audit Error: {str(e)}" }