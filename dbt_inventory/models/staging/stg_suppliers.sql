select
    supplier_id,
    initcap(trim(supplier_name))          as supplier_name,
    upper(country_code)                    as country_code,
    country_name,
    primary_category,
    lead_time_days,
    payment_terms_days,
    contract_tier,
    reliability_factor,
    iff(country_code = 'GB', 'Domestic',
        iff(country_code in ('IE','NL','DE','FR','IT','ES','PT','PL','SE'), 'Europe', 'Far East & Asia')) as sourcing_region,
    active_flag                            as is_active
from {{ source('raw', 'erp_suppliers') }}
