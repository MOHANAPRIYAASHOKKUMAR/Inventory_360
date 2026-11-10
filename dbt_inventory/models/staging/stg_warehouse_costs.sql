select
    period_month,
    warehouse_code,
    cost_category,
    actual_cost_gbp
from {{ source('raw', 'fin_warehouse_costs_monthly') }}
