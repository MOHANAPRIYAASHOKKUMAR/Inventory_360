select
    po_number || '-' || lpad(to_varchar(po_line), 3, '0')      as po_line_id,
    po_number,
    po_line,
    supplier_id,
    warehouse_code,
    sku,
    order_date,
    expected_date,
    received_date,
    qty_ordered,
    qty_received,
    unit_cost_gbp,
    qty_ordered * unit_cost_gbp                                as order_value_gbp,
    upper(po_status)                                           as po_status,
    datediff(day, expected_date, received_date)                as days_late,
    received_date is not null and received_date <= expected_date as is_on_time,
    received_date is not null and qty_received >= qty_ordered  as is_in_full
from {{ source('raw', 'erp_purchase_order_lines') }}
