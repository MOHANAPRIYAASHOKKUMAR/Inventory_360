import pandas as pd
import streamlit as st

from components import charts, filters
from components.layout import day, download, filter_scope, kpi, num, page_header, pct, section, table
from inventory360.analytics.forecasting import forecast_accuracy, holt_winters_forecast, to_weekly
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.data_access import queries
from inventory360.data_access.queries import INVENTORY_COLS
from inventory360.utils.formatting import fmt_int, fmt_pct

f = filters.current()
page_header("Demand forecast", "Weekly demand forecast with seasonality and 80% prediction intervals", as_of=f.end)
filter_scope(f, INVENTORY_COLS, use_date=False, note="history runs to the end of the date range; forecast starts after it")

with st.container(horizontal=True, vertical_alignment="bottom"):
    horizon = st.slider("Horizon (weeks)", 4, 26, 13, key="fc_horizon")
    show_band = st.toggle("Show prediction interval", value=True, key="fc_band")


@st.cache_data(ttl=600, show_spinner=False)
def run_forecast(series: pd.Series, h: int) -> pd.DataFrame:
    return holt_winters_forecast(series, horizon=h)


daily = queries.demand_daily(f)
weekly = to_weekly(daily)
try:
    fc = run_forecast(weekly, horizon)
except ValueError as exc:
    st.warning(str(exc), icon=":material/warning:", title="Not enough history for this filter")
    st.stop()

fit_window = fc[fc["actual"].notna()].tail(26)
acc = forecast_accuracy(fit_window["actual"], fit_window["fitted"])
accuracy = 1 - acc["wape"] if acc["wape"] is not None else None
future = fc[fc["forecast"].notna()]
end = pd.Timestamp(f.end)
ly = weekly[(weekly.index > end - pd.Timedelta(weeks=52)) & (weekly.index <= end - pd.Timedelta(weeks=52 - horizon))].sum()

cols = st.columns(4)
with cols[0]:
    kpi(f"Forecast next {horizon} weeks", f"{fmt_int(future['forecast'].sum())} units", current=future["forecast"].sum(),
        previous=ly or None, desc="vs same weeks last year")
with cols[1]:
    kpi("Last 4 weeks actual", f"{fmt_int(weekly.tail(4).sum())} units", current=weekly.tail(4).sum(),
        previous=weekly.iloc[-8:-4].sum(), desc="vs previous 4 weeks")
with cols[2]:
    kpi("Forecast accuracy", fmt_pct(accuracy), status=rag_for("forecast_accuracy", accuracy),
        status_text=f"Target ≥ {fmt_pct(TARGETS['forecast_accuracy'].green, 0)}",
        help="1 − WAPE over the last 26 fitted weeks.")
with cols[3]:
    bias = acc["bias"]
    kpi("Forecast bias", fmt_pct(bias, signed=True), status="Green" if bias is not None and abs(bias) <= 0.05 else "Amber",
        status_text="Within ±5%" if bias is not None and abs(bias) <= 0.05 else "Outside ±5%", help="Positive = over-forecasting.")

with section("Weekly demand", "Navy = actual · dotted = model fit · teal = forecast"):
    fig = charts.forecast(fc[fc["week"] >= fc["week"].max() - pd.Timedelta(weeks=78)])
    if not show_band:
        fig.data = fig.data[1:]
    charts.show(fig, alt="Weekly demand actuals and forecast")

c1, c2 = st.columns([2, 3])
with c1:
    with section("Forecast table"):
        tbl = future[["week", "forecast", "lower", "upper"]]
        table(tbl, key="fc_table", select=False, alt="Weekly forecast values", csv_name="demand forecast", height=360,
              column_config={"week": day("Week ending"), "forecast": num("Forecast"), "lower": num("Lower (80%)"),
                             "upper": num("Upper (80%)")})
with c2:
    with section("Forecast by category", "Select a category to view its own forecast"):
        cat_daily = queries.demand_daily(f, by_category=True)
        rows = []
        for cat, g in cat_daily.groupby("category"):
            s = to_weekly(g)
            try:
                cfc = run_forecast(s, horizon)
            except ValueError:
                continue
            w = cfc[cfc["actual"].notna()].tail(26)
            a = forecast_accuracy(w["actual"], w["fitted"])
            fut = cfc["forecast"].sum()
            last = s.tail(horizon).sum()
            rows.append({"category": cat, "forecast": fut, "last_period": last, "change": fut / last - 1 if last else None,
                         "accuracy": 1 - a["wape"] if a["wape"] is not None else None})
        cats = pd.DataFrame(rows).sort_values("forecast", ascending=False)
        cats["status"] = cats["accuracy"].map(lambda v: rag_for("forecast_accuracy", v))
        sel = table(cats, key="fc_cats", alt="Forecast by category", csv_name="forecast by category", rag_cols=["status"],
                    height=360,
                    column_config={"category": "Category", "forecast": num(f"Next {horizon} wks"),
                                   "last_period": num(f"Last {horizon} wks"), "change": pct("Change"),
                                   "accuracy": pct("Accuracy"), "status": "RAG"})

if sel is not None:
    with section(f"Drill-down · {sel['category']}"):
        g = cat_daily[cat_daily["category"] == sel["category"]]
        cfc = run_forecast(to_weekly(g), horizon)
        charts.show(charts.forecast(cfc[cfc["week"] >= cfc["week"].max() - pd.Timedelta(weeks=78)], height=320),
                    alt=f"Weekly demand and forecast for {sel['category']}")
        download(cfc, f"{sel['category']} forecast", key="dl_fc_drill")

st.caption("Model: additive Holt-Winters (level, trend and 52-week seasonality when at least 60 weeks of history exist). "
           "Use for planning conversations; the replenishment engine uses the 28-day demand baseline.")
