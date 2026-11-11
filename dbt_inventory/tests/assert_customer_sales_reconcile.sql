-- Customer allocation must reconcile to site-level POS sales (tolerance for float rounding)
with alloc as (
    select sales_date, warehouse_code, sku, sum(net_sales_gbp) as net_sales_gbp
    from {{ ref('fct_customer_sales_daily') }}
    group by 1, 2, 3
)
select s.sales_date, s.warehouse_code, s.sku, s.net_sales_gbp, a.net_sales_gbp as allocated
from {{ ref('stg_sales') }} s
join {{ ref('dim_product') }} p on p.sku = s.sku
left join alloc a
  on a.sales_date = s.sales_date and a.warehouse_code = s.warehouse_code and a.sku = s.sku
where abs(s.net_sales_gbp - coalesce(a.net_sales_gbp, 0)) > 0.01
