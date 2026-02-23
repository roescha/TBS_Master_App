import json
import os
from PIL import Image
from google import genai
from google.genai import types

client = genai.Client()

async def run_vision_audit(ticker: str, profile: str) -> dict:
    """
    [MAX SPEED VERSION] Executes the AI-Assisted Visual Audit on the generated triple_view.png.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    chart_path = os.path.join(project_root, "charts", f"{ticker.upper()}_triple_view.png")

    if not os.path.exists(chart_path):
        return {
            "verdict": "HALT",
            "reasoning": f"Visual Evidence Missing: Could not locate {chart_path}."
        }

    prompt = f"""
    You are the TBS Master Analyst. You are executing the AI-Assisted Visual Audit for the ticker {ticker.upper()} under Profile {profile}.
    
    Analyze the provided Triple-View chart and strictly verify the following:
    
    [MANDATE: DATA INTEGRITY (AUTO-REJECT)]
    1. Zero-Markup Rule: Are there any manual drawings (trendlines, text boxes, fibonacci) on the chart? If YES, you MUST return a HALT verdict.
    2. Numerical Legend Rule: Is the legend visible, and are any numerical values masked with asterisks (e.g., ***)? If masked, you MUST return a HALT verdict.
    
    [MANDATE: STRUCTURAL ALIGNMENT]
    3. Moving Average Stack: Are the fast moving averages cleanly stacked above the structural floors (SMA 50, SMA 200)?
    4. Volume Climaxes: Is there visual evidence of a massive volume climax (institutional distribution) on a recent down bar?
    5. Structural Health: Does the overall price action look structurally sound and aligned with a markup phase?
    
    Based on these factors, issue a proposed verdict of either "PASS" or "HALT".
    
    Respond STRICTLY with a JSON object matching this schema:
    {{
        "verdict": "PASS" | "HALT",
        "reasoning": "A concise 2-3 sentence explanation of your visual findings, specifically noting if an Auto-Reject rule was triggered."
    }}
    """

    try:
        chart_image = Image.open(chart_path)

        # [MANDATE: INSTANT EXECUTION]
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, chart_image],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        return json.loads(response.text)

    except Exception as e:
        return {
            "verdict": "HALT",
            "reasoning": f"AI Vision HALT: API Connection Error. Operator must manually verify the chart."
        }