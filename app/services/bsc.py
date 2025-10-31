from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple

import httpx
from web3 import Web3

from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    Factor,
    Liquidity,
    Supply,
    Tax,
    Timestamps,
)

ZERO = "0x0000000000000000000000000000000000000000"
DEAD = Web3.to_checksum_address("0x000000000000000000000000000000000000dEaD")

PANCAKE_V2_FACTORY = Web3.to_checksum_address("0xCA143Ce32Fe78f1f7019d7d551a6402fC5350c73")
WBNB = Web3.to_checksum_address("0xBB4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
USDT = Web3.to_checksum_address("0x55d398326f99059fF775485246999027B3197955")

PANCAKE_V3_FACTORY = Web3.to_checksum_address("0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865")
V3_FEE_TIERS = (100, 500, 2500, 10000)

FACTORY_V2_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]
FACTORY_V3_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24",  "name": "fee",    "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

KNOWN_LOCKERS = {
    Web3.to_checksum_address("0x000000000000000000000000000000000000dEaD"): "Burned LP",
    Web3.to_checksum_address("0x71b5759d73262fbB223956913ecF4ecC51057641"): "PinkLock",
    Web3.to_checksum_address("0x160C404B2b49CB2bB4eacF99C43D87bE4D5d7011"): "Unicrypt",
    Web3.to_checksum_address("0x04e6F62f0fB5C0a2bF9b2b9D8c9C28840fd6B5C8"): "Team.Finance",
}

SCORE_BANDS = [
    (70, "lower_risk"),
    (40, "caution"),
    (0, "high_risk"),
]

FACTOR_WEIGHTS = {
    "ownership": 0.25,
    "mint_blacklist": 0.20,
    "liquidity_lock": 0.20,
    "holder_concentration": 0.15,
    "dev_history": 0.10,
    "tax_honeypot": 0.05,
    "market_integrity": 0.05,
}

def band_from_score(score: float) -> str:
    for threshold, label in SCORE_BANDS:
        if score >= threshold:
            return label
    return "high_risk"

def _w3() -> Optional[Web3]:
    rpc = os.getenv("BSC_RPC_URL") or "https://bsc-dataseed.binance.org/"
    try:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 8}))
        return w3 if w3.is_connected() else None
    except Exception:
        return None

def _get_json(url: str, params: dict, timeout: int = 8) -> Optional[dict]:
    try:
        r = httpx.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def mock_factors(addr: str) -> List[Factor]:
    h = int(addr[2:6], 16)
    s1 = -1 if (h % 3 == 0) else (1 if (h % 3 == 1) else 0)
    s2 = -1 if (h % 5 == 0) else 1
    s3 = 1 if (h % 7 != 0) else -1
    s4 = 0 if (h % 2 == 0) else -1
    s5 = 1 if (h % 11 != 0) else 0
    s6 = -1 if (h % 13 == 0) else 1
    s7 = 1 if (h % 17 != 0) else -1
    rows = [
        ("ownership", s1, ["owner=0xabc…", "renounce=false"]),
        ("mint_blacklist", s2, ["mint() present", "blacklist() absent"]),
        ("liquidity_lock", s3, ["lock=80% until 2026-12-31"]),
        ("holder_concentration", s4, ["top10=22%", "dead=50%"]),
        ("dev_history", s5, ["no known rugs linked"]),
        ("tax_honeypot", s6, ["buy=2, sell=2", "honeypot=false"]),
        ("market_integrity", s7, ["Pancake v2/v3 pool (if found)"]),
    ]
    out: List[Factor] = []
    for fid, signal, evidence in rows:
        weight = FACTOR_WEIGHTS[fid]
        impact = round(weight * (f.signal * 10), 2)
        out.append(Factor(id=fid, weight=weight, signal=signal, evidence=evidence, impact=impact))
    return out

def find_pancake_v2_pair(token_address: str) -> Optional[str]:
    w3 = _w3()
    if not w3:
        return None
    try:
        token = Web3.to_checksum_address(token_address)
    except Exception:
        return None
    factory = w3.eth.contract(address=PANCAKE_V2_FACTORY, abi=FACTORY_V2_ABI)
    for other in (WBNB, USDT):
        try:
            pair = factory.functions.getPair(token, other).call()
            if pair and pair.lower() != ZERO:
                return Web3.to_checksum_address(pair)
        except Exception:
            continue
    return None

def find_pancake_v3_pool(token_address: str) -> Optional[Tuple[str, int, str]]:
    w3 = _w3()
    if not w3:
        return None
    try:
        token = Web3.to_checksum_address(token_address)
    except Exception:
        return None
    factory = w3.eth.contract(address=PANCAKE_V3_FACTORY, abi=FACTORY_V3_ABI)
    for quote, symbol in ((WBNB, "WBNB"), (USDT, "USDT")):
        for fee in V3_FEE_TIERS:
            try:
                pool = factory.functions.getPool(token, quote, fee).call()
                if pool and pool.lower() != ZERO:
                    return Web3.to_checksum_address(pool), fee, symbol
            except Exception:
                continue
    return None

def fetch_abi_from_bscscan(token_address: str) -> Optional[list]:
    api_key = os.getenv("BSCSCAN_API_KEY", "")
    if not api_key:
        return None
    params = {"module": "contract", "action": "getabi", "address": token_address, "apikey": api_key}
    data = _get_json("https://api.bscscan.com/api", params)
    if not data:
        return None
    try:
        if data.get("status") == "1" and data.get("result"):
            return json.loads(data["result"])
    except Exception:
        pass
    return None

def get_owner_via_abi(token_address: str) -> Optional[str]:
    abi = fetch_abi_from_bscscan(token_address)
    if not abi:
        return None
    w3 = _w3()
    if not w3:
        return None
    try:
        token = Web3.to_checksum_address(token_address)
        c = w3.eth.contract(address=token, abi=abi)
        for fn in ("owner", "getOwner"):
            if hasattr(c.functions, fn):
                try:
                    owner = getattr(c.functions, fn)().call()
                    if isinstance(owner, str) and owner.startswith("0x") and len(owner) == 42:
                        return Web3.to_checksum_address(owner)
                except Exception:
                    continue
    except Exception:
        return None
    return None

def ownership_signal(addr: str) -> tuple[int, List[str]]:
    owner = get_owner_via_abi(addr)
    if owner is None:
        return 0, ["Owner unknown (ABI/owner() not available)"]
    if owner.lower() == ZERO:
        return 1, [f"Ownership renounced (owner={ZERO})"]
    return -1, [f"Owner set: {owner}"]

def get_supply_stats(token_address: str) -> tuple[Optional[str], Optional[float], Optional[int]]:
    w3 = _w3()
    if not w3:
        return None, None, None
    try:
        token = Web3.to_checksum_address(token_address)
        c = w3.eth.contract(address=token, abi=ERC20_ABI)
        decimals = int(c.functions.decimals().call())
        total = c.functions.totalSupply().call()
        dead_bal = c.functions.balanceOf(DEAD).call()
        scale = 10 ** decimals if decimals >= 0 else 1
        total_h = total / scale if scale else float(total)
        dead_h = dead_bal / scale if scale else float(dead_bal)
        dead_pct = round((dead_h / total_h) * 100, 4) if total_h > 0 else None
        total_disp = f"{total_h:,.0f}" if total_h >= 1_000_000 else f"{total_h}"
        return total_disp, dead_pct, decimals
    except Exception:
        return None, None, None

def top_holders_pct_bscscan(token_address: str, decimals: Optional[int]) -> Optional[float]:
    api_key = os.getenv("BSCSCAN_API_KEY", "")
    if not api_key:
        return None
    params = {
        "module": "token",
        "action": "tokenholderlist",
        "contractaddress": token_address,
        "page": 1,
        "offset": 10,
        "apikey": api_key,
    }
    data = _get_json("https://api.bscscan.com/api", params)
    if not data or data.get("status") != "1" or not data.get("result"):
        return None
    w3 = _w3()
    if not w3:
        return None
    try:
        token = Web3.to_checksum_address(token_address)
        c = w3.eth.contract(address=token, abi=ERC20_ABI)
        total_raw = c.functions.totalSupply().call()
        if total_raw <= 0:
            return None
        top_sum_raw = 0
        for h in data["result"]:
            qty_str = h.get("TokenHolderQuantity") or "0"
            try:
                top_sum_raw += int(qty_str)
            except Exception:
                top_sum_raw += int(qty_str.replace(".", ""))
        pct = (top_sum_raw / total_raw) * 100
        return round(pct, 4)
    except Exception:
        return None

SUSPICIOUS_FN_KEYWORDS = {
    "blacklist", "whitelist", "isBlacklisted", "setBlacklist",
    "setTax", "setFee", "setFees", "setBuyFee", "setSellFee",
    "setMaxTx", "maxTx", "setMaxWallet", "enableTrading",
    "addLiquidity", "removeLimits", "excludeFromFee",
    "mint", "setBalance"
}

def abi_risk_flags(token_address: str) -> tuple[int, List[str], int, List[str]]:
    abi = fetch_abi_from_bscscan(token_address)
    if not abi:
        return 0, ["ABI unavailable"], 0, ["ABI unavailable"]
    fn_names = set()
    try:
        for item in abi:
            if item.get("type") == "function" and "name" in item:
                fn_names.add(item["name"])
    except Exception:
        return 0, ["ABI parse error"], 0, ["ABI parse error"]
    mb_evidence, mb_signal = [], 0
    for k in SUSPICIOUS_FN_KEYWORDS:
        for name in fn_names:
            if k.lower() in name.lower():
                mb_evidence.append(f"Suspicious fn: {name}()")
                mb_signal = -1
    th_evidence, th_signal = [], 0
    for name in fn_names:
        lname = name.lower()
        if "buyfee" in lname or "sellfee" in lname or "tax" in lname or "fees" in lname:
            th_evidence.append(f"Fee/tax fn: {name}()")
            th_signal = -1
    if not mb_evidence:
        mb_evidence = ["No obvious mint/blacklist functions detected"]
    if not th_evidence:
        th_evidence = ["No obvious tax/honeypot functions detected"]
    return mb_signal, mb_evidence, th_signal, th_evidence

def liquidity_lock_status_v2(pair_address: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    if not pair_address or pair_address.lower() == ZERO:
        return None, None
    w3 = _w3()
    if not w3:
        return None, None
    try:
        pair = Web3.to_checksum_address(pair_address)
        lp = w3.eth.contract(address=pair, abi=ERC20_ABI)
        total_lp = lp.functions.totalSupply().call()
        if total_lp == 0:
            return None, None
        best_label, best_pct = None, 0.0
        for addr, label in KNOWN_LOCKERS.items():
            bal = lp.functions.balanceOf(addr).call()
            pct = (bal / total_lp) * 100
            if pct > best_pct:
                best_pct, best_label = pct, label
        if best_label is None:
            return None, None
        return round(best_pct, 4), best_label
    except Exception:
        return None, None

def analyze_bsc(req: AnalyzeRequest) -> AnalyzeResponse:
    addr = req.address
    v2_pair = find_pancake_v2_pair(addr)
    v3_res = find_pancake_v3_pool(addr)

    own_signal, own_evidence = ownership_signal(addr)
    total_disp, dead_pct, decimals = get_supply_stats(addr)
    top10_pct = top_holders_pct_bscscan(addr, decimals)
    mb_signal, mb_evidence, th_signal, th_evidence = abi_risk_flags(addr)
    lp_locked_pct, locker_label = liquidity_lock_status_v2(v2_pair)

    factors = mock_factors(addr)

    for f in factors:
        if f.id == "ownership":
            f.signal = own_signal; f.evidence = own_evidence
            f.impact = round(f.weight * (f.signal * 10), 2); break
    for f in factors:
        if f.id == "mint_blacklist":
            f.signal = mb_signal; f.evidence = mb_evidence
            f.impact = round(f.weight * (f.signal * 10), 2); break
    for f in factors:
        if f.id == "tax_honeypot":
            f.signal = th_signal; f.evidence = th_evidence
            f.impact = round(f.weight * (f.signal * 10), 2); break
    for f in factors:
        if f.id == "holder_concentration":
            if top10_pct is not None:
                f.signal = -1 if top10_pct > 50 else (0 if top10_pct > 25 else 1)
                f.evidence = [f"Top10 holders = {top10_pct}%"]
                f.impact = round(f.weight * (f.signal * 10), 2)
            else:
                f.evidence = ["Top10 holders unknown (API limit)"]
            break
    if v2_pair and v3_res:
        pool, fee, quote = v3_res
        for f in factors:
            if f.id == "market_integrity":
                f.signal = max(f.signal, 1)
                f.evidence = [f"Pancake v2 pair found: {v2_pair}",
                              f"Pancake v3 pool found: {pool} (fee {fee/100:.2f}%, {quote})"]
                f.impact = round(f.weight * (f.signal * 10), 2); break
    elif v2_pair:
        for f in factors:
            if f.id == "market_integrity":
                f.signal = max(f.signal, 1)
                f.evidence = [f"Pancake v2 pair found: {v2_pair}"]
                f.impact = round(f.weight * (f.signal * 10), 2); break
    elif v3_res:
        pool, fee, quote = v3_res
        for f in factors:
            if f.id == "market_integrity":
                f.signal = max(f.signal, 1)
                f.evidence = [f"Pancake v3 pool found: {pool} (fee {fee/100:.2f}%, {quote})"]
                f.impact = round(f.weight * (f.signal * 10), 2); break

    if v2_pair:
        dex = "PancakeSwapV2"; pair_or_pool = v2_pair
    elif v3_res:
        dex = "PancakeSwapV3"; pair_or_pool = v3_res[0]; lp_locked_pct, locker_label = None, None
    else:
        dex = None; pair_or_pool = ZERO

    score = max(0.0, min(100.0, sum(f.impact for f in factors) + 60))
    band = band_from_score(score)

    liquidity = Liquidity(
        pair=pair_or_pool, dex=dex,
        lp_locked_pct=lp_locked_pct, locker=locker_label, lock_until=None
    )
    supply = Supply(total=total_disp, dead_wallet_pct=dead_pct, top10_pct=top10_pct)
    tax = Tax(buy=None, sell=None, honeypot=(th_signal == -1))
    ts = Timestamps(deployed=None, first_liquidity=None)

    explanations = [
        "Ownership via BscScan ABI; renounced if owner() == 0x0",
        "Pancake v2 pair via factory.getPair(token, WBNB/USDT)",
        "Pancake v3 pool via factory.getPool(token, WBNB/USDT, fee)",
        "Supply & burn via ERC-20 totalSupply()/balanceOf(dead)",
        "Top holders via BscScan tokenholderlist (best-effort)",
        "LP lock via v2 LP ERC-20 balances held by known lockers",
    ]

    return AnalyzeResponse(
        chain="bsc",
        token={"address": addr, "symbol": "MEME", "name": "Memecoin"},
        score=round(score, 2), band=band, factors=factors,
        liquidity=liquidity, supply=supply, tax=tax,
        dev_links=[], timestamps=ts, explanations=explanations
    )
