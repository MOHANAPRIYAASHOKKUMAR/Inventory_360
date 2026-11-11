"""Rule-based Executive Insights.

Turns evaluated KPIs and a few operational facts into short, ranked statements a
manager can act on. Rules (no model, fully explainable):

1. KPI off target (Red) or close to it (Amber).
2. Significant adverse move vs the comparison period (>= 1 pt for ratios, >= 5 %
   otherwise), even when the KPI is still on target.
3. Operational exceptions: urgent (P1) replenishment, excess stock cash at risk,
   overdue inbound shipments, high-risk supplier spend.

Insights are ranked by severity (Red before Amber), then by GBP impact.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from inventory360.business_logic.exceptions import AMBER, RED
from inventory360.business_logic.kpi_framework import KpiResult
from inventory360.utils.formatting import fmt_days, fmt_gbp, fmt_int, fmt_pct

ADVERSE_PCT = 0.05     # 5 % relative move
ADVERSE_PTS = 0.01     # 1 percentage point for ratio KPIs
SEVERITY_RANK = {RED: 0, AMBER: 1}


@dataclass(frozen=True)
class Insight:
    title: str
    detail: str
    severity: str                  # Red | Amber
    metric: str                    # KPI key or fact name (drives the drill-down)
    actual: str = ""
    target: str = ""
    variance: str = ""
    period: str = ""
    impact_gbp: float = 0.0
    tags: tuple[str, ...] = field(default_factory=tuple)


def _fmt(r: KpiResult, v: float | None) -> str:
    if v is None:
        return "–"
    return {"pct": fmt_pct, "gbp": fmt_gbp, "days": fmt_days, "ratio": lambda x: f"{x:.1f}x",
            "num": fmt_int}[r.spec.unit](v)


def _change_text(r: KpiResult) -> str:
    if r.abs_change is None:
        return ""
    if r.spec.unit == "pct":
        return f"{r.abs_change * 100:+.1f} pts vs comparison"
    return "" if r.pct_change is None else f"{r.pct_change:+.1%} vs comparison"


def _adverse(r: KpiResult) -> bool:
    if r.favourable is not False:
        return False
    if r.spec.unit == "pct":
        return abs(r.abs_change or 0) >= ADVERSE_PTS
    return r.pct_change is not None and abs(r.pct_change) >= ADVERSE_PCT


def kpi_insights(results: list[KpiResult], period: str, impacts: dict[str, float] | None = None) -> list[Insight]:
    impacts = impacts or {}
    out = []
    for r in results:
        s = r.spec
        off = r.status in (RED, AMBER)
        moved = _adverse(r)
        if not (off or moved):
            continue
        direction = "below" if s.higher_is_better else "above"
        if off:
            title = f"{s.label} {direction} target" if r.status == RED else f"{s.label} close to target"
            severity = r.status
        else:
            verb = "fell" if r.trend == "down" else "rose"
            title = f"{s.label} {verb} vs the comparison period"
            severity = AMBER
        detail_bits = [f"{_fmt(r, r.value)} actual"]
        if r.target is not None:
            detail_bits.append(f"target {'≥' if s.higher_is_better else '≤'} {_fmt(r, r.target)}")
        change = _change_text(r)
        if change:
            detail_bits.append(change)
        out.append(Insight(
            title=title, detail=" · ".join(detail_bits), severity=severity, metric=s.key,
            actual=_fmt(r, r.value), target="" if r.target is None else _fmt(r, r.target),
            variance=change or ("" if r.gap is None else _fmt(r, abs(r.gap)) + (" short" if r.gap < 0 else " over")),
            period=period, impact_gbp=float(impacts.get(s.key, 0.0)),
        ))
    return out


def operational_insights(facts: dict, period: str) -> list[Insight]:
    """``facts`` keys (all optional): p1_lines, p1_value, excess_value, excess_share, overdue_shipments,
    open_shipments, high_risk_suppliers, high_risk_spend, lost_sales, lost_sales_prev."""
    out = []
    if facts.get("p1_lines"):
        out.append(Insight(
            "Urgent replenishment needed", f"{fmt_int(facts['p1_lines'])} A-class SKU-locations out of stock or critical"
            f" · {fmt_gbp(facts.get('p1_value', 0))} to order", RED, "p1_replenishment",
            actual=f"{fmt_int(facts['p1_lines'])} lines", target="0 lines", period="Latest snapshot",
            impact_gbp=float(facts.get("p1_value", 0))))
    share = facts.get("excess_share") or 0
    if share > 0.05:
        out.append(Insight(
            "Excess stock tying up cash", f"{fmt_gbp(facts.get('excess_value', 0))} above overstock limits"
            f" · {fmt_pct(share)} of stock value", RED if share > 0.15 else AMBER, "excess_value",
            actual=fmt_pct(share), target="≤ 5.0% of stock", period="Latest snapshot",
            impact_gbp=float(facts.get("excess_value", 0))))
    overdue = facts.get("overdue_shipments") or 0
    if overdue:
        out.append(Insight(
            "Inbound shipments overdue", f"{fmt_int(overdue)} in transit past planned arrival"
            f" · {fmt_int(facts.get('open_shipments', 0))} open shipments", RED if overdue > 20 else AMBER,
            "overdue_shipments", actual=fmt_int(overdue), target="0", period="Open order book"))
    risky = facts.get("high_risk_suppliers") or 0
    if risky:
        out.append(Insight(
            "Spend with high-risk suppliers", f"{risky} high-risk suppliers · {fmt_gbp(facts.get('high_risk_spend', 0))}"
            " of 12-month spend", RED if risky > 3 else AMBER, "high_risk_suppliers",
            actual=str(risky), target="0", period="Rolling 12 months",
            impact_gbp=float(facts.get("high_risk_spend", 0))))
    lost, lost_prev = facts.get("lost_sales"), facts.get("lost_sales_prev")
    if lost and lost_prev and lost > lost_prev * (1 + ADVERSE_PCT):
        out.append(Insight(
            "Lost sales rising", f"{fmt_gbp(lost)} lost to stockouts · {lost / lost_prev - 1:+.1%} vs comparison",
            AMBER, "lost_sales", actual=fmt_gbp(lost), variance=f"{lost / lost_prev - 1:+.1%}", period=period,
            impact_gbp=float(lost - lost_prev)))
    return out


def rank(insights: list[Insight]) -> list[Insight]:
    """Severity first, then GBP impact; one insight per metric (the most severe)."""
    best: dict[str, Insight] = {}
    for i in insights:
        cur = best.get(i.metric)
        if cur is None or (SEVERITY_RANK[i.severity], -i.impact_gbp) < (SEVERITY_RANK[cur.severity], -cur.impact_gbp):
            best[i.metric] = i
    return sorted(best.values(), key=lambda i: (SEVERITY_RANK[i.severity], -i.impact_gbp, i.title))


def build(results: list[KpiResult], facts: dict, period: str, impacts: dict[str, float] | None = None) -> list[Insight]:
    return rank(kpi_insights(results, period, impacts) + operational_insights(facts, period))
