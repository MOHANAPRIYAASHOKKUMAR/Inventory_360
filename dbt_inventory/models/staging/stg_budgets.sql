select
    period_month,
    {{ uk_fiscal_year('period_month') }}                       as fiscal_year,
    budget_area,
    dimension_key,
    budget_gbp,
    forecast_gbp,
    budget_version
from {{ source('raw', 'fin_budgets_monthly') }}
