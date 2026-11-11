-- =============================================================================
-- Inventory 360 | Account security hardening (security audit H2)
--
-- REVIEW BEFORE RUNNING. Nothing here has been executed. These statements change
-- how people sign in; a mistake can lock you out of the account.
--
-- Safe-run checklist:
--   [ ] Keep one Snowsight session open as ACCOUNTADMIN the whole time (to undo).
--   [ ] Run one section at a time, then open a NEW private browser window and
--       confirm you can still sign in before moving on.
--   [ ] Store the break-glass password in a password manager, never in this repo.
--
-- Evidence (audit): MOHANAASHOK is the only ACCOUNTADMIN, has a password, no MFA,
-- no key pair; the account has 0 network policies and 0 password policies.
-- =============================================================================
USE ROLE ACCOUNTADMIN;

-- -----------------------------------------------------------------------------
-- 1. MFA for your user (done in Snowsight, not SQL)
--    Snowsight > your name > Settings > Authentication > Multi-factor authentication
--    > Enroll. Then confirm:
-- -----------------------------------------------------------------------------
-- SELECT name, has_mfa FROM snowflake.account_usage.users WHERE name = 'MOHANAASHOK';

-- -----------------------------------------------------------------------------
-- 2. Break-glass administrator (second way in if your user is locked or lost)
--    Replace <SET_A_LONG_RANDOM_PASSWORD> when you run it; do not save it here.
--    Sign in once as this user, change the password and enrol MFA, then log out
--    and only use it in an emergency.
-- -----------------------------------------------------------------------------
CREATE USER IF NOT EXISTS INV360_BREAKGLASS
    TYPE = PERSON
    PASSWORD = '<SET_A_LONG_RANDOM_PASSWORD>'
    MUST_CHANGE_PASSWORD = TRUE
    EMAIL = 'saravmona@gmail.com'
    DEFAULT_ROLE = ACCOUNTADMIN
    COMMENT = 'Emergency access only - see sql/roles/04_account_security.sql';
GRANT ROLE ACCOUNTADMIN TO USER INV360_BREAKGLASS;

-- -----------------------------------------------------------------------------
-- 3. Policies live in their own schema
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS INVENTORY_360_DB.SECURITY COMMENT = 'Account security policies';

-- 3a. Password policy: long passwords, lockout after repeated failures
CREATE PASSWORD POLICY IF NOT EXISTS INVENTORY_360_DB.SECURITY.PASSWORD_POLICY
    PASSWORD_MIN_LENGTH = 14
    PASSWORD_MIN_UPPER_CASE_CHARS = 1
    PASSWORD_MIN_LOWER_CASE_CHARS = 1
    PASSWORD_MIN_NUMERIC_CHARS = 1
    PASSWORD_MIN_SPECIAL_CHARS = 1
    PASSWORD_MAX_RETRIES = 5
    PASSWORD_LOCKOUT_TIME_MINS = 30
    PASSWORD_HISTORY = 5
    COMMENT = 'Inventory 360 account password policy';
-- Applies to new passwords; existing passwords keep working until changed.
ALTER ACCOUNT SET PASSWORD POLICY INVENTORY_360_DB.SECURITY.PASSWORD_POLICY;

-- 3b. Authentication policy: password sign-ins must use MFA.
--     Run ONLY after step 1 (your MFA) and step 2 (break-glass MFA) are done,
--     or password sign-in will prompt for an MFA you haven't enrolled.
CREATE AUTHENTICATION POLICY IF NOT EXISTS INVENTORY_360_DB.SECURITY.REQUIRE_MFA
    MFA_ENROLLMENT = REQUIRED
    COMMENT = 'Password sign-in requires MFA';
-- ALTER ACCOUNT SET AUTHENTICATION POLICY INVENTORY_360_DB.SECURITY.REQUIRE_MFA;

-- -----------------------------------------------------------------------------
-- 4. Network policy (optional, highest lock-out risk - left commented out)
--    Only if you always connect from known IPs. Your home IP may change; a wrong
--    list locks every user out. Find your IP: SELECT CURRENT_IP_ADDRESS();
--    Test on your USER first (ALTER USER ... SET NETWORK_POLICY), confirm a new
--    sign-in works, and only then consider the account level.
-- -----------------------------------------------------------------------------
-- CREATE NETWORK RULE INVENTORY_360_DB.SECURITY.ALLOWED_IPS
--     MODE = INGRESS TYPE = IPV4 VALUE_LIST = ('<YOUR_IP>/32');
-- CREATE NETWORK POLICY INV360_NETWORK_POLICY
--     ALLOWED_NETWORK_RULE_LIST = ('INVENTORY_360_DB.SECURITY.ALLOWED_IPS');
-- ALTER USER MOHANAASHOK SET NETWORK_POLICY = INV360_NETWORK_POLICY;

-- -----------------------------------------------------------------------------
-- Undo (from the session you kept open)
-- -----------------------------------------------------------------------------
-- ALTER ACCOUNT UNSET AUTHENTICATION POLICY;
-- ALTER ACCOUNT UNSET PASSWORD POLICY;
-- ALTER USER MOHANAASHOK UNSET NETWORK_POLICY;
