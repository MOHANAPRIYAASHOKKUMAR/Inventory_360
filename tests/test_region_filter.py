"""Unit tests for the region filter and its resolution into warehouse codes."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inventory360.data_access.filters import GlobalFilters, applicability, build_where, resolve_regions  # noqa: E402

WH = pd.DataFrame({"warehouse_code": ["DC01", "DC02", "DC06", "DC07"],
                   "uk_region": ["East Midlands", "South East", "Scotland", "Wales"]})
BASE = GlobalFilters(start=date(2026, 10, 1), end=date(2026, 10, 31))


def test_no_regions_keeps_selection():
    assert resolve_regions(WH, (), ("DC02",)) == ("DC02",)
    assert resolve_regions(WH, (), ()) == ()


def test_regions_only_expand_to_their_warehouses():
    assert resolve_regions(WH, ("Scotland", "Wales"), ()) == ("DC06", "DC07")


def test_regions_and_warehouses_intersect():
    assert resolve_regions(WH, ("Scotland",), ("DC01", "DC06")) == ("DC06",)


def test_region_pushes_down_as_warehouse_codes():
    f = GlobalFilters(start=BASE.start, end=BASE.end, regions=("Scotland",),
                      warehouses=resolve_regions(WH, ("Scotland",), ()))
    where, params = build_where(f, {"date": "d", "warehouse": "warehouse_code"})
    assert "warehouse_code in (?)" in where and params[-1] == "DC06"


def test_region_applicability_follows_warehouse_support():
    f = GlobalFilters(start=BASE.start, end=BASE.end, regions=("Wales",), warehouses=("DC07",))
    applied, ignored = applicability(f, {"date": "d", "warehouse": "w"})
    assert "Region" in applied and not ignored
    applied, ignored = applicability(f, {"date": "d", "supplier": "s"})
    assert "Region" in ignored


def test_prior_keeps_regions():
    f = GlobalFilters(start=BASE.start, end=BASE.end, regions=("Wales",))
    assert f.prior().regions == ("Wales",)
