import pandas as pd
import streamlit as st

from components import charts, filters
from components.layout import day, download, filter_scope, gbp, kpi, num, page_header, pct, section, table
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.data_access import queries
from inventory360.data_access.queries import SHIPMENT_COLS
from inventory360.utils.formatting import fmt_days, fmt_gbp, fmt_int, fmt_pct

MODES = ["Road", "Sea", "Rail", "Air"]
f = filters.current()
as_of = st.session_state["gf_as_of"]
page_header("Logistics & freight", "Inbound transport cost, carrier performance, carbon and shipments in flight", f, as_of)
filter_scope(f, SHIPMENT_COLS, note="date range applies to dispatch date")

with st.container(horizontal=True, vertical_alignment="bottom"):
    modes = st.pills("Transport mode", MODES, selection_mode="multi", key="log_modes")
    grain = st.segmented_control("View", ["By mode", "By carrier", "By warehouse"], default="By mode", key="log_view") or "By mode"

ship = queries.shipments_monthly(f)
ship_p = queries.shipments_monthly(f.prior())
open_ = queries.shipments_open(f)
if modes:
    ship, ship_p, open_ = (d[d["transport_mode"].isin(modes)] for d in (ship, ship_p, open_))


def totals(d: pd.DataFrame) -> dict:
    delivered = d["delivered"].sum()
    return {
        "landed": d["landed_cost_gbp"].sum(), "freight": d["freight_cost_gbp"].sum(), "duty": d["duty_cost_gbp"].sum(),
        "cpp": d["freight_cost_gbp"].sum() / d["pallets"].sum() if d["pallets"].sum() else None,
        "otr": d["on_time"].sum() / delivered if delivered else None,
        "transit": d["transit_days_sum"].sum() / delivered if delivered else None,
        "co2": d["co2_tonnes"].sum(), "shipments": d["shipments"].sum(),
    }


t, p = totals(ship), totals(ship_p)
cols = st.columns(5)
with cols[0]:
    kpi("Landed cost", fmt_gbp(t["landed"]), current=t["landed"], previous=p["landed"], inverse=True,
        help=f"Freight {fmt_gbp(t['freight'])} + duty {fmt_gbp(t['duty'])}")
with cols[1]:
    kpi("Freight per pallet", f"£{t['cpp']:,.2f}" if t["cpp"] else "–", current=t["cpp"], previous=p["cpp"], inverse=True)
with cols[2]:
    kpi("On-time arrival", fmt_pct(t["otr"]), current=t["otr"], previous=p["otr"], points=True,
        status=rag_for("on_time_arrival", t["otr"]), status_text=f"Target ≥ {fmt_pct(TARGETS['on_time_arrival'].green, 0)}")
with cols[3]:
    kpi("Average transit", fmt_days(t["transit"]), current=t["transit"], previous=p["transit"], inverse=True)
with cols[4]:
    kpi("Inbound CO₂e", f"{t['co2']:,.0f} t", current=t["co2"], previous=p["co2"], inverse=True,
        help=f"{fmt_int(t['shipments'])} shipments dispatched in the period")

dim = {"By mode": "transport_mode", "By carrier": "carrier", "By warehouse": "warehouse_code"}[grain]
left, right = st.columns(2)
with left:
    with section(f"Landed cost {grain.lower()}", "Monthly freight + duty"):
        m = ship.groupby(["period_month", dim], as_index=False)["landed_cost_gbp"].sum()
        charts.show(charts.bar(m, "period_month", "landed_cost_gbp", dim, height=320), alt=f"Monthly landed cost {grain.lower()}")
with right:
    with section("Freight cost per pallet", f"Monthly, {grain.lower()}"):
        c = ship.groupby(["period_month", dim], as_index=False)[["freight_cost_gbp", "pallets"]].sum()
        c["cpp"] = c["freight_cost_gbp"] / c["pallets"].where(c["pallets"] > 0)
        charts.show(charts.line(c, "period_month", "cpp", dim, kind="gbp2", height=320, markers=True),
                    alt=f"Monthly freight cost per pallet {grain.lower()}")

# --------------------------------------------------------------------------- #
# Carrier league table with drill-down
# --------------------------------------------------------------------------- #
with section("Carrier league table", "Select a carrier to see its monthly cost and punctuality"):
    car = ship.groupby(["carrier", "transport_mode"], as_index=False).agg(
        shipments=("shipments", "sum"), delivered=("delivered", "sum"), on_time=("on_time", "sum"),
        pallets=("pallets", "sum"), freight=("freight_cost_gbp", "sum"), landed=("landed_cost_gbp", "sum"),
        co2=("co2_tonnes", "sum"), delay=("delay_days_sum", "sum"))
    car["otr"] = car["on_time"] / car["delivered"].where(car["delivered"] > 0)
    car["cpp"] = car["freight"] / car["pallets"].where(car["pallets"] > 0)
    car["avg_delay"] = car["delay"] / car["delivered"].where(car["delivered"] > 0)
    car["otr_status"] = car["otr"].map(lambda v: rag_for("on_time_arrival", v))
    sel = table(
        car.sort_values("landed", ascending=False), key="log_carriers", alt="Carrier league table", csv_name="carrier league table",
        rag_cols=["otr_status"],
        columns=["carrier", "transport_mode", "shipments", "pallets", "freight", "landed", "cpp", "otr", "otr_status",
                 "avg_delay", "co2"],
        column_config={"carrier": "Carrier", "transport_mode": "Mode", "shipments": num("Shipments"), "pallets": num("Pallets"),
                       "freight": gbp("Freight"), "landed": gbp("Landed cost"), "cpp": gbp("£ / pallet", 2),
                       "otr": pct("On-time arrival"), "otr_status": "RAG", "avg_delay": num("Avg delay", 1, " d"),
                       "co2": num("CO₂e (t)", 1)},
    )

if sel is not None:
    with section(f"Drill-down · {sel['carrier']} ({sel['transport_mode']})"):
        m = ship[(ship["carrier"] == sel["carrier"]) & (ship["transport_mode"] == sel["transport_mode"])] \
            .groupby("period_month", as_index=False)[["landed_cost_gbp", "on_time", "delivered", "pallets", "freight_cost_gbp"]].sum()
        m["otr"] = m["on_time"] / m["delivered"].where(m["delivered"] > 0)
        charts.show(charts.combo(m, "period_month", "landed_cost_gbp", "otr", "Landed cost", "On-time arrival",
                                 line_target=TARGETS["on_time_arrival"].green, height=300),
                    alt=f"Monthly landed cost and punctuality for {sel['carrier']}")
        download(m, f"{sel['carrier']} monthly", key="dl_log_drill")

# --------------------------------------------------------------------------- #
# Shipments in flight
# --------------------------------------------------------------------------- #
open_ = open_.assign(days_to_eta=(open_["planned_arrival"] - as_of).dt.days,
                     overdue=(open_["planned_arrival"] < as_of) & (open_["shipment_status"] == "IN_TRANSIT"))
open_["rag"] = open_.apply(lambda r: "Red" if r["overdue"] else "Amber" if r["days_to_eta"] <= 3 else "Green", axis=1)
with section("Shipments in flight", "Booked or in transit · overdue first"):
    c = st.columns(3)
    c[0].metric("In transit", fmt_int((open_["shipment_status"] == "IN_TRANSIT").sum()), border=True)
    c[1].metric("Booked", fmt_int((open_["shipment_status"] == "BOOKED").sum()), border=True)
    c[2].metric("Overdue vs plan", fmt_int(open_["overdue"].sum()), border=True)
    table(
        open_.sort_values(["overdue", "planned_arrival"], ascending=[False, True]), key="log_open", select=False,
        alt="Shipments in flight", csv_name="shipments in flight", rag_cols=["rag"], height=380,
        columns=["rag", "shipment_id", "po_number", "supplier_name", "carrier", "transport_mode", "origin_country",
                 "warehouse_code", "dispatch_date", "planned_arrival", "days_to_eta", "pallets", "freight_cost_gbp",
                 "shipment_status"],
        column_config={"rag": "RAG", "shipment_id": "Shipment", "po_number": "PO", "supplier_name": "Supplier",
                       "carrier": "Carrier", "transport_mode": "Mode", "origin_country": "Origin", "warehouse_code": "Site",
                       "dispatch_date": day("Dispatched"), "planned_arrival": day("ETA"), "days_to_eta": num("Days to ETA"),
                       "pallets": num("Pallets"), "freight_cost_gbp": gbp("Freight"), "shipment_status": "Status"},
    )
