import json
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FMP_API_KEY, FMP_BASE_URL, CACHE_DIR, CACHE_TTL_HOURS


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _load_cache(key: str):
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    if age_hours > CACHE_TTL_HOURS:
        return None
    with open(path) as f:
        return json.load(f)


def _save_cache(key: str, data) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(key), "w") as f:
        json.dump(data, f)


def _get(endpoint: str, params: dict = None):
    params = params or {}
    params["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE_URL}/{endpoint}"
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def get_income_statement(ticker: str, limit: int = 5) -> list:
    key = f"income_{ticker}_{limit}"
    cached = _load_cache(key)
    if cached:
        return cached
    data = _get("income-statement", {"symbol": ticker, "limit": limit, "period": "annual"})
    _save_cache(key, data)
    return data


def get_balance_sheet(ticker: str, limit: int = 5) -> list:
    key = f"balance_{ticker}_{limit}"
    cached = _load_cache(key)
    if cached:
        return cached
    data = _get("balance-sheet-statement", {"symbol": ticker, "limit": limit, "period": "annual"})
    _save_cache(key, data)
    return data


def get_cash_flow(ticker: str, limit: int = 5) -> list:
    key = f"cashflow_{ticker}_{limit}"
    cached = _load_cache(key)
    if cached:
        return cached
    data = _get("cash-flow-statement", {"symbol": ticker, "limit": limit, "period": "annual"})
    _save_cache(key, data)
    return data


def get_company_profile(ticker: str) -> dict:
    key = f"profile_{ticker}"
    cached = _load_cache(key)
    if cached:
        return cached[0] if isinstance(cached, list) else cached
    data = _get("profile", {"symbol": ticker})
    _save_cache(key, data)
    return data[0] if data else {}


def get_peers(ticker: str) -> list:
    key = f"peers_{ticker}"
    cached = _load_cache(key)
    if cached:
        return cached
    data = _get("stock-peers", {"symbol": ticker})
    peers = [p["symbol"] for p in data] if data else []
    _save_cache(key, peers)
    return peers


def get_risk_free_rate() -> float:
    """Pull 10Y US Treasury yield from FRED (no API key needed)."""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
        r = requests.get(url, timeout=10)
        lines = r.text.strip().split("\n")
        for line in reversed(lines):
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() != ".":
                return float(parts[1].strip()) / 100
    except Exception:
        pass
    from config import RISK_FREE_RATE_DEFAULT
    return RISK_FREE_RATE_DEFAULT


def validate_ticker(ticker: str) -> bool:
    try:
        profile = get_company_profile(ticker.upper())
        return bool(profile.get("symbol"))
    except Exception:
        return False
