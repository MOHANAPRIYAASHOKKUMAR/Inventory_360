-- Grain: one row per supplier. Rolling 12-month performance scorecard.
with po as (
    select *
    from {{ ref('fct_purchase_orders') }}
    where order_date >= dateadd(month, -12, current_date())
),
perf as (
    select
        supplier_id,
        count(distinct po_number)                                       as po_count,
        count(*)                                                        as po_lines,
        sum(order_value_gbp)                                            as spend_gbp,
        sum(iff(po_status = 'RECEIVED', 1, 0))                          as lines_received,
        avg(iff(po_status = 'RECEIVED', iff(is_on_time, 1, 0), null))   as on_time_rate,
        avg(iff(po_status = 'RECEIVED', iff(is_in_full, 1, 0), null))   as in_full_rate,
        avg(iff(is_otif, 1, 0))                                         as otif_rate,
        {{ safe_divide("sum(iff(po_status = 'RECEIVED', qty_received, 0))", "sum(iff(po_status = 'RECEIVED', qty_ordered, 0))") }} as unit_fill_rate,
        avg(iff(po_status = 'RECEIVED', greatest(days_late, 0), null))  as avg_days_late,
        avg(actual_lead_time_days)                                      as avg_actual_lead_time_days,
        stddev_samp(actual_lead_time_days)                              as lead_time_variability_days,
        sum(iff(po_status in ('OPEN', 'IN_TRANSIT'), order_value_gbp, 0)) as open_order_value_gbp
    from po
    group by 1
),
freight as (
    select supplier_id,
           sum(freight_cost_gbp)  as freight_cost_gbp,
           sum(duty_cost_gbp)     as duty_cost_gbp,
           sum(co2_kg) / 1000     as co2_tonnes
    from {{ ref('fct_shipments') }}
    where dispatch_date >= dateadd(month, -12, current_date())
    group by 1
),
scored as (
    select
        s.supplier_id,
        s.supplier_name,
        s.country_code,
        s.country_name,
        s.sourcing_region,
        s.primary_category,
        s.contract_tier,
        s.lead_time_days                                                as contract_lead_time_days,
        s.payment_terms_days,
        p.po_count,
        p.po_lines,
        p.spend_gbp,
        p.open_order_value_gbp,
        p.on_time_rate,
        p.in_full_rate,
        p.otif_rate,
        p.unit_fill_rate,
        p.avg_days_late,
        p.avg_actual_lead_time_days,
        p.lead_time_variability_days,
        f.freight_cost_gbp,
        f.duty_cost_gbp,
        f.co2_tonnes,
        {{ safe_divide('f.freight_cost_gbp + f.duty_cost_gbp', 'p.spend_gbp') }} as landed_cost_uplift_pct,
        -- Weighted composite score (0-100): OTIF 50%, fill 25%, lead-time stability 15%, cost 10%
        round(100 * (
              0.50 * coalesce(p.otif_rate, 0)
            + 0.25 * coalesce(p.unit_fill_rate, 0)
            + 0.15 * greatest(0, 1 - coalesce(p.lead_time_variability_days, 0) / 15)
            + 0.10 * greatest(0, 1 - coalesce({{ safe_divide('f.freight_cost_gbp + f.duty_cost_gbp', 'p.spend_gbp') }}, 0) / 0.30)
        ), 1)                                                           as performance_score
    from {{ ref('dim_supplier') }} s
    left join perf p    on p.supplier_id = s.supplier_id
    left join freight f on f.supplier_id = s.supplier_id
)
select
    scored.*,
    case when performance_score >= 85 then 'Low'
         when performance_score >= 72 then 'Medium'
         else 'High' end                                                as risk_rating,
    rank() over (order by spend_gbp desc)                               as spend_rank
from scored
