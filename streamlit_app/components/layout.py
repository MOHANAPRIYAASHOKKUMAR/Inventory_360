"""Page scaffolding: header, filter scope, KPI cards, RAG chips, tables and CSV export."""
from __future__ import annotations

import re
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import date

import pandas as pd
import streamlit as st

from inventory360.business_logic.exceptions import AMBER, GREEN, NA, RED
from inventory360.business_logic.kpi_framework import KPIS, NO_DATA, NO_TARGET, KpiResult
from inventory360.data_access.filters import GlobalFilters, applicability
from inventory360.utils.formatting import fmt_days, fmt_gbp, fmt_int, fmt_pct, pct_change

RAG_BADGE = {GREEN: ("green", ":material/check_circle:"), AMBER: ("orange", ":material/error:"),
             RED: ("red", ":material/cancel:"), NA: ("gray", ":material/remove:"),
             NO_DATA: ("gray", ":material/remove:"), NO_TARGET: ("gray", ":material/flag:")}
RAG_TEXT = {GREEN: "#15803D", AMBER: "#B45309", RED: "#B42318", NA: "#64748B"}
STATUS_WORD = {GREEN: "On target", AMBER: "Watch", RED: "Off target", NA: "No data", NO_DATA: "No data",
               NO_TARGET: "No target"}


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
    """Active-filter chips plus one line stating which global filters this page honours."""
    from components import filters as _filters  # local import: filters is a sibling component

    _filters.chips()
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
    """Status chip. The status is always spelled out (never colour alone)."""
    colour, icon = RAG_BADGE.get(status, RAG_BADGE[NA])
    word = STATUS_WORD.get(status, status)
    st.badge(f"{word} · {text}" if text else word, icon=icon, color=colour)


def _missing(v) -> bool:
    return v is None or pd.isna(v)


def _delta(current, previous, *, points: bool) -> tuple[str | None, bool]:
    """Delta text and whether the change is within the flat band (0.1 pt / 0.5 %)."""
    if _missing(current) or _missing(previous):
        return None, False
    if points:
        diff = current - previous
        return f"{diff * 100:+.1f} pts", abs(diff) < 0.001
    change = pct_change(current, previous)
    if change is None:
        return None, False
    return f"{change * 100:+.1f}%", abs(change) < 0.005


def _formatter(value: str, fmt, points: bool):
    """Formatter for the comparison value, inferred from the displayed value when not given."""
    if callable(fmt):
        return fmt
    unit = fmt or ("pct" if points or value.endswith("%") else "gbp" if "£" in value else
                   "days" if value.endswith("days") else "x" if value.endswith("x") else "int")
    return {"pct": fmt_pct, "gbp": fmt_gbp, "days": fmt_days, "x": lambda v: f"{v:.1f}x",
            "int": fmt_int, "ratio": lambda v: f"{v:.1f}x", "num": fmt_int}.get(unit, fmt_int)


def _spark(spark) -> list | None:
    """Sparkline only when it says something: >= 4 points with some variance."""
    if spark is None:
        return None
    values = [v for v in list(spark) if not _missing(v)]
    return values if len(values) >= 4 and max(values) != min(values) else None


def kpi(label: str, value: str, *, current=None, previous=None, inverse: bool = False, points: bool = False,
        status: str | None = None, status_text: str | None = None, help: str | None = None, spark=None,
        desc: str = "vs prior period", key: str | None = None, fmt=None) -> None:
    """Standard KPI card used on every page.

    Order: title (help icon = definition) · main value · change vs comparison with a
    trend arrow coloured by whether the move is favourable · comparison value · status
    chip (icon + words) · optional sparkline. ``inverse`` marks KPIs where a fall is
    good; ``points`` shows ratio deltas in percentage points; ``key`` pulls the KPI
    definition from the registry.
    """
    spec = KPIS.get(key) if key else None
    if spec and help is None:
        help = spec.definition
    delta, flat = _delta(current, previous, points=points)
    with st.container(border=True, height="stretch", gap="small"):
        st.metric(
            label, value, delta=delta,
            delta_color="off" if flat else ("inverse" if inverse else "normal"),
            delta_arrow="off" if flat else "auto",
            delta_description=(desc + (" · flat" if flat else "")) if delta else None, help=help,
            chart_data=_spark(spark), chart_type="area",
        )
        if not _missing(previous) and value != "–":
            st.caption(f"Comparison: {_formatter(value, fmt, points)(previous)}")
        if status:
            rag_badge(status, status_text)
        elif value == "–":
            rag_badge(NO_DATA, "nothing in the current filters")


def kpi_result(r: KpiResult, *, label: str | None = None, spark=None, desc: str = "vs prior period",
               status_text: str | None = None) -> None:
    """KPI card from a framework result (value/target formatting from the spec unit)."""
    s = r.spec
    fmt = {"pct": fmt_pct, "gbp": fmt_gbp, "days": fmt_days, "ratio": lambda v: f"{v:.1f}x", "num": fmt_int}[s.unit]
    value = "–" if r.value is None else fmt(r.value)
    if status_text is None and r.target is not None:
        status_text = f"Target {'≥' if s.higher_is_better else '≤'} {fmt(r.target)}"
    kpi(label or s.label, value, current=r.value, previous=r.previous, inverse=not s.higher_is_better,
        points=s.unit == "pct", status=None if r.status == NO_DATA and r.value is None else r.status,
        status_text=status_text, help=s.definition, spark=spark, desc=desc, fmt=fmt)


def kpi_grid(n: int, per_row: int = 4):
    """Columns for ``n`` KPI cards, wrapping after ``per_row`` (keeps rows equal height)."""
    cols = []
    for start in range(0, n, per_row):
        cols += st.columns(per_row)[: min(per_row, n - start)]
    return cols


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
