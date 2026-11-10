-- Grain: month x site. Capacity utilisation and operating cost efficiency.
with occupancy as (
    select
        date_trunc('month', snapshot_date)                 as period_month,
        warehouse_code,
        snapshot_date,
        sum(pallets_on_hand)                               as pallets_used,
        sum(units_sold)                                    as units_dispatched,
        sum(qty_received)                                  as units_received,
        sum(stock_value_gbp)                               as stock_value_gbp
    from {{ ref('fct_inventory_daily') }}
    group by 1, 2, 3
),
monthly as (
    select
        period_month,
        warehouse_code,
        avg(pallets_used)                                  as avg_pallets_used,
        max(pallets_used)                                  as peak_pallets_used,
        sum(units_dispatched)                              as units_dispatched,
        sum(units_received)                                as units_received,
        avg(stock_value_gbp)                               as avg_stock_value_gbp
    from occupancy
    group by 1, 2
),
costs as (
    select period_month, warehouse_code,
           sum(actual_cost_gbp)                                         as opex_gbp,
           sum(iff(cost_category = 'Labour', actual_cost_gbp, 0))       as labour_cost_gbp
    from {{ ref('stg_warehouse_costs') }}
    group by 1, 2
)
select
    m.period_month,
    m.warehouse_code,
    w.warehouse_name,
    w.uk_region,
    w.nation,
    w.site_type,
    w.capacity_pallets,
    w.latitude,
    w.longitude,
    m.avg_pallets_used,
    m.peak_pallets_used,
    {{ safe_divide('m.avg_pallets_used', 'w.capacity_pallets') }}      as avg_utilisation_pct,
    {{ safe_divide('m.peak_pallets_used', 'w.capacity_pallets') }}     as peak_utilisation_pct,
    m.units_dispatched,
    m.units_received,
    m.avg_stock_value_gbp,
    c.opex_gbp,
    c.labour_cost_gbp,
    {{ safe_divide('c.opex_gbp', 'm.units_dispatched') }}              as cost_per_unit_dispatched_gbp,
    {{ safe_divide('c.opex_gbp', 'm.avg_pallets_used') }}              as cost_per_pallet_stored_gbp
from monthly m
join {{ ref('dim_warehouse') }} w on w.warehouse_code = m.warehouse_code
left join costs c on c.period_month = m.period_month and c.warehouse_code = m.warehouse_code
