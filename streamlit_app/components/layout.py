"""Page scaffolding: headers, KPI cards and shared sidebar filters."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from inventory360.utils.formatting import pct_change

FILTER_WAREHOUSES = "flt_warehouses"
FILTER_CATEGORIES = "flt_categories"


def page_header(title: str, subtitle: str, icon: str, as_of=None) -> None:
    with st.container(horizontal=True, vertical_alignment="bottom"):
        with st.container():
            st.title(title, anchor=False, icon=icon) if _title_supports_icon() else st.title(f"{icon} {title}", anchor=False)
            st.caption(subtitle)
        if as_of is not None:
            st.badge(f"Data as of {pd.Timestamp(as_of):%d %b %Y}", icon=":material/schedule:", color="gray")


def _title_supports_icon() -> bool:
    import inspect
    return "icon" in inspect.signature(st.title).parameters


def kpi(label: str, value: str, current=None, previous=None, *, inverse: bool = False,
        help: str | None = None, spark=None, as_points: bool = False, desc: str = "vs prior period") -> None:
    """Bordered metric card with a period-over-period delta.

    ``inverse=True`` flags metrics where a decrease is good (e.g. lost sales).
    ``as_points=True`` shows the delta in percentage points (for ratios).
    """
    delta = None
    if current is not None and previous is not None:
        if as_points:
            delta = round((current - previous) * 100, 2)
            delta = f"{delta:+.2f} pts" if delta else 0
        else:
            change = pct_change(current, previous)
            delta = f"{change * 100:+.1f}%" if change else (0 if change == 0 else None)
    st.metric(
        label,
        value,
        delta=delta,
        delta_color="inverse" if inverse else "normal",
        delta_description=desc if delta is not None else None,
        help=help,
        border=True,
        chart_data=list(spark) if spark is not None else None,
        chart_type="area",
        height="stretch",
    )


def sidebar_filters(warehouses: pd.DataFrame, categories: list[str]) -> None:
    """Global site / category filters persisted in session state across pages."""
    with st.sidebar:
        st.subheader("Filters", anchor=False)
        wh_labels = dict(zip(warehouses["warehouse_code"], warehouses["warehouse_name"]))
        st.multiselect(
            "Distribution sites",
            options=list(wh_labels),
            format_func=lambda c: f"{c} · {wh_labels[c]}",
            key=FILTER_WAREHOUSES,
            placeholder="All sites",
        )
        st.multiselect("Categories", options=categories, key=FILTER_CATEGORIES, placeholder="All categories")
        st.button("Clear filters", icon=":material/filter_alt_off:", on_click=_clear_filters, width="stretch")


def _clear_filters() -> None:
    st.session_state[FILTER_WAREHOUSES] = []
    st.session_state[FILTER_CATEGORIES] = []


def apply_filters(df: pd.DataFrame, warehouse_col: str | None = "warehouse_code",
                  category_col: str | None = "category") -> pd.DataFrame:
    out = df
    whs = st.session_state.get(FILTER_WAREHOUSES) or []
    cats = st.session_state.get(FILTER_CATEGORIES) or []
    if whs and warehouse_col and warehouse_col in out.columns:
        out = out[out[warehouse_col].isin(whs)]
    if cats and category_col and category_col in out.columns:
        out = out[out[category_col].isin(cats)]
    return out


def active_filter_caption() -> None:
    whs = st.session_state.get(FILTER_WAREHOUSES) or []
    cats = st.session_state.get(FILTER_CATEGORIES) or []
    if whs or cats:
        parts = []
        if whs:
            parts.append(f"{len(whs)} site(s)")
        if cats:
            parts.append(", ".join(cats))
        st.caption(f":material/filter_alt: Filtered to {' · '.join(parts)}")
