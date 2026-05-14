import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from models.dcf import run_dcf


def wacc_growth_sensitivity(
    ticker: str,
    base_wacc: float,
    base_growth: float,
    wacc_range: tuple = (-0.02, 0.02),
    growth_range: tuple = (-0.01, 0.02),
    steps: int = 5,
    growth_rates: list = None,
) -> dict:
    """
    2D sensitivity: rows = WACC variants, cols = terminal growth rate variants.
    Returns: {
        waccs: [...],
        growths: [...],
        prices: [[...], ...],   # rows=wacc, cols=growth
    }
    """
    waccs = np.linspace(base_wacc + wacc_range[0], base_wacc + wacc_range[1], steps)
    growths = np.linspace(base_growth + growth_range[0], base_growth + growth_range[1], steps)

    prices = []
    for w in waccs:
        row = []
        for g in growths:
            if w <= g:
                row.append(None)
                continue
            result = run_dcf(
                ticker,
                revenue_growth_rates=growth_rates,
                terminal_growth_rate=float(g),
                wacc_override=float(w),
            )
            row.append(round(result["intrinsic_price"], 2))
        prices.append(row)

    return {
        "waccs": [round(w * 100, 2) for w in waccs],
        "growths": [round(g * 100, 2) for g in growths],
        "prices": prices,
    }


def scenario_analysis(ticker: str, base_result: dict) -> dict:
    """Bear / Base / Bull scenarios via growth rate adjustment."""
    base_rates = base_result["growth_rates"]
    wacc = base_result["wacc"]
    tg = base_result["terminal_growth_rate"]

    bear_rates = [max(r * 0.5, 0.0) for r in base_rates]
    bull_rates = [min(r * 1.5, 0.35) for r in base_rates]

    bear = run_dcf(ticker, bear_rates, tg * 0.8, wacc * 1.05)
    base = base_result
    bull = run_dcf(ticker, bull_rates, tg * 1.2, wacc * 0.95)

    return {
        "bear": {"label": "Bear", "price": bear["intrinsic_price"], "growth_rates": bear_rates},
        "base": {"label": "Base", "price": base["intrinsic_price"], "growth_rates": base_rates},
        "bull": {"label": "Bull", "price": bull["intrinsic_price"], "growth_rates": bull_rates},
    }
