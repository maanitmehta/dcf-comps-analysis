# DCF & Comparable Company Analysis Tool

An automated valuation tool that pulls live financial data, runs a full Discounted Cash Flow model, performs sensitivity analysis across WACC and growth assumptions, and benchmarks against comparable company trading multiples — all in an interactive dashboard.

**Live demo: [dcf-comps-analysis.onrender.com](https://dcf-comps-analysis.onrender.com)**

> First load may take ~30 seconds if the server has spun down (free tier).

---

## Features

- **Live Financial Data** — Income statement, balance sheet, and cash flow pulled from the Financial Modeling Prep API with a 24-hour local cache
- **DCF Model** — 5-year FCF projection with CAPM-based WACC and Gordon Growth terminal value
- **Sensitivity Analysis** — 2D heatmap across WACC (±200bps) and terminal growth rate, click any cell to drill into the full model for that assumption pair
- **Scenario Analysis** — Bear, Base, and Bull cases via growth rate adjustment
- **Comparable Company Analysis** — EV/EBITDA, EV/Revenue, P/E, and P/FCF multiples across peer universe with median-implied prices and custom peer editing
- **Football Field Chart** — Unified valuation range across all methods vs current market price
- **Historical Valuation** — 1-year price chart vs DCF intrinsic bands, coloured green (undervalued) / red (overvalued)
- **Multi-Ticker Comparison** — Run DCF on up to 3 tickers in parallel with side-by-side charts
- **Real-Time Price Streaming** — Auto-refreshes market price every 60 seconds during NYSE hours with a live LIVE/CLOSED badge and intraday change
- **Assumption Sidebar** — Override risk-free rate (with FRED sync), ERP, beta, and growth assumptions without touching code
- **Dark / Light Mode** — Full theme toggle
- **PDF & Excel Export** — One-click export of the full valuation summary

---

## Dashboard

| Tab | Content |
|---|---|
| **DCF Model** | FCF waterfall (historical + projected), WACC decomposition chart, scenario prices, model assumptions |
| **Sensitivity** | Interactive WACC × terminal growth heatmap — click any cell to drill into that scenario |
| **Comps** | Trading multiples table + implied prices from peer medians + custom peer universe editor |
| **Football Field** | Valuation range summary across all methods with hover detail |
| **Historical** | 1-year price vs Bear/Base/Bull DCF bands — green when undervalued, red when overvalued |
| **Compare** | Side-by-side DCF for up to 3 tickers — market vs intrinsic, upside bars, metrics table |

---

## Methodology

### WACC
```
Cost of Equity  = Rf + β × ERP          (CAPM)
Cost of Debt    = Interest Expense / Total Debt
WACC            = (E/V) × Ke + (D/V) × Kd × (1 − t)
```
- Risk-free rate pulled live from FRED (10Y US Treasury)
- Equity Risk Premium: 5.5% (Damodaran)
- Beta sourced from FMP company profile (manual override available)

### DCF
```
FCF Base         = 3-year normalised average Free Cash Flow
Projected FCFs   = FCF Base × ∏(1 + gᵢ)  for i = 1..5
Terminal Value   = FCF₅ × (1 + g) / (WACC − g)
Enterprise Value = Σ PV(FCFs) + PV(Terminal Value)
Equity Value     = Enterprise Value − Net Debt
Intrinsic Price  = Equity Value / Shares Outstanding
```

### Comparable Company Analysis
Peer universe sourced from FMP. For each peer and the target:
- **EV/Revenue** = Enterprise Value / Revenue
- **EV/EBITDA** = Enterprise Value / EBITDA
- **P/E** = Market Cap / Net Income
- **P/FCF** = Market Cap / Operating Cash Flow

Implied price = Median peer multiple × Target metric − Net Debt, divided by shares.

---

## Example Output — AAPL

```
WACC:             10.06%
Base FCF:         $102.4B  (3yr normalised)
Enterprise Value: $1,413.8B
Intrinsic Price:  $92.33   (DCF base case)

Bear:  $77.28
Base:  $92.33
Bull:  $112.29

Comps implied:
  EV/Revenue:  $303.79
  EV/EBITDA:   $183.89
```

> Note: AAPL's DCF base case sits below market price (~$298) — this is expected. AAPL trades on growth optionality and buyback yield that a pure FCF-based DCF undervalues. The comps-implied range ($184–$304) is closer to market, which is the correct analytical framing for advisory discussions.

---

## Project Structure

```
dcf_tool/
├── app.py                  # Dash app — layout, all callbacks, PDF/Excel export
├── config.py               # Constants: FMP URL, WACC defaults, cache TTL
│
├── data/
│   └── fetcher.py          # FMP API calls, FRED risk-free rate, historical prices,
│                             live price streaming, local JSON cache (24hr TTL)
│
├── models/
│   ├── fcf.py              # Historical FCF, 3yr normalised base, projections
│   ├── wacc.py             # CAPM cost of equity, cost of debt, capital structure
│   ├── dcf.py              # 5yr projection + terminal value + equity bridge
│   ├── sensitivity.py      # Parallel 2D sensitivity grid + Bear/Base/Bull scenarios
│   └── comps.py            # Parallel peer multiples + implied valuation
│
├── dashboard/
│   └── charts.py           # All Plotly figures: waterfall, heatmap, football field,
│                             WACC decomp, historical valuation, comparison charts
│
├── tests/
├── requirements.txt
└── Procfile                # gunicorn app:server
```

---

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/maanitmehta/dcf-comps-analysis.git
cd dcf-comps-analysis
```

**2. Create a virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**3. Add your API key**

Create a `.env` file in the project root:
```
FMP_API_KEY=your_key_here
```

Get a free key (250 calls/day) at [financialmodelingprep.com](https://financialmodelingprep.com/developer/docs).

**4. Run**
```bash
python3 app.py
```

Open `http://localhost:8051` in your browser.

---

## API & Data Sources

| Source | Data | Auth |
|---|---|---|
| [Financial Modeling Prep](https://financialmodelingprep.com) | Income statement, balance sheet, cash flow, company profile, peers, historical prices, live quote | API key (free tier) |
| [FRED](https://fred.stlouisfed.org) | 10Y US Treasury yield (risk-free rate) | None |

API responses are cached locally as JSON for 24 hours. Live price streaming bypasses cache and hits the quote endpoint directly every 60 seconds during market hours.

---

## Dependencies

```
dash>=2.17.1
dash-bootstrap-components>=1.6.0
plotly>=5.22.0
pandas>=2.0.0
numpy>=1.24.0
requests>=2.31.0
python-dotenv>=1.0.0
openpyxl>=3.1.0
gunicorn>=22.0.0
reportlab>=4.0.0
```

---

## Limitations

- Free FMP tier caps financial statement history at 5 years and live quote data at 250 calls/day
- DCF is sensitive to terminal growth rate and WACC assumptions — use the sensitivity tab to stress-test
- Peer universe is sourced automatically from FMP; use the custom peer editor in the Comps tab for precision
- Historical valuation chart uses the current DCF intrinsic as a static reference, not a rolling historical DCF
