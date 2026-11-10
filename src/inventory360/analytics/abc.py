"""ABC (Pareto) segmentation of the range by sales value."""
from __future__ import annotations

import pandas as pd


def abc_classify(df: pd.DataFrame, value_col: str, a_cut: float = 0.80, b_cut: float = 0.95,
                 key: str = "sku") -> pd.DataFrame:
    """Add cumulative share and ABC class (A = top 80% of value, B = next 15%, C = tail)."""
    out = df.groupby(key, as_index=False)[value_col].sum().sort_values(value_col, ascending=False)
    total = out[value_col].sum()
    out["share"] = out[value_col] / total if total else 0.0
    out["cumulative_share"] = out["share"].cumsum()
    out["rank"] = range(1, len(out) + 1)
    out["rank_pct"] = out["rank"] / len(out) if len(out) else 0.0
    out["abc_class"] = pd.cut(
        out["cumulative_share"].shift(fill_value=0),
        bins=[-1, a_cut, b_cut, 2],
        labels=["A", "B", "C"],
    ).astype(str)
    return out.reset_index(drop=True)
