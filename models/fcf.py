import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from data.fetcher import get_cash_flow, get_income_statement


def compute_historical_fcf(ticker: str, years: int = 5) -> list:
    """
    Returns list of dicts [{year, revenue, ebitda, operating_cf, capex, fcf}]
    sorted oldest → newest.
    """
    cf_data = get_cash_flow(ticker, years)
    inc_data = get_income_statement(ticker, years)

    inc_by_year = {r["fiscalYear"]: r for r in inc_data}

    rows = []
    for cf in cf_data:
        fy = cf["fiscalYear"]
        inc = inc_by_year.get(fy, {})
        operating_cf = cf.get("operatingCashFlow", 0) or 0
        capex = abs(cf.get("capitalExpenditure", 0) or 0)
        fcf = operating_cf - capex
        rows.append({
            "year": fy,
            "revenue": inc.get("revenue", 0) or 0,
            "ebitda": inc.get("ebitda", 0) or 0,
            "operating_cf": operating_cf,
            "capex": capex,
            "fcf": fcf,
        })

    rows.sort(key=lambda r: r["year"])
    return rows


def normalized_base_fcf(historical: list) -> float:
    """3-year average FCF as base for projections."""
    recent = [r["fcf"] for r in historical[-3:] if r["fcf"] != 0]
    return float(np.mean(recent)) if recent else 0.0


def project_fcf(base_fcf: float, growth_rates: list) -> list:
    """
    Project FCF for each year given a list of annual growth rates.
    Returns list of projected FCF values.
    """
    projected = []
    fcf = base_fcf
    for g in growth_rates:
        fcf = fcf * (1 + g)
        projected.append(fcf)
    return projected
