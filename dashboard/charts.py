import plotly.graph_objects as go

THEMES = {
    "dark": {
        "bg": "#1a1a2e", "card": "#16213e", "accent": "#0f3460",
        "green": "#00d4aa", "red": "#e94560", "text": "#e0e0e0",
        "grid": "#2a2a4a", "bar1": "#0f3460", "bar2": "#00d4aa",
    },
    "light": {
        "bg": "#f0f2f5", "card": "#ffffff", "accent": "#4a90d9",
        "green": "#0a8a6e", "red": "#c0392b", "text": "#1a1a2e",
        "grid": "#dde1e7", "bar1": "#4a90d9", "bar2": "#0a8a6e",
    },
}


def _t(dark: bool) -> dict:
    return THEMES["dark"] if dark else THEMES["light"]


def _base_layout(title: str = "", dark: bool = True) -> dict:
    c = _t(dark)
    return dict(
        title=dict(text=title, font=dict(color=c["text"], size=14)),
        paper_bgcolor=c["card"],
        plot_bgcolor=c["card"],
        font=dict(color=c["text"], size=11),
        margin=dict(l=50, r=20, t=40, b=40),
        xaxis=dict(gridcolor=c["grid"], zerolinecolor=c["grid"]),
        yaxis=dict(gridcolor=c["grid"], zerolinecolor=c["grid"]),
    )


def make_fcf_waterfall(historical: list, projected_fcfs: list, years: list, dark: bool = True) -> go.Figure:
    c = _t(dark)
    hist_years = [str(r["year"]) for r in historical]
    hist_fcfs = [r["fcf"] / 1e9 for r in historical]
    proj_years = [str(y) for y in years]
    proj_vals = [f / 1e9 for f in projected_fcfs]

    fig = go.Figure()

    # Historical — solid fill
    fig.add_trace(go.Bar(
        x=hist_years, y=hist_fcfs,
        name="Historical FCF",
        marker=dict(color=c["bar1"]),
        text=[f"${v:.1f}B" for v in hist_fcfs],
        textposition="outside",
        textfont=dict(color=c["text"]),
    ))

    # Projected — hatched/striped + slightly transparent to signal uncertainty
    fig.add_trace(go.Bar(
        x=proj_years, y=proj_vals,
        name="Projected FCF",
        marker=dict(
            color=c["bar2"],
            opacity=0.75,
            pattern=dict(shape="/", solidity=0.35, fgcolor=c["card"]),
        ),
        text=[f"${v:.1f}B" for v in proj_vals],
        textposition="outside",
        textfont=dict(color=c["text"]),
    ))

    # Divider line between historical and projected
    if hist_years and proj_years:
        fig.add_vline(
            x=len(hist_years) - 0.5,
            line_color=c["text"],
            line_dash="dot",
            line_width=1,
            annotation_text="◀ Historical  |  Projected ▶",
            annotation_font_color=c["text"],
            annotation_font_size=10,
            annotation_yref="paper",
            annotation_y=1.0,
        )

    fig.update_layout(**_base_layout("Free Cash Flow — Historical & Projected ($B)", dark))
    fig.update_layout(legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        font=dict(color=c["text"]),
    ))
    return fig


def make_wacc_decomp(wacc_data: dict, dark: bool = True) -> go.Figure:
    """Two-row stacked bar: Cost of Equity build-up + WACC blend."""
    c = _t(dark)
    w = wacc_data
    rf = w["risk_free_rate"] * 100
    erp_contrib = w["beta"] * 5.5
    ke = w["cost_of_equity"] * 100
    kd_at = w["cost_of_debt"] * (1 - w["tax_rate"]) * 100
    ke_weighted = w["weight_equity"] * ke
    kd_weighted = w["weight_debt"] * kd_at

    fig = go.Figure()

    # Row 1: Cost of Equity = Rf + β×ERP
    fig.add_trace(go.Bar(
        y=["Cost of Equity"], x=[rf], orientation="h",
        name=f"Risk-Free Rate",
        marker_color="#4a90d9",
        text=[f"Rf {rf:.2f}%"], textposition="inside",
        insidetextanchor="middle",
    ))
    fig.add_trace(go.Bar(
        y=["Cost of Equity"], x=[erp_contrib], orientation="h",
        name=f"β × ERP",
        marker_color="#7bb3f0",
        text=[f"β×ERP {erp_contrib:.2f}%"], textposition="inside",
        insidetextanchor="middle",
    ))

    # Row 2: WACC = Ke×E/V + Kd(1-t)×D/V
    fig.add_trace(go.Bar(
        y=["WACC"], x=[ke_weighted], orientation="h",
        name=f"Ke × E/V",
        marker_color=c["green"],
        text=[f"Ke×E/V {ke_weighted:.2f}%"], textposition="inside",
        insidetextanchor="middle",
    ))
    fig.add_trace(go.Bar(
        y=["WACC"], x=[kd_weighted], orientation="h",
        name=f"Kd(1-t) × D/V",
        marker_color="#00a896",
        text=[f"Kd(1-t)×D/V {kd_weighted:.2f}%"], textposition="inside",
        insidetextanchor="middle",
    ))

    layout = _base_layout("WACC Decomposition (%)", dark)
    layout.update(
        barmode="stack",
        xaxis=dict(title="Rate (%)", gridcolor=c["grid"], zerolinecolor=c["grid"]),
        yaxis=dict(gridcolor=c["grid"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(color=c["text"])),
    )
    # Annotate totals
    fig.add_annotation(x=ke, y="Cost of Equity", text=f"= {ke:.2f}%",
                        showarrow=False, xanchor="left", xshift=6,
                        font=dict(color=c["text"], size=11))
    fig.add_annotation(x=ke_weighted + kd_weighted, y="WACC",
                        text=f"= {ke_weighted+kd_weighted:.2f}%",
                        showarrow=False, xanchor="left", xshift=6,
                        font=dict(color=c["text"], size=11))
    fig.update_layout(**layout)
    return fig


def make_sensitivity_heatmap(
    waccs: list, growths: list, prices: list, current_price: float, dark: bool = True
) -> go.Figure:
    c = _t(dark)
    z = [[p if p is not None else 0 for p in row] for row in prices]
    text = [[f"${p:.0f}" if p is not None else "N/A" for p in row] for row in prices]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"{g}%" for g in growths],
        y=[f"{w}%" for w in waccs],
        text=text,
        texttemplate="%{text}",
        colorscale=[[0.0, c["red"]], [0.5, c["grid"]], [1.0, c["green"]]],
        zmid=current_price,
        colorbar=dict(title="Price ($)", tickfont=dict(color=c["text"]),
                      titlefont=dict(color=c["text"])),
        hovertemplate=(
            "<b>WACC: %{y}</b><br>"
            "Terminal Growth: %{x}<br>"
            "Implied Price: %{text}<br>"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(**_base_layout("Sensitivity: Intrinsic Price by WACC × Terminal Growth Rate", dark))
    fig.update_xaxes(title="Terminal Growth Rate")
    fig.update_yaxes(title="WACC", autorange="reversed")
    return fig


def make_football_field(
    dcf_scenarios: dict, implied_prices: dict, current_price: float, dark: bool = True
) -> go.Figure:
    c = _t(dark)
    bars, colors, labels = [], [], []

    if dcf_scenarios:
        bear = dcf_scenarios["bear"]["price"]
        bull = dcf_scenarios["bull"]["price"]
        bars.append((bear, bull - bear))
        colors.append(c["accent"])
        labels.append("DCF (Bear–Bull)")

    for method, price in implied_prices.items():
        if price:
            spread = price * 0.10
            bars.append((price - spread, spread * 2))
            colors.append(c["green"])
            labels.append(f"Comps ({method.upper().replace('_', '/')})")

    fig = go.Figure()
    for label, (low, width), color in zip(labels, bars, colors):
        high = low + width
        updown_low = (low - current_price) / current_price * 100 if current_price else 0
        updown_high = (high - current_price) / current_price * 100 if current_price else 0
        fig.add_trace(go.Bar(
            x=[width], y=[label], base=[low],
            orientation="h", marker_color=color, name=label,
            text=[f"${low:.0f} – ${high:.0f}"],
            textposition="inside", insidetextanchor="middle",
            hovertemplate=(
                f"<b>{label}</b><br>"
                f"Range: ${low:.2f} – ${high:.2f}<br>"
                f"vs Market: {updown_low:+.1f}% to {updown_high:+.1f}%<br>"
                f"Market Price: ${current_price:.2f}<br>"
                "<extra></extra>"
            ),
        ))

    fig.add_vline(
        x=current_price, line_color=c["red"], line_dash="dash",
        annotation_text=f"Market ${current_price:.0f}",
        annotation_font_color=c["red"],
    )

    layout = _base_layout("Football Field — Valuation Range Summary", dark)
    layout.update(
        barmode="overlay", showlegend=False,
        xaxis=dict(title="Implied Share Price ($)", gridcolor=c["grid"], zerolinecolor=c["grid"]),
        yaxis=dict(gridcolor=c["grid"]),
    )
    fig.update_layout(**layout)
    return fig


def make_comps_table(rows: list, medians: dict, dark: bool = True) -> go.Figure:
    c = _t(dark)
    cols = ["Ticker", "Company", "EV/Rev", "EV/EBITDA", "P/E", "P/FCF"]
    table_rows = {col: [] for col in cols}

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
            fill_colors.append(c["accent"])
        elif is_median:
            fill_colors.append("#0d2137" if dark else "#e8f4fd")
        else:
            fill_colors.append(c["card"])

    fig = go.Figure(go.Table(
        header=dict(
            values=cols,
            fill_color=c["bg"],
            font=dict(color=c["text"], size=12),
            align="center",
        ),
        cells=dict(
            values=[table_rows[col] for col in cols],
            fill_color=[fill_colors] * len(cols),
            font=dict(color=c["text"], size=11),
            align="center",
            height=28,
        ),
    ))
    fig.update_layout(paper_bgcolor=c["card"], margin=dict(l=0, r=0, t=10, b=0))
    return fig
