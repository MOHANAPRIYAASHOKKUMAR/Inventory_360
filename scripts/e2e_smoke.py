"""End-to-end smoke test for Inventory 360 (headless, against live Snowflake data).

Sections:
  1. Pages        every page x every tier renders without errors; tier rules hold
  2. Filters      every global filter alone, in combination, presets, reset, chip removal
  3. Controls     every page-level control (segmented, pills, selectbox, radio, toggle, slider) per option
  4. Drill-downs  every KPI drill and insight "Explore" on the overview
  5. Write path   planner approves + submits replenishment lines; rows verified in Snowflake, then removed
  6. Data         overview net sales == direct SQL for the same window
  7. Security     Snowflake rejects a viewer INSERT; planner INSERT allowed (rolled back); caller grants exist

    $env:SNOWFLAKE_DEFAULT_CONNECTION_NAME = "<connection>"
    .venv\\Scripts\\python.exe scripts\\e2e_smoke.py            # all sections
    .venv\\Scripts\\python.exe scripts\\e2e_smoke.py --no-write # skip section 5
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = str(ROOT / "streamlit_app" / "streamlit_app.py")
PAGES = sorted(p.name for p in (ROOT / "streamlit_app" / "pages").glob("*.py"))
CONN = os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "")
SNOW = str(ROOT / ".venv" / "Scripts" / "snow.exe")
sys.path[:0] = [str(ROOT / "src")]

RESULTS: list[tuple[str, str, bool, str]] = []   # section, name, ok, detail


def record(section: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((section, name, ok, detail))
    print(f"  {'ok  ' if ok else 'FAIL'} {section:<9} {name:<62} {detail[:110]}", flush=True)


def errors(at: AppTest) -> list[str]:
    return [str(e.value) for e in at.error] + [str(x.value) for x in at.exception]


def app(tier: str = "developer", page: str | None = None, seed: dict | None = None) -> AppTest:
    """Run the app through its navigation script on ``page`` with session state ``seed`` (filters).

    ``AppTest.switch_page`` runs a page file on its own (no navigation script, no sidebar), so
    pages are opened as the default page via the local-only INV360_START_PAGE hook instead.
    """
    os.environ["INV360_TIER_OVERRIDE"] = tier
    os.environ["INV360_START_PAGE"] = page or "01_executive_overview.py"
    at = AppTest.from_file(ENTRY, default_timeout=300)
    for key, value in (seed or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def check(section: str, name: str, at: AppTest, extra_ok: bool = True, detail: str = "") -> bool:
    errs = errors(at)
    ok = not errs and extra_ok
    record(section, name, ok, errs[0] if errs else detail)
    return ok


# --------------------------------------------------------------------------- #
# 1. Pages x tiers
# --------------------------------------------------------------------------- #
def section_pages() -> None:
    print("\n[1] Pages x tiers", flush=True)
    for tier in ("viewer", "planner", "developer"):
        for page in PAGES:
            if page == "09_data_governance.py" and tier != "developer":
                at = app(tier, page)   # not registered for this tier -> app falls back to the overview
                reachable = any(t.value == "Data & governance" for t in at.title)
                record("pages", f"{tier}: governance page blocked", not reachable)
                continue
            at = app(tier, page)
            expected = {"01": "Executive overview", "02": "Inventory health", "03": "Replenishment planner",
                        "04": "Supplier performance", "05": "Logistics", "06": "Warehouse", "07": "Budget",
                        "08": "Demand forecast", "09": "Data & governance", "10": "Customers"}[page[:2]]
            on_page = any(expected.lower() in str(t.value).lower() for t in at.title)
            has_filters = len(at.sidebar.multiselect) == 6
            extra, detail = on_page and has_filters, f"title ok={on_page}, sidebar filters={has_filters}"
            if page == "03_replenishment.py":
                has_submit = any(b.label == "Submit approved orders" for b in at.button)
                extra = extra and has_submit == (tier != "viewer")
                detail += f", submit visible={has_submit}"
            check("pages", f"{tier}: {page}", at, extra, detail)


# --------------------------------------------------------------------------- #
# 2. Global filters (applied on every page)
# --------------------------------------------------------------------------- #
def _options(at: AppTest, key: str) -> list:
    return list(at.sidebar.multiselect(key=key).options)


def section_filters() -> None:
    print("\n[2] Global filters", flush=True)
    from inventory360.data_access import queries  # real option values (the harness only exposes labels)

    wh_df = queries.load_warehouses()
    regions = sorted(wh_df["uk_region"].dropna().unique())
    warehouses = wh_df["warehouse_code"].tolist()
    cats = sorted(queries.load_products()["category"].unique())
    sups = queries.load_suppliers()["supplier_id"].tolist()
    custs = queries.load_customers()["customer_id"].tolist()
    probe = app("developer")
    lo, hi = probe.session_state["gf_dates"]
    lo_bound = queries.load_date_bounds()[0].date()
    sys.path.insert(0, str(ROOT / "streamlit_app"))
    from components.filters import _preset_range as preset_range

    scenarios = {
        "region = Scotland": {"gf_regions": [r for r in regions if "Scotland" in r][:1] or regions[:1]},
        "2 regions": {"gf_regions": regions[:2]},
        "warehouse = first": {"gf_warehouses": warehouses[:1]},
        "category = first": {"gf_categories": cats[:1]},
        "supplier = first": {"gf_suppliers": sups[:1]},
        "customer = first": {"gf_customers": custs[:1]},
        "combined region+category+supplier": {"gf_regions": regions[:1], "gf_categories": cats[:1], "gf_suppliers": sups[:1]},
    }
    presets = ["4W", "26W", "52W", "YTD"]

    for page in PAGES:
        for label, sel in scenarios.items():
            at = app("developer", page, sel)
            chips = [b for b in at.button if b.key and b.key.startswith("chip_") and b.key != "chip_clear"]
            check("filters", f"{page}: {label}", at, bool(chips), f"{len(chips)} chip(s)")
        for p in presets:
            start, end = preset_range(p, lo_bound, hi)
            at = app("developer", page, {"gf_preset": p, "gf_dates": (start, end)})
            f = at.session_state["gf_current"]
            check("filters", f"{page}: period {p}", at, (f.start, f.end) == (start, end), f"{start}..{end}")
        at = app("developer", page, {"gf_preset": None, "gf_dates": (hi - timedelta(days=6), hi)})
        check("filters", f"{page}: custom 7-day range", at,
              (at.session_state["gf_current"].start, at.session_state["gf_current"].end) == (hi - timedelta(days=6), hi))

    # Product filter cascades from category; warehouse list cascades from region
    at = app("developer")
    total_products = len(_options(at, "gf_products"))
    at = app("developer", None, {"gf_categories": cats[:1]})
    record("filters", "product list narrows with category", len(_options(at, "gf_products")) < total_products,
           f"{total_products} -> {len(_options(at, 'gf_products'))}")
    at = app("developer", None, {"gf_regions": regions[:1]})
    record("filters", "warehouse list narrows with region", len(_options(at, "gf_warehouses")) < len(warehouses),
           f"{len(warehouses)} -> {len(_options(at, 'gf_warehouses'))}")
    at = app("developer", None, {"gf_warehouses": warehouses[:1]})
    record("filters", "customer list narrows with warehouse", len(_options(at, "gf_customers")) < len(custs),
           f"{len(custs)} -> {len(_options(at, 'gf_customers'))}")

    # Conflict pruning: a warehouse outside the selected region is removed with a toast
    home = wh_df.set_index("warehouse_code")["uk_region"]
    other = next(r for r in regions if r != home[warehouses[0]])
    at = app("developer", None, {"gf_warehouses": warehouses[:1], "gf_regions": [other]})
    pruned = warehouses[0] not in (at.session_state["gf_warehouses"] or [])
    check("filters", "conflicting warehouse removed when region changes", at, pruned and len(at.toast) > 0,
          f"toast={[t.value for t in at.toast][:1]}")

    # Filters really narrow the data: overview net sales with one category < unfiltered
    def net_sales(at):
        m = next((m for m in at.metric if m.label == "Net sales"), None)
        return m.value if m else None
    full, one = net_sales(app("developer")), net_sales(app("developer", None, {"gf_categories": cats[:1]}))
    record("filters", "category filter changes Net sales KPI", full is not None and one is not None and full != one,
           f"all {full} vs {cats[0]} {one}")

    # Chip removal and Clear filters: the on_click callbacks update the filter state
    at = app("developer", "01_executive_overview.py", {"gf_categories": cats[:2]})
    chip = next(b for b in at.button if b.key and b.key.startswith("chip_gf_categories"))
    chip.click().run()
    record("filters", "chip click removes one filter", len(at.session_state["gf_categories"]) == 1)
    at.button(key="chip_clear").click().run()
    cleared = not any(at.session_state[k] for k in
                      ("gf_regions", "gf_warehouses", "gf_categories", "gf_suppliers", "gf_products", "gf_customers"))
    record("filters", "Clear filters resets every selection", cleared)
    at = app("developer", None, {"gf_suppliers": sups[:1]})
    next(b for b in at.sidebar.button if "Reset" in b.label).click().run()
    record("filters", "sidebar Reset filters", not at.session_state["gf_suppliers"])

    # Filters are global: the same selection is honoured by every page
    for page in ("02_inventory_health.py", "10_customers_and_sales.py"):
        at = app("developer", page, {"gf_categories": cats[:1]})
        scope = " ".join(str(c.value) for c in at.caption)
        check("filters", f"{page}: scope line reports the category filter", at, "Category" in scope)


# --------------------------------------------------------------------------- #
# 3. Page-level controls
# --------------------------------------------------------------------------- #
SIDEBAR_KEYS = {"gf_preset", "gf_dates", "gf_regions", "gf_warehouses", "gf_categories", "gf_suppliers",
                "gf_products", "gf_customers"}


def _controls(at: AppTest):
    for kind in ("segmented_control", "pills", "radio", "selectbox"):
        for w in getattr(at.main, kind):
            if w.key and w.key not in SIDEBAR_KEYS and not w.key.startswith("chip_"):
                yield kind, w


def section_controls() -> None:
    print("\n[3] Page controls", flush=True)
    for page in PAGES:
        base = app("developer", page)
        found = [(k, w.key, list(w.options)) for k, w in _controls(base)]
        for t in base.main.toggle:
            found.append(("toggle", t.key, [True, False]))
        for s in base.main.slider:
            if s.key:
                found.append(("slider", s.key, [s.min, s.max]))
        if not found:
            record("controls", f"{page}: (no page controls)", True)
        for kind, key, options in found:
            for opt in options[:6]:
                at = app("developer", page)
                widget = getattr(at, kind)(key=key)
                if kind == "pills" and getattr(widget, "proto", None) is not None and widget.proto.click_mode == 0:
                    value = [opt]   # multi-select pills take a list
                else:
                    value = opt
                try:
                    widget.set_value(value).run()
                except Exception as exc:  # noqa: BLE001
                    record("controls", f"{page}: {key} = {opt}", False, str(exc))
                    continue
                check("controls", f"{page}: {key} = {opt}", at)
            # re-click the selected option: single-choice toggles must stay selected
            if kind == "segmented_control":
                at = app("developer", page)
                at.segmented_control(key=key).set_value(options[0]).run()
                at.segmented_control(key=key).set_value(options[0]).run()
                check("controls", f"{page}: {key} stays selected on re-click", at,
                      at.segmented_control(key=key).value is not None)


# --------------------------------------------------------------------------- #
# 4. Drill-downs
# --------------------------------------------------------------------------- #
def section_drills() -> None:
    print("\n[4] Drill-downs", flush=True)
    base = app("developer", "01_executive_overview.py")
    keys = [b.key for b in base.button if b.key and (b.key.startswith("drill_") or b.key.startswith("ins_"))]
    for key in keys:
        at = app("developer", "01_executive_overview.py")
        at.button(key=key).click().run()
        check("drills", f"overview {key}", at, len(at.tabs) > 0 or bool(at.dataframe), f"{len(at.tabs)} tabs")
    # Table row drill-downs (category scorecard)
    for page, table_key in (("01_executive_overview.py", "exec_cat"),):
        at = app("developer", page)
        df = at.get_by_key(table_key) if hasattr(at, "get_by_key") else None
        record("drills", f"{page}: {table_key} table present", df is not None)


# --------------------------------------------------------------------------- #
# 5. Write path (planner submits; rows verified then removed)
# --------------------------------------------------------------------------- #
def snow_sql(query: str, role: str | None = None) -> subprocess.CompletedProcess:
    cmd = [SNOW, "sql", "-c", CONN, "--warehouse", "INV360_WH", "--format", "json", "-q", query]
    if role:
        cmd += ["--role", role]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def snow_rows(query: str, role: str | None = None) -> list[dict]:
    """Rows of the last statement (snow returns a list per statement for multi-statement input)."""
    import json

    res = snow_sql(query, role)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[-300:] or res.stdout.strip()[-300:])
    data = json.loads(res.stdout)
    if data and isinstance(data[0], list):
        data = data[-1]
    return data


def section_write() -> None:
    print("\n[5] Write path (replenishment submit)", flush=True)
    from inventory360.utils.config import APP_SCHEMA

    note = f"E2E SMOKE TEST {uuid.uuid4().hex[:8]}"
    started = snow_rows("select current_timestamp()::varchar as t")[0]["T"]
    at = app("planner", "03_replenishment.py")
    submit = next((b for b in at.button if b.label == "Submit approved orders"), None)
    record("write", "planner sees enabled Submit (P1 lines pre-approved)", submit is not None and not submit.disabled)
    if submit is None or submit.disabled:
        return
    submit.click().run()
    dialog_ok = any(b.label == "Confirm and submit" for b in at.button) and any(t.label == "Planner note" for t in at.text_area)
    check("write", "Submit opens the confirmation dialog", at, dialog_ok)

    # AppTest cannot click inside st.dialog (the click reruns the page without the open dialog), so the
    # submit runs through the app's own write function with the Planner tier and real P1 lines.
    import streamlit as st

    from inventory360.business_logic.replenishment import Scenario, recalculate_plan
    from inventory360.data_access import queries
    from inventory360.utils.access import AccessDenied, Tier

    f = at.session_state["gf_current"]
    plan = recalculate_plan(queries.inventory_position(f), Scenario())
    lines = plan[(plan["scenario_priority"] == "P1 - Urgent") & (plan["scenario_order_qty"] > 0)].head(3)
    lines = lines.assign(approved_qty=lines["scenario_order_qty"], recommended_order_qty=lines["scenario_order_qty"],
                         replenishment_priority=lines["scenario_priority"])
    st.session_state["access_tier"] = Tier.VIEWER
    try:
        queries.submit_replenishment_requests(lines, note)
        record("write", "viewer tier blocked by the app before INSERT", False)
    except AccessDenied:
        record("write", "viewer tier blocked by the app before INSERT", True)
    st.session_state["access_tier"] = Tier.PLANNER
    written = queries.submit_replenishment_requests(lines, note)
    record("write", "planner submit writes order lines", written == len(lines) > 0, f"{written} lines")

    rows = snow_rows(f"select count(*) as n, sum(order_value_gbp) as v from {APP_SCHEMA}.REPLENISHMENT_REQUESTS "
                     f"where planner_note = '{note}'")[0]
    record("write", "rows landed in APP.REPLENISHMENT_REQUESTS", int(rows["N"]) > 0, f"{rows['N']} rows, £{rows['V']}")
    audit = snow_rows(f"select count(*) as n from {APP_SCHEMA}.APP_AUDIT_LOG where event_type = 'REPLENISHMENT_SUBMITTED' "
                      f"and event_ts >= '{started}'::timestamp_ltz")[0]
    record("write", "audit event written", int(audit["N"]) >= 1, f"{audit['N']} event(s)")

    at = app("planner", "03_replenishment.py")
    outbox = [d.value for d in at.dataframe if hasattr(d.value, "columns") and "planner_note" in d.value.columns]
    record("write", "outbox shows the submitted lines", any((df["planner_note"] == note).any() for df in outbox))

    cleanup = snow_sql(
        f"begin; delete from {APP_SCHEMA}.REPLENISHMENT_REQUESTS where planner_note = '{note}'; "
        f"delete from {APP_SCHEMA}.APP_AUDIT_LOG where event_type = 'REPLENISHMENT_SUBMITTED' "
        f"and event_ts >= '{started}'::timestamp_ltz and user_name = current_user(); commit;", role="SYSADMIN")
    left = snow_rows(f"select count(*) as n from {APP_SCHEMA}.REPLENISHMENT_REQUESTS where planner_note = '{note}'")[0]
    record("write", "test rows removed", cleanup.returncode == 0 and int(left["N"]) == 0, f"{left['N']} left")


# --------------------------------------------------------------------------- #
# 6. Data correctness
# --------------------------------------------------------------------------- #
def section_data() -> None:
    print("\n[6] Data correctness", flush=True)
    from inventory360.utils.config import MARTS

    at = app("developer", "01_executive_overview.py")
    lo, hi = at.session_state["gf_dates"]
    card = next((m for m in at.metric if m.label == "Net sales"), None)
    sql_m = float(snow_rows(f"select round(sum(net_sales_gbp) / 1e6, 1) as m from {MARTS}.FCT_CUSTOMER_SALES_DAILY "
                            f"where sales_date between '{lo}' and '{hi}'")[0]["M"])
    shown = card.value if card else "?"
    record("data", "overview Net sales card == SQL", shown == f"£{sql_m:.1f}M", f"card {shown} vs SQL £{sql_m}M ({lo}..{hi})")
    latest = snow_rows(f"select max(snapshot_date)::varchar as d from {MARTS}.FCT_INVENTORY_DAILY")[0]["D"]
    record("data", "date filter upper bound = latest mart date", latest == str(hi), f"mart {latest} vs filter {hi}")


# --------------------------------------------------------------------------- #
# 7. Snowflake enforcement
# --------------------------------------------------------------------------- #
def section_security() -> None:
    print("\n[7] Snowflake enforcement", flush=True)
    insert = ("insert into INVENTORY_360_DB.APP.REPLENISHMENT_REQUESTS (as_of_date, warehouse_code, sku, supplier_id, "
              "recommended_qty, approved_qty, unit_cost_gbp, order_value_gbp, priority, status, planner_note) "
              "values (current_date(), 'DC01', 'X', 'X', 0, 0, 0, 0, 'P4 - Routine', 'SUBMITTED', 'E2E')")
    v = snow_sql(f"use secondary roles none; {insert}", role="INV360_VIEWER")
    record("security", "viewer INSERT rejected by Snowflake", v.returncode != 0 and "privilege" in (v.stdout + v.stderr).lower())
    p = snow_sql(f"use secondary roles none; begin; {insert}; rollback;", role="INV360_PLANNER")
    record("security", "planner INSERT allowed (rolled back)", p.returncode == 0, p.stderr.strip()[-120:])
    r = snow_sql("select count(*) as n from INVENTORY_360_DB.MARTS.FCT_INVENTORY_DAILY", role="INV360_VIEWER")
    record("security", "viewer can read marts", r.returncode == 0)

    def denied(res: subprocess.CompletedProcess) -> bool:
        return res.returncode != 0 and any(t in (res.stdout + res.stderr).lower()
                                           for t in ("privilege", "not authorized", "does not exist"))

    w = snow_sql("use secondary roles none; alter warehouse INV360_WH suspend", role="INV360_VIEWER")
    record("security", "viewer cannot suspend the warehouse (no OPERATE)", denied(w))
    u = snow_sql("use secondary roles none; begin; update INVENTORY_360_DB.APP.REPLENISHMENT_REQUESTS "
                 "set status = 'APPROVED' where 1 = 0; rollback;", role="INV360_PLANNER")
    record("security", "planner cannot UPDATE orders (status change)", denied(u))
    a = snow_sql("use secondary roles none; begin; update INVENTORY_360_DB.APP.APP_AUDIT_LOG "
                 "set event_type = 'X' where 1 = 0; rollback;", role="INV360_PLANNER")
    record("security", "planner cannot UPDATE the audit log", denied(a))
    v = snow_sql("use secondary roles none; select count(*) from INVENTORY_360_DB.APP.APP_AUDIT_LOG", role="INV360_VIEWER")
    record("security", "viewer cannot read the audit log", denied(v))
    o = snow_sql("use secondary roles none; select count(*) from INVENTORY_360_DB.APP.V_REPLENISHMENT_OUTBOX",
                 role="INV360_VIEWER")
    record("security", "viewer can read the outbox view", o.returncode == 0, o.stderr.strip()[-120:])
    g = snow_sql("show caller grants to role INV360_ADMIN", role="ACCOUNTADMIN")
    record("security", "caller grants present on app owner", g.returncode == 0 and "INSERT" in g.stdout and "SELECT" in g.stdout)
    s = snow_sql("show streamlits like 'INVENTORY_360' in schema INVENTORY_360_DB.APP", role="INV360_ADMIN")
    record("security", "app deployed and owned by INV360_ADMIN", '"INV360_ADMIN"' in s.stdout)


if __name__ == "__main__":
    t0 = time.time()
    sections = {"pages": section_pages, "filters": section_filters, "controls": section_controls,
                "drills": section_drills, "write": section_write, "data": section_data, "security": section_security}
    chosen = [a for a in sys.argv[1:] if a in sections] or list(sections)
    if "--no-write" in sys.argv:
        chosen = [s for s in chosen if s != "write"]
    for name in chosen:
        try:
            sections[name]()
        except Exception as exc:  # noqa: BLE001 - a crashing section is a failure, keep going
            import traceback

            record(name, "section crashed", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
    failed = [r for r in RESULTS if not r[2]]
    by = {}
    for s, _, ok, _ in RESULTS:
        by.setdefault(s, [0, 0])[0 if ok else 1] += 1
    print(f"\n==== {len(RESULTS) - len(failed)} passed, {len(failed)} failed in {time.time() - t0:.0f}s")
    for s, (ok, bad) in by.items():
        print(f"  {s:<9} {ok} passed, {bad} failed")
    for s, n, _, d in failed:
        print(f"  FAIL {s}: {n} - {d}")
    sys.exit(1 if failed else 0)
