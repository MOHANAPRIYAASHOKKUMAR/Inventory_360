# KPI definitions

All monetary values are GBP. Source model shown for each KPI.

## Inventory (`RPT_INVENTORY_KPIS_MONTHLY`)

| KPI | Definition |
| --- | --- |
| Stock value at cost | Σ on-hand units × unit cost (average across trading days for the period, or closing value) |
| Fill rate | Units sold ÷ units demanded |
| On-shelf availability | 1 − OOS rate |
| OOS rate | SKU-location-days with zero stock ÷ all SKU-location-days |
| Lost sales | max(units demanded − units sold, 0) × unit price |
| Stock turns (annualised) | (COGS × 365 ÷ trading days) ÷ average stock value |
| Days inventory outstanding (DIO) | Average stock value × trading days ÷ COGS |
| Holding cost | Average stock value × 22% ÷ 12 (dbt var `holding_cost_rate`) |
| Gross profit | Net sales − COGS |

## Inventory position and replenishment (`RPT_INVENTORY_POSITION`)

Periodic-review (R, s, S) policy, demand from the last 28 days (`demand_lookback_days`).

| Measure | Definition |
| --- | --- |
| Service policy | Velocity A: 95% (z = 1.65), review 7 days · B: 90% (z = 1.28), 14 days · C: 85% (z = 1.04), 28 days |
| Safety stock | ⌈z × σ(daily demand) × √lead time⌉ |
| Reorder point | ⌈mean daily demand × lead time + safety stock⌉ |
| Order-up-to level | ⌈mean daily demand × (lead time + review period) + safety stock⌉ |
| Inventory position | On hand − allocated + open / in-transit PO quantity |
| Days of cover | On hand ÷ mean daily demand |
| Recommended order | If inventory position < reorder point (and not discontinued): order-up-to − inventory position, rounded up to MOQ multiple |
| Excess stock value | max(on hand − 60 days' demand, 0) × unit cost |

### Stock status

| Status | Rule (first match wins) |
| --- | --- |
| Out of stock | On hand = 0 and demand > 0 |
| Excess | Demand = 0 and on hand > 0 |
| Critical | Cover < 3 days |
| Low | Cover < 7 days |
| Excess | Cover > 120 days |
| Overstock | Cover > 60 days |
| Healthy | Otherwise |

### Replenishment priority

| Priority | Rule |
| --- | --- |
| P1 – Urgent | Out of stock / Critical and velocity A |
| P2 – High | Out of stock / Critical |
| P3 – Medium | Low |
| P4 – Routine | Any other line with a recommended order |
| None | No order recommended |

The planner page can re-run the policy under scenario levers (service level, demand uplift, lead-time
buffer) using `inventory360.business_logic.replenishment.recalculate_plan`.

## Suppliers (`RPT_SUPPLIER_SCORECARD`, rolling 12 months)

| KPI | Definition |
| --- | --- |
| On time | Received lines with received date ≤ expected date ÷ received lines |
| In full | Received lines with qty received ≥ qty ordered ÷ received lines |
| OTIF | Lines both on time and in full ÷ all lines |
| Unit fill rate | Units received ÷ units ordered (received lines) |
| Lead-time variability | Standard deviation of actual lead time (days) |
| Landed cost uplift | (Freight + duty) ÷ spend |
| Performance score (0–100) | 50% OTIF + 25% unit fill + 15% lead-time stability (1 − σ/15) + 10% cost (1 − uplift/30%) |
| Risk rating | Score ≥ 85 Low · ≥ 72 Medium · otherwise High |

## Logistics (`RPT_LOGISTICS_MONTHLY`)

| KPI | Definition |
| --- | --- |
| Landed cost | Freight + duty |
| Freight per pallet | Freight cost ÷ pallets |
| On-time arrival | Delivered shipments arriving on or before planned date ÷ delivered shipments |
| Transit days | Dispatch → actual (or planned) arrival |
| CO₂ | Σ shipment CO₂ kg ÷ 1,000 (tonnes) |

## Warehouses (`RPT_WAREHOUSE_UTILISATION`)

| KPI | Definition |
| --- | --- |
| Utilisation | Pallets on hand ÷ pallet capacity (monthly average and peak) |
| Cost per unit dispatched | Site opex ÷ units dispatched |
| Cost per pallet stored | Site opex ÷ average pallets used |

## Finance (`RPT_BUDGET_VS_ACTUAL`)

| KPI | Definition |
| --- | --- |
| Variance | Actual − budget (positive = overspend for cost areas) |
| Variance % | Variance ÷ budget |
| RAG | Green ≤ 3%, Amber ≤ 7%, Red > 7% absolute variance (`VARIANCE_AMBER`, `VARIANCE_RED`) |
| Outturn | Actuals for closed months + forecast for remaining months of the fiscal year |

## Customers and sales (`FCT_CUSTOMER_SALES_DAILY`)

Grain: day × site × SKU × customer. Each site's daily POS sales (`stg_sales`) are allocated across the
active customers that site serves using a channel × category mix weight; shares are normalised within
site × category so customer totals reconcile to `stg_sales`. Aggregated by customer (joined to
`DIM_CUSTOMER`) and filtered by channel on the Customers & sales page.

| KPI | Definition |
| --- | --- |
| Net sales | Σ allocated net sales |
| Gross profit | Σ (net sales − units sold × unit cost) × share |
| Gross margin | Gross profit ÷ net sales (by customer, channel or total) |
| Customer fill rate | Units sold ÷ units demanded (by customer, channel or total) |
| Lost sales | Σ allocated units lost × unit price |
| Active customers | Customers with net sales > 0 in the period |
| Top-5 share | Net sales of the five largest customers ÷ total net sales |
| Sales share | Customer net sales ÷ total net sales |
| Growth vs prior | Net sales ÷ prior-period net sales − 1 |
| SKUs bought | Distinct SKUs with allocated sales |

Margin and fill rate are rated against the `gross_margin` and `fill_rate` targets below.

## RAG policy targets (`inventory360.business_logic.exceptions.TARGETS`)

Green if the value meets the green threshold, Amber if it meets the amber threshold, otherwise Red;
missing values are `n/a`. Direction depends on `higher_is_better`.

| Key | KPI | Green | Amber | Direction |
| --- | --- | --- | --- | --- |
| `availability` | On-shelf availability | ≥ 96% | ≥ 93% | Higher is better |
| `fill_rate` | Demand fill rate | ≥ 97% | ≥ 94% | Higher is better |
| `otif` | Supplier OTIF | ≥ 90% | ≥ 80% | Higher is better |
| `on_time_arrival` | On-time arrival | ≥ 92% | ≥ 85% | Higher is better |
| `gross_margin` | Gross margin | ≥ 35% | ≥ 30% | Higher is better |
| `forecast_accuracy` | Forecast accuracy | ≥ 85% | ≥ 75% | Higher is better |
| `stock_turns` | Stock turn | ≥ 8.0 | ≥ 6.0 | Higher is better |
| `days_cover` | Days of cover | ≤ 45 days | ≤ 60 days | Lower is better |
| `utilisation_peak` | Peak utilisation | ≤ 85% | ≤ 92% | Lower is better |
| `budget_variance` | Budget variance | ≤ 3% | ≤ 7% | Lower is better |
| `lost_sales_share` | Lost sales % of sales | ≤ 2% | ≤ 4% | Lower is better |
| `freshness_hours` | Data age (hours) | ≤ 30 | ≤ 54 | Lower is better |
