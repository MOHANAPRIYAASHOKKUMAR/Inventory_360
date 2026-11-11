"""KPI specification registry and status evaluation.

One ``KpiSpec`` per business KPI: definition, unit, direction, target and amber
tolerance. ``evaluate`` turns a value (and its comparison value) into a
``KpiResult`` with change, trend, whether the trend is favourable, RAG status and
the gap to target, so every card, insight and drill-down judges a KPI the same way.

Targets mirror ``exceptions.TARGETS`` (the existing policy, unchanged) and can be
overridden per deployment with ``INV360_TARGET_<KEY>`` / ``INV360_TOLERANCE_<KEY>``.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace

from inventory360.business_logic.exceptions import AMBER, GREEN, RED, TARGETS

NO_TARGET, NO_DATA = "No target", "No data"
UP, DOWN, FLAT = "up", "down", "flat"
STATUS_ORDER = {RED: 3, AMBER: 2, GREEN: 1, NO_TARGET: 0, NO_DATA: 0}


@dataclass(frozen=True)
class KpiSpec:
    key: str
    label: str
    definition: str
    unit: str = "pct"                  # pct | gbp | num | days | ratio
    higher_is_better: bool = True
    target: float | None = None        # green threshold
    amber_tolerance: float | None = None
    tolerance_type: str = "absolute"   # absolute | relative (fraction of target)
    target_vs_previous: float | None = None  # target = previous x (1 + this), e.g. growth KPIs
    scope: str = "Global filters"
    source: str = ""
    flat_band: float = 0.005           # |relative change| below this is "flat"

    def amber_limit(self, target: float) -> float | None:
        if self.amber_tolerance is None:
            return None
        tol = self.amber_tolerance * abs(target) if self.tolerance_type == "relative" else self.amber_tolerance
        return target - tol if self.higher_is_better else target + tol


@dataclass(frozen=True)
class KpiResult:
    spec: KpiSpec
    value: float | None
    previous: float | None = None
    target: float | None = None
    abs_change: float | None = None
    pct_change: float | None = None
    trend: str | None = None
    favourable: bool | None = None
    status: str = NO_DATA
    gap: float | None = None           # value - target (signed; +ve is good when higher_is_better)

    @property
    def is_exception(self) -> bool:
        return self.status in (RED, AMBER)


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _from_targets(key: str, definition: str, source: str, unit: str | None = None, **kw) -> KpiSpec:
    t = TARGETS[key]
    unit = unit or {"pct": "pct", "days": "days", "ratio": "ratio", "gbp": "gbp"}[t.fmt]
    return KpiSpec(key, t.label, definition, unit, t.higher_is_better, t.green, abs(t.green - t.amber), "absolute",
                   source=source, **kw)


def _env_overrides(spec: KpiSpec) -> KpiSpec:
    key = spec.key.upper()
    changes = {}
    for env, field in ((f"INV360_TARGET_{key}", "target"), (f"INV360_TOLERANCE_{key}", "amber_tolerance")):
        raw = os.getenv(env)
        if raw:
            try:
                changes[field] = float(raw)
            except ValueError:
                pass
    return replace(spec, **changes) if changes else spec


_SPECS = [
    _from_targets("availability", "Share of SKU-location-days with stock on hand (not out of stock).",
                  "MARTS.FCT_INVENTORY_DAILY"),
    _from_targets("fill_rate", "Units sold / units demanded. Demand not met is lost sales.", "MARTS.FCT_INVENTORY_DAILY"),
    _from_targets("otif", "Received PO lines delivered on time and in full / received PO lines.",
                  "MARTS.FCT_PURCHASE_ORDERS"),
    _from_targets("on_time_arrival", "Delivered shipments arriving on or before the planned date / delivered shipments.",
                  "MARTS.FCT_SHIPMENTS"),
    _from_targets("gross_margin", "(Net sales - cost of goods sold) / net sales.", "MARTS.FCT_INVENTORY_DAILY"),
    _from_targets("forecast_accuracy", "1 - weighted absolute percentage error of the demand forecast.",
                  "MARTS.FCT_INVENTORY_DAILY"),
    _from_targets("stock_turns", "Annualised cost of goods sold / average stock value.", "MARTS.FCT_INVENTORY_DAILY"),
    _from_targets("days_cover", "Stock on hand / average daily demand (lower ties up less cash).",
                  "MARTS.RPT_INVENTORY_POSITION"),
    _from_targets("utilisation_peak", "Highest monthly pallet occupancy / pallet capacity.",
                  "MARTS.RPT_WAREHOUSE_UTILISATION"),
    _from_targets("budget_variance", "|Actual or outturn - budget| / budget.", "MARTS.RPT_BUDGET_VS_ACTUAL"),
    _from_targets("lost_sales_share", "Lost sales value / (net sales + lost sales).", "MARTS.FCT_INVENTORY_DAILY"),
    _from_targets("freshness_hours", "Hours since the latest business date in the marts.", "MARTS"),
    KpiSpec("net_sales", "Net sales", "Net sales value after returns and discounts, ex VAT.", "gbp",
            target_vs_previous=0.0, amber_tolerance=0.02, tolerance_type="relative",
            source="MARTS.FCT_INVENTORY_DAILY"),
    KpiSpec("lost_sales", "Lost sales", "Value of demand not met because stock was unavailable.", "gbp",
            higher_is_better=False, source="MARTS.FCT_INVENTORY_DAILY"),
    KpiSpec("stock_value", "Stock value", "Average stock on hand at cost over the period.", "gbp",
            higher_is_better=False, source="MARTS.FCT_INVENTORY_DAILY"),
    KpiSpec("excess_value", "Excess stock", "Stock value above the overstock threshold (cash at risk).", "gbp",
            higher_is_better=False, source="MARTS.RPT_INVENTORY_POSITION"),
]
KPIS: dict[str, KpiSpec] = {s.key: _env_overrides(s) for s in _SPECS}


def spec(key: str) -> KpiSpec:
    return KPIS[key]


def status_of(value: float | None, spec_: KpiSpec, target: float | None) -> str:
    if _missing(value):
        return NO_DATA
    if target is None or _missing(target):
        return NO_TARGET
    amber = spec_.amber_limit(target)
    if spec_.higher_is_better:
        if value >= target:
            return GREEN
        return AMBER if amber is not None and value >= amber else RED
    if value <= target:
        return GREEN
    return AMBER if amber is not None and value <= amber else RED


def evaluate(key_or_spec: str | KpiSpec, value: float | None, previous: float | None = None, *,
             target: float | None = None) -> KpiResult:
    """Evaluate a KPI. ``target`` overrides the spec (e.g. a budget line)."""
    s = key_or_spec if isinstance(key_or_spec, KpiSpec) else KPIS[key_or_spec]
    value = None if _missing(value) else float(value)
    previous = None if _missing(previous) else float(previous)
    if target is None:
        if s.target_vs_previous is not None:
            target = None if previous is None else previous * (1 + s.target_vs_previous)
        else:
            target = s.target

    abs_change = pct = trend = favourable = None
    if value is not None and previous is not None:
        abs_change = value - previous
        pct = abs_change / abs(previous) if previous else None
        if s.unit == "pct":
            flat = abs(abs_change) < 0.001          # 0.1 percentage point
        else:
            flat = pct is not None and abs(pct) < s.flat_band or (previous == 0 and value == 0)
        trend = FLAT if flat else UP if abs_change > 0 else DOWN
        favourable = None if trend == FLAT else (trend == UP) == s.higher_is_better

    gap = None if value is None or target is None else value - target
    return KpiResult(s, value, previous, target, abs_change, pct, trend, favourable, status_of(value, s, target), gap)


def worst_status(results) -> str:
    results = list(results)
    if not results:
        return NO_DATA
    return max((r.status for r in results), key=lambda st: STATUS_ORDER.get(st, 0))
