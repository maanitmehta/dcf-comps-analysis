import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import json
import io
import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update
import dash_bootstrap_components as dbc
import pandas as pd

import threading
from concurrent.futures import ThreadPoolExecutor
from data.fetcher import (validate_ticker, get_company_profile, get_risk_free_rate,
                           get_live_price, is_market_open, get_historical_prices,
                           get_income_statement, get_balance_sheet, get_cash_flow, get_peers)
from models.dcf import run_dcf
from models.sensitivity import wacc_growth_sensitivity, scenario_analysis
from models.comps import build_comps_table
from dashboard.charts import (
    make_fcf_waterfall, make_sensitivity_heatmap, make_football_field,
    make_comps_table, make_wacc_decomp,
    make_historical_valuation_chart, make_comparison_chart, make_comparison_table,
)

# ── Theme palettes ─────────────────────────────────────────────────────────────

THEMES = {
    "dark":  {"bg": "#1a1a2e", "card": "#16213e", "text": "#e0e0e0",
               "border": "#2a2a4a", "green": "#00d4aa", "red": "#e94560",
               "input_bg": "#16213e", "badge": "#0f3460"},
    "light": {"bg": "#f0f2f5", "card": "#ffffff", "text": "#1a1a2e",
               "border": "#dde1e7", "green": "#0a8a6e", "red": "#c0392b",
               "input_bg": "#ffffff", "badge": "#4a90d9"},
}


def C(key, theme="dark"):
    return THEMES[theme][key]


app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.SLATE],
    title="DCF & Comps Valuation Tool",
    suppress_callback_exceptions=True,
)
server = app.server

def _warm_cache(ticker: str) -> None:
    try:
        get_income_statement(ticker, 5)
        get_balance_sheet(ticker, 5)
        get_cash_flow(ticker, 5)
        get_company_profile(ticker)
        get_peers(ticker)
    except Exception:
        pass

# Pre-fetch the 3 most common tickers in background on server startup
for _t in ["AAPL", "MSFT", "TSLA"]:
    threading.Thread(target=_warm_cache, args=(_t,), daemon=True).start()

# ── Loading overlay CSS ────────────────────────────────────────────────────────

app.index_string = """<!DOCTYPE html>
<html>
<head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
#loading-overlay {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(26,26,46,0.92); z-index: 9999;
    display: none; flex-direction: column;
    align-items: center; justify-content: center;
}
.step-list { list-style: none; padding: 0; margin-top: 20px; }
.step-list li {
    color: #888; font-size: 14px; padding: 6px 0;
    transition: color 0.4s;
}
.step-list li.active { color: #00d4aa; font-weight: 600; }
@keyframes spin {
    0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); }
}
.spinner {
    width: 48px; height: 48px;
    border: 4px solid #2a2a4a;
    border-top-color: #00d4aa;
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
}
@keyframes step-cycle {
    0%,20%  { --s:0; } 21%,40% { --s:1; } 41%,60% { --s:2; } 61%,80% { --s:3; } 81%,100% { --s:4; }
}
@keyframes pulse {
    0%, 100% { opacity: 1; } 50% { opacity: 0.3; }
}
.live-badge {
    display: inline-block;
    background: #e94560;
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 10px;
    letter-spacing: 1px;
    animation: pulse 1.4s ease-in-out infinite;
    vertical-align: middle;
    margin-left: 8px;
}
.closed-badge {
    display: inline-block;
    background: #555;
    color: #ccc;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 10px;
    letter-spacing: 0.5px;
    vertical-align: middle;
    margin-left: 8px;
}
</style>
</head>
<body>{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
<script>
function animateSteps() {
    var steps = document.querySelectorAll('.step-list li');
    var i = 0;
    return setInterval(function() {
        steps.forEach(function(s) { s.classList.remove('active'); });
        if (steps[i]) steps[i].classList.add('active');
        i = (i + 1) % steps.length;
    }, 900);
}
var _stepTimer = null;
var _obs = new MutationObserver(function() {
    var ov = document.getElementById('loading-overlay');
    if (!ov) return;
    if (ov.style.display === 'flex') {
        if (!_stepTimer) _stepTimer = animateSteps();
    } else {
        if (_stepTimer) { clearInterval(_stepTimer); _stepTimer = null; }
        document.querySelectorAll('.step-list li').forEach(function(s) {
            s.classList.remove('active');
        });
    }
});
document.addEventListener('DOMContentLoaded', function() {
    var ov = document.getElementById('loading-overlay');
    if (ov) _obs.observe(ov, { attributes: true, attributeFilter: ['style'] });
});
</script>
</body>
</html>"""

# ── Layout helpers ─────────────────────────────────────────────────────────────

def card(title, children, id=None, theme="dark"):
    c = THEMES[theme]
    kwargs = {"id": id} if id else {}
    return dbc.Card([
        dbc.CardHeader(title, style={"color": c["green"], "fontWeight": "600", "fontSize": "13px",
                                      "backgroundColor": c["card"], "borderColor": c["border"]}),
        dbc.CardBody(children, style={"backgroundColor": c["card"]}),
    ], style={"backgroundColor": c["card"], "border": f"1px solid {c['border']}"}, className="mb-3", **kwargs)


# ── Assumption Sidebar (Offcanvas) ─────────────────────────────────────────────

def assumption_sidebar():
    return dbc.Offcanvas([
        html.P("Override model assumptions. Leave blank to use API-computed values.",
               style={"fontSize": "12px", "opacity": "0.7"}),
        html.Hr(),

        html.Label("Risk-Free Rate (10Y Treasury, %)", className="fw-semibold"),
        dbc.InputGroup([
            dbc.Input(id="input-rfr", type="number", min=0.5, max=8, step=0.1,
                      placeholder="e.g. 4.5"),
            dbc.Button("Sync FRED", id="btn-sync-fred", color="info", size="sm", outline=True),
        ], className="mb-1"),
        html.Small(id="rfr-status", style={"opacity": "0.6", "fontSize": "11px"}),
        html.Hr(),

        html.Label("Equity Risk Premium (%)", className="fw-semibold"),
        dcc.Slider(id="slider-erp", min=3.0, max=8.0, step=0.25, value=5.5,
                   marks={i: f"{i}%" for i in [3, 4, 5, 6, 7, 8]},
                   tooltip={"placement": "bottom"}),
        html.Small("Damodaran Jan 2026 US ERP: 5.5%", style={"opacity": "0.5", "fontSize": "11px"}),
        html.Hr(),

        html.Label("Beta Override", className="fw-semibold"),
        dbc.Switch(id="switch-beta", label="Manual Override", value=False, className="mb-2"),
        dbc.Input(id="input-beta", type="number", min=0.1, max=3.0, step=0.05,
                  placeholder="e.g. 1.2", disabled=True, className="mb-1"),
        html.Hr(),

        html.Label("FCF Growth — Year 1–2 (%)", className="fw-semibold"),
        dcc.Slider(id="sidebar-growth", min=2, max=30, step=1, value=10,
                   marks={i: f"{i}%" for i in [2, 5, 10, 15, 20, 30]},
                   tooltip={"placement": "bottom"}),
        html.Hr(),

        html.Label("Terminal Growth Rate (%)", className="fw-semibold"),
        dcc.Slider(id="sidebar-tgr", min=0.5, max=5.0, step=0.25, value=2.5,
                   marks={i: f"{i}%" for i in [1, 2, 3, 4, 5]},
                   tooltip={"placement": "bottom"}),
        html.Hr(),

        dbc.Button("Apply & Run", id="btn-apply-sidebar", color="success", className="w-100"),
    ],
        id="offcanvas-assumptions",
        title="Assumption Overrides",
        is_open=False,
        placement="start",
        style={"width": "360px", "backgroundColor": "#16213e", "color": "#e0e0e0"},
    )


# ── Main layout ────────────────────────────────────────────────────────────────

app.layout = html.Div([
    # Loading overlay
    html.Div([
        html.Div(className="spinner"),
        html.H5("Running Analysis…", style={"color": "#00d4aa", "marginTop": "20px"}),
        html.Ul([
            html.Li("Fetching financials from FMP", className=""),
            html.Li("Computing WACC (CAPM)", className=""),
            html.Li("Projecting FCF & terminal value", className=""),
            html.Li("Running sensitivity grid", className=""),
            html.Li("Building comparable company table", className=""),
        ], className="step-list"),
    ], id="loading-overlay"),

    assumption_sidebar(),

    # Heatmap drill-down modal
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="drill-modal-title")),
        dbc.ModalBody(id="drill-modal-body"),
        dbc.ModalFooter(dbc.Button("Close", id="btn-close-drill", className="ms-auto")),
    ], id="drill-modal", size="lg", is_open=False),

    dbc.Container([
        # Header row
        dbc.Row([
            dbc.Col([
                html.H3("DCF & Comparable Company Analysis", id="header-title",
                        style={"color": "#00d4aa", "marginBottom": "2px"}),
                html.Small("Intrinsic Valuation · Sensitivity Analysis · Trading Comps",
                           id="header-sub", style={"color": "#e0e0e0", "opacity": "0.6"}),
            ], width=7),
            dbc.Col([
                dbc.Button("⚙ Assumptions", id="btn-open-sidebar", color="secondary",
                           size="sm", outline=True, className="me-2"),
                dbc.Button("☀ Light", id="btn-theme", color="secondary",
                           size="sm", outline=True, className="me-2"),
                dbc.Button("PDF", id="btn-pdf", color="warning",
                           size="sm", outline=True, className="me-2"),
                dbc.Button("Excel", id="btn-export", color="success",
                           size="sm", outline=True),
                dcc.Download(id="download-excel"),
                dcc.Download(id="download-pdf"),
            ], width=5, className="d-flex align-items-center justify-content-end gap-1"),
        ], className="mb-3 mt-3"),

        # Controls
        dbc.Row([
            dbc.Col([
                dbc.InputGroup([
                    dbc.Input(id="ticker-input", placeholder="Ticker (e.g. AAPL)",
                              type="text", value="AAPL", debounce=False),
                    dbc.Button("Analyse", id="btn-run", color="success", n_clicks=0),
                ]),
                html.Small(id="ticker-status", style={"marginTop": "4px", "fontSize": "12px"}),
            ], md=4),
            dbc.Col([
                html.Label("FCF Growth Base (%)", style={"fontSize": "12px"}),
                dcc.Slider(id="growth-slider", min=2, max=25, step=1, value=10,
                           marks={i: f"{i}%" for i in [2, 5, 10, 15, 20, 25]},
                           tooltip={"placement": "top"}),
            ], md=4),
            dbc.Col([
                html.Label("Terminal Growth Rate (%)", style={"fontSize": "12px"}),
                dcc.Slider(id="tgr-slider", min=1, max=4, step=0.5, value=2.5,
                           marks={i: f"{i}%" for i in [1, 2, 3, 4]},
                           tooltip={"placement": "top"}),
            ], md=4),
        ], className="mb-3"),

        # KPI strip
        html.Div(id="kpi-strip", className="mb-3"),

        # Tabs
        dbc.Tabs([
            dbc.Tab(label="DCF Model",      tab_id="tab-dcf"),
            dbc.Tab(label="Sensitivity",    tab_id="tab-sens"),
            dbc.Tab(label="Comps",          tab_id="tab-comps"),
            dbc.Tab(label="Football Field", tab_id="tab-ff"),
            dbc.Tab(label="Historical",     tab_id="tab-hist"),
            dbc.Tab(label="Compare",        tab_id="tab-compare"),
        ], id="tabs", active_tab="tab-dcf", className="mb-3"),

        html.Div(id="tab-content"),

    ], fluid=True, style={"padding": "20px"}, id="main-container"),

    # Stores
    dcc.Store(id="store-results"),
    dcc.Store(id="store-theme", data="dark"),
    dcc.Store(id="store-custom-peers", data=[]),
    dcc.Store(id="store-sidebar-vals", data={}),
    dcc.Store(id="store-live-price", data={}),
    dcc.Store(id="store-comparison", data=[]),

    # Price streaming — fires every 60s, enabled only when a ticker is loaded
    dcc.Interval(id="price-interval", interval=60_000, disabled=True),

], id="page-wrapper", style={"backgroundColor": "#1a1a2e", "minHeight": "100vh"})


# ── Callbacks ─────────────────────────────────────────────────────────────────

# Theme toggle
@app.callback(
    Output("page-wrapper", "style"),
    Output("main-container", "style"),
    Output("btn-theme", "children"),
    Output("store-theme", "data"),
    Input("btn-theme", "n_clicks"),
    State("store-theme", "data"),
    prevent_initial_call=True,
)
def toggle_theme(_, theme):
    new_theme = "light" if theme == "dark" else "dark"
    c = THEMES[new_theme]
    wrapper = {"backgroundColor": c["bg"], "minHeight": "100vh"}
    container = {"padding": "20px", "color": c["text"]}
    label = "🌙 Dark" if new_theme == "light" else "☀ Light"
    return wrapper, container, label, new_theme


# Sidebar open
@app.callback(
    Output("offcanvas-assumptions", "is_open"),
    Input("btn-open-sidebar", "n_clicks"),
    Input("btn-apply-sidebar", "n_clicks"),
    State("offcanvas-assumptions", "is_open"),
    prevent_initial_call=True,
)
def toggle_sidebar(open_clicks, apply_clicks, is_open):
    ctx = callback_context
    if not ctx.triggered:
        return is_open
    trigger = ctx.triggered[0]["prop_id"]
    if trigger == "btn-open-sidebar.n_clicks":
        return not is_open
    return False  # close on Apply


# Beta input enable/disable
@app.callback(
    Output("input-beta", "disabled"),
    Input("switch-beta", "value"),
)
def toggle_beta_input(enabled):
    return not enabled


# Sync FRED rate into the Rf input
@app.callback(
    Output("input-rfr", "value"),
    Output("rfr-status", "children"),
    Input("btn-sync-fred", "n_clicks"),
    prevent_initial_call=True,
)
def sync_fred(_):
    rfr = get_risk_free_rate()
    return round(rfr * 100, 2), f"Synced: {rfr:.2%} (10Y Treasury)"


# Store sidebar values when Apply is clicked
@app.callback(
    Output("store-sidebar-vals", "data"),
    Input("btn-apply-sidebar", "n_clicks"),
    State("input-rfr", "value"),
    State("slider-erp", "value"),
    State("switch-beta", "value"),
    State("input-beta", "value"),
    State("sidebar-growth", "value"),
    State("sidebar-tgr", "value"),
    prevent_initial_call=True,
)
def save_sidebar(_, rfr, erp, beta_manual, beta_val, growth, tgr):
    return {
        "rfr": rfr / 100 if rfr else None,
        "erp": erp / 100 if erp else None,
        "beta": beta_val if beta_manual and beta_val else None,
        "growth": growth,
        "tgr": tgr,
    }


def _prefetch(ticker: str) -> None:
    """Warm the cache for a ticker in a background thread."""
    try:
        get_income_statement(ticker, 5)
        get_balance_sheet(ticker, 5)
        get_cash_flow(ticker, 5)
        get_company_profile(ticker)
        get_peers(ticker)
    except Exception:
        pass


# Ticker validation + background cache warm-up
@app.callback(
    Output("ticker-status", "children"),
    Output("ticker-status", "style"),
    Input("ticker-input", "value"),
    State("store-theme", "data"),
)
def validate(ticker, theme):
    c = THEMES[theme or "dark"]
    if not ticker:
        return "", {}
    t = ticker.strip().upper()
    if validate_ticker(t):
        # Pre-fetch financials in background so Analyse click hits cache
        threading.Thread(target=_prefetch, args=(t,), daemon=True).start()
        return f"✓ {t} recognised", {"color": c["green"], "fontSize": "12px"}
    return f"✗ {t} not found", {"color": c["red"], "fontSize": "12px"}


# Enable price interval when analysis completes
@app.callback(
    Output("price-interval", "disabled"),
    Input("store-results", "data"),
)
def enable_price_stream(data):
    return data is None


# Fetch live price every 60s
@app.callback(
    Output("store-live-price", "data"),
    Input("price-interval", "n_intervals"),
    State("store-results", "data"),
    prevent_initial_call=True,
)
def stream_price(_, data):
    if not data:
        return {}
    ticker = json.loads(data)["ticker"]
    live = get_live_price(ticker)
    live["market_open"] = is_market_open()
    live["ticker"] = ticker
    return live


# Loading overlay — show on run, hide on results
@app.callback(
    Output("loading-overlay", "style"),
    Input("btn-run", "n_clicks"),
    Input("btn-apply-sidebar", "n_clicks"),
    Input("store-results", "data"),
    prevent_initial_call=True,
)
def toggle_loading_overlay(run_clicks, apply_clicks, _data):
    ctx = callback_context
    if not ctx.triggered:
        return {"display": "none"}
    trigger = ctx.triggered[0]["prop_id"]
    if trigger in ("btn-run.n_clicks", "btn-apply-sidebar.n_clicks"):
        return {"display": "flex", "flexDirection": "column",
                "alignItems": "center", "justifyContent": "center"}
    return {"display": "none"}


# Main analysis
@app.callback(
    Output("store-results", "data"),
    Input("btn-run", "n_clicks"),
    Input("btn-apply-sidebar", "n_clicks"),
    State("ticker-input", "value"),
    State("growth-slider", "value"),
    State("tgr-slider", "value"),
    State("store-sidebar-vals", "data"),
    State("store-custom-peers", "data"),
    prevent_initial_call=False,
)
def run_analysis(_, _apply, ticker, growth_pct, tgr_pct, sidebar, custom_peers):
    ticker = (ticker or "AAPL").strip().upper()
    sb = sidebar or {}

    growth = (sb.get("growth") or growth_pct) / 100
    tgr = (sb.get("tgr") or tgr_pct) / 100
    rfr = sb.get("rfr")
    erp = sb.get("erp")
    beta = sb.get("beta")

    growth_rates = [growth, growth, growth * 0.85, growth * 0.85, growth * 0.70]
    peers_arg = custom_peers if custom_peers else None

    # Phase 1 — run_dcf, comps, and profile are independent: fire all three at once
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_dcf     = ex.submit(run_dcf, ticker, growth_rates, tgr, None, rfr, erp, beta)
        f_comps   = ex.submit(build_comps_table, ticker, 6, peers_arg)
        f_profile = ex.submit(get_company_profile, ticker)

    dcf     = f_dcf.result()
    comps   = f_comps.result()
    profile = f_profile.result()

    # Phase 2 — scenarios and sensitivity both depend on dcf: run them in parallel
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_scen = ex.submit(scenario_analysis, ticker, dcf)
        f_sens = ex.submit(wacc_growth_sensitivity, ticker, dcf["wacc"], tgr,
                           steps=5, growth_rates=growth_rates)

    scenarios = f_scen.result()
    sens      = f_sens.result()

    return json.dumps({
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
    })


# KPI strip — updates on both initial results and live price ticks
@app.callback(
    Output("kpi-strip", "children"),
    Input("store-results", "data"),
    Input("store-live-price", "data"),
    State("store-theme", "data"),
)
def update_kpis(data, live, theme):
    if not data:
        return ""
    c = THEMES[theme or "dark"]
    d = json.loads(data)
    dcf = d["dcf"]

    # Use live price if available and for the same ticker, else fall back to snapshot
    live = live or {}
    if live.get("ticker") == d["ticker"] and live.get("price"):
        price = live["price"]
        change = live.get("change", 0)
        change_pct = live.get("change_pct", 0)
        market_open = live.get("market_open", False)
        price_label = [
            f"${price:.2f} ",
            html.Span(f"{change:+.2f} ({change_pct:+.2f}%)",
                      style={"fontSize": "12px",
                             "color": c["green"] if change >= 0 else c["red"]}),
            html.Span("LIVE" if market_open else "CLOSED",
                      className="live-badge" if market_open else "closed-badge"),
        ]
    else:
        price = d["current_price"]
        price_label = f"${price:.2f}"

    intrinsic = dcf["intrinsic_price"]
    updown = ((intrinsic - price) / price * 100) if price else 0
    ud_color = c["green"] if updown >= 0 else c["red"]

    def kpi(label, value, color=None):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(label, style={"color": c["text"], "opacity": "0.6", "fontSize": "11px"}),
            html.Div(value, style={"color": color or c["text"], "fontWeight": "700", "fontSize": "20px"}),
        ], style={"padding": "12px"}),
            style={"backgroundColor": c["card"], "border": f"1px solid {c['border']}"}), md=2)

    return dbc.Row([
        kpi("Company",         d["company_name"][:18]),
        kpi("Market Price",    price_label),
        kpi("Intrinsic (DCF)", f"${intrinsic:.2f}", ud_color),
        kpi("Upside/Downside", f"{updown:+.1f}%",  ud_color),
        kpi("WACC",            f"{dcf['wacc']:.2%}"),
        kpi("Enterprise Value",f"${dcf['enterprise_value']/1e9:.1f}B"),
    ])


# Tab renderer
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
    Input("store-results", "data"),
    State("store-theme", "data"),
    State("store-custom-peers", "data"),
)
def render_tab(active_tab, data, theme, custom_peers):
    dark = (theme or "dark") == "dark"
    c = THEMES["dark" if dark else "light"]

    if not data:
        return html.P("Enter a ticker and click Analyse.",
                      style={"color": c["text"], "opacity": "0.5"})
    d = json.loads(data)
    dcf = d["dcf"]
    price = d["current_price"]
    ticker = d["ticker"]

    if active_tab == "tab-dcf":
        fig_fcf = make_fcf_waterfall(dcf["historical"], dcf["projected_fcfs"],
                                     dcf["projection_years"], dark=dark)
        fig_wacc = make_wacc_decomp(dcf["wacc_data"], dark=dark)
        return [
            dbc.Row([
                dbc.Col(card("Free Cash Flow — Historical & Projected",
                             dcc.Graph(figure=fig_fcf, config={"displayModeBar": False}),
                             theme="dark" if dark else "light"), md=8),
                dbc.Col([
                    card("WACC Breakdown",  _wacc_table(dcf["wacc_data"], c),
                         theme="dark" if dark else "light"),
                    card("Scenario Analysis", _scenario_table(d["scenarios"], c),
                         theme="dark" if dark else "light"),
                ], md=4),
            ]),
            dbc.Row([
                dbc.Col(card("WACC Decomposition",
                             dcc.Graph(figure=fig_wacc, style={"height": "180px"},
                                       config={"displayModeBar": False}),
                             theme="dark" if dark else "light"), md=8),
                dbc.Col(card("DCF Assumptions", _assumptions_table(dcf, c),
                             theme="dark" if dark else "light"), md=4),
            ]),
        ]

    elif active_tab == "tab-sens":
        sens = d["sens"]
        fig = make_sensitivity_heatmap(sens["waccs"], sens["growths"],
                                       sens["prices"], price, dark=dark)
        return [
            card("Click any cell to drill into the full model for that assumption pair",
                 dcc.Graph(id="heatmap-graph", figure=fig,
                           config={"displayModeBar": False}),
                 theme="dark" if dark else "light"),
            html.Small("💡 Click a cell to see the full FCF waterfall for that WACC × growth combination.",
                       style={"color": c["text"], "opacity": "0.5", "fontSize": "12px"}),
        ]

    elif active_tab == "tab-comps":
        comps = d["comps"]
        fig = make_comps_table(comps["rows"], comps["medians"], dark=dark)
        return [
            card("Custom Peer Universe", _peer_editor(custom_peers or [], ticker, c),
                 theme="dark" if dark else "light"),
            card("Trading Comps Table",
                 dcc.Graph(figure=fig, config={"displayModeBar": False}),
                 theme="dark" if dark else "light"),
            card("Implied Prices from Comps Medians",
                 _implied_table(comps["implied_prices"], price, c),
                 theme="dark" if dark else "light"),
        ]

    elif active_tab == "tab-ff":
        fig = make_football_field(d["scenarios"], d["comps"]["implied_prices"], price, dark=dark)
        return card("Football Field — Valuation Range (hover for details)",
                    dcc.Graph(figure=fig, style={"height": "360px"},
                              config={"displayModeBar": False}),
                    theme="dark" if dark else "light")

    elif active_tab == "tab-hist":
        hist = get_historical_prices(ticker, limit=252)
        if not hist:
            return html.P("No historical price data available.",
                          style={"color": c["text"], "opacity": "0.5"})
        fig = make_historical_valuation_chart(hist, d["scenarios"], ticker, dark=dark)
        latest = hist[0]
        pct_vs_base = ((latest["close"] - d["scenarios"]["base"]["price"])
                       / d["scenarios"]["base"]["price"] * 100)
        badge_color = c["red"] if pct_vs_base > 0 else c["green"]
        badge_text  = f"{'Premium' if pct_vs_base > 0 else 'Discount'} to DCF: {pct_vs_base:+.1f}%"
        return [
            dbc.Row([
                dbc.Col(dbc.Alert(badge_text, color="danger" if pct_vs_base > 0 else "success",
                                  className="py-2 mb-3"), md=4),
                dbc.Col(html.Small(
                    "Green = trading below DCF intrinsic (undervalued)  ·  "
                    "Red = trading above DCF intrinsic (overvalued)",
                    style={"color": c["text"], "opacity": "0.5", "fontSize": "12px"}
                ), md=8, className="d-flex align-items-center"),
            ]),
            card(f"{ticker} — 1-Year Price vs DCF Intrinsic",
                 dcc.Graph(figure=fig, style={"height": "420px"},
                           config={"displayModeBar": False}),
                 theme="dark" if dark else "light"),
        ]

    elif active_tab == "tab-compare":
        return _compare_ui(c)

    return ""


# Heatmap drill-down modal
@app.callback(
    Output("drill-modal", "is_open"),
    Output("drill-modal-title", "children"),
    Output("drill-modal-body", "children"),
    Input("heatmap-graph", "clickData"),
    Input("btn-close-drill", "n_clicks"),
    State("store-results", "data"),
    State("store-theme", "data"),
    prevent_initial_call=True,
)
def heatmap_drill(click_data, close_clicks, data, theme):
    ctx = callback_context
    if not ctx.triggered:
        return False, "", ""
    trigger = ctx.triggered[0]["prop_id"]
    if trigger == "btn-close-drill.n_clicks":
        return False, "", ""
    if not click_data or not data:
        return False, "", ""

    dark = (theme or "dark") == "dark"
    d = json.loads(data)
    ticker = d["ticker"]
    point = click_data["points"][0]
    wacc_str = point["y"].replace("%", "")
    tgr_str  = point["x"].replace("%", "")
    wacc_val = float(wacc_str) / 100
    tgr_val  = float(tgr_str)  / 100
    implied_price = point["z"]

    result = run_dcf(ticker, terminal_growth_rate=tgr_val, wacc_override=wacc_val,
                     revenue_growth_rates=d["dcf"].get("growth_rates"))
    fig = make_fcf_waterfall(result["historical"], result["projected_fcfs"],
                              result["projection_years"], dark=dark)
    title = f"{ticker} — WACC {wacc_str}% × g {tgr_str}%  →  ${implied_price:.2f}"
    body = [
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
        html.Hr(),
        html.P(f"Intrinsic Price: ${result['intrinsic_price']:.2f}  |  "
               f"EV: ${result['enterprise_value']/1e9:.1f}B  |  "
               f"Equity Value: ${result['equity_value']/1e9:.1f}B",
               style={"fontSize": "13px", "fontWeight": "600"}),
    ]
    return True, title, body


# Peer add/remove
@app.callback(
    Output("store-custom-peers", "data"),
    Output("peer-badge-row", "children"),
    Input("btn-add-peer", "n_clicks"),
    Input({"type": "btn-remove-peer", "index": dash.ALL}, "n_clicks"),
    State("input-peer", "value"),
    State("store-custom-peers", "data"),
    State("store-results", "data"),
    prevent_initial_call=True,
)
def manage_peers(add_clicks, remove_clicks, new_ticker, current_peers, results_data):
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update

    trigger = ctx.triggered[0]["prop_id"]
    peers = list(current_peers or [])

    if "btn-add-peer" in trigger and new_ticker:
        t = new_ticker.strip().upper()
        if t and t not in peers and validate_ticker(t):
            peers.append(t)

    elif "btn-remove-peer" in trigger:
        try:
            prop = json.loads(trigger.split(".")[0])
            peers = [p for p in peers if p != prop["index"]]
        except Exception:
            pass

    return peers, _peer_badges(peers)


def _peer_badges(peers):
    if not peers:
        return html.Small("No custom peers — using FMP auto-sourced universe.",
                          style={"opacity": "0.5", "fontSize": "12px"})
    return [
        dbc.Badge([
            peers[i], " ",
            html.Span("×", id={"type": "btn-remove-peer", "index": peers[i]},
                      n_clicks=0, style={"cursor": "pointer", "fontWeight": "700"}),
        ], color="primary", className="me-1 mb-1", style={"fontSize": "12px"})
        for i in range(len(peers))
    ]


def _peer_editor(peers, ticker, c):
    return html.Div([
        dbc.InputGroup([
            dbc.Input(id="input-peer", placeholder="Add ticker (e.g. MSFT)", type="text",
                      style={"maxWidth": "220px"}),
            dbc.Button("Add", id="btn-add-peer", color="primary", size="sm", outline=True),
        ], className="mb-2"),
        html.Div(id="peer-badge-row", children=_peer_badges(peers)),
        html.Small("Changes take effect on next Analyse run.",
                   style={"opacity": "0.4", "fontSize": "11px"}),
    ])


# Excel export
@app.callback(
    Output("download-excel", "data"),
    Input("btn-export", "n_clicks"),
    State("store-results", "data"),
    prevent_initial_call=True,
)
def export_excel(_, data):
    if not data:
        return no_update
    d = json.loads(data)
    ticker = d["ticker"]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(d["dcf"]["historical"]).to_excel(
            writer, sheet_name="Historical FCF", index=False)
        pd.DataFrame({
            "Year": d["dcf"]["projection_years"],
            "Projected FCF ($)": d["dcf"]["projected_fcfs"],
        }).to_excel(writer, sheet_name="DCF Projection", index=False)
        sens = d["sens"]
        pd.DataFrame(
            sens["prices"],
            index=[f"WACC {w}%" for w in sens["waccs"]],
            columns=[f"g {g}%" for g in sens["growths"]],
        ).to_excel(writer, sheet_name="Sensitivity")
        if d["comps"]["rows"]:
            pd.DataFrame(d["comps"]["rows"]).to_excel(
                writer, sheet_name="Comps", index=False)
    buf.seek(0)
    return dcc.send_bytes(buf.read(), filename=f"{ticker}_valuation.xlsx")


# PDF export
@app.callback(
    Output("download-pdf", "data"),
    Input("btn-pdf", "n_clicks"),
    State("store-results", "data"),
    prevent_initial_call=True,
)
def export_pdf(_, data):
    if not data:
        return no_update
    d = json.loads(data)
    ticker = d["ticker"]
    dcf = d["dcf"]
    price = d["current_price"]
    intrinsic = dcf["intrinsic_price"]
    updown = ((intrinsic - price) / price * 100) if price else 0
    scen = d["scenarios"]
    implied = d["comps"]["implied_prices"]

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                         Table, TableStyle, HRFlowable)
        from reportlab.lib.units import cm
        import datetime

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                 leftMargin=2*cm, rightMargin=2*cm,
                                 topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        GREEN_RL = colors.HexColor("#00d4aa")
        DARK_RL  = colors.HexColor("#1a1a2e")
        CARD_RL  = colors.HexColor("#16213e")
        TEXT_RL  = colors.HexColor("#e0e0e0")

        h1 = ParagraphStyle("h1", parent=styles["Heading1"],
                             textColor=GREEN_RL, fontSize=18, spaceAfter=4)
        h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                             textColor=GREEN_RL, fontSize=12, spaceAfter=4)
        body = ParagraphStyle("body", parent=styles["Normal"],
                               textColor=colors.HexColor("#333333"), fontSize=10)
        sub = ParagraphStyle("sub", parent=styles["Normal"],
                              textColor=colors.grey, fontSize=8)

        ts_base = TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), DARK_RL),
            ("TEXTCOLOR",   (0, 0), (-1, 0), GREEN_RL),
            ("BACKGROUND",  (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f0f2f5")]),
            ("ALIGN",       (1, 0), (-1, -1), "CENTER"),
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",  (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ])

        story = []
        story.append(Paragraph(f"Valuation Summary — {ticker}", h1))
        story.append(Paragraph(
            f"{d['company_name']}  ·  {d['sector']}  ·  "
            f"Generated {datetime.date.today().strftime('%d %b %Y')}", sub))
        story.append(HRFlowable(width="100%", thickness=1, color=GREEN_RL, spaceAfter=10))

        # KPI table
        story.append(Paragraph("Key Metrics", h2))
        ud_color = colors.HexColor("#00d4aa") if updown >= 0 else colors.HexColor("#e94560")
        kpi_data = [
            ["Market Price", "Intrinsic Price (DCF)", "Upside / Downside",
             "WACC", "Enterprise Value"],
            [f"${price:.2f}", f"${intrinsic:.2f}", f"{updown:+.1f}%",
             f"{dcf['wacc']:.2%}", f"${dcf['enterprise_value']/1e9:.1f}B"],
        ]
        t = Table(kpi_data, colWidths=[3.2*cm]*5)
        t.setStyle(ts_base)
        story.append(t)
        story.append(Spacer(1, 0.4*cm))

        # Scenarios
        story.append(Paragraph("Scenario Analysis", h2))
        scen_data = [["Scenario", "Implied Price"]] + [
            [v["label"], f"${v['price']:.2f}"] for v in scen.values()
        ]
        t2 = Table(scen_data, colWidths=[8*cm, 8*cm])
        t2.setStyle(ts_base)
        story.append(t2)
        story.append(Spacer(1, 0.4*cm))

        # Assumptions
        story.append(Paragraph("Model Assumptions", h2))
        wacc_d = dcf["wacc_data"]
        ass_data = [
            ["Parameter", "Value"],
            ["Risk-Free Rate (10Y)", f"{wacc_d['risk_free_rate']:.2%}"],
            ["Beta", f"{wacc_d['beta']:.2f}"],
            ["Cost of Equity", f"{wacc_d['cost_of_equity']:.2%}"],
            ["Cost of Debt", f"{wacc_d['cost_of_debt']:.2%}"],
            ["WACC", f"{wacc_d['wacc']:.2%}"],
            ["Terminal Growth Rate", f"{dcf['terminal_growth_rate']:.2%}"],
            ["Base FCF (3yr avg)", f"${dcf['base_fcf']/1e9:.1f}B"],
            ["Net Debt", f"${wacc_d['net_debt']/1e9:.1f}B"],
        ]
        t3 = Table(ass_data, colWidths=[8*cm, 8*cm])
        t3.setStyle(ts_base)
        story.append(t3)
        story.append(Spacer(1, 0.4*cm))

        # Comps-implied prices
        if implied:
            story.append(Paragraph("Comps-Implied Prices", h2))
            imp_data = [["Method", "Implied Price", "vs Market"]] + [
                [m.upper().replace("_", "/"), f"${p:.2f}",
                 f"{((p-price)/price*100):+.1f}%" if price else "—"]
                for m, p in implied.items() if p
            ]
            t4 = Table(imp_data, colWidths=[5.3*cm, 5.3*cm, 5.4*cm])
            t4.setStyle(ts_base)
            story.append(t4)

        story.append(Spacer(1, 0.6*cm))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.grey, spaceAfter=6))
        story.append(Paragraph(
            "This report is generated automatically. All figures are model outputs "
            "and do not constitute investment advice.", sub))

        doc.build(story)
        buf.seek(0)
        return dcc.send_bytes(buf.read(), filename=f"{ticker}_valuation.pdf")

    except Exception as e:
        return no_update


# ── Helper tables ──────────────────────────────────────────────────────────────

def _wacc_table(w, c):
    rows = [
        ("Risk-Free Rate", f"{w['risk_free_rate']:.2%}"),
        ("Beta",           f"{w['beta']:.2f}"),
        ("Cost of Equity", f"{w['cost_of_equity']:.2%}"),
        ("Cost of Debt",   f"{w['cost_of_debt']:.2%}"),
        ("Tax Rate",       f"{w['tax_rate']:.2%}"),
        ("Weight Equity",  f"{w['weight_equity']:.1%}"),
        ("Weight Debt",    f"{w['weight_debt']:.1%}"),
        ("WACC",           f"{w['wacc']:.2%}"),
    ]
    return html.Table(html.Tbody([
        html.Tr([
            html.Td(k, style={"color": c["text"], "opacity": "0.7",
                               "fontSize": "12px", "paddingRight": "16px", "paddingBottom": "4px"}),
            html.Td(v, style={"color": c["green"], "fontWeight": "600", "fontSize": "12px"}),
        ]) for k, v in rows
    ]), style={"width": "100%"})


def _scenario_table(scenarios, c):
    rows = [(v["label"], f"${v['price']:.2f}") for v in scenarios.values()]
    palette = [c["text"], c["green"], "#5bc0de"]
    return html.Table(html.Tbody([
        html.Tr([
            html.Td(label, style={"color": c["text"], "fontSize": "13px", "paddingRight": "20px"}),
            html.Td(price, style={"color": col, "fontWeight": "700", "fontSize": "16px"}),
        ]) for (label, price), col in zip(rows, palette)
    ]), style={"width": "100%"})


def _assumptions_table(dcf, c):
    rows = [
        ("Projection Years", "5"),
        ("Base FCF",         f"${dcf['base_fcf']/1e9:.1f}B"),
        ("Terminal Growth",  f"{dcf['terminal_growth_rate']:.2%}"),
        ("Net Debt",         f"${dcf['wacc_data']['net_debt']/1e9:.1f}B"),
    ]
    return html.Table(html.Tbody([
        html.Tr([
            html.Td(k, style={"color": c["text"], "opacity": "0.7",
                               "fontSize": "12px", "paddingRight": "16px"}),
            html.Td(v, style={"color": c["text"], "fontSize": "12px"}),
        ]) for k, v in rows
    ]), style={"width": "100%"})


def _implied_table(implied, market_price, c):
    if not implied:
        return html.P("No comps implied prices available.",
                      style={"color": c["text"], "opacity": "0.5"})
    rows = []
    for method, price in implied.items():
        updown = (price - market_price) / market_price * 100 if market_price else 0
        color = c["green"] if updown >= 0 else c["red"]
        rows.append(html.Tr([
            html.Td(method.upper().replace("_", "/"),
                    style={"color": c["text"], "fontSize": "12px", "paddingRight": "20px"}),
            html.Td(f"${price:.2f}", style={"color": c["text"], "fontWeight": "600"}),
            html.Td(f"{updown:+.1f}%", style={"color": color, "fontWeight": "600"}),
        ]))
    return html.Table(html.Tbody(rows), style={"width": "100%"})


# ── Compare UI & callback ──────────────────────────────────────────────────────

def _compare_ui(c):
    return html.Div([
        dbc.Card(dbc.CardBody([
            html.Label("Enter up to 3 tickers to compare", className="fw-semibold mb-2",
                       style={"color": c["text"]}),
            dbc.Row([
                dbc.Col(dbc.Input(id="cmp-t1", placeholder="Ticker 1", value="AAPL",
                                  type="text"), md=3),
                dbc.Col(dbc.Input(id="cmp-t2", placeholder="Ticker 2", value="MSFT",
                                  type="text"), md=3),
                dbc.Col(dbc.Input(id="cmp-t3", placeholder="Ticker 3 (optional)",
                                  type="text"), md=3),
                dbc.Col(dbc.Button("Run Comparison", id="btn-compare",
                                   color="success", className="w-100"), md=3),
            ], className="g-2"),
        ]), style={"backgroundColor": c["card"], "border": f"1px solid {c['border']}"},
           className="mb-3"),
        html.Div(id="compare-output"),
    ])


@app.callback(
    Output("compare-output", "children"),
    Input("btn-compare", "n_clicks"),
    State("cmp-t1", "value"),
    State("cmp-t2", "value"),
    State("cmp-t3", "value"),
    State("store-theme", "data"),
    State("growth-slider", "value"),
    State("tgr-slider", "value"),
    prevent_initial_call=True,
)
def run_comparison(_, t1, t2, t3, theme, growth_pct, tgr_pct):
    dark = (theme or "dark") == "dark"
    c = THEMES["dark" if dark else "light"]
    tickers = [t.strip().upper() for t in [t1, t2, t3] if t and t.strip()]
    if not tickers:
        return html.P("Enter at least one ticker.", style={"color": c["text"]})

    growth = growth_pct / 100
    tgr    = tgr_pct   / 100
    growth_rates = [growth, growth, growth * 0.85, growth * 0.85, growth * 0.70]

    def _run_one(ticker):
        try:
            dcf      = run_dcf(ticker, revenue_growth_rates=growth_rates,
                                terminal_growth_rate=tgr)
            scen     = scenario_analysis(ticker, dcf)
            profile  = get_company_profile(ticker)
            return {
                "ticker":           ticker,
                "current_price":    profile.get("price", 0),
                "intrinsic_price":  dcf["intrinsic_price"],
                "enterprise_value": dcf["enterprise_value"],
                "wacc":             dcf["wacc"],
                "bear":             scen["bear"]["price"],
                "bull":             scen["bull"]["price"],
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=3) as ex:
        results = [r for r in ex.map(_run_one, tickers) if r]

    if not results:
        return html.P("Could not fetch data for any of those tickers.",
                      style={"color": c["text"]})

    fig_bars  = make_comparison_chart(results, dark=dark)
    fig_table = make_comparison_table(results, dark=dark)

    return [
        card("DCF Comparison",
             dcc.Graph(figure=fig_bars, style={"height": "380px"},
                       config={"displayModeBar": False}),
             theme="dark" if dark else "light"),
        card("Metrics Summary",
             dcc.Graph(figure=fig_table, config={"displayModeBar": False}),
             theme="dark" if dark else "light"),
    ]


if __name__ == "__main__":
    app.run(debug=True, port=8051)
