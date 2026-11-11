"""Three access tiers for the Inventory 360 app.

Snowflake enforces data access (the app runs with restricted caller's rights); the
tiers only decide what the UI offers, so a missing or unknown role fails closed to
Viewer.

| Tier      | Roles                                              | Adds                              |
|-----------|----------------------------------------------------|-----------------------------------|
| Viewer    | INV360_VIEWER, anything unknown                    | business pages, CSV export        |
| Planner   | INV360_PLANNER                                     | replenishment approval / submit   |
| Developer | INV360_ENGINEER, INV360_ADMIN, SYSADMIN, ACCOUNTADMIN | Data & governance, diagnostics |
"""
from __future__ import annotations

import os
from enum import IntEnum


class Tier(IntEnum):
    VIEWER = 1
    PLANNER = 2
    DEVELOPER = 3


ROLE_TIERS: dict[str, Tier] = {
    "INV360_VIEWER": Tier.VIEWER,
    "INV360_PLANNER": Tier.PLANNER,
    "INV360_ENGINEER": Tier.DEVELOPER,
    "INV360_ADMIN": Tier.DEVELOPER,
    "SYSADMIN": Tier.DEVELOPER,
    "ACCOUNTADMIN": Tier.DEVELOPER,
}
TIER_LABELS = {Tier.VIEWER: "Viewer", Tier.PLANNER: "Planner", Tier.DEVELOPER: "Developer"}
APP_ROLES = frozenset(ROLE_TIERS)


class AccessDenied(PermissionError):
    """Raised when an action needs a higher tier than the session has."""


def tier_for_role(role: str | None) -> Tier:
    return ROLE_TIERS.get((role or "").strip().upper(), Tier.VIEWER)


def override_tier() -> Tier | None:
    """INV360_TIER_OVERRIDE=viewer|planner|developer simulates a tier for local tests.

    Ignored inside Snowflake (SNOWFLAKE_HOST is set there) so it can never widen access.
    """
    value = os.getenv("INV360_TIER_OVERRIDE", "").strip().upper()
    if not value or os.getenv("SNOWFLAKE_HOST"):
        return None
    return Tier.__members__.get(value)


def current_tier() -> Tier:
    import streamlit as st

    return st.session_state.get("access_tier", Tier.VIEWER)


def has(tier: Tier) -> bool:
    return current_tier() >= tier


def require(tier: Tier, action: str = "this action") -> None:
    if not has(tier):
        raise AccessDenied(f"{action} needs the {TIER_LABELS[tier]} tier or above.")
