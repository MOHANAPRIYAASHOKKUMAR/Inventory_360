select
    sku,
    product_name,
    category,
    subcategory,
    brand,
    supplier_id,
    unit_cost_gbp,
    unit_price_gbp,
    {{ safe_divide('unit_price_gbp - unit_cost_gbp', 'unit_price_gbp') }} as gross_margin_pct,
    units_per_pallet,
    min_order_qty,
    shelf_life_days,
    velocity_class,
    lifecycle_status,
    launch_date
from {{ source('raw', 'erp_products') }}
