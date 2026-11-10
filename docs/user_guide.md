# User guide

Inventory 360 is Sample Retail Group's single view of stock, suppliers, warehouses, logistics and budget.
All values are in GBP (£). Data is refreshed daily; the latest snapshot date is shown on each page.

## Getting around

- **Sidebar navigation** groups pages by area: Overview, Inventory, Supply chain, Finance, Platform.
- **Global filters** in the sidebar (warehouse and category) apply to every page.
- Charts have tooltips; tables can be sorted, searched and downloaded from the table toolbar.

## Pages

### Executive overview
Headline KPIs against the comparison period — stock value, net sales, on-shelf availability, fill rate,
stock turns, lost sales — plus budget variance and the top exceptions needing attention.

### Inventory health
Stock status mix (out of stock → excess), days-of-cover distribution, excess by lifecycle stage and a
SKU-location drill-down. Use it to find shortage risk and cash tied up in slow stock.

### Replenishment planner (planners)
1. Review recommended orders, sorted by priority (P1 Urgent first).
2. Optionally adjust scenario levers (service level, demand uplift, lead-time buffer) to see the effect on
   safety stock and order value.
3. Edit approved quantities and add a note where needed.
4. Submit — orders are saved to the replenishment outbox for the ERP interface and logged in the audit
   trail.

> The app runs with its owner's rights, so the page does not itself restrict who can submit. Grant app
> access only to `INV360_PLANNER` users if submission must be limited (see Access below).

### Demand forecast
Weekly demand trend and a 13-week forecast with recent accuracy, by category or SKU.

### Supplier performance
Rolling 12-month scorecard: spend, OTIF, fill rate, lead-time variability and a 0–100 performance score
with Low / Medium / High risk rating. Spend concentration shows dependency on the largest suppliers.

### Logistics & freight
Landed cost (freight + duty), cost per pallet, on-time arrival and CO₂ by transport mode, carrier and
sourcing region.

### Warehouse network
Map of the nine UK sites with utilisation, throughput and operating cost per unit and per pallet.

### Budget & costs
Budget vs actual vs forecast by area, variance RAG (green ≤ 3%, amber ≤ 7%, red > 7%) and full-year
outturn.

### Data & governance
Object inventory per layer, data freshness, lineage overview and the application audit trail.

## Definitions

See [kpi_definitions.md](kpi_definitions.md) for how every KPI is calculated.

## Access

Ask the platform team for `INV360_VIEWER` (read-only) or `INV360_PLANNER` (can submit replenishment).
