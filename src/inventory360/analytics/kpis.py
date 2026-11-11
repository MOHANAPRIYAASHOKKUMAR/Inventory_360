"""Network KPI rollups computed from the daily trend frame.

All ratios are re-derived from summed numerators and denominators so that
filtered views (site / category) stay mathematically consistent.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PeriodKpis:
    start: pd.Timestamp
    end: pd.Timestamp
    avg_stock_value_gbp: float
    closing_stock_value_gbp: float
    net_sales_gbp: float
    cogs_gbp: float
    gross_margin_pct: float | None
    lost_sales_gbp: float
    fill_rate: float | None
    availability: float | None
    stock_turns: float | None
    days_cover: float | None


def period_kpis(daily: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> PeriodKpis:
    """KPIs for the inclusive window [start, end] of a filtered daily trend frame."""
    w = daily[(daily["snapshot_date"] >= start) & (daily["snapshot_date"] <= end)]
    by_day = w.groupby("snapshot_date").agg(
        stock_value_gbp=("stock_value_gbp", "sum"),
        net_sales_gbp=("net_sales_gbp", "sum"),
        cogs_gbp=("cogs_gbp", "sum"),
        lost_sales_gbp=("lost_sales_gbp", "sum"),
        units_demanded=("units_demanded", "sum"),
        units_sold=("units_sold", "sum"),
        sku_locations=("sku_locations", "sum"),
        sku_locations_oos=("sku_locations_oos", "sum"),
    )
    days = len(by_day)
    if days == 0:
        return PeriodKpis(start, end, 0, 0, 0, 0, None, 0, None, None, None, None)
    avg_stock = by_day["stock_value_gbp"].mean()
    sales = by_day["net_sales_gbp"].sum()
    cogs = by_day["cogs_gbp"].sum()
    demanded = by_day["units_demanded"].sum()
    locations = by_day["sku_locations"].sum()
    daily_cogs = cogs / days
    return PeriodKpis(
        start=start,
        end=end,
        avg_stock_value_gbp=float(avg_stock),
        closing_stock_value_gbp=float(by_day["stock_value_gbp"].iloc[-1]),
        net_sales_gbp=float(sales),
        cogs_gbp=float(cogs),
        gross_margin_pct=float((sales - cogs) / sales) if sales else None,
        lost_sales_gbp=float(by_day["lost_sales_gbp"].sum()),
        fill_rate=float(by_day["units_sold"].sum() / demanded) if demanded else None,
        availability=float(1 - by_day["sku_locations_oos"].sum() / locations) if locations else None,
        stock_turns=float(daily_cogs * 365 / avg_stock) if avg_stock else None,
        days_cover=float(by_day["stock_value_gbp"].iloc[-1] / daily_cogs) if daily_cogs else None,
    )


def comparison_window(end: pd.Timestamp, days: int) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """Current window of ``days`` ending at ``end`` and the equal-length prior window."""
    cur_start = end - pd.Timedelta(days=days - 1)
    prev_end = cur_start - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=days - 1)
    return cur_start, end, prev_start, prev_end


def weekly_trend(daily: pd.DataFrame) -> pd.DataFrame:
    """Weekly network trend with derived availability and cover."""
    d = daily.copy()
    d["week"] = d["snapshot_date"].dt.to_period("W-SUN").dt.start_time
    by_day = d.groupby(["week", "snapshot_date"], as_index=False).agg(
        stock_value_gbp=("stock_value_gbp", "sum"),
        net_sales_gbp=("net_sales_gbp", "sum"),
        cogs_gbp=("cogs_gbp", "sum"),
        lost_sales_gbp=("lost_sales_gbp", "sum"),
        sku_locations=("sku_locations", "sum"),
        sku_locations_oos=("sku_locations_oos", "sum"),
    )
    wk = by_day.groupby("week", as_index=False).agg(
        stock_value_gbp=("stock_value_gbp", "mean"),
        net_sales_gbp=("net_sales_gbp", "sum"),
        cogs_gbp=("cogs_gbp", "sum"),
        lost_sales_gbp=("lost_sales_gbp", "sum"),
        sku_locations=("sku_locations", "sum"),
        sku_locations_oos=("sku_locations_oos", "sum"),
        days=("snapshot_date", "nunique"),
    )
    wk["availability"] = 1 - wk["sku_locations_oos"] / wk["sku_locations"]
    wk["days_cover"] = wk["stock_value_gbp"] / (wk["cogs_gbp"] / wk["days"])
    # Partial weeks (start of history / current week) distort weekly sums
    return wk[wk["days"] == 7].reset_index(drop=True)


GRAINS = {"Daily": "D", "Weekly": "W-SUN", "Monthly": "MS"}


def bucket(df: pd.DataFrame, date_col: str, grain: str, sums: list[str], by: list[str] | None = None,
           means: list[str] | None = None) -> pd.DataFrame:
    """Aggregate a daily frame to Daily / Weekly (week starting Monday) / Monthly periods.

    ``sums`` are flow measures added up across days; ``means`` are stock measures
    averaged across the days in the period (e.g. stock value).
    """
    d = df.copy()
    ts = pd.to_datetime(d[date_col])
    if grain == "Weekly":
        d["period"] = (ts - pd.to_timedelta(ts.dt.dayofweek, unit="D")).dt.normalize()
    elif grain == "Monthly":
        d["period"] = ts.dt.to_period("M").dt.start_time
    else:
        d["period"] = ts.dt.normalize()
    keys = ["period", *(by or [])]
    means = means or []
    # Stock measures: sum across groups per day first, then average days within the period
    if means:
        per_day = d.groupby([*keys, date_col], as_index=False)[means].sum()
        avg = per_day.groupby(keys, as_index=False)[means].mean()
    out = d.groupby(keys, as_index=False)[sums].sum() if sums else d[keys].drop_duplicates()
    if means:
        out = out.merge(avg, on=keys, how="left")
    return out.sort_values(keys).reset_index(drop=True)
