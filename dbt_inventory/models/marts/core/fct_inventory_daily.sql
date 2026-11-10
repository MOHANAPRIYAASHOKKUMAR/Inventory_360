{{ config(cluster_by=['snapshot_date']) }}

-- Grain: one row per site x SKU x day. Joins the WMS stock position with
-- demand / sales so that availability and cover can be computed consistently.
select
    k.snapshot_date,
    k.warehouse_code,
    k.sku,
    p.category,
    p.velocity_class,
    k.qty_on_hand,
    k.qty_available,
    k.qty_received,
    k.qty_damaged,
    coalesce(s.units_demanded, 0)                      as units_demanded,
    coalesce(s.units_sold, 0)                          as units_sold,
    coalesce(s.units_lost, 0)                          as units_lost,
    coalesce(s.net_sales_gbp, 0)                       as net_sales_gbp,
    coalesce(s.units_sold, 0) * p.unit_cost_gbp        as cogs_gbp,
    coalesce(s.units_lost, 0) * p.unit_price_gbp       as lost_sales_gbp,
    k.qty_on_hand * p.unit_cost_gbp                    as stock_value_gbp,
    k.qty_on_hand * p.unit_price_gbp                   as stock_retail_value_gbp,
    ceil(k.qty_on_hand / nullif(p.units_per_pallet, 0)) as pallets_on_hand,
    k.qty_on_hand = 0                                  as is_out_of_stock
from {{ ref('stg_stock_snapshots') }} k
join {{ ref('dim_product') }} p on p.sku = k.sku
left join {{ ref('stg_sales') }} s
    on s.sales_date = k.snapshot_date
   and s.warehouse_code = k.warehouse_code
   and s.sku = k.sku
