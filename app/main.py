from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import AnalyzeRequest
from app.services.bsc import analyze_bsc, fetch_abi_from_bscscan
import os

app = FastAPI(title="MCA — BSC Analyzer", version="0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    if req.chain.lower() != "bsc":
        raise HTTPException(status_code=400, detail="MVP supports only 'bsc' chain")
    return analyze_bsc(req).model_dump()

@app.get("/debug/bscscan")
def debug_bscscan(address: str = Query(..., description="Token contract address")):
    key_present = bool(os.getenv("BSCSCAN_API_KEY"))
    abi = fetch_abi_from_bscscan(address)
    return {
        "key_present": key_present,
        "abi_status": "ok" if abi else "missing_or_rate_limited",
        "abi_function_count": len(abi) if abi else 0,
    }
