# User guide

Inventory 360 is Sample Retail Group's single view of stock, customers, suppliers, warehouses, logistics and
budget.
All values are in GBP (£). Data is refreshed daily; the latest snapshot date is shown on each page.

## Getting around

- **Sidebar navigation** groups pages by area: Overview, Inventory, Supply chain, Finance and, for the
  Developer tier only, Platform.
- **Global filters** in the sidebar apply to every page: period presets (4W, 13W, 26W, 52W, YTD from
  1 April; default 13W), date range, region, warehouse, product category, supplier, product and
  customer. Lists cascade (warehouse by region, product by category / supplier, customer by
  warehouse); a selection that no longer fits is removed with a notice. **Reset filters** restores
  the defaults.
- Active filters appear as chips under each page header; click a chip to remove it. Each page notes
  any filter that does not apply to its data.
- **KPI cards** show the value, the change against the previous period of equal length and a RAG
  status spelled out in words (On target / Watch / Off target / No data).
- Charts have tooltips. Detail tables show a row count, a **Download CSV** button, and many allow
  selecting a row to open a drill-down.

## Pages

### Executive overview
Headline KPIs against the comparison period — stock value, net sales, on-shelf availability, fill rate,
stock turns, lost sales — plus budget variance and the top exceptions needing attention. Drill-down
buttons break net sales, gross margin, availability and more down by region, warehouse, category, SKU or
customer; insights with **Explore** open the matching drill-down.

### Customers & sales
Net sales, gross profit, gross margin, customer fill rate and active customers, with a sales trend by
channel, channel mix, top customers and category mix by channel. Filter by channel (Own stores,
Franchise, Wholesale, Online), choose daily / weekly / monthly granularity, and select a customer in the
scorecard to drill into weekly sales and category mix.

### Inventory health
Stock status mix (out of stock → excess), days-of-cover distribution, excess by lifecycle stage and a
SKU-location drill-down. Use it to find shortage risk and cash tied up in slow stock.

### Replenishment planner (submitting requires Planner tier)
1. Review recommended orders, sorted by priority (P1 Urgent first).
2. Optionally adjust scenario levers (service level, demand uplift, lead-time buffer) to see the effect on
   safety stock and order value.
3. Edit approved quantities and add a note where needed.
4. Submit — orders are saved to the replenishment outbox for the ERP interface and logged in the audit
   trail.

> The app runs with restricted caller's rights: every query uses your own default role, so Snowflake
> enforces what you can see and write. The *Submit approved orders* button appears only for the Planner
> tier or above; viewers can review recommendations but cannot submit.

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

### Data & governance (Developer tier only)
Object inventory per layer, data freshness, lineage overview and the application audit trail. Visible
only when your default role is `INV360_ENGINEER`, `INV360_ADMIN`, `SYSADMIN` or `ACCOUNTADMIN`.

## Definitions

See [kpi_definitions.md](kpi_definitions.md) for how every KPI is calculated.

## Access

Ask the platform team for `INV360_VIEWER` (read-only) or `INV360_PLANNER` (can submit replenishment).
The role must be set as your **default role**: the app always uses your default role, not the role
selected in Snowsight. Otherwise you see an access message instead of the dashboard.

| Tier | Default role | Adds |
| --- | --- | --- |
| Viewer | `INV360_VIEWER` | Business pages, drill-downs, CSV export (read-only) |
| Planner | `INV360_PLANNER` | Approve and submit replenishment orders |
| Developer | `INV360_ENGINEER`, `INV360_ADMIN`, `SYSADMIN`, `ACCOUNTADMIN` | Data & governance page, technical error details |

If the app cannot confirm who you are, it shows no data (it never falls back to the owner's rights);
reopen the app.
