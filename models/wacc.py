import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import EQUITY_RISK_PREMIUM, TAX_RATE_DEFAULT
from data.fetcher import get_company_profile, get_balance_sheet, get_income_statement, get_risk_free_rate


def compute_wacc(ticker: str, risk_free_rate: float = None) -> dict:
    """
    Returns WACC components and final WACC as a dict.

    Cost of Equity  = Rf + Beta × ERP          (CAPM)
    Cost of Debt    = Interest Expense / Total Debt
    WACC            = (E/V) × Ke + (D/V) × Kd × (1 − t)
    """
    rfr = risk_free_rate if risk_free_rate is not None else get_risk_free_rate()

    profile = get_company_profile(ticker)
    beta = profile.get("beta") or 1.0

    bs = get_balance_sheet(ticker, 1)[0]
    inc = get_income_statement(ticker, 1)[0]

    total_debt = (bs.get("totalDebt") or 0)
    cash = (bs.get("cashAndCashEquivalents") or 0) + (bs.get("shortTermInvestments") or 0)
    market_cap = profile.get("marketCap") or 0
    price = profile.get("price") or 1
    shares = market_cap / price if price > 0 else 1

    interest_expense = abs(inc.get("interestExpense") or 0)
    income_tax = abs(inc.get("incomeTaxExpense") or 0)
    pretax_income = inc.get("incomeBeforeTax") or 1
    tax_rate = income_tax / pretax_income if pretax_income > 0 else TAX_RATE_DEFAULT
    tax_rate = min(max(tax_rate, 0.05), 0.40)

    cost_of_equity = rfr + beta * EQUITY_RISK_PREMIUM

    cost_of_debt = (interest_expense / total_debt) if total_debt > 0 else rfr
    cost_of_debt = min(cost_of_debt, 0.20)

    total_capital = market_cap + total_debt
    weight_equity = market_cap / total_capital if total_capital > 0 else 0.8
    weight_debt = total_debt / total_capital if total_capital > 0 else 0.2

    wacc = weight_equity * cost_of_equity + weight_debt * cost_of_debt * (1 - tax_rate)

    return {
        "wacc": wacc,
        "cost_of_equity": cost_of_equity,
        "cost_of_debt": cost_of_debt,
        "tax_rate": tax_rate,
        "beta": beta,
        "risk_free_rate": rfr,
        "weight_equity": weight_equity,
        "weight_debt": weight_debt,
        "market_cap": market_cap,
        "total_debt": total_debt,
        "net_debt": total_debt - cash,
        "shares_outstanding": shares,
    }
