-- Customer dimension enriched with the fulfilling site.
select
    c.customer_id,
    c.customer_name,
    c.channel,
    c.customer_segment,
    c.warehouse_code,
    w.warehouse_name,
    w.uk_region,
    w.nation,
    c.credit_terms_days,
    c.credit_limit_gbp,
    c.account_manager,
    c.onboarded_date,
    c.is_active
from {{ ref('stg_customers') }} c
left join {{ ref('dim_warehouse') }} w on w.warehouse_code = c.warehouse_code
