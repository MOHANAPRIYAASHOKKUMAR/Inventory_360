-- Grain: month x budget area x dimension (category or site).
-- Actuals are sourced from the same facts that drive operational reporting
-- so finance and operations reconcile.
with actuals as (
    select date_trunc('month', order_date) as period_month,
           'Inventory Purchases'           as budget_area,
           category                        as dimension_key,
           sum(order_value_gbp)            as actual_gbp
    from {{ ref('fct_purchase_orders') }}
    group by 1, 2, 3
    union all
    select date_trunc('month', planned_arrival), 'Freight & Duty', warehouse_code, sum(landed_cost_gbp)
    from {{ ref('fct_shipments') }}
    group by 1, 2, 3
    union all
    select period_month, 'Warehousing', warehouse_code, sum(actual_cost_gbp)
    from {{ ref('stg_warehouse_costs') }}
    group by 1, 2, 3
),
closed as (
    -- Only fully closed months count as actuals
    select * from actuals where period_month < date_trunc('month', current_date())
)
select
    b.period_month,
    b.fiscal_year,
    b.budget_area,
    b.dimension_key,
    b.budget_version,
    b.budget_gbp,
    a.actual_gbp,
    b.forecast_gbp,
    coalesce(a.actual_gbp, b.forecast_gbp)                             as outturn_gbp,
    a.actual_gbp - b.budget_gbp                                        as variance_gbp,
    {{ safe_divide('a.actual_gbp - b.budget_gbp', 'b.budget_gbp') }}   as variance_pct,
    a.actual_gbp is not null                                           as is_actualised
from {{ ref('stg_budgets') }} b
left join closed a
    on a.period_month = b.period_month
   and a.budget_area = b.budget_area
   and a.dimension_key = b.dimension_key
