import altair as alt
import pandas as pd
import streamlit as st

from components import charts
from components.layout import active_filter_caption, apply_filters, kpi, page_header
from inventory360.analytics.abc import abc_classify
from inventory360.data_access import queries
from inventory360.utils.config import STOCK_STATUS_ORDER
from inventory360.utils.formatting import fmt_gbp, fmt_int, fmt_pct

position_all = queries.load_inventory_position()
as_of = position_all["as_of_date"].max()
page_header("Inventory health", "Stock status, cover, ABC segmentation and exception management", ":material/inventory_2:", as_of)
active_filter_caption()

position = apply_filters(position_all)
risk_mask = position["stock_status"].isin(["Out of stock", "Critical", "Low"])
excess_mask = position["stock_status"].isin(["Overstock", "Excess"])

cols = st.columns(4)
with cols[0]:
    kpi("SKU-locations ranged", fmt_int(len(position)), help="Active SKU x distribution site combinations.")
with cols[1]:
    kpi("Stock at cost", fmt_gbp(position["stock_value_gbp"].sum()),
        help=f"Retail value {fmt_gbp(position['stock_retail_value_gbp'].sum())}")
with cols[2]:
    kpi("At-risk lines", fmt_int(risk_mask.sum()),
        help="Out of stock, critical (<3 days cover) or low (<7 days cover).")
with cols[3]:
    kpi("Excess stock value", fmt_gbp(position["excess_stock_value_gbp"].sum()),
        help="Value of stock above 60 days of forward cover.")

tab_status, tab_cover, tab_abc = st.tabs(
    [":material/donut_small: Status mix", ":material/hourglass_bottom: Cover profile", ":material/bar_chart: ABC analysis"]
)

with tab_status:
    c1, c2 = st.columns(2)
    by_cat = position.groupby(["category", "stock_status"], as_index=False).agg(n=("sku", "count"))
    by_site = position.groupby(["warehouse_name", "stock_status"], as_index=False).agg(n=("sku", "count"))
    with c1:
        with st.container(border=True):
            st.subheader("By category", anchor=False)
            st.altair_chart(charts.status_stacked_bar(by_cat, "category", "n"), alt="Stock status mix by category")
    with c2:
        with st.container(border=True):
            st.subheader("By distribution site", anchor=False)
            st.altair_chart(charts.status_stacked_bar(by_site, "warehouse_name", "n"), alt="Stock status mix by site")

with tab_cover:
    bins = [-0.1, 0, 3, 7, 14, 30, 60, 120, float("inf")]
    labels = ["0", "0-3", "3-7", "7-14", "14-30", "30-60", "60-120", "120+"]
    cover = position[position["avg_daily_demand"] > 0].copy()
    cover["cover_band"] = pd.cut(cover["days_of_cover"].fillna(0), bins=bins, labels=labels).astype(str)
    band = cover.groupby("cover_band", as_index=False).agg(
        sku_locations=("sku", "count"), stock_value_gbp=("stock_value_gbp", "sum"))
    band["cover_risk"] = band["cover_band"].map(
        lambda b: "Shortage risk" if b in ("0", "0-3", "3-7") else "Excess risk" if b in ("60-120", "120+") else "Healthy")
    with st.container(border=True):
        st.subheader("Days of cover distribution", anchor=False)
        st.caption("Forward cover = stock on hand ÷ average daily demand over the last 28 days")
        st.altair_chart(
            alt.Chart(band).mark_bar(cornerRadiusEnd=3).encode(
                x=alt.X("cover_band:N", sort=labels, title="Days of cover"),
                y=alt.Y("stock_value_gbp:Q", title="Stock value", axis=charts.GBP_AXIS),
                color=alt.Color("cover_risk:N", title=None,
                                scale=alt.Scale(domain=["Shortage risk", "Healthy", "Excess risk"],
                                                range=["#E04F16", "#1D4ED8", "#6941C6"]),
                                legend=alt.Legend(orient="top")),
                tooltip=["cover_band", alt.Tooltip("sku_locations:Q", title="SKU-locations"),
                         alt.Tooltip("stock_value_gbp:Q", format=",.0f", title="Stock £")],
            ).properties(height=300),
            alt="Stock value by days-of-cover band",
        )
    lifecycle = position.groupby("lifecycle_status", as_index=False).agg(
        stock_value_gbp=("stock_value_gbp", "sum"), excess_gbp=("excess_stock_value_gbp", "sum"),
        sku_locations=("sku", "count"))
    lifecycle["excess_share"] = lifecycle["excess_gbp"] / lifecycle["stock_value_gbp"]
    with st.container(border=True):
        st.subheader("Excess by lifecycle", anchor=False)
        st.dataframe(
            lifecycle.sort_values("excess_gbp", ascending=False),
            hide_index=True,
            alt="Excess stock by product lifecycle",
            column_config={
                "lifecycle_status": "Lifecycle",
                "stock_value_gbp": st.column_config.NumberColumn("Stock value", format="£%,.0f"),
                "excess_gbp": st.column_config.NumberColumn("Excess (>60d)", format="£%,.0f"),
                "excess_share": st.column_config.ProgressColumn("Excess share", format="percent", min_value=0, max_value=1),
                "sku_locations": st.column_config.NumberColumn("SKU-locations", format="%,d"),
            },
        )

with tab_abc:
    sales = position.rename(columns={"net_sales_28d_gbp": "sales"})
    abc = abc_classify(sales, "sales")
    planner_class = position.groupby("sku")["velocity_class"].first()
    abc["velocity_class"] = abc["sku"].map(planner_class)
    c1, c2 = st.columns([3, 2])
    with c1:
        with st.container(border=True):
            st.subheader("Pareto of 28-day sales", anchor=False)
            st.altair_chart(charts.pareto(abc), alt="Pareto curve of SKU sales")
    with c2:
        with st.container(border=True):
            st.subheader("Calculated vs planner class", anchor=False)
            st.caption("Mismatches indicate SKUs whose service policy should be reviewed")
            matrix = pd.crosstab(abc["abc_class"], abc["velocity_class"]).reindex(index=["A", "B", "C"], columns=["A", "B", "C"], fill_value=0)
            matrix.index.name = "Sales ABC ↓ / Planner class →"
            st.dataframe(matrix, alt="ABC reclassification matrix")
            mism = (abc["abc_class"] != abc["velocity_class"]).sum()
            st.caption(f"{mism} of {len(abc)} SKUs ({fmt_pct(mism / max(len(abc), 1))}) would change class")

# --------------------------------------------------------------------------- #
# Exception register
# --------------------------------------------------------------------------- #
st.subheader("Exception register", anchor=False)
with st.container(horizontal=True, vertical_alignment="bottom"):
    status_pick = st.pills("Stock status", STOCK_STATUS_ORDER, selection_mode="multi",
                           default=["Out of stock", "Critical", "Low"], key="inv_status_pick")
    search = st.text_input("Search SKU or product", placeholder="e.g. SRG-000123 or kettle", key="inv_search")

ex = position[position["stock_status"].isin(status_pick or STOCK_STATUS_ORDER)]
if search:
    s = search.strip().lower()
    ex = ex[ex["sku"].str.lower().str.contains(s, regex=False) | ex["product_name"].str.lower().str.contains(s, regex=False)]
ex = ex.assign(status_rank=ex["stock_status"].map({k: i for i, k in enumerate(STOCK_STATUS_ORDER)})) \
       .sort_values(["status_rank", "net_sales_28d_gbp"], ascending=[True, False])

st.dataframe(
    ex[["stock_status", "sku", "product_name", "category", "warehouse_name", "velocity_class", "qty_on_hand",
        "avg_daily_demand", "days_of_cover", "inbound_qty", "next_delivery_date", "stock_value_gbp",
        "lost_sales_28d_gbp", "supplier_name"]],
    hide_index=True,
    height=420,
    alt="Inventory exception register",
    column_config={
        "stock_status": "Status",
        "sku": "SKU",
        "product_name": st.column_config.TextColumn("Product", width="large"),
        "category": "Category",
        "warehouse_name": "Site",
        "velocity_class": "Class",
        "qty_on_hand": st.column_config.NumberColumn("On hand", format="%,d"),
        "avg_daily_demand": st.column_config.NumberColumn("Avg daily demand", format="%.1f"),
        "days_of_cover": st.column_config.NumberColumn("Cover (days)", format="%.1f"),
        "inbound_qty": st.column_config.NumberColumn("Inbound", format="%,d"),
        "next_delivery_date": st.column_config.DateColumn("Next delivery", format="DD MMM YYYY"),
        "stock_value_gbp": st.column_config.NumberColumn("Stock value", format="£%,.0f"),
        "lost_sales_28d_gbp": st.column_config.NumberColumn("Lost sales 28d", format="£%,.0f"),
        "supplier_name": "Supplier",
    },
)
st.download_button(
    "Download exceptions (CSV)",
    ex.drop(columns="status_rank").to_csv(index=False).encode("utf-8"),
    file_name=f"inventory_exceptions_{pd.Timestamp(as_of):%Y%m%d}.csv",
    mime="text/csv",
    icon=":material/download:",
)
