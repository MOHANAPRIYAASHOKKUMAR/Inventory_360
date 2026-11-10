"""Altair chart builders with consistent enterprise styling."""
from __future__ import annotations

import altair as alt
import pandas as pd

from inventory360.utils.config import RISK_COLOURS, STOCK_STATUS_COLOURS, STOCK_STATUS_ORDER

GBP_AXIS = alt.Axis(format="~s", labelExpr="'£' + datum.label")
PCT_AXIS = alt.Axis(format=".0%")


def _base(chart: alt.Chart, height: int) -> alt.Chart:
    return chart.properties(height=height).configure_view(strokeWidth=0)


def line(df: pd.DataFrame, x: str, y: str, color: str | None = None, y_title: str = "",
         gbp: bool = False, pct: bool = False, height: int = 280) -> alt.Chart:
    axis = GBP_AXIS if gbp else PCT_AXIS if pct else alt.Axis(format="~s")
    enc = {
        "x": alt.X(f"{x}:T", title=None),
        "y": alt.Y(f"{y}:Q", title=y_title, axis=axis),
        "tooltip": [alt.Tooltip(f"{x}:T", title="Period"),
                    alt.Tooltip(f"{y}:Q", title=y_title or y, format=",.2%" if pct else ",.0f")],
    }
    if color:
        enc["color"] = alt.Color(f"{color}:N", title=None, legend=alt.Legend(orient="bottom"))
        enc["tooltip"].insert(0, alt.Tooltip(f"{color}:N"))
    return _base(alt.Chart(df).mark_line(point=False, strokeWidth=2.2).encode(**enc), height)


def area_with_line(df: pd.DataFrame, x: str, area_y: str, line_y: str, area_title: str,
                   line_title: str, height: int = 300) -> alt.LayerChart:
    """Dual-axis: bars/areas for value (left, GBP) and a line for a ratio (right)."""
    base = alt.Chart(df).encode(x=alt.X(f"{x}:T", title=None))
    area = base.mark_area(opacity=0.35, line=True).encode(
        y=alt.Y(f"{area_y}:Q", title=area_title, axis=GBP_AXIS),
        tooltip=[alt.Tooltip(f"{x}:T", title="Week"), alt.Tooltip(f"{area_y}:Q", title=area_title, format=",.0f")],
    )
    ln = base.mark_line(color="#E04F16", strokeWidth=2).encode(
        y=alt.Y(f"{line_y}:Q", title=line_title, axis=PCT_AXIS, scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip(f"{x}:T", title="Week"), alt.Tooltip(f"{line_y}:Q", title=line_title, format=".2%")],
    )
    return alt.layer(area, ln).resolve_scale(y="independent").properties(height=height).configure_view(strokeWidth=0)


def bar(df: pd.DataFrame, x: str, y: str, color: str | None = None, horizontal: bool = False,
        gbp: bool = False, pct: bool = False, sort: str | None = "-x", height: int = 280,
        title_x: str = "", title_y: str = "", stack: bool = True) -> alt.Chart:
    axis = GBP_AXIS if gbp else PCT_AXIS if pct else alt.Axis(format="~s")
    fmt = ",.1%" if pct else ",.0f"
    if horizontal:
        enc = {
            "y": alt.Y(f"{x}:N", title=title_x or None, sort=sort),
            "x": alt.X(f"{y}:Q", title=title_y, axis=axis, stack=stack or None),
        }
    else:
        enc = {
            "x": alt.X(f"{x}:N", title=title_x or None, sort=sort),
            "y": alt.Y(f"{y}:Q", title=title_y, axis=axis, stack=stack or None),
        }
    enc["tooltip"] = [alt.Tooltip(f"{x}:N"), alt.Tooltip(f"{y}:Q", format=fmt, title=title_y or y)]
    if color:
        enc["color"] = alt.Color(f"{color}:N", title=None, legend=alt.Legend(orient="bottom"))
        enc["tooltip"].insert(1, alt.Tooltip(f"{color}:N"))
        if not stack:
            enc["xOffset" if not horizontal else "yOffset"] = alt.XOffset(f"{color}:N") if not horizontal else alt.YOffset(f"{color}:N")
    return _base(alt.Chart(df).mark_bar(cornerRadiusEnd=3).encode(**enc), height)


def monthly_bar(df: pd.DataFrame, x: str, y: str, color: str | None = None, gbp: bool = True,
                height: int = 280, y_title: str = "") -> alt.Chart:
    enc = {
        "x": alt.X(f"yearmonth({x}):T", title=None, axis=alt.Axis(format="%b %y")),
        "y": alt.Y(f"sum({y}):Q", title=y_title, axis=GBP_AXIS if gbp else alt.Axis(format="~s")),
        "tooltip": [alt.Tooltip(f"yearmonth({x}):T", title="Month"),
                    alt.Tooltip(f"sum({y}):Q", title=y_title or y, format=",.0f")],
    }
    if color:
        enc["color"] = alt.Color(f"{color}:N", title=None, legend=alt.Legend(orient="bottom"))
        enc["tooltip"].insert(1, alt.Tooltip(f"{color}:N"))
    return _base(alt.Chart(df).mark_bar().encode(**enc), height)


def status_donut(df: pd.DataFrame, value: str, height: int = 260) -> alt.Chart:
    present = [s for s in STOCK_STATUS_ORDER if s in set(df["stock_status"])]
    return _base(
        alt.Chart(df).mark_arc(innerRadius=62, cornerRadius=3).encode(
            theta=alt.Theta(f"{value}:Q", stack=True),
            color=alt.Color(
                "stock_status:N",
                title=None,
                scale=alt.Scale(domain=present, range=[STOCK_STATUS_COLOURS[s] for s in present]),
                sort=present,
                legend=alt.Legend(orient="right"),
            ),
            order=alt.Order("order:Q"),
            tooltip=[alt.Tooltip("stock_status:N", title="Status"), alt.Tooltip(f"{value}:Q", format=",.0f")],
        ).transform_calculate(order=f"indexof({present}, datum.stock_status)"),
        height,
    )


def status_stacked_bar(df: pd.DataFrame, category: str, value: str, height: int = 320) -> alt.Chart:
    present = [s for s in STOCK_STATUS_ORDER if s in set(df["stock_status"])]
    return _base(
        alt.Chart(df).mark_bar().encode(
            y=alt.Y(f"{category}:N", title=None, sort="-x"),
            x=alt.X(f"sum({value}):Q", title="Share of SKU-locations", stack="normalize", axis=PCT_AXIS),
            color=alt.Color(
                "stock_status:N", title=None,
                scale=alt.Scale(domain=present, range=[STOCK_STATUS_COLOURS[s] for s in present]),
                sort=present, legend=alt.Legend(orient="bottom"),
            ),
            order=alt.Order("order:Q"),
            tooltip=[alt.Tooltip(f"{category}:N"), alt.Tooltip("stock_status:N"),
                     alt.Tooltip(f"sum({value}):Q", title="SKU-locations")],
        ).transform_calculate(order=f"indexof({present}, datum.stock_status)"),
        height,
    )


def supplier_matrix(df: pd.DataFrame, height: int = 380) -> alt.Chart:
    """Spend vs OTIF bubble matrix coloured by risk rating."""
    present = [r for r in ("High", "Medium", "Low") if r in set(df["risk_rating"])]
    return _base(
        alt.Chart(df).mark_circle(opacity=0.8, stroke="#FFFFFF", strokeWidth=1).encode(
            x=alt.X("otif_rate:Q", title="OTIF (12 months)", axis=PCT_AXIS, scale=alt.Scale(zero=False)),
            y=alt.Y("spend_gbp:Q", title="Spend (12 months)", axis=GBP_AXIS),
            size=alt.Size("lead_time_variability_days:Q", title="Lead-time variability (days)",
                          scale=alt.Scale(range=[60, 900]), legend=None),
            color=alt.Color("risk_rating:N", title="Risk",
                            scale=alt.Scale(domain=present, range=[RISK_COLOURS[r] for r in present]),
                            legend=alt.Legend(orient="bottom")),
            tooltip=[
                alt.Tooltip("supplier_name:N", title="Supplier"),
                alt.Tooltip("country_name:N", title="Country"),
                alt.Tooltip("spend_gbp:Q", title="Spend £", format=",.0f"),
                alt.Tooltip("otif_rate:Q", title="OTIF", format=".1%"),
                alt.Tooltip("performance_score:Q", title="Score"),
                alt.Tooltip("lead_time_variability_days:Q", title="LT variability (d)", format=".1f"),
            ],
        ),
        height,
    )


def forecast_chart(df: pd.DataFrame, height: int = 340) -> alt.LayerChart:
    base = alt.Chart(df).encode(x=alt.X("week:T", title=None))
    band = base.mark_area(opacity=0.18, color="#1D4ED8").encode(y="lower:Q", y2="upper:Q")
    actual = base.mark_line(color="#0F172A", strokeWidth=1.8).encode(
        y=alt.Y("actual:Q", title="Units per week", axis=alt.Axis(format="~s")),
        tooltip=[alt.Tooltip("week:T"), alt.Tooltip("actual:Q", format=",.0f")],
    )
    fitted = base.mark_line(color="#94A3B8", strokeDash=[4, 3]).encode(y="fitted:Q")
    fc = base.mark_line(color="#1D4ED8", strokeWidth=2.5).encode(
        y="forecast:Q",
        tooltip=[alt.Tooltip("week:T"), alt.Tooltip("forecast:Q", format=",.0f"),
                 alt.Tooltip("lower:Q", format=",.0f"), alt.Tooltip("upper:Q", format=",.0f")],
    )
    return alt.layer(band, actual, fitted, fc).properties(height=height).configure_view(strokeWidth=0)


def pareto(df: pd.DataFrame, height: int = 300) -> alt.LayerChart:
    base = alt.Chart(df).encode(x=alt.X("rank_pct:Q", title="Share of SKUs", axis=PCT_AXIS))
    curve = base.mark_area(opacity=0.25, line={"color": "#1D4ED8"}, color="#1D4ED8").encode(
        y=alt.Y("cumulative_share:Q", title="Cumulative share of sales", axis=PCT_AXIS),
        tooltip=[alt.Tooltip("sku:N"), alt.Tooltip("abc_class:N"),
                 alt.Tooltip("cumulative_share:Q", format=".1%")],
    )
    rules = alt.Chart(pd.DataFrame({"y": [0.80, 0.95]})).mark_rule(strokeDash=[4, 4], color="#94A3B8").encode(y="y:Q")
    return alt.layer(curve, rules).properties(height=height).configure_view(strokeWidth=0)


def uk_site_map(df: pd.DataFrame, size_col: str, colour_col: str, height: int = 420) -> alt.Chart:
    """Dot map of UK sites on a lat/long plane (no remote tiles, SiS-safe)."""
    return _base(
        alt.Chart(df).mark_circle(opacity=0.85, stroke="#0B1F3A", strokeWidth=1).encode(
            longitude="longitude:Q",
            latitude="latitude:Q",
            size=alt.Size(f"{size_col}:Q", scale=alt.Scale(range=[150, 1800]), legend=None),
            color=alt.Color(f"{colour_col}:Q", title="Utilisation", scale=alt.Scale(scheme="blues", domain=[0, 1]),
                            legend=alt.Legend(format=".0%", orient="bottom")),
            tooltip=[alt.Tooltip("warehouse_name:N", title="Site"), alt.Tooltip("uk_region:N", title="Region"),
                     alt.Tooltip("capacity_pallets:Q", title="Capacity (pallets)", format=",.0f"),
                     alt.Tooltip(f"{colour_col}:Q", title="Utilisation", format=".1%")],
        ).project(type="mercator"),
        height,
    )
