import altair as alt
import streamlit as st

from components import charts
from components.layout import kpi, page_header
from inventory360.business_logic.supplier import spend_concentration, supplier_actions
from inventory360.data_access import queries
from inventory360.utils.formatting import fmt_gbp, fmt_int, fmt_pct

scorecard_all = queries.load_supplier_scorecard()
monthly = queries.load_supplier_monthly_performance()
open_pos = queries.load_open_purchase_orders()
as_of = queries.load_data_freshness()["as_of_date"].iloc[0]

page_header("Supplier performance", "Rolling 12-month OTIF, lead-time reliability, landed cost and risk", ":material/handshake:", as_of)

with st.container(horizontal=True, vertical_alignment="bottom"):
    regions = st.pills("Sourcing region", sorted(scorecard_all["sourcing_region"].unique()), selection_mode="multi",
                       key="sup_regions")
    tiers = st.pills("Contract tier", ["Strategic", "Preferred", "Approved"], selection_mode="multi", key="sup_tiers")

scorecard = scorecard_all
if regions:
    scorecard = scorecard[scorecard["sourcing_region"].isin(regions)]
if tiers:
    scorecard = scorecard[scorecard["contract_tier"].isin(tiers)]
ids = set(scorecard["supplier_id"])
monthly = monthly[monthly["supplier_id"].isin(ids)]
open_pos = open_pos[open_pos["supplier_id"].isin(ids)]

spend = scorecard["spend_gbp"].sum()
w_otif = (scorecard["otif_rate"] * scorecard["spend_gbp"]).sum() / spend if spend else None
cols = st.columns(4)
with cols[0]:
    kpi("12-month spend", fmt_gbp(spend), help=f"{len(scorecard)} active suppliers")
with cols[1]:
    kpi("Spend-weighted OTIF", fmt_pct(w_otif), help="On time and in full, weighted by purchase value.")
with cols[2]:
    kpi("Top-5 spend concentration", fmt_pct(spend_concentration(scorecard)))
with cols[3]:
    kpi("Open order book", fmt_gbp(open_pos["order_value_gbp"].sum()),
        help=f"{fmt_int(len(open_pos))} open or in-transit purchase orders")

left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        st.subheader("Risk matrix", anchor=False)
        st.caption("Spend vs OTIF; bubble size = lead-time variability")
        st.altair_chart(charts.supplier_matrix(scorecard), alt="Supplier spend vs OTIF risk matrix")
with right:
    with st.container(border=True):
        st.subheader("OTIF trend by region", anchor=False)
        trend = monthly.assign(w=monthly["otif_rate"] * monthly["po_lines"]) \
                       .groupby(["period_month", "sourcing_region"], as_index=False)[["w", "po_lines"]].sum()
        trend["otif_rate"] = trend["w"] / trend["po_lines"]
        st.altair_chart(charts.line(trend, "period_month", "otif_rate", "sourcing_region", "OTIF", pct=True, height=330),
                        alt="Monthly OTIF by sourcing region")

st.subheader("Supplier scorecard", anchor=False)
view = scorecard.copy()
view["recommended_action"] = view.apply(supplier_actions, axis=1)
event = st.dataframe(
    view[["risk_rating", "supplier_name", "country_name", "primary_category", "contract_tier", "performance_score",
          "spend_gbp", "otif_rate", "on_time_rate", "in_full_rate", "avg_days_late", "contract_lead_time_days",
          "avg_actual_lead_time_days", "lead_time_variability_days", "landed_cost_uplift_pct", "recommended_action"]],
    hide_index=True,
    height=420,
    on_select="rerun",
    selection_mode="single-row",
    key="sup_table",
    alt="Supplier scorecard",
    column_config={
        "risk_rating": "Risk",
        "supplier_name": "Supplier",
        "country_name": "Country",
        "primary_category": "Category",
        "contract_tier": "Tier",
        "performance_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
        "spend_gbp": st.column_config.NumberColumn("Spend 12m", format="£%,.0f"),
        "otif_rate": st.column_config.NumberColumn("OTIF", format="percent"),
        "on_time_rate": st.column_config.NumberColumn("On time", format="percent"),
        "in_full_rate": st.column_config.NumberColumn("In full", format="percent"),
        "avg_days_late": st.column_config.NumberColumn("Avg days late", format="%.1f"),
        "contract_lead_time_days": st.column_config.NumberColumn("Contract LT", format="%d d"),
        "avg_actual_lead_time_days": st.column_config.NumberColumn("Actual LT", format="%.1f d"),
        "lead_time_variability_days": st.column_config.NumberColumn("LT std dev", format="%.1f d"),
        "landed_cost_uplift_pct": st.column_config.NumberColumn("Freight+duty uplift", format="percent"),
        "recommended_action": st.column_config.TextColumn("Recommended action", width="large"),
    },
)
st.caption("Select a supplier row to drill into its monthly performance and open orders.")

rows = event.selection.rows if event and event.selection else []
if rows:
    sel = view.iloc[rows[0]]
    with st.container(border=True):
        st.subheader(f"{sel['supplier_name']} · {sel['country_name']}", anchor=False)
        st.caption(f"{sel['contract_tier']} supplier · {sel['primary_category']} · payment terms {sel['payment_terms_days']} days")
        m = monthly[monthly["supplier_id"] == sel["supplier_id"]]
        c1, c2 = st.columns(2)
        with c1:
            st.altair_chart(
                alt.Chart(m).mark_bar(color="#1D4ED8", opacity=0.75).encode(
                    x=alt.X("yearmonth(period_month):T", title=None, axis=alt.Axis(format="%b %y")),
                    y=alt.Y("spend_gbp:Q", title="Received value", axis=charts.GBP_AXIS),
                    tooltip=[alt.Tooltip("yearmonth(period_month):T", title="Month"),
                             alt.Tooltip("spend_gbp:Q", format=",.0f")],
                ).properties(height=240),
                alt="Monthly received value for selected supplier",
            )
        with c2:
            st.altair_chart(charts.line(m, "period_month", "otif_rate", y_title="OTIF", pct=True, height=240),
                            alt="Monthly OTIF for selected supplier")
        po = open_pos[open_pos["supplier_id"] == sel["supplier_id"]]
        st.dataframe(
            po[["po_number", "warehouse_code", "order_date", "expected_date", "po_status", "lines", "units", "order_value_gbp"]],
            hide_index=True, alt="Open purchase orders for selected supplier",
            column_config={
                "po_number": "PO", "warehouse_code": "Site",
                "order_date": st.column_config.DateColumn("Ordered", format="DD MMM YYYY"),
                "expected_date": st.column_config.DateColumn("Due", format="DD MMM YYYY"),
                "po_status": "Status", "units": st.column_config.NumberColumn("Units", format="%,d"),
                "order_value_gbp": st.column_config.NumberColumn("Value", format="£%,.0f"),
            },
        )
