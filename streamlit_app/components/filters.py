"""Global sidebar filters shared by every page.

Widgets live in the navigation script, so their session-state keys persist
while the user moves between pages. Cascading lists (product depends on
category / supplier, customer depends on warehouse) are pruned before render
so a stale selection never raises.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from inventory360.data_access.filters import GlobalFilters

K_DATES, K_PRESET = "gf_dates", "gf_preset"
K_WH, K_CAT, K_SUP, K_SKU, K_CUST = "gf_warehouses", "gf_categories", "gf_suppliers", "gf_products", "gf_customers"
PRESETS = {"4W": 28, "13W": 91, "26W": 182, "52W": 364, "YTD": None}
DEFAULT_PRESET = "13W"


def _preset_range(preset: str, lo: date, hi: date) -> tuple[date, date]:
    if preset == "YTD":  # UK financial year starting 1 April
        fy_start = date(hi.year if hi.month >= 4 else hi.year - 1, 4, 1)
        return max(fy_start, lo), hi
    return max(hi - timedelta(days=PRESETS[preset] - 1), lo), hi


def _prune(key: str, options) -> None:
    allowed = set(options)
    if key in st.session_state:
        st.session_state[key] = [v for v in st.session_state[key] if v in allowed]


def _on_preset(lo: date, hi: date) -> None:
    preset = st.session_state.get(K_PRESET)
    if preset:
        st.session_state[K_DATES] = _preset_range(preset, lo, hi)


def _on_dates() -> None:
    st.session_state[K_PRESET] = None


def _reset(lo: date, hi: date) -> None:
    for key in (K_WH, K_CAT, K_SUP, K_SKU, K_CUST):
        st.session_state[key] = []
    st.session_state[K_PRESET] = DEFAULT_PRESET
    st.session_state[K_DATES] = _preset_range(DEFAULT_PRESET, lo, hi)


def render(warehouses: pd.DataFrame, products: pd.DataFrame, suppliers: pd.DataFrame,
           customers: pd.DataFrame, lo: date, hi: date) -> GlobalFilters:
    if K_DATES not in st.session_state:
        st.session_state[K_PRESET] = DEFAULT_PRESET
        st.session_state[K_DATES] = _preset_range(DEFAULT_PRESET, lo, hi)

    wh_names = dict(zip(warehouses["warehouse_code"], warehouses["warehouse_name"]))
    sup_names = dict(zip(suppliers["supplier_id"], suppliers["supplier_name"]))

    with st.sidebar:
        st.subheader("Filters", anchor=False)
        st.segmented_control("Period", list(PRESETS), key=K_PRESET, on_change=_on_preset, args=(lo, hi),
                             width="stretch")
        st.date_input("Date range", key=K_DATES, min_value=lo, max_value=hi, format="DD/MM/YYYY",
                      on_change=_on_dates)

        st.multiselect("Warehouse", list(wh_names), format_func=lambda c: f"{c} · {wh_names[c]}",
                       key=K_WH, placeholder="All warehouses")
        st.multiselect("Product category", sorted(products["category"].unique()), key=K_CAT,
                       placeholder="All categories")
        st.multiselect("Supplier", sorted(sup_names, key=sup_names.get), format_func=sup_names.get,
                       key=K_SUP, placeholder="All suppliers")

        prod = products
        if st.session_state.get(K_CAT):
            prod = prod[prod["category"].isin(st.session_state[K_CAT])]
        if st.session_state.get(K_SUP):
            prod = prod[prod["supplier_id"].isin(st.session_state[K_SUP])]
        sku_names = dict(zip(prod["sku"], prod["product_name"]))
        _prune(K_SKU, sku_names)
        st.multiselect("Product", sorted(sku_names, key=sku_names.get), format_func=lambda s: f"{sku_names[s]} ({s})",
                       key=K_SKU, placeholder=f"All products ({len(sku_names)})")

        cust = customers
        if st.session_state.get(K_WH):
            cust = cust[cust["warehouse_code"].isin(st.session_state[K_WH])]
        cust_names = dict(zip(cust["customer_id"], cust["customer_name"]))
        _prune(K_CUST, cust_names)
        st.multiselect("Customer", sorted(cust_names, key=cust_names.get), format_func=cust_names.get,
                       key=K_CUST, placeholder=f"All customers ({len(cust_names)})")

        st.button("Reset filters", icon=":material/filter_alt_off:", on_click=_reset, args=(lo, hi),
                  width="stretch")

    dates = st.session_state.get(K_DATES) or ()
    # date_input returns a 1-tuple while the user is mid-selection
    start, end = (dates[0], dates[1]) if len(dates) == 2 else _preset_range(DEFAULT_PRESET, lo, hi)
    return GlobalFilters(
        start=start, end=end,
        warehouses=tuple(st.session_state.get(K_WH) or ()),
        categories=tuple(st.session_state.get(K_CAT) or ()),
        suppliers=tuple(st.session_state.get(K_SUP) or ()),
        skus=tuple(st.session_state.get(K_SKU) or ()),
        customers=tuple(st.session_state.get(K_CUST) or ()),
    )


def current() -> GlobalFilters:
    """Filters for the running page (set by the navigation script)."""
    return st.session_state["gf_current"]
