import pandas as pd
import streamlit as st

from components import charts, filters
from components.layout import download, filter_scope, gbp, kpi, num, page_header, pct, section, table
from inventory360.analytics.kpis import bucket
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.data_access import queries
from inventory360.data_access.queries import CUSTOMER_COLS
from inventory360.utils.formatting import fmt_gbp, fmt_int, fmt_pct

CHANNELS = ["Own stores", "Franchise", "Wholesale", "Online"]

f = filters.current()
page_header("Customers & sales", "Sales, margin and service by customer account and channel", f, st.session_state["gf_as_of"])
filter_scope(f, CUSTOMER_COLS)

with st.container(horizontal=True, vertical_alignment="bottom"):
    channels = st.pills("Channel", CHANNELS, selection_mode="multi", key="cust_channels")
    grain = st.segmented_control("Granularity", ["Daily", "Weekly", "Monthly"], default="Weekly", key="cust_grain",
                                 required=True)
    top_n = st.segmented_control("Top customers", [10, 20, 36], default=10, key="cust_topn", required=True)

summary = queries.customer_summary(f)
daily = queries.customer_sales_daily(f)
prior = queries.customer_summary(f.prior())
if channels:
    summary = summary[summary["channel"].isin(channels)]
    daily = daily[daily["channel"].isin(channels)]
    prior = prior[prior["channel"].isin(channels)]

cur_d = daily[daily["sales_date"].between(pd.Timestamp(f.start), pd.Timestamp(f.end))]


def totals(df: pd.DataFrame) -> dict:
    net, dem = df["net_sales_gbp"].sum(), df["units_demanded"].sum()
    return {"net": net, "gp": df["gross_profit_gbp"].sum(), "lost": df["lost_sales_gbp"].sum(),
            "gm": df["gross_profit_gbp"].sum() / net if net else None,
            "fill": df["units_sold"].sum() / dem if dem else None,
            "active": int((df["net_sales_gbp"] > 0).sum())}


t, p = totals(summary), totals(prior)
top5_share = summary.nlargest(5, "net_sales_gbp")["net_sales_gbp"].sum() / t["net"] if t["net"] else None

cols = st.columns(5)
with cols[0]:
    kpi("Net sales", fmt_gbp(t["net"]), current=t["net"], previous=p["net"],
        spark=bucket(cur_d, "sales_date", "Weekly", ["net_sales_gbp"])["net_sales_gbp"])
with cols[1]:
    kpi("Gross profit", fmt_gbp(t["gp"]), current=t["gp"], previous=p["gp"])
with cols[2]:
    kpi("Gross margin", fmt_pct(t["gm"]), current=t["gm"], previous=p["gm"], points=True,
        status=rag_for("gross_margin", t["gm"]), status_text=f"Target ≥ {fmt_pct(TARGETS['gross_margin'].green, 0)}")
with cols[3]:
    kpi("Customer fill rate", fmt_pct(t["fill"]), current=t["fill"], previous=p["fill"], points=True,
        status=rag_for("fill_rate", t["fill"]), status_text=f"Target ≥ {fmt_pct(TARGETS['fill_rate'].green, 0)}")
with cols[4]:
    kpi("Active customers", fmt_int(t["active"]), current=t["active"], previous=p["active"],
        help=f"Top-5 customers account for {fmt_pct(top5_share)} of net sales.")

left, right = st.columns([3, 2])
with left:
    with section("Sales trend by channel", f"{grain} net sales"):
        trend = bucket(cur_d, "sales_date", grain, ["net_sales_gbp"], by=["channel"])
        charts.show(charts.bar(trend, "period", "net_sales_gbp", "channel", height=320,
                               order=CHANNELS, value_title="Net sales (£)", category_title="Period"),
                    alt="Net sales trend by channel")
with right:
    with section("Channel mix", "Share of net sales", height="stretch"):
        mix = summary.groupby("channel", as_index=False)["net_sales_gbp"].sum()
        charts.show(charts.donut(mix, "channel", "net_sales_gbp", kind="gbp", order=CHANNELS, height=320),
                    alt="Net sales by channel")

left, right = st.columns([2, 3])
with left:
    with section(f"Top {top_n} customers", "Net sales in the period"):
        top = summary.nlargest(int(top_n), "net_sales_gbp")
        charts.show(charts.bar(top, "customer_name", "net_sales_gbp", "channel", horizontal=True, height=34 * len(top) + 80,
                               order=top["customer_name"].tolist(),
                               value_title="Net sales (£)", category_title="Customer"), alt="Top customers by net sales")
with right:
    with section("Category mix by channel", "Net sales (£)"):
        cm = queries.customer_category_mix(f)
        if channels:
            cm = cm[cm["channel"].isin(channels)]
        pivot = cm.pivot_table(index="category", columns="channel", values="net_sales_gbp", aggfunc="sum").fillna(0)
        pivot = pivot[[c for c in CHANNELS if c in pivot.columns]]
        pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
        fig = charts.heatmap(pivot, kind="gbp", height=34 * len(pivot) + 90)
        fig.data[0].colorscale = [[0, "#F0FDFA"], [1, charts.TEAL]]
        charts.show(fig, alt="Net sales by category and channel")

with section("Customer scorecard", "Select a customer to drill into weekly sales and category mix"):
    summary = summary.assign(
        sales_share=summary["net_sales_gbp"] / t["net"] if t["net"] else 0,
        margin_status=summary["gross_margin"].map(lambda v: rag_for("gross_margin", v)),
        fill_status=summary["fill_rate"].map(lambda v: rag_for("fill_rate", v)),
    ).merge(prior[["customer_id", "net_sales_gbp"]].rename(columns={"net_sales_gbp": "prior_sales"}), on="customer_id", how="left")
    summary["growth"] = summary["net_sales_gbp"] / summary["prior_sales"].where(summary["prior_sales"] > 0) - 1
    sel = table(
        summary.sort_values("net_sales_gbp", ascending=False), key="cust_table", alt="Customer scorecard",
        csv_name="customer scorecard", rag_cols=["margin_status", "fill_status"], height=420,
        columns=["customer_id", "customer_name", "channel", "customer_segment", "warehouse_name", "account_manager",
                 "net_sales_gbp", "sales_share", "growth", "gross_profit_gbp", "gross_margin", "margin_status",
                 "fill_rate", "fill_status", "lost_sales_gbp", "skus_bought", "credit_terms_days", "credit_limit_gbp"],
        column_config={
            "customer_id": "ID", "customer_name": st.column_config.TextColumn("Customer", width="medium"),
            "channel": "Channel", "customer_segment": "Segment", "warehouse_name": "Served from",
            "account_manager": "Account manager", "net_sales_gbp": gbp("Net sales"), "sales_share": pct("Share"),
            "growth": pct("vs prior"), "gross_profit_gbp": gbp("Gross profit"), "gross_margin": pct("Margin"),
            "margin_status": "Margin RAG", "fill_rate": pct("Fill rate"), "fill_status": "Fill RAG",
            "lost_sales_gbp": gbp("Lost sales"), "skus_bought": num("SKUs"),
            "credit_terms_days": num("Terms", suffix=" d"), "credit_limit_gbp": gbp("Credit limit"),
        },
    )

if sel is not None:
    with section(f"Drill-down · {sel['customer_name']}",
                 f"{sel['channel']} · {sel['customer_segment']} · served from {sel['warehouse_name']} · {sel['account_manager']}"):
        wk = queries.customer_weekly(f, sel["customer_id"])
        c1, c2 = st.columns([3, 2])
        with c1:
            charts.show(charts.bar(wk, "week", "net_sales_gbp", "category", height=320,
                                   value_title="Net sales (£)", category_title="Week"),
                        alt=f"Weekly net sales by category for {sel['customer_name']}")
        with c2:
            cat = wk.groupby("category", as_index=False)[["net_sales_gbp", "lost_sales_gbp"]].sum() \
                    .sort_values("net_sales_gbp", ascending=False)
            st.dataframe(cat, hide_index=True, alt="Category totals for selected customer", height=320,
                         column_config={"category": "Category", "net_sales_gbp": gbp("Net sales"),
                                        "lost_sales_gbp": gbp("Lost sales")})
        download(wk, f"{sel['customer_name']} weekly sales", key="dl_cust_drill")
