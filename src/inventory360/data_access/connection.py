"""Snowflake connectivity for the Streamlit app.

Inside Streamlit in Snowflake the platform provides the session for
``st.connection("snowflake")``; locally ``SNOWFLAKE_DEFAULT_CONNECTION_NAME``
selects an entry from ``~/.snowflake/connections.toml``.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pandas as pd
import streamlit as st


def get_connection():
    name = os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME")
    if name:
        # Local development: named entry from ~/.snowflake/connections.toml
        return st.connection(name, type="snowflake")
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
