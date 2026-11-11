"""CSV formula escaping and replenishment submit validation."""
import pandas as pd
import pytest

from inventory360.data_access.queries import validate_submission
from inventory360.utils.formatting import csv_safe


def test_csv_safe_escapes_formula_text_only():
    df = pd.DataFrame({"note": ["=HYPERLINK(\"x\")", "+1", "-cmd", "@SUM(A1)", "plain", None],
                       "qty": [-5, 1, 2, 3, 4, 5]})
    out = csv_safe(df)
    assert out["note"].tolist()[:5] == ["'=HYPERLINK(\"x\")", "'+1", "'-cmd", "'@SUM(A1)", "plain"]
    assert out["note"].iloc[5] is None
    assert out["qty"].tolist() == [-5, 1, 2, 3, 4, 5]          # numbers untouched
    assert df["note"].iloc[0] == "=HYPERLINK(\"x\")"            # input not mutated


def _lines(**over):
    row = {"approved_qty": 120, "recommended_order_qty": 100, "unit_cost_gbp": 4.5,
           "replenishment_priority": "P1 - Urgent", "warehouse_code": "DC01", "sku": "SRG-000001",
           "supplier_id": "SUP001"}
    row.update(over)
    return pd.DataFrame([row])


def test_valid_lines_pass():
    validate_submission(_lines())


@pytest.mark.parametrize("over", [
    {"approved_qty": -1}, {"approved_qty": 2.5}, {"approved_qty": 5_000_000}, {"approved_qty": None},
    {"unit_cost_gbp": -1}, {"replenishment_priority": "P0 - Hack"}, {"replenishment_priority": "None"},
    {"sku": ""}, {"warehouse_code": None},
])
def test_invalid_lines_rejected(over):
    with pytest.raises(ValueError):
        validate_submission(_lines(**over))
