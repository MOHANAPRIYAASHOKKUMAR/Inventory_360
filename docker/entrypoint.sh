#!/bin/sh
# Container startup for Inventory 360.
set -eu

PORT="${PORT:-8501}"

if [ -f "${SNOWFLAKE_TOKEN_PATH:-/snowflake/session/token}" ] && [ -n "${SNOWFLAKE_HOST:-}" ]; then
  mode="spcs (service OAuth token)"
elif [ -n "${SNOWFLAKE_ACCOUNT:-}" ] && [ -n "${SNOWFLAKE_USER:-}" ]; then
  mode="env (${SNOWFLAKE_USER}@${SNOWFLAKE_ACCOUNT})"
else
  echo "ERROR: no Snowflake credentials. Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and" >&2
  echo "       SNOWFLAKE_PASSWORD (password/PAT) or SNOWFLAKE_PRIVATE_KEY_FILE." >&2
  exit 1
fi

echo "Inventory 360 starting on port ${PORT}; Snowflake auth: ${mode}; warehouse ${INV360_WAREHOUSE}"
exec streamlit run /app/streamlit_app/streamlit_app.py --server.port "${PORT}"
