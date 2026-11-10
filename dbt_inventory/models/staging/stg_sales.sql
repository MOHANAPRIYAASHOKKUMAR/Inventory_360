select
    sales_date,
    warehouse_code,
    sku,
    coalesce(units_sold, 0)                                    as units_sold,
    coalesce(units_demanded, 0)                                as units_demanded,
    greatest(coalesce(units_demanded, 0) - coalesce(units_sold, 0), 0) as units_lost,
    coalesce(net_sales_gbp, 0)                                 as net_sales_gbp
from {{ source('raw', 'pos_sales_daily') }}
