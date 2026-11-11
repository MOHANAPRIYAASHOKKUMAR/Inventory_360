"""Live data-quality and freshness checks (no history table: evaluated on demand).

The SQL lives in ``queries.dq_*``; this module only judges the results, so it is
unit-testable. Wording is deliberately factual: "Latest data loaded" is the latest
business date present, "Model last rebuilt" is the table's LAST_ALTERED time. The
platform has no orchestration log, so it never claims that a refresh "succeeded".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from inventory360.business_logic.exceptions import AMBER, GREEN, RED
from inventory360.business_logic.kpi_framework import evaluate

DAY_DROP_AMBER = 0.05    # a day with >5 % fewer rows than the 28-day median is incomplete
DAY_DROP_RED = 0.20
# Event-driven sources (POs follow supplier delivery schedules) are lumpy by nature:
# daily rows swing roughly -40 % / +50 % around the median, so only a near-empty day is suspect.
VOLUME_TOLERANCE = {"Purchase orders": (0.60, 0.80)}
STATUS_ORDER = {RED: 3, AMBER: 2, GREEN: 1}


@dataclass(frozen=True)
class Check:
    area: str
    name: str
    status: str
    detail: str


def freshness(latest: dict[str, date | None], today: date) -> list[Check]:
    """Age of the latest business date per source vs the freshness target (hours)."""
    out = []
    for source, d in latest.items():
        if d is None:
            out.append(Check("Freshness", source, RED, "No rows found"))
            continue
        age_h = max((today - pd.Timestamp(d).date()).days, 0) * 24
        r = evaluate("freshness_hours", age_h)
        out.append(Check("Freshness", source, r.status,
                         f"Latest data loaded: {pd.Timestamp(d):%d %b %Y} ({age_h // 24} day(s) old)"))
    return out


def key_nulls(nulls: dict[str, int]) -> list[Check]:
    return [Check("Completeness", f"Nulls in {name}", GREEN if n == 0 else RED,
                  "No nulls in key columns" if n == 0 else f"{n:,} rows with a null key")
            for name, n in nulls.items()]


def duplicates(dupes: dict[str, int]) -> list[Check]:
    return [Check("Uniqueness", f"Duplicate grain in {name}", GREEN if n == 0 else RED,
                  "One row per grain key" if n == 0 else f"{n:,} duplicate grain rows")
            for name, n in dupes.items()]


def daily_volume(counts: pd.DataFrame, source: str, date_col: str = "d", count_col: str = "n") -> list[Check]:
    """Incomplete days and the latest day's volume vs the trailing 28-day median.

    Tolerances are per source (``VOLUME_TOLERANCE``); steady daily feeds use 5 % / 20 %.
    """
    amber_drop, red_drop = VOLUME_TOLERANCE.get(source, (DAY_DROP_AMBER, DAY_DROP_RED))
    if counts.empty:
        return [Check("Volume", source, RED, "No rows in the last 35 days")]
    c = counts.sort_values(date_col)
    median = float(c[count_col].tail(28).median())
    if median <= 0:
        return [Check("Volume", source, RED, "Median daily volume is zero")]
    drop = 1 - c[count_col] / median
    short = c[drop > amber_drop]
    latest_drop = float(drop.iloc[-1])
    status = RED if latest_drop > red_drop else AMBER if latest_drop > amber_drop or len(short) else GREEN
    latest = pd.Timestamp(c[date_col].iloc[-1])
    detail = (f"Latest day {latest:%d %b}: {int(c[count_col].iloc[-1]):,} rows vs median {median:,.0f}"
              + (f" · {len(short)} incomplete day(s) in the window" if len(short) else ""))
    return [Check("Volume", source, status, detail)]


def rebuilt(last_altered: dict[str, datetime | None]) -> list[Check]:
    """Informational: when each mart model was last rebuilt (not a success signal)."""
    return [Check("Model", name, GREEN if ts is not None else AMBER,
                  f"Model last rebuilt: {pd.Timestamp(ts):%d %b %Y %H:%M}" if ts is not None else "Rebuild time unknown")
            for name, ts in last_altered.items()]


def overall(checks: list[Check]) -> str:
    return max((c.status for c in checks), key=lambda s: STATUS_ORDER.get(s, 0)) if checks else AMBER


def to_frame(checks: list[Check]) -> pd.DataFrame:
    return pd.DataFrame([vars(c) for c in checks], columns=["area", "name", "status", "detail"])
