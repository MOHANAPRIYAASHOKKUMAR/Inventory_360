select
    warehouse_code,
    warehouse_name,
    town,
    uk_region,
    nation,
    site_type,
    capacity_pallets,
    latitude,
    longitude,
    opened_date
from {{ source('raw', 'wms_warehouses') }}
