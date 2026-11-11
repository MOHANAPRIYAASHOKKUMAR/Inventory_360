"""Unit tests for the live data-quality rules."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inventory360.business_logic import data_quality as dq  # noqa: E402
from inventory360.business_logic.exceptions import AMBER, GREEN, RED  # noqa: E402

TODAY = date(2026, 11, 11)


def test_freshness_bands():
    got = {c.name: c.status for c in dq.freshness(
        {"a": date(2026, 11, 10), "b": date(2026, 11, 9), "c": date(2026, 11, 1), "d": None}, TODAY)}
    # 24 h -> green (<= 30), 48 h -> amber (<= 54), 240 h -> red, missing -> red
    assert got == {"a": GREEN, "b": AMBER, "c": RED, "d": RED}


def test_freshness_wording_is_factual():
    [c] = dq.freshness({"a": date(2026, 11, 10)}, TODAY)
    assert c.detail.startswith("Latest data loaded") and "succeed" not in c.detail.lower()


def test_nulls_and_duplicates():
    assert [c.status for c in dq.key_nulls({"x": 0, "y": 3})] == [GREEN, RED]
    assert [c.status for c in dq.duplicates({"x": 0, "y": 1})] == [GREEN, RED]


def _counts(values):
    return pd.DataFrame({"d": pd.date_range("2026-10-01", periods=len(values)), "n": values})


def test_daily_volume_ok():
    [c] = dq.daily_volume(_counts([1000] * 30), "inv")
    assert c.status == GREEN


def test_daily_volume_partial_latest_day():
    [c] = dq.daily_volume(_counts([1000] * 29 + [700]), "inv")
    assert c.status == RED


def test_daily_volume_incomplete_day_in_window():
    [c] = dq.daily_volume(_counts([1000] * 10 + [900] + [1000] * 19), "inv")
    assert c.status == AMBER and "incomplete" in c.detail


def test_daily_volume_empty():
    [c] = dq.daily_volume(pd.DataFrame({"d": [], "n": []}), "inv")
    assert c.status == RED


def test_rebuilt_and_overall():
    checks = dq.rebuilt({"a": datetime(2026, 11, 10, 6), "b": None})
    assert [c.status for c in checks] == [GREEN, AMBER]
    assert "Model last rebuilt" in checks[0].detail
    assert dq.overall(checks) == AMBER
    assert dq.overall([]) == AMBER
    assert list(dq.to_frame(checks).columns) == ["area", "name", "status", "detail"]
