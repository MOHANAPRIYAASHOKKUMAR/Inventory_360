select
    snapshot_date,
    warehouse_code,
    sku,
    coalesce(qty_on_hand, 0)                                   as qty_on_hand,
    coalesce(qty_allocated, 0)                                 as qty_allocated,
    greatest(coalesce(qty_on_hand, 0) - coalesce(qty_allocated, 0), 0) as qty_available,
    coalesce(qty_received, 0)                                  as qty_received,
    coalesce(qty_damaged, 0)                                   as qty_damaged
from {{ source('raw', 'wms_stock_snapshot_daily') }}
