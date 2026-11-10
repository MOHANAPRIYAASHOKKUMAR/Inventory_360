select
    l.*,
    p.category,
    p.product_name,
    s.supplier_name,
    s.sourcing_region,
    s.lead_time_days                                    as contract_lead_time_days,
    datediff(day, l.order_date, l.received_date)        as actual_lead_time_days,
    l.qty_received * l.unit_cost_gbp                    as received_value_gbp,
    case when l.po_status = 'RECEIVED' then (l.is_on_time and l.is_in_full) end as is_otif
from {{ ref('stg_purchase_order_lines') }} l
join {{ ref('dim_product') }} p on p.sku = l.sku
join {{ ref('dim_supplier') }} s on s.supplier_id = l.supplier_id
