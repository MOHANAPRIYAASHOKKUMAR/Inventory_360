"""Lightweight demand forecasting for planning conversations.

Uses an additive Holt-Winters style model on weekly demand (level + trend +
52-week seasonality when enough history exists, otherwise level + trend).
Kept dependency-free (numpy / pandas) so it runs inside Streamlit in Snowflake.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def to_weekly(daily: pd.DataFrame, date_col: str = "snapshot_date", value_col: str = "units_demanded") -> pd.Series:
    s = daily.set_index(date_col)[value_col].resample("W-SUN").sum()
    # Drop a trailing partial week so it does not drag the level down
    if len(daily) and daily[date_col].max().dayofweek != 6:
        s = s.iloc[:-1]
    return s


def holt_winters_forecast(series: pd.Series, horizon: int = 12, alpha: float = 0.35,
                          beta: float = 0.05, gamma: float = 0.30, season: int = 52) -> pd.DataFrame:
    """Return a frame of fitted + forecast values with an 80% prediction band."""
    y = series.astype(float).to_numpy()
    n = len(y)
    if n < 8:
        raise ValueError("At least 8 weeks of history are required")
    seasonal = n >= season + 8
    level = y[:8].mean()
    trend = (y[4:8].mean() - y[:4].mean()) / 4
    s_idx = np.zeros(season)
    if seasonal:
        s_idx = y[:season] - y[:season].mean()

    fitted = np.empty(n)
    for t in range(n):
        s = s_idx[t % season] if seasonal else 0.0
        fitted[t] = level + trend + s
        prev_level = level
        level = alpha * (y[t] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        if seasonal:
            s_idx[t % season] = gamma * (y[t] - level) + (1 - gamma) * s

    resid_sd = float(np.std(y[-26:] - fitted[-26:], ddof=1)) if n > 27 else float(np.std(y - fitted, ddof=1))
    steps = np.arange(1, horizon + 1)
    fc = np.array([level + h * trend + (s_idx[(n + h - 1) % season] if seasonal else 0.0) for h in steps])
    fc = np.clip(fc, 0, None)
    band = 1.28 * resid_sd * np.sqrt(steps)

    idx_future = pd.date_range(series.index[-1] + pd.Timedelta(weeks=1), periods=horizon, freq="W-SUN")
    hist = pd.DataFrame({"week": series.index, "actual": y, "fitted": fitted, "forecast": np.nan,
                         "lower": np.nan, "upper": np.nan})
    fut = pd.DataFrame({"week": idx_future, "actual": np.nan, "fitted": np.nan, "forecast": fc,
                        "lower": np.clip(fc - band, 0, None), "upper": fc + band})
    return pd.concat([hist, fut], ignore_index=True)


def forecast_accuracy(actual: pd.Series, fitted: pd.Series) -> dict:
    """MAPE / WAPE / bias over the overlapping, non-null window."""
    mask = actual.notna() & fitted.notna()
    a, f = actual[mask].astype(float), fitted[mask].astype(float)
    if a.sum() == 0:
        return {"wape": None, "bias": None, "mape": None}
    nz = a != 0
    return {
        "wape": float((a - f).abs().sum() / a.sum()),
        "bias": float((f - a).sum() / a.sum()),
        "mape": float(((a[nz] - f[nz]).abs() / a[nz]).mean()) if nz.any() else None,
    }
