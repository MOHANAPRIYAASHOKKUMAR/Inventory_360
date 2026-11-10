-- Grain: one row per site x SKU for the latest snapshot date.
-- Implements a periodic-review (R, s, S) replenishment policy:
--   safety stock   = z(service level) * sigma(daily demand) * sqrt(lead time)
--   reorder point  = mean daily demand * lead time + safety stock
--   order-up-to    = reorder point + mean daily demand * review period
--   inventory pos. = on hand - allocated + open / in-transit purchase orders
with latest as (
    select max(snapshot_date) as as_of_date from {{ ref('fct_inventory_daily') }}
),

demand as (
    select
        f.warehouse_code,
        f.sku,
        avg(f.units_demanded)              as avg_daily_demand,
        stddev_samp(f.units_demanded)      as stddev_daily_demand,
        sum(f.units_sold)                  as units_sold_28d,
        sum(f.net_sales_gbp)               as net_sales_28d_gbp,
        sum(f.lost_sales_gbp)              as lost_sales_28d_gbp,
        avg(iff(f.is_out_of_stock, 1, 0))  as oos_rate_28d
    from {{ ref('fct_inventory_daily') }} f, latest
    where f.snapshot_date > dateadd(day, -{{ var('demand_lookback_days') }}, latest.as_of_date)
    group by 1, 2
),

inbound as (
    select
        warehouse_code,
        sku,
        sum(qty_ordered)                   as inbound_qty,
        min(expected_date)                 as next_delivery_date,
        count(distinct po_number)          as open_po_count
    from {{ ref('fct_purchase_orders') }}
    where po_status in ('OPEN', 'IN_TRANSIT')
    group by 1, 2
),

current_stock as (
    select f.*
    from {{ ref('fct_inventory_daily') }} f
    join latest on f.snapshot_date = latest.as_of_date
),

base as (
    select
        c.snapshot_date                                         as as_of_date,
        c.warehouse_code,
        w.warehouse_name,
        w.uk_region,
        c.sku,
        p.product_name,
        p.category,
        p.subcategory,
        p.brand,
        p.supplier_id,
        p.supplier_name,
        p.sourcing_region,
        p.velocity_class,
        p.lifecycle_status,
        p.unit_cost_gbp,
        p.unit_price_gbp,
        p.min_order_qty,
        p.units_per_pallet,
        p.supplier_lead_time_days                               as lead_time_days,
        case p.velocity_class when 'A' then 7 when 'B' then 14 else 28 end as review_period_days,
        case p.velocity_class when 'A' then 1.65 when 'B' then 1.28 else 1.04 end as service_z,
        case p.velocity_class when 'A' then 0.95 when 'B' then 0.90 else 0.85 end as target_service_level,
        c.qty_on_hand,
        c.qty_available,
        c.qty_on_hand - c.qty_available                         as qty_allocated,
        c.stock_value_gbp,
        c.stock_retail_value_gbp,
        c.pallets_on_hand,
        coalesce(d.avg_daily_demand, 0)                         as avg_daily_demand,
        coalesce(d.stddev_daily_demand, 0)                      as stddev_daily_demand,
        coalesce(d.units_sold_28d, 0)                           as units_sold_28d,
        coalesce(d.net_sales_28d_gbp, 0)                        as net_sales_28d_gbp,
        coalesce(d.lost_sales_28d_gbp, 0)                       as lost_sales_28d_gbp,
        coalesce(d.oos_rate_28d, 0)                             as oos_rate_28d,
        coalesce(i.inbound_qty, 0)                              as inbound_qty,
        i.next_delivery_date,
        coalesce(i.open_po_count, 0)                            as open_po_count
    from current_stock c
    join {{ ref('dim_product') }} p   on p.sku = c.sku
    join {{ ref('dim_warehouse') }} w on w.warehouse_code = c.warehouse_code
    left join demand d  on d.warehouse_code = c.warehouse_code and d.sku = c.sku
    left join inbound i on i.warehouse_code = c.warehouse_code and i.sku = c.sku
),

policy as (
    select
        base.*,
        ceil(service_z * stddev_daily_demand * sqrt(lead_time_days))            as safety_stock_qty,
        ceil(avg_daily_demand * lead_time_days
             + service_z * stddev_daily_demand * sqrt(lead_time_days))          as reorder_point_qty,
        ceil(avg_daily_demand * (lead_time_days + review_period_days)
             + service_z * stddev_daily_demand * sqrt(lead_time_days))          as order_up_to_qty,
        qty_on_hand - qty_allocated + inbound_qty                               as inventory_position_qty,
        {{ safe_divide('qty_on_hand', 'avg_daily_demand') }}                    as days_of_cover
    from base
),

classified as (
    select
        policy.*,
        case
            when qty_on_hand = 0 and avg_daily_demand > 0                               then 'Out of stock'
            when avg_daily_demand = 0 and qty_on_hand > 0                               then 'Excess'
            when days_of_cover < {{ var('critical_cover_days') }}                       then 'Critical'
            when days_of_cover < {{ var('low_cover_days') }}                            then 'Low'
            when days_of_cover > {{ var('excess_cover_days') }}                         then 'Excess'
            when days_of_cover > {{ var('overstock_cover_days') }}                      then 'Overstock'
            else 'Healthy'
        end                                                                             as stock_status,
        iff(inventory_position_qty < reorder_point_qty and lifecycle_status <> 'Discontinued',
            ceil((order_up_to_qty - inventory_position_qty) / nullif(min_order_qty, 0)) * min_order_qty,
            0)                                                                          as recommended_order_qty,
        greatest(qty_on_hand - avg_daily_demand * {{ var('overstock_cover_days') }}, 0) * unit_cost_gbp
                                                                                        as excess_stock_value_gbp
    from policy
)

select
    classified.*,
    recommended_order_qty * unit_cost_gbp                                               as recommended_order_value_gbp,
    ceil(recommended_order_qty / nullif(units_per_pallet, 0))                           as recommended_pallets,
    case
        when recommended_order_qty = 0                                                  then 'None'
        when stock_status in ('Out of stock', 'Critical') and velocity_class = 'A'      then 'P1 - Urgent'
        when stock_status in ('Out of stock', 'Critical')                               then 'P2 - High'
        when stock_status = 'Low'                                                       then 'P3 - Medium'
        else 'P4 - Routine'
    end                                                                                 as replenishment_priority,
    dateadd(day, lead_time_days, as_of_date)                                            as earliest_arrival_if_ordered
from classified
