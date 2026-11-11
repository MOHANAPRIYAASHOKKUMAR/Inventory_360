-- =============================================================================
-- Inventory 360 - restricted caller's rights for the Streamlit app
--
-- The app reads and writes with st.connection("snowflake-callers-rights"), so every
-- query runs as the viewer (their DEFAULT role). Snowflake allows a statement only
-- when BOTH hold:
--   1. the viewer's role has the privilege (sql/roles/01_roles_and_grants.sql), and
--   2. the app OWNER role holds a matching CALLER grant (this script).
--
-- Idempotent: safe to re-run. Run as ACCOUNTADMIN.
-- After running, redeploy the app as INV360_ADMIN:
--   .\scripts\deploy_streamlit.ps1 -Connection <name> -OwnerRole INV360_ADMIN
-- =============================================================================
use role accountadmin;

-- -----------------------------------------------------------------------------
-- 1. Customer objects created ad hoc as ACCOUNTADMIN -> SYSADMIN, like the rest
-- -----------------------------------------------------------------------------
grant ownership on table INVENTORY_360_DB.RAW.ERP_CUSTOMERS            to role SYSADMIN copy current grants;
grant ownership on view  INVENTORY_360_DB.STAGING.STG_CUSTOMERS        to role SYSADMIN copy current grants;
grant ownership on table INVENTORY_360_DB.MARTS.DIM_CUSTOMER           to role SYSADMIN copy current grants;
grant ownership on table INVENTORY_360_DB.MARTS.FCT_CUSTOMER_SALES_DAILY to role SYSADMIN copy current grants;

-- -----------------------------------------------------------------------------
-- 2. INV360_ADMIN becomes the app owner (caller grants are scoped to this role,
--    never to ACCOUNTADMIN). It already has CREATE STREAMLIT on APP.
-- -----------------------------------------------------------------------------
grant usage on compute pool SYSTEM_COMPUTE_POOL_CPU to role INV360_ADMIN;
grant usage, operate on warehouse INV360_WH to role INV360_ADMIN;
grant database role SNOWFLAKE.PYPI_REPOSITORY_USER to role INV360_ADMIN;
-- Existing app object: Snowflake does not support GRANT OWNERSHIP ON STREAMLIT, so a
-- STREAMLIT created by another role is dropped once here and recreated by INV360_ADMIN
-- on the next deploy (same name, same URL; the deploy script re-applies grants).
-- Uncomment only when migrating an app currently owned by a different role:
-- drop streamlit if exists INVENTORY_360_DB.APP.INVENTORY_360;

-- -----------------------------------------------------------------------------
-- 3. Viewer gap: the Warehouses page reads STAGING.STG_WAREHOUSE_COSTS
-- -----------------------------------------------------------------------------
grant usage  on schema INVENTORY_360_DB.STAGING                     to role INV360_VIEWER;
-- STAGING is materialised as tables (dbt_project.yml); the view grant covers older builds
grant select on table  INVENTORY_360_DB.STAGING.STG_WAREHOUSE_COSTS to role INV360_VIEWER;

-- -----------------------------------------------------------------------------
-- 4. Caller grants: what the app may do with the viewer's privileges
-- -----------------------------------------------------------------------------
grant manage caller grants on account to role SECURITYADMIN;
use role securityadmin;

grant caller usage on database INVENTORY_360_DB                  to role INV360_ADMIN;
grant caller usage on schema   INVENTORY_360_DB.MARTS            to role INV360_ADMIN;
grant caller usage on schema   INVENTORY_360_DB.STAGING          to role INV360_ADMIN;
grant caller usage on schema   INVENTORY_360_DB.APP              to role INV360_ADMIN;
grant caller usage on warehouse INV360_WH                        to role INV360_ADMIN;

-- Marts: current and future tables/views (dbt rebuilds keep working)
grant inherited caller select on all tables in schema INVENTORY_360_DB.MARTS to role INV360_ADMIN;
grant inherited caller select on all views  in schema INVENTORY_360_DB.MARTS to role INV360_ADMIN;

-- Staging: the single object business pages read (a table since staging moved off views)
grant caller select on table INVENTORY_360_DB.STAGING.STG_WAREHOUSE_COSTS to role INV360_ADMIN;

-- Data & governance page (Developer tier) catalogues RAW and STAGING. Viewers and
-- planners hold no privileges there, so these caller grants expose nothing to them.
grant caller usage on schema INVENTORY_360_DB.RAW to role INV360_ADMIN;
grant inherited caller select on all tables in schema INVENTORY_360_DB.RAW     to role INV360_ADMIN;
grant inherited caller select on all tables in schema INVENTORY_360_DB.STAGING to role INV360_ADMIN;
grant inherited caller select on all views  in schema INVENTORY_360_DB.STAGING to role INV360_ADMIN;

-- App schema: outbox view, audit log, replenishment write-back
grant caller select on view  INVENTORY_360_DB.APP.V_REPLENISHMENT_OUTBOX        to role INV360_ADMIN;
grant caller select, insert on table INVENTORY_360_DB.APP.REPLENISHMENT_REQUESTS to role INV360_ADMIN;
grant caller select, insert on table INVENTORY_360_DB.APP.APP_AUDIT_LOG          to role INV360_ADMIN;

-- -----------------------------------------------------------------------------
-- 5. Verify
-- -----------------------------------------------------------------------------
show caller grants to role INV360_ADMIN;
