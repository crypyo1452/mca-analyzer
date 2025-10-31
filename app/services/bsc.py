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


@dataclass
class AnalysisResult:
    address: str
    score: float
    verdict: str
    chain: str
    factors: List[RiskFactor]

    def model_dump(self) -> Dict[str, Any]:
        return {
            "address": self.address,
            "score": self.score,
            "verdict": self.verdict,
            "chain": self.chain,
            "factors": [asdict(f) for f in self.factors],
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
        impact = round(weight * (signal * 10), 2)
        factors.append(RiskFactor(id=fid, weight=weight, signal=signal, evidence=evidence, impact=impact))
    return factors


# ============================================================
# MAIN ANALYZER (mock scoring for now)
# ============================================================

def analyze_bsc(addr: str) -> AnalysisResult:
    factors = mock_factors(addr)

    # Aggregate mock score, clamp to [0, 10]
    score = sum(f.impact for f in factors)
    score = max(min(score + 5, 10), 0)

    if score >= 8:
        verdict = "✅ Safe / Trusted"
    elif score >= 5:
        verdict = "⚠️ Moderate Risk"
    else:
        verdict = "❌ High Risk"

    return AnalysisResult(
        address=addr,
        score=round(score, 2),
        verdict=verdict,
        chain="bsc",
        factors=factors,
    )


# ============================================================
# LIVE LOOKUP HELPERS (optional)
# ============================================================

def fetch_abi_from_bscscan(address: str) -> Optional[str]:
    """
    Return contract ABI as a JSON string from BscScan, or None if unavailable.
    Kept to satisfy imports from main.py.
    """
    if not BSCSCAN_API_KEY:
        # No key configured: return None so callers can fall back gracefully.
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
            # BscScan returns ABI as a JSON string
            return data.get("result")
        return None
    except Exception:
        return None


def get_token_info_from_bscscan(address: str) -> Dict[str, Any]:
    """
    Example BscScan token info call (not used in mock scoring).
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
