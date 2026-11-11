-- =============================================================================
-- Inventory 360 | Customer master (ERP)
-- Synthetic customer accounts: one per sales channel per fulfilling site.
-- Fictional names. Deterministic: re-running yields the same rows.
-- Adds RAW.ERP_CUSTOMERS only; no existing table is modified.
-- =============================================================================
USE SCHEMA INVENTORY_360_DB.RAW;

CREATE OR REPLACE TABLE ERP_CUSTOMERS (
    CUSTOMER_ID            VARCHAR(10)   NOT NULL,
    CUSTOMER_NAME          VARCHAR(120)  NOT NULL,
    CHANNEL                VARCHAR(30)   NOT NULL,   -- Own stores / Franchise / Wholesale / Online
    CUSTOMER_SEGMENT       VARCHAR(30)   NOT NULL,   -- Key account / Standard
    HOME_WAREHOUSE_CODE    VARCHAR(10)   NOT NULL,   -- fulfilling DC
    CREDIT_TERMS_DAYS      NUMBER(3,0),
    CREDIT_LIMIT_GBP       NUMBER(12,0),
    ACCOUNT_MANAGER        VARCHAR(60),
    ONBOARDED_DATE         DATE,
    ACTIVE_FLAG            BOOLEAN       DEFAULT TRUE,
    _LOADED_AT             TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_ERP_CUSTOMERS PRIMARY KEY (CUSTOMER_ID)
) COMMENT = 'ERP customer master - accounts served by each distribution site';

INSERT INTO ERP_CUSTOMERS
    (CUSTOMER_ID, CUSTOMER_NAME, CHANNEL, CUSTOMER_SEGMENT, HOME_WAREHOUSE_CODE,
     CREDIT_TERMS_DAYS, CREDIT_LIMIT_GBP, ACCOUNT_MANAGER, ONBOARDED_DATE, ACTIVE_FLAG)
WITH channels AS (
    SELECT * FROM VALUES
        (1, 'Own stores', 'Key account', 0,  'SRG {town} Stores'),
        (2, 'Franchise',  'Key account', 30, '{region} Franchise Partners'),
        (3, 'Wholesale',  'Standard',    45, '{town} Trade Wholesale'),
        (4, 'Online',     'Standard',    0,  'SRG Online - {town} Fulfilment')
        AS c(ch_no, channel, segment, terms, name_tpl)
),
managers AS (
    SELECT * FROM VALUES
        (0, 'A. Patel'), (1, 'J. Murray'), (2, 'R. Evans'), (3, 'S. O''Neill'),
        (4, 'L. Hughes'), (5, 'K. Campbell')
        AS m(m_no, manager)
),
sites AS (
    SELECT warehouse_code, town, uk_region,
           ROW_NUMBER() OVER (ORDER BY warehouse_code) AS site_no
    FROM WMS_WAREHOUSES
)
SELECT
    'CUST' || LPAD(TO_VARCHAR((s.site_no - 1) * 4 + c.ch_no), 3, '0')               AS customer_id,
    REPLACE(REPLACE(c.name_tpl, '{town}', s.town), '{region}', s.uk_region)           AS customer_name,
    c.channel,
    c.segment,
    s.warehouse_code,
    c.terms,
    IFF(c.channel = 'Own stores', NULL, 250000 + MOD(ABS(HASH(s.warehouse_code, c.channel)), 8) * 125000),
    m.manager,
    DATEADD(day, -MOD(ABS(HASH(s.warehouse_code, c.channel, 'onboard')), 2900), '2025-04-01'::date),
    TRUE
FROM sites s
CROSS JOIN channels c
JOIN managers m ON m.m_no = MOD(s.site_no + c.ch_no, 6)
ORDER BY 1;
