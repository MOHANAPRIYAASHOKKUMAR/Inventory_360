import pandas as pd
import streamlit as st

from components import charts, filters
from components.layout import day, download, filter_scope, gbp, kpi, num, page_header, pct, section, table
from inventory360.analytics.abc import abc_classify
from inventory360.business_logic.exceptions import AMBER, GREEN, RED
from inventory360.data_access import queries
from inventory360.data_access.queries import POSITION_COLS
from inventory360.utils.config import STOCK_STATUS_ORDER
from inventory360.utils.formatting import fmt_days, fmt_gbp, fmt_int, fmt_pct

STATUS_RAG = {"Out of stock": RED, "Critical": RED, "Low": AMBER, "Healthy": GREEN, "Overstock": AMBER, "Excess": RED}

f = filters.current()
position_all = queries.inventory_position(f)
as_of = position_all["as_of_date"].max() if not position_all.empty else st.session_state["gf_as_of"]
page_header("Inventory health", "Stock position, cover, availability risk and excess across the network", as_of=as_of)
filter_scope(f, POSITION_COLS, use_date=False, note="SKU history drill-down uses the date range")

with st.container(horizontal=True, vertical_alignment="bottom"):
    statuses = st.pills("Stock status", STOCK_STATUS_ORDER, selection_mode="multi", key="inv_status")
    velocity = st.pills("Velocity class", ["A", "B", "C"], selection_mode="multi", key="inv_velocity")
    lifecycle = st.pills("Lifecycle", sorted(position_all["lifecycle_status"].dropna().unique()), selection_mode="multi",
                         key="inv_lifecycle")

position = position_all
if statuses:
    position = position[position["stock_status"].isin(statuses)]
if velocity:
    position = position[position["velocity_class"].isin(velocity)]
if lifecycle:
    position = position[position["lifecycle_status"].isin(lifecycle)]

ranged = position[position["avg_daily_demand"] > 0]
at_risk = position[position["stock_status"].isin(["Out of stock", "Critical"])]
excess = position["excess_stock_value_gbp"].sum()
value = position["stock_value_gbp"].sum()
avg_cover = (ranged["qty_on_hand"].sum() / ranged["avg_daily_demand"].sum()) if not ranged.empty else None
oos_share = (position["stock_status"] == "Out of stock").mean() if len(position) else None

cols = st.columns(5)
with cols[0]:
    kpi("SKU-locations", fmt_int(len(position)), help="Site x SKU combinations in the current filter.")
with cols[1]:
    kpi("Stock value at cost", fmt_gbp(value), help=f"Retail value {fmt_gbp(position['stock_retail_value_gbp'].sum())}")
with cols[2]:
    kpi("At-risk lines", fmt_int(len(at_risk)), status=RED if len(at_risk) else GREEN,
        status_text=f"{fmt_pct(oos_share)} out of stock", help="Out of stock or under 3 days' cover.")
with cols[3]:
    share = excess / value if value else None
    kpi("Excess stock", fmt_gbp(excess), status=RED if (share or 0) > 0.15 else AMBER if (share or 0) > 0.05 else GREEN,
        status_text=f"{fmt_pct(share)} of stock value", help="Stock beyond 60 days of demand, at cost.")
with cols[4]:
    kpi("Forward cover", fmt_days(avg_cover), help="On hand ÷ average daily demand (28-day), demand-weighted.")

tab_status, tab_cover, tab_matrix, tab_abc = st.tabs(["Status by warehouse", "Cover profile", "Warehouse × category", "ABC analysis"])
with tab_status:
    by_wh = position.groupby(["warehouse_name", "stock_status"], as_index=False)["stock_value_gbp"].sum()
    basis = st.segmented_control("Measure", ["Stock value", "SKU-locations"], default="Stock value", key="inv_status_basis",
                                 required=True)
    if basis == "SKU-locations":
        by_wh = position.groupby(["warehouse_name", "stock_status"], as_index=False).agg(stock_value_gbp=("sku", "count"))
    charts.show(charts.bar(by_wh, "warehouse_name", "stock_value_gbp", "stock_status", horizontal=True, height=380,
                           colors=charts.STATUS_COLOURS, kind="num" if basis == "SKU-locations" else "gbp"),
                alt="Stock status mix by warehouse")
with tab_cover:
    bins = [-0.1, 0, 3, 7, 14, 30, 60, 120, float("inf")]
    labels = ["0", "0-3", "3-7", "7-14", "14-30", "30-60", "60-120", "120+"]
    cover = ranged.assign(cover_band=pd.cut(ranged["days_of_cover"].fillna(0), bins=bins, labels=labels).astype(str))
    band = cover.groupby("cover_band", as_index=False).agg(stock_value_gbp=("stock_value_gbp", "sum"), lines=("sku", "count"))
    band["risk"] = band["cover_band"].map(lambda b: "Red" if b in ("0", "0-3") else "Amber" if b in ("3-7", "60-120")
                                          else "Red" if b == "120+" else "Green")
    charts.show(charts.bar(band, "cover_band", "stock_value_gbp", "risk", order=labels, colors=charts.RAG_COLOURS,
                           height=340, value_title="Stock value"),
                alt="Stock value by days-of-cover band")
    st.caption("Days of cover = stock on hand ÷ average daily demand over the last 28 days. Red: under 3 days or over 120; "
               "amber: 3-7 or 60-120 days.")
with tab_matrix:
    measure = st.segmented_control("Show", ["Availability (1 − OOS rate 28d)", "Excess stock (£)"],
                                   default="Availability (1 − OOS rate 28d)", key="inv_matrix", required=True)
    if measure.startswith("Excess"):
        pv = position.pivot_table(index="warehouse_name", columns="category", values="excess_stock_value_gbp", aggfunc="sum").fillna(0)
        charts.show(charts.heatmap(pv, kind="gbp", reverse=True, height=380), alt="Excess stock by warehouse and category")
    else:
        pv = 1 - position.pivot_table(index="warehouse_name", columns="category", values="oos_rate_28d", aggfunc="mean")
        charts.show(charts.heatmap(pv, kind="pct", zmid=0.95, height=380), alt="Availability by warehouse and category")
with tab_abc:
    abc = abc_classify(position.assign(v=position["net_sales_28d_gbp"]), "v")
    abc_curve = abc.assign(rank_pct=abc["rank_pct"], cumulative_share=abc["cumulative_share"])
    c1, c2 = st.columns([2, 1])
    with c1:
        fig = charts.line(abc_curve, "rank_pct", "cumulative_share", "abc_class", kind="pct", height=320,
                          colors={"A": charts.NAVY, "B": charts.TEAL, "C": charts.SLATE})
        fig.update_xaxes(tickformat=".0%", title="Share of SKUs (ranked by 28-day sales)")
        charts.show(fig, alt="Pareto curve of 28-day sales")
    with c2:
        summ = abc.groupby("abc_class", as_index=False).agg(skus=("sku", "count"), sales=("v", "sum"))
        summ["share"] = summ["sales"] / summ["sales"].sum()
        st.dataframe(summ, hide_index=True, alt="ABC class summary",
                     column_config={"abc_class": "Class", "skus": num("SKUs"), "sales": gbp("28-day sales"), "share": pct("Share")})

# --------------------------------------------------------------------------- #
# Exception register with SKU drill-down
# --------------------------------------------------------------------------- #
with section("SKU-location register", "Sorted by risk: out of stock and critical first, then excess value"):
    order = {s: i for i, s in enumerate(["Out of stock", "Critical", "Low", "Excess", "Overstock", "Healthy"])}
    reg = position.assign(rag=position["stock_status"].map(STATUS_RAG), _o=position["stock_status"].map(order)) \
                  .sort_values(["_o", "excess_stock_value_gbp", "lost_sales_28d_gbp"], ascending=[True, False, False])
    sel = table(
        reg, key="inv_register", alt="SKU-location exception register", csv_name="inventory register", rag_cols=["rag"],
        height=440,
        columns=["rag", "stock_status", "warehouse_code", "sku", "product_name", "category", "supplier_name", "velocity_class",
                 "qty_on_hand", "avg_daily_demand", "days_of_cover", "reorder_point_qty", "inbound_qty", "next_delivery_date",
                 "stock_value_gbp", "excess_stock_value_gbp", "lost_sales_28d_gbp", "replenishment_priority"],
        column_config={
            "rag": "RAG", "stock_status": "Status", "warehouse_code": "Site", "sku": "SKU",
            "product_name": st.column_config.TextColumn("Product", width="medium"), "category": "Category",
            "supplier_name": "Supplier", "velocity_class": "Class", "qty_on_hand": num("On hand"),
            "avg_daily_demand": num("Demand/day", 1), "days_of_cover": num("Cover", 1, " d"),
            "reorder_point_qty": num("Reorder pt"), "inbound_qty": num("Inbound"), "next_delivery_date": day("Next delivery"),
            "stock_value_gbp": gbp("Stock value"), "excess_stock_value_gbp": gbp("Excess"),
            "lost_sales_28d_gbp": gbp("Lost sales 28d"), "replenishment_priority": "Priority",
        },
    )

if sel is not None:
    with section(f"Drill-down · {sel['product_name']} at {sel['warehouse_name']}",
                 f"{sel['sku']} · {sel['supplier_name']} · lead time {sel['lead_time_days']:.0f} days · "
                 f"MOQ {sel['min_order_qty']:,.0f} · {f.start:%d %b %Y} – {f.end:%d %b %Y}"):
        hist = queries.sku_history(f, sel["sku"], sel["warehouse_code"])
        c1, c2 = st.columns([3, 1])
        with c1:
            long = hist.melt(id_vars="snapshot_date", value_vars=["qty_on_hand", "units_demanded"], var_name="measure",
                             value_name="units").replace({"qty_on_hand": "On hand", "units_demanded": "Demand"})
            fig = charts.line(long, "snapshot_date", "units", "measure", kind="num", height=320,
                              target=float(sel["reorder_point_qty"]), target_label="Reorder point",
                              colors={"On hand": charts.NAVY, "Demand": charts.TEAL})
            charts.show(fig, alt="Daily on-hand stock and demand for the selected SKU-location")
        with c2:
            st.metric("Safety stock", f"{sel['safety_stock_qty']:,.0f} units", border=True)
            st.metric("Order-up-to level", f"{sel['order_up_to_qty']:,.0f} units", border=True)
            st.metric("Recommended order", f"{sel['recommended_order_qty']:,.0f} units", border=True)
        download(hist, f"{sel['sku']} {sel['warehouse_code']} history", key="dl_inv_drill")
