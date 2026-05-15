import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from data.fetcher import get_peers, get_company_profile, get_income_statement, get_balance_sheet


def _get_multiples(ticker: str) -> dict:
    try:
        profile = get_company_profile(ticker)
        inc = get_income_statement(ticker, 1)
        bs = get_balance_sheet(ticker, 1)
        if not inc or not bs:
            return None

        inc0, bs0 = inc[0], bs[0]
        market_cap = profile.get("marketCap") or 0
        total_debt = bs0.get("totalDebt") or 0
        cash = (bs0.get("cashAndCashEquivalents") or 0) + (bs0.get("shortTermInvestments") or 0)
        ev = market_cap + total_debt - cash

        revenue = inc0.get("revenue") or 0
        ebitda = inc0.get("ebitda") or 0
        net_income = inc0.get("netIncome") or 0
        price = profile.get("price") or 0
        fcf_proxy = inc0.get("operatingCashFlow") or 0

        return {
            "ticker": ticker,
            "name": profile.get("companyName", ticker),
            "market_cap": market_cap,
            "ev": ev,
            "revenue": revenue,
            "ebitda": ebitda,
            "net_income": net_income,
            "price": price,
            "ev_revenue": round(ev / revenue, 2) if revenue > 0 else None,
            "ev_ebitda": round(ev / ebitda, 2) if ebitda > 0 else None,
            "pe": round(market_cap / net_income, 2) if net_income > 0 else None,
            "p_fcf": round(market_cap / fcf_proxy, 2) if fcf_proxy > 0 else None,
        }
    except Exception:
        return None


def build_comps_table(ticker: str, max_peers: int = 6, custom_peers: list = None) -> dict:
    """
    Returns comps table for target + peers, plus median multiples
    and implied valuation range from those medians.
    Fetches all peers in parallel for speed.
    """
    peers = custom_peers if custom_peers is not None else get_peers(ticker)[:max_peers]
    all_tickers = [ticker] + [p for p in peers if p != ticker]

    # Fetch all tickers in parallel
    rows = []
    with ThreadPoolExecutor(max_workers=min(len(all_tickers), 8)) as ex:
        future_to_ticker = {ex.submit(_get_multiples, t): t for t in all_tickers}
        for future in as_completed(future_to_ticker):
            m = future.result()
            if m:
                m["is_target"] = (future_to_ticker[future] == ticker)
                rows.append(m)

    if not rows:
        return {"rows": [], "medians": {}, "implied_prices": {}}

    # Keep target first, then peers alphabetically
    rows.sort(key=lambda r: (not r["is_target"], r["ticker"]))

    target = next((r for r in rows if r["is_target"]), None)
    peers_rows = [r for r in rows if not r["is_target"]]

    def _median(key):
        vals = [r[key] for r in peers_rows if r.get(key) is not None]
        return round(float(np.median(vals)), 2) if vals else None

    medians = {
        "ev_revenue": _median("ev_revenue"),
        "ev_ebitda": _median("ev_ebitda"),
        "pe": _median("pe"),
        "p_fcf": _median("p_fcf"),
    }

    implied = {}
    if target:
        shares = target["market_cap"] / target["price"] if target["price"] > 0 else 1
        net_debt = target["ev"] - target["market_cap"]
        if medians["ev_revenue"] and target["revenue"]:
            implied["ev_revenue"] = round(
                (medians["ev_revenue"] * target["revenue"] - net_debt) / shares, 2)
        if medians["ev_ebitda"] and target["ebitda"]:
            implied["ev_ebitda"] = round(
                (medians["ev_ebitda"] * target["ebitda"] - net_debt) / shares, 2)
        if medians["pe"] and target["net_income"]:
            implied["pe"] = round(medians["pe"] * target["net_income"] / shares, 2)

    return {"rows": rows, "medians": medians, "implied_prices": implied}
