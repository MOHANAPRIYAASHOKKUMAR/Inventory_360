# Architecture

## Context

Sample Retail Group runs nine UK distribution sites supplying stores across England, Scotland, Wales and
Northern Ireland. Inventory, purchasing, transport and finance data live in separate operational systems.
Inventory 360 brings them together in Snowflake and serves one governed view to management and planners.

## Layers

| Layer | Schema | Objects | Built by | Materialisation |
| --- | --- | --- | --- | --- |
| Landing | `RAW` | 9 source extracts (ERP, WMS, POS, TMS, FIN) | `sql/load/` | Tables |
| Conformed | `STAGING` | `stg_*` — typed, cleansed, derived fields | dbt `models/staging` | Views |
| Dimensional | `MARTS` | `dim_*`, `fct_*` | dbt `models/marts/core` | Tables |
| Reporting | `MARTS` | `rpt_*` — business-ready KPI tables | dbt `models/marts/reporting` | Tables |
| Application | `APP` | Streamlit app, write-back tables, outbox view | `sql/deployment/`, `snowflake.yml` | Tables / view / Streamlit |

`fct_inventory_daily` (~1.2M rows) is clustered on `snapshot_date`.

## Source systems

| Code | System | RAW tables |
| --- | --- | --- |
| ERP | Enterprise resource planning | `ERP_PRODUCTS`, `ERP_SUPPLIERS`, `ERP_PURCHASE_ORDER_LINES` |
| WMS | Warehouse management | `WMS_WAREHOUSES`, `WMS_STOCK_SNAPSHOT_DAILY` |
| POS | Point of sale (aggregated to site/day) | `POS_SALES_DAILY` |
| TMS | Transport management | `TMS_SHIPMENTS` |
| FIN | Finance | `FIN_BUDGETS_MONTHLY`, `FIN_WAREHOUSE_COSTS_MONTHLY` |

In this environment the RAW layer is populated by the deterministic generator
`sql/load/02_generate_synthetic_data.sql` (FY25/26 start → yesterday).

## Application

```
streamlit_app/streamlit_app.py      navigation, global filters, branding
  ├── pages/                         one module per business area (9 pages)
  ├── components/                    layout (header, KPI cards, filters) and Altair chart builders
  └── src/inventory360/
        ├── data_access/             Snowflake connection + parameterised, cached queries
        ├── business_logic/          replenishment scenarios, supplier risk, budget RAG / outturn
        ├── analytics/               KPI windows, ABC classification, Holt-Winters forecast
        └── utils/                   configuration constants, GBP / % formatting
```

- Pages only call `data_access` and pure functions in `business_logic` / `analytics`, so the logic is
  unit-tested without Snowflake.
- Reads are cached (`TTL_REFERENCE` 1 h for dimensions, `TTL_OPERATIONAL` 10 min for operational data).
- Write-back (replenishment submissions) goes to `APP.REPLENISHMENT_REQUESTS` with an
  `APP.APP_AUDIT_LOG` entry; `APP.V_REPLENISHMENT_OUTBOX` is the hand-off to the ERP interface
  ([service/README.md](../service/README.md)).

## Runtime

| Item | Value |
| --- | --- |
| App object | `INVENTORY_360_DB.APP.INVENTORY_360` |
| Runtime | `SYSTEM$ST_CONTAINER_RUNTIME_PY3_11` on `SYSTEM_COMPUTE_POOL_CPU` |
| Query warehouse | `INV360_WH` (X-Small, auto-suspend 60 s) |
| Packages | Container pre-installed set (trial account: no PyPI external access) |

## Security model

```
SYSADMIN
  └── INV360_ADMIN      platform owner; owns APP objects and the Streamlit app
        └── INV360_ENGINEER   builds RAW / STAGING / MARTS
              └── INV360_PLANNER    MARTS read + APP insert/update (write-back)
                    └── INV360_VIEWER     MARTS + APP read; app usage
```

Defined in `sql/roles/01_roles_and_grants.sql`. Future grants keep new mart tables readable without
re-granting. The Streamlit app runs with its owner's rights, so in-app actions (including replenishment
submission) are available to anyone granted USAGE on the app — limit app grants accordingly. User
identity is captured with `CURRENT_USER()` defaults on write-back tables.

## CI/CD

- `.github/workflows/ci.yml` — ruff, pytest, `dbt parse`, and a check that
  `sql/deployment/02_dbt_models_rendered.sql` matches the dbt models.
- `.github/workflows/deploy.yml` — manual: `dbt build --target ci` then `snow streamlit deploy`, using
  key-pair authentication from repository secrets.
