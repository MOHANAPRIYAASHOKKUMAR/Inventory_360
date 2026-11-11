# syntax=docker/dockerfile:1
# Inventory 360 - Streamlit container for local Docker and Snowpark Container Services.
# SPCS runs linux/amd64 on CPU_X64 / GEN_X64 pools: always build with --platform linux/amd64.

FROM python:3.11-slim-bookworm AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r /tmp/requirements.txt

FROM python:3.11-slim-bookworm AS runtime
ARG APP_VERSION=1.0.0
LABEL org.opencontainers.image.title="inventory-360" \
      org.opencontainers.image.description="Inventory 360 - Sample Retail Group supply chain intelligence" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8501 \
    # Streamlit server configuration for a headless container behind the SPCS ingress proxy
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_RUN_ON_SAVE=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_CLIENT_TOOLBAR_MODE=viewer \
    # Snowflake object defaults (override at runtime)
    INV360_DATABASE=INVENTORY_360_DB \
    INV360_WAREHOUSE=INV360_WH

COPY --from=build /opt/venv /opt/venv
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser streamlit_app/ /app/streamlit_app/
COPY --chown=appuser:appuser docker/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

USER appuser
# Run from the app folder so .streamlit/config.toml (theme) is picked up
WORKDIR /app/streamlit_app
EXPOSE 8501

# Streamlit's built-in health endpoint returns 200 "ok" once the server is up
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8501\")}/_stcore/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
