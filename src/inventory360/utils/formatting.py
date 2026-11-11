"""Display formatting helpers (UK conventions, GBP)."""
from __future__ import annotations

import math

# Leading characters that make Excel / Sheets treat a cell as a formula (CSV injection)
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(df):
    """Copy of ``df`` whose text cells cannot run as spreadsheet formulas when opened.

    Only string values are touched (prefixed with an apostrophe); numbers, including
    negatives, stay numeric.
    """
    out = df.copy()
    for col in out.select_dtypes(include=["object", "string"]).columns:
        out[col] = out[col].map(
            lambda v: f"'{v}" if isinstance(v, str) and v.startswith(_FORMULA_PREFIXES) else v)
    return out


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def fmt_gbp(value, decimals: int = 1) -> str:
    """Compact GBP: £1.2bn, £3.4M, £56.7k, £890."""
    if _is_missing(value):
        return "–"
    v = float(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        return f"{sign}£{v / 1e9:.{decimals}f}bn"
    if v >= 1e6:
        return f"{sign}£{v / 1e6:.{decimals}f}M"
    if v >= 1e3:
        return f"{sign}£{v / 1e3:.{decimals}f}k"
    return f"{sign}£{v:,.0f}"


def fmt_int(value) -> str:
    if _is_missing(value):
        return "–"
    v = float(value)
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f}M"
    if abs(v) >= 1e4:
        return f"{v / 1e3:.1f}k"
    return f"{v:,.0f}"


def fmt_pct(value, decimals: int = 1, signed: bool = False) -> str:
    """Format a ratio (0.123) as a percentage (12.3%)."""
    if _is_missing(value):
        return "–"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value * 100:.{decimals}f}%"


def fmt_days(value) -> str:
    if _is_missing(value):
        return "–"
    return f"{value:,.1f} days"


def pct_change(current, previous):
    """Relative change, or None when not computable."""
    if _is_missing(current) or _is_missing(previous) or previous == 0:
        return None
    return (current - previous) / abs(previous)
