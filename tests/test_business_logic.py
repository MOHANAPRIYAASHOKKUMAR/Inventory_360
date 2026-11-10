"""Unit tests for replenishment, budget, supplier, ABC and forecasting logic."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inventory360.analytics.abc import abc_classify  # noqa: E402
from inventory360.analytics.forecasting import forecast_accuracy, holt_winters_forecast  # noqa: E402
from inventory360.analytics.kpis import comparison_window, period_kpis  # noqa: E402
from inventory360.business_logic import replenishment as rp  # noqa: E402
from inventory360.business_logic.budget import full_year_outturn, variance_rag  # noqa: E402
from inventory360.business_logic.supplier import risk_rating, spend_concentration  # noqa: E402
from inventory360.utils.formatting import fmt_gbp, fmt_pct, pct_change  # noqa: E402


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,expected", [(1_234_567, "£1.2M"), (45_600, "£45.6k"), (999, "£999"),
                                            (-2_500_000, "-£2.5M"), (3.2e9, "£3.2bn"), (None, "–")])
def test_fmt_gbp(value, expected):
    assert fmt_gbp(value) == expected


def test_fmt_pct_and_change():
    assert fmt_pct(0.1234) == "12.3%"
    assert fmt_pct(0.05, signed=True) == "+5.0%"
    assert pct_change(110, 100) == pytest.approx(0.10)
    assert pct_change(1, 0) is None


# --------------------------------------------------------------------------- #
# Replenishment policy
# --------------------------------------------------------------------------- #
def test_z_lookup_and_interpolation():
    assert rp.z_for_service_level(0.95) == pytest.approx(1.65)
    assert 1.28 < rp.z_for_service_level(0.92) < 1.65
    with pytest.raises(ValueError):
        rp.z_for_service_level(1.0)


def test_safety_stock_and_reorder_point():
    # z=1.65, sigma=10, LT=16 -> 1.65*10*4 = 66
    assert rp.safety_stock(1.65, 10, 16) == 66
    # 20/day * 16 days + 66
    assert rp.reorder_point(20, 10, 16, 1.65) == 386


@pytest.mark.parametrize("qty,moq,expected", [(0, 12, 0), (-5, 12, 0), (1, 12, 12), (24, 12, 24), (25, 12, 36), (7, 0, 7)])
def test_round_up_to_moq(qty, moq, expected):
    assert rp.round_up_to_moq(qty, moq) == expected


@pytest.mark.parametrize("on_hand,demand,expected", [
    (0, 5, "Out of stock"), (10, 5, "Critical"), (30, 5, "Low"), (100, 5, "Healthy"),
    (400, 5, "Overstock"), (700, 5, "Excess"), (50, 0, "Excess"), (0, 0, "Healthy"),
])
def test_classify_stock_status(on_hand, demand, expected):
    assert rp.classify_stock_status(on_hand, demand) == expected


def test_priority_rules():
    assert rp.priority("Out of stock", "A", 10) == "P1 - Urgent"
    assert rp.priority("Critical", "B", 10) == "P2 - High"
    assert rp.priority("Low", "C", 10) == "P3 - Medium"
    assert rp.priority("Healthy", "A", 10) == "P4 - Routine"
    assert rp.priority("Out of stock", "A", 0) == "None"


def _position_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "sku": ["S1", "S2", "S3"],
        "velocity_class": ["A", "B", "C"],
        "avg_daily_demand": [20.0, 5.0, 1.0],
        "stddev_daily_demand": [6.0, 2.0, 0.5],
        "lead_time_days": [14, 30, 56],
        "review_period_days": [7, 14, 28],
        "inventory_position_qty": [100, 500, 10],
        "min_order_qty": [24, 10, 6],
        "unit_cost_gbp": [2.5, 10.0, 40.0],
        "lifecycle_status": ["Core", "Core", "Discontinued"],
        "stock_status": ["Critical", "Healthy", "Low"],
    })


def test_recalculate_plan_base_policy_matches_sql_logic():
    plan = rp.recalculate_plan(_position_frame(), rp.Scenario())
    s1 = plan.iloc[0]
    rop = np.ceil(20 * 14 + 1.65 * 6 * np.sqrt(14))
    out = np.ceil(20 * 21 + 1.65 * 6 * np.sqrt(14))
    assert s1["scenario_reorder_point"] == rop
    assert s1["scenario_order_qty"] == np.ceil((out - 100) / 24) * 24
    assert s1["scenario_order_qty"] % 24 == 0
    assert s1["scenario_priority"] == "P1 - Urgent"
    # Healthy B line above reorder point: no order
    assert plan.iloc[1]["scenario_order_qty"] == 0
    # Discontinued lines are never re-ordered
    assert plan.iloc[2]["scenario_order_qty"] == 0


def test_scenario_levers_increase_requirement():
    base = rp.recalculate_plan(_position_frame(), rp.Scenario())
    stressed = rp.recalculate_plan(_position_frame(), rp.Scenario(service_level_a=0.99, demand_uplift=0.2, lead_time_buffer_days=7))
    assert stressed["scenario_order_value_gbp"].sum() > base["scenario_order_value_gbp"].sum()
    assert stressed["scenario_safety_stock"].iloc[0] > base["scenario_safety_stock"].iloc[0]


# --------------------------------------------------------------------------- #
# Budget and supplier
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("v,expected", [(None, "n/a"), (-0.10, "Green"), (0.02, "Green"), (0.05, "Amber"), (0.12, "Red")])
def test_variance_rag(v, expected):
    assert variance_rag(v) == expected


def test_full_year_outturn():
    bva = pd.DataFrame({
        "fiscal_year": ["FY26/27"] * 3,
        "budget_area": ["Freight & Duty"] * 3,
        "budget_gbp": [100.0, 100.0, 100.0],
        "actual_gbp": [110.0, None, None],
        "forecast_gbp": [None, None, 95.0],
        "is_actualised": [True, False, False],
    })
    out = full_year_outturn(bva, "FY26/27").iloc[0]
    assert out["budget_gbp"] == 300
    assert out["budget_ytd_gbp"] == 100
    assert out["ytd_variance_pct"] == pytest.approx(0.10)
    # actual 110 + open month at budget 100 + forecast 95
    assert out["outturn_gbp"] == pytest.approx(305)
    assert out["rag"] == "Red"


def test_supplier_rating_and_concentration():
    assert risk_rating(90) == "Low"
    assert risk_rating(80) == "Medium"
    assert risk_rating(50) == "High"
    assert risk_rating(None) == "High"
    sc = pd.DataFrame({"spend_gbp": [50, 30, 10, 5, 3, 2]})
    assert spend_concentration(sc, top_n=2) == pytest.approx(0.8)


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
def test_abc_classification():
    df = pd.DataFrame({"sku": list("ABCDEFGHIJ"), "sales": [500, 200, 100, 60, 50, 40, 20, 15, 10, 5]})
    out = abc_classify(df, "sales")
    assert out.iloc[0]["abc_class"] == "A"
    assert out.iloc[-1]["abc_class"] == "C"
    assert out["cumulative_share"].iloc[-1] == pytest.approx(1.0)


def test_holt_winters_shapes_and_accuracy():
    idx = pd.date_range("2025-01-05", periods=80, freq="W-SUN")
    season = 100 + 40 * np.sin(np.arange(80) * 2 * np.pi / 52)
    series = pd.Series(season + np.arange(80) * 0.5, index=idx)
    fc = holt_winters_forecast(series, horizon=8)
    assert len(fc) == 88
    assert fc["forecast"].notna().sum() == 8
    assert (fc["upper"].dropna() >= fc["forecast"].dropna()).all()
    acc = forecast_accuracy(fc["actual"].iloc[-30:-8], fc["fitted"].iloc[-30:-8])
    assert acc["wape"] < 0.15
    with pytest.raises(ValueError):
        holt_winters_forecast(series.head(5))


def test_period_kpis_and_windows():
    dates = pd.date_range("2026-01-01", periods=56, freq="D")
    daily = pd.DataFrame({
        "snapshot_date": dates, "stock_value_gbp": 1000.0, "net_sales_gbp": 100.0, "cogs_gbp": 60.0,
        "lost_sales_gbp": 5.0, "units_demanded": 50, "units_sold": 45, "sku_locations": 10, "sku_locations_oos": 1,
    })
    cs, ce, ps, pe = comparison_window(dates[-1], 28)
    assert (ce - cs).days == 27 and pe == cs - pd.Timedelta(days=1)
    k = period_kpis(daily, cs, ce)
    assert k.net_sales_gbp == 2800
    assert k.fill_rate == pytest.approx(0.9)
    assert k.availability == pytest.approx(0.9)
    assert k.gross_margin_pct == pytest.approx(0.4)
    assert k.stock_turns == pytest.approx(60 * 365 / 1000)
