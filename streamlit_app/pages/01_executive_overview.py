import pandas as pd
import streamlit as st

from components import charts
from components.layout import active_filter_caption, apply_filters, kpi, page_header
from inventory360.analytics.kpis import comparison_window, period_kpis, weekly_trend
from inventory360.business_logic.budget import full_year_outturn
from inventory360.business_logic.replenishment import status_summary
from inventory360.data_access import queries
from inventory360.utils.formatting import fmt_days, fmt_gbp, fmt_int, fmt_pct

daily_all = queries.load_network_daily_trend()
as_of = daily_all["snapshot_date"].max()

page_header("Executive overview", "Network-wide inventory, availability, supplier and cost position", ":material/dashboard:", as_of)
active_filter_caption()

WINDOWS = {"Last 4 weeks": 28, "Last 13 weeks": 91, "Last 52 weeks": 364}
window = st.segmented_control("Reporting period", list(WINDOWS), default="Last 4 weeks", key="exec_window")
days = WINDOWS[window or "Last 4 weeks"]

daily = apply_filters(daily_all)
cur_s, cur_e, prev_s, prev_e = comparison_window(as_of, days)
cur = period_kpis(daily, cur_s, cur_e)
prev = period_kpis(daily, prev_s, prev_e)
weekly = weekly_trend(daily)
spark = weekly.tail(26)

# --------------------------------------------------------------------------- #
# Headline KPIs
# --------------------------------------------------------------------------- #
row1 = st.columns(4)
with row1[0]:
    kpi("Stock value at cost", fmt_gbp(cur.closing_stock_value_gbp), cur.closing_stock_value_gbp,
        prev.closing_stock_value_gbp, inverse=True, spark=spark["stock_value_gbp"],
        help="Closing on-hand stock valued at standard unit cost.")
with row1[1]:
    kpi("Net sales", fmt_gbp(cur.net_sales_gbp), cur.net_sales_gbp, prev.net_sales_gbp,
        spark=spark["net_sales_gbp"], help="Net sales fulfilled from the DC network in the period.")
with row1[2]:
    kpi("On-shelf availability", fmt_pct(cur.availability), cur.availability, prev.availability,
        as_points=True, spark=spark["availability"],
        help="Share of ranged SKU-locations with stock on hand, averaged across days.")
with row1[3]:
    kpi("Lost sales (stockouts)", fmt_gbp(cur.lost_sales_gbp), cur.lost_sales_gbp, prev.lost_sales_gbp,
        inverse=True, spark=spark["lost_sales_gbp"], help="Unfulfilled demand valued at retail price.")

row2 = st.columns(4)
with row2[0]:
    kpi("Gross margin", fmt_pct(cur.gross_margin_pct), cur.gross_margin_pct, prev.gross_margin_pct, as_points=True)
with row2[1]:
    kpi("Demand fill rate", fmt_pct(cur.fill_rate), cur.fill_rate, prev.fill_rate, as_points=True,
        help="Units sold ÷ units demanded.")
with row2[2]:
    kpi("Stock turn (annualised)", f"{cur.stock_turns:.1f}x" if cur.stock_turns else "–",
        cur.stock_turns, prev.stock_turns)
with row2[3]:
    kpi("Days of cover", fmt_days(cur.days_cover), cur.days_cover, prev.days_cover, inverse=True,
        help="Closing stock value ÷ average daily cost of sales.")

# --------------------------------------------------------------------------- #
# Trends and current position
# --------------------------------------------------------------------------- #
left, right = st.columns([2, 1])
with left:
    with st.container(border=True):
        st.subheader("Stock investment vs availability", anchor=False)
        st.caption("Weekly average stock value (area, left axis) and on-shelf availability (line, right axis)")
        st.altair_chart(
            charts.area_with_line(weekly, "week", "stock_value_gbp", "availability", "Stock value", "Availability"),
            alt="Weekly stock value and availability trend",
        )

position = apply_filters(queries.load_inventory_position())
summary = status_summary(position)
with right:
    with st.container(border=True, height="stretch"):
        st.subheader("Current stock status", anchor=False)
        basis = st.segmented_control("Measure", ["SKU-locations", "Stock value"], default="SKU-locations",
                                     key="exec_status_basis", label_visibility="collapsed")
        value_col = "stock_value_gbp" if basis == "Stock value" else "sku_locations"
        st.altair_chart(charts.status_donut(summary, value_col), alt="Stock status distribution")

# --------------------------------------------------------------------------- #
# Category scorecard
# --------------------------------------------------------------------------- #
window_rows = daily[(daily["snapshot_date"] >= cur_s) & (daily["snapshot_date"] <= cur_e)]
cat_days = window_rows.groupby(["category", "snapshot_date"], as_index=False).sum(numeric_only=True)
cat = cat_days.groupby("category", as_index=False).agg(
    net_sales_gbp=("net_sales_gbp", "sum"),
    cogs_gbp=("cogs_gbp", "sum"),
    avg_stock_gbp=("stock_value_gbp", "mean"),
    lost_sales_gbp=("lost_sales_gbp", "sum"),
    sku_locations=("sku_locations", "sum"),
    sku_locations_oos=("sku_locations_oos", "sum"),
    days=("snapshot_date", "nunique"),
)
cat["gross_margin"] = (cat["net_sales_gbp"] - cat["cogs_gbp"]) / cat["net_sales_gbp"]
cat["availability"] = 1 - cat["sku_locations_oos"] / cat["sku_locations"]
cat["stock_turn"] = cat["cogs_gbp"] / cat["days"] * 365 / cat["avg_stock_gbp"]
cat["sales_share"] = cat["net_sales_gbp"] / cat["net_sales_gbp"].sum()
cat = cat.sort_values("net_sales_gbp", ascending=False)

with st.container(border=True):
    st.subheader("Category scorecard", anchor=False)
    st.caption(f"{window} · {cur_s:%d %b %Y} to {cur_e:%d %b %Y}")
    st.dataframe(
        cat[["category", "net_sales_gbp", "sales_share", "gross_margin", "avg_stock_gbp", "stock_turn",
             "availability", "lost_sales_gbp"]],
        hide_index=True,
        alt="Category performance scorecard",
        column_config={
            "category": st.column_config.TextColumn("Category"),
            "net_sales_gbp": st.column_config.NumberColumn("Net sales", format="£%,.0f"),
            "sales_share": st.column_config.ProgressColumn("Sales mix", format="percent", min_value=0, max_value=float(cat["sales_share"].max() or 1)),
            "gross_margin": st.column_config.NumberColumn("Gross margin", format="percent"),
            "avg_stock_gbp": st.column_config.NumberColumn("Avg stock", format="£%,.0f"),
            "stock_turn": st.column_config.NumberColumn("Stock turn", format="%.1fx"),
            "availability": st.column_config.NumberColumn("Availability", format="percent"),
            "lost_sales_gbp": st.column_config.NumberColumn("Lost sales", format="£%,.0f"),
        },
    )

# --------------------------------------------------------------------------- #
# Cross-functional alerts
# --------------------------------------------------------------------------- #
scorecard = queries.load_supplier_scorecard()
bva = queries.load_budget_vs_actual()
fy = bva.loc[bva["period_month"] <= as_of, "fiscal_year"].max()
outturn = full_year_outturn(bva, fy)
in_flight = apply_filters(queries.load_shipments_in_flight(), category_col=None)
late_in_flight = in_flight[(in_flight["planned_arrival"] < as_of) & (in_flight["shipment_status"] == "IN_TRANSIT")]

p1 = position[position["replenishment_priority"] == "P1 - Urgent"]
high_risk = scorecard[scorecard["risk_rating"] == "High"]
ytd_var = outturn["ytd_variance_gbp"].sum()
excess_value = position["excess_stock_value_gbp"].sum()

st.subheader("Management attention", anchor=False)
alerts = st.columns(4)
with alerts[0]:
    with st.container(border=True, height="stretch"):
        st.markdown(":material/priority_high: **Urgent replenishment**")
        st.markdown(f"### {fmt_int(len(p1))} lines")
        st.caption(f"A-class SKU-locations out of stock or critical · {fmt_gbp(p1['recommended_order_value_gbp'].sum())} to order")
        st.page_link("pages/03_replenishment.py", label="Open planner", icon=":material/arrow_forward:")
with alerts[1]:
    with st.container(border=True, height="stretch"):
        st.markdown(":material/warning: **High-risk suppliers**")
        st.markdown(f"### {len(high_risk)} of {len(scorecard)}")
        st.caption(f"{fmt_gbp(high_risk['spend_gbp'].sum())} of 12-month spend at risk")
        st.page_link("pages/04_suppliers.py", label="Supplier scorecard", icon=":material/arrow_forward:")
with alerts[2]:
    with st.container(border=True, height="stretch"):
        st.markdown(":material/account_balance_wallet: **Budget position**")
        st.markdown(f"### {fmt_gbp(ytd_var)} {'over' if ytd_var > 0 else 'under'}")
        st.caption(f"{fy} year-to-date variance across purchases, freight and warehousing")
        st.page_link("pages/07_budget_and_costs.py", label="Budget & costs", icon=":material/arrow_forward:")
with alerts[3]:
    with st.container(border=True, height="stretch"):
        st.markdown(":material/inventory: **Excess stock**")
        st.markdown(f"### {fmt_gbp(excess_value)}")
        st.caption(f"Stock beyond 60 days' cover · {len(late_in_flight)} inbound shipments overdue")
        st.page_link("pages/02_inventory_health.py", label="Inventory health", icon=":material/arrow_forward:")

# --------------------------------------------------------------------------- #
# Narrative insights (rule-based, recomputed for the current filter)
# --------------------------------------------------------------------------- #
insights = []
if cur.availability is not None and prev.availability is not None:
    move = (cur.availability - prev.availability) * 100
    insights.append(f"Availability is **{fmt_pct(cur.availability)}**, {'up' if move >= 0 else 'down'} "
                    f"{abs(move):.2f} pts on the prior period; stockouts cost **{fmt_gbp(cur.lost_sales_gbp)}** in lost sales.")
if not cat.empty:
    worst = cat.sort_values("availability").iloc[0]
    insights.append(f"**{worst['category']}** has the weakest availability ({fmt_pct(worst['availability'])}) "
                    f"with {fmt_gbp(worst['lost_sales_gbp'])} lost sales.")
    slow = cat.sort_values("stock_turn").iloc[0]
    insights.append(f"**{slow['category']}** is the slowest-turning category at {slow['stock_turn']:.1f}x, "
                    f"holding {fmt_gbp(slow['avg_stock_gbp'])} of stock on average.")
if not high_risk.empty:
    top = high_risk.sort_values("spend_gbp", ascending=False).iloc[0]
    insights.append(f"Largest high-risk supplier is **{top['supplier_name']}** ({top['country_name']}) with "
                    f"{fmt_pct(top['otif_rate'])} OTIF on {fmt_gbp(top['spend_gbp'])} spend.")
freight = outturn[outturn["budget_area"] == "Freight & Duty"]
if not freight.empty and pd.notna(freight["ytd_variance_pct"].iloc[0]):
    insights.append(f"Freight & duty is {fmt_pct(freight['ytd_variance_pct'].iloc[0], signed=True)} against "
                    f"{fy} budget year to date, driven by the winter sea-freight surcharge.")

with st.container(border=True):
    st.subheader("Key insights", anchor=False)
    for line in insights:
        st.markdown(f"- {line}")
