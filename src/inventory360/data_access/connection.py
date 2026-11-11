"""Snowflake connectivity for the Streamlit app.

The connection mode is chosen from the environment, in this order:

1. ``spcs``  - running in Snowpark Container Services: Snowflake mounts an OAuth
   token at ``/snowflake/session/token`` and sets ``SNOWFLAKE_HOST`` /
   ``SNOWFLAKE_ACCOUNT``. No secrets are stored in the image.
2. ``named`` - ``SNOWFLAKE_DEFAULT_CONNECTION_NAME`` selects an entry from
   ``~/.snowflake/connections.toml`` (local development).
3. ``env``   - ``SNOWFLAKE_ACCOUNT`` + ``SNOWFLAKE_USER`` with ``SNOWFLAKE_PASSWORD``
   (password or programmatic access token) or ``SNOWFLAKE_PRIVATE_KEY_FILE``
   (local Docker container).
4. ``sis``   - Streamlit in Snowflake: embedded session identity.
"""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from inventory360.utils.config import DATABASE, WAREHOUSE

SPCS_TOKEN_PATH = Path(os.getenv("SNOWFLAKE_TOKEN_PATH", "/snowflake/session/token"))


def connection_mode() -> str:
    if SPCS_TOKEN_PATH.is_file() and os.getenv("SNOWFLAKE_HOST"):
        return "spcs"
    if os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME"):
        return "named"
    if os.getenv("SNOWFLAKE_ACCOUNT") and os.getenv("SNOWFLAKE_USER"):
        return "env"
    return "sis"


def _context() -> dict:
    return {
        "warehouse": WAREHOUSE,
        "database": DATABASE,
        "schema": os.getenv("INV360_SCHEMA", "MARTS"),
        # Long-lived dashboard sessions: keep the connection from idling out
        "client_session_keep_alive": True,
    }


@st.cache_resource(show_spinner=False)
def _spcs_connection():
    # Token is read once at connect time; an established session does not expire
    # with the token, so later file rotations do not need a new connection.
    return st.connection(
        "spcs", type="snowflake",
        host=os.environ["SNOWFLAKE_HOST"],
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        authenticator="oauth",
        token=SPCS_TOKEN_PATH.read_text().strip(),
        **_context(),
    )


@st.cache_resource(show_spinner=False)
def _env_connection():
    params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.getenv("SNOWFLAKE_ROLE", "INV360_PLANNER"),
        **_context(),
    }
    if os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE"):
        params.update(authenticator="SNOWFLAKE_JWT", private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"])
        if os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE_PWD"):
            params["private_key_file_pwd"] = os.environ["SNOWFLAKE_PRIVATE_KEY_FILE_PWD"]
    elif os.getenv("SNOWFLAKE_PASSWORD"):
        # Accepts a password or a programmatic access token (PAT)
        params["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    else:
        raise RuntimeError("Set SNOWFLAKE_PASSWORD (password or PAT) or SNOWFLAKE_PRIVATE_KEY_FILE")
    return st.connection("env", type="snowflake", **params)


def get_connection():
    mode = connection_mode()
    if mode == "spcs":
        return _spcs_connection()
    if mode == "named":
        # Local development: named entry from ~/.snowflake/connections.toml
        return st.connection(os.environ["SNOWFLAKE_DEFAULT_CONNECTION_NAME"], type="snowflake")
    if mode == "env":
        return _env_connection()
    # Streamlit in Snowflake: embedded session identity
    return st.connection("snowflake")


def run_query(sql: str, params: list | None = None, ttl: int = 600) -> pd.DataFrame:
    """Execute a read query (qmark-parameterised) and return lower-cased columns."""
    df = get_connection().query(sql, params=params, ttl=ttl)
    df.columns = [c.lower() for c in df.columns]
    return _coerce_decimals(df)


def _coerce_decimals(df: pd.DataFrame) -> pd.DataFrame:
    """Snowflake NUMBER(p, s) can arrive as decimal.Decimal objects; use floats for analytics."""
    for col in df.select_dtypes(include="object").columns:
        sample = df[col].dropna()
        if not sample.empty and isinstance(sample.iloc[0], Decimal):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df


def execute(sql: str, params: list | None = None) -> None:
    """Execute a write statement through the Snowpark session (uncached)."""
    get_connection().session().sql(sql, params=params).collect()
