"""KPI drill-down dialogs.

``open_for(metric, f)`` opens a dialog that breaks a KPI down by region, warehouse,
category, SKU and (for sales KPIs) customer, honouring the global filters. Every
query runs on the session's caller's-rights connection, so Snowflake applies the
viewer's own access. Each tab has a chart, a table and a CSV export.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from components import charts
from components.layout import download, gbp, num, pct
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.data_access import queries
from inventory360.data_access.filters import GlobalFilters

# metric -> (column in inventory_breakdown, label, kind, RAG target key or None, sort ascending = worst first)
FLOW_METRICS = {
    "availability": ("availability", "On-shelf availability", "pct", "availability", True),
    "fill_rate": ("fill_rate", "Demand fill rate", "pct", "fill_rate", True),
    "gross_margin": ("gross_margin", "Gross margin", "pct", "gross_margin", True),
    "stock_turns": ("stock_turns", "Stock turn", "ratio", "stock_turns", True),
    "net_sales": ("net_sales_gbp", "Net sales", "gbp", None, False),
    "lost_sales": ("lost_sales_gbp", "Lost sales", "gbp", None, False),
    "lost_sales_share": ("lost_sales_gbp", "Lost sales", "gbp", None, False),
}
# metric -> (column in inventory_position, label, kind, filter)
POSITION_METRICS = {
    "excess_value": ("excess_stock_value_gbp", "Excess stock value", "gbp", None),
    "days_cover": ("stock_value_gbp", "Stock value (cover)", "gbp", None),
    "p1_replenishment": ("recommended_order_value_gbp", "Urgent order value (P1)", "gbp", "P1 - Urgent"),
}
PAGE_LINKS = {
    "overdue_shipments": ("pages/05_logistics.py", "Open Logistics & freight"),
    "high_risk_suppliers": ("pages/04_suppliers.py", "Open Supplier performance"),
    "budget_variance": ("pages/07_budget_and_costs.py", "Open Budget & costs"),
}
CUSTOMER_METRICS = {"net_sales", "fill_rate", "gross_margin", "lost_sales", "lost_sales_share"}
TOP_N = 25
UNITS = {"gbp": " (£)", "pct": " (%)", "ratio": " (x)"}


def available(metric: str) -> bool:
    return metric in FLOW_METRICS or metric in POSITION_METRICS or metric in PAGE_LINKS


def _cfg(col: str, label: str, kind: str):
    return {"pct": pct(label), "gbp": gbp(label), "ratio": num(label, 1, "x")}.get(kind, num(label))


def _tab(df: pd.DataFrame, dim: str, dim_label: str, col: str, label: str, kind: str, target_key: str | None,
         ascending: bool, name: str) -> None:
    if df.empty:
        st.info("No data for the current filters.", icon=":material/info:")
        return
    df = df.sort_values(col, ascending=ascending, na_position="last")
    if target_key:
        df = df.assign(status=df[col].map(lambda v: rag_for(target_key, v)))
    shown = df.head(TOP_N)
    target = TARGETS[target_key].green if target_key else None
    fig = charts.bar(shown, dim, col, "status" if target_key else None, kind="dec" if kind == "ratio" else kind,
                     horizontal=True, height=max(260, 22 * len(shown) + 60),
                     colors=charts.RAG_COLOURS if target_key else None, value_title=label + UNITS.get(kind, ""), category_title=dim_label)
    if target is not None:
        fig.add_vline(x=target, line_dash="dot", line_color=charts.SLATE,
                      annotation_text=f"Target {target:.0%}" if kind == "pct" else f"Target {target:g}")
    charts.show(fig, alt=f"{label} by {dim_label.lower()}")
    cols = [dim, col] + (["status"] if target_key else [])
    st.caption(f"Showing {len(shown)} of {len(df)} {dim_label.lower()}s" + (" · worst first" if ascending else ""))
    st.dataframe(shown[cols], hide_index=True, alt=f"{label} by {dim_label.lower()} table",
                 column_config={dim: dim_label, col: _cfg(col, label, kind), "status": "Status"})
    download(df[cols], f"{name} by {dim_label}", key=f"dl_drill_{name}_{dim}")


@st.dialog("KPI drill-down", width="large")
def _flow_dialog(metric: str, f: GlobalFilters) -> None:
    col, label, kind, target_key, asc = FLOW_METRICS[metric]
    st.subheader(label, anchor=False)
    st.caption(f"{f.start:%d %b %Y} – {f.end:%d %b %Y} · global filters applied")
    whs = queries.load_warehouses()[["warehouse_code", "warehouse_name", "uk_region"]]
    tabs = ["Region", "Warehouse", "Category", "SKU"] + (["Customer"] if metric in CUSTOMER_METRICS else [])
    t = dict(zip(tabs, st.tabs(tabs)))

    by_wh = queries.inventory_breakdown(f, ("warehouse_code",)).merge(whs, on="warehouse_code", how="left")
    with t["Region"]:
        sums = ["net_sales_gbp", "cogs_gbp", "lost_sales_gbp", "units_demanded", "units_sold", "sku_locations",
                "sku_locations_oos", "avg_stock_value_gbp"]
        reg = by_wh.groupby("uk_region", as_index=False).agg({**{c: "sum" for c in sums}, "days": "max"})
        reg["availability"] = 1 - reg["sku_locations_oos"] / reg["sku_locations"]
        reg["fill_rate"] = reg["units_sold"] / reg["units_demanded"].where(reg["units_demanded"] > 0)
        reg["gross_margin"] = (reg["net_sales_gbp"] - reg["cogs_gbp"]) / reg["net_sales_gbp"].where(reg["net_sales_gbp"] > 0)
        reg["stock_turns"] = (reg["cogs_gbp"] / reg["days"] * 365) / reg["avg_stock_value_gbp"].where(reg["avg_stock_value_gbp"] > 0)
        _tab(reg, "uk_region", "Region", col, label, kind, target_key, asc, metric)
    with t["Warehouse"]:
        _tab(by_wh, "warehouse_name", "Warehouse", col, label, kind, target_key, asc, metric)
    with t["Category"]:
        _tab(queries.inventory_breakdown(f, ("category",)), "category", "Category", col, label, kind, target_key, asc, metric)
    with t["SKU"]:
        sku = queries.inventory_breakdown(f, ("sku",))
        names = queries.load_products()[["sku", "product_name"]]
        sku = sku.merge(names, on="sku", how="left")
        sku["product"] = sku["product_name"].fillna(sku["sku"]) + " (" + sku["sku"] + ")"
        if asc:   # rates: ignore SKUs with negligible demand so the list is meaningful
            sku = sku[sku["units_demanded"] >= sku["units_demanded"].quantile(0.25)]
        _tab(sku, "product", "SKU", col, label, kind, target_key, asc, metric)
    if "Customer" in t:
        with t["Customer"]:
            cust = queries.customer_summary(f)
            ccol = {"net_sales_gbp": "net_sales_gbp", "lost_sales_gbp": "lost_sales_gbp", "fill_rate": "fill_rate",
                    "gross_margin": "gross_margin"}[col]
            _tab(cust, "customer_name", "Customer", ccol, label, kind, target_key, asc, metric)


@st.dialog("KPI drill-down", width="large")
def _position_dialog(metric: str, f: GlobalFilters) -> None:
    col, label, kind, priority = POSITION_METRICS[metric]
    st.subheader(label, anchor=False)
    st.caption("Latest stock snapshot · global filters applied (date range not applicable)")
    pos = queries.inventory_position(f)
    if priority:
        pos = pos[pos["replenishment_priority"] == priority]
    pos = pos.assign(product=pos["product_name"] + " (" + pos["sku"] + ")")
    t = st.tabs(["Region", "Warehouse", "Category", "SKU"])
    for tab, dim, dim_label in zip(t, ["uk_region", "warehouse_name", "category", "product"],
                                   ["Region", "Warehouse", "Category", "SKU"]):
        with tab:
            grouped = pos.groupby(dim, as_index=False)[col].sum()
            _tab(grouped[grouped[col] > 0], dim, dim_label, col, label, kind, None, False, metric)


def open_for(metric: str, f: GlobalFilters) -> None:
    if metric in FLOW_METRICS:
        _flow_dialog(metric, f)
    elif metric in POSITION_METRICS:
        _position_dialog(metric, f)
    elif metric in PAGE_LINKS:
        page, label = PAGE_LINKS[metric]
        st.switch_page(page)
