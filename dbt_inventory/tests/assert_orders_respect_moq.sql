-- Recommended orders must respect the supplier minimum order quantity
select *
from {{ ref('rpt_inventory_position') }}
where recommended_order_qty > 0
  and mod(recommended_order_qty, min_order_qty) <> 0
