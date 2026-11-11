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

import streamlit as st  # noqa: E402

from components import filters, quality  # noqa: E402
from inventory360 import __version__  # noqa: E402
from inventory360.data_access import connection, queries  # noqa: E402
from inventory360.utils import access  # noqa: E402
from inventory360.utils.access import Tier  # noqa: E402
from inventory360.utils.config import APP_NAME, COMPANY_NAME  # noqa: E402

st.set_page_config(
    page_title=f"{APP_NAME} | {COMPANY_NAME}",
    page_icon=str(APP_DIR / "assets" / "icon.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
)
st.logo(str(APP_DIR / "assets" / "logo.svg"), icon_image=str(APP_DIR / "assets" / "icon.svg"), size="large")


# --------------------------------------------------------------------------- #
# Identity and tier. The session connection is opened HERE, at the top of the
# script: caller's-rights viewer tokens are only valid at the start of a session.
# --------------------------------------------------------------------------- #
identity = connection.init_session()
role = identity["role"]
tier = access.override_tier() or access.tier_for_role(role)
st.session_state["access_tier"] = tier
st.session_state["viewer_role"] = role

if identity["error"] or role not in access.APP_ROLES and access.override_tier() is None:
    # No usable Inventory 360 role: explain how to get access, no stack trace
    st.title(APP_NAME)
    st.warning(
        "Your Snowflake default role doesn't give access to Inventory 360. Ask the platform "
        "administrator to grant you INV360_VIEWER (read-only) or INV360_PLANNER and set it as "
        "your default role, then reopen the app.",
        icon=":material/lock:",
    )
    if role:
        st.caption(f"Current default role: {role}")
    st.stop()

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
if tier >= Tier.DEVELOPER:
    sections["Platform"] = [
        st.Page(PAGES / "09_data_governance.py", title="Data & governance", icon=":material/verified_user:"),
    ]
# Pages not registered here cannot be opened, even by URL
page = st.navigation(sections, position="sidebar")

# Reference data (cached 1 h) drives the global filters on every page
try:
    lo, hi = queries.load_date_bounds()
    st.session_state["gf_current"] = filters.render(
        queries.load_warehouses(), queries.load_products(), queries.load_suppliers(), queries.load_customers(),
        lo.date(), hi.date(),
    )
except connection.DataAccessDenied as exc:
    st.error(connection.DENIED_MESSAGE, icon=":material/lock:")
    if tier >= Tier.DEVELOPER:
        st.code(exc.detail)
    st.stop()
st.session_state["gf_as_of"] = hi

with st.sidebar:
    st.divider()
    caption = f"{COMPANY_NAME} · UK retail & distribution  \nAll values in GBP (£) · v{__version__}  \n" \
              f"Access: {access.TIER_LABELS[tier]}"
    if tier >= Tier.DEVELOPER:
        caption += f" · role {role} · {identity['mode']} connection"
    st.caption(caption)

# Error boundary: a failing page shows a business message, never a stack trace
# (developers also get the technical detail). st.rerun/st.stop are BaseExceptions.
try:
    page.run()
    quality.footer()
except connection.DataAccessDenied as exc:
    st.error(connection.DENIED_MESSAGE, icon=":material/lock:")
    if tier >= Tier.DEVELOPER:
        st.code(exc.detail)
except access.AccessDenied as exc:
    st.warning(str(exc), icon=":material/lock:")
except Exception as exc:  # noqa: BLE001
    st.error("This page couldn't be loaded. Try again, or clear filters. If it keeps happening, "
             "contact the Inventory 360 administrator.", icon=":material/error:")
    if tier >= Tier.DEVELOPER:
        st.exception(exc)
