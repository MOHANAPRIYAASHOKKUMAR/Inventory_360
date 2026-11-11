"""Read / write access to the Inventory 360 marts.

Every read takes the global filters and pushes them down to Snowflake as
qmark parameters, so pages receive only aggregated results. Results are cached
by ``st.connection`` per (SQL, params) for the TTL. Column names are lower case.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd

from inventory360.data_access.connection import execute, run_query
from inventory360.data_access.filters import GlobalFilters, build_where, product_scope
from inventory360.utils.config import APP_SCHEMA, DATABASE, MARTS, STAGING, TTL_OPERATIONAL, TTL_REFERENCE

# Filter dimensions supported by each source (dimension -> column)
INVENTORY_COLS = {"date": "snapshot_date", "warehouse": "warehouse_code", "product": "sku", "category": "category"}
POSITION_COLS = {"warehouse": "warehouse_code", "product": "sku", "category": "category", "supplier": "supplier_id"}
PO_COLS = {"date": "order_date", "warehouse": "warehouse_code", "product": "sku", "category": "category",
           "supplier": "supplier_id"}
SHIPMENT_COLS = {"date": "dispatch_date", "warehouse": "warehouse_code", "supplier": "supplier_id"}
UTILISATION_COLS = {"date": "period_month", "warehouse": "warehouse_code"}
CUSTOMER_COLS = {"date": "f.sales_date", "warehouse": "f.warehouse_code", "product": "f.sku", "category": "f.category",
                 "supplier": "f.supplier_id", "customer": "f.customer_id"}
BUDGET_COLS = {"date": "period_month", "warehouse": "dimension_key", "category": "dimension_key"}


def _dates(df: pd.DataFrame, *cols: str) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    return df


def _scope(f: GlobalFilters):
    return product_scope(load_products(), f)


def _month_window(f: GlobalFilters) -> GlobalFilters:
    """Monthly tables: widen the start to the first of its month."""
    return replace(f, start=f.start.replace(day=1))


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #
def load_warehouses() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.DIM_WAREHOUSE order by warehouse_code", ttl=TTL_REFERENCE)


def load_suppliers() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.DIM_SUPPLIER order by supplier_name", ttl=TTL_REFERENCE)


def load_products() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.DIM_PRODUCT order by sku", ttl=TTL_REFERENCE)


def load_customers() -> pd.DataFrame:
    return run_query(f"select * from {MARTS}.DIM_CUSTOMER order by customer_name", ttl=TTL_REFERENCE)


def load_date_bounds() -> tuple[pd.Timestamp, pd.Timestamp]:
    df = run_query(f"select min(snapshot_date) as lo, max(snapshot_date) as hi from {MARTS}.FCT_INVENTORY_DAILY",
                   ttl=TTL_OPERATIONAL)
    return pd.Timestamp(df["lo"].iloc[0]), pd.Timestamp(df["hi"].iloc[0])


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
def inventory_daily(f: GlobalFilters, *, with_prior: bool = True) -> pd.DataFrame:
    """Network daily totals for the window (and the prior window for comparisons)."""
    window = replace(f, start=f.prior().start) if with_prior else f
    where, params = build_where(window, INVENTORY_COLS, _scope(f))
    df = run_query(
        f"""
        select snapshot_date,
               sum(stock_value_gbp)            as stock_value_gbp,
               sum(net_sales_gbp)              as net_sales_gbp,
               sum(cogs_gbp)                   as cogs_gbp,
               sum(lost_sales_gbp)             as lost_sales_gbp,
               sum(units_demanded)             as units_demanded,
               sum(units_sold)                 as units_sold,
               count(*)                        as sku_locations,
               sum(iff(is_out_of_stock, 1, 0)) as sku_locations_oos
        from {MARTS}.FCT_INVENTORY_DAILY {where}
        group by 1 order by 1
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )
    return _dates(df, "snapshot_date")


def inventory_breakdown(f: GlobalFilters, dims: tuple[str, ...] = ("category",)) -> pd.DataFrame:
    """Window KPIs grouped by category and/or warehouse_code."""
    allowed = {"category", "warehouse_code"}
    if not set(dims) <= allowed:
        raise ValueError(f"dims must be within {allowed}")
    where, params = build_where(f, INVENTORY_COLS, _scope(f))
    group = ", ".join(dims)
    df = run_query(
        f"""
        select {group},
               count(distinct snapshot_date)                      as days,
               sum(stock_value_gbp) / count(distinct snapshot_date) as avg_stock_value_gbp,
               sum(net_sales_gbp)                                 as net_sales_gbp,
               sum(cogs_gbp)                                      as cogs_gbp,
               sum(lost_sales_gbp)                                as lost_sales_gbp,
               sum(units_demanded)                                as units_demanded,
               sum(units_sold)                                    as units_sold,
               count(*)                                           as sku_locations,
               sum(iff(is_out_of_stock, 1, 0))                    as sku_locations_oos
        from {MARTS}.FCT_INVENTORY_DAILY {where}
        group by {group}
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )
    df["availability"] = 1 - df["sku_locations_oos"] / df["sku_locations"]
    df["fill_rate"] = df["units_sold"] / df["units_demanded"].where(df["units_demanded"] > 0)
    df["gross_margin"] = (df["net_sales_gbp"] - df["cogs_gbp"]) / df["net_sales_gbp"].where(df["net_sales_gbp"] > 0)
    df["stock_turns"] = (df["cogs_gbp"] / df["days"] * 365) / df["avg_stock_value_gbp"].where(df["avg_stock_value_gbp"] > 0)
    return df


def sku_history(f: GlobalFilters, sku: str, warehouse_code: str | None = None) -> pd.DataFrame:
    sql = f"""
        select snapshot_date,
               sum(qty_on_hand)     as qty_on_hand,
               sum(units_demanded)  as units_demanded,
               sum(units_sold)      as units_sold,
               sum(stock_value_gbp) as stock_value_gbp
        from {MARTS}.FCT_INVENTORY_DAILY
        where sku = ? and snapshot_date between ? and ?
    """
    params: list = [sku, f.start.isoformat(), f.end.isoformat()]
    if warehouse_code:
        sql += " and warehouse_code = ?"
        params.append(warehouse_code)
    return _dates(run_query(sql + " group by 1 order by 1", params=params, ttl=TTL_OPERATIONAL), "snapshot_date")


def inventory_position(f: GlobalFilters) -> pd.DataFrame:
    """Latest snapshot by site x SKU (date range does not apply)."""
    where, params = build_where(f, POSITION_COLS, _scope(f), use_date=False)
    return _dates(run_query(f"select * from {MARTS}.RPT_INVENTORY_POSITION {where}", params=params, ttl=TTL_OPERATIONAL),
                  "as_of_date", "next_delivery_date", "earliest_arrival_if_ordered")


def demand_daily(f: GlobalFilters, *, by_category: bool = False) -> pd.DataFrame:
    """Full demand history up to the end date (forecasting needs history beyond the window)."""
    where, params = build_where(f, INVENTORY_COLS, _scope(f), use_date=False)
    where = f"{where} and snapshot_date <= ?" if where else "where snapshot_date <= ?"
    params = [*params, f.end.isoformat()]
    group = "snapshot_date, category" if by_category else "snapshot_date"
    df = run_query(
        f"select {group}, sum(units_demanded) as units_demanded, sum(units_sold) as units_sold "
        f"from {MARTS}.FCT_INVENTORY_DAILY {where} group by {group} order by 1",
        params=params, ttl=TTL_OPERATIONAL,
    )
    return _dates(df, "snapshot_date")


# --------------------------------------------------------------------------- #
# Suppliers and purchasing
# --------------------------------------------------------------------------- #
def load_supplier_scorecard() -> pd.DataFrame:
    """Rolling 12-month scorecard with composite score and risk rating (not date-filtered)."""
    return run_query(f"select * from {MARTS}.RPT_SUPPLIER_SCORECARD order by spend_gbp desc", ttl=TTL_OPERATIONAL)


def supplier_performance(f: GlobalFilters) -> pd.DataFrame:
    """Per-supplier purchasing KPIs for PO lines ordered in the window."""
    where, params = build_where(f, PO_COLS, _scope(f))
    return run_query(
        f"""
        select supplier_id,
               any_value(supplier_name)                                        as supplier_name,
               any_value(sourcing_region)                                      as sourcing_region,
               count(distinct po_number)                                       as po_count,
               count(*)                                                        as po_lines,
               sum(order_value_gbp)                                            as spend_gbp,
               sum(iff(po_status in ('OPEN', 'IN_TRANSIT'), order_value_gbp, 0)) as open_value_gbp,
               sum(iff(po_status = 'RECEIVED', 1, 0))                          as lines_received,
               avg(iff(po_status = 'RECEIVED', iff(is_otif, 1, 0), null))      as otif_rate,
               avg(iff(po_status = 'RECEIVED', iff(is_on_time, 1, 0), null))   as on_time_rate,
               avg(iff(po_status = 'RECEIVED', iff(is_in_full, 1, 0), null))   as in_full_rate,
               avg(iff(po_status = 'RECEIVED', greatest(days_late, 0), null))  as avg_days_late,
               avg(actual_lead_time_days)                                      as avg_lead_time_days,
               stddev_samp(actual_lead_time_days)                              as lead_time_std_days,
               avg(contract_lead_time_days)                                    as contract_lead_time_days
        from {MARTS}.FCT_PURCHASE_ORDERS {where}
        group by supplier_id
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )


def supplier_monthly(f: GlobalFilters) -> pd.DataFrame:
    where, params = build_where(f, PO_COLS, _scope(f))
    df = run_query(
        f"""
        select date_trunc('month', order_date)                                 as period_month,
               supplier_id,
               any_value(supplier_name)                                        as supplier_name,
               any_value(sourcing_region)                                      as sourcing_region,
               sum(order_value_gbp)                                            as spend_gbp,
               sum(iff(po_status = 'RECEIVED', 1, 0))                          as lines_received,
               sum(iff(po_status = 'RECEIVED' and is_otif, 1, 0))              as lines_otif,
               avg(iff(po_status = 'RECEIVED', greatest(days_late, 0), null))  as avg_days_late
        from {MARTS}.FCT_PURCHASE_ORDERS {where}
        group by 1, 2 order by 1
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )
    df["otif_rate"] = df["lines_otif"] / df["lines_received"].where(df["lines_received"] > 0)
    return _dates(df, "period_month")


def open_purchase_orders(f: GlobalFilters) -> pd.DataFrame:
    """Open / in-transit PO lines (date range does not apply: the order book is current)."""
    where, params = build_where(f, PO_COLS, _scope(f), use_date=False)
    status = "po_status in ('OPEN', 'IN_TRANSIT')"
    where = f"{where} and {status}" if where else f"where {status}"
    df = run_query(
        f"""
        select po_number, supplier_id, supplier_name, warehouse_code, sku, product_name, category,
               order_date, expected_date, po_status, qty_ordered, order_value_gbp
        from {MARTS}.FCT_PURCHASE_ORDERS {where}
        order by expected_date
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )
    return _dates(df, "order_date", "expected_date")


# --------------------------------------------------------------------------- #
# Logistics
# --------------------------------------------------------------------------- #
def shipments_monthly(f: GlobalFilters) -> pd.DataFrame:
    where, params = build_where(f, SHIPMENT_COLS)
    df = run_query(
        f"""
        select date_trunc('month', dispatch_date)                         as period_month,
               transport_mode, carrier, warehouse_code, sourcing_region,
               count(*)                                                   as shipments,
               sum(iff(shipment_status = 'DELIVERED', 1, 0))              as delivered,
               sum(iff(shipment_status = 'DELIVERED' and is_on_time_arrival, 1, 0)) as on_time,
               sum(pallets)                                               as pallets,
               sum(freight_cost_gbp)                                      as freight_cost_gbp,
               sum(duty_cost_gbp)                                         as duty_cost_gbp,
               sum(landed_cost_gbp)                                       as landed_cost_gbp,
               sum(co2_kg) / 1000                                         as co2_tonnes,
               sum(iff(shipment_status = 'DELIVERED', transit_days, 0))   as transit_days_sum,
               sum(iff(shipment_status = 'DELIVERED', greatest(arrival_delay_days, 0), 0)) as delay_days_sum
        from {MARTS}.FCT_SHIPMENTS {where}
        group by 1, 2, 3, 4, 5 order by 1
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )
    return _dates(df, "period_month")


def shipments_open(f: GlobalFilters) -> pd.DataFrame:
    """Booked / in-transit shipments (date range does not apply)."""
    where, params = build_where(f, SHIPMENT_COLS, use_date=False)
    status = "shipment_status in ('IN_TRANSIT', 'BOOKED')"
    where = f"{where} and {status}" if where else f"where {status}"
    df = run_query(
        f"""
        select shipment_id, po_number, supplier_name, carrier, transport_mode, origin_country, warehouse_code,
               dispatch_date, planned_arrival, pallets, freight_cost_gbp, duty_cost_gbp, co2_kg, shipment_status
        from {MARTS}.FCT_SHIPMENTS {where}
        order by planned_arrival
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )
    return _dates(df, "dispatch_date", "planned_arrival")


# --------------------------------------------------------------------------- #
# Warehouses, costs and budgets
# --------------------------------------------------------------------------- #
def warehouse_utilisation(f: GlobalFilters) -> pd.DataFrame:
    where, params = build_where(_month_window(f), UTILISATION_COLS)
    return _dates(run_query(f"select * from {MARTS}.RPT_WAREHOUSE_UTILISATION {where} order by period_month",
                            params=params, ttl=TTL_OPERATIONAL), "period_month")


def warehouse_costs(f: GlobalFilters) -> pd.DataFrame:
    where, params = build_where(_month_window(f), UTILISATION_COLS)
    return _dates(run_query(f"select * from {STAGING}.STG_WAREHOUSE_COSTS {where}", params=params, ttl=TTL_OPERATIONAL),
                  "period_month")


def load_budget_vs_actual() -> pd.DataFrame:
    """All budget lines; pages filter by fiscal year / dimension in memory (small table)."""
    return _dates(run_query(f"select * from {MARTS}.RPT_BUDGET_VS_ACTUAL", ttl=TTL_OPERATIONAL), "period_month")


# --------------------------------------------------------------------------- #
# Customers and sales
# --------------------------------------------------------------------------- #
def customer_sales_daily(f: GlobalFilters, *, with_prior: bool = True) -> pd.DataFrame:
    window = replace(f, start=f.prior().start) if with_prior else f
    where, params = build_where(window, CUSTOMER_COLS, _scope(f))
    df = run_query(
        f"""
        select f.sales_date, c.channel,
               sum(f.net_sales_gbp)    as net_sales_gbp,
               sum(f.gross_profit_gbp) as gross_profit_gbp,
               sum(f.lost_sales_gbp)   as lost_sales_gbp,
               sum(f.units_demanded)   as units_demanded,
               sum(f.units_sold)       as units_sold
        from {MARTS}.FCT_CUSTOMER_SALES_DAILY f
        join {MARTS}.DIM_CUSTOMER c on c.customer_id = f.customer_id
        {where}
        group by 1, 2 order by 1
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )
    return _dates(df, "sales_date")


def customer_summary(f: GlobalFilters) -> pd.DataFrame:
    where, params = build_where(f, CUSTOMER_COLS, _scope(f))
    df = run_query(
        f"""
        select c.customer_id, c.customer_name, c.channel, c.customer_segment, c.warehouse_code, c.warehouse_name,
               c.uk_region, c.account_manager, c.credit_terms_days, c.credit_limit_gbp,
               sum(f.net_sales_gbp)    as net_sales_gbp,
               sum(f.gross_profit_gbp) as gross_profit_gbp,
               sum(f.lost_sales_gbp)   as lost_sales_gbp,
               sum(f.units_demanded)   as units_demanded,
               sum(f.units_sold)       as units_sold,
               count(distinct f.sku)   as skus_bought
        from {MARTS}.FCT_CUSTOMER_SALES_DAILY f
        join {MARTS}.DIM_CUSTOMER c on c.customer_id = f.customer_id
        {where}
        group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )
    df["gross_margin"] = df["gross_profit_gbp"] / df["net_sales_gbp"].where(df["net_sales_gbp"] > 0)
    df["fill_rate"] = df["units_sold"] / df["units_demanded"].where(df["units_demanded"] > 0)
    return df


def customer_category_mix(f: GlobalFilters) -> pd.DataFrame:
    where, params = build_where(f, CUSTOMER_COLS, _scope(f))
    return run_query(
        f"""
        select c.channel, f.category, f.customer_id,
               sum(f.net_sales_gbp) as net_sales_gbp, sum(f.gross_profit_gbp) as gross_profit_gbp
        from {MARTS}.FCT_CUSTOMER_SALES_DAILY f
        join {MARTS}.DIM_CUSTOMER c on c.customer_id = f.customer_id
        {where}
        group by 1, 2, 3
        """,
        params=params, ttl=TTL_OPERATIONAL,
    )


def customer_weekly(f: GlobalFilters, customer_id: str) -> pd.DataFrame:
    where, params = build_where(f, CUSTOMER_COLS, _scope(f))
    where = f"{where} and f.customer_id = ?" if where else "where f.customer_id = ?"
    df = run_query(
        f"""
        select date_trunc('week', f.sales_date) as week, f.category,
               sum(f.net_sales_gbp) as net_sales_gbp, sum(f.lost_sales_gbp) as lost_sales_gbp
        from {MARTS}.FCT_CUSTOMER_SALES_DAILY f {where}
        group by 1, 2 order by 1
        """,
        params=[*params, customer_id], ttl=TTL_OPERATIONAL,
    )
    return _dates(df, "week")


# --------------------------------------------------------------------------- #
# Governance
# --------------------------------------------------------------------------- #
def load_catalogue() -> pd.DataFrame:
    df = run_query(
        f"""
        select table_schema, table_name, table_type, row_count, bytes, last_altered, comment
        from {DATABASE}.information_schema.tables
        where table_schema in ('RAW', 'STAGING', 'MARTS', 'APP')
        order by decode(table_schema, 'RAW', 1, 'STAGING', 2, 'MARTS', 3, 4), table_name
        """,
        ttl=TTL_OPERATIONAL,
    )
    return _dates(df, "last_altered")


def load_columns(schema: str, table: str) -> pd.DataFrame:
    return run_query(
        f"""
        select column_name, data_type, is_nullable, comment
        from {DATABASE}.information_schema.columns
        where table_schema = ? and table_name = ?
        order by ordinal_position
        """,
        params=[schema, table], ttl=TTL_REFERENCE,
    )


def load_audit_log(limit: int = 500) -> pd.DataFrame:
    return _dates(run_query(
        f"select event_ts, user_name, event_type, event_detail from {APP_SCHEMA}.APP_AUDIT_LOG "
        f"order by event_ts desc limit {int(limit)}",
        ttl=0,
    ), "event_ts")


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
            str(pd.Timestamp(row.as_of_date).date()),
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
