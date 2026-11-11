import pandas as pd
import streamlit as st

from components import charts, drilldown, filters
from components.layout import download, filter_scope, gbp, kpi, num, page_header, pct, rag_badge, section, table
from inventory360.analytics.kpis import bucket, period_kpis
from inventory360.business_logic import insights
from inventory360.business_logic import kpi_framework as kf
from inventory360.business_logic.budget import full_year_outturn
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.business_logic.replenishment import status_summary
from inventory360.data_access import queries
from inventory360.data_access.queries import CUSTOMER_COLS
from inventory360.utils.config import STOCK_STATUS_ORDER
from inventory360.utils.formatting import fmt_days, fmt_gbp, fmt_int, fmt_pct

f = filters.current()
as_of = st.session_state["gf_as_of"]
page_header("Executive overview", "Network-wide sales, inventory, availability and exceptions", f, as_of)
filter_scope(f, CUSTOMER_COLS, note="customer filter applies to sales KPIs; inventory KPIs cover all customers")

grain = st.segmented_control("Trend granularity", ["Daily", "Weekly", "Monthly"], default="Weekly", key="exec_grain",
                             required=True, help="Applies to the stock and sales trend charts below.")

# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
inv = queries.inventory_daily(f)
sales = queries.customer_sales_daily(f)
cur_s, cur_e = pd.Timestamp(f.start), pd.Timestamp(f.end)
prior = f.prior()
cur = period_kpis(inv, cur_s, cur_e)
prev = period_kpis(inv, pd.Timestamp(prior.start), pd.Timestamp(prior.end))


def _sales_window(start, end) -> dict:
    w = sales[(sales["sales_date"] >= start) & (sales["sales_date"] <= end)]
    net, gp, dem = w["net_sales_gbp"].sum(), w["gross_profit_gbp"].sum(), w["units_demanded"].sum()
    return {"net": net, "gm": gp / net if net else None, "lost": w["lost_sales_gbp"].sum(),
            "fill": w["units_sold"].sum() / dem if dem else None}


s_cur = _sales_window(cur_s, cur_e)
s_prev = _sales_window(pd.Timestamp(prior.start), pd.Timestamp(prior.end))
lost_share = s_cur["lost"] / (s_cur["net"] + s_cur["lost"]) if s_cur["net"] else None

inv_cur = inv[inv["snapshot_date"].between(cur_s, cur_e)]
trend = bucket(inv_cur, "snapshot_date", grain,
               sums=["net_sales_gbp", "cogs_gbp", "lost_sales_gbp", "sku_locations", "sku_locations_oos"],
               means=["stock_value_gbp"])
trend["availability"] = 1 - trend["sku_locations_oos"] / trend["sku_locations"]
spark = trend.tail(26)

position = queries.inventory_position(f)
scorecard = queries.load_supplier_scorecard()
if f.suppliers:
    scorecard = scorecard[scorecard["supplier_id"].isin(f.suppliers)]
bva = queries.load_budget_vs_actual()
fy = bva.loc[bva["period_month"] <= as_of, "fiscal_year"].max()
outturn = full_year_outturn(bva, fy)
ytd_var_pct = outturn["ytd_variance_gbp"].sum() / outturn["budget_ytd_gbp"].sum()
in_flight = queries.shipments_open(f)
overdue = in_flight[(in_flight["planned_arrival"] < as_of) & (in_flight["shipment_status"] == "IN_TRANSIT")]
p1 = position[position["replenishment_priority"] == "P1 - Urgent"]
high_risk = scorecard[scorecard["risk_rating"] == "High"]

# --------------------------------------------------------------------------- #
# Executive insights (rule-based, ranked by severity then GBP impact)
# --------------------------------------------------------------------------- #
period_label = f"{f.start:%d %b} – {f.end:%d %b %Y}"
results = [
    kf.evaluate("availability", cur.availability, prev.availability),
    kf.evaluate("fill_rate", s_cur["fill"], s_prev["fill"]),
    kf.evaluate("gross_margin", s_cur["gm"], s_prev["gm"]),
    kf.evaluate("lost_sales_share", lost_share),
    kf.evaluate("stock_turns", cur.stock_turns, prev.stock_turns),
    kf.evaluate("days_cover", cur.days_cover, prev.days_cover),
    kf.evaluate("net_sales", s_cur["net"], s_prev["net"]),
    kf.evaluate("budget_variance", abs(ytd_var_pct) if ytd_var_pct == ytd_var_pct else None),
]
stock_value = position["stock_value_gbp"].sum()
facts = {
    "p1_lines": len(p1), "p1_value": p1["recommended_order_value_gbp"].sum(),
    "excess_value": position["excess_stock_value_gbp"].sum(),
    "excess_share": position["excess_stock_value_gbp"].sum() / stock_value if stock_value else None,
    "overdue_shipments": len(overdue), "open_shipments": len(in_flight),
    "high_risk_suppliers": len(high_risk), "high_risk_spend": high_risk["spend_gbp"].sum(),
    "lost_sales": s_cur["lost"], "lost_sales_prev": s_prev["lost"],
}
impacts = {"lost_sales_share": s_cur["lost"], "availability": s_cur["lost"],
           "budget_variance": abs(outturn["ytd_variance_gbp"].sum()), "net_sales": abs(s_cur["net"] - s_prev["net"])}
found = insights.build(results, facts, period_label, impacts)


def _insight_card(i: insights.Insight, idx: int) -> None:
    with st.container(border=True, height="stretch", gap="small"):
        rag_badge(i.severity, i.period)
        st.markdown(f"**{i.title}**")
        st.caption(i.detail)
        if drilldown.available(i.metric) and st.button("Explore", key=f"ins_{idx}", icon=":material/zoom_in:",
                                                       type="tertiary"):
            drilldown.open_for(i.metric, f)


with section("Executive insights", f"{len(found)} items need attention · ranked by severity, then £ impact"
             if found else "Nothing needs attention: every KPI is on target and stable"):
    for start in range(0, min(len(found), 6), 3):
        cols = st.columns(3)
        for col, (idx, item) in zip(cols, list(enumerate(found))[start:start + 3]):
            with col:
                _insight_card(item, idx)
    if len(found) > 6:
        with st.expander(f"{len(found) - 6} more"):
            for idx, item in list(enumerate(found))[6:]:
                _insight_card(item, idx)
    if found:
        download(pd.DataFrame([vars(i) for i in found]).drop(columns="tags"), "executive insights", key="dl_insights")

# --------------------------------------------------------------------------- #
# KPI cards
# --------------------------------------------------------------------------- #
statuses = {
    "gross_margin": rag_for("gross_margin", s_cur["gm"]),
    "availability": rag_for("availability", cur.availability),
    "fill_rate": rag_for("fill_rate", s_cur["fill"]),
    "lost_sales_share": rag_for("lost_sales_share", lost_share),
    "stock_turns": rag_for("stock_turns", cur.stock_turns),
    "days_cover": rag_for("days_cover", cur.days_cover),
}
row = st.columns(4)
with row[0]:
    kpi("Net sales", fmt_gbp(s_cur["net"]), current=s_cur["net"], previous=s_prev["net"],
        spark=spark["net_sales_gbp"], help="Net sales to customers in the selected period.")
with row[1]:
    kpi("Gross margin", fmt_pct(s_cur["gm"]), current=s_cur["gm"], previous=s_prev["gm"], points=True,
        status=statuses["gross_margin"], status_text=f"Target ≥ {fmt_pct(TARGETS['gross_margin'].green, 0)}", key="gross_margin")
with row[2]:
    kpi("Stock value at cost", fmt_gbp(cur.closing_stock_value_gbp), current=cur.closing_stock_value_gbp,
        previous=prev.closing_stock_value_gbp, inverse=True, spark=spark["stock_value_gbp"],
        help="Closing on-hand stock valued at standard unit cost.")
with row[3]:
    kpi("On-shelf availability", fmt_pct(cur.availability), current=cur.availability, previous=prev.availability,
        points=True, spark=spark["availability"], status=statuses["availability"],
        status_text=f"Target ≥ {fmt_pct(TARGETS['availability'].green, 0)}", key="availability")

row = st.columns(4)
with row[0]:
    kpi("Demand fill rate", fmt_pct(s_cur["fill"]), current=s_cur["fill"], previous=s_prev["fill"], points=True,
        status=statuses["fill_rate"], status_text=f"Target ≥ {fmt_pct(TARGETS['fill_rate'].green, 0)}",
        help="Units sold ÷ units demanded.")
with row[1]:
    kpi("Lost sales (stockouts)", fmt_gbp(s_cur["lost"]), current=s_cur["lost"], previous=s_prev["lost"], inverse=True,
        status=statuses["lost_sales_share"], status_text=f"{fmt_pct(lost_share)} of demand value",
        help="Unfulfilled demand valued at retail price.")
with row[2]:
    kpi("Stock turn (annualised)", f"{cur.stock_turns:.1f}x" if cur.stock_turns else "–", current=cur.stock_turns,
        previous=prev.stock_turns, status=statuses["stock_turns"], status_text=f"Target ≥ {TARGETS['stock_turns'].green:.0f}x",
        key="stock_turns")
with row[3]:
    kpi("Days of cover", fmt_days(cur.days_cover), current=cur.days_cover, previous=prev.days_cover, inverse=True,
        status=statuses["days_cover"], status_text=f"Target ≤ {TARGETS['days_cover'].green:.0f} days",
        help="Closing stock value ÷ average daily cost of sales.")

DRILLS = [("net_sales", "Net sales"), ("gross_margin", "Gross margin"), ("availability", "Availability"),
          ("fill_rate", "Fill rate"), ("lost_sales", "Lost sales"), ("stock_turns", "Stock turn"),
          ("excess_value", "Excess stock")]
with st.container(horizontal=True, gap="small", vertical_alignment="center"):
    st.caption("Drill down by region, warehouse, category, SKU or customer:")
    for drill_key, drill_label in DRILLS:
        if st.button(drill_label, key=f"drill_{drill_key}", type="tertiary", icon=":material/zoom_in:"):
            drilldown.open_for(drill_key, f)

# --------------------------------------------------------------------------- #
# Trends
# --------------------------------------------------------------------------- #
left, right = st.columns([2, 1])
with left:
    with section("Stock investment vs availability", f"{grain} average stock value (bars) and on-shelf availability (line)"):
        charts.show(charts.combo(trend, "period", "stock_value_gbp", "availability", "Stock value", "Availability",
                                 line_target=TARGETS["availability"].green), alt="Stock value and availability trend")
with right:
    with section("Current stock status", "Latest snapshot · share of SKU-locations", height="stretch"):
        summary = status_summary(position)
        summary["stock_status"] = summary["stock_status"].astype(str)
        charts.show(charts.donut(summary, "stock_status", "sku_locations", colors=charts.STATUS_COLOURS,
                                 order=STOCK_STATUS_ORDER, height=300), alt="Stock status distribution")

left, right = st.columns([2, 1])
with left:
    with section("Net sales by channel", f"{grain} net sales by customer channel"):
        by_channel = bucket(sales[sales["sales_date"].between(cur_s, cur_e)], "sales_date", grain,
                            sums=["net_sales_gbp"], by=["channel"])
        charts.show(charts.bar(by_channel, "period", "net_sales_gbp", "channel", height=300),
                    alt="Net sales by customer channel over time")
with right:
    with section("Exception register", "KPIs against policy targets", height="stretch"):
        values = {"gross_margin": s_cur["gm"], "availability": cur.availability, "fill_rate": s_cur["fill"],
                  "lost_sales_share": lost_share, "stock_turns": cur.stock_turns, "days_cover": cur.days_cover}
        reg = pd.DataFrame([{
            "KPI": TARGETS[k].label,
            "Actual": fmt_days(v) if TARGETS[k].fmt == "days" else (f"{v:.1f}x" if TARGETS[k].fmt == "ratio" and v else fmt_pct(v)),
            "Target": ("≥ " if TARGETS[k].higher_is_better else "≤ ")
            + (f"{TARGETS[k].green:.0f} days" if TARGETS[k].fmt == "days" else f"{TARGETS[k].green:.0f}x"
               if TARGETS[k].fmt == "ratio" else fmt_pct(TARGETS[k].green, 0)),
            "Status": statuses[k],
        } for k, v in values.items()])
        reg["_o"] = reg["Status"].map({"Red": 0, "Amber": 1, "Green": 2, "n/a": 3})
        table(reg.sort_values("_o"), key="exec_register", columns=["KPI", "Actual", "Target", "Status"],
              rag_cols=["Status"], select=False, alt="KPI exception register", csv_name="kpi exceptions")

# --------------------------------------------------------------------------- #
# Management attention
# --------------------------------------------------------------------------- #
st.subheader("Management attention", anchor=False)
cards = st.columns(4)
attention = [
    ("Urgent replenishment", f"{fmt_int(len(p1))} lines", "Red" if len(p1) else "Green",
     f"{fmt_gbp(p1['recommended_order_value_gbp'].sum())} to order on A-class lines out of stock or critical",
     "pages/03_replenishment.py", "Open planner"),
    ("High-risk suppliers", f"{len(high_risk)} of {len(scorecard)}",
     "Red" if len(high_risk) > 3 else "Amber" if len(high_risk) else "Green",
     f"{fmt_gbp(high_risk['spend_gbp'].sum())} of 12-month spend", "pages/04_suppliers.py", "Supplier scorecard"),
    (f"Budget {fy} YTD", fmt_pct(ytd_var_pct, signed=True), rag_for("budget_variance", ytd_var_pct),
     f"{fmt_gbp(outturn['ytd_variance_gbp'].sum())} vs year-to-date budget (+ = overspend)",
     "pages/07_budget_and_costs.py", "Budget & costs"),
    ("Overdue inbound shipments", fmt_int(len(overdue)), "Red" if len(overdue) > 20 else "Amber" if len(overdue) else "Green",
     f"In transit past planned arrival · {fmt_int(len(in_flight))} open shipments", "pages/05_logistics.py", "Logistics"),
]
for col, (title, value, status, note, link, link_label) in zip(cards, attention):
    with col:
        with st.container(border=True, height="stretch"):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"**{title}**")
                rag_badge(status)
            st.markdown(f"### {value}")
            st.caption(note)
            st.page_link(link, label=link_label, icon=":material/arrow_forward:")

# --------------------------------------------------------------------------- #
# Category scorecard with warehouse drill-down
# --------------------------------------------------------------------------- #
with section("Category scorecard", f"{f.start:%d %b %Y} – {f.end:%d %b %Y} · select a category to see its warehouse split"):
    cat = queries.inventory_breakdown(f, ("category",)).sort_values("net_sales_gbp", ascending=False)
    cat["sales_share"] = cat["net_sales_gbp"] / cat["net_sales_gbp"].sum()
    cat["availability_status"] = cat["availability"].map(lambda v: rag_for("availability", v))
    cat["margin_status"] = cat["gross_margin"].map(lambda v: rag_for("gross_margin", v))
    sel = table(
        cat, key="exec_cat", rag_cols=["availability_status", "margin_status"], alt="Category scorecard",
        csv_name="category scorecard",
        columns=["category", "net_sales_gbp", "sales_share", "gross_margin", "margin_status", "avg_stock_value_gbp",
                 "stock_turns", "availability", "availability_status", "lost_sales_gbp"],
        column_config={
            "category": "Category", "net_sales_gbp": gbp("Net sales"),
            "sales_share": st.column_config.ProgressColumn("Sales mix", format="percent", min_value=0,
                                                           # NaN when the filters match no sales ("nan or 1" stays NaN)
                                                           max_value=float(cat["sales_share"].max()) if cat["sales_share"].notna().any() else 1.0),
            "gross_margin": pct("Gross margin"), "margin_status": "Margin RAG",
            "avg_stock_value_gbp": gbp("Avg stock"), "stock_turns": num("Stock turn", 1, "x"),
            "availability": pct("Availability"), "availability_status": "Availability RAG",
            "lost_sales_gbp": gbp("Lost sales"),
        },
    )

if sel is not None:
    with section(f"Drill-down · {sel['category']} by warehouse"):
        whs = queries.load_warehouses()[["warehouse_code", "warehouse_name"]]
        split = queries.inventory_breakdown(f, ("category", "warehouse_code"))
        split = split[split["category"] == sel["category"]].merge(whs, on="warehouse_code", how="left")
        split["status"] = split["availability"].map(lambda v: rag_for("availability", v))
        c1, c2 = st.columns([1, 1])
        with c1:
            charts.show(charts.bar(split.sort_values("net_sales_gbp", ascending=False), "warehouse_name", "net_sales_gbp",
                                   horizontal=True, height=320, value_title="Net sales"),
                        alt=f"Net sales by warehouse for {sel['category']}")
        with c2:
            fig = charts.bar(split.sort_values("availability"), "warehouse_name", "availability", "status", kind="pct",
                             horizontal=True, height=320, colors=charts.RAG_COLOURS, value_title="Availability")
            charts.show(fig, alt=f"Availability by warehouse for {sel['category']}")
        cols = ["warehouse_code", "warehouse_name", "net_sales_gbp", "gross_margin", "avg_stock_value_gbp",
                "availability", "status", "lost_sales_gbp"]
        st.dataframe(split[cols], hide_index=True, alt="Category by warehouse detail",
                     column_config={"warehouse_code": "Code", "warehouse_name": "Warehouse", "net_sales_gbp": gbp("Net sales"),
                                    "gross_margin": pct("Gross margin"), "avg_stock_value_gbp": gbp("Avg stock"),
                                    "availability": pct("Availability"), "status": "RAG", "lost_sales_gbp": gbp("Lost sales")})
        download(split[cols], f"{sel['category']} by warehouse", key="dl_exec_drill")

st.caption(f"Comparison period: {prior.start:%d %b %Y} – {prior.end:%d %b %Y}. "
           "Targets are maintained in inventory360.business_logic.exceptions. Generated "
           f"{pd.Timestamp.now():%d %b %Y %H:%M}.")
