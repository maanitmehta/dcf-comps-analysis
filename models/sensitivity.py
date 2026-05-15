import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from concurrent.futures import ThreadPoolExecutor
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
    waccs = np.linspace(base_wacc + wacc_range[0], base_wacc + wacc_range[1], steps)
    growths = np.linspace(base_growth + growth_range[0], base_growth + growth_range[1], steps)

    # Build all (wacc, growth) pairs, skip invalid ones
    pairs = [
        (float(w), float(g))
        for w in waccs for g in growths
        if w > g
    ]

    def _one(wg):
        w, g = wg
        result = run_dcf(ticker, revenue_growth_rates=growth_rates,
                         terminal_growth_rate=g, wacc_override=w)
        return w, g, round(result["intrinsic_price"], 2)

    # Run all cells in parallel (data is cached after the initial DCF run)
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(pairs), 12)) as ex:
        for w, g, price in ex.map(_one, pairs):
            results[(w, g)] = price

    prices = [
        [results.get((float(w), float(g)), None) for g in growths]
        for w in waccs
    ]

    return {
        "waccs":   [round(w * 100, 2) for w in waccs],
        "growths": [round(g * 100, 2) for g in growths],
        "prices":  prices,
    }


def scenario_analysis(ticker: str, base_result: dict) -> dict:
    base_rates = base_result["growth_rates"]
    wacc = base_result["wacc"]
    tg = base_result["terminal_growth_rate"]

    bear_rates = [max(r * 0.5, 0.0) for r in base_rates]
    bull_rates = [min(r * 1.5, 0.35) for r in base_rates]

    def _bear():
        return run_dcf(ticker, bear_rates, tg * 0.8, wacc * 1.05)

    def _bull():
        return run_dcf(ticker, bull_rates, tg * 1.2, wacc * 0.95)

    # Bear and Bull run in parallel
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_bear = ex.submit(_bear)
        f_bull = ex.submit(_bull)
        bear = f_bear.result()
        bull = f_bull.result()

    return {
        "bear": {"label": "Bear", "price": bear["intrinsic_price"], "growth_rates": bear_rates},
        "base": {"label": "Base", "price": base_result["intrinsic_price"], "growth_rates": base_rates},
        "bull": {"label": "Bull", "price": bull["intrinsic_price"], "growth_rates": bull_rates},
    }
