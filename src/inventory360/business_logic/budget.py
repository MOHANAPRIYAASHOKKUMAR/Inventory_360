"""Budget control: variance RAG status and full-year outturn."""
from __future__ import annotations

import pandas as pd

from inventory360.utils.config import VARIANCE_AMBER, VARIANCE_RED


def variance_rag(variance_pct: float | None) -> str:
    """Cost budgets: overspend is adverse. Returns Green / Amber / Red / n/a."""
    if variance_pct is None or pd.isna(variance_pct):
        return "n/a"
    if variance_pct > VARIANCE_RED:
        return "Red"
    if variance_pct > VARIANCE_AMBER:
        return "Amber"
    return "Green"


def full_year_outturn(bva: pd.DataFrame, fiscal_year: str) -> pd.DataFrame:
    """Budget, actual-to-date, forecast remainder and projected outturn by area."""
    fy = bva[bva["fiscal_year"] == fiscal_year]
    out = (
        fy.groupby("budget_area", as_index=False)
        .agg(
            budget_gbp=("budget_gbp", "sum"),
            actual_ytd_gbp=("actual_gbp", "sum"),
            budget_ytd_gbp=("budget_gbp", lambda s: s[fy.loc[s.index, "is_actualised"]].sum()),
            forecast_remaining_gbp=("forecast_gbp", "sum"),
        )
    )
    # Months that are neither actualised nor forecast (current month) use budget
    open_budget = (
        fy[~fy["is_actualised"] & fy["forecast_gbp"].isna()]
        .groupby("budget_area")["budget_gbp"].sum()
    )
    out["forecast_remaining_gbp"] += out["budget_area"].map(open_budget).fillna(0)
    out["outturn_gbp"] = out["actual_ytd_gbp"] + out["forecast_remaining_gbp"]
    out["ytd_variance_gbp"] = out["actual_ytd_gbp"] - out["budget_ytd_gbp"]
    out["ytd_variance_pct"] = out["ytd_variance_gbp"] / out["budget_ytd_gbp"].where(out["budget_ytd_gbp"] != 0)
    out["outturn_variance_gbp"] = out["outturn_gbp"] - out["budget_gbp"]
    out["outturn_variance_pct"] = out["outturn_variance_gbp"] / out["budget_gbp"].where(out["budget_gbp"] != 0)
    out["rag"] = out["ytd_variance_pct"].map(variance_rag)
    return out
