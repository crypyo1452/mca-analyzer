import os
import requests
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

# ============================================================
# CONFIG
# ============================================================

BSCSCAN_API_KEY = os.getenv("BSCSCAN_API_KEY", "")
BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org/")

# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class RiskFactor:
    id: str
    weight: float
    signal: float  # -1 = bad, 0 = neutral, 1 = good
    evidence: List[str]
    impact: float = 0.0

    @property
    def label(self) -> str:
        # Convert ids like "holder_concentration" -> "Holder concentration"
        return self.id.replace("_", " ").capitalize()

@dataclass
class AnalysisResult:
    chain: str
    address: str
    token: Dict[str, Any]
    score: float           # 0..10
    band: str              # "safe" | "caution" | "high"
    verdict: str           # emoji text
    factors: List[RiskFactor]

    def model_dump(self) -> Dict[str, Any]:
        return {
            "chain": self.chain,
            "address": self.address,
            "token": self.token,
            "score": self.score,
            "band": self.band,
            "verdict": self.verdict,
            "factors": [
                {
                    **asdict(f),
                    "label": f.label,
                }
                for f in self.factors
            ],
        }

# ============================================================
# MOCK FACTORS (temporary)
# ============================================================

def mock_factors(addr: str) -> List[RiskFactor]:
    base = [
        ("ownership",            0.25,  0,  ["Owner unknown (ABI/owner() not available)"]),
        ("mint_blacklist",       0.20,  0,  ["ABI unavailable"]),
        ("liquidity_lock",       0.20, -1,  ["LP locked 0.0% via Burned LP"]),
        ("holder_concentration", 0.15, -1,  ["Top10 holders unknown (API limit)"]),
        ("dev_history",          0.10,  1,  ["No known rugs linked"]),
        ("tax_honeypot",         0.05,  0,  ["ABI unavailable"]),
        ("market_integrity",     0.05,  1,  ["Pancake v2 pair found: 0x0eD7e52944161450477ee417DE9Cd3a859b14fD0"]),
    ]
    factors: List[RiskFactor] = []
    for fid, weight, signal, evidence in base:
        impact = round(weight * (signal * 10), 2)  # e.g., 0.2 * (-1*10) = -2.0
        factors.append(RiskFactor(id=fid, weight=weight, signal=signal, evidence=evidence, impact=impact))
    return factors

# ============================================================
# MAIN ANALYZER (mock scoring now, real data later)
# ============================================================

def analyze_bsc(addr: str) -> AnalysisResult:
    # 1) Try to fetch token name/symbol from BscScan
    token_name, token_symbol = fetch_token_meta(addr)

    # 2) Compute factors and score (mock for now)
    factors = mock_factors(addr)
    raw = sum(f.impact for f in factors)            # can be negative/positive
    score = max(min(raw + 5, 10), 0)                # normalize to 0..10

    # 3) Map to band + verdict
    if score >= 8:
        band = "safe"
        verdict = "✅ Safe / Trusted"
    elif score >= 5:
        band = "caution"
        verdict = "⚠️ Moderate Risk"
    else:
        band = "high"
        verdict = "❌ High Risk"

    token = {
        "address": addr,
        "name": token_name or "?",
        "symbol": token_symbol or "?",
    }

    return AnalysisResult(
        chain="bsc",
        address=addr,
        token=token,
        score=round(score, 1),
        band=band,
        verdict=verdict,
        factors=factors,
    )

# ============================================================
# LIVE LOOKUP HELPERS (optional)
# ============================================================

def fetch_abi_from_bscscan(address: str) -> Optional[str]:
    """
    Return contract ABI as a JSON string from BscScan, or None if unavailable.
    Kept for compatibility with main.py imports.
    """
    if not BSCSCAN_API_KEY:
        return None
    url = "https://api.bscscan.com/api"
    params = {
        "module": "contract",
        "action": "getabi",
        "address": address,
        "apikey": BSCSCAN_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        data = r.json()
        if data.get("status") == "1":
            return data.get("result")
        return None
    except Exception:
        return None

def fetch_token_meta(address: str) -> (Optional[str], Optional[str]):
    """
    Best-effort token name/symbol via BscScan.
    Returns (name, symbol) or (None, None) if unavailable.
    """
    if not BSCSCAN_API_KEY:
        return None, None

    url = "https://api.bscscan.com/api"
    params = {
        "module": "token",
        "action": "tokeninfo",
        "contractaddress": address,
        "apikey": BSCSCAN_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        data = r.json()
        if data.get("status") == "1":
            result = data.get("result") or []
            if isinstance(result, list) and result:
                item = result[0]
                name = item.get("tokenName") or item.get("name")
                symbol = item.get("symbol")
                return name, symbol
        return None, None
    except Exception:
        return None, None

def get_token_info_from_bscscan(address: str) -> Dict[str, Any]:
    """
    Raw tokeninfo call (not used by analyzer, useful for debugging).
    """
    if not BSCSCAN_API_KEY:
        return {"error": "Missing BSCSCAN_API_KEY"}
    url = "https://api.bscscan.com/api"
    params = {
        "module": "token",
        "action": "tokeninfo",
        "contractaddress": address,
        "apikey": BSCSCAN_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        return r.json()
    except Exception as e:
        return {"error": str(e)}
