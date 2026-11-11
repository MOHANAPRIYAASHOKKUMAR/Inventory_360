select
    customer_id,
    trim(customer_name)                    as customer_name,
    channel,
    customer_segment,
    home_warehouse_code                    as warehouse_code,
    credit_terms_days,
    credit_limit_gbp,
    account_manager,
    onboarded_date,
    active_flag                            as is_active
from {{ source('raw', 'erp_customers') }}
