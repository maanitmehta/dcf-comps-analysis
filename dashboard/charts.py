import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

DARK_BG = "#1a1a2e"
CARD_BG = "#16213e"
ACCENT = "#0f3460"
GREEN = "#00d4aa"
RED = "#e94560"
TEXT = "#e0e0e0"
GRID = "#2a2a4a"


def _base_layout(title: str = "") -> dict:
    return dict(
        title=dict(text=title, font=dict(color=TEXT, size=14)),
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        font=dict(color=TEXT, size=11),
        margin=dict(l=50, r=20, t=40, b=40),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    )


def make_fcf_waterfall(historical: list, projected_fcfs: list, years: list) -> go.Figure:
    hist_years = [str(r["year"]) for r in historical]
    hist_fcfs = [r["fcf"] / 1e9 for r in historical]
    proj_years = [str(y) for y in years]
    proj_vals = [f / 1e9 for f in projected_fcfs]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=hist_years, y=hist_fcfs,
        name="Historical FCF", marker_color=ACCENT,
        text=[f"${v:.1f}B" for v in hist_fcfs], textposition="outside",
    ))
    fig.add_trace(go.Bar(
        x=proj_years, y=proj_vals,
        name="Projected FCF", marker_color=GREEN,
        text=[f"${v:.1f}B" for v in proj_vals], textposition="outside",
    ))
    fig.update_layout(**_base_layout("Free Cash Flow — Historical & Projected ($B)"))
    return fig


def make_sensitivity_heatmap(waccs: list, growths: list, prices: list, current_price: float) -> go.Figure:
    z = [[p if p is not None else 0 for p in row] for row in prices]
    text = [[f"${p:.0f}" if p is not None else "N/A" for p in row] for row in prices]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"{g}%" for g in growths],
        y=[f"{w}%" for w in waccs],
        text=text,
        texttemplate="%{text}",
        colorscale=[
            [0.0, RED],
            [0.5, "#2a2a4a"],
            [1.0, GREEN],
        ],
        zmid=current_price,
        colorbar=dict(title="Price ($)", tickfont=dict(color=TEXT), titlefont=dict(color=TEXT)),
    ))
    fig.update_layout(**_base_layout("Sensitivity: Intrinsic Price by WACC × Terminal Growth Rate"))
    fig.update_xaxes(title="Terminal Growth Rate")
    fig.update_yaxes(title="WACC", autorange="reversed")
    return fig


def make_football_field(dcf_scenarios: dict, implied_prices: dict, current_price: float) -> go.Figure:
    bars = []
    colors = []
    labels = []

    if dcf_scenarios:
        bear = dcf_scenarios["bear"]["price"]
        bull = dcf_scenarios["bull"]["price"]
        bars.append((bear, bull - bear))
        colors.append(ACCENT)
        labels.append("DCF (Bear–Bull)")

    for method, price in implied_prices.items():
        if price:
            spread = price * 0.10
            bars.append((price - spread, spread * 2))
            colors.append(GREEN)
            labels.append(f"Comps ({method.upper().replace('_', '/')})")

    fig = go.Figure()
    for i, (label, (low, width), color) in enumerate(zip(labels, bars, colors)):
        fig.add_trace(go.Bar(
            x=[width], y=[label], base=[low],
            orientation="h", marker_color=color, name=label,
            text=[f"${low:.0f} – ${low+width:.0f}"],
            textposition="inside", insidetextanchor="middle",
        ))

    fig.add_vline(x=current_price, line_color=RED, line_dash="dash",
                  annotation_text=f"Market ${current_price:.0f}", annotation_font_color=RED)

    layout = _base_layout("Football Field — Valuation Range Summary")
    layout.update(barmode="overlay", showlegend=False,
                  xaxis=dict(title="Implied Share Price ($)", gridcolor=GRID, zerolinecolor=GRID),
                  yaxis=dict(gridcolor=GRID))
    fig.update_layout(**layout)
    return fig


def make_comps_table(rows: list, medians: dict) -> go.Figure:
    cols = ["Ticker", "Company", "EV/Rev", "EV/EBITDA", "P/E", "P/FCF"]
    table_rows = {c: [] for c in cols}

    for r in rows:
        table_rows["Ticker"].append(r["ticker"])
        table_rows["Company"].append(r["name"][:25])
        table_rows["EV/Rev"].append(f"{r['ev_revenue']:.1f}x" if r["ev_revenue"] else "—")
        table_rows["EV/EBITDA"].append(f"{r['ev_ebitda']:.1f}x" if r["ev_ebitda"] else "—")
        table_rows["P/E"].append(f"{r['pe']:.1f}x" if r["pe"] and r["pe"] > 0 else "—")
        table_rows["P/FCF"].append(f"{r['p_fcf']:.1f}x" if r["p_fcf"] else "—")

    table_rows["Ticker"].append("MEDIAN")
    table_rows["Company"].append("—")
    table_rows["EV/Rev"].append(f"{medians['ev_revenue']:.1f}x" if medians["ev_revenue"] else "—")
    table_rows["EV/EBITDA"].append(f"{medians['ev_ebitda']:.1f}x" if medians["ev_ebitda"] else "—")
    table_rows["P/E"].append(f"{medians['pe']:.1f}x" if medians["pe"] and medians["pe"] > 0 else "—")
    table_rows["P/FCF"].append(f"{medians['p_fcf']:.1f}x" if medians["p_fcf"] else "—")

    n = len(table_rows["Ticker"])
    fill_colors = []
    for i in range(n):
        is_target = rows[i]["is_target"] if i < len(rows) else False
        is_median = (i == n - 1)
        if is_target:
            fill_colors.append(ACCENT)
        elif is_median:
            fill_colors.append("#0d2137")
        else:
            fill_colors.append(CARD_BG)

    fig = go.Figure(go.Table(
        header=dict(
            values=cols,
            fill_color=DARK_BG,
            font=dict(color=TEXT, size=12),
            align="center",
        ),
        cells=dict(
            values=[table_rows[c] for c in cols],
            fill_color=[fill_colors] * len(cols),
            font=dict(color=TEXT, size=11),
            align="center",
            height=28,
        ),
    ))
    fig.update_layout(paper_bgcolor=CARD_BG, margin=dict(l=0, r=0, t=10, b=0))
    return fig
