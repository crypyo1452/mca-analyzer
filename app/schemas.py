from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field

class AnalyzeRequest(BaseModel):
    chain: str = Field(..., description="Only 'bsc' supported in MVP")
    address: str

class Factor(BaseModel):
    id: str
    weight: float
    signal: int
    evidence: List[str]
    impact: float

class Liquidity(BaseModel):
    pair: str
    dex: Optional[str] = None
    lp_locked_pct: Optional[float] = None
    locker: Optional[str] = None
    lock_until: Optional[str] = None

class Supply(BaseModel):
    total: Optional[str] = None
    dead_wallet_pct: Optional[float] = None
    top10_pct: Optional[float] = None

class Tax(BaseModel):
    buy: Optional[float] = None
    sell: Optional[float] = None
    honeypot: bool = False

class Timestamps(BaseModel):
    deployed: Optional[str] = None
    first_liquidity: Optional[str] = None

class AnalyzeResponse(BaseModel):
    chain: str
    token: dict
    score: float
    band: str
    factors: List[Factor]
    liquidity: Liquidity
    supply: Supply
    tax: Tax
    dev_links: List[dict] = []
    timestamps: Timestamps
    explanations: List[str]
    version: str = "0.1"
