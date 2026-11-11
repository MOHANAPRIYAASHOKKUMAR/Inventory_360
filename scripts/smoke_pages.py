"""Headless smoke test: render every page per access tier against Snowflake.

Uses the local named connection (owner credentials) and INV360_TIER_OVERRIDE to
simulate each tier's UI. Snowflake-side enforcement is verified separately (see
docs/callers_rights_verification.md); this checks the app renders without errors.

    $env:SNOWFLAKE_DEFAULT_CONNECTION_NAME = "<connection>"
    .venv\\Scripts\\python.exe scripts\\smoke_pages.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "streamlit_app" / "streamlit_app.py"
PAGES = sorted(p.name for p in (ROOT / "streamlit_app" / "pages").glob("*.py"))
EXPECT_GOVERNANCE = {"viewer": False, "planner": False, "developer": True}


def run_tier(tier: str) -> list[str]:
    os.environ["INV360_TIER_OVERRIDE"] = tier
    failures = []
    for page in PAGES:
        at = AppTest.from_file(str(ENTRY), default_timeout=240)
        at.run()
        if page == "09_data_governance.py" and not EXPECT_GOVERNANCE[tier]:
            try:
                at.switch_page(f"pages/{page}").run()
            except Exception:  # noqa: BLE001 - expected: page not registered
                pass
            if any("Data & governance" == getattr(t, "value", "") for t in at.title):
                failures.append(f"{tier}: governance page reachable")
            continue
        at.switch_page(f"pages/{page}").run()
        errors = [e.value for e in at.error] + [str(x.value) for x in at.exception]
        if errors:
            failures.append(f"{tier} {page}: {errors[0][:300]}")
        if page == "03_replenishment.py":
            has_submit = any(b.label == "Submit approved orders" for b in at.button)
            if has_submit != (tier != "viewer"):
                failures.append(f"{tier}: submit button visible={has_submit}")
        if page == "01_executive_overview.py" and tier == "developer":
            for b in [b for b in at.button if b.key and (b.key.startswith("drill_") or b.key.startswith("ins_"))]:
                at2 = AppTest.from_file(str(ENTRY), default_timeout=240)
                at2.run()
                at2.switch_page(f"pages/{page}").run()
                at2.button(key=b.key).click().run()
                errs = [e.value for e in at2.error] + [str(x.value) for x in at2.exception]
                print(f"    drill {b.key:<28} {'FAIL' if errs else 'ok'}", flush=True)
                if errs:
                    failures.append(f"drill {b.key}: {errs[0][:300]}")
        print(f"  {tier:<9} {page:<32} {'FAIL' if errors else 'ok'}", flush=True)
    return failures


if __name__ == "__main__":
    tiers = sys.argv[1:] or ["viewer", "planner", "developer"]
    problems = [p for t in tiers for p in run_tier(t)]
    print("\n".join(problems) if problems else "ALL PAGES OK")
    sys.exit(1 if problems else 0)
