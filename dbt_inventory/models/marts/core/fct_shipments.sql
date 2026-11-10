select
    sh.*,
    s.supplier_id,
    s.supplier_name,
    s.sourcing_region,
    {{ safe_divide('sh.freight_cost_gbp', 'sh.pallets') }}       as freight_cost_per_pallet_gbp,
    case when sh.actual_arrival is not null then sh.actual_arrival <= sh.planned_arrival end as is_on_time_arrival
from {{ ref('stg_shipments') }} sh
left join (
    select distinct po_number, supplier_id from {{ ref('stg_purchase_order_lines') }}
) po on po.po_number = sh.po_number
left join {{ ref('dim_supplier') }} s on s.supplier_id = po.supplier_id
