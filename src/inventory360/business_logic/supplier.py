"""Supplier risk segmentation and concentration analysis."""
from __future__ import annotations

import pandas as pd


def risk_rating(score: float | None) -> str:
    """Map a 0-100 composite performance score to a risk rating."""
    if score is None or pd.isna(score):
        return "High"
    if score >= 85:
        return "Low"
    if score >= 72:
        return "Medium"
    return "High"


def spend_concentration(scorecard: pd.DataFrame, top_n: int = 5) -> float:
    """Share of 12-month spend placed with the top-N suppliers."""
    spend = scorecard["spend_gbp"].fillna(0).sort_values(ascending=False)
    total = spend.sum()
    return float(spend.head(top_n).sum() / total) if total else 0.0


def supplier_actions(row: pd.Series) -> str:
    """Recommended commercial action for a supplier scorecard row."""
    otif = row.get("otif_rate") or 0
    variability = row.get("lead_time_variability_days") or 0
    if row.get("risk_rating") == "High" and row.get("contract_tier") == "Strategic":
        return "Escalate: joint improvement plan and dual-source critical lines"
    if row.get("risk_rating") == "High":
        return "Review contract; qualify alternative supplier"
    if otif < 0.80:
        return "Agree OTIF recovery plan at next QBR"
    if variability > 7:
        return "Increase safety stock / move to fixed sailing schedule"
    return "Maintain - monitor monthly"
