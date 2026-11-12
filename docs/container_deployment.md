# Container deployment — Docker, Snowpark Container Registry and Snowpark Container Services

This guide packages the Inventory 360 Streamlit app as a Docker image, runs it locally, then deploys it
to Snowflake-managed compute. It complements the Streamlit-in-Snowflake deployment (`snowflake.yml`),
which remains the simplest way to host the app.

## Concepts

| | Snowpark Container **Registry** (SPCR) | Snowpark Container **Services** (SPCS) |
| --- | --- | --- |
| What it is | An OCI-compliant image registry inside your Snowflake account | A managed runtime that runs containers on Snowflake compute |
| Snowflake object | `IMAGE REPOSITORY` (schema-level) | `COMPUTE POOL` (account-level) + `SERVICE` (schema-level) |
| You interact with it via | `docker login / tag / push` to `<account>.registry.snowflakecomputing.com` | SQL: `CREATE SERVICE`, `ALTER SERVICE`, `SHOW ENDPOINTS` |
| Cost | Image storage only (billed like stage storage) | Credits per compute-pool node while it is running (idle or active) |
| Analogy | Docker Hub / Amazon ECR | Kubernetes / Amazon ECS |

**In short:** the registry *stores* the image; Container Services *pulls that image and runs it* on a
compute pool, exposing an authenticated HTTPS endpoint. You need both, but only the compute pool and
service consume compute credits.

## What is in the repository

| File | Purpose |
| --- | --- |
| `Dockerfile` | Multi-stage `python:3.11-slim-bookworm` image, non-root user, `linux/amd64`, built-in `HEALTHCHECK` |
| `requirements.txt` | Pinned runtime dependencies (versions validated locally) |
| `streamlit_app/requirements.txt` | Package list for the Streamlit-in-Snowflake container runtime (installed from PyPI); keep in step with the root file |
| `.dockerignore` | Excludes venvs, git, secrets, dbt/SQL/docs/tests from the build context |
| `docker/entrypoint.sh` | Startup command: detects auth mode, refuses to start without credentials, `exec streamlit run` |
| `streamlit_app/.streamlit/config.toml` | Theme; container server settings are applied via `STREAMLIT_*` env vars in the Dockerfile |
| `.env.example` | Environment-based configuration template for local runs |
| `service/app_service_spec.yaml` | SPCS service specification (container, env, resources, readiness probe, public endpoint) |
| `sql/deployment/03_spcs_container_service.sql` | All Snowflake-side SQL: repository, stage, pool, service, grants, suspend, drop |

### Health check

Streamlit exposes `GET /_stcore/health` → `200 ok` when the server is ready. It is used by:

- Docker `HEALTHCHECK` (container shows `healthy` in `docker ps`)
- SPCS `readinessProbe` (traffic is routed only after it passes)

### Environment-based configuration

`src/inventory360/data_access/connection.py` chooses how to authenticate from the environment:

| Mode | Triggered by | Used where |
| --- | --- | --- |
| `callers` | `SNOWFLAKE_HOST` set, `/snowflake/session/token` exists and the request carries the viewer token header (`Sf-Context-Current-User-Token`); disable with `INV360_CALLERS_RIGHTS=false` | Streamlit in Snowflake (container runtime) — restricted caller's rights as the viewer's default role |
| `spcs` | `SNOWFLAKE_HOST` set, `/snowflake/session/token` exists, no viewer token, and `INV360_ALLOW_SERVICE_IDENTITY=true` | Snowpark Container Services acting as the service owner role — no secrets in the image |
| `named` | `SNOWFLAKE_DEFAULT_CONNECTION_NAME` | Local `streamlit run` with `~/.snowflake/connections.toml` |
| `env` | `SNOWFLAKE_ACCOUNT` + `SNOWFLAKE_USER` + (`SNOWFLAKE_PRIVATE_KEY_FILE` or `SNOWFLAKE_PASSWORD`) | Local Docker |
| `sis` | none of the above | Streamlit in Snowflake |

Inside Snowflake (`SNOWFLAKE_HOST` set) with neither `callers` nor `spcs` available the mode is `denied`:
the app fails closed rather than falling back to the owner's identity.

| Variable | Default | Meaning |
| --- | --- | --- |
| `INV360_DATABASE` | `INVENTORY_360_DB` | Database holding RAW / STAGING / MARTS / APP |
| `INV360_WAREHOUSE` | `INV360_WH` | Warehouse for queries |
| `INV360_SCHEMA` | `MARTS` | Default schema for the session |
| `SNOWFLAKE_ROLE` | `INV360_VIEWER` | Role for `env` mode (SPCS uses the service owner role, opt-in via `INV360_ALLOW_SERVICE_IDENTITY`) |
| `PORT` | `8501` | Streamlit port inside the container |

## Account eligibility (checked 2026-11-11 on `TBSLJYV-RM91730`, AWS us-east-2)

| Check | Result |
| --- | --- |
| Account type | **Trial**. Snowflake's SPCS tutorials state *"trial accounts are not supported"*. |
| SPCS present in account | Yes — Snowflake-managed pools `SYSTEM_COMPUTE_POOL_CPU` / `_GPU` exist (they back Streamlit in Snowflake) |
| Instance families offered in region | Yes — `CPU_X64_XS`, `GEN_X64_G2_*`, etc. (`SHOW COMPUTE POOL INSTANCE FAMILIES`) |
| Registry host published | Yes — `tbsljyv-rm91730.registry.snowflakecomputing.com` in `SYSTEM$ALLOWLIST()` |
| User-created image repository / compute pool / service | **Not verified.** Creating them was deliberately not attempted (would start billable compute without approval). |
| External access integrations | **Not available on trial** (confirmed: `External access is not supported for trial accounts`). Not required by this app — it reaches Snowflake through the internal SPCS token. |
| Docker on the development machine | **Not installed** — local container build/run has not been executed yet. |

**Status: the container deployment has NOT been performed.** Everything below is ready to run on an
eligible (paid / on-demand) account once Docker is installed and the local container test passes.

## Prerequisites

1. **Docker Desktop** (Windows): install, enable the WSL 2 backend, then `docker version` must show a Server section.
2. **Snowflake CLI** — already in `.venv\Scripts\snow.exe` (v3.16).
3. **Non-interactive credentials for the local container.** Your connection uses browser OAuth, which
   cannot run inside a headless container. Choose one:
   - **Key pair (recommended — no network policy needed):**
     ```powershell
     mkdir secrets
     openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out secrets\rsa_key.p8 -nocrypt
     openssl rsa -in secrets\rsa_key.p8 -pubout -out secrets\rsa_key.pub
     ```
     ```sql
     -- paste the key body without the BEGIN/END lines
     ALTER USER MohanaAshok SET RSA_PUBLIC_KEY = 'MIIBIjANBgkqh...';
     ```
   - **Programmatic access token:** Snowsight → *Settings* → *Authentication* → *Generate new token*.
     By default PATs only authenticate when the user is subject to a **network policy**; without one,
     authentication fails.
4. **A role for the app user.** The Streamlit-in-Snowflake app is owned by `INV360_ADMIN` and runs
   under restricted caller's rights (`sql/roles/02_callers_rights.sql`); the container uses the role in
   `SNOWFLAKE_ROLE`, which must be granted to the user it authenticates as, for example:
   ```sql
   GRANT ROLE INV360_VIEWER TO USER MohanaAshok;   -- INV360_PLANNER to test submit
   ```
   Never run the container as ACCOUNTADMIN: the app acts with exactly this role.

`secrets/` and `.env` must never be committed — `*.p8`, `*.pem` and `.env` are in `.gitignore` and `.dockerignore`.

## 1. Build the image

From the repository root:

```powershell
docker build --platform linux/amd64 -t inventory-360:1.0.0 --build-arg APP_VERSION=1.0.0 .
docker images inventory-360
```

`--platform linux/amd64` is mandatory: SPCS `CPU_X64` / `GEN_X64` nodes run amd64 images.

## 2. Test the container locally (required before Snowflake deployment)

```powershell
Copy-Item .env.example .env      # then fill in the credential values
```

Key-pair (mount the key read-only). `127.0.0.1:` keeps the app reachable from this PC only:

```powershell
docker run --rm -d --name inv360 -p 127.0.0.1:8501:8501 --env-file .env `
  -e SNOWFLAKE_PRIVATE_KEY_FILE=/secrets/rsa_key.p8 `
  -v ${PWD}\secrets:/secrets:ro `
  inventory-360:1.0.0
```

PAT (value set as `SNOWFLAKE_PASSWORD` in `.env`):

```powershell
docker run --rm -d --name inv360 -p 127.0.0.1:8501:8501 --env-file .env inventory-360:1.0.0
```

Verify:

```powershell
docker logs inv360                                   # "Inventory 360 starting ... Snowflake auth: env (...)"
Invoke-WebRequest http://localhost:8501/_stcore/health -UseBasicParsing | Select-Object StatusCode, Content   # 200 ok
docker inspect --format '{{.State.Health.Status}}' inv360                        # healthy (after ~30 s)
Start-Process http://localhost:8501                  # open all 10 pages; check for error boxes
docker stop inv360
```

Do not continue until every page loads in the container.

## 3. Authenticate to Snowflake

```powershell
.venv\Scripts\snow connection test -c tbsljyv-rm91730
```

## 4. Create or select the image repository (SPCR)

```sql
USE ROLE ACCOUNTADMIN;
CREATE IMAGE REPOSITORY IF NOT EXISTS INVENTORY_360_DB.APP.INV360_IMAGES;
SHOW IMAGE REPOSITORIES IN SCHEMA INVENTORY_360_DB.APP;
```

The `repository_url` will be:
`tbsljyv-rm91730.registry.snowflakecomputing.com/inventory_360_db/app/inv360_images`

## 5. Log in to the registry, tag and push

```powershell
.venv\Scripts\snow spcs image-registry login -c tbsljyv-rm91730

$REPO = "tbsljyv-rm91730.registry.snowflakecomputing.com/inventory_360_db/app/inv360_images"
docker tag inventory-360:1.0.0 "$REPO/inventory-360:1.0.0"
docker push "$REPO/inventory-360:1.0.0"

.venv\Scripts\snow spcs image-repository list-images INV360_IMAGES --database INVENTORY_360_DB --schema APP -c tbsljyv-rm91730
```

If login fails with a browser-OAuth connection, use `docker login $REPO.Split('/')[0] -u MohanaAshok`
with a PAT as the password, or a key-pair connection.

## 6. Upload the service specification

```sql
CREATE STAGE IF NOT EXISTS INVENTORY_360_DB.APP.SERVICE_SPECS DIRECTORY = (ENABLE = TRUE);
```

```powershell
.venv\Scripts\snow stage copy service/app_service_spec.yaml @INVENTORY_360_DB.APP.SERVICE_SPECS --overwrite -c tbsljyv-rm91730
```

## 7. Create the compute pool — **starts billing**

```sql
CREATE COMPUTE POOL IF NOT EXISTS INV360_APP_POOL
  MIN_NODES = 1 MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS
  AUTO_RESUME = TRUE AUTO_SUSPEND_SECS = 3600;
DESCRIBE COMPUTE POOL INV360_APP_POOL;     -- wait for IDLE or ACTIVE
```

`CPU_X64_XS` (1 vCPU, 6 GiB) is the smallest family and is sufficient for this app.

## 8. Deploy the service — **billing continues while running**

```sql
CREATE SERVICE IF NOT EXISTS INVENTORY_360_DB.APP.INVENTORY_360_SVC
  IN COMPUTE POOL INV360_APP_POOL
  FROM @INVENTORY_360_DB.APP.SERVICE_SPECS
  SPECIFICATION_FILE = 'app_service_spec.yaml'
  QUERY_WAREHOUSE = INV360_WH
  MIN_INSTANCES = 1 MAX_INSTANCES = 1;

SELECT SYSTEM$GET_SERVICE_STATUS('INVENTORY_360_DB.APP.INVENTORY_360_SVC');   -- READY
SELECT SYSTEM$GET_SERVICE_LOGS('INVENTORY_360_DB.APP.INVENTORY_360_SVC', 0, 'inventory-360', 100);
```

The service runs as its **owner role** (here `ACCOUNTADMIN`) via the injected OAuth token. To run with a
least-privilege owner, create the service as `INV360_ADMIN` after the grants in section 4 of
`sql/deployment/03_spcs_container_service.sql`.

## 9. Configure and use the endpoint

The spec declares one public endpoint, `app`, on port 8501:

```sql
SHOW ENDPOINTS IN SERVICE INVENTORY_360_DB.APP.INVENTORY_360_SVC;   -- ingress_url
```

Endpoint provisioning can take a few minutes (`ingress_url` shows *Endpoints provisioning in progress*).
Grant access to consumers:

```sql
GRANT USAGE ON DATABASE INVENTORY_360_DB TO ROLE INV360_VIEWER;
GRANT USAGE ON SCHEMA INVENTORY_360_DB.APP TO ROLE INV360_VIEWER;
GRANT SERVICE ROLE INVENTORY_360_DB.APP.INVENTORY_360_SVC!ALL_ENDPOINTS_USAGE TO ROLE INV360_VIEWER;
```

## 10. Test the deployed application

1. Open `https://<ingress_url>` and sign in with Snowflake.
2. Check every page loads; confirm the sidebar shows data as of the latest snapshot date.
3. `SHOW SERVICE CONTAINERS IN SERVICE INVENTORY_360_DB.APP.INVENTORY_360_SVC;` → status `READY`.
4. Review logs with `SYSTEM$GET_SERVICE_LOGS` for connection errors.

## 11. Update after a code change

```powershell
docker build --platform linux/amd64 -t inventory-360:1.0.1 .
docker tag inventory-360:1.0.1 "$REPO/inventory-360:1.0.1"
docker push "$REPO/inventory-360:1.0.1"
# edit the image tag in service/app_service_spec.yaml, re-upload it (step 6), then:
```

```sql
ALTER SERVICE INVENTORY_360_DB.APP.INVENTORY_360_SVC
  FROM @INVENTORY_360_DB.APP.SERVICE_SPECS SPECIFICATION_FILE = 'app_service_spec.yaml';
```

Use `ALTER SERVICE`, not drop/recreate — recreating changes the ingress URL.

## 12. Suspend or remove resources

Stop paying for compute (keeps everything for later):

```sql
ALTER SERVICE INVENTORY_360_DB.APP.INVENTORY_360_SVC SUSPEND;
ALTER COMPUTE POOL INV360_APP_POOL STOP ALL;
ALTER COMPUTE POOL INV360_APP_POOL SUSPEND;
SHOW COMPUTE POOLS LIKE 'INV360_APP_POOL';   -- state SUSPENDED
```

Resume: `ALTER COMPUTE POOL INV360_APP_POOL RESUME; ALTER SERVICE INVENTORY_360_DB.APP.INVENTORY_360_SVC RESUME;`

Remove permanently:

```sql
DROP SERVICE IF EXISTS INVENTORY_360_DB.APP.INVENTORY_360_SVC;
DROP COMPUTE POOL IF EXISTS INV360_APP_POOL;
DROP IMAGE REPOSITORY IF EXISTS INVENTORY_360_DB.APP.INV360_IMAGES;   -- deletes images
DROP STAGE IF EXISTS INVENTORY_360_DB.APP.SERVICE_SPECS;
```

Local cleanup: `docker rm -f inv360; docker rmi inventory-360:1.0.0`.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `exec /app/entrypoint.sh: no such file` | CRLF line endings — the Dockerfile strips them; `.gitattributes` forces LF |
| Container exits: *no Snowflake credentials* | `.env` missing values or not passed with `--env-file` |
| `JWT token is invalid` | Public key not set on the user, or wrong key mounted |
| PAT rejected | User not subject to a network policy (default PAT requirement) |
| `Role ... is not granted` | Grant `INV360_PLANNER` to the user or change `SNOWFLAKE_ROLE` |
| Service stuck `PENDING` | Pool not `IDLE/ACTIVE`, or resource requests exceed the node size |
| `Image not found` | Path in spec must be `/inventory_360_db/app/inv360_images/inventory-360:<tag>` (lower case, leading slash) |
| Readiness probe failing | Port mismatch — `PORT`, `readinessProbe.port` and `endpoints.port` must all be 8501 |
| `Unauthorized` on push | Re-run `snow spcs image-registry login` |
| Blank page / websocket errors behind ingress | XSRF/CORS are disabled in the image for the SPCS proxy; check browser console |
