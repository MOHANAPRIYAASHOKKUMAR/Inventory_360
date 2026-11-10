"""Inventory 360 - Enterprise Supply Chain Intelligence Platform.

Entry point for Streamlit in Snowflake and local development:
    streamlit run streamlit_app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
for path in (APP_DIR, APP_DIR.parent / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import streamlit as st  # noqa: E402

from components.layout import sidebar_filters  # noqa: E402
from inventory360 import __version__  # noqa: E402
from inventory360.data_access import queries  # noqa: E402
from inventory360.utils.config import APP_NAME, COMPANY_NAME  # noqa: E402

st.set_page_config(
    page_title=f"{APP_NAME} | {COMPANY_NAME}",
    page_icon=str(APP_DIR / "assets" / "icon.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
)
st.logo(str(APP_DIR / "assets" / "logo.svg"), icon_image=str(APP_DIR / "assets" / "icon.svg"), size="large")

PAGES = APP_DIR / "pages"
page = st.navigation(
    {
        "Overview": [
            st.Page(PAGES / "01_executive_overview.py", title="Executive overview", icon=":material/dashboard:", default=True),
        ],
        "Inventory": [
            st.Page(PAGES / "02_inventory_health.py", title="Inventory health", icon=":material/inventory_2:"),
            st.Page(PAGES / "03_replenishment.py", title="Replenishment planner", icon=":material/autorenew:"),
            st.Page(PAGES / "08_demand_forecast.py", title="Demand forecast", icon=":material/trending_up:"),
        ],
        "Supply chain": [
            st.Page(PAGES / "04_suppliers.py", title="Supplier performance", icon=":material/handshake:"),
            st.Page(PAGES / "05_logistics.py", title="Logistics & freight", icon=":material/local_shipping:"),
            st.Page(PAGES / "06_warehouses.py", title="Warehouse network", icon=":material/warehouse:"),
        ],
        "Finance": [
            st.Page(PAGES / "07_budget_and_costs.py", title="Budget & costs", icon=":material/account_balance:"),
        ],
        "Platform": [
            st.Page(PAGES / "09_data_governance.py", title="Data & governance", icon=":material/verified_user:"),
        ],
    },
    position="sidebar",
)

# Shared reference data drives the global filters on every page
warehouses = queries.load_warehouses()
categories = sorted(queries.load_products()["category"].unique().tolist())
sidebar_filters(warehouses, categories)

with st.sidebar:
    st.divider()
    st.caption(f"{COMPANY_NAME} · UK retail & distribution  \nReporting currency GBP (£) · v{__version__}")

page.run()
