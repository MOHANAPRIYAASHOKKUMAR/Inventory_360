"""Unit tests for global filter push-down and RAG exception rules."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inventory360.business_logic.exceptions import AMBER, GREEN, NA, RED, TARGETS, rag, rag_for, worst  # noqa: E402
from inventory360.data_access.filters import (  # noqa: E402
    GlobalFilters,
    applicability,
    apply_frame,
    build_where,
    product_scope,
)

BASE = GlobalFilters(start=date(2026, 10, 1), end=date(2026, 10, 31))
PRODUCTS = pd.DataFrame({
    "sku": ["S1", "S2", "S3", "S4"],
    "category": ["Toys", "Toys", "Garden", "Garden"],
    "supplier_id": ["SUP1", "SUP2", "SUP1", "SUP3"],
})


def test_prior_window_is_equal_length_and_adjacent():
    prior = BASE.prior()
    assert prior.days == BASE.days == 31
    assert prior.end == date(2026, 9, 30)
    assert prior.start == date(2026, 8, 31)


def test_date_only_where_clause():
    sql, params = build_where(BASE, {"date": "d"})
    assert sql == "where d between ? and ?"
    assert params == ["2026-10-01", "2026-10-31"]


def test_unfiltered_without_date_returns_empty_clause():
    assert build_where(BASE, {"warehouse": "w"}) == ("", [])


def test_multi_value_filters_are_parameterised():
    f = GlobalFilters(BASE.start, BASE.end, warehouses=("DC01", "DC02"), customers=("C1",))
    sql, params = build_where(f, {"date": "d", "warehouse": "w", "customer": "c"})
    assert sql == "where d between ? and ? and w in (?, ?) and c in (?)"
    assert params == ["2026-10-01", "2026-10-31", "DC01", "DC02", "C1"]
    # values never appear in the SQL text
    assert "DC01" not in sql


def test_product_scope_combines_category_supplier_product():
    f = GlobalFilters(BASE.start, BASE.end, categories=("Toys", "Garden"), suppliers=("SUP1",))
    assert product_scope(PRODUCTS, f) == ("S1", "S3")
    assert product_scope(PRODUCTS, BASE) is None
    f2 = GlobalFilters(BASE.start, BASE.end, categories=("Toys",), suppliers=("SUP3",))
    assert product_scope(PRODUCTS, f2) == ()


def test_sku_scope_replaces_category_and_supplier_columns():
    f = GlobalFilters(BASE.start, BASE.end, categories=("Toys",), suppliers=("SUP1",))
    scope = product_scope(PRODUCTS, f)
    sql, params = build_where(f, {"product": "sku", "category": "cat", "supplier": "sup"}, scope, use_date=False)
    assert sql == "where sku in (?)"
    assert params == ["S1"]


def test_empty_scope_matches_nothing():
    f = GlobalFilters(BASE.start, BASE.end, suppliers=("NONE",))
    sql, params = build_where(f, {"product": "sku"}, product_scope(PRODUCTS, f), use_date=False)
    assert sql == "where 1 = 0" and params == []


def test_without_product_column_falls_back_to_own_columns():
    f = GlobalFilters(BASE.start, BASE.end, categories=("Toys",), skus=("S1",))
    sql, params = build_where(f, {"category": "cat"}, use_date=False)
    assert sql == "where cat in (?)" and params == ["Toys"]


def test_applicability_reports_unsupported_filters():
    f = GlobalFilters(BASE.start, BASE.end, warehouses=("DC01",), categories=("Toys",), customers=("C1",))
    applied, ignored = applicability(f, {"date": "d", "warehouse": "w", "product": "sku"})
    assert applied == ["Date range", "Warehouse", "Category"]
    assert ignored == ["Customer"]


def test_apply_frame_matches_sql_semantics():
    df = pd.DataFrame({
        "d": pd.to_datetime(["2026-09-30", "2026-10-01", "2026-10-15", "2026-11-01"]),
        "w": ["DC01", "DC01", "DC02", "DC01"],
        "sku": ["S1", "S2", "S1", "S1"],
    })
    f = GlobalFilters(BASE.start, BASE.end, warehouses=("DC01",))
    out = apply_frame(df, f, {"date": "d", "warehouse": "w"})
    assert out.index.tolist() == [1]
    scoped = apply_frame(df, BASE, {"date": "d", "product": "sku"}, ("S1",))
    assert scoped.index.tolist() == [2]


@pytest.mark.parametrize("key,value,expected", [
    ("availability", 0.97, GREEN), ("availability", 0.95, AMBER), ("availability", 0.90, RED),
    ("days_cover", 30, GREEN), ("days_cover", 50, AMBER), ("days_cover", 75, RED),
    ("budget_variance", -0.05, GREEN), ("budget_variance", 0.05, AMBER), ("budget_variance", 0.10, RED),
    ("otif", None, NA), ("otif", float("nan"), NA),
])
def test_rag_bands(key, value, expected):
    assert rag_for(key, value) == expected


def test_rag_boundaries_are_inclusive():
    t = TARGETS["availability"]
    assert rag(t.green, t) == GREEN
    assert rag(t.amber, t) == AMBER


def test_worst_status():
    assert worst([GREEN, AMBER, GREEN]) == AMBER
    assert worst([GREEN, RED, AMBER]) == RED
    assert worst([]) == NA
