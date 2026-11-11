# Data model

All objects live in `INVENTORY_360_DB`. Grain is stated for every mart table.

## Dimensions (`MARTS`)

| Table | Grain | Key | Notes |
| --- | --- | --- | --- |
| `DIM_DATE` | Day | `DATE_DAY` | UK fiscal year (April start, e.g. `FY26/27`), fiscal month/quarter, trading period |
| `DIM_PRODUCT` | SKU | `SKU` | 360 SKUs; category hierarchy, supplier, cost/price, margin, velocity class (A/B/C), lifecycle |
| `DIM_SUPPLIER` | Supplier | `SUPPLIER_ID` | 36 suppliers; country, contract tier, lead time, payment terms |
| `DIM_WAREHOUSE` | Site | `WAREHOUSE_CODE` | 9 UK sites; region, nation, site type, pallet capacity, coordinates |
| `DIM_CUSTOMER` | Customer | `CUSTOMER_ID` | 36 synthetic accounts (one per channel per site: Own stores, Franchise, Wholesale, Online); fulfilling site, credit terms, account manager |

## Facts (`MARTS`)

| Table | Grain | Measures |
| --- | --- | --- |
| `FCT_INVENTORY_DAILY` | Day × site × SKU | On hand, available, received, damaged, demand, sold, lost units; net sales, COGS, lost sales, stock value at cost and retail, pallets, OOS flag |
| `FCT_PURCHASE_ORDERS` | PO line | Ordered / received qty and value, expected vs received date, days late, on-time / in-full / OTIF flags, contract vs actual lead time |
| `FCT_SHIPMENTS` | Shipment | Carrier, mode, pallets, freight, duty, landed cost, CO₂, transit and delay days, on-time arrival |
| `FCT_CUSTOMER_SALES_DAILY` | Day × site × SKU × customer | POS sales allocated to the customers each site serves (channel × category mix weights, normalised per site and category); demand, sold, lost units, net sales, COGS, gross profit, lost sales. Reconciles exactly to `STG_SALES` (test `assert_customer_sales_reconcile`) |

## Reporting tables (`MARTS`)

| Table | Grain | Used by |
| --- | --- | --- |
| `RPT_INVENTORY_POSITION` | Site × SKU at latest snapshot | Inventory health, Replenishment planner |
| `RPT_INVENTORY_KPIS_MONTHLY` | Month × site × category | Executive overview, Inventory health |
| `RPT_SUPPLIER_SCORECARD` | Supplier (rolling 12 months) | Supplier performance |
| `RPT_LOGISTICS_MONTHLY` | Month × mode × carrier × site × sourcing region | Logistics & freight |
| `RPT_WAREHOUSE_UTILISATION` | Month × site | Warehouse network |
| `RPT_BUDGET_VS_ACTUAL` | Month × budget area × dimension key × version | Budget & costs |

## Application tables (`APP`)

| Object | Purpose |
| --- | --- |
| `REPLENISHMENT_REQUESTS` | Planner-submitted orders. `STATUS`: `SUBMITTED` → `APPROVED` → `SENT_TO_ERP` / `REJECTED` |
| `APP_AUDIT_LOG` | Event trail (`EVENT_TYPE`, `EVENT_DETAIL` variant, user, timestamp) |
| `V_REPLENISHMENT_OUTBOX` | Open requests enriched with product and supplier names, for the ERP interface |

## Lineage

```
ERP_PRODUCTS ─▶ stg_products ─▶ dim_product ─┐
ERP_SUPPLIERS ─▶ stg_suppliers ─▶ dim_supplier ├─▶ fct_purchase_orders ─▶ rpt_supplier_scorecard
ERP_PURCHASE_ORDER_LINES ─▶ stg_purchase_order_lines ┘          └──────▶ rpt_inventory_position
WMS_STOCK_SNAPSHOT_DAILY ─▶ stg_stock_snapshots ─┐
POS_SALES_DAILY ─▶ stg_sales ────────────────────┴─▶ fct_inventory_daily ─▶ rpt_inventory_kpis_monthly
                                                                        ─▶ rpt_inventory_position
                                                                        ─▶ rpt_warehouse_utilisation
WMS_WAREHOUSES ─▶ stg_warehouses ─▶ dim_warehouse
ERP_CUSTOMERS ─▶ stg_customers ─▶ dim_customer ─┐
POS_SALES_DAILY ─▶ stg_sales ───────────────────┴─▶ fct_customer_sales_daily
TMS_SHIPMENTS ─▶ stg_shipments ─▶ fct_shipments ─▶ rpt_logistics_monthly
FIN_WAREHOUSE_COSTS_MONTHLY ─▶ stg_warehouse_costs ─▶ rpt_warehouse_utilisation, rpt_budget_vs_actual
FIN_BUDGETS_MONTHLY ─▶ stg_budgets ─▶ rpt_budget_vs_actual (also reads fct_purchase_orders, fct_shipments)
```

## Data quality

dbt tests in `dbt_inventory/models/**/_*.yml` (unique, not_null, relationships, accepted_values) plus
singular tests:

- `assert_sold_not_above_demand` — units sold never exceed units demanded.
- `assert_orders_respect_moq` — recommended order quantities are multiples of the supplier MOQ.
- `assert_customer_sales_reconcile` — customer-allocated sales equal site-level POS sales for every day × site × SKU.
