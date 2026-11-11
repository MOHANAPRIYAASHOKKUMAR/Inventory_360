"""Data-quality summary shared by the page footer and the governance page."""
from __future__ import annotations

from datetime import date

import streamlit as st

from components.layout import rag_badge
from inventory360.business_logic import data_quality as dq
from inventory360.data_access import queries


def run_checks() -> list[dq.Check]:
    """All live checks. Each query is cached for 10 minutes on the session's connection."""
    checks = dq.freshness(queries.dq_latest_dates(), date.today())
    nulls, dupes = queries.dq_key_checks()
    checks += dq.key_nulls(nulls) + dq.duplicates(dupes)
    for source in queries.DQ_SOURCES:
        checks += dq.daily_volume(queries.dq_daily_counts(source), source)
    checks += dq.rebuilt(queries.dq_last_altered())
    return checks


def footer() -> None:
    """Business footer on every page: reporting period, data as-of, freshness and DQ status."""
    f, as_of = st.session_state.get("gf_current"), st.session_state.get("gf_as_of")
    try:
        checks = run_checks()
    except Exception:  # noqa: BLE001 - the footer must never break a page
        checks = []
    fresh = [c for c in checks if c.area == "Freshness"]
    st.divider()
    with st.container(horizontal=True, gap="small", vertical_alignment="center"):
        if f is not None:
            st.caption(f"Reporting period {f.start:%d %b %Y} – {f.end:%d %b %Y}")
        if as_of is not None:
            st.caption(f"· Data as of {as_of:%d %b %Y}")
        if checks:
            rag_badge(dq.overall(fresh), "data freshness")
            rag_badge(dq.overall([c for c in checks if c.area != "Freshness"]), "data quality checks")
        else:
            st.caption("· Data quality status unavailable")
