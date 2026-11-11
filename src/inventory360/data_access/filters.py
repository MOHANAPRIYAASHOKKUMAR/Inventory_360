"""Global dashboard filters and their translation into parameterised SQL.

Filters are pushed down to Snowflake so pages only fetch aggregated results.
Each fact table declares which filter dimensions it supports through a column
mapping; dimensions a table cannot honour are reported as "not applicable" so
the UI can say so instead of silently ignoring them.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta

import pandas as pd

# Display order and labels for the global dimensions
DIMENSIONS = ("date", "region", "warehouse", "category", "supplier", "product", "customer")
LABELS = {
    "date": "Date range",
    "region": "Region",
    "warehouse": "Warehouse",
    "category": "Category",
    "supplier": "Supplier",
    "product": "Product",
    "customer": "Customer",
}
# Dimensions resolved through the product master when a table only carries SKU
PRODUCT_DIMENSIONS = ("category", "supplier", "product")


@dataclass(frozen=True)
class GlobalFilters:
    start: date
    end: date
    warehouses: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    suppliers: tuple[str, ...] = ()
    skus: tuple[str, ...] = ()
    customers: tuple[str, ...] = ()
    # Warehouse regions (UK region of the site). The UI resolves regions into
    # ``warehouses``, so SQL push-down only ever filters on warehouse codes.
    regions: tuple[str, ...] = ()

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def prior(self) -> GlobalFilters:
        """Equal-length window immediately before the current one."""
        end = self.start - timedelta(days=1)
        return replace(self, start=end - timedelta(days=self.days - 1), end=end)

    def selection(self, dimension: str) -> tuple[str, ...]:
        return {
            "region": self.regions,
            "warehouse": self.warehouses,
            "category": self.categories,
            "supplier": self.suppliers,
            "product": self.skus,
            "customer": self.customers,
        }.get(dimension, ())

    def active(self) -> list[str]:
        """Non-date dimensions with a selection."""
        return [d for d in DIMENSIONS[1:] if self.selection(d)]

    @property
    def narrows_products(self) -> bool:
        return bool(self.categories or self.suppliers or self.skus)


def product_scope(products: pd.DataFrame, f: GlobalFilters) -> tuple[str, ...] | None:
    """SKUs matching the category / supplier / product filters, or None when unfiltered."""
    if not f.narrows_products:
        return None
    p = products
    if f.categories:
        p = p[p["category"].isin(f.categories)]
    if f.suppliers:
        p = p[p["supplier_id"].isin(f.suppliers)]
    if f.skus:
        p = p[p["sku"].isin(f.skus)]
    return tuple(sorted(p["sku"].unique()))


def _in(col: str, values: Iterable) -> tuple[str, list]:
    values = list(values)
    if not values:
        return "1 = 0", []
    return f"{col} in ({', '.join('?' * len(values))})", values


def build_where(f: GlobalFilters, columns: Mapping[str, str], sku_scope: tuple[str, ...] | None = None,
                *, use_date: bool = True) -> tuple[str, list]:
    """Return (``where ...`` clause or empty string, qmark params).

    ``columns`` maps dimension -> SQL column; omit a dimension the table lacks.
    When the table has a product (SKU) column and ``sku_scope`` is given, the
    category / supplier / product filters are applied through that SKU list,
    so tables without category or supplier columns still honour them.
    """
    clauses: list[str] = []
    params: list = []

    def add(clause: tuple[str, list]) -> None:
        clauses.append(clause[0])
        params.extend(clause[1])

    if use_date and "date" in columns:
        clauses.append(f"{columns['date']} between ? and ?")
        params.extend([f.start.isoformat(), f.end.isoformat()])
    if f.warehouses and "warehouse" in columns:
        add(_in(columns["warehouse"], f.warehouses))
    if "product" in columns and sku_scope is not None:
        add(_in(columns["product"], sku_scope))
    else:
        for dim in PRODUCT_DIMENSIONS:
            if f.selection(dim) and dim in columns:
                add(_in(columns[dim], f.selection(dim)))
    if f.customers and "customer" in columns:
        add(_in(columns["customer"], f.customers))
    return (f"where {' and '.join(clauses)}" if clauses else ""), params


def applicability(f: GlobalFilters, columns: Mapping[str, str], *, use_date: bool = True) -> tuple[list[str], list[str]]:
    """Split the active filters into (applied, not applicable) dimension labels."""
    applied, ignored = [], []
    if use_date and "date" in columns:
        applied.append(LABELS["date"])
    for dim in f.active():
        supported = (dim in columns or (dim in PRODUCT_DIMENSIONS and "product" in columns)
                     or (dim == "region" and "warehouse" in columns))
        (applied if supported else ignored).append(LABELS[dim])
    return applied, ignored


def resolve_regions(warehouses: pd.DataFrame, regions: Iterable[str], selected: Iterable[str]) -> tuple[str, ...]:
    """Effective warehouse codes: the explicit selection, narrowed to the chosen regions.

    No regions -> the selection unchanged. Regions but no explicit warehouses -> every
    warehouse in those regions. Both -> the intersection.
    """
    regions, selected = tuple(regions), tuple(selected)
    if not regions:
        return selected
    in_region = warehouses.loc[warehouses["uk_region"].isin(regions), "warehouse_code"].tolist()
    if not selected:
        return tuple(sorted(in_region))
    return tuple(c for c in selected if c in set(in_region))


def apply_frame(df: pd.DataFrame, f: GlobalFilters, columns: Mapping[str, str],
                sku_scope: tuple[str, ...] | None = None, *, use_date: bool = True) -> pd.DataFrame:
    """In-memory equivalent of ``build_where`` for small, already-loaded frames."""
    mask = pd.Series(True, index=df.index)
    if use_date and "date" in columns:
        d = pd.to_datetime(df[columns["date"]])
        mask &= (d >= pd.Timestamp(f.start)) & (d <= pd.Timestamp(f.end))
    if f.warehouses and "warehouse" in columns:
        mask &= df[columns["warehouse"]].isin(f.warehouses)
    if "product" in columns and sku_scope is not None:
        mask &= df[columns["product"]].isin(sku_scope)
    else:
        for dim in PRODUCT_DIMENSIONS:
            if f.selection(dim) and dim in columns:
                mask &= df[columns[dim]].isin(f.selection(dim))
    if f.customers and "customer" in columns:
        mask &= df[columns["customer"]].isin(f.customers)
    return df[mask]
