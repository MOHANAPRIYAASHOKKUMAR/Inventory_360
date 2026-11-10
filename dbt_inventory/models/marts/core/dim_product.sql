select
    p.sku,
    p.product_name,
    p.category,
    p.subcategory,
    p.brand,
    p.supplier_id,
    s.supplier_name,
    s.sourcing_region,
    s.lead_time_days                       as supplier_lead_time_days,
    p.unit_cost_gbp,
    p.unit_price_gbp,
    p.gross_margin_pct,
    p.units_per_pallet,
    p.min_order_qty,
    p.shelf_life_days,
    p.velocity_class,
    p.lifecycle_status,
    p.launch_date
from {{ ref('stg_products') }} p
left join {{ ref('stg_suppliers') }} s on s.supplier_id = p.supplier_id
