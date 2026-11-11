-- =============================================================================
-- Inventory 360 | Least-privilege APP grants (security audit M1, M2, L1)
-- Fresh installs: run after sql/deployment/01_app_objects.sql (SETUP.md step 9).
-- Existing installs: brings older broad grants in line with this model.
-- Idempotent: REVOKE of a privilege that is not held is a no-op. Run as SYSADMIN.
--
--   M2  Viewers: warehouse USAGE only. OPERATE lets a role suspend/resume the
--       warehouse and see/abort other users' queries on it.
--   M1  Planners: INSERT only in APP. UPDATE allowed editing the audit trail and
--       changing any order's STATUS (e.g. self-approval) outside the app.
--       Order status changes stay with INV360_ADMIN.
--   L1  Viewers: read the outbox view only, not the audit log or raw order rows.
-- =============================================================================
USE ROLE SYSADMIN;

-- M2: warehouse
REVOKE OPERATE ON WAREHOUSE INV360_WH FROM ROLE INV360_VIEWER;
GRANT  OPERATE ON WAREHOUSE INV360_WH TO   ROLE INV360_ADMIN;

-- M1: planner write-back is insert-only
REVOKE UPDATE ON ALL TABLES    IN SCHEMA INVENTORY_360_DB.APP FROM ROLE INV360_PLANNER;
REVOKE UPDATE ON FUTURE TABLES IN SCHEMA INVENTORY_360_DB.APP FROM ROLE INV360_PLANNER;
REVOKE INSERT ON FUTURE TABLES IN SCHEMA INVENTORY_360_DB.APP FROM ROLE INV360_PLANNER;
GRANT  INSERT ON TABLE INVENTORY_360_DB.APP.REPLENISHMENT_REQUESTS TO ROLE INV360_PLANNER;
GRANT  INSERT ON TABLE INVENTORY_360_DB.APP.APP_AUDIT_LOG          TO ROLE INV360_PLANNER;

-- L1: viewers read the outbox view, not the underlying tables
REVOKE SELECT ON ALL TABLES    IN SCHEMA INVENTORY_360_DB.APP FROM ROLE INV360_VIEWER;
REVOKE SELECT ON FUTURE TABLES IN SCHEMA INVENTORY_360_DB.APP FROM ROLE INV360_VIEWER;
GRANT  SELECT ON VIEW INVENTORY_360_DB.APP.V_REPLENISHMENT_OUTBOX TO ROLE INV360_VIEWER;
-- Developer tier (Data & governance page) still reads the audit trail
GRANT  SELECT ON TABLE INVENTORY_360_DB.APP.APP_AUDIT_LOG TO ROLE INV360_ENGINEER;

-- Verify
SHOW GRANTS TO ROLE INV360_VIEWER;
SHOW GRANTS TO ROLE INV360_PLANNER;
SHOW FUTURE GRANTS IN SCHEMA INVENTORY_360_DB.APP;
