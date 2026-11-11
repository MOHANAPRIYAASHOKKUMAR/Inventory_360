"""Plotly chart builders with the Inventory 360 house style.

All charts share one look: white plot panels on the grey app canvas, navy text,
teal accent, fixed RAG colours, and consistent GBP / percentage axis formats.
Rendered with ``theme=None`` so the house style is not overridden.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

NAVY = "#0B2545"
NAVY_2 = "#1E3A5F"
TEAL = "#0F766E"
TEAL_LIGHT = "#14B8A6"
SLATE = "#94A3B8"
GRID = "#E6EBF1"
RED, AMBER, GREEN = "#C0392B", "#D97706", "#15803D"
RAG_COLOURS = {"Red": RED, "Amber": AMBER, "Green": GREEN, "n/a": SLATE}
PALETTE = ["#0B2545", "#0F766E", "#5B8DB8", "#14B8A6", "#94A3B8", "#1E3A5F", "#7FB7B0", "#C49A3A", "#8C6B9E", "#3F6E8C"]
STATUS_COLOURS = {
    "Out of stock": "#991B1B", "Critical": RED, "Low": AMBER,
    "Healthy": GREEN, "Overstock": "#5B8DB8", "Excess": NAVY_2,
}
FONT = '"Source Sans Pro", "Segoe UI", "Helvetica Neue", Arial, sans-serif'

CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}

# Axis formats: tick label / hover label
FORMATS = {
    "gbp": {"tickprefix": "£", "tickformat": "~s", "hoverformat": ",.0f"},
    "gbp2": {"tickprefix": "£", "tickformat": ",.2f", "hoverformat": ",.2f"},
    "pct": {"tickformat": ".0%", "hoverformat": ".1%"},
    "num": {"tickformat": "~s", "hoverformat": ",.0f"},
    "dec": {"tickformat": ",.1f", "hoverformat": ",.1f"},
    "days": {"ticksuffix": " d", "tickformat": ",.0f", "hoverformat": ",.1f"},
}


def _axis(kind: str | None, title: str | None = None) -> dict:
    out = {"title": {"text": title, "font": {"size": 12}} if title else None,
           "gridcolor": GRID, "zeroline": False, "linecolor": GRID}
    if kind:
        out.update(FORMATS[kind])
    return out


def style(fig: go.Figure, *, height: int = 320, y: str | None = None, x: str | None = None,
          y_title: str | None = None, x_title: str | None = None, legend: bool = True,
          hovermode: str | None = "x unified") -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 36 if legend else 12, "b": 8},
        font={"family": FONT, "size": 12, "color": NAVY},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        colorway=PALETTE,
        hovermode=hovermode,
        hoverlabel={"bgcolor": "#FFFFFF", "bordercolor": GRID, "font": {"family": FONT, "color": NAVY}},
        showlegend=legend,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0, "title": None, "font": {"size": 11}},
        xaxis=_axis(x, x_title),
        yaxis=_axis(y, y_title),
        bargap=0.25,
    )
    return fig


def show(fig: go.Figure, alt: str, *, key: str | None = None, select: bool = False):
    """Render a figure; with ``select=True`` returns the click / selection state."""
    if select:
        return st.plotly_chart(fig, theme=None, config=CONFIG, alt=alt, key=key,
                               on_select="rerun", selection_mode="points")
    st.plotly_chart(fig, theme=None, config=CONFIG, alt=alt, key=key)
    return None


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def line(df: pd.DataFrame, x: str, y: str, color: str | None = None, *, kind: str = "gbp",
         height: int = 320, y_title: str | None = None, target: float | None = None,
         target_label: str = "Target", colors: dict | None = None, markers: bool = False) -> go.Figure:
    fig = px.line(df, x=x, y=y, color=color, color_discrete_map=colors, markers=markers,
                  color_discrete_sequence=PALETTE)
    fig.update_traces(line={"width": 2.2})
    if target is not None:
        fig.add_hline(y=target, line_dash="dot", line_color=AMBER, line_width=1.5,
                      annotation_text=target_label, annotation_position="top left",
                      annotation_font={"color": AMBER, "size": 11})
    return style(fig, height=height, y=kind, y_title=y_title, legend=color is not None)


def bar(df: pd.DataFrame, x: str, y: str, color: str | None = None, *, kind: str = "gbp",
        horizontal: bool = False, stacked: bool = True, height: int = 320, value_title: str | None = None,
        colors: dict | None = None, single_colour: str = TEAL, order: list | None = None,
        text: bool = False) -> go.Figure:
    kwargs = {"x": y, "y": x, "orientation": "h"} if horizontal else {"x": x, "y": y}
    fig = px.bar(df, color=color, color_discrete_map=colors, barmode="stack" if stacked else "group",
                 color_discrete_sequence=PALETTE if color else [single_colour],
                 category_orders={x: order} if order else None, **kwargs)
    fig.update_traces(marker_line_width=0)
    if text:
        fmt = FORMATS[kind]
        fig.update_traces(texttemplate=f"{fmt.get('tickprefix', '')}%{{{'x' if horizontal else 'y'}:{fmt['tickformat']}}}"
                          f"{fmt.get('ticksuffix', '')}", textposition="outside", cliponaxis=False)
    if horizontal:
        fig = style(fig, height=height, x=kind, x_title=value_title, legend=color is not None, hovermode="y unified")
        fig.update_yaxes(title=None, autorange="reversed" if not order else None, gridcolor="rgba(0,0,0,0)")
    else:
        fig = style(fig, height=height, y=kind, y_title=value_title, legend=color is not None)
        fig.update_xaxes(title=None)
    return fig


def combo(df: pd.DataFrame, x: str, bar_y: str, line_y: str, bar_name: str, line_name: str, *,
          bar_kind: str = "gbp", line_kind: str = "pct", height: int = 320,
          line_target: float | None = None) -> go.Figure:
    """Bars on the left axis with a line on a secondary right axis."""
    fig = go.Figure()
    fig.add_bar(x=df[x], y=df[bar_y], name=bar_name, marker_color="#B8C7D9", marker_line_width=0)
    fig.add_scatter(x=df[x], y=df[line_y], name=line_name, mode="lines+markers", yaxis="y2",
                    line={"color": TEAL, "width": 2.4}, marker={"size": 5})
    style(fig, height=height, y=bar_kind)
    fig.update_layout(yaxis2={**_axis(line_kind), "overlaying": "y", "side": "right", "showgrid": False})
    if line_target is not None:
        fig.add_hline(y=line_target, yref="y2", line_dash="dot", line_color=AMBER, line_width=1.5,
                      annotation_text="Target", annotation_position="top left",
                      annotation_font={"color": AMBER, "size": 11})
    return fig


def donut(df: pd.DataFrame, names: str, values: str, *, colors: dict | None = None, kind: str = "num",
          height: int = 300, order: list | None = None) -> go.Figure:
    if order:
        df = df.set_index(names).reindex([o for o in order if o in set(df[names])]).reset_index()
    marker = {"colors": [colors.get(n, SLATE) for n in df[names]]} if colors else {"colors": PALETTE}
    fmt = FORMATS[kind]
    fig = go.Figure(go.Pie(
        labels=df[names], values=df[values], hole=0.62, sort=False, direction="clockwise", marker=marker,
        textinfo="percent", textfont={"size": 11, "color": "#FFFFFF"},
        hovertemplate=f"%{{label}}<br>{fmt.get('tickprefix', '')}%{{value:{fmt['hoverformat']}}} · %{{percent}}<extra></extra>",
    ))
    style(fig, height=height, hovermode="closest")
    fig.update_layout(legend={"orientation": "v", "y": 0.5, "yanchor": "middle", "x": 1.02})
    return fig


def scatter(df: pd.DataFrame, x: str, y: str, *, color: str | None = None, size: str | None = None,
            hover: str | None = None, x_kind: str = "gbp", y_kind: str = "pct", height: int = 360,
            colors: dict | None = None, x_title: str | None = None, y_title: str | None = None,
            y_ref: float | None = None, x_log: bool = False, custom: list[str] | None = None,
            size_max: int = 34) -> go.Figure:
    fig = px.scatter(df, x=x, y=y, color=color, size=size, hover_name=hover, color_discrete_map=colors,
                     color_discrete_sequence=PALETTE, size_max=size_max, log_x=x_log, custom_data=custom)
    fig.update_traces(marker={"line": {"width": 1, "color": "#FFFFFF"}, "opacity": 0.88})
    if y_ref is not None:
        fig.add_hline(y=y_ref, line_dash="dot", line_color=AMBER, line_width=1.5,
                      annotation_text="Target", annotation_position="bottom right",
                      annotation_font={"color": AMBER, "size": 11})
    return style(fig, height=height, x=x_kind, y=y_kind, x_title=x_title, y_title=y_title,
                 legend=color is not None, hovermode="closest")


def heatmap(pivot: pd.DataFrame, *, kind: str = "pct", height: int = 340, reverse: bool = False,
            zmid: float | None = None) -> go.Figure:
    """Rows x columns matrix; ``reverse`` makes low values teal (good) and high red."""
    fmt = FORMATS[kind]
    scale = [[0, RED], [0.5, "#F8E1D8"], [1, TEAL]] if not reverse else [[0, TEAL], [0.5, "#F8E1D8"], [1, RED]]
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=list(pivot.columns), y=list(pivot.index), colorscale=scale, zmid=zmid,
        xgap=2, ygap=2, colorbar={"thickness": 10, "tickformat": fmt["tickformat"],
                                   "tickprefix": fmt.get("tickprefix", "")},
        hovertemplate=f"%{{y}} · %{{x}}<br>{fmt.get('tickprefix', '')}%{{z:{fmt['hoverformat']}}}<extra></extra>",
        texttemplate=f"{fmt.get('tickprefix', '')}%{{z:{fmt['tickformat']}}}", textfont={"size": 10},
    ))
    style(fig, height=height, legend=False, hovermode="closest")
    fig.update_xaxes(side="top", gridcolor="rgba(0,0,0,0)", tickangle=0)
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    return fig


def waterfall(labels: list[str], values: list[float], *, total_label: str = "Total", height: int = 340) -> go.Figure:
    """Variance bridge: positive (overspend) red, negative (saving) green."""
    fig = go.Figure(go.Waterfall(
        x=[*labels, total_label], y=[*values, sum(values)], measure=["relative"] * len(values) + ["total"],
        increasing={"marker": {"color": RED}}, decreasing={"marker": {"color": GREEN}},
        totals={"marker": {"color": NAVY}}, connector={"line": {"color": GRID}},
        texttemplate="£%{y:~s}", textposition="outside", cliponaxis=False,
        hovertemplate="%{x}<br>£%{y:,.0f}<extra></extra>",
    ))
    style(fig, height=height, y="gbp", legend=False, hovermode="closest")
    return fig


def forecast(fc: pd.DataFrame, *, height: int = 380) -> go.Figure:
    """Actuals, model fit and forecast with an 80% prediction band."""
    fut = fc[fc["forecast"].notna()]
    fig = go.Figure()
    fig.add_scatter(x=pd.concat([fut["week"], fut["week"][::-1]]), y=pd.concat([fut["upper"], fut["lower"][::-1]]),
                    fill="toself", fillcolor="rgba(15,118,110,0.14)", line={"width": 0}, hoverinfo="skip",
                    name="80% interval")
    fig.add_scatter(x=fc["week"], y=fc["actual"], name="Actual", mode="lines", line={"color": NAVY, "width": 2})
    fig.add_scatter(x=fc["week"], y=fc["fitted"], name="Model fit", mode="lines",
                    line={"color": SLATE, "width": 1.5, "dash": "dot"})
    fig.add_scatter(x=fut["week"], y=fut["forecast"], name="Forecast", mode="lines+markers",
                    line={"color": TEAL, "width": 2.6}, marker={"size": 5})
    return style(fig, height=height, y="num", y_title="Units")
