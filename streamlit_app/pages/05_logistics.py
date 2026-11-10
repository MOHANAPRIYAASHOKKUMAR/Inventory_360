import pandas as pd
import streamlit as st

from components import charts
from components.layout import active_filter_caption, apply_filters, kpi, page_header
from inventory360.data_access import queries
from inventory360.utils.formatting import fmt_gbp, fmt_int, fmt_pct

logistics_all = queries.load_logistics_monthly()
in_flight_all = queries.load_shipments_in_flight()
as_of = pd.Timestamp(queries.load_data_freshness()["as_of_date"].iloc[0])

page_header("Logistics & freight", "Inbound transport cost, carrier performance, carbon and shipments in flight",
            ":material/local_shipping:", as_of)
active_filter_caption()

modes = st.pills("Transport mode", ["Road", "Sea", "Rail", "Air"], selection_mode="multi", key="log_modes")
logistics = apply_filters(logistics_all, category_col=None)
in_flight = apply_filters(in_flight_all, category_col=None)
if modes:
    logistics = logistics[logistics["transport_mode"].isin(modes)]
    in_flight = in_flight[in_flight["transport_mode"].isin(modes)]

hist = logistics[logistics["period_month"] <= as_of]
last12 = hist[hist["period_month"] > as_of - pd.DateOffset(months=12)]
prior12 = hist[(hist["period_month"] <= as_of - pd.DateOffset(months=12)) & (hist["period_month"] > as_of - pd.DateOffset(months=24))]


def _rate(df: pd.DataFrame) -> float | None:
    delivered = df["shipments_delivered"].sum()
    return float((df["on_time_arrival_rate"] * df["shipments_delivered"]).sum() / delivered) if delivered else None


cols = st.columns(4)
with cols[0]:
    kpi("Landed cost (12 months)", fmt_gbp(last12["landed_cost_gbp"].sum()),
        help=f"Freight {fmt_gbp(last12['freight_cost_gbp'].sum())} + duty {fmt_gbp(last12['duty_cost_gbp'].sum())}")
with cols[1]:
    cpp = last12["freight_cost_gbp"].sum() / max(last12["pallets"].sum(), 1)
    kpi("Freight cost per pallet", f"£{cpp:,.2f}")
with cols[2]:
    kpi("On-time arrival", fmt_pct(_rate(last12)), help="Delivered shipments arriving on or before planned date.")
with cols[3]:
    kpi("Inbound CO₂e (12 months)", f"{last12['co2_tonnes'].sum():,.0f} t",
        help="Estimated from pallets moved and mode-specific emission factors.")

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True):
        st.subheader("Freight & duty by mode", anchor=False)
        st.altair_chart(charts.monthly_bar(hist, "period_month", "landed_cost_gbp", "transport_mode", y_title="Landed cost"),
                        alt="Monthly landed cost by transport mode")
with c2:
    with st.container(border=True):
        st.subheader("Cost per pallet by mode", anchor=False)
        st.caption("Sea rates rose ~45% Dec-25 to Apr-26 on Red Sea re-routing")
        cpp_m = hist.groupby(["period_month", "transport_mode"], as_index=False)[["freight_cost_gbp", "pallets"]].sum()
        cpp_m["cost_per_pallet"] = cpp_m["freight_cost_gbp"] / cpp_m["pallets"]
        st.altair_chart(charts.line(cpp_m, "period_month", "cost_per_pallet", "transport_mode", "£ per pallet"),
                        alt="Monthly freight cost per pallet by mode")

with st.container(border=True):
    st.subheader("Carrier league table · last 12 months", anchor=False)
    carriers = last12.assign(w=last12["on_time_arrival_rate"] * last12["shipments_delivered"],
                             d=last12["avg_delay_days"].fillna(0) * last12["shipments_delivered"]) \
        .groupby(["carrier", "transport_mode"], as_index=False) \
        .agg(shipments=("shipments", "sum"), delivered=("shipments_delivered", "sum"), pallets=("pallets", "sum"),
             freight=("freight_cost_gbp", "sum"), w=("w", "sum"), d=("d", "sum"), co2=("co2_tonnes", "sum"))
    carriers["on_time"] = carriers["w"] / carriers["delivered"]
    carriers["avg_delay"] = carriers["d"] / carriers["delivered"]
    carriers["cost_per_pallet"] = carriers["freight"] / carriers["pallets"]
    prev_cpp = prior12.groupby("carrier")[["freight_cost_gbp", "pallets"]].sum()
    carriers["cpp_change"] = carriers.apply(
        lambda r: (r["cost_per_pallet"] / (prev_cpp.loc[r["carrier"], "freight_cost_gbp"] / prev_cpp.loc[r["carrier"], "pallets"]) - 1)
        if r["carrier"] in prev_cpp.index and prev_cpp.loc[r["carrier"], "pallets"] else None, axis=1)
    st.dataframe(
        carriers.sort_values("freight", ascending=False)[
            ["carrier", "transport_mode", "shipments", "pallets", "freight", "cost_per_pallet", "cpp_change", "on_time", "avg_delay", "co2"]],
        hide_index=True, alt="Carrier performance league table",
        column_config={
            "carrier": "Carrier", "transport_mode": "Mode",
            "shipments": st.column_config.NumberColumn("Shipments", format="%,d"),
            "pallets": st.column_config.NumberColumn("Pallets", format="%,d"),
            "freight": st.column_config.NumberColumn("Freight spend", format="£%,.0f"),
            "cost_per_pallet": st.column_config.NumberColumn("£ / pallet", format="£%.2f"),
            "cpp_change": st.column_config.NumberColumn("£ / pallet vs prior yr", format="percent"),
            "on_time": st.column_config.ProgressColumn("On-time arrival", format="percent", min_value=0, max_value=1),
            "avg_delay": st.column_config.NumberColumn("Avg delay", format="%.1f d"),
            "co2": st.column_config.NumberColumn("CO₂e (t)", format="%,.0f"),
        },
    )

st.subheader("Shipments in flight", anchor=False)
in_flight = in_flight.assign(
    days_to_arrival=(in_flight["planned_arrival"] - as_of).dt.days,
    overdue=(in_flight["planned_arrival"] < as_of) & (in_flight["shipment_status"] == "IN_TRANSIT"),
)
cols = st.columns(3)
cols[0].metric("In transit", fmt_int((in_flight["shipment_status"] == "IN_TRANSIT").sum()), border=True)
cols[1].metric("Booked (not dispatched)", fmt_int((in_flight["shipment_status"] == "BOOKED").sum()), border=True)
cols[2].metric("Overdue vs plan", fmt_int(in_flight["overdue"].sum()), border=True)
st.dataframe(
    in_flight.sort_values(["overdue", "planned_arrival"], ascending=[False, True])[
        ["overdue", "shipment_id", "po_number", "supplier_name", "carrier", "transport_mode", "origin_country",
         "warehouse_code", "dispatch_date", "planned_arrival", "days_to_arrival", "pallets", "freight_cost_gbp", "shipment_status"]],
    hide_index=True, height=380, alt="Shipments in flight",
    column_config={
        "overdue": st.column_config.CheckboxColumn("Overdue"),
        "shipment_id": "Shipment", "po_number": "PO", "supplier_name": "Supplier", "carrier": "Carrier",
        "transport_mode": "Mode", "origin_country": "Origin", "warehouse_code": "Destination",
        "dispatch_date": st.column_config.DateColumn("Dispatched", format="DD MMM YYYY"),
        "planned_arrival": st.column_config.DateColumn("ETA", format="DD MMM YYYY"),
        "days_to_arrival": st.column_config.NumberColumn("Days to ETA", format="%d"),
        "pallets": st.column_config.NumberColumn("Pallets", format="%,d"),
        "freight_cost_gbp": st.column_config.NumberColumn("Freight", format="£%,.0f"),
        "shipment_status": "Status",
    },
)
