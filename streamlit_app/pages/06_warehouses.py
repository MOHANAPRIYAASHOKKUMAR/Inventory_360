import streamlit as st

from components import charts, filters
from components.layout import download, filter_scope, gbp, kpi, num, page_header, pct, section, table
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.data_access import queries
from inventory360.data_access.queries import UTILISATION_COLS
from inventory360.utils.formatting import fmt_gbp, fmt_int, fmt_pct

f = filters.current()
page_header("Warehouse network", "Capacity utilisation, throughput and operating cost across UK distribution sites", f,
            st.session_state["gf_as_of"])
filter_scope(f, UTILISATION_COLS, note="monthly data; the start date is rounded to the first of its month")

util = queries.warehouse_utilisation(f)
util_p = queries.warehouse_utilisation(f.prior())
costs = queries.warehouse_costs(f)

with st.container(horizontal=True, vertical_alignment="bottom"):
    site_types = st.pills("Site type", sorted(util["site_type"].dropna().unique()), selection_mode="multi", key="wh_types")
    nations = st.pills("Nation", sorted(util["nation"].dropna().unique()), selection_mode="multi", key="wh_nations")
if site_types:
    util, util_p = util[util["site_type"].isin(site_types)], util_p[util_p["site_type"].isin(site_types)]
if nations:
    util, util_p = util[util["nation"].isin(nations)], util_p[util_p["nation"].isin(nations)]
costs = costs[costs["warehouse_code"].isin(util["warehouse_code"].unique())]


def totals(d):
    latest = d[d["period_month"] == d["period_month"].max()] if not d.empty else d
    cap = latest["capacity_pallets"].sum()
    return {
        "capacity": cap,
        "avg_util": latest["avg_pallets_used"].sum() / cap if cap else None,
        "peak_util": (latest["peak_pallets_used"] / latest["capacity_pallets"]).max() if not latest.empty else None,
        "opex": d["opex_gbp"].sum(),
        "dispatched": d["units_dispatched"].sum(),
        "cpu": d["opex_gbp"].sum() / d["units_dispatched"].sum() if d["units_dispatched"].sum() else None,
    }


t, p = totals(util), totals(util_p)
cols = st.columns(5)
with cols[0]:
    kpi("Pallet capacity", fmt_int(t["capacity"]), help=f"{util['warehouse_code'].nunique()} sites in filter")
with cols[1]:
    kpi("Average utilisation", fmt_pct(t["avg_util"]), current=t["avg_util"], previous=p["avg_util"], points=True,
        help="Latest month: average pallets used ÷ capacity.")
with cols[2]:
    kpi("Peak site utilisation", fmt_pct(t["peak_util"]), status=rag_for("utilisation_peak", t["peak_util"]),
        status_text=f"Alert above {fmt_pct(TARGETS['utilisation_peak'].green, 0)}", help="Highest single-site peak in the latest month.")
with cols[3]:
    kpi("Operating cost", fmt_gbp(t["opex"]), current=t["opex"], previous=p["opex"], inverse=True)
with cols[4]:
    kpi("Cost per unit dispatched", f"£{t['cpu']:,.3f}" if t["cpu"] else "–", current=t["cpu"], previous=p["cpu"], inverse=True)

site = util.groupby(["warehouse_code", "warehouse_name", "site_type", "uk_region", "nation"], as_index=False).agg(
    capacity=("capacity_pallets", "max"), avg_used=("avg_pallets_used", "mean"), peak_used=("peak_pallets_used", "max"),
    dispatched=("units_dispatched", "sum"), received=("units_received", "sum"), opex=("opex_gbp", "sum"),
    labour=("labour_cost_gbp", "sum"), stock=("avg_stock_value_gbp", "mean"))
site["avg_util"] = site["avg_used"] / site["capacity"]
site["peak_util"] = site["peak_used"] / site["capacity"]
site["cpu"] = site["opex"] / site["dispatched"].where(site["dispatched"] > 0)
site["cpp"] = site["opex"] / site["avg_used"].where(site["avg_used"] > 0)
site["labour_share"] = site["labour"] / site["opex"].where(site["opex"] > 0)
site["status"] = site["peak_util"].map(lambda v: rag_for("utilisation_peak", v))

left, right = st.columns(2)
with left:
    with section("Peak utilisation by site", "Max of monthly peak pallets ÷ capacity"):
        charts.show(charts.bar(site.sort_values("peak_util", ascending=False), "warehouse_name", "peak_util", "status",
                               kind="pct", horizontal=True, colors=charts.RAG_COLOURS, height=340),
                    alt="Peak utilisation by warehouse")
with right:
    with section("Cost efficiency", "Operating cost per unit dispatched vs throughput · bubble = capacity"):
        charts.show(charts.scatter(site, "dispatched", "cpu", size="capacity", color="site_type", hover="warehouse_name",
                                   x_kind="num", y_kind="gbp2", x_title="Units dispatched", y_title="£ per unit", height=340),
                    alt="Cost per unit vs throughput by warehouse")

with section("Operating cost trend", "Monthly opex by site"):
    charts.show(charts.bar(util, "period_month", "opex_gbp", "warehouse_code", height=300), alt="Monthly operating cost by site")

with section("Site scorecard", "Select a site to drill into utilisation and cost categories"):
    sel = table(
        site.sort_values("opex", ascending=False), key="wh_table", alt="Warehouse site scorecard", csv_name="warehouse scorecard",
        rag_cols=["status"],
        columns=["warehouse_code", "warehouse_name", "site_type", "uk_region", "capacity", "avg_util", "peak_util", "status",
                 "dispatched", "received", "stock", "opex", "labour_share", "cpu", "cpp"],
        column_config={"warehouse_code": "Code", "warehouse_name": "Warehouse", "site_type": "Type", "uk_region": "Region",
                       "capacity": num("Capacity (pallets)"), "avg_util": pct("Avg utilisation"),
                       "peak_util": pct("Peak utilisation"), "status": "RAG", "dispatched": num("Units dispatched"),
                       "received": num("Units received"), "stock": gbp("Avg stock"), "opex": gbp("Operating cost"),
                       "labour_share": pct("Labour share"), "cpu": gbp("£ / unit", 3), "cpp": gbp("£ / pallet", 2)},
    )

if sel is not None:
    with section(f"Drill-down · {sel['warehouse_name']}", f"{sel['site_type']} · {sel['uk_region']} · capacity {sel['capacity']:,.0f} pallets"):
        u = util[util["warehouse_code"] == sel["warehouse_code"]]
        k = costs[costs["warehouse_code"] == sel["warehouse_code"]]
        c1, c2 = st.columns(2)
        with c1:
            long = u.melt(id_vars="period_month", value_vars=["avg_utilisation_pct", "peak_utilisation_pct"],
                          var_name="measure", value_name="util").replace(
                {"avg_utilisation_pct": "Average", "peak_utilisation_pct": "Peak"})
            charts.show(charts.line(long, "period_month", "util", "measure", kind="pct", height=300, markers=True,
                                    target=TARGETS["utilisation_peak"].green, target_label="Alert level",
                                    colors={"Average": charts.TEAL, "Peak": charts.NAVY}),
                        alt=f"Monthly utilisation for {sel['warehouse_name']}")
        with c2:
            charts.show(charts.bar(k, "period_month", "actual_cost_gbp", "cost_category", height=300),
                        alt=f"Monthly cost categories for {sel['warehouse_name']}")
        download(k, f"{sel['warehouse_code']} cost detail", key="dl_wh_drill")
