# Runbook

Connection used in examples: `tbsljyv-rm91730` (from `~/.snowflake/connections.toml`).
Prefix commands with `.venv\Scripts\` on Windows if the tools are not on PATH.

## Routine operations

### Refresh the models

```powershell
cd dbt_inventory
dbt build --profiles-dir <dir-with-profiles.yml>
```

SSO-only accounts (dbt cannot authenticate): render and run the SQL instead.

```powershell
python scripts/render_dbt_models.py > sql/deployment/02_dbt_models_rendered.sql
snow sql -c tbsljyv-rm91730 -f sql/deployment/02_dbt_models_rendered.sql
```

### Deploy / redeploy the app

```powershell
.\scripts\deploy_streamlit.ps1 -Connection tbsljyv-rm91730
```

Add any new Python file to `artifacts` in `snowflake.yml` first — unlisted files are not uploaded.

### Change the app's warehouse

```sql
ALTER STREAMLIT INVENTORY_360_DB.APP.INVENTORY_360 SET QUERY_WAREHOUSE = INV360_WH;
```

### Grant a user access

```sql
GRANT ROLE INV360_VIEWER  TO USER <user>;   -- dashboards only
GRANT ROLE INV360_PLANNER TO USER <user>;   -- + replenishment submission
```

### Review submitted replenishment

```sql
SELECT * FROM INVENTORY_360_DB.APP.V_REPLENISHMENT_OUTBOX ORDER BY CREATED_AT DESC;
SELECT * FROM INVENTORY_360_DB.APP.APP_AUDIT_LOG ORDER BY EVENT_TS DESC LIMIT 100;
```

## Troubleshooting

| Symptom | Check / fix |
| --- | --- |
| App shows stale numbers | Cached reads expire after 10 min (operational) / 1 h (reference); wait or redeploy to reset. Confirm models refreshed: `SELECT MAX(SNAPSHOT_DATE) FROM MARTS.FCT_INVENTORY_DAILY` |
| App fails on first load after deploy | A file is missing from `snowflake.yml` `artifacts`. Re-run the deploy script — its pre-flight check lists missing files |
| `ModuleNotFoundError` in deployed app | Package not in the container runtime. Trial accounts cannot add PyPI packages (no external access integrations) |
| `Invalid connection_name` locally | Set `SNOWFLAKE_DEFAULT_CONNECTION_NAME` to a name from `snow connection list` |
| Planner cannot submit | Role lacks `INSERT` on `APP.REPLENISHMENT_REQUESTS` — re-run `sql/roles/01_roles_and_grants.sql` |
| Warehouse cost higher than expected | `SHOW WAREHOUSES LIKE 'INV360_WH'` — confirm X-Small and `AUTO_SUSPEND = 60` |
| GitHub push rejected (file > 100 MB) | A virtual environment was committed. Keep `.venv/` and `.venv-dbt/` in `.gitignore`; remove them from history before pushing |

## Rebuild from zero

Run in order: `sql/setup/01_database_and_warehouse.sql` → `sql/roles/01_roles_and_grants.sql` →
`sql/load/01_create_raw_tables.sql` → `sql/load/02_generate_synthetic_data.sql` → dbt build (or the
rendered SQL) → `sql/deployment/01_app_objects.sql` → deploy script.

`01_create_raw_tables.sql` uses `CREATE OR REPLACE` and **drops existing RAW data**.
