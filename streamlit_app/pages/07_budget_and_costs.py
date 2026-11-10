import altair as alt
import pandas as pd
import streamlit as st

from components import charts
from components.layout import kpi, page_header
from inventory360.business_logic.budget import full_year_outturn, variance_rag
from inventory360.data_access import queries
from inventory360.utils.formatting import fmt_gbp, fmt_pct

bva_all = queries.load_budget_vs_actual()
as_of = pd.Timestamp(queries.load_data_freshness()["as_of_date"].iloc[0])
page_header("Budget & costs", "Budget, actuals and full-year outturn for inventory purchasing, freight and warehousing",
            ":material/account_balance:", as_of)

years = sorted(bva_all["fiscal_year"].unique())
current_fy = bva_all.loc[bva_all["period_month"] <= as_of, "fiscal_year"].max()
with st.container(horizontal=True, vertical_alignment="bottom"):
    fy = st.segmented_control("Financial year", years, default=current_fy, key="bud_fy")
    area = st.segmented_control("Budget area", ["All", "Inventory Purchases", "Freight & Duty", "Warehousing"],
                                default="All", key="bud_area")
fy = fy or current_fy
area = area or "All"

outturn = full_year_outturn(bva_all, fy)
bva = bva_all[bva_all["fiscal_year"] == fy]
if area != "All":
    bva = bva[bva["budget_area"] == area]
    outturn_sel = outturn[outturn["budget_area"] == area]
else:
    outturn_sel = outturn

budget = outturn_sel["budget_gbp"].sum()
actual = outturn_sel["actual_ytd_gbp"].sum()
budget_ytd = outturn_sel["budget_ytd_gbp"].sum()
proj = outturn_sel["outturn_gbp"].sum()

cols = st.columns(4)
with cols[0]:
    kpi(f"{fy} budget", fmt_gbp(budget))
with cols[1]:
    kpi("Actual year to date", fmt_gbp(actual), actual, budget_ytd, inverse=True, desc="vs YTD budget")
with cols[2]:
    kpi("YTD variance", fmt_gbp(actual - budget_ytd), help=f"{fmt_pct((actual - budget_ytd) / budget_ytd if budget_ytd else None, signed=True)} vs budget; positive = overspend")
with cols[3]:
    kpi("Projected full-year outturn", fmt_gbp(proj), proj, budget, inverse=True, desc="vs full-year budget",
        help="Actuals for closed months plus latest forecast for the remainder of the year.")

with st.container(border=True):
    st.subheader("Full-year outturn by area", anchor=False)
    view = outturn.copy()
    view["status"] = view["rag"].map({"Green": "Green · on track", "Amber": "Amber · watch", "Red": "Red · overspend", "n/a": "–"})
    st.dataframe(
        view[["budget_area", "status", "budget_gbp", "budget_ytd_gbp", "actual_ytd_gbp", "ytd_variance_gbp",
              "ytd_variance_pct", "forecast_remaining_gbp", "outturn_gbp", "outturn_variance_gbp", "outturn_variance_pct"]],
        hide_index=True, alt="Full-year outturn by budget area",
        column_config={
            "budget_area": "Area", "status": "RAG",
            "budget_gbp": st.column_config.NumberColumn("FY budget", format="£%,.0f"),
            "budget_ytd_gbp": st.column_config.NumberColumn("YTD budget", format="£%,.0f"),
            "actual_ytd_gbp": st.column_config.NumberColumn("YTD actual", format="£%,.0f"),
            "ytd_variance_gbp": st.column_config.NumberColumn("YTD variance", format="£%,.0f"),
            "ytd_variance_pct": st.column_config.NumberColumn("YTD var %", format="percent"),
            "forecast_remaining_gbp": st.column_config.NumberColumn("Forecast remaining", format="£%,.0f"),
            "outturn_gbp": st.column_config.NumberColumn("Projected outturn", format="£%,.0f"),
            "outturn_variance_gbp": st.column_config.NumberColumn("FY variance", format="£%,.0f"),
            "outturn_variance_pct": st.column_config.NumberColumn("FY var %", format="percent"),
        },
    )

monthly = bva.groupby("period_month", as_index=False).agg(budget=("budget_gbp", "sum"), actual=("actual_gbp", "sum"),
                                                          forecast=("forecast_gbp", "sum"), actualised=("is_actualised", "max"))
monthly["actual"] = monthly["actual"].where(monthly["actualised"])
monthly["forecast"] = monthly["forecast"].where(monthly["forecast"] > 0)
long = monthly.melt(id_vars="period_month", value_vars=["actual", "forecast"], var_name="type", value_name="value").dropna()

with st.container(border=True):
    st.subheader("Monthly actual / forecast vs budget", anchor=False)
    bars = alt.Chart(long).mark_bar(opacity=0.85).encode(
        x=alt.X("yearmonth(period_month):T", title=None, axis=alt.Axis(format="%b %y")),
        y=alt.Y("value:Q", title="£", axis=charts.GBP_AXIS),
        color=alt.Color("type:N", title=None, scale=alt.Scale(domain=["actual", "forecast"], range=["#1D4ED8", "#93C5FD"]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("yearmonth(period_month):T", title="Month"), "type:N", alt.Tooltip("value:Q", format=",.0f")],
    )
    budget_line = alt.Chart(monthly).mark_line(color="#0F172A", strokeDash=[5, 3], point=True).encode(
        x="yearmonth(period_month):T", y="budget:Q",
        tooltip=[alt.Tooltip("yearmonth(period_month):T", title="Month"), alt.Tooltip("budget:Q", title="Budget", format=",.0f")],
    )
    st.altair_chart(alt.layer(bars, budget_line).properties(height=320).configure_view(strokeWidth=0),
                    alt="Monthly actual and forecast against budget")

with st.container(border=True):
    st.subheader("Variance by cost centre (closed months)", anchor=False)
    closed = bva[bva["is_actualised"]]
    dim = closed.groupby(["budget_area", "dimension_key"], as_index=False).agg(budget=("budget_gbp", "sum"), actual=("actual_gbp", "sum"))
    dim["variance"] = dim["actual"] - dim["budget"]
    dim["variance_pct"] = dim["variance"] / dim["budget"]
    dim["rag"] = dim["variance_pct"].map(variance_rag)
    c1, c2 = st.columns([3, 2])
    with c1:
        st.dataframe(
            dim.sort_values("variance", ascending=False), hide_index=True, height=360, alt="Variance by cost centre",
            column_config={
                "budget_area": "Area", "dimension_key": "Cost centre",
                "budget": st.column_config.NumberColumn("Budget", format="£%,.0f"),
                "actual": st.column_config.NumberColumn("Actual", format="£%,.0f"),
                "variance": st.column_config.NumberColumn("Variance", format="£%,.0f"),
                "variance_pct": st.column_config.NumberColumn("Var %", format="percent"),
                "rag": "RAG",
            },
        )
    with c2:
        top = dim.reindex(dim["variance"].abs().sort_values(ascending=False).index).head(12)
        st.altair_chart(
            alt.Chart(top).mark_bar(cornerRadiusEnd=3).encode(
                y=alt.Y("dimension_key:N", title=None, sort="-x"),
                x=alt.X("variance:Q", title="Variance (£, + = overspend)", axis=charts.GBP_AXIS),
                color=alt.condition("datum.variance > 0", alt.value("#B42318"), alt.value("#12B76A")),
                tooltip=["budget_area:N", "dimension_key:N", alt.Tooltip("variance:Q", format=",.0f"),
                         alt.Tooltip("variance_pct:Q", format=".1%")],
            ).properties(height=360),
            alt="Largest cost centre variances",
        )
