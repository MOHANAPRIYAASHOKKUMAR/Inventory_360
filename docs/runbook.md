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
.\scripts\deploy_streamlit.ps1 -Connection tbsljyv-rm91730 -OwnerRole INV360_ADMIN
```

Add any new Python file to `artifacts` in `snowflake.yml` first — unlisted files are not uploaded.
The deploying user must be able to use `INV360_ADMIN`.

The script runs `snow streamlit deploy --replace`, which **recreates** the STREAMLIT object and so drops
its grants and attached artifact repositories. The script re-applies both; if you deployed another way,
re-run the script or restore them by hand:

```sql
ALTER STREAMLIT INVENTORY_360_DB.APP.INVENTORY_360
  SET ARTIFACT_REPOSITORIES = (snowflake.snowpark.pypi_shared_repository);
GRANT USAGE ON STREAMLIT INVENTORY_360_DB.APP.INVENTORY_360 TO ROLE INV360_PLANNER;
GRANT USAGE ON STREAMLIT INVENTORY_360_DB.APP.INVENTORY_360 TO ROLE INV360_VIEWER;
```

Plotly and the other packages come from Snowflake's shared PyPI repository using
`streamlit_app/requirements.txt` (no external access integration needed, works on trial accounts).
The owner role needs `SNOWFLAKE.PYPI_REPOSITORY_USER`, granted by `sql/roles/02_callers_rights.sql`.

`GRANT OWNERSHIP ON STREAMLIT` is not supported. To change the owner, drop the app and redeploy as the
new owner role:

```sql
DROP STREAMLIT IF EXISTS INVENTORY_360_DB.APP.INVENTORY_360;
```

then run the deploy script with `-OwnerRole INV360_ADMIN` (caller grants are scoped to that role).

### Change the app's warehouse

```sql
ALTER STREAMLIT INVENTORY_360_DB.APP.INVENTORY_360 SET QUERY_WAREHOUSE = INV360_WH;
```

### Grant a user access

```sql
GRANT ROLE INV360_VIEWER  TO USER <user>;   -- dashboards only
GRANT ROLE INV360_PLANNER TO USER <user>;   -- + replenishment submission
ALTER USER <user> SET DEFAULT_ROLE = INV360_VIEWER;   -- or INV360_PLANNER
```

Setting `DEFAULT_ROLE` is required: the app runs with restricted caller's rights and its connection uses
the viewer's **default** role, not the role selected in Snowsight. A user whose default role is not an
`INV360_*` role (or `SYSADMIN` / `ACCOUNTADMIN`) gets an access message instead of the dashboard.
The Data & governance page is shown only to `INV360_ENGINEER`, `INV360_ADMIN`, `SYSADMIN` and
`ACCOUNTADMIN`.

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
| `ModuleNotFoundError` in deployed app (e.g. `plotly`) | The shared PyPI repository was detached by a redeploy, or the package is missing from `streamlit_app/requirements.txt`. Re-run the deploy script (or the `ALTER STREAMLIT ... SET ARTIFACT_REPOSITORIES` above) |
| "Your Snowflake default role doesn't give access" | Grant an `INV360_*` role and set it as the user's `DEFAULT_ROLE` |
| "Inventory 360 couldn't confirm who you are" | The caller's-rights viewer token was unavailable. The app fails closed (no data, no fallback to owner's rights). Reopen the app |
| "You don't have access to this information" | The viewer's role lacks the privilege, or `INV360_ADMIN` lacks the matching caller grant — re-run `sql/roles/02_callers_rights.sql` |
| `Unsupported feature 'GRANT/REVOKE OWNERSHIP ON STREAMLIT'` | Drop the app and redeploy as `INV360_ADMIN` |
| `Invalid connection_name` locally | Set `SNOWFLAKE_DEFAULT_CONNECTION_NAME` to a name from `snow connection list` |
| Planner cannot submit | The user's default role must be `INV360_PLANNER` (Planner tier shows the *Submit approved orders* button). Planners are INSERT-only on `APP.REPLENISHMENT_REQUESTS` and `APP.APP_AUDIT_LOG` (`sql/roles/03_hardening.sql`); the owner also needs `CALLER SELECT, INSERT` on both tables (`sql/roles/02_callers_rights.sql`). Re-run both scripts |
| Warehouse cost higher than expected | `SHOW WAREHOUSES LIKE 'INV360_WH'` — confirm X-Small and `AUTO_SUSPEND = 60` |
| GitHub push rejected (file > 100 MB) | A virtual environment was committed. Keep `.venv/` and `.venv-dbt/` in `.gitignore`; remove them from history before pushing |

## Rebuild from zero

Run in order (see SETUP.md section 4 for the commands and roles):

1. `sql/setup/01_database_and_warehouse.sql`
2. `sql/roles/01_roles_and_grants.sql`
3. `sql/load/01_create_raw_tables.sql`
4. `sql/load/02_generate_synthetic_data.sql`
5. `sql/load/03_create_customers.sql`
6. dbt build (or `sql/deployment/02_dbt_models_rendered.sql`)
7. `sql/deployment/01_app_objects.sql`
8. `sql/roles/02_callers_rights.sql` (ACCOUNTADMIN)
9. `sql/roles/03_hardening.sql`
10. `.\scripts\deploy_streamlit.ps1 -Connection <name> -OwnerRole INV360_ADMIN`

`01_create_raw_tables.sql` uses `CREATE OR REPLACE` and **drops existing RAW data**.

## Smoke test

`scripts/e2e_smoke.py` runs the app headless (Streamlit `AppTest`) against live Snowflake data.

```powershell
$env:SNOWFLAKE_DEFAULT_CONNECTION_NAME = "tbsljyv-rm91730"
.venv\Scripts\python.exe scripts\e2e_smoke.py                  # all sections
.venv\Scripts\python.exe scripts\e2e_smoke.py pages filters    # selected sections
.venv\Scripts\python.exe scripts\e2e_smoke.py --no-write       # skip the write path
```

Sections: `pages` (every page x tier), `filters`, `controls`, `drills`, `write` (planner submits
replenishment lines, verifies them in Snowflake, then removes them), `data` (overview net sales vs
direct SQL), `security` (viewer INSERT rejected, caller grants present, app owned by `INV360_ADMIN`).
Exit code is 1 if any check fails.

The script sets `INV360_TIER_OVERRIDE` per tier and `INV360_START_PAGE` to open each page through the
navigation script (so the sidebar filters exist), and seeds filter values into session state before
each run. Both variables are ignored inside Snowflake.

## Break-glass access

`sql/roles/04_account_security.sql` is **not** part of the automated run order. On this account it has
already been applied: `INV360_BREAKGLASS` (login `MONA_BREAKGLASS`) exists with MFA enrolled. When
re-running it on a new account, read its checklist, keep one ACCOUNTADMIN session open, and run it one
section at a time.

- Break-glass user `INV360_BREAKGLASS` (`DEFAULT_ROLE = ACCOUNTADMIN`, granted `ACCOUNTADMIN`),
  created with a long random password and `MUST_CHANGE_PASSWORD = TRUE`. Keep the password in a
  password manager, never in the repo.
- Sign in once as `INV360_BREAKGLASS`, change the password, enrol MFA, log out; use it only in an
  emergency.
- Password policy `INVENTORY_360_DB.SECURITY.PASSWORD_POLICY` is set on the account.
- Authentication policy `INVENTORY_360_DB.SECURITY.REQUIRE_MFA` (`MFA_ENROLLMENT = REQUIRED`) is
  created; the `ALTER ACCOUNT SET AUTHENTICATION POLICY` line is commented out — apply it only after
  your user and the break-glass user have enrolled MFA.
- No network policy is applied; that section is commented out because of the lock-out risk.
- Undo from the open session: `ALTER ACCOUNT UNSET AUTHENTICATION POLICY;`
  `ALTER ACCOUNT UNSET PASSWORD POLICY;`
