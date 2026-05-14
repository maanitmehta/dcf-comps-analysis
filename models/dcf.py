import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import PROJECTION_YEARS
from models.fcf import compute_historical_fcf, normalized_base_fcf, project_fcf
from models.wacc import compute_wacc


def run_dcf(
    ticker: str,
    revenue_growth_rates: list = None,
    terminal_growth_rate: float = 0.025,
    wacc_override: float = None,
    rfr_override: float = None,
    erp_override: float = None,
    beta_override: float = None,
) -> dict:
    """
    Full DCF model. Returns intrinsic value per share and all intermediate steps.

    Args:
        ticker:               Stock symbol
        revenue_growth_rates: List of annual FCF growth rates for projection period.
                              Defaults to trailing 3-yr avg revenue CAGR.
        terminal_growth_rate: Perpetuity growth rate (g) for terminal value.
        wacc_override:        Override computed WACC (float, e.g. 0.09 for 9%).
    """
    historical = compute_historical_fcf(ticker, min(PROJECTION_YEARS + 1, 5))
    base_fcf = normalized_base_fcf(historical)

    if revenue_growth_rates is None:
        revenue_growth_rates = _estimate_growth(historical)

    wacc_data = compute_wacc(ticker, risk_free_rate=rfr_override,
                              erp_override=erp_override, beta_override=beta_override)
    wacc = wacc_override if wacc_override is not None else wacc_data["wacc"]

    projected_fcfs = project_fcf(base_fcf, revenue_growth_rates)

    pv_fcfs = [
        fcf / (1 + wacc) ** (i + 1)
        for i, fcf in enumerate(projected_fcfs)
    ]

    terminal_fcf = projected_fcfs[-1] * (1 + terminal_growth_rate)
    if wacc <= terminal_growth_rate:
        terminal_value = 0.0
    else:
        terminal_value = terminal_fcf / (wacc - terminal_growth_rate)

    pv_terminal = terminal_value / (1 + wacc) ** PROJECTION_YEARS

    enterprise_value = sum(pv_fcfs) + pv_terminal
    equity_value = enterprise_value - wacc_data["net_debt"]
    shares = wacc_data["shares_outstanding"] or 1
    intrinsic_price = equity_value / shares

    years = list(range(
        _last_historical_year(historical) + 1,
        _last_historical_year(historical) + 1 + PROJECTION_YEARS
    ))

    return {
        "ticker": ticker,
        "intrinsic_price": intrinsic_price,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "pv_fcfs": pv_fcfs,
        "projected_fcfs": projected_fcfs,
        "pv_terminal": pv_terminal,
        "terminal_value": terminal_value,
        "wacc": wacc,
        "terminal_growth_rate": terminal_growth_rate,
        "base_fcf": base_fcf,
        "historical": historical,
        "projection_years": years,
        "wacc_data": wacc_data,
        "growth_rates": revenue_growth_rates,
    }


def _estimate_growth(historical: list) -> list:
    """Estimate forward growth from trailing revenue CAGR, tapering to conservatism."""
    revenues = [r["revenue"] for r in historical if r["revenue"] > 0]
    if len(revenues) >= 2:
        cagr = (revenues[-1] / revenues[0]) ** (1 / (len(revenues) - 1)) - 1
    else:
        cagr = 0.05
    cagr = min(max(cagr, 0.0), 0.30)
    taper = cagr * 0.85
    return [cagr, cagr, taper, taper, taper * 0.85]


def _last_historical_year(historical: list) -> int:
    if historical:
        return int(historical[-1]["year"])
    import datetime
    return datetime.datetime.now().year - 1
