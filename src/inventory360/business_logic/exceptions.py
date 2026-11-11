"""Red / amber / green exception rules shared by every dashboard page.

Targets are business policy, kept in one place so a KPI is judged the same way
wherever it appears. ``higher_is_better`` decides the direction of the bands.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

GREEN, AMBER, RED, NA = "Green", "Amber", "Red", "n/a"


@dataclass(frozen=True)
class Target:
    label: str
    green: float          # threshold for green
    amber: float          # threshold for amber (beyond it = red)
    higher_is_better: bool = True
    fmt: str = "pct"      # pct | days | ratio | gbp


TARGETS: dict[str, Target] = {
    "availability":        Target("On-shelf availability", 0.96, 0.93),
    "fill_rate":           Target("Demand fill rate", 0.97, 0.94),
    "otif":                Target("Supplier OTIF", 0.90, 0.80),
    "on_time_arrival":     Target("On-time arrival", 0.92, 0.85),
    "gross_margin":        Target("Gross margin", 0.35, 0.30),
    "forecast_accuracy":   Target("Forecast accuracy", 0.85, 0.75),
    "stock_turns":         Target("Stock turn", 8.0, 6.0, fmt="ratio"),
    "days_cover":          Target("Days of cover", 45.0, 60.0, higher_is_better=False, fmt="days"),
    "utilisation_peak":    Target("Peak utilisation", 0.85, 0.92, higher_is_better=False),
    "budget_variance":     Target("Budget variance", 0.03, 0.07, higher_is_better=False),
    "lost_sales_share":    Target("Lost sales % of sales", 0.02, 0.04, higher_is_better=False),
    "freshness_hours":     Target("Data age (hours)", 30.0, 54.0, higher_is_better=False, fmt="ratio"),
}


def rag(value: float | None, target: Target) -> str:
    """Classify a value against a target. Missing values are ``n/a``."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return NA
    if target.higher_is_better:
        return GREEN if value >= target.green else AMBER if value >= target.amber else RED
    return GREEN if value <= target.green else AMBER if value <= target.amber else RED


def rag_for(key: str, value: float | None) -> str:
    return rag(value, TARGETS[key])


def worst(statuses) -> str:
    """Most severe status in a collection (Red > Amber > Green > n/a)."""
    order = {RED: 3, AMBER: 2, GREEN: 1, NA: 0}
    statuses = list(statuses)
    return max(statuses, key=lambda s: order.get(s, 0)) if statuses else NA
