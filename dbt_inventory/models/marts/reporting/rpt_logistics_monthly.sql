-- Grain: month (planned arrival) x transport mode x carrier x destination site
select
    date_trunc('month', planned_arrival)                               as period_month,
    {{ uk_fiscal_year("date_trunc('month', planned_arrival)") }}       as fiscal_year,
    transport_mode,
    carrier,
    warehouse_code,
    sourcing_region,
    count(*)                                                           as shipments,
    sum(iff(shipment_status = 'DELIVERED', 1, 0))                      as shipments_delivered,
    sum(iff(shipment_status = 'IN_TRANSIT', 1, 0))                     as shipments_in_transit,
    sum(pallets)                                                       as pallets,
    sum(freight_cost_gbp)                                              as freight_cost_gbp,
    sum(duty_cost_gbp)                                                 as duty_cost_gbp,
    sum(landed_cost_gbp)                                               as landed_cost_gbp,
    {{ safe_divide('sum(freight_cost_gbp)', 'sum(pallets)') }}         as freight_cost_per_pallet_gbp,
    avg(iff(is_on_time_arrival, 1, 0))                                 as on_time_arrival_rate,
    avg(iff(shipment_status = 'DELIVERED', greatest(arrival_delay_days, 0), null)) as avg_delay_days,
    avg(transit_days)                                                  as avg_transit_days,
    sum(co2_kg) / 1000                                                 as co2_tonnes
from {{ ref('fct_shipments') }}
group by 1, 2, 3, 4, 5, 6
