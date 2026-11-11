"""Inventory 360 - Enterprise Supply Chain Intelligence Platform.

Entry point for Streamlit in Snowflake, Snowpark Container Services and local development:
    streamlit run streamlit_app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
for path in (APP_DIR, APP_DIR.parent / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import os  # noqa: E402

import streamlit as st  # noqa: E402

from components import filters  # noqa: E402
from inventory360 import __version__  # noqa: E402
from inventory360.data_access import connection, queries  # noqa: E402
from inventory360.utils.config import APP_NAME, COMPANY_NAME  # noqa: E402

st.set_page_config(
    page_title=f"{APP_NAME} | {COMPANY_NAME}",
    page_icon=str(APP_DIR / "assets" / "icon.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
)
st.logo(str(APP_DIR / "assets" / "logo.svg"), icon_image=str(APP_DIR / "assets" / "icon.svg"), size="large")


PLATFORM_ROLES = {"INV360_PLANNER", "INV360_ENGINEER", "INV360_ADMIN", "SYSADMIN", "ACCOUNTADMIN"}


def _can_view_platform() -> bool:
    """Data & governance is hidden from read-only viewers (INV360_VIEWER).

    The app itself runs with owner's rights, so the viewer's role is read through a
    restricted caller's-rights connection (container runtime only). Only the PRIMARY
    role is checked: CURRENT_ROLE() is the viewer's default role. IS_ROLE_IN_SESSION
    is not used because DEFAULT_SECONDARY_ROLES = ('ALL') would activate every
    granted role. Locally the developer's own connection is checked. Fails closed.
    """
    if "can_view_platform" not in st.session_state:
        try:
            conn = (st.connection("snowflake-callers-rights") if os.getenv("SNOWFLAKE_HOST")
                    else connection.get_connection())
            role = str(conn.query("select current_role() as r", ttl=0).iloc[0, 0]).upper()
            st.session_state["viewer_role"] = role
            st.session_state["can_view_platform"] = role in PLATFORM_ROLES
        except Exception:  # noqa: BLE001 - any failure means no access
            st.session_state["can_view_platform"] = False
    return st.session_state["can_view_platform"]


# Resolve the viewer's access before building navigation: caller's-rights tokens are
# only valid at the start of the session.
show_platform = _can_view_platform()

PAGES = APP_DIR / "pages"
sections = {
        "Overview": [
            st.Page(PAGES / "01_executive_overview.py", title="Executive overview", icon=":material/dashboard:", default=True),
            st.Page(PAGES / "10_customers_and_sales.py", title="Customers & sales", icon=":material/storefront:"),
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
}
if show_platform:
    sections["Platform"] = [
        st.Page(PAGES / "09_data_governance.py", title="Data & governance", icon=":material/verified_user:"),
    ]
# Pages not registered here cannot be opened, even by URL
page = st.navigation(sections, position="sidebar")

# Reference data (cached 1 h) drives the global filters on every page
lo, hi = queries.load_date_bounds()
st.session_state["gf_current"] = filters.render(
    queries.load_warehouses(), queries.load_products(), queries.load_suppliers(), queries.load_customers(),
    lo.date(), hi.date(),
)
st.session_state["gf_as_of"] = hi

with st.sidebar:
    st.divider()
    st.caption(f"{COMPANY_NAME} · UK retail & distribution  \nAll values in GBP (£) · v{__version__}  \n"
               f"Access role: {st.session_state.get('viewer_role', 'unknown')}")

page.run()
