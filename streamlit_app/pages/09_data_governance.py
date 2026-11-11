import pandas as pd
import streamlit as st

from components import charts, filters
from components.layout import download, filter_scope, kpi, num, page_header, section, table
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.data_access import queries
from inventory360.utils.formatting import fmt_int, fmt_pct

f = filters.current()
as_of = st.session_state["gf_as_of"]
page_header("Data & governance", "Data freshness, catalogue, lineage, KPI definitions and access model", as_of=as_of)
filter_scope(f, {}, use_date=False, note="platform metadata is not filtered by business dimensions")

cat = queries.load_catalogue()
now = pd.Timestamp.now(tz=cat["last_altered"].dt.tz) if cat["last_altered"].dt.tz is not None else pd.Timestamp.now()
cat["age_hours"] = (now - cat["last_altered"]).dt.total_seconds() / 3600
cat["freshness"] = cat["age_hours"].map(lambda v: rag_for("freshness_hours", v))
data_age_days = (pd.Timestamp.now().normalize() - pd.Timestamp(as_of).normalize()).days

cols = st.columns(4)
for col, schema in zip(cols[:3], ["RAW", "STAGING", "MARTS"]):
    s = cat[cat["table_schema"] == schema]
    with col:
        kpi(f"{schema} objects", fmt_int(len(s)), help=f"{int(s['row_count'].fillna(0).sum()):,} rows")
with cols[3]:
    kpi("Latest business date", f"{pd.Timestamp(as_of):%d %b %Y}",
        status="Green" if data_age_days <= 1 else "Amber" if data_age_days <= 2 else "Red",
        status_text=f"{data_age_days} day(s) behind today")

tab_cat, tab_lineage, tab_kpi, tab_access = st.tabs(["Catalogue & freshness", "Lineage", "KPI dictionary", "Access & audit"])

with tab_cat:
    with st.container(horizontal=True, vertical_alignment="bottom"):
        schemas = st.pills("Schema", ["RAW", "STAGING", "MARTS", "APP"], selection_mode="multi", key="gov_schema")
        search = st.text_input("Search objects", key="gov_search", placeholder="Name or description")
    view = cat
    if schemas:
        view = view[view["table_schema"].isin(schemas)]
    if search:
        s = search.lower()
        view = view[view["table_name"].str.lower().str.contains(s, regex=False)
                    | view["comment"].fillna("").str.lower().str.contains(s, regex=False)]
    c1, c2 = st.columns([1, 2])
    with c1:
        with section("Rows by schema"):
            agg = view.groupby("table_schema", as_index=False)["row_count"].sum()
            charts.show(charts.bar(agg, "table_schema", "row_count", kind="num", height=260, order=["RAW", "STAGING", "MARTS", "APP"],
                                   text=True), alt="Row counts by schema")
    with c2:
        with section("Largest tables"):
            big = view.dropna(subset=["row_count"]).nlargest(10, "row_count")
            charts.show(charts.bar(big, "table_name", "row_count", "table_schema", kind="num", horizontal=True, height=260,
                                   order=big["table_name"].tolist()), alt="Largest tables by row count")
    with section("Data catalogue", "Select an object to see its columns"):
        sel = table(
            view, key="gov_cat", alt="Data catalogue", csv_name="data catalogue", rag_cols=["freshness"], height=420,
            columns=["table_schema", "table_name", "table_type", "row_count", "bytes", "last_altered", "age_hours", "freshness",
                     "comment"],
            column_config={"table_schema": "Schema", "table_name": "Object", "table_type": "Type", "row_count": num("Rows"),
                           "bytes": st.column_config.NumberColumn("Size", format="bytes"),
                           "last_altered": st.column_config.DatetimeColumn("Last altered", format="DD MMM YYYY HH:mm"),
                           "age_hours": num("Age (h)", 1), "freshness": "Freshness",
                           "comment": st.column_config.TextColumn("Description", width="large")},
        )
    if sel is not None:
        with section(f"Columns · {sel['table_schema']}.{sel['table_name']}"):
            colsdf = queries.load_columns(sel["table_schema"], sel["table_name"])
            st.dataframe(colsdf, hide_index=True, alt="Column definitions",
                         column_config={"column_name": "Column", "data_type": "Type", "is_nullable": "Nullable",
                                        "comment": st.column_config.TextColumn("Description", width="large")})
            download(colsdf, f"{sel['table_name']} columns", key="dl_gov_cols")
    st.caption(f"Freshness: green ≤ {TARGETS['freshness_hours'].green:.0f} h since last change, amber ≤ "
               f"{TARGETS['freshness_hours'].amber:.0f} h, red beyond. Views report the time their definition changed.")

with tab_lineage:
    st.mermaid_chart(
        """
        flowchart LR
          subgraph Sources
            ERP[ERP - items, vendors, customers, POs]
            WMS[WMS - sites, stock]
            POS[POS - demand and sales]
            TMS[TMS - shipments]
            FIN[Finance - GL, budgets]
          end
          R1[(RAW landing tables)]
          S1[STAGING - stg_* views]
          D[MARTS dims - product, supplier, warehouse, customer, date]
          F[MARTS facts - inventory, customer sales, purchase orders, shipments]
          R[MARTS reports - position, KPIs, supplier, logistics, budget, utilisation]
          APP[Inventory 360 app]
          WB[(APP.REPLENISHMENT_REQUESTS)]
          ERP & WMS & POS & TMS & FIN --> R1 --> S1 --> D & F
          D & F --> R --> APP
          F --> APP
          APP -- planner approvals --> WB -- outbox --> ERP
        """,
        alt="Data lineage from source systems to the Inventory 360 app",
    )
    st.caption("Transformations are version-controlled in dbt_inventory/ and validated in CI (GitHub Actions).")

with tab_kpi:
    def fmt_target(t) -> str:
        sign = "≥" if t.higher_is_better else "≤"
        value = lambda v: f"{v:.0f} days" if t.fmt == "days" else f"{v:.0f}x" if t.fmt == "ratio" else fmt_pct(v, 0)  # noqa: E731
        return f"Green {sign} {value(t.green)} · amber {sign} {value(t.amber)} · red beyond"

    defs = {
        "availability": "1 − (SKU-locations with zero stock ÷ ranged SKU-locations)",
        "fill_rate": "Units sold ÷ units demanded",
        "otif": "Received PO lines delivered on or before due date and in full ÷ received lines",
        "on_time_arrival": "Delivered shipments arriving on or before planned date ÷ delivered shipments",
        "gross_margin": "(Net sales − cost of sales) ÷ net sales",
        "forecast_accuracy": "1 − WAPE over the last 26 fitted weeks",
        "stock_turns": "Annualised cost of sales ÷ average stock value",
        "days_cover": "Closing stock value ÷ average daily cost of sales",
        "utilisation_peak": "Peak pallets used ÷ pallet capacity (highest site)",
        "budget_variance": "(Actual − budget) ÷ budget; positive = overspend",
        "lost_sales_share": "Lost sales ÷ (net sales + lost sales)",
        "freshness_hours": "Hours since the object last changed",
    }
    kpis = pd.DataFrame([{"KPI": t.label, "Definition": defs.get(k, ""), "RAG bands": fmt_target(t)} for k, t in TARGETS.items()])
    table(kpis, key="gov_kpis", select=False, alt="KPI dictionary", csv_name="kpi dictionary",
          column_config={"Definition": st.column_config.TextColumn(width="large"),
                         "RAG bands": st.column_config.TextColumn(width="large")})

with tab_access:
    roles = pd.DataFrame([
        ("INV360_VIEWER", "Management, finance", "Read MARTS and app"),
        ("INV360_PLANNER", "Supply and replenishment planners", "Viewer + submit replenishment orders"),
        ("INV360_ENGINEER", "Data engineering", "Planner + build RAW / STAGING / MARTS"),
        ("INV360_ADMIN", "Platform owner", "Engineer + app deployment, warehouse administration"),
    ], columns=["Role", "Persona", "Capability"])
    st.dataframe(roles, hide_index=True, alt="Role-based access model")
    with section("Audit log", "Most recent 500 application events"):
        audit = queries.load_audit_log()
        if audit.empty:
            st.caption("No application events recorded yet.")
        else:
            audit["event_detail"] = audit["event_detail"].astype(str)
            table(audit, key="gov_audit", select=False, alt="Application audit log", csv_name="audit log",
                  column_config={"event_ts": st.column_config.DatetimeColumn("Time", format="DD MMM YYYY HH:mm:ss"),
                                 "user_name": "User", "event_type": "Event", "event_detail": "Detail"})
