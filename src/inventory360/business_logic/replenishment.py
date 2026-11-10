"""Replenishment policy - periodic review (R, s, S) with service-level safety stock.

Mirrors the logic in ``dbt_inventory/models/marts/reporting/rpt_inventory_position.sql``
so planners can run what-if scenarios in the app (different service levels,
lead-time buffers or demand uplifts) without rebuilding the mart.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from inventory360.utils.config import STOCK_STATUS_ORDER

# Inverse standard normal for common service levels (avoids a scipy dependency)
_Z_TABLE = {
    0.80: 0.84, 0.85: 1.04, 0.90: 1.28, 0.925: 1.44, 0.95: 1.65,
    0.97: 1.88, 0.98: 2.05, 0.99: 2.33, 0.995: 2.58,
}


def z_for_service_level(service_level: float) -> float:
    """z-score for a cycle service level, interpolating the lookup table."""
    if not 0.5 <= service_level < 1:
        raise ValueError("service_level must be in [0.5, 1)")
    levels = sorted(_Z_TABLE)
    if service_level <= levels[0]:
        return _Z_TABLE[levels[0]]
    if service_level >= levels[-1]:
        return _Z_TABLE[levels[-1]]
    return float(np.interp(service_level, levels, [_Z_TABLE[k] for k in levels]))


def safety_stock(z: float, sigma_daily: float, lead_time_days: float) -> int:
    return int(math.ceil(z * sigma_daily * math.sqrt(max(lead_time_days, 0))))


def reorder_point(mean_daily: float, sigma_daily: float, lead_time_days: float, z: float) -> int:
    return int(math.ceil(mean_daily * lead_time_days + z * sigma_daily * math.sqrt(max(lead_time_days, 0))))


def round_up_to_moq(qty: float, moq: int) -> int:
    if qty <= 0:
        return 0
    moq = max(int(moq), 1)
    return int(math.ceil(qty / moq) * moq)


def classify_stock_status(qty_on_hand: float, mean_daily: float,
                          critical: float = 3, low: float = 7,
                          overstock: float = 60, excess: float = 120) -> str:
    if qty_on_hand <= 0 and mean_daily > 0:
        return "Out of stock"
    if mean_daily <= 0:
        return "Excess" if qty_on_hand > 0 else "Healthy"
    cover = qty_on_hand / mean_daily
    if cover < critical:
        return "Critical"
    if cover < low:
        return "Low"
    if cover > excess:
        return "Excess"
    if cover > overstock:
        return "Overstock"
    return "Healthy"


def priority(status: str, velocity_class: str, order_qty: int) -> str:
    if order_qty <= 0:
        return "None"
    if status in ("Out of stock", "Critical"):
        return "P1 - Urgent" if velocity_class == "A" else "P2 - High"
    if status == "Low":
        return "P3 - Medium"
    return "P4 - Routine"


@dataclass(frozen=True)
class Scenario:
    """Planner what-if levers applied on top of the base policy."""
    service_level_a: float = 0.95
    service_level_b: float = 0.90
    service_level_c: float = 0.85
    demand_uplift: float = 0.0          # e.g. 0.15 = +15% demand
    lead_time_buffer_days: int = 0      # extra days added to supplier lead time


def recalculate_plan(position: pd.DataFrame, scenario: Scenario) -> pd.DataFrame:
    """Recompute reorder points and order quantities for a scenario.

    Expects the columns produced by RPT_INVENTORY_POSITION.
    """
    df = position.copy()
    service = df["velocity_class"].map(
        {"A": scenario.service_level_a, "B": scenario.service_level_b, "C": scenario.service_level_c}
    ).fillna(scenario.service_level_c)
    df["scenario_z"] = service.map(z_for_service_level)
    mean = df["avg_daily_demand"] * (1 + scenario.demand_uplift)
    sigma = df["stddev_daily_demand"] * (1 + scenario.demand_uplift)
    lead = df["lead_time_days"] + scenario.lead_time_buffer_days
    sqrt_lead = np.sqrt(lead.clip(lower=0))

    df["scenario_safety_stock"] = np.ceil(df["scenario_z"] * sigma * sqrt_lead)
    df["scenario_reorder_point"] = np.ceil(mean * lead + df["scenario_z"] * sigma * sqrt_lead)
    df["scenario_order_up_to"] = np.ceil(mean * (lead + df["review_period_days"]) + df["scenario_z"] * sigma * sqrt_lead)

    need = (df["inventory_position_qty"] < df["scenario_reorder_point"]) & (df["lifecycle_status"] != "Discontinued")
    raw_qty = (df["scenario_order_up_to"] - df["inventory_position_qty"]).where(need, 0)
    moq = df["min_order_qty"].clip(lower=1)
    df["scenario_order_qty"] = (np.ceil(raw_qty.clip(lower=0) / moq) * moq).astype(int)
    df["scenario_order_value_gbp"] = df["scenario_order_qty"] * df["unit_cost_gbp"]
    df["scenario_safety_stock_value_gbp"] = df["scenario_safety_stock"] * df["unit_cost_gbp"]
    df["scenario_priority"] = [
        priority(s, v, q) for s, v, q in zip(df["stock_status"], df["velocity_class"], df["scenario_order_qty"])
    ]
    return df


def status_summary(position: pd.DataFrame) -> pd.DataFrame:
    """SKU-location count and stock value by status, in display order."""
    out = (
        position.groupby("stock_status", as_index=False)
        .agg(sku_locations=("sku", "count"), stock_value_gbp=("stock_value_gbp", "sum"))
    )
    out["stock_status"] = pd.Categorical(out["stock_status"], STOCK_STATUS_ORDER, ordered=True)
    return out.sort_values("stock_status").reset_index(drop=True)
