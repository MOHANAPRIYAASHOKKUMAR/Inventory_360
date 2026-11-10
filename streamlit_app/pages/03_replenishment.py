import pandas as pd
import streamlit as st

from components.layout import active_filter_caption, apply_filters, kpi, page_header
from inventory360.business_logic.replenishment import Scenario, recalculate_plan
from inventory360.data_access import queries
from inventory360.utils.config import PRIORITY_ORDER
from inventory360.utils.formatting import fmt_gbp, fmt_int, pct_change

position_all = queries.load_inventory_position()
as_of = position_all["as_of_date"].max()
page_header("Replenishment planner", "Service-level driven order recommendations with what-if scenarios and approval workflow",
            ":material/autorenew:", as_of)
active_filter_caption()

if "repl_scenario" not in st.session_state:
    st.session_state.repl_scenario = Scenario()

# --------------------------------------------------------------------------- #
# Scenario levers (batched in a form so the plan recalculates once on apply)
# --------------------------------------------------------------------------- #
with st.expander("Scenario levers", icon=":material/tune:", expanded=False):
    with st.form("scenario_form", border=False):
        c1, c2, c3 = st.columns(3)
        sc = st.session_state.repl_scenario
        sl_a = c1.slider("Target service level - A class", 0.85, 0.995, sc.service_level_a, 0.005, format="%.3f")
        sl_b = c2.slider("Target service level - B class", 0.80, 0.99, sc.service_level_b, 0.01, format="%.2f")
        sl_c = c3.slider("Target service level - C class", 0.80, 0.98, sc.service_level_c, 0.01, format="%.2f")
        d1, d2 = st.columns(2)
        uplift = d1.slider("Demand uplift", -0.30, 0.50, sc.demand_uplift, 0.05, format="%.2f",
                           help="Apply a promotional or seasonal uplift to the 28-day demand baseline (0.15 = +15%).")
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
position = apply_filters(position_all)
plan = recalculate_plan(position, scenario)

base_value = plan["recommended_order_value_gbp"].sum()
scen_value = plan["scenario_order_value_gbp"].sum()
base_ss = (plan["safety_stock_qty"] * plan["unit_cost_gbp"]).sum()
scen_ss = plan["scenario_safety_stock_value_gbp"].sum()

cols = st.columns(4)
with cols[0]:
    kpi("Order lines (scenario)", fmt_int((plan["scenario_order_qty"] > 0).sum()),
        (plan["scenario_order_qty"] > 0).sum(), (plan["recommended_order_qty"] > 0).sum(), desc="vs base policy")
with cols[1]:
    kpi("Order value (scenario)", fmt_gbp(scen_value), scen_value, base_value, inverse=True, desc="vs base policy")
with cols[2]:
    kpi("Safety stock investment", fmt_gbp(scen_ss), scen_ss, base_ss, inverse=True, desc="vs base policy",
        help="Value of safety stock implied by the service-level targets.")
with cols[3]:
    urgent = plan[plan["scenario_priority"] == "P1 - Urgent"]
    kpi("Urgent lines (P1)", fmt_int(len(urgent)), help="A-class SKU-locations out of stock or critical.")

if scenario != Scenario():
    change = pct_change(scen_value, base_value)
    st.info(
        f"Scenario active: service A/B/C {scenario.service_level_a:.1%} / {scenario.service_level_b:.0%} / "
        f"{scenario.service_level_c:.0%}, demand {scenario.demand_uplift:+.0%}, +{scenario.lead_time_buffer_days} days lead time. "
        f"Order value {'+' if (change or 0) >= 0 else ''}{(change or 0):.1%} vs policy.",
        icon=":material/science:",
    )

# --------------------------------------------------------------------------- #
# Recommendation grid with approval
# --------------------------------------------------------------------------- #
recs = plan[plan["scenario_order_qty"] > 0].copy()
with st.container(horizontal=True, vertical_alignment="bottom"):
    prio = st.pills("Priority", PRIORITY_ORDER[:-1], selection_mode="multi", default=PRIORITY_ORDER[:2], key="repl_prio")
    supplier = st.selectbox("Supplier", ["All suppliers"] + sorted(recs["supplier_name"].unique()), key="repl_supplier")

if prio:
    recs = recs[recs["scenario_priority"].isin(prio)]
if supplier != "All suppliers":
    recs = recs[recs["supplier_name"] == supplier]
recs = recs.assign(prio_rank=recs["scenario_priority"].map({p: i for i, p in enumerate(PRIORITY_ORDER)})) \
           .sort_values(["prio_rank", "scenario_order_value_gbp"], ascending=[True, False])
recs["approve"] = recs["scenario_priority"] == "P1 - Urgent"
recs["approved_qty"] = recs["scenario_order_qty"]

st.subheader(f"Recommended orders · {len(recs)} lines", anchor=False)
st.caption("Tick lines to approve and adjust quantities if needed. Approved quantities are rounded up to the supplier MOQ on submission.")
edited = st.data_editor(
    recs[["approve", "scenario_priority", "sku", "product_name", "warehouse_name", "supplier_name", "stock_status",
          "qty_on_hand", "inventory_position_qty", "scenario_reorder_point", "scenario_order_qty", "approved_qty",
          "min_order_qty", "unit_cost_gbp", "scenario_order_value_gbp", "earliest_arrival_if_ordered"]],
    hide_index=True,
    height=440,
    key="repl_editor",
    alt="Replenishment recommendations",
    disabled=[c for c in recs.columns if c not in ("approve", "approved_qty")],
    column_config={
        "approve": st.column_config.CheckboxColumn("Approve", width="small"),
        "scenario_priority": "Priority",
        "sku": "SKU",
        "product_name": st.column_config.TextColumn("Product", width="medium"),
        "warehouse_name": "Site",
        "supplier_name": "Supplier",
        "stock_status": "Status",
        "qty_on_hand": st.column_config.NumberColumn("On hand", format="%,d"),
        "inventory_position_qty": st.column_config.NumberColumn("Inv. position", format="%,d",
                                                                help="On hand - allocated + open/in-transit POs"),
        "scenario_reorder_point": st.column_config.NumberColumn("Reorder point", format="%,d"),
        "scenario_order_qty": st.column_config.NumberColumn("Recommended", format="%,d"),
        "approved_qty": st.column_config.NumberColumn("Approved qty", format="%,d", min_value=0, step=1),
        "min_order_qty": st.column_config.NumberColumn("MOQ", format="%,d"),
        "unit_cost_gbp": st.column_config.NumberColumn("Unit cost", format="£%.2f"),
        "scenario_order_value_gbp": st.column_config.NumberColumn("Order value", format="£%,.0f"),
        "earliest_arrival_if_ordered": st.column_config.DateColumn("Earliest arrival", format="DD MMM YYYY"),
    },
)

approved = recs.loc[edited.index[edited["approve"]]].copy()
approved["approved_qty"] = edited.loc[approved.index, "approved_qty"]
moq = approved["min_order_qty"].clip(lower=1)
approved["approved_qty"] = ((approved["approved_qty"] / moq).apply(lambda v: -(-v // 1)) * moq).astype(int)
approved = approved[approved["approved_qty"] > 0]
approved_value = float((approved["approved_qty"] * approved["unit_cost_gbp"]).sum())

# --------------------------------------------------------------------------- #
# Supplier consolidation of the approved basket
# --------------------------------------------------------------------------- #
left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        st.subheader("Approved basket by supplier", anchor=False)
        if approved.empty:
            st.caption("No lines approved yet.")
        else:
            basket = approved.assign(value=approved["approved_qty"] * approved["unit_cost_gbp"],
                                     pallets=(approved["approved_qty"] / approved["units_per_pallet"]).apply(lambda v: -(-v // 1)))
            by_sup = basket.groupby(["supplier_name", "sourcing_region"], as_index=False).agg(
                lines=("sku", "count"), sites=("warehouse_code", "nunique"), pallets=("pallets", "sum"), value=("value", "sum"),
                lead_time=("lead_time_days", "max"))
            st.dataframe(
                by_sup.sort_values("value", ascending=False), hide_index=True, alt="Approved basket by supplier",
                column_config={
                    "supplier_name": "Supplier", "sourcing_region": "Region", "lines": "Lines", "sites": "Sites",
                    "pallets": st.column_config.NumberColumn("Pallets", format="%,d"),
                    "value": st.column_config.NumberColumn("Value", format="£%,.0f"),
                    "lead_time": st.column_config.NumberColumn("Lead time", format="%d days"),
                },
            )


@st.dialog("Submit replenishment orders")
def confirm_submission(lines: pd.DataFrame, value: float) -> None:
    st.write(f"You are about to submit **{len(lines)} order lines** worth **{fmt_gbp(value, 2)}** "
             f"to the ERP interface queue.")
    note = st.text_area("Planner note", placeholder="Reason, promotion reference or supplier conversation",
                        max_chars=1000)
    if st.button("Confirm and submit", type="primary", icon=":material/send:", width="stretch"):
        try:
            written = queries.submit_replenishment_requests(lines, note or "")
        except Exception as exc:  # surfaced to the planner; nothing partially written (single INSERT)
            st.error(f"Submission failed: {exc}", icon=":material/error:")
            return
        st.session_state.repl_last_submit = (written, value)
        st.rerun()


with right:
    with st.container(border=True, height="stretch"):
        st.subheader("Submit for ordering", anchor=False)
        st.metric("Approved lines", fmt_int(len(approved)))
        st.metric("Approved value", fmt_gbp(approved_value))
        if st.button("Submit approved orders", type="primary", icon=":material/send:", disabled=approved.empty,
                     width="stretch"):
            confirm_submission(approved, approved_value)

if "repl_last_submit" in st.session_state:
    n, v = st.session_state.pop("repl_last_submit")
    st.toast(f"{n} lines ({fmt_gbp(v)}) submitted to the ERP outbox", icon=":material/check_circle:")

with st.expander("ERP outbox · submitted orders awaiting interface", icon=":material/outbox:"):
    outbox = queries.load_replenishment_requests()
    if outbox.empty:
        st.caption("No orders in the outbox.")
    else:
        st.dataframe(
            outbox[["created_at", "created_by", "status", "priority", "sku", "product_name", "warehouse_code",
                    "supplier_name", "approved_qty", "order_value_gbp", "planner_note"]],
            hide_index=True, alt="Submitted replenishment orders",
            column_config={
                "created_at": st.column_config.DatetimeColumn("Submitted", format="DD MMM YYYY HH:mm"),
                "approved_qty": st.column_config.NumberColumn("Qty", format="%,d"),
                "order_value_gbp": st.column_config.NumberColumn("Value", format="£%,.0f"),
            },
        )
