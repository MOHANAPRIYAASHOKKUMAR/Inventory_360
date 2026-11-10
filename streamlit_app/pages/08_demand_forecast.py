import pandas as pd
import streamlit as st

from components import charts
from components.layout import apply_filters, kpi, page_header
from inventory360.analytics.forecasting import forecast_accuracy, holt_winters_forecast
from inventory360.data_access import queries
from inventory360.utils.formatting import fmt_int, fmt_pct

daily_all = queries.load_network_daily_trend()
products = queries.load_products()
as_of = daily_all["snapshot_date"].max()
page_header("Demand forecast", "Weekly demand forecast with seasonality and prediction intervals", ":material/trending_up:", as_of)

LEVELS = ["Category", "SKU"]
with st.container(horizontal=True, vertical_alignment="bottom"):
    level = st.segmented_control("Forecast level", LEVELS, default="Category", key="fc_level")
    horizon = st.slider("Horizon (weeks)", 4, 26, 13, key="fc_horizon")

level = level or "Category"
if level == "Category":
    cats = sorted(daily_all["category"].unique())
    category = st.selectbox("Category", cats, index=cats.index("Toys & Seasonal"), key="fc_category")
    hist = apply_filters(daily_all, category_col=None)
    hist = hist[hist["category"] == category].groupby("snapshot_date", as_index=False)["units_demanded"].sum()
    title = category
else:
    options = products.sort_values(["category", "product_name"])
    labels = dict(zip(options["sku"], options["sku"] + " · " + options["product_name"]))
    sku = st.selectbox("SKU", list(labels), format_func=labels.get, key="fc_sku")
    hist = queries.load_sku_daily_history(sku)
    title = labels[sku]

weekly = hist.set_index("snapshot_date")["units_demanded"].resample("W-SUN").sum()
if as_of.dayofweek != 6:
    weekly = weekly.iloc[:-1]  # exclude the partial current week

try:
    fc = holt_winters_forecast(weekly, horizon=horizon)
except ValueError as exc:
    st.warning(str(exc), icon=":material/warning:")
    st.stop()

acc = forecast_accuracy(fc["actual"].tail(horizon + 26).head(26), fc["fitted"].tail(horizon + 26).head(26))
future = fc[fc["forecast"].notna()]
same_period_ly = weekly[(weekly.index > as_of - pd.Timedelta(weeks=52)) &
                        (weekly.index <= as_of - pd.Timedelta(weeks=52) + pd.Timedelta(weeks=horizon))].sum()

cols = st.columns(4)
with cols[0]:
    kpi(f"Forecast next {horizon} weeks", f"{fmt_int(future['forecast'].sum())} units",
        future["forecast"].sum(), same_period_ly or None, desc="vs same weeks last year")
with cols[1]:
    kpi("Last 4 weeks actual", f"{fmt_int(weekly.tail(4).sum())} units", weekly.tail(4).sum(), weekly.iloc[-8:-4].sum())
with cols[2]:
    kpi("Forecast accuracy (1 - WAPE)", fmt_pct(1 - acc["wape"]) if acc["wape"] is not None else "–",
        help="Weighted absolute percentage error over the last 26 fitted weeks.")
with cols[3]:
    kpi("Forecast bias", fmt_pct(acc["bias"], signed=True) if acc["bias"] is not None else "–",
        help="Positive = over-forecasting.")

with st.container(border=True):
    st.subheader(title, anchor=False)
    st.caption("Black = actual weekly demand · dashed = model fit · blue = forecast with 80% prediction interval")
    st.altair_chart(charts.forecast_chart(fc), alt="Weekly demand actuals and forecast")

with st.expander("Forecast table", icon=":material/table:"):
    st.dataframe(
        future[["week", "forecast", "lower", "upper"]], hide_index=True, alt="Weekly forecast values",
        column_config={
            "week": st.column_config.DateColumn("Week ending", format="DD MMM YYYY"),
            "forecast": st.column_config.NumberColumn("Forecast", format="%,.0f"),
            "lower": st.column_config.NumberColumn("Lower (80%)", format="%,.0f"),
            "upper": st.column_config.NumberColumn("Upper (80%)", format="%,.0f"),
        },
    )
    st.download_button("Download forecast (CSV)", future.to_csv(index=False).encode("utf-8"),
                       file_name="demand_forecast.csv", mime="text/csv", icon=":material/download:")

st.caption("Model: additive Holt-Winters (level, trend, 52-week seasonality where at least 60 weeks of history exist). "
           "Use for planning conversations; the replenishment engine uses the 28-day demand baseline.")
