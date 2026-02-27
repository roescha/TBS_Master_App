from dotenv import load_dotenv
load_dotenv()  # Load environment variables immediately

import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
from pydantic import BaseModel
import uvicorn
import os

# --- AI Layers ---
from layers.ai_fundamental_retriever import run_retriever_with_timeout
from layers.ai_event_radar import run_risk_radar
from layers.ai_vision_auditor import run_vision_audit

# --- TBS Helper Imports (The Brains) ---
from core.tbs_autoid import verify_asset_type
from core.tbs_governor import calculate_sizing_and_targets

# --- TBS Engine Imports (The Layers) ---
from layers.ibkr_sentinel import run_tbs_sentinel
from layers.yahoo_fundamentals import run_v8_clean_audit
from layers.ibkr_sympathy_audit import run_sympathy_audit
from layers.ibkr_asset_gates import run_asset_gates
from layers.ibkr_purity_engine import run_tbs_engine

# Initialize App
app = FastAPI(title="TBS Master API v8.3")

# CORS Middleware for Next.js Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the charts folder so the frontend can display the Triple-View charts
os.makedirs("charts", exist_ok=True)
app.mount("/charts", StaticFiles(directory="charts"), name="charts")

# ==============================================================================
# SCHEMAS
# ==============================================================================

class AuditRequest(BaseModel):
    ticker: str
    profile: str
    mode: str
    is_etf: bool = False
    total_capital: float = 100000.0

    # [v8.3] The Fallback Track: Analyst Override Mandate fields
    wacc: Optional[float] = None
    moat: Optional[str] = None
    tnx: Optional[float] = None
    roic_override: Optional[float] = None
    de_override: Optional[float] = None
    fcf_yield_override: Optional[float] = None
    rev_override: Optional[float] = None
    eps_override: Optional[float] = None
    sector_etf_override: Optional[str] = None
    pivot_confirmed: bool = False

class SizingRequest(BaseModel):
    profile: str
    mode: str
    regime: str
    event_aware: bool
    vix_storm: bool
    audit_status: str
    engine_metrics: dict
    total_capital: float

# ==============================================================================
# PIPELINE ENDPOINTS (Synchronous / Threaded for IBKR Safety)
# ==============================================================================

import traceback # Add this at the top of main.py if not already there

@app.post("/api/preflight/autoid")
def get_autoid(req: dict):
    """Pre-Flight: Detect if ETF or Equity"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        res = verify_asset_type(req.get("ticker"), mode=req.get("mode", "INFO"))

        # Smart-Parsing: Handle both Dictionary and Tuple returns from v8.3
        is_etf = False
        long_name = ""

        if isinstance(res, dict):
            is_etf = res.get("is_etf", False)
            long_name = res.get("long_name", "")
        elif isinstance(res, tuple) or isinstance(res, list):
            # Scan the tuple to find which element is the actual boolean
            for item in res:
                if isinstance(item, bool):
                    is_etf = item
                    break
            # Attempt to grab a string name if available
            strings = [x for x in res if isinstance(x, str) and x != req.get("ticker")]
            if strings:
                long_name = strings[0]

        # Force strict boolean casting to protect downstream Pydantic schemas
        return {"is_etf": bool(is_etf), "long_name": str(long_name)}

    except Exception as e:
        print("=== PREFLIGHT CRASH ===")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/layer0/sentinel")
def get_sentinel(req: dict):
    """Layer 0: Systemic Macro Weather calculation"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        port = 4001 if req.get("mode", "INFO") == "LIVE" else 4002
        regime, verdict, reason, storm_watch, details = run_tbs_sentinel(
            port=port,
            profile=req.get("profile", "TREND"),
            useRTH=True
        )
        return {
            "regime": regime,
            "verdict": verdict,
            "reason": reason,
            "storm_watch": storm_watch,
            "details": details
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/layer15/sympathy")
def get_sympathy_audit(req: AuditRequest):
    """Layer 1.5a: Sector ETF Sympathy Audit"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        status, diag, metrics = run_sympathy_audit(
            ticker=req.ticker,
            profile=req.profile,
            sector_etf_override=req.sector_etf_override,
            mode=req.mode
        )
        return {"status": status, "diagnostic": diag, "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/layer15/asset-gates")
def get_asset_gates(req: AuditRequest):
    """Layer 1.5b: IV Guard and Dividend Lockout"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        status, diag, metrics = run_asset_gates(
            ticker=req.ticker,
            profile=req.profile,
            mode=req.mode
        )
        return {"status": status, "diagnostic": diag, "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/layer1/fundamentals")
def get_fundamentals(req: AuditRequest):
    """Layer 1: Fundamental DNA, Pulse, and Health Audit"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        status, diag, metrics = run_v8_clean_audit(
            ticker=req.ticker,
            profile=req.profile,
            is_etf=req.is_etf,
            wacc=req.wacc,
            moat=req.moat,
            pivot_confirmed=req.pivot_confirmed,
            roic_override=req.roic_override,
            tnx=req.tnx,
            de_override=req.de_override,
            fcf_yield_override=req.fcf_yield_override,
            rev_override=req.rev_override,
            eps_override=req.eps_override
        )
        return {"status": status, "diagnostic": diag, "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/layer2/technical")
def get_technical(req: AuditRequest):
    """Layer 2: Structural Verification & Technical Engine"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        status, diag, metrics = run_tbs_engine(
            ticker=req.ticker,
            profile=req.profile,
            is_etf=req.is_etf,
            mode=req.mode
        )
        return {
            "status": status,
            "diagnostic": diag,
            "metrics": metrics,
            "charts": {
                "primary": f"http://localhost:8000/charts/{req.ticker}_primary.png",
                "context": f"http://localhost:8000/charts/{req.ticker}_context.png",
                "focus":   f"http://localhost:8000/charts/{req.ticker}_focus.png"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/governor/sizing")
def get_sizing(req: SizingRequest):
    """Layer 3 (Part 1): Posture Multipliers & Expectancy Math"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        result = calculate_sizing_and_targets(
            profile=req.profile,
            mode=req.mode,
            regime=req.regime,
            event_aware=req.event_aware,
            vix_storm=req.vix_storm,
            audit_status=req.audit_status,
            engine_metrics=req.engine_metrics,
            total_net_worth=req.total_capital
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# AI ANALYST ENDPOINTS (Asynchronous / Network Bound)
# ==============================================================================

@app.get("/api/analyst/retrieve/{ticker}")
async def get_analyst_retrieval(ticker: str, metric: str = "WACC"):
    """Step 5.1: Analyst-Automated Fundamental Retrieval with 120s Extended Timeout."""
    try:
        # Pass the 120.0 explicitly as the third argument
        result = await run_retriever_with_timeout(ticker, metric, timeout=120.0)

        if result.get("data", {}).get("error"):
            raise HTTPException(status_code=408, detail=result["data"]["error"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analyst/radar/{ticker}")
async def get_analyst_radar(ticker: str):
    """AI Risk Radar (Integrity Shocks & Event Gates)"""
    try:
        result = await run_risk_radar(ticker)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyst/vision")
async def get_vision_audit(req: AuditRequest):
    """AI-Assisted Visual Audit (v8.3 Protocol)"""
    try:
        result = await run_vision_audit(req.ticker, req.profile)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)