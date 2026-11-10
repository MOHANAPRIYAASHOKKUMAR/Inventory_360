-- =============================================================================
-- Inventory 360 | Application objects (APP schema)
-- Write-back tables used by the Streamlit app for the replenishment approval
-- workflow, plus an audit log. Run after dbt has built the MARTS schema.
-- =============================================================================
USE ROLE SYSADMIN;
USE SCHEMA INVENTORY_360_DB.APP;

CREATE TABLE IF NOT EXISTS REPLENISHMENT_REQUESTS (
    REQUEST_ID               VARCHAR(36)    DEFAULT UUID_STRING(),
    CREATED_AT               TIMESTAMP_LTZ  DEFAULT CURRENT_TIMESTAMP(),
    CREATED_BY               VARCHAR(255)   DEFAULT CURRENT_USER(),
    AS_OF_DATE               DATE,
    WAREHOUSE_CODE           VARCHAR(10),
    SKU                      VARCHAR(12),
    SUPPLIER_ID              VARCHAR(10),
    RECOMMENDED_QTY          NUMBER(12,0),
    APPROVED_QTY             NUMBER(12,0),
    UNIT_COST_GBP            NUMBER(10,2),
    ORDER_VALUE_GBP          NUMBER(14,2),
    PRIORITY                 VARCHAR(20),
    STATUS                   VARCHAR(20)    DEFAULT 'SUBMITTED',  -- SUBMITTED / APPROVED / REJECTED / SENT_TO_ERP
    PLANNER_NOTE             VARCHAR(1000),
    CONSTRAINT PK_REPLENISHMENT_REQUESTS PRIMARY KEY (REQUEST_ID)
) COMMENT = 'Planner-approved replenishment orders awaiting ERP interface';

CREATE TABLE IF NOT EXISTS APP_AUDIT_LOG (
    EVENT_ID                 VARCHAR(36)    DEFAULT UUID_STRING(),
    EVENT_TS                 TIMESTAMP_LTZ  DEFAULT CURRENT_TIMESTAMP(),
    USER_NAME                VARCHAR(255)   DEFAULT CURRENT_USER(),
    EVENT_TYPE               VARCHAR(50),
    EVENT_DETAIL             VARIANT
) COMMENT = 'Application audit trail';

-- Convenience view for the ERP interface / downstream integration
CREATE OR REPLACE VIEW V_REPLENISHMENT_OUTBOX AS
SELECT r.*, p.PRODUCT_NAME, s.SUPPLIER_NAME
FROM REPLENISHMENT_REQUESTS r
LEFT JOIN INVENTORY_360_DB.MARTS.DIM_PRODUCT p  ON p.SKU = r.SKU
LEFT JOIN INVENTORY_360_DB.MARTS.DIM_SUPPLIER s ON s.SUPPLIER_ID = r.SUPPLIER_ID
WHERE r.STATUS IN ('SUBMITTED', 'APPROVED');
