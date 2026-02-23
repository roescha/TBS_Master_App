from dotenv import load_dotenv
load_dotenv()  # Load environment variables immediately

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
from pydantic import BaseModel
from layers.ai_wacc_estimator import run_wacc_estimator_with_timeout
from layers.ai_event_radar import run_risk_radar
from layers.ai_vision_auditor import run_vision_audit
import uvicorn
import os

# --- TBS Helper Imports (The Brains) ---
from core.tbs_autoid import verify_asset_type
from core.tbs_governor import calculate_sizing_and_targets

# --- TBS Engine Imports (The Layers) ---
from layers.ibkr_sentinel import run_tbs_sentinel
from layers.yahoo_fundamentals import run_v8_clean_audit
from layers.ibkr_purity_engine import run_tbs_engine

# Initialize App
app = FastAPI(title="TBS Master API v8.2")

# CORS Middleware for Next.js Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the charts folder so the frontend can display the triple_view.png
os.makedirs("charts", exist_ok=True)
app.mount("/charts", StaticFiles(directory="charts"), name="charts")


# ==========================================
# PYDANTIC SCHEMAS (Payload Definitions)
# ==========================================
class AutoIDRequest(BaseModel):
    ticker: str
    mode: str = "INFO"

class AuditRequest(BaseModel):
    ticker: str
    profile: str
    mode: str
    is_etf: bool = False
    wacc: Optional[float] = None  # This explicitly allows 'null' from React

class SizingRequest(BaseModel):
    profile: str
    mode: str
    regime: str
    event_aware: bool
    vix_storm: bool
    audit_status: str
    engine_metrics: dict
    total_capital: float = 100000.0  # [MANDATE: Dynamic Capital Support]


# ==========================================
# THE EXECUTION PIPELINE ENDPOINTS
# ==========================================

@app.post("/api/preflight/autoid")
def check_asset_id(req: AutoIDRequest):
    """Step 0: Deterministic Asset Classification (ETF vs Standard)"""
    try:
        result = verify_asset_type(ticker=req.ticker, mode=req.mode)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/layer0/sentinel")
def get_sentinel():
    try:
        # Update this line to include storm_watch
        regime, verdict, reason, storm_watch = run_tbs_sentinel()

        return {
            "regime": regime,
            "verdict": verdict,
            "reason": reason,
            "storm_watch": storm_watch # Optional: pass it to the frontend if needed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/layer1/fundamentals")
def get_clean_audit(req: AuditRequest):
    """Step 5: Fundamental Clean Trade Audit (ROIC, Pulse, Turnaround)"""
    try:
        status, diag, metrics = run_v8_clean_audit(
            ticker=req.ticker,
            profile=req.profile,
            is_etf=req.is_etf,
            wacc=req.wacc
        )
        return {"status": status, "diagnostic": diag, "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/layer2/technical")
def get_technical_engine(req: AuditRequest):
    """Step 6: Structural Verification, Extension Rule & Triple-View Render"""
    try:
        status, diag, metrics = run_tbs_engine(
            ticker=req.ticker,
            profile=req.profile,
            is_etf=req.is_etf,
            mode=req.mode
        )
        chart_url = f"http://localhost:8000/charts/{req.ticker.upper()}_triple_view.png"

        return {
            "status": status,
            "diagnostic": diag,
            "metrics": metrics,
            "chart_url": chart_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/governor/sizing")
def calculate_sizing(req: SizingRequest):
    """Step 7: Posture Multipliers & Expectancy Math"""
    try:
        result = calculate_sizing_and_targets(
            profile=req.profile,
            mode=req.mode,
            regime=req.regime,
            event_aware=req.event_aware,
            vix_storm=req.vix_storm,
            audit_status=req.audit_status,
            engine_metrics=req.engine_metrics,
            total_net_worth=req.total_capital # [MANDATE: Dynamic Capital Injection]
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analyst/wacc/{ticker}")
async def get_analyst_wacc(ticker: str):
    """Step 5.1: Analyst-Automated WACC Retrieval with 60s Timeout Guard."""
    try:
        result = await run_wacc_estimator_with_timeout(ticker)
        if result.get("error"):
            raise HTTPException(status_code=408, detail=result["error"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analyst/radar/{ticker}")
async def get_analyst_radar(ticker: str):
    """Step 4: AI Risk Radar (Integrity Shocks & Event Gates)"""
    try:
        result = await run_risk_radar(ticker)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyst/vision")
async def get_vision_audit(req: AuditRequest):
    """Step 6.5: AI-Assisted Visual Audit (v8.2 Protocol)"""
    try:
        # The AI physically reads the triple_view.png generated in Step 6
        result = await run_vision_audit(ticker=req.ticker, profile=req.profile)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)