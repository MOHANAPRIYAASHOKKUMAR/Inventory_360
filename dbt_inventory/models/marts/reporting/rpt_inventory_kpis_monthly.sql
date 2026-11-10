-- Grain: month x site x category. Core inventory health KPIs.
with daily as (
    select
        date_trunc('month', snapshot_date)                 as period_month,
        warehouse_code,
        category,
        snapshot_date,
        sum(stock_value_gbp)                               as stock_value_gbp,
        sum(units_demanded)                                as units_demanded,
        sum(units_sold)                                    as units_sold,
        sum(net_sales_gbp)                                 as net_sales_gbp,
        sum(cogs_gbp)                                      as cogs_gbp,
        sum(lost_sales_gbp)                                as lost_sales_gbp,
        count(*)                                           as sku_locations,
        sum(iff(is_out_of_stock, 1, 0))                    as sku_locations_oos
    from {{ ref('fct_inventory_daily') }}
    group by 1, 2, 3, 4
)
select
    period_month,
    {{ uk_fiscal_year('period_month') }}                   as fiscal_year,
    warehouse_code,
    category,
    count(distinct snapshot_date)                          as trading_days,
    avg(stock_value_gbp)                                   as avg_stock_value_gbp,
    max_by(stock_value_gbp, snapshot_date)                 as closing_stock_value_gbp,
    sum(units_demanded)                                    as units_demanded,
    sum(units_sold)                                        as units_sold,
    sum(net_sales_gbp)                                     as net_sales_gbp,
    sum(cogs_gbp)                                          as cogs_gbp,
    sum(net_sales_gbp) - sum(cogs_gbp)                     as gross_profit_gbp,
    sum(lost_sales_gbp)                                    as lost_sales_gbp,
    {{ safe_divide('sum(units_sold)', 'sum(units_demanded)') }}        as fill_rate,
    {{ safe_divide('sum(sku_locations_oos)', 'sum(sku_locations)') }} as oos_rate,
    -- Annualised stock turn and days inventory outstanding
    {{ safe_divide('sum(cogs_gbp) * 365 / count(distinct snapshot_date)', 'avg(stock_value_gbp)') }} as stock_turns_annualised,
    {{ safe_divide('avg(stock_value_gbp) * count(distinct snapshot_date)', 'sum(cogs_gbp)') }}      as days_inventory_outstanding,
    avg(stock_value_gbp) * {{ var('holding_cost_rate') }} / 12                                      as holding_cost_gbp
from daily
group by 1, 2, 3, 4
