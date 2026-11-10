-- =============================================================================
-- Inventory 360 | RAW layer - source system landing tables
-- Sources: ERP (master data, purchasing), WMS (stock), POS (sales),
--          TMS (transport), FIN (finance / budgets)
-- =============================================================================
USE SCHEMA INVENTORY_360_DB.RAW;

CREATE OR REPLACE TABLE ERP_SUPPLIERS (
    SUPPLIER_ID          VARCHAR(10)   NOT NULL,
    SUPPLIER_NAME        VARCHAR(100)  NOT NULL,
    COUNTRY_CODE         VARCHAR(2),
    COUNTRY_NAME         VARCHAR(50),
    PRIMARY_CATEGORY     VARCHAR(50),
    LEAD_TIME_DAYS       NUMBER(4,0),
    PAYMENT_TERMS_DAYS   NUMBER(4,0),
    CONTRACT_TIER        VARCHAR(20),     -- Strategic / Preferred / Approved
    RELIABILITY_FACTOR   NUMBER(5,3),     -- source-system score 0-1
    ACTIVE_FLAG          BOOLEAN,
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'ERP vendor master';

CREATE OR REPLACE TABLE WMS_WAREHOUSES (
    WAREHOUSE_CODE       VARCHAR(10)   NOT NULL,
    WAREHOUSE_NAME       VARCHAR(100)  NOT NULL,
    TOWN                 VARCHAR(50),
    UK_REGION            VARCHAR(50),
    NATION               VARCHAR(30),
    SITE_TYPE            VARCHAR(30),     -- National DC / Regional DC / Import Centre
    CAPACITY_PALLETS     NUMBER(10,0),
    LATITUDE             NUMBER(9,6),
    LONGITUDE            NUMBER(9,6),
    DEMAND_FACTOR        NUMBER(5,2),
    OPENED_DATE          DATE,
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'WMS site master';

CREATE OR REPLACE TABLE ERP_PRODUCTS (
    SKU                  VARCHAR(12)   NOT NULL,
    PRODUCT_NAME         VARCHAR(150),
    CATEGORY             VARCHAR(50),
    SUBCATEGORY          VARCHAR(50),
    BRAND                VARCHAR(50),
    SUPPLIER_ID          VARCHAR(10),
    UNIT_COST_GBP        NUMBER(10,2),
    UNIT_PRICE_GBP       NUMBER(10,2),
    UNITS_PER_PALLET     NUMBER(6,0),
    MIN_ORDER_QTY        NUMBER(8,0),
    SHELF_LIFE_DAYS      NUMBER(6,0),
    VELOCITY_CLASS       VARCHAR(1),      -- A / B / C (planner-assigned)
    LIFECYCLE_STATUS     VARCHAR(20),     -- Core / Seasonal / New / Discontinued
    LAUNCH_DATE          DATE,
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'ERP item master';

CREATE OR REPLACE TABLE WMS_STOCK_SNAPSHOT_DAILY (
    SNAPSHOT_DATE        DATE          NOT NULL,
    WAREHOUSE_CODE       VARCHAR(10)   NOT NULL,
    SKU                  VARCHAR(12)   NOT NULL,
    QTY_ON_HAND          NUMBER(12,0),
    QTY_ALLOCATED        NUMBER(12,0),
    QTY_RECEIVED         NUMBER(12,0),
    QTY_DAMAGED          NUMBER(12,0),
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) CLUSTER BY (SNAPSHOT_DATE) COMMENT = 'WMS end-of-day stock position';

CREATE OR REPLACE TABLE POS_SALES_DAILY (
    SALES_DATE           DATE          NOT NULL,
    WAREHOUSE_CODE       VARCHAR(10)   NOT NULL,   -- fulfilling DC
    SKU                  VARCHAR(12)   NOT NULL,
    UNITS_SOLD           NUMBER(12,0),
    UNITS_DEMANDED       NUMBER(12,0),             -- incl. unfulfilled demand
    NET_SALES_GBP        NUMBER(14,2),
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) CLUSTER BY (SALES_DATE) COMMENT = 'Store + online demand aggregated to fulfilling DC';

CREATE OR REPLACE TABLE ERP_PURCHASE_ORDER_LINES (
    PO_NUMBER            VARCHAR(20)   NOT NULL,
    PO_LINE              NUMBER(6,0)   NOT NULL,
    SUPPLIER_ID          VARCHAR(10),
    WAREHOUSE_CODE       VARCHAR(10),
    SKU                  VARCHAR(12),
    ORDER_DATE           DATE,
    EXPECTED_DATE        DATE,
    RECEIVED_DATE        DATE,
    QTY_ORDERED          NUMBER(12,0),
    QTY_RECEIVED         NUMBER(12,0),
    UNIT_COST_GBP        NUMBER(10,2),
    PO_STATUS            VARCHAR(20),     -- RECEIVED / IN_TRANSIT / OPEN
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'ERP purchase order lines';

CREATE OR REPLACE TABLE TMS_SHIPMENTS (
    SHIPMENT_ID          VARCHAR(20)   NOT NULL,
    PO_NUMBER            VARCHAR(20),
    CARRIER              VARCHAR(50),
    TRANSPORT_MODE       VARCHAR(10),     -- Road / Sea / Air / Rail
    ORIGIN_COUNTRY       VARCHAR(2),
    DESTINATION_CODE     VARCHAR(10),
    DISPATCH_DATE        DATE,
    PLANNED_ARRIVAL      DATE,
    ACTUAL_ARRIVAL       DATE,
    PALLETS              NUMBER(8,0),
    FREIGHT_COST_GBP     NUMBER(12,2),
    DUTY_COST_GBP        NUMBER(12,2),
    CO2_KG               NUMBER(12,1),
    SHIPMENT_STATUS      VARCHAR(20),
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'TMS inbound shipments';

CREATE OR REPLACE TABLE FIN_WAREHOUSE_COSTS_MONTHLY (
    PERIOD_MONTH         DATE          NOT NULL,
    WAREHOUSE_CODE       VARCHAR(10)   NOT NULL,
    COST_CATEGORY        VARCHAR(30)   NOT NULL,   -- Labour / Rent & Rates / Utilities / Equipment / Shrinkage
    ACTUAL_COST_GBP      NUMBER(14,2),
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'Finance GL actuals by site';

CREATE OR REPLACE TABLE FIN_BUDGETS_MONTHLY (
    PERIOD_MONTH         DATE          NOT NULL,
    BUDGET_AREA          VARCHAR(30)   NOT NULL,   -- Inventory Purchases / Freight / Warehousing
    DIMENSION_KEY        VARCHAR(50)   NOT NULL,   -- category or warehouse code
    BUDGET_GBP           NUMBER(14,2),
    FORECAST_GBP         NUMBER(14,2),
    BUDGET_VERSION       VARCHAR(20),
    _LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
) COMMENT = 'FY budget and latest forecast';
