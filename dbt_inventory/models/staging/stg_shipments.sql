select
    shipment_id,
    po_number,
    carrier,
    transport_mode,
    origin_country,
    destination_code                                           as warehouse_code,
    dispatch_date,
    planned_arrival,
    actual_arrival,
    pallets,
    freight_cost_gbp,
    duty_cost_gbp,
    freight_cost_gbp + duty_cost_gbp                           as landed_cost_gbp,
    co2_kg,
    upper(shipment_status)                                     as shipment_status,
    datediff(day, planned_arrival, actual_arrival)             as arrival_delay_days,
    datediff(day, dispatch_date, coalesce(actual_arrival, planned_arrival)) as transit_days
from {{ source('raw', 'tms_shipments') }}
