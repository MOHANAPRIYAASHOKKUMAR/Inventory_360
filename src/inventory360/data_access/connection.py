"""Snowflake connectivity for the Streamlit app.

The connection mode is chosen from the environment, in this order:

0. ``callers`` - Streamlit in Snowflake (container runtime) with a viewer token: every
   read and write runs with **restricted caller's rights** as the viewer's default
   role, so Snowflake RBAC (and the CALLER grants on the app owner) enforce access.
   The connection is session-scoped and must be opened at the top of the entry
   script (``init_session``) while the 2-minute viewer token is valid.
1. ``spcs``  - self-hosted Snowpark Container Services acting as its own service role. Only
   with ``INV360_ALLOW_SERVICE_IDENTITY=true``; inside Snowflake without a viewer token the
   mode is ``denied`` (fail closed, never the app owner's identity).
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
CALLER_TOKEN_HEADER = "Sf-Context-Current-User-Token"

# Snowflake error codes meaning "no privilege / object not visible to this role"
_DENIED_CODES = {2003, 3001, 3041, 3540}
_DENIED_TEXT = ("insufficient privileges", "does not exist or not authorized", "not authorized")
DENIED_MESSAGE = ("You don't have access to this information. "
                  "Contact the Inventory 360 administrator to request access.")


class DataAccessDenied(PermissionError):
    """Snowflake refused a statement for the current role (caller's rights)."""

    def __init__(self, detail: str):
        super().__init__(DENIED_MESSAGE)
        self.detail = detail


def _callers_rights_available() -> bool:
    if os.getenv("INV360_CALLERS_RIGHTS", "true").lower() in {"0", "false", "no"}:
        return False
    if not (os.getenv("SNOWFLAKE_HOST") and SPCS_TOKEN_PATH.is_file()):
        return False
    try:
        return CALLER_TOKEN_HEADER in st.context.headers
    except Exception:  # noqa: BLE001 - no script context (tests, threads)
        return False


def _in_snowflake() -> bool:
    return bool(os.getenv("SNOWFLAKE_HOST"))


def _service_identity_allowed() -> bool:
    # Self-hosted SPCS service that should act as its own service role (opt-in only)
    return os.getenv("INV360_ALLOW_SERVICE_IDENTITY", "").lower() in {"1", "true", "yes"}


def connection_mode() -> str:
    """Pick the connection mode. Inside Snowflake this fails closed: without the viewer's
    caller's-rights token the app never falls back to the owner's identity."""
    if _in_snowflake():
        if _callers_rights_available():
            return "callers"
        if SPCS_TOKEN_PATH.is_file() and _service_identity_allowed():
            return "spcs"
        return "denied"
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
        # Least privilege by default: read-only unless the operator asks for a write role
        "role": os.getenv("SNOWFLAKE_ROLE", "INV360_VIEWER"),
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


def _callers_connection():
    # st.connection caches caller's-rights connections per session (scope="session"),
    # so every call in a session returns the connection opened by init_session().
    return st.connection("snowflake-callers-rights", **_context())


def get_connection():
    mode = connection_mode()
    if mode == "denied":
        raise DataAccessDenied("Viewer identity unavailable: caller's-rights token missing")
    if mode == "callers":
        return _callers_connection()
    if mode == "spcs":
        return _spcs_connection()
    if mode == "named":
        # Local development: named entry from ~/.snowflake/connections.toml
        return st.connection(os.environ["SNOWFLAKE_DEFAULT_CONNECTION_NAME"], type="snowflake")
    if mode == "env":
        return _env_connection()
    # Streamlit in Snowflake: embedded session identity
    return st.connection("snowflake")


def init_session() -> dict:
    """Open this session's connection and resolve who is using the app.

    Call once at the top of the entry script. Secondary roles are switched off so the
    session's privileges are exactly the primary (default) role's, matching the tier.
    Returns ``{"mode", "role", "user", "error"}`` and caches it in session state.
    """
    if "inv360_identity" in st.session_state:
        return st.session_state["inv360_identity"]
    mode = connection_mode()
    identity = {"mode": mode, "role": None, "user": None, "error": None}
    if mode == "denied":
        identity["error"] = "identity_unavailable"
        st.session_state["inv360_identity"] = identity
        return identity
    try:
        conn = get_connection()
        cur = conn.raw_connection.cursor()
        try:
            if mode == "callers":
                cur.execute("use secondary roles none")
            cur.execute("select current_role(), current_user()")
            role, user = cur.fetchone()
        finally:
            cur.close()
        identity.update(role=str(role or "").upper() or None, user=user)
    except Exception as exc:  # noqa: BLE001 - surfaced as an access message, fails closed
        identity["error"] = str(exc)
    st.session_state["inv360_identity"] = identity
    return identity


def is_denied(exc: BaseException) -> bool:
    if isinstance(exc, DataAccessDenied):
        return True
    errno = getattr(exc, "errno", None)
    text = str(exc).lower()
    return errno in _DENIED_CODES or any(t in text for t in _DENIED_TEXT)


def run_query(sql: str, params: list | None = None, ttl: int = 600) -> pd.DataFrame:
    """Execute a read query (qmark-parameterised) and return lower-cased columns.

    Results are cached by ``st.connection`` per (SQL, params); caller's-rights
    connections are session-scoped, so one viewer's results never reach another.
    """
    try:
        df = get_connection().query(sql, params=params, ttl=ttl, show_spinner=False)
    except Exception as exc:
        if is_denied(exc):
            raise DataAccessDenied(str(exc)) from exc
        raise
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
    """Execute a write statement (uncached, autocommit) on this session's connection."""
    cur = get_connection().raw_connection.cursor()
    try:
        cur.execute(sql, params)
    except Exception as exc:
        if is_denied(exc):
            raise DataAccessDenied(str(exc)) from exc
        raise
    finally:
        cur.close()
