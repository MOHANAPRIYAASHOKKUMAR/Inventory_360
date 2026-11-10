-- Units sold can never exceed units demanded
select *
from {{ ref('fct_inventory_daily') }}
where units_sold > units_demanded
