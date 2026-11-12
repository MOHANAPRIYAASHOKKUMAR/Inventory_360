# ERP interface service (design)

Status: **designed, not deployed.** The Streamlit app writes planner-approved orders to
`INVENTORY_360_DB.APP.REPLENISHMENT_REQUESTS`; this service is the outbound leg that turns them into
purchase orders in the ERP.

## Contract

| Item | Value |
| --- | --- |
| Source | `INVENTORY_360_DB.APP.V_REPLENISHMENT_OUTBOX` (status `SUBMITTED` / `APPROVED`) |
| Status lifecycle | `SUBMITTED` → `APPROVED` → `SENT_TO_ERP` (or `REJECTED`) |
| Idempotency key | `REQUEST_ID` (UUID) — sent as the ERP external reference |
| Audit | Every transition writes a row to `APP.APP_AUDIT_LOG` (`EVENT_TYPE = 'ERP_SYNC'`) |
| Role | Needs UPDATE on `REPLENISHMENT_REQUESTS` and INSERT on `APP_AUDIT_LOG`. `INV360_ENGINEER` does **not** have UPDATE: after `sql/roles/03_hardening.sql` it inherits only INSERT on both tables (via `INV360_PLANNER`) plus SELECT on `APP_AUDIT_LOG`, and order status changes stay with `INV360_ADMIN`. Run the service as `INV360_ADMIN`, or grant UPDATE on `REPLENISHMENT_REQUESTS` to a dedicated service role before deploying |

## Processing loop

1. Select `APPROVED` rows from the outbox (batch of ≤ 500).
2. Group by `SUPPLIER_ID` + `WAREHOUSE_CODE` into one PO per supplier/site; lines keep `REQUEST_ID`.
3. POST to the ERP purchasing API; on 2xx set `STATUS = 'SENT_TO_ERP'` for those request IDs.
4. On failure leave the status unchanged and log the error; the next run retries (idempotent by `REQUEST_ID`).

## Deployment options

- **Snowpark Container Services** job on a schedule (`spec.yaml` in this folder: the `erp-outbox-sync`
  job run with `EXECUTE JOB SERVICE`), with an external access integration to the ERP host. Requires a
  non-trial account. `app_service_spec.yaml` in the same folder is unrelated to this service: it is the
  long-running Streamlit app service described in `docs/container_deployment.md`.
- **Snowflake task + stored procedure** calling an external function, if the ERP exposes an API gateway.

## Why not built yet

Trial accounts cannot create external access integrations, so the service cannot reach an ERP. The
outbox view and status model are in place so the service can be added without app changes.
