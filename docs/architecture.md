# Architecture

## Context

Sample Retail Group runs nine UK distribution sites supplying stores across England, Scotland, Wales and
Northern Ireland. Inventory, purchasing, transport and finance data live in separate operational systems.
Inventory 360 brings them together in Snowflake and serves one governed view to management and planners.

## Layers

| Layer | Schema | Objects | Built by | Materialisation |
| --- | --- | --- | --- | --- |
| Landing | `RAW` | 10 source extracts (ERP, WMS, POS, TMS, FIN) | `sql/load/` | Tables |
| Conformed | `STAGING` | `stg_*` — typed, cleansed, derived fields | dbt `models/staging` | Tables |
| Dimensional | `MARTS` | `dim_*`, `fct_*` | dbt `models/marts/core` | Tables |
| Reporting | `MARTS` | `rpt_*` — business-ready KPI tables | dbt `models/marts/reporting` | Tables |
| Application | `APP` | Streamlit app, write-back tables, outbox view | `sql/deployment/`, `snowflake.yml` | Tables / view / Streamlit |

`fct_inventory_daily` (~1.2M rows) is clustered on `snapshot_date`.

## Source systems

| Code | System | RAW tables |
| --- | --- | --- |
| ERP | Enterprise resource planning | `ERP_PRODUCTS`, `ERP_SUPPLIERS`, `ERP_PURCHASE_ORDER_LINES`, `ERP_CUSTOMERS` |
| WMS | Warehouse management | `WMS_WAREHOUSES`, `WMS_STOCK_SNAPSHOT_DAILY` |
| POS | Point of sale (aggregated to site/day) | `POS_SALES_DAILY` |
| TMS | Transport management | `TMS_SHIPMENTS` |
| FIN | Finance | `FIN_BUDGETS_MONTHLY`, `FIN_WAREHOUSE_COSTS_MONTHLY` |

In this environment the RAW layer is populated by the deterministic generator
`sql/load/02_generate_synthetic_data.sql` plus `sql/load/03_create_customers.sql` (FY25/26 start → yesterday).

## Application

```
streamlit_app/streamlit_app.py      navigation, global filters, branding
  ├── pages/                         one module per business area (10 pages)
  ├── components/                    layout (header, KPI cards, filters) and Plotly chart builders
  └── src/inventory360/
        ├── data_access/             Snowflake connection + parameterised, cached queries; global filters
        │                            pushed down to SQL (filters.py)
        ├── business_logic/          replenishment scenarios, supplier risk, budget RAG / outturn,
        │                            RAG policy targets (exceptions.py)
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
| Packages | `streamlit_app/requirements.txt`, installed from the shared PyPI artifact repository (`snowflake.snowpark.pypi_shared_repository`) |

## Security model

```
SYSADMIN
  └── INV360_ADMIN      platform owner; owns APP objects and the Streamlit app
        └── INV360_ENGINEER   builds RAW / STAGING / MARTS
              └── INV360_PLANNER    MARTS read + APP insert only (write-back; no UPDATE)
                    └── INV360_VIEWER     MARTS read + outbox view; app and warehouse USAGE
```

Defined in `sql/roles/01_roles_and_grants.sql` and `sql/roles/03_hardening.sql`. Future grants keep new
mart tables readable without re-granting. The Streamlit app runs with **restricted caller's rights**: every
query uses the viewer's own default role, and only where the app owner `INV360_ADMIN` holds a matching
caller grant (`sql/roles/02_callers_rights.sql`). If the viewer's identity is unavailable the app fails
closed rather than using the owner's rights. Order status changes and the audit trail can't be edited by
planners; user identity is captured with `CURRENT_USER()` defaults on write-back tables.

### Account security

`sql/roles/04_account_security.sql` is an optional, step-by-step checklist (not part of the build order):
MFA for the administrator user, a break-glass `ACCOUNTADMIN` user `INV360_BREAKGLASS`, and a password
policy and MFA authentication policy in `INVENTORY_360_DB.SECURITY`. The account-level authentication
policy assignment is commented out until MFA is enrolled. A network policy is defined only in comments and
is not applied.

## CI/CD

- `.github/workflows/ci.yml` — ruff, pytest, `dbt parse`, and a check that
  `sql/deployment/02_dbt_models_rendered.sql` matches the dbt models.
- `.github/workflows/deploy.yml` — manual: `dbt build --target ci`, then `snow streamlit deploy --replace`
  as the owner role `INV360_ADMIN`, re-grants app usage to `INV360_PLANNER` / `INV360_VIEWER`, attaches
  the shared PyPI artifact repository and verifies with `SHOW STREAMLITS`, using key-pair authentication
  from repository secrets (same steps as `scripts/deploy_streamlit.ps1`).
