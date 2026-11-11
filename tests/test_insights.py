"""Unit tests for the Executive Insights rules."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inventory360.business_logic import insights  # noqa: E402
from inventory360.business_logic.exceptions import AMBER, RED  # noqa: E402
from inventory360.business_logic.kpi_framework import evaluate  # noqa: E402


def test_on_target_and_stable_kpis_raise_nothing():
    rs = [evaluate("availability", 0.97, 0.97), evaluate("fill_rate", 0.98, 0.979)]
    assert insights.kpi_insights(rs, "Oct") == []


def test_red_kpi_raises_red_insight_with_target():
    [i] = insights.kpi_insights([evaluate("availability", 0.90, 0.95)], "Oct")
    assert i.severity == RED and "below target" in i.title and "≥ 96.0%" in i.detail and i.period == "Oct"


def test_lower_is_better_wording():
    [i] = insights.kpi_insights([evaluate("days_cover", 70, 70)], "Oct")
    assert "above target" in i.title


def test_adverse_move_on_target_is_amber():
    # Still green (>= 96 %) but down 2 pts
    [i] = insights.kpi_insights([evaluate("availability", 0.97, 0.99)], "Oct")
    assert i.severity == AMBER and "fell" in i.title


def test_small_adverse_move_is_ignored():
    assert insights.kpi_insights([evaluate("availability", 0.975, 0.98)], "Oct") == []


def test_favourable_move_is_ignored():
    assert insights.kpi_insights([evaluate("lost_sales", 80.0, 100.0)], "Oct") == []


def test_operational_rules():
    facts = {"p1_lines": 12, "p1_value": 50_000, "excess_value": 2e6, "excess_share": 0.2, "overdue_shipments": 3,
             "open_shipments": 40, "high_risk_suppliers": 0, "lost_sales": 120.0, "lost_sales_prev": 100.0}
    got = {i.metric: i.severity for i in insights.operational_insights(facts, "Oct")}
    assert got == {"p1_replenishment": RED, "excess_value": RED, "overdue_shipments": AMBER, "lost_sales": AMBER}


def test_empty_facts_raise_nothing():
    assert insights.operational_insights({}, "Oct") == []


def test_rank_severity_then_impact_and_dedup():
    a = insights.Insight("a", "", AMBER, "m1", impact_gbp=1e9)
    b = insights.Insight("b", "", RED, "m2", impact_gbp=10)
    c = insights.Insight("c", "", RED, "m3", impact_gbp=100)
    d = insights.Insight("d", "", RED, "m1", impact_gbp=5)
    ranked = insights.rank([a, b, c, d])
    assert [i.title for i in ranked] == ["c", "b", "d"]   # d replaces a (same metric, more severe)
