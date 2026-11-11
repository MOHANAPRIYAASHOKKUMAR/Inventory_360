"""Unit tests for the access tiers and caller's-rights error mapping."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inventory360.data_access.connection import DataAccessDenied, is_denied  # noqa: E402
from inventory360.utils import access  # noqa: E402
from inventory360.utils.access import Tier, tier_for_role  # noqa: E402


@pytest.mark.parametrize(("role", "tier"), [
    ("INV360_VIEWER", Tier.VIEWER),
    ("inv360_planner", Tier.PLANNER),
    ("INV360_ENGINEER", Tier.DEVELOPER),
    ("INV360_ADMIN", Tier.DEVELOPER),
    ("ACCOUNTADMIN", Tier.DEVELOPER),
    ("PUBLIC", Tier.VIEWER),
    (None, Tier.VIEWER),
    ("", Tier.VIEWER),
])
def test_role_to_tier_fails_closed(role, tier):
    assert tier_for_role(role) == tier


def test_tiers_are_ordered():
    assert Tier.VIEWER < Tier.PLANNER < Tier.DEVELOPER


def test_override_only_outside_snowflake(monkeypatch):
    monkeypatch.setenv("INV360_TIER_OVERRIDE", "developer")
    monkeypatch.delenv("SNOWFLAKE_HOST", raising=False)
    assert access.override_tier() == Tier.DEVELOPER
    monkeypatch.setenv("SNOWFLAKE_HOST", "x.snowflakecomputing.com")
    assert access.override_tier() is None


def test_override_rejects_unknown_values(monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_HOST", raising=False)
    monkeypatch.setenv("INV360_TIER_OVERRIDE", "superuser")
    assert access.override_tier() is None


def test_require_blocks_lower_tier(monkeypatch):
    monkeypatch.setattr(access, "current_tier", lambda: Tier.VIEWER)
    with pytest.raises(access.AccessDenied):
        access.require(Tier.PLANNER, "Submitting")
    monkeypatch.setattr(access, "current_tier", lambda: Tier.PLANNER)
    access.require(Tier.PLANNER)


class _SfError(Exception):
    def __init__(self, msg, errno=None):
        super().__init__(msg)
        self.errno = errno


@pytest.mark.parametrize(("exc", "denied"), [
    (_SfError("SQL access control error: Insufficient privileges to operate on table", 3001), True),
    (_SfError("Object 'X' does not exist or not authorized.", 2003), True),
    (_SfError("Numeric value 'abc' is not recognized", 100038), False),
    (ValueError("boom"), False),
    (DataAccessDenied("detail"), True),
])
def test_permission_errors_are_recognised(exc, denied):
    assert is_denied(exc) is denied


def test_denied_message_hides_sql_detail():
    exc = DataAccessDenied("select * from SECRET")
    assert "SECRET" not in str(exc) and exc.detail == "select * from SECRET"
