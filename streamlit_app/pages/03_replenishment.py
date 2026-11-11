import numpy as np
import pandas as pd
import streamlit as st

from components import charts, filters
from components.layout import day, download, filter_scope, gbp, kpi, num, page_header, section
from inventory360.business_logic.replenishment import Scenario, recalculate_plan
from inventory360.data_access import queries
from inventory360.data_access.queries import POSITION_COLS
from inventory360.utils.config import PRIORITY_ORDER
from inventory360.utils.formatting import fmt_gbp, fmt_int, pct_change

PRIORITY_COLOURS = {"P1 - Urgent": charts.RED, "P2 - High": charts.AMBER, "P3 - Medium": "#5B8DB8",
                    "P4 - Routine": charts.SLATE}

f = filters.current()
position = queries.inventory_position(f)
as_of = position["as_of_date"].max() if not position.empty else st.session_state["gf_as_of"]
page_header("Replenishment planner", "Service-level driven order recommendations, what-if scenarios and approval", as_of=as_of)
filter_scope(f, POSITION_COLS, use_date=False)

if "repl_scenario" not in st.session_state:
    st.session_state.repl_scenario = Scenario()

with st.expander("Scenario levers", icon=":material/tune:", expanded=False):
    with st.form("scenario_form", border=False):
        sc = st.session_state.repl_scenario
        c1, c2, c3 = st.columns(3)
        sl_a = c1.slider("Target service level - A class", 0.85, 0.995, sc.service_level_a, 0.005, format="%.3f")
        sl_b = c2.slider("Target service level - B class", 0.80, 0.99, sc.service_level_b, 0.01, format="%.2f")
        sl_c = c3.slider("Target service level - C class", 0.80, 0.98, sc.service_level_c, 0.01, format="%.2f")
        d1, d2 = st.columns(2)
        uplift = d1.slider("Demand uplift", -0.30, 0.50, sc.demand_uplift, 0.05, format="%.2f",
                           help="Promotional or seasonal uplift on the 28-day demand baseline (0.15 = +15%).")
        buffer = d2.slider("Lead-time buffer (days)", 0, 21, sc.lead_time_buffer_days,
                           help="Extra days to protect against supplier or port delays.")
        with st.container(horizontal=True):
            applied = st.form_submit_button("Apply scenario", type="primary", icon=":material/play_arrow:")
            reset = st.form_submit_button("Reset to policy", icon=":material/restart_alt:")
    if applied:
        st.session_state.repl_scenario = Scenario(sl_a, sl_b, sl_c, uplift, buffer)
        st.rerun()
    if reset:
        st.session_state.repl_scenario = Scenario()
        st.rerun()

scenario: Scenario = st.session_state.repl_scenario
plan = recalculate_plan(position, scenario)
base_value = plan["recommended_order_value_gbp"].sum()
scen_value = plan["scenario_order_value_gbp"].sum()
base_ss = (plan["safety_stock_qty"] * plan["unit_cost_gbp"]).sum()
scen_ss = plan["scenario_safety_stock_value_gbp"].sum()
lines = int((plan["scenario_order_qty"] > 0).sum())
urgent = plan[plan["scenario_priority"] == "P1 - Urgent"]

cols = st.columns(4)
with cols[0]:
    kpi("Order lines", fmt_int(lines), current=lines, previous=int((plan["recommended_order_qty"] > 0).sum()),
        desc="vs base policy")
with cols[1]:
    kpi("Order value", fmt_gbp(scen_value), current=scen_value, previous=base_value, inverse=True, desc="vs base policy")
with cols[2]:
    kpi("Safety stock investment", fmt_gbp(scen_ss), current=scen_ss, previous=base_ss, inverse=True,
        desc="vs base policy", help="Value of safety stock implied by the service-level targets.")
with cols[3]:
    kpi("Urgent lines (P1)", fmt_int(len(urgent)), status="Red" if len(urgent) else "Green",
        status_text=f"{fmt_gbp(urgent['scenario_order_value_gbp'].sum())} to order",
        help="A-class SKU-locations out of stock or critical.")

if scenario != Scenario():
    change = pct_change(scen_value, base_value) or 0
    st.info(f"Service A/B/C {scenario.service_level_a:.1%} / {scenario.service_level_b:.0%} / {scenario.service_level_c:.0%}, "
            f"demand {scenario.demand_uplift:+.0%}, +{scenario.lead_time_buffer_days} days lead time. "
            f"Order value {change:+.1%} vs policy.", icon=":material/science:", title="Scenario active")

recs_all = plan[plan["scenario_order_qty"] > 0]
left, right = st.columns([3, 2])
with left:
    with section("Order value by supplier", "Top 15 suppliers in the recommended plan, by priority"):
        by_sup = recs_all.groupby(["supplier_name", "scenario_priority"], as_index=False)["scenario_order_value_gbp"].sum()
        top = by_sup.groupby("supplier_name")["scenario_order_value_gbp"].sum().nlargest(15).index.tolist()
        charts.show(charts.bar(by_sup[by_sup["supplier_name"].isin(top)], "supplier_name", "scenario_order_value_gbp",
                               "scenario_priority", horizontal=True, order=top, colors=PRIORITY_COLOURS, height=420),
                    alt="Recommended order value by supplier and priority")
with right:
    with section("Plan by priority", "Recommended order value", height="stretch"):
        by_p = recs_all.groupby("scenario_priority", as_index=False)["scenario_order_value_gbp"].sum()
        charts.show(charts.donut(by_p, "scenario_priority", "scenario_order_value_gbp", kind="gbp",
                                 colors=PRIORITY_COLOURS, order=PRIORITY_ORDER, height=380),
                    alt="Recommended order value by priority")

# --------------------------------------------------------------------------- #
# Recommendation grid with approval
# --------------------------------------------------------------------------- #
with st.container(horizontal=True, vertical_alignment="bottom"):
    prio = st.pills("Priority", PRIORITY_ORDER[:-1], selection_mode="multi", default=PRIORITY_ORDER[:2], key="repl_prio")
    search = st.text_input("Search SKU or product", key="repl_search", placeholder="e.g. SKU0123 or garden")

recs = recs_all
if prio:
    recs = recs[recs["scenario_priority"].isin(prio)]
if search:
    s = search.strip().lower()
    recs = recs[recs["sku"].str.lower().str.contains(s, regex=False) | recs["product_name"].str.lower().str.contains(s, regex=False)]
recs = recs.assign(prio_rank=recs["scenario_priority"].map({p: i for i, p in enumerate(PRIORITY_ORDER)})) \
           .sort_values(["prio_rank", "scenario_order_value_gbp"], ascending=[True, False])
recs = recs.assign(approve=recs["scenario_priority"] == "P1 - Urgent", approved_qty=recs["scenario_order_qty"])

GRID = ["approve", "scenario_priority", "sku", "product_name", "warehouse_name", "supplier_name", "stock_status",
        "qty_on_hand", "inventory_position_qty", "scenario_reorder_point", "scenario_order_qty", "approved_qty",
        "min_order_qty", "unit_cost_gbp", "scenario_order_value_gbp", "earliest_arrival_if_ordered"]
with section(f"Recommended orders · {len(recs):,} lines",
             "Tick lines to approve and adjust quantities. Approved quantities are rounded up to the supplier MOQ."):
    with st.container(horizontal=True, horizontal_alignment="right"):
        download(recs[GRID[1:]], "replenishment recommendations", key="dl_repl_recs")
    edited = st.data_editor(
        recs[GRID], hide_index=True, height=440, key="repl_editor", alt="Replenishment recommendations",
        disabled=[c for c in GRID if c not in ("approve", "approved_qty")],
        column_config={
            "approve": st.column_config.CheckboxColumn("Approve", width="small"),
            "scenario_priority": "Priority", "sku": "SKU",
            "product_name": st.column_config.TextColumn("Product", width="medium"),
            "warehouse_name": "Site", "supplier_name": "Supplier", "stock_status": "Status",
            "qty_on_hand": num("On hand"),
            "inventory_position_qty": num("Inv. position", help="On hand - allocated + open/in-transit POs"),
            "scenario_reorder_point": num("Reorder point"), "scenario_order_qty": num("Recommended"),
            "approved_qty": st.column_config.NumberColumn("Approved qty", format="%,d", min_value=0, step=1),
            "min_order_qty": num("MOQ"), "unit_cost_gbp": gbp("Unit cost", 2),
            "scenario_order_value_gbp": gbp("Order value"), "earliest_arrival_if_ordered": day("Earliest arrival"),
        },
    )

approved = recs.loc[edited.index[edited["approve"]]].copy()
approved["approved_qty"] = edited.loc[approved.index, "approved_qty"]
moq = approved["min_order_qty"].clip(lower=1)
approved["approved_qty"] = (np.ceil(approved["approved_qty"] / moq) * moq).astype(int)
approved = approved[approved["approved_qty"] > 0]
approved_value = float((approved["approved_qty"] * approved["unit_cost_gbp"]).sum())

left, right = st.columns([3, 2])
with left:
    with section("Approved basket by supplier", height="stretch"):
        if approved.empty:
            st.caption("No lines approved yet.")
        else:
            basket = approved.assign(value=approved["approved_qty"] * approved["unit_cost_gbp"],
                                     pallets=np.ceil(approved["approved_qty"] / approved["units_per_pallet"].clip(lower=1)))
            by_sup = basket.groupby(["supplier_name", "sourcing_region"], as_index=False).agg(
                lines=("sku", "count"), sites=("warehouse_code", "nunique"), pallets=("pallets", "sum"),
                value=("value", "sum"), lead_time=("lead_time_days", "max"))
            st.dataframe(by_sup.sort_values("value", ascending=False), hide_index=True, alt="Approved basket by supplier",
                         column_config={"supplier_name": "Supplier", "sourcing_region": "Region", "lines": num("Lines"),
                                        "sites": num("Sites"), "pallets": num("Pallets"), "value": gbp("Value"),
                                        "lead_time": num("Lead time", suffix=" d")})
            download(by_sup, "approved basket", key="dl_repl_basket")


@st.dialog("Submit replenishment orders")
def confirm_submission(lines_df: pd.DataFrame, value: float) -> None:
    st.write(f"You are about to submit **{len(lines_df)} order lines** worth **{fmt_gbp(value, 2)}** to the ERP interface queue.")
    note = st.text_area("Planner note", placeholder="Reason, promotion reference or supplier conversation", max_chars=1000)
    if st.button("Confirm and submit", type="primary", icon=":material/send:", width="stretch"):
        try:
            written = queries.submit_replenishment_requests(lines_df, note or "")
        except Exception as exc:  # surfaced to the planner; nothing partially written (single INSERT)
            st.error(f"Submission failed: {exc}", icon=":material/error:")
            return
        st.session_state.repl_last_submit = (written, value)
        st.rerun()


with right:
    with section("Submit for ordering", height="stretch"):
        c1, c2 = st.columns(2)
        c1.metric("Approved lines", fmt_int(len(approved)))
        c2.metric("Approved value", fmt_gbp(approved_value))
        if st.button("Submit approved orders", type="primary", icon=":material/send:", disabled=approved.empty, width="stretch"):
            confirm_submission(approved, approved_value)

if "repl_last_submit" in st.session_state:
    n, v = st.session_state.pop("repl_last_submit")
    st.toast(f"{n} lines ({fmt_gbp(v)}) submitted to the ERP outbox", icon=":material/check_circle:")

# --------------------------------------------------------------------------- #
# Drill-down and outbox
# --------------------------------------------------------------------------- #
with section("SKU drill-down", "Inspect the stock and demand history behind a recommendation"):
    options = recs.assign(label=recs["sku"] + " · " + recs["product_name"] + " · " + recs["warehouse_code"])
    pick = st.selectbox("Recommendation", options["label"].tolist(), index=None, placeholder="Choose a line", key="repl_pick")
    if pick:
        row = options[options["label"] == pick].iloc[0]
        hist = queries.sku_history(f, row["sku"], row["warehouse_code"])
        long = hist.melt(id_vars="snapshot_date", value_vars=["qty_on_hand", "units_demanded"], var_name="measure",
                         value_name="units").replace({"qty_on_hand": "On hand", "units_demanded": "Demand"})
        charts.show(charts.line(long, "snapshot_date", "units", "measure", kind="num", height=300,
                                target=float(row["scenario_reorder_point"]), target_label="Scenario reorder point",
                                colors={"On hand": charts.NAVY, "Demand": charts.TEAL}),
                    alt="Stock and demand history for the selected recommendation")

with st.expander("ERP outbox · submitted orders awaiting interface", icon=":material/outbox:"):
    outbox = queries.load_replenishment_requests()
    if outbox.empty:
        st.caption("No orders in the outbox.")
    else:
        cols_o = ["created_at", "created_by", "status", "priority", "sku", "product_name", "warehouse_code",
                  "supplier_name", "approved_qty", "order_value_gbp", "planner_note"]
        st.dataframe(outbox[cols_o], hide_index=True, alt="Submitted replenishment orders",
                     column_config={"created_at": st.column_config.DatetimeColumn("Submitted", format="DD MMM YYYY HH:mm"),
                                    "approved_qty": num("Qty"), "order_value_gbp": gbp("Value")})
        download(outbox[cols_o], "erp outbox", key="dl_repl_outbox")
