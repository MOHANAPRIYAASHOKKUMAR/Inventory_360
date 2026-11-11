"""Page scaffolding: header, filter scope, KPI cards, RAG chips, tables and CSV export."""
from __future__ import annotations

import re
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import date

import pandas as pd
import streamlit as st

from inventory360.business_logic.exceptions import AMBER, GREEN, NA, RED
from inventory360.data_access.filters import GlobalFilters, applicability
from inventory360.utils.formatting import pct_change

RAG_BADGE = {GREEN: ("green", ":material/check_circle:"), AMBER: ("orange", ":material/error:"),
             RED: ("red", ":material/cancel:"), NA: ("gray", ":material/remove:")}
RAG_TEXT = {GREEN: "#15803D", AMBER: "#B45309", RED: "#B42318", NA: "#64748B"}


def page_header(title: str, subtitle: str, f: GlobalFilters | None = None, as_of=None) -> None:
    with st.container(horizontal=True, vertical_alignment="bottom"):
        with st.container():
            st.title(title, anchor=False)
            st.caption(subtitle)
        with st.container(horizontal=True, horizontal_alignment="right", width="content"):
            if f is not None:
                st.badge(f"{f.start:%d %b %Y} – {f.end:%d %b %Y}", icon=":material/date_range:", color="blue")
            if as_of is not None:
                st.badge(f"Data as of {pd.Timestamp(as_of):%d %b %Y}", icon=":material/schedule:", color="gray")


def filter_scope(f: GlobalFilters, columns: Mapping[str, str], *, use_date: bool = True, note: str | None = None) -> None:
    """One-line statement of which global filters this page honours."""
    applied, ignored = applicability(f, columns, use_date=use_date)
    parts = []
    if applied:
        parts.append(f":material/filter_alt: Filtered by {', '.join(applied)}")
    if not use_date:
        parts.append("snapshot view (date range not applicable)")
    if ignored:
        parts.append(f"not applicable here: {', '.join(ignored)}")
    if note:
        parts.append(note)
    if parts:
        st.caption(" · ".join(parts))


def rag_badge(status: str, text: str | None = None) -> None:
    colour, icon = RAG_BADGE.get(status, RAG_BADGE[NA])
    st.badge(text or status, icon=icon, color=colour)


def _delta(current, previous, *, points: bool) -> str | None:
    if current is None or previous is None or pd.isna(current) or pd.isna(previous):
        return None
    if points:
        return f"{(current - previous) * 100:+.1f} pts"
    change = pct_change(current, previous)
    return None if change is None else f"{change * 100:+.1f}%"


def kpi(label: str, value: str, *, current=None, previous=None, inverse: bool = False, points: bool = False,
        status: str | None = None, status_text: str | None = None, help: str | None = None, spark=None,
        desc: str = "vs prior period") -> None:
    """Bordered KPI card: value, period-over-period delta, optional sparkline and RAG chip.

    ``inverse`` marks KPIs where a fall is good; ``points`` shows ratio deltas in percentage points.
    """
    delta = _delta(current, previous, points=points)
    with st.container(border=True, height="stretch", gap="small"):
        st.metric(
            label, value, delta=delta, delta_color="inverse" if inverse else "normal",
            delta_description=desc if delta else None, help=help,
            chart_data=list(spark) if spark is not None and len(spark) > 1 else None, chart_type="area",
        )
        if status:
            rag_badge(status, status_text)


@contextmanager
def section(title: str, caption: str | None = None, *, height="content"):
    with st.container(border=True, height=height):
        st.subheader(title, anchor=False)
        if caption:
            st.caption(caption)
        yield


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def download(df: pd.DataFrame, name: str, *, label: str = "Download CSV", key: str | None = None) -> None:
    """CSV export of exactly the rows shown (UTF-8 with BOM so Excel renders £ correctly)."""
    st.download_button(
        label, df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"inventory360_{_slug(name)}_{date.today():%Y%m%d}.csv", mime="text/csv",
        icon=":material/download:", key=key or f"dl_{_slug(name)}", on_click="ignore",
    )


def _style_rag(df: pd.DataFrame, rag_cols: list[str]):
    def colour(v):
        c = RAG_TEXT.get(v)
        return f"color: {c}; font-weight: 600" if c else ""
    return df.style.map(colour, subset=[c for c in rag_cols if c in df.columns])


def table(df: pd.DataFrame, *, key: str, column_config: dict | None = None, height: int | str = "auto",
          rag_cols: list[str] | None = None, select: bool = True, alt: str, csv_name: str | None = None,
          columns: list[str] | None = None) -> pd.Series | None:
    """Detail table with optional RAG colouring, CSV export and single-row drill-down.

    Returns the selected row (from ``df``) or None.
    """
    view = df[columns] if columns else df
    view = view.reset_index(drop=True)
    data = _style_rag(view, rag_cols) if rag_cols else view
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"{len(view):,} rows" + (" · select a row to drill down" if select else ""))
        if csv_name:
            with st.container(horizontal=True, horizontal_alignment="right"):
                download(view, csv_name, key=f"dl_{key}")
    event = st.dataframe(
        data, hide_index=True, height=height, key=key, alt=alt, column_config=column_config,
        on_select="rerun" if select else "ignore", selection_mode="single-row",
    )
    if select and event and event.selection and event.selection.rows:
        return df.reset_index(drop=True).iloc[event.selection.rows[0]]
    return None


# Reusable column formats (GBP always shown with £ and thousands separators)
def gbp(label: str, decimals: int = 0, **kw):
    return st.column_config.NumberColumn(label, format=f"£%,.{decimals}f", **kw)


def pct(label: str, **kw):
    return st.column_config.NumberColumn(label, format="percent", **kw)


def num(label: str, decimals: int = 0, suffix: str = "", **kw):
    return st.column_config.NumberColumn(label, format=f"%,.{decimals}f{suffix}", **kw)


def day(label: str, **kw):
    return st.column_config.DateColumn(label, format="DD MMM YYYY", **kw)
