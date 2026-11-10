with days as (
    select dateadd(day, row_number() over (order by seq4()) - 1, '2025-04-01'::date) as date_day
    from table(generator(rowcount => 730))
)
select
    date_day,
    year(date_day)                                     as calendar_year,
    month(date_day)                                    as month_number,
    to_char(date_day, 'MON')                           as month_short_name,
    date_trunc('month', date_day)                      as month_start,
    date_trunc('week', date_day)                       as week_start,
    dayofweekiso(date_day)                             as iso_day_of_week,
    dayofweekiso(date_day) in (6, 7)                   as is_weekend,
    {{ uk_fiscal_year('date_day') }}                   as fiscal_year,
    mod(month(date_day) + 8, 12) + 1                   as fiscal_month,
    'Q' || to_varchar(ceil((mod(month(date_day) + 8, 12) + 1) / 3)) as fiscal_quarter,
    -- Retail trading periods used in planning conversations
    case
        when month(date_day) = 11 and day(date_day) between 20 and 30 then 'Black Friday'
        when month(date_day) = 12 and day(date_day) <= 24 then 'Christmas Peak'
        when month(date_day) in (3, 4, 5, 6, 7) then 'Spring / Summer'
        when month(date_day) = 1 then 'January Sale'
        else 'Core Trading'
    end                                                as trading_period
from days
