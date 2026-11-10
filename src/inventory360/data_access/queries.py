"""Read / write access to the Inventory 360 marts.

Every function returns a pandas DataFrame with lower-case column names.
Interactive filtering happens in pandas on these cached frames, so each
query runs at most once per TTL window.
"""
from __future__ import annotations

import json

import pandas as pd

from inventory360.data_access.connection import execute, run_query
from inventory360.utils.config import APP_SCHEMA, MARTS, STAGING, TTL_OPERATIONAL, TTL_REFERENCE


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #
def load_warehouses() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.DIM_WAREHOUSE order by warehouse_code", ttl=TTL_REFERENCE)


def load_suppliers() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.DIM_SUPPLIER order by supplier_id", ttl=TTL_REFERENCE)


def load_products() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.DIM_PRODUCT order by sku", ttl=TTL_REFERENCE)


def load_data_freshness() -> pd.DataFrame:
    return run_query(
        f"""
        select max(snapshot_date) as as_of_date,
               count(distinct snapshot_date) as days_loaded,
               count(*) as fact_rows
        from {MARTS}.FCT_INVENTORY_DAILY
        """,
        ttl=TTL_OPERATIONAL,
    )


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
def load_inventory_position() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.RPT_INVENTORY_POSITION", ttl=TTL_OPERATIONAL)


def load_inventory_kpis_monthly() -> pd.DataFrame:
    df = run_query(f"select * from {MARTS}.RPT_INVENTORY_KPIS_MONTHLY", ttl=TTL_OPERATIONAL)
    df["period_month"] = pd.to_datetime(df["period_month"])
    return df


def load_network_daily_trend() -> pd.DataFrame:
    df = run_query(
        f"""
        select snapshot_date,
               warehouse_code,
               category,
               sum(stock_value_gbp)                 as stock_value_gbp,
               sum(net_sales_gbp)                   as net_sales_gbp,
               sum(cogs_gbp)                        as cogs_gbp,
               sum(lost_sales_gbp)                  as lost_sales_gbp,
               sum(units_demanded)                  as units_demanded,
               sum(units_sold)                      as units_sold,
               count(*)                             as sku_locations,
               sum(iff(is_out_of_stock, 1, 0))      as sku_locations_oos
        from {MARTS}.FCT_INVENTORY_DAILY
        group by 1, 2, 3
        """,
        ttl=TTL_OPERATIONAL,
    )
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


def load_sku_daily_history(sku: str, warehouse_code: str | None = None) -> pd.DataFrame:
    sql = f"""
        select snapshot_date,
               sum(units_demanded)  as units_demanded,
               sum(units_sold)      as units_sold,
               sum(qty_on_hand)     as qty_on_hand
        from {MARTS}.FCT_INVENTORY_DAILY
        where sku = ?
    """
    params: list = [sku]
    if warehouse_code:
        sql += " and warehouse_code = ?"
        params.append(warehouse_code)
    sql += " group by 1 order by 1"
    df = run_query(sql, params=params, ttl=TTL_OPERATIONAL)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


# --------------------------------------------------------------------------- #
# Suppliers and purchasing
# --------------------------------------------------------------------------- #
def load_supplier_scorecard() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.RPT_SUPPLIER_SCORECARD order by spend_gbp desc", ttl=TTL_OPERATIONAL)


def load_supplier_monthly_performance() -> pd.DataFrame:
    df = run_query(
        f"""
        select date_trunc('month', expected_date)                 as period_month,
               supplier_id,
               supplier_name,
               sourcing_region,
               sum(order_value_gbp)                               as spend_gbp,
               avg(iff(is_otif, 1, 0))                            as otif_rate,
               avg(iff(po_status = 'RECEIVED', greatest(days_late, 0), null)) as avg_days_late,
               count(*)                                           as po_lines
        from {MARTS}.FCT_PURCHASE_ORDERS
        where po_status = 'RECEIVED'
        group by 1, 2, 3, 4
        """,
        ttl=TTL_OPERATIONAL,
    )
    df["period_month"] = pd.to_datetime(df["period_month"])
    return df


def load_open_purchase_orders() -> pd.DataFrame:
    df = run_query(
        f"""
        select po_number,
               supplier_id,
               supplier_name,
               warehouse_code,
               min(order_date)          as order_date,
               min(expected_date)       as expected_date,
               max(po_status)           as po_status,
               count(*)                 as lines,
               sum(qty_ordered)         as units,
               sum(order_value_gbp)     as order_value_gbp
        from {MARTS}.FCT_PURCHASE_ORDERS
        where po_status in ('OPEN', 'IN_TRANSIT')
        group by 1, 2, 3, 4
        order by expected_date
        """,
        ttl=TTL_OPERATIONAL,
    )
    for col in ("order_date", "expected_date"):
        df[col] = pd.to_datetime(df[col])
    return df


# --------------------------------------------------------------------------- #
# Logistics
# --------------------------------------------------------------------------- #
def load_logistics_monthly() -> pd.DataFrame:
    df = run_query(f"select * from {MARTS}.RPT_LOGISTICS_MONTHLY", ttl=TTL_OPERATIONAL)
    df["period_month"] = pd.to_datetime(df["period_month"])
    return df


def load_shipments_in_flight() -> pd.DataFrame:
    df = run_query(
        f"""
        select shipment_id, po_number, supplier_name, carrier, transport_mode, origin_country,
               warehouse_code, dispatch_date, planned_arrival, pallets, freight_cost_gbp,
               duty_cost_gbp, co2_kg, shipment_status
        from {MARTS}.FCT_SHIPMENTS
        where shipment_status in ('IN_TRANSIT', 'BOOKED')
        order by planned_arrival
        """,
        ttl=TTL_OPERATIONAL,
    )
    for col in ("dispatch_date", "planned_arrival"):
        df[col] = pd.to_datetime(df[col])
    return df


# --------------------------------------------------------------------------- #
# Warehouses, costs and budgets
# --------------------------------------------------------------------------- #
def load_warehouse_utilisation() -> pd.DataFrame:
    df = run_query(f"select * from {MARTS}.RPT_WAREHOUSE_UTILISATION", ttl=TTL_OPERATIONAL)
    df["period_month"] = pd.to_datetime(df["period_month"])
    return df


def load_warehouse_costs() -> pd.DataFrame:
    df = run_query(f"select * from {STAGING}.STG_WAREHOUSE_COSTS", ttl=TTL_OPERATIONAL)
    df["period_month"] = pd.to_datetime(df["period_month"])
    return df


def load_budget_vs_actual() -> pd.DataFrame:
    df = run_query(f"select * from {MARTS}.RPT_BUDGET_VS_ACTUAL", ttl=TTL_OPERATIONAL)
    df["period_month"] = pd.to_datetime(df["period_month"])
    return df


# --------------------------------------------------------------------------- #
# Replenishment write-back
# --------------------------------------------------------------------------- #
def load_replenishment_requests() -> pd.DataFrame:
    return run_query(
        f"select * from {APP_SCHEMA}.V_REPLENISHMENT_OUTBOX order by created_at desc",
        ttl=0,
    )


def submit_replenishment_requests(lines: pd.DataFrame, note: str) -> int:
    """Insert approved order lines in one batched statement; returns rows written."""
    if lines.empty:
        return 0
    placeholders = ", ".join(["(?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED', ?)"] * len(lines))
    params: list = []
    for row in lines.itertuples(index=False):
        params += [
            str(row.as_of_date),
            row.warehouse_code,
            row.sku,
            row.supplier_id,
            int(row.recommended_order_qty),
            int(row.approved_qty),
            float(row.unit_cost_gbp),
            round(float(row.approved_qty * row.unit_cost_gbp), 2),
            row.replenishment_priority,
            note[:1000],
        ]
    execute(
        f"""
        insert into {APP_SCHEMA}.REPLENISHMENT_REQUESTS
            (as_of_date, warehouse_code, sku, supplier_id, recommended_qty, approved_qty,
             unit_cost_gbp, order_value_gbp, priority, status, planner_note)
        values {placeholders}
        """,
        params=params,
    )
    log_event(
        "REPLENISHMENT_SUBMITTED",
        {"lines": len(lines), "value_gbp": float((lines.approved_qty * lines.unit_cost_gbp).sum())},
    )
    return len(lines)


def log_event(event_type: str, detail: dict) -> None:
    execute(
        f"insert into {APP_SCHEMA}.APP_AUDIT_LOG (event_type, event_detail) select ?, parse_json(?)",
        params=[event_type, json.dumps(detail)],
    )
