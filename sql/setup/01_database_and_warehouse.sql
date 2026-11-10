-- =============================================================================
-- Inventory 360 | 01 - Database, schemas and warehouse
-- Sample Retail Group - Enterprise Supply Chain Intelligence Platform
-- Run as: SYSADMIN (or ACCOUNTADMIN)
-- =============================================================================
USE ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS INV360_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Inventory 360 - transformation, BI and Streamlit workloads';

CREATE DATABASE IF NOT EXISTS INVENTORY_360_DB
    COMMENT = 'Inventory 360 - Sample Retail Group supply chain intelligence platform';

-- Medallion-style layering
CREATE SCHEMA IF NOT EXISTS INVENTORY_360_DB.RAW
    COMMENT = 'Landing zone: source-system extracts (ERP, WMS, TMS, Finance)';
CREATE SCHEMA IF NOT EXISTS INVENTORY_360_DB.STAGING
    COMMENT = 'dbt staging models: cleansed, typed, conformed';
CREATE SCHEMA IF NOT EXISTS INVENTORY_360_DB.MARTS
    COMMENT = 'dbt marts: dimensional model and business-ready KPIs';
CREATE SCHEMA IF NOT EXISTS INVENTORY_360_DB.APP
    COMMENT = 'Application objects: Streamlit app, write-back tables, services';

-- File format and stage for source extracts
CREATE FILE FORMAT IF NOT EXISTS INVENTORY_360_DB.RAW.FF_CSV
    TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF = ('', 'NULL') EMPTY_FIELD_AS_NULL = TRUE;

CREATE STAGE IF NOT EXISTS INVENTORY_360_DB.RAW.SOURCE_EXTRACTS
    FILE_FORMAT = INVENTORY_360_DB.RAW.FF_CSV
    COMMENT = 'Inbound CSV extracts from source systems';
