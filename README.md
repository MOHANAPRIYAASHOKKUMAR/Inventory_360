# Inventory 360 — Enterprise Supply Chain Intelligence Platform

**Sample Retail Group** · UK retail & distribution · Reporting currency **GBP (£)** · Built on **Snowflake**

Inventory 360 gives management a single 360-degree view of inventory, suppliers, warehouses,
logistics, costs, budgets and replenishment. Source-system extracts land in Snowflake, are modelled
with dbt into a dimensional mart, and are served through a multi-page Streamlit in Snowflake app
with a planner write-back workflow.

## Architecture

```
 ERP · WMS · POS · TMS · FIN          Snowflake: INVENTORY_360_DB                         Consumers
 ─────────────────────────   ┌───────────┐   ┌───────────┐   ┌──────────────────┐   ┌─────────────────────┐
  source extracts  ────────▶ │    RAW    │──▶│  STAGING  │──▶│      MARTS       │──▶│ Streamlit in        │
                             │ 9 tables  │   │ 9 views   │   │ dims · facts ·   │   │ Snowflake app       │
                             └───────────┘   └───────────┘   │ rpt_* KPI tables │   │ (APP.INVENTORY_360) │
                                                    dbt      └──────────────────┘   └──────────┬──────────┘
                                                                                               │ write-back
                                                             ┌──────────────────┐              ▼
                                         ERP interface  ◀────│ APP.V_REPLENISH- │◀── APP.REPLENISHMENT_REQUESTS
                                         (service/)          │ MENT_OUTBOX      │    APP.APP_AUDIT_LOG
                                                             └──────────────────┘
```

Compute: `INV360_WH` (X-Small, 60 s auto-suspend). App runtime: container runtime on `SYSTEM_COMPUTE_POOL_CPU`.
See [docs/architecture.md](docs/architecture.md) for detail.

## Repository layout

| Path | Contents |
| --- | --- |
| `sql/setup/` | Database, schemas, warehouse |
| `sql/roles/` | Functional roles (`INV360_ADMIN` / `ENGINEER` / `PLANNER` / `VIEWER`) and grants |
| `sql/load/` | RAW table DDL and the deterministic synthetic data generator |
| `sql/deployment/` | APP write-back objects; dbt models rendered to plain SQL (fallback path) |
| `dbt_inventory/` | dbt project: `staging` views, `marts/core` dims & facts, `marts/reporting` KPI tables, tests |
| `src/inventory360/` | Python package: `data_access`, `business_logic`, `analytics`, `utils` |
| `streamlit_app/` | Streamlit entry point, `pages/`, `components/`, `assets/`, theme |
| `tests/` | pytest suite for business logic and analytics (no Snowflake needed) |
| `scripts/` | Deployment and utility scripts |
| `service/` | Design + spec for the ERP interface service that consumes the replenishment outbox |
| `docs/` | Architecture, data model, KPI definitions, runbook, user guide |
| `.github/workflows/` | CI (lint, tests, dbt parse) and manual deploy |
| `snowflake.yml` | Streamlit in Snowflake deployment manifest |

## App modules

Global sidebar filters (date range with 4W / 13W / 26W / 52W / YTD presets, warehouse, product category,
supplier, product, customer) apply to every page; each page states which filters it honours. Filters are
pushed down to Snowflake as parameterised SQL. Every page has KPI cards with red / amber / green status
against policy targets (`inventory360.business_logic.exceptions`), interactive Plotly charts, a detail
table with row drill-down, and CSV export.

| Page | What it answers |
| --- | --- |
| Executive overview | Sales, margin, stock value, availability, fill rate, lost sales, turns, cover; exception register; management attention |
| Customers & sales | Sales, margin and fill rate by customer and channel; top customers; category mix; customer drill-down |
| Inventory health | Stock status by warehouse, days of cover, warehouse × category heatmap, ABC analysis, SKU-location register |
| Replenishment planner | Reorder recommendations and what-if levers; planners edit and submit orders to `APP.REPLENISHMENT_REQUESTS` |
| Demand forecast | Weekly demand forecast with prediction interval, accuracy and bias; per-category forecasts |
| Supplier performance | Spend, OTIF, lead time, risk matrix, scorecard with recommended action; open order book |
| Logistics & freight | Landed cost, cost per pallet, on-time arrival, CO₂ by mode / carrier / site; shipments in flight |
| Warehouse network | Utilisation, cost per unit and pallet, opex trend, cost categories by site |
| Budget & costs | Budget vs actual for the date range, variance bridge, full-year outturn, cost-centre drill-down |
| Data & governance | Freshness RAG, catalogue with column drill-down, lineage, KPI dictionary, access model, audit log |

## Getting started

Prerequisites: Python 3.11, Git, a Snowflake connection in `~/.snowflake/connections.toml`.

```powershell
python -m venv .venv
.venv\Scripts\pip install "streamlit[snowflake]==1.67.0" snowflake-snowpark-python pandas numpy altair pytest ruff pyyaml jinja2 snowflake-cli
```

### 1. Build the platform (first time only)

Run in order as `SYSADMIN`/`ACCOUNTADMIN`:

```powershell
.venv\Scripts\snow sql -c <connection> -f sql/setup/01_database_and_warehouse.sql
.venv\Scripts\snow sql -c <connection> -f sql/roles/01_roles_and_grants.sql
.venv\Scripts\snow sql -c <connection> -f sql/load/01_create_raw_tables.sql
.venv\Scripts\snow sql -c <connection> -f sql/load/02_generate_synthetic_data.sql
```

Then build the models — either with dbt:

```powershell
cd dbt_inventory; dbt build --profiles-dir .   # after copying profiles.example.yml to profiles.yml
```

or, where dbt cannot authenticate (SSO-only accounts), from the rendered SQL:

```powershell
.venv\Scripts\python scripts/render_dbt_models.py > sql/deployment/02_dbt_models_rendered.sql
.venv\Scripts\snow sql -c <connection> -f sql/deployment/02_dbt_models_rendered.sql
.venv\Scripts\snow sql -c <connection> -f sql/deployment/01_app_objects.sql
```

### 2. Run the app locally

```powershell
$env:SNOWFLAKE_DEFAULT_CONNECTION_NAME = "<connection>"
.venv\Scripts\streamlit run streamlit_app/streamlit_app.py
```

### 3. Deploy to Streamlit in Snowflake

```powershell
.\scripts\deploy_streamlit.ps1 -Connection <connection>
```

The script checks every manifest artifact exists, runs `snow streamlit deploy --replace`, grants app
access to `INV360_PLANNER` / `INV360_VIEWER`, and verifies the object with `SHOW STREAMLITS`.

### 3b. Container deployment (Docker / Snowpark Container Services)

The app also ships as a Docker image (`Dockerfile`, `requirements.txt`) that runs locally and on
Snowpark Container Services. See [docs/container_deployment.md](docs/container_deployment.md) for build,
local test, registry push, compute pool, service, endpoint and teardown commands, and the trial-account
eligibility findings.

### 4. Test

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check src streamlit_app tests
```

## Security

- Never commit `secrets.toml`, `profiles.yml`, `.env`, or key files — all are in `.gitignore`.
- Virtual environments (`.venv/`, `.venv-dbt/`) are ignored; GitHub rejects their >100 MB binaries.
- App queries are qmark-parameterised; write-back runs with the app owner's rights and is audited in `APP.APP_AUDIT_LOG`.
