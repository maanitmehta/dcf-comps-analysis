import json
import os
import sys
import time
import threading
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FMP_API_KEY, FMP_BASE_URL, CACHE_DIR, CACHE_TTL_HOURS

# ── In-memory cache (process-level, survives across requests in same worker) ──
_mem_cache: dict = {}
_mem_lock = threading.Lock()

# ── Semaphore: cap concurrent FMP API calls to avoid free-tier throttling ─────
_api_sem = threading.Semaphore(3)


def _load_cache(key: str):
    # 1. Memory cache — instant
    with _mem_lock:
        if key in _mem_cache:
            ts, data = _mem_cache[key]
            if time.time() - ts < CACHE_TTL_HOURS * 3600:
                return data
            del _mem_cache[key]

    # 2. File cache — persists across cold starts on same instance
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    if (time.time() - os.path.getmtime(path)) / 3600 > CACHE_TTL_HOURS:
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        with _mem_lock:
            _mem_cache[key] = (time.time(), data)
        return data
    except Exception:
        return None


def _save_cache(key: str, data) -> None:
    with _mem_lock:
        _mem_cache[key] = (time.time(), data)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, f"{key}.json"), "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _get(endpoint: str, params: dict = None):
    params = params or {}
    params["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE_URL}/{endpoint}"
    with _api_sem:          # max 3 concurrent calls — prevents FMP throttling
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()


def get_income_statement(ticker: str, limit: int = 5) -> list:
    key = f"income_{ticker}_{limit}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    data = _get("income-statement", {"symbol": ticker, "limit": limit, "period": "annual"})
    _save_cache(key, data)
    return data


def get_balance_sheet(ticker: str, limit: int = 5) -> list:
    key = f"balance_{ticker}_{limit}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    data = _get("balance-sheet-statement", {"symbol": ticker, "limit": limit, "period": "annual"})
    _save_cache(key, data)
    return data


def get_cash_flow(ticker: str, limit: int = 5) -> list:
    key = f"cashflow_{ticker}_{limit}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    data = _get("cash-flow-statement", {"symbol": ticker, "limit": limit, "period": "annual"})
    _save_cache(key, data)
    return data


def get_company_profile(ticker: str) -> dict:
    key = f"profile_{ticker}"
    cached = _load_cache(key)
    if cached is not None:
        return cached[0] if isinstance(cached, list) else cached
    data = _get("profile", {"symbol": ticker})
    _save_cache(key, data)
    return data[0] if data else {}


def get_peers(ticker: str) -> list:
    key = f"peers_{ticker}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    data = _get("stock-peers", {"symbol": ticker})
    peers = [p["symbol"] for p in data] if data else []
    _save_cache(key, peers)
    return peers


def get_historical_prices(ticker: str, limit: int = 252) -> list:
    key = f"hist_{ticker}_{limit}"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    data = _get("historical-price-eod/full", {"symbol": ticker, "limit": limit})
    _save_cache(key, data)
    return data


def get_risk_free_rate() -> float:
    key = "rfr_fred"
    cached = _load_cache(key)
    if cached is not None:
        return cached
    try:
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
                         timeout=10)
        for line in reversed(r.text.strip().split("\n")):
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() != ".":
                rfr = float(parts[1].strip()) / 100
                _save_cache(key, rfr)
                return rfr
    except Exception:
        pass
    from config import RISK_FREE_RATE_DEFAULT
    return RISK_FREE_RATE_DEFAULT


def get_live_price(ticker: str) -> dict:
    try:
        data = _get("quote-short", {"symbol": ticker})
        if data:
            price  = data[0].get("price",  0) or 0
            change = data[0].get("change", 0) or 0
            prev   = price - change
            return {"price": price, "change": change,
                    "change_pct": round(change / prev * 100, 2) if prev else 0}
    except Exception:
        pass
    return {"price": 0, "change": 0, "change_pct": 0}


def is_market_open() -> bool:
    utc_now = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-4 if 3 <= utc_now.month <= 11 else -5)
    et_now = (utc_now + et_offset).replace(tzinfo=None)
    if et_now.weekday() >= 5:
        return False
    open_t  = et_now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_t = et_now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_t <= et_now <= close_t


def validate_ticker(ticker: str) -> bool:
    try:
        return bool(get_company_profile(ticker.upper()).get("symbol"))
    except Exception:
        return False
