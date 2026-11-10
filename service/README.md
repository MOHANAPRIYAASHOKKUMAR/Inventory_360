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
| Role | `INV360_ENGINEER` (needs UPDATE on `REPLENISHMENT_REQUESTS`, INSERT on `APP_AUDIT_LOG`) |

## Processing loop

1. Select `APPROVED` rows from the outbox (batch of ≤ 500).
2. Group by `SUPPLIER_ID` + `WAREHOUSE_CODE` into one PO per supplier/site; lines keep `REQUEST_ID`.
3. POST to the ERP purchasing API; on 2xx set `STATUS = 'SENT_TO_ERP'` for those request IDs.
4. On failure leave the status unchanged and log the error; the next run retries (idempotent by `REQUEST_ID`).

## Deployment options

- **Snowpark Container Services** job on a schedule (`spec.yaml` in this folder), with an external access
  integration to the ERP host. Requires a non-trial account.
- **Snowflake task + stored procedure** calling an external function, if the ERP exposes an API gateway.

## Why not built yet

Trial accounts cannot create external access integrations, so the service cannot reach an ERP. The
outbox view and status model are in place so the service can be added without app changes.
