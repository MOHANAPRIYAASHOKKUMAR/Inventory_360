import pandas as pd
import streamlit as st

from components import charts, filters
from components.layout import download, filter_scope, gbp, kpi, page_header, pct, section, table
from inventory360.business_logic.budget import full_year_outturn
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.data_access import queries
from inventory360.data_access.queries import BUDGET_COLS
from inventory360.utils.formatting import fmt_gbp, fmt_pct

AREAS = ["Inventory Purchases", "Freight & Duty", "Warehousing"]
f = filters.current()
as_of = st.session_state["gf_as_of"]
page_header("Budget & costs", "Budget, actuals, variance and full-year outturn for purchasing, freight and warehousing", f, as_of)
filter_scope(f, BUDGET_COLS, note="category filters Inventory Purchases lines; warehouse filters Freight and Warehousing lines")

bva_all = queries.load_budget_vs_actual()
# Global filters map onto the budget dimension key (category for purchases, site code otherwise)
keep = pd.Series(True, index=bva_all.index)
purchases = bva_all["budget_area"] == "Inventory Purchases"
if f.categories:
    keep &= ~purchases | bva_all["dimension_key"].isin(f.categories)
if f.warehouses:
    keep &= purchases | bva_all["dimension_key"].isin(f.warehouses)
bva_all = bva_all[keep]

years = sorted(bva_all["fiscal_year"].unique())
current_fy = bva_all.loc[bva_all["period_month"] <= as_of, "fiscal_year"].max()
with st.container(horizontal=True, vertical_alignment="bottom"):
    fy = st.segmented_control("Financial year (outturn)", years, default=current_fy, key="bud_fy") or current_fy
    areas = st.pills("Budget area", AREAS, selection_mode="multi", key="bud_area")
if areas:
    bva_all = bva_all[bva_all["budget_area"].isin(areas)]

# Period view honours the date range (months overlapping it); outturn is always the full financial year
start_m = pd.Timestamp(f.start).to_period("M").start_time
period = bva_all[(bva_all["period_month"] >= start_m) & (bva_all["period_month"] <= pd.Timestamp(f.end))]
closed = period[period["is_actualised"]]
budget_p, actual_p = closed["budget_gbp"].sum(), closed["actual_gbp"].sum()
var_p = actual_p - budget_p
var_pct = var_p / budget_p if budget_p else None

outturn = full_year_outturn(bva_all, fy)
fy_budget, fy_out = outturn["budget_gbp"].sum(), outturn["outturn_gbp"].sum()
out_var_pct = (fy_out - fy_budget) / fy_budget if fy_budget else None

cols = st.columns(4)
with cols[0]:
    kpi("Budget (closed months)", fmt_gbp(budget_p), help=f"{closed['period_month'].nunique()} actualised months in the date range")
with cols[1]:
    kpi("Actual (closed months)", fmt_gbp(actual_p), current=actual_p, previous=budget_p, inverse=True, desc="vs budget")
with cols[2]:
    kpi("Variance", fmt_gbp(var_p), status=rag_for("budget_variance", var_pct),
        status_text=f"{fmt_pct(var_pct, signed=True)} · amber > {fmt_pct(TARGETS['budget_variance'].green, 0)}",
        help="Actual − budget; positive = overspend.")
with cols[3]:
    kpi(f"{fy} projected outturn", fmt_gbp(fy_out), current=fy_out, previous=fy_budget, inverse=True, desc="vs full-year budget",
        status=rag_for("budget_variance", out_var_pct), status_text=f"{fmt_pct(out_var_pct, signed=True)} vs budget")

left, right = st.columns([3, 2])
with left:
    with section("Monthly actual and forecast vs budget", f"{fy} · bars = actual (closed) or forecast · line = budget"):
        fyd = bva_all[bva_all["fiscal_year"] == fy]
        m = fyd.groupby("period_month", as_index=False).agg(budget=("budget_gbp", "sum"), actual=("actual_gbp", "sum"),
                                                            forecast=("forecast_gbp", "sum"), closed=("is_actualised", "max"))
        m["value"] = m["actual"].where(m["closed"], m["forecast"].where(m["forecast"] > 0, m["budget"]))
        m["type"] = m["closed"].map({True: "Actual", False: "Forecast"})
        fig = charts.bar(m, "period_month", "value", "type", colors={"Actual": charts.NAVY, "Forecast": "#B8C7D9"},
                         height=330, stacked=False)
        fig.add_scatter(x=m["period_month"], y=m["budget"], name="Budget", mode="lines+markers",
                        line={"color": charts.TEAL, "width": 2.2, "dash": "dot"})
        charts.show(fig, alt="Monthly actual and forecast against budget")
with right:
    with section("Variance bridge", "Closed months in the date range · + = overspend", height="stretch"):
        by_area = closed.groupby("budget_area", as_index=False)[["budget_gbp", "actual_gbp"]].sum()
        by_area["variance"] = by_area["actual_gbp"] - by_area["budget_gbp"]
        charts.show(charts.waterfall(by_area["budget_area"].tolist(), by_area["variance"].tolist(), total_label="Net variance",
                                     height=330), alt="Variance by budget area")

with section(f"{fy} full-year outturn by area"):
    view = outturn.assign(outturn_rag=outturn["outturn_variance_pct"].map(lambda v: rag_for("budget_variance", v)))
    table(view, key="bud_outturn", select=False, alt="Full-year outturn by area", csv_name=f"outturn {fy}",
          rag_cols=["rag", "outturn_rag"],
          columns=["budget_area", "rag", "budget_gbp", "budget_ytd_gbp", "actual_ytd_gbp", "ytd_variance_gbp", "ytd_variance_pct",
                   "forecast_remaining_gbp", "outturn_gbp", "outturn_variance_gbp", "outturn_variance_pct", "outturn_rag"],
          column_config={"budget_area": "Area", "rag": "YTD RAG", "budget_gbp": gbp("FY budget"), "budget_ytd_gbp": gbp("YTD budget"),
                         "actual_ytd_gbp": gbp("YTD actual"), "ytd_variance_gbp": gbp("YTD variance"),
                         "ytd_variance_pct": pct("YTD var %"), "forecast_remaining_gbp": gbp("Forecast remaining"),
                         "outturn_gbp": gbp("Projected outturn"), "outturn_variance_gbp": gbp("FY variance"),
                         "outturn_variance_pct": pct("FY var %"), "outturn_rag": "Outturn RAG"})

with section("Cost centre variance", "Closed months in the date range · select a cost centre for its monthly profile"):
    cc = closed.groupby(["budget_area", "dimension_key"], as_index=False)[["budget_gbp", "actual_gbp"]].sum()
    cc["variance"] = cc["actual_gbp"] - cc["budget_gbp"]
    cc["variance_pct"] = cc["variance"] / cc["budget_gbp"].where(cc["budget_gbp"] != 0)
    cc["rag"] = cc["variance_pct"].map(lambda v: rag_for("budget_variance", v))
    cc = cc.sort_values("variance", ascending=False)
    c1, c2 = st.columns([3, 2])
    with c1:
        sel = table(cc, key="bud_cc", alt="Variance by cost centre", csv_name="cost centre variance", rag_cols=["rag"], height=380,
                    column_config={"budget_area": "Area", "dimension_key": "Cost centre", "budget_gbp": gbp("Budget"),
                                   "actual_gbp": gbp("Actual"), "variance": gbp("Variance"), "variance_pct": pct("Var %"),
                                   "rag": "RAG"})
    with c2:
        top = cc.reindex(cc["variance"].abs().sort_values(ascending=False).index).head(12)
        top = top.assign(direction=top["variance"].map(lambda v: "Red" if v > 0 else "Green"))
        charts.show(charts.bar(top, "dimension_key", "variance", "direction", horizontal=True, colors=charts.RAG_COLOURS,
                               height=380, order=top["dimension_key"].tolist()), alt="Largest cost centre variances")

if sel is not None:
    with section(f"Drill-down · {sel['budget_area']} · {sel['dimension_key']}"):
        d = bva_all[(bva_all["budget_area"] == sel["budget_area"]) & (bva_all["dimension_key"] == sel["dimension_key"])] \
            .sort_values("period_month")
        long = d.melt(id_vars="period_month", value_vars=["budget_gbp", "actual_gbp", "forecast_gbp"], var_name="series",
                      value_name="gbp").dropna().replace({"budget_gbp": "Budget", "actual_gbp": "Actual", "forecast_gbp": "Forecast"})
        charts.show(charts.line(long, "period_month", "gbp", "series", height=300, markers=True,
                                colors={"Budget": charts.TEAL, "Actual": charts.NAVY, "Forecast": charts.SLATE}),
                    alt="Monthly budget, actual and forecast for the selected cost centre")
        cols_d = ["period_month", "fiscal_year", "budget_gbp", "actual_gbp", "forecast_gbp", "variance_gbp", "variance_pct"]
        download(d[cols_d], f"{sel['dimension_key']} monthly budget", key="dl_bud_drill")
