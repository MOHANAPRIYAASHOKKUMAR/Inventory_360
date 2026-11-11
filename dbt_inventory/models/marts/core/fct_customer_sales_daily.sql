{{ config(cluster_by=['sales_date']) }}

-- Grain: one row per day x site x SKU x customer.
-- POS sales are recorded at the fulfilling site; this model allocates each site's
-- daily SKU sales across the customers that site serves, using a channel x category
-- mix weight with a stable per-customer adjustment. Shares are normalised within
-- site x category, so customer totals reconcile exactly to stg_sales.
with weights as (
    select
        c.customer_id,
        c.warehouse_code,
        p.category,
        (case c.channel
             when 'Own stores' then 0.55
             when 'Franchise'  then 0.20
             when 'Wholesale'  then 0.15
             else 0.10 end)
        * (case
             when c.channel = 'Online'    and p.category in ('Electricals', 'Toys & Seasonal', 'Health & Beauty') then 1.8
             when c.channel = 'Wholesale' and p.category in ('Garden & DIY', 'Household', 'Grocery & Ambient')     then 1.6
             when c.channel = 'Franchise' and p.category in ('Clothing & Footwear', 'Baby & Toddler')             then 1.4
             else 1.0 end)
        * (0.85 + mod(abs(hash(c.customer_id, p.category)), 31) / 100.0)   as raw_weight
    from {{ ref('dim_customer') }} c
    cross join (select distinct category from {{ ref('dim_product') }}) p
    where c.is_active
),
shares as (
    select
        customer_id,
        warehouse_code,
        category,
        raw_weight / sum(raw_weight) over (partition by warehouse_code, category) as share
    from weights
)
select
    s.sales_date,
    sh.customer_id,
    s.warehouse_code,
    s.sku,
    p.category,
    p.supplier_id,
    s.units_demanded * sh.share                               as units_demanded,
    s.units_sold * sh.share                                   as units_sold,
    s.units_lost * sh.share                                   as units_lost,
    s.net_sales_gbp * sh.share                                as net_sales_gbp,
    s.units_sold * sh.share * p.unit_cost_gbp                 as cogs_gbp,
    (s.net_sales_gbp - s.units_sold * p.unit_cost_gbp) * sh.share as gross_profit_gbp,
    s.units_lost * sh.share * p.unit_price_gbp                as lost_sales_gbp
from {{ ref('stg_sales') }} s
join {{ ref('dim_product') }} p on p.sku = s.sku
join shares sh on sh.warehouse_code = s.warehouse_code and sh.category = p.category
