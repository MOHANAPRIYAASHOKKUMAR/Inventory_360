"""Unit tests for the KPI spec registry and status evaluation."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inventory360.business_logic import kpi_framework as kf  # noqa: E402
from inventory360.business_logic.exceptions import AMBER, GREEN, RED, TARGETS, rag  # noqa: E402

PROBES = [-1.0, 0.0, 0.5, 0.75, 0.8, 0.85, 0.9, 0.93, 0.94, 0.95, 0.96, 0.97, 1.0, 6.0, 7.0, 8.0, 30.0, 45.0, 50.0,
          54.0, 60.0, 70.0]


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_registry_matches_existing_policy(key):
    """The framework must judge every KPI exactly as the existing RAG rules do."""
    for v in PROBES:
        assert kf.evaluate(key, v).status == rag(v, TARGETS[key]), (key, v)


def test_higher_is_better_boundaries():
    assert kf.evaluate("availability", 0.96).status == GREEN
    assert kf.evaluate("availability", 0.9599).status == AMBER
    assert kf.evaluate("availability", 0.93).status == AMBER
    assert kf.evaluate("availability", 0.9299).status == RED


def test_lower_is_better_boundaries():
    assert kf.evaluate("days_cover", 45).status == GREEN
    assert kf.evaluate("days_cover", 45.1).status == AMBER
    assert kf.evaluate("days_cover", 60).status == AMBER
    assert kf.evaluate("days_cover", 60.1).status == RED


@pytest.mark.parametrize("value", [None, float("nan")])
def test_missing_value_is_no_data(value):
    r = kf.evaluate("availability", value, 0.95)
    assert r.status == kf.NO_DATA and r.trend is None and r.gap is None


def test_no_target_status():
    r = kf.evaluate("lost_sales", 1000.0, 900.0)
    assert r.status == kf.NO_TARGET
    assert r.trend == kf.UP and r.favourable is False


def test_trend_and_favourability_respect_direction():
    up_good = kf.evaluate("availability", 0.97, 0.95)
    assert (up_good.trend, up_good.favourable) == (kf.UP, True)
    up_bad = kf.evaluate("days_cover", 50, 40)
    assert (up_bad.trend, up_bad.favourable) == (kf.UP, False)
    down_good = kf.evaluate("days_cover", 40, 50)
    assert (down_good.trend, down_good.favourable) == (kf.DOWN, True)


def test_flat_band():
    assert kf.evaluate("availability", 0.9605, 0.9600).trend == kf.FLAT       # < 0.1 pt
    assert kf.evaluate("stock_value", 1_002_000, 1_000_000).trend == kf.FLAT  # < 0.5 %
    assert kf.evaluate("stock_value", 1_010_000, 1_000_000).trend == kf.UP


def test_changes_and_gap():
    r = kf.evaluate("fill_rate", 0.95, 0.90)
    assert r.abs_change == pytest.approx(0.05)
    assert r.pct_change == pytest.approx(0.05 / 0.90)
    assert r.gap == pytest.approx(0.95 - 0.97)


def test_zero_previous_has_no_pct_change():
    r = kf.evaluate("lost_sales", 10.0, 0.0)
    assert r.pct_change is None and r.trend == kf.UP


def test_relative_tolerance_target_from_previous():
    # Net sales: target = prior period, amber within 2 %
    assert kf.evaluate("net_sales", 100.0, 100.0).status == GREEN
    assert kf.evaluate("net_sales", 98.5, 100.0).status == AMBER
    assert kf.evaluate("net_sales", 97.0, 100.0).status == RED
    assert kf.evaluate("net_sales", 100.0).status == kf.NO_TARGET


def test_explicit_target_override():
    assert kf.evaluate("stock_value", 90.0, target=100.0).status == GREEN
    assert kf.evaluate("stock_value", 110.0, target=100.0).status == RED


def test_env_override(monkeypatch):
    monkeypatch.setenv("INV360_TARGET_AVAILABILITY", "0.99")
    s = kf._env_overrides(kf.KPIS["availability"])
    assert s.target == 0.99
    monkeypatch.setenv("INV360_TARGET_AVAILABILITY", "not-a-number")
    assert kf._env_overrides(kf.KPIS["availability"]).target == TARGETS["availability"].green


def test_worst_status():
    rs = [kf.evaluate("availability", 0.99), kf.evaluate("availability", 0.5), kf.evaluate("lost_sales", 1.0)]
    assert kf.worst_status(rs) == RED
    assert kf.worst_status([]) == kf.NO_DATA


def test_every_spec_has_definition_and_source():
    for s in kf.KPIS.values():
        assert s.definition and s.source and s.unit in {"pct", "gbp", "num", "days", "ratio"}
