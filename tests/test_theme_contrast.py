"""WCAG 2.1 contrast checks for the theme colour pairs (AA: 4.5:1 text, 3:1 large text / UI)."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "streamlit_app"))
sys.path.insert(0, str(ROOT / "src"))
THEME = tomllib.loads((ROOT / "streamlit_app/.streamlit/config.toml").read_text(encoding="utf-8"))["theme"]


def _lum(hex_colour: str) -> float:
    rgb = [int(hex_colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize(("fg", "bg", "minimum"), [
    (THEME["textColor"], THEME["backgroundColor"], 4.5),
    (THEME["textColor"], "#FFFFFF", 4.5),
    (THEME["textColor"], THEME["secondaryBackgroundColor"], 4.5),
    ("#FFFFFF", THEME["primaryColor"], 4.5),                       # primary button text
    (THEME["linkColor"], THEME["backgroundColor"], 4.5),
    (THEME["dataframeHeaderTextColor"], THEME["dataframeHeaderBackgroundColor"], 4.5),
    (THEME["sidebar"]["textColor"], THEME["sidebar"]["backgroundColor"], 4.5),
    (THEME["redColor"], "#FFFFFF", 4.5),
    (THEME["greenColor"], "#FFFFFF", 4.5),
    (THEME["orangeColor"], "#FFFFFF", 3.0),                        # amber is always paired with an icon + word
])
def test_theme_pairs_meet_wcag_aa(fg, bg, minimum):
    assert contrast(fg, bg) >= minimum, f"{fg} on {bg}: {contrast(fg, bg):.2f}"


def test_rag_table_text_colours_meet_aa():
    from components.layout import RAG_TEXT

    for colour in RAG_TEXT.values():
        assert contrast(colour, "#FFFFFF") >= 4.5, colour
