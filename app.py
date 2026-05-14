import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import json
import io
import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import pandas as pd

from data.fetcher import validate_ticker, get_company_profile
from models.dcf import run_dcf
from models.sensitivity import wacc_growth_sensitivity, scenario_analysis
from models.comps import build_comps_table
from dashboard.charts import (
    make_fcf_waterfall, make_sensitivity_heatmap,
    make_football_field, make_comps_table,
)

DARK_BG = "#1a1a2e"
CARD_BG = "#16213e"
TEXT = "#e0e0e0"
GREEN = "#00d4aa"
RED = "#e94560"

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.SLATE],
    title="DCF & Comps Valuation Tool",
)
server = app.server

# ── Layout ────────────────────────────────────────────────────────────────────

def card(title, children, id=None):
    kwargs = {"id": id} if id else {}
    return dbc.Card([
        dbc.CardHeader(title, style={"color": GREEN, "fontWeight": "600", "fontSize": "13px"}),
        dbc.CardBody(children),
    ], style={"backgroundColor": CARD_BG, "border": f"1px solid #2a2a4a"}, className="mb-3", **kwargs)


app.layout = dbc.Container([
    # ── Header ──
    dbc.Row([
        dbc.Col([
            html.H3("DCF & Comparable Company Analysis", style={"color": GREEN, "marginBottom": "2px"}),
            html.Small("Intrinsic Valuation · Sensitivity Analysis · Trading Comps",
                       style={"color": TEXT, "opacity": "0.6"}),
        ], width=8),
        dbc.Col([
            dbc.Button("Export Excel", id="btn-export", color="success", size="sm",
                       outline=True, className="float-end"),
            dcc.Download(id="download-excel"),
        ], width=4, className="d-flex align-items-center justify-content-end"),
    ], className="mb-3 mt-3"),

    # ── Controls ──
    dbc.Row([
        dbc.Col([
            dbc.InputGroup([
                dbc.Input(id="ticker-input", placeholder="Enter ticker (e.g. AAPL)", type="text",
                          value="AAPL", debounce=False,
                          style={"backgroundColor": CARD_BG, "color": TEXT, "border": "1px solid #2a2a4a"}),
                dbc.Button("Analyse", id="btn-run", color="success", n_clicks=0),
            ]),
            html.Small(id="ticker-status", style={"color": TEXT, "opacity": "0.7", "marginTop": "4px"}),
        ], md=4),

        dbc.Col([
            html.Label("FCF Growth (Base, %)", style={"color": TEXT, "fontSize": "12px"}),
            dcc.Slider(id="growth-slider", min=2, max=25, step=1, value=10,
                       marks={i: f"{i}%" for i in [2, 5, 10, 15, 20, 25]},
                       tooltip={"placement": "top"}),
        ], md=4),

        dbc.Col([
            html.Label("Terminal Growth Rate (%)", style={"color": TEXT, "fontSize": "12px"}),
            dcc.Slider(id="tgr-slider", min=1, max=4, step=0.5, value=2.5,
                       marks={i: f"{i}%" for i in [1, 2, 3, 4]},
                       tooltip={"placement": "top"}),
        ], md=4),
    ], className="mb-3"),

    # ── KPI strip ──
    html.Div(id="kpi-strip", className="mb-3"),

    # ── Tabs ──
    dbc.Tabs([
        dbc.Tab(label="DCF Model", tab_id="tab-dcf"),
        dbc.Tab(label="Sensitivity", tab_id="tab-sens"),
        dbc.Tab(label="Comps", tab_id="tab-comps"),
        dbc.Tab(label="Football Field", tab_id="tab-ff"),
    ], id="tabs", active_tab="tab-dcf", className="mb-3"),

    html.Div(id="tab-content"),

    dcc.Store(id="store-results"),
    dcc.Loading(id="loading", type="circle", color=GREEN,
                children=html.Div(id="loading-output")),
], fluid=True, style={"backgroundColor": DARK_BG, "minHeight": "100vh", "padding": "20px"})


# ── Callbacks ─────────────────────────────────────────────────────────────────

@app.callback(
    Output("ticker-status", "children"),
    Output("ticker-status", "style"),
    Input("ticker-input", "value"),
)
def validate(ticker):
    if not ticker or len(ticker) < 1:
        return "", {}
    t = ticker.strip().upper()
    if validate_ticker(t):
        return f"✓ {t} recognised", {"color": GREEN, "fontSize": "12px"}
    return f"✗ {t} not found", {"color": RED, "fontSize": "12px"}


@app.callback(
    Output("store-results", "data"),
    Output("loading-output", "children"),
    Input("btn-run", "n_clicks"),
    State("ticker-input", "value"),
    State("growth-slider", "value"),
    State("tgr-slider", "value"),
    prevent_initial_call=False,
)
def run_analysis(n_clicks, ticker, growth_pct, tgr_pct):
    ticker = (ticker or "AAPL").strip().upper()
    growth = growth_pct / 100
    tgr = tgr_pct / 100
    growth_rates = [growth, growth, growth * 0.85, growth * 0.85, growth * 0.70]

    dcf = run_dcf(ticker, revenue_growth_rates=growth_rates, terminal_growth_rate=tgr)
    scenarios = scenario_analysis(ticker, dcf)
    sens = wacc_growth_sensitivity(ticker, dcf["wacc"], tgr, steps=5, growth_rates=growth_rates)
    comps = build_comps_table(ticker, max_peers=6)
    profile = get_company_profile(ticker)

    payload = {
        "ticker": ticker,
        "dcf": {
            "intrinsic_price": dcf["intrinsic_price"],
            "enterprise_value": dcf["enterprise_value"],
            "wacc": dcf["wacc"],
            "base_fcf": dcf["base_fcf"],
            "terminal_growth_rate": dcf["terminal_growth_rate"],
            "historical": dcf["historical"],
            "projected_fcfs": dcf["projected_fcfs"],
            "projection_years": dcf["projection_years"],
            "wacc_data": dcf["wacc_data"],
        },
        "scenarios": scenarios,
        "sens": sens,
        "comps": comps,
        "current_price": profile.get("price", 0),
        "company_name": profile.get("companyName", ticker),
        "sector": profile.get("industry", ""),
    }
    return json.dumps(payload), ""


@app.callback(
    Output("kpi-strip", "children"),
    Input("store-results", "data"),
)
def update_kpis(data):
    if not data:
        return ""
    d = json.loads(data)
    dcf = d["dcf"]
    price = d["current_price"]
    intrinsic = dcf["intrinsic_price"]
    updown = ((intrinsic - price) / price * 100) if price else 0
    color = GREEN if updown >= 0 else RED

    def kpi(label, value, color=TEXT):
        return dbc.Col(dbc.Card([
            dbc.CardBody([
                html.Div(label, style={"color": TEXT, "opacity": "0.6", "fontSize": "11px"}),
                html.Div(value, style={"color": color, "fontWeight": "700", "fontSize": "20px"}),
            ], style={"padding": "12px"})
        ], style={"backgroundColor": CARD_BG, "border": "1px solid #2a2a4a"}), md=2)

    return dbc.Row([
        kpi("Company", d["company_name"][:18], TEXT),
        kpi("Market Price", f"${price:.2f}"),
        kpi("Intrinsic (DCF)", f"${intrinsic:.2f}", color),
        kpi("Upside / Downside", f"{updown:+.1f}%", color),
        kpi("WACC", f"{dcf['wacc']:.2%}"),
        kpi("Enterprise Value", f"${dcf['enterprise_value']/1e9:.1f}B"),
    ])


@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
    Input("store-results", "data"),
)
def render_tab(active_tab, data):
    if not data:
        return html.P("Enter a ticker and click Analyse.", style={"color": TEXT, "opacity": "0.5"})
    d = json.loads(data)
    dcf = d["dcf"]
    price = d["current_price"]

    if active_tab == "tab-dcf":
        fig_fcf = make_fcf_waterfall(dcf["historical"], dcf["projected_fcfs"], dcf["projection_years"])
        wacc_d = dcf["wacc_data"]
        return [
            dbc.Row([
                dbc.Col(card("Free Cash Flow Bridge",
                             dcc.Graph(figure=fig_fcf, config={"displayModeBar": False})), md=8),
                dbc.Col(card("WACC Breakdown", [
                    _wacc_table(wacc_d),
                ]), md=4),
            ]),
            dbc.Row([
                dbc.Col(card("Scenario Analysis", _scenario_table(d["scenarios"])), md=6),
                dbc.Col(card("DCF Assumptions", _assumptions_table(dcf)), md=6),
            ]),
        ]

    elif active_tab == "tab-sens":
        sens = d["sens"]
        fig = make_sensitivity_heatmap(sens["waccs"], sens["growths"], sens["prices"], price)
        return card("WACC × Terminal Growth Rate Sensitivity (Intrinsic Price)",
                    dcc.Graph(figure=fig, config={"displayModeBar": False}))

    elif active_tab == "tab-comps":
        comps = d["comps"]
        fig = make_comps_table(comps["rows"], comps["medians"])
        return [
            card("Trading Comps Table", dcc.Graph(figure=fig, config={"displayModeBar": False})),
            card("Implied Prices from Comps Medians", _implied_table(comps["implied_prices"], price)),
        ]

    elif active_tab == "tab-ff":
        fig = make_football_field(d["scenarios"], d["comps"]["implied_prices"], price)
        return card("Football Field — Valuation Range",
                    dcc.Graph(figure=fig, config={"displayModeBar": False},
                              style={"height": "350px"}))

    return ""


@app.callback(
    Output("download-excel", "data"),
    Input("btn-export", "n_clicks"),
    State("store-results", "data"),
    prevent_initial_call=True,
)
def export_excel(n, data):
    if not data:
        return
    d = json.loads(data)
    ticker = d["ticker"]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        hist_df = pd.DataFrame(d["dcf"]["historical"])
        hist_df.to_excel(writer, sheet_name="Historical FCF", index=False)

        proj_df = pd.DataFrame({
            "Year": d["dcf"]["projection_years"],
            "Projected FCF": d["dcf"]["projected_fcfs"],
        })
        proj_df.to_excel(writer, sheet_name="DCF Projection", index=False)

        sens = d["sens"]
        sens_df = pd.DataFrame(sens["prices"],
                               index=[f"WACC {w}%" for w in sens["waccs"]],
                               columns=[f"g {g}%" for g in sens["growths"]])
        sens_df.to_excel(writer, sheet_name="Sensitivity")

        if d["comps"]["rows"]:
            comps_df = pd.DataFrame(d["comps"]["rows"])
            comps_df.to_excel(writer, sheet_name="Comps", index=False)

    buf.seek(0)
    return dcc.send_bytes(buf.read(), filename=f"{ticker}_valuation.xlsx")


# ── Helper tables ──────────────────────────────────────────────────────────────

def _wacc_table(w: dict):
    rows = [
        ("Risk-Free Rate", f"{w['risk_free_rate']:.2%}"),
        ("Beta", f"{w['beta']:.2f}"),
        ("Cost of Equity", f"{w['cost_of_equity']:.2%}"),
        ("Cost of Debt", f"{w['cost_of_debt']:.2%}"),
        ("Tax Rate", f"{w['tax_rate']:.2%}"),
        ("Weight Equity", f"{w['weight_equity']:.1%}"),
        ("Weight Debt", f"{w['weight_debt']:.1%}"),
        ("WACC", f"{w['wacc']:.2%}"),
    ]
    return html.Table([
        html.Tbody([
            html.Tr([
                html.Td(k, style={"color": TEXT, "opacity": "0.7", "fontSize": "12px", "paddingRight": "16px"}),
                html.Td(v, style={"color": GREEN, "fontWeight": "600", "fontSize": "12px"}),
            ]) for k, v in rows
        ])
    ], style={"width": "100%"})


def _scenario_table(scenarios: dict):
    rows = [(v["label"], f"${v['price']:.2f}") for v in scenarios.values()]
    colors = [TEXT, GREEN, "#5bc0de"]
    return html.Table([
        html.Tbody([
            html.Tr([
                html.Td(label, style={"color": TEXT, "fontSize": "13px", "paddingRight": "20px"}),
                html.Td(price, style={"color": c, "fontWeight": "700", "fontSize": "16px"}),
            ]) for (label, price), c in zip(rows, colors)
        ])
    ], style={"width": "100%"})


def _assumptions_table(dcf: dict):
    rows = [
        ("Projection Years", "5"),
        ("Base FCF", f"${dcf['base_fcf']/1e9:.1f}B"),
        ("Terminal Growth Rate", f"{dcf['terminal_growth_rate']:.2%}"),
        ("Net Debt", f"${dcf['wacc_data']['net_debt']/1e9:.1f}B"),
    ]
    return html.Table([
        html.Tbody([
            html.Tr([
                html.Td(k, style={"color": TEXT, "opacity": "0.7", "fontSize": "12px", "paddingRight": "16px"}),
                html.Td(v, style={"color": TEXT, "fontSize": "12px"}),
            ]) for k, v in rows
        ])
    ], style={"width": "100%"})


def _implied_table(implied: dict, market_price: float):
    if not implied:
        return html.P("No comps implied prices available.", style={"color": TEXT, "opacity": "0.5"})
    rows = []
    for method, price in implied.items():
        updown = (price - market_price) / market_price * 100 if market_price else 0
        color = GREEN if updown >= 0 else RED
        rows.append(html.Tr([
            html.Td(method.upper().replace("_", "/"),
                    style={"color": TEXT, "fontSize": "12px", "paddingRight": "20px"}),
            html.Td(f"${price:.2f}", style={"color": TEXT, "fontWeight": "600"}),
            html.Td(f"{updown:+.1f}%", style={"color": color, "fontWeight": "600"}),
        ]))
    return html.Table([html.Tbody(rows)], style={"width": "100%"})


if __name__ == "__main__":
    app.run(debug=True, port=8051)
