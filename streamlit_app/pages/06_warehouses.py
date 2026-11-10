import altair as alt
import pandas as pd
import streamlit as st

from components import charts
from components.layout import active_filter_caption, apply_filters, kpi, page_header
from inventory360.data_access import queries
from inventory360.utils.formatting import fmt_gbp, fmt_int, fmt_pct

util_all = queries.load_warehouse_utilisation()
costs_all = queries.load_warehouse_costs()
as_of = util_all["period_month"].max()

page_header("Warehouse network", "Capacity utilisation, throughput and operating cost across UK distribution sites",
            ":material/warehouse:", queries.load_data_freshness()["as_of_date"].iloc[0])
active_filter_caption()

util = apply_filters(util_all, category_col=None)
costs = apply_filters(costs_all, category_col=None)
current = util[util["period_month"] == as_of]
closed_months = sorted(costs["period_month"].unique())
last_closed = closed_months[-1] if closed_months else None
ltm = util[(util["period_month"] > as_of - pd.DateOffset(months=12)) & util["opex_gbp"].notna()]

cols = st.columns(4)
with cols[0]:
    kpi("Network capacity", f"{fmt_int(current['capacity_pallets'].sum())} pallets", help=f"{len(current)} sites")
with cols[1]:
    used = current["avg_pallets_used"].sum() / current["capacity_pallets"].sum() if len(current) else None
    kpi("Average utilisation (MTD)", fmt_pct(used))
with cols[2]:
    kpi("Operating cost (12 months)", fmt_gbp(ltm["opex_gbp"].sum()))
with cols[3]:
    cpu = ltm["opex_gbp"].sum() / max(ltm["units_dispatched"].sum(), 1)
    kpi("Cost per unit dispatched", f"£{cpu:,.3f}", help="Last 12 closed months.")

left, right = st.columns([2, 3])
with left:
    with st.container(border=True, height="stretch"):
        st.subheader("UK network", anchor=False)
        st.caption("Bubble size = capacity, colour = current utilisation")
        st.altair_chart(charts.uk_site_map(current, "capacity_pallets", "avg_utilisation_pct", height=460),
                        alt="Map of UK distribution sites coloured by utilisation")
with right:
    with st.container(border=True):
        st.subheader("Site performance · last 12 months", anchor=False)
        site = ltm.groupby(["warehouse_code", "warehouse_name", "site_type", "uk_region", "capacity_pallets"], as_index=False).agg(
            avg_util=("avg_utilisation_pct", "mean"), peak_util=("peak_utilisation_pct", "max"),
            units=("units_dispatched", "sum"), opex=("opex_gbp", "sum"), stock=("avg_stock_value_gbp", "mean"))
        site["cost_per_unit"] = site["opex"] / site["units"]
        site["cost_per_pallet_space"] = site["opex"] / site["capacity_pallets"]
        st.dataframe(
            site.sort_values("opex", ascending=False)[
                ["warehouse_name", "site_type", "uk_region", "capacity_pallets", "avg_util", "peak_util", "units",
                 "opex", "cost_per_unit", "cost_per_pallet_space", "stock"]],
            hide_index=True, alt="Site performance table",
            column_config={
                "warehouse_name": "Site", "site_type": "Type", "uk_region": "Region",
                "capacity_pallets": st.column_config.NumberColumn("Capacity", format="%,d"),
                "avg_util": st.column_config.ProgressColumn("Avg utilisation", format="percent", min_value=0, max_value=1),
                "peak_util": st.column_config.NumberColumn("Peak", format="percent"),
                "units": st.column_config.NumberColumn("Units dispatched", format="compact"),
                "opex": st.column_config.NumberColumn("Opex", format="£%,.0f"),
                "cost_per_unit": st.column_config.NumberColumn("£ / unit", format="£%.3f"),
                "cost_per_pallet_space": st.column_config.NumberColumn("£ / pallet space", format="£%.2f"),
                "stock": st.column_config.NumberColumn("Avg stock", format="£%,.0f"),
            },
        )
    with st.container(border=True):
        st.subheader("Utilisation trend", anchor=False)
        st.altair_chart(charts.line(util, "period_month", "avg_utilisation_pct", "warehouse_code", "Utilisation", pct=True, height=240),
                        alt="Monthly utilisation by site")

with st.container(border=True):
    st.subheader("Operating cost mix", anchor=False)
    st.altair_chart(
        alt.Chart(costs).mark_bar().encode(
            x=alt.X("yearmonth(period_month):T", title=None, axis=alt.Axis(format="%b %y")),
            y=alt.Y("sum(actual_cost_gbp):Q", title="Operating cost", axis=charts.GBP_AXIS),
            color=alt.Color("cost_category:N", title=None, legend=alt.Legend(orient="bottom")),
            tooltip=[alt.Tooltip("yearmonth(period_month):T", title="Month"), "cost_category:N",
                     alt.Tooltip("sum(actual_cost_gbp):Q", title="Cost £", format=",.0f")],
        ).properties(height=300),
        alt="Monthly operating cost by category",
    )
    if last_closed is not None:
        st.caption(f"GL actuals to {pd.Timestamp(last_closed):%B %Y} (latest closed period)")
