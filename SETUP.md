# Inventory 360 – Setup guide

How to give someone access to the dashboard, or deploy the whole platform into a new
Snowflake account from this repository.

- **Option A – view an existing deployment.** No code or tools needed. [Jump to A](#option-a--view-an-existing-deployment)
- **Option B – deploy into your own Snowflake account.** [Jump to B](#option-b--deploy-into-your-own-snowflake-account)

---

## Option A – view an existing deployment

The account administrator of the deployment does this for each new user:

```sql
USE ROLE SECURITYADMIN;
CREATE USER IF NOT EXISTS <user_name> PASSWORD = '<temporary>' MUST_CHANGE_PASSWORD = TRUE
  EMAIL = '<email>';
GRANT ROLE INV360_VIEWER TO USER <user_name>;      -- or INV360_PLANNER to approve/submit orders
ALTER USER <user_name> SET DEFAULT_ROLE = INV360_VIEWER;
```

Then send the user the app link (Snowsight » Projects » Streamlit » **INVENTORY_360**).

> **The default role matters.** The app runs with restricted caller's rights and always uses the
> user's **default** role, not the role selected in Snowsight. A user whose default role is not an
> `INV360_*` role sees an "access" message instead of the dashboard.

| Role | What the user sees |
|---|---|
| `INV360_VIEWER` | All business pages, drill-downs, CSV export (read-only) |
| `INV360_PLANNER` | Viewer + approve and submit replenishment orders |
| `INV360_ENGINEER`, `INV360_ADMIN`, `SYSADMIN`, `ACCOUNTADMIN` | Planner + Data & governance page and technical error details |

---

## Option B – deploy into your own Snowflake account

### 1. Prerequisites

**Accounts and privileges**

- GitHub access to this repository.
- A Snowflake account (a trial account works) where you can use `ACCOUNTADMIN` for the one-time
  setup: it creates the database, warehouse and roles, and grants `MANAGE CALLER GRANTS`.
- Streamlit in Snowflake **container runtime** (`SYSTEM$ST_CONTAINER_RUNTIME_PY3_11`) and the
  default compute pool `SYSTEM_COMPUTE_POOL_CPU`. Restricted caller's rights only works on this runtime.
- Network access to Snowsight and to `*.snowflakecomputing.com`.

**Local tools**

| Tool | Version | Used for |
|---|---|---|
| Git | any | Clone the repository |
| Python | 3.11 | Matches the app runtime |
| Snowflake CLI (`snow`) | 3.x | Run SQL scripts and deploy the app |
| PowerShell | 5.1+ | `scripts/deploy_streamlit.ps1` (on macOS/Linux run the `snow` commands it contains) |
| dbt-snowflake | optional | Only to build models with dbt instead of the rendered SQL |

### 2. Clone and install

```powershell
git clone https://github.com/MOHANAPRIYAASHOKKUMAR/Inventory_360.git
cd Inventory_360
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt snowflake-cli pytest ruff pyyaml jinja2
```

### 3. Create a Snowflake connection

```powershell
.venv\Scripts\snow connection add      # name it e.g. inv360; browser SSO, password or key-pair
.venv\Scripts\snow connection test -c inv360
```

All commands below use `-c inv360`; replace it with your connection name.

### 4. Build the platform (run once, in this order)

| # | Script | Run as | Creates |
|---|---|---|---|
| 1 | `sql/setup/01_database_and_warehouse.sql` | SYSADMIN (in script) | `INVENTORY_360_DB` (RAW, STAGING, MARTS, APP) and `INV360_WH` |
| 2 | `sql/roles/01_roles_and_grants.sql` | SECURITYADMIN / SYSADMIN (in script) | `INV360_VIEWER` → `PLANNER` → `ENGINEER` → `ADMIN` and grants |
| 3 | `sql/load/01_create_raw_tables.sql` | SYSADMIN | Empty RAW source tables |
| 4 | `sql/load/02_generate_synthetic_data.sql` | SYSADMIN | Synthetic data from 1 Apr 2025 to yesterday (~2.5M rows) |
| 5 | `sql/load/03_create_customers.sql` | SYSADMIN | Customer master (36 accounts) |
| 6 | `sql/deployment/02_dbt_models_rendered.sql` | SYSADMIN | STAGING and MARTS tables (25 models) |
| 7 | `sql/deployment/01_app_objects.sql` | SYSADMIN (in script) | App audit log and replenishment outbox |
| 8 | `sql/roles/02_callers_rights.sql` | ACCOUNTADMIN (in script) | Caller grants for the app owner `INV360_ADMIN` |

```powershell
$c = "inv360"
.venv\Scripts\snow sql -c $c -f sql/setup/01_database_and_warehouse.sql
.venv\Scripts\snow sql -c $c -f sql/roles/01_roles_and_grants.sql
.venv\Scripts\snow sql -c $c --role SYSADMIN --warehouse INV360_WH -f sql/load/01_create_raw_tables.sql
.venv\Scripts\snow sql -c $c --role SYSADMIN --warehouse INV360_WH -f sql/load/02_generate_synthetic_data.sql
.venv\Scripts\snow sql -c $c --role SYSADMIN --warehouse INV360_WH -f sql/load/03_create_customers.sql
.venv\Scripts\snow sql -c $c --role SYSADMIN --warehouse INV360_WH -f sql/deployment/02_dbt_models_rendered.sql
.venv\Scripts\snow sql -c $c -f sql/deployment/01_app_objects.sql
.venv\Scripts\snow sql -c $c -f sql/roles/02_callers_rights.sql
```

**Alternative to step 6 (dbt):** copy `dbt_inventory/profiles.example.yml` to
`dbt_inventory/profiles.yml`, fill in your account, then `cd dbt_inventory; dbt build --profiles-dir .`.
dbt needs password, PAT or key-pair authentication; SSO-only accounts should use the rendered SQL.
If you change a dbt model, regenerate the rendered SQL with
`.venv\Scripts\python scripts/render_dbt_models.py` and save it **as UTF-8 without a BOM**.

### 5. Check data quality

```powershell
.venv\Scripts\snow sql -c $c --role SYSADMIN --warehouse INV360_WH -f sql/quality/01_data_quality_checks.sql
```

Expect 59 rows, all `PASS`. The checks cover row counts, freshness, missing days, unique keys,
nulls, referential integrity, business rules, staging-to-raw reconciliation and the dbt tests.

### 6. Deploy the app

```powershell
.\scripts\deploy_streamlit.ps1 -Connection $c -OwnerRole INV360_ADMIN
```

The script checks every artifact in `snowflake.yml` exists, deploys with `--replace`, grants
usage to `INV360_VIEWER` / `INV360_PLANNER`, attaches Snowflake's shared PyPI repository (so
Plotly installs; no external access integration needed) and confirms the object with `SHOW STREAMLITS`.

The user running the deploy must be able to use `INV360_ADMIN`; for example:
`GRANT ROLE INV360_ADMIN TO USER <you>;`.

### 7. Give people access

Follow [Option A](#option-a--view-an-existing-deployment) for each user, including yourself if you
want to test a lower tier (set your default role, reopen the app, then set it back).

### 8. Verify

- Open the app: the sidebar shows **Access: Developer · role … · callers connection** for admins.
- With `DEFAULT_ROLE = INV360_VIEWER`: no *Data & governance* page and no *Submit approved orders* button.
- Every page footer shows the reporting period, data date, freshness and data-quality status.

---

## Local development

```powershell
$env:SNOWFLAKE_DEFAULT_CONNECTION_NAME = "inv360"
.venv\Scripts\streamlit run streamlit_app/streamlit_app.py
```

- Caller's rights is not available locally; the app uses your own connection and role.
- Simulate a tier with `$env:INV360_TIER_OVERRIDE = "viewer"` (or `planner`, `developer`). This is
  ignored inside Snowflake.
- Tests: `.venv\Scripts\python -m pytest tests` and `.venv\Scripts\ruff check src streamlit_app tests`.
- Headless page smoke test against Snowflake: `.venv\Scripts\python scripts/smoke_pages.py`.

---

## Things to know

| Topic | Detail |
|---|---|
| Fixed object names | `INVENTORY_360_DB`, `INV360_WH`, the `INV360_*` roles and `SYSTEM_COMPUTE_POOL_CPU` are used in the SQL scripts, `snowflake.yml` and `src/inventory360/utils/config.py`. To rename them, change all three. `INV360_DATABASE` / `INV360_WAREHOUSE` only override the app side. |
| App ownership | Snowflake cannot transfer ownership of a Streamlit app. If `INVENTORY_360_DB.APP.INVENTORY_360` already exists under another role, drop it before deploying as `INV360_ADMIN`. |
| Redeploys | `snow streamlit deploy --replace` recreates the app, which removes its grants and PyPI repository. Always deploy with `scripts/deploy_streamlit.ps1`, which re-applies both. |
| Sample data | Synthetic and deterministic, anchored to the current date. Re-running `02_generate_synthetic_data.sql` replaces all RAW data up to yesterday; then re-run steps 5–6 of section 4 and the quality checks. |
| Staging | Materialised as tables. A view cannot be replaced by a table of the same name, so drop old `STAGING.STG_*` views first when upgrading an older deployment. |
| Cost | The warehouse (`INV360_WH`), the Streamlit compute pool and each user's session queries consume credits. Caller's rights caches results per user session, so many users means more queries. |
| Security | No credentials are stored in the repository. `.env` files and `profiles.yml` are git-ignored; use `.env.example` and `profiles.example.yml` as templates. |

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Your Snowflake default role doesn't give access" | Grant an `INV360_*` role and set it as the user's `DEFAULT_ROLE`. |
| "You don't have access to this information" | The role lacks a privilege or the owner lacks a caller grant; re-run `sql/roles/02_callers_rights.sql`. |
| `ModuleNotFoundError: plotly` | The PyPI repository was detached by a redeploy; re-run the deploy script. |
| `Unsupported feature 'GRANT/REVOKE OWNERSHIP ON STREAMLIT'` | Drop the app and deploy again as `INV360_ADMIN`. |
| `syntax error line 1 at position 0 unexpected 'ï»¿'` | The SQL file has a UTF-8 BOM; save it as UTF-8 without BOM. |
| `Object found is of type 'VIEW'` when building staging | Drop the old staging views, then re-run the rendered SQL. |
