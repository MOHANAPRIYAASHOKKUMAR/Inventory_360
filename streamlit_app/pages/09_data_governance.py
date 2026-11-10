import pandas as pd
import streamlit as st

from components.layout import page_header
from inventory360.data_access.connection import run_query
from inventory360.utils.config import APP_SCHEMA, DATABASE

freshness = run_query(
    f"""
    select table_schema, table_name, table_type, row_count, bytes, last_altered, comment
    from {DATABASE}.information_schema.tables
    where table_schema in ('RAW', 'STAGING', 'MARTS', 'APP')
    order by decode(table_schema, 'RAW', 1, 'STAGING', 2, 'MARTS', 3, 4), table_name
    """,
    ttl=600,
)
as_of = run_query(f"select max(snapshot_date) as d from {DATABASE}.MARTS.FCT_INVENTORY_DAILY", ttl=600)["d"].iloc[0]

page_header("Data & governance", "Lineage, freshness, KPI definitions and access model", ":material/verified_user:", as_of)

tab_lineage, tab_catalog, tab_kpis, tab_access = st.tabs(
    [":material/account_tree: Lineage", ":material/database: Catalogue", ":material/menu_book: KPI dictionary",
     ":material/admin_panel_settings: Access & audit"]
)

with tab_lineage:
    st.mermaid_chart(
        """
        flowchart LR
          subgraph Sources
            ERP[ERP - items, vendors, POs]
            WMS[WMS - sites, stock]
            POS[POS / e-com - demand]
            TMS[TMS - shipments]
            FIN[Finance - GL, budgets]
          end
          subgraph RAW[RAW schema]
            R1[(Landing tables)]
          end
          subgraph STAGING[STAGING - dbt views]
            S1[stg_* cleansed & conformed]
          end
          subgraph MARTS[MARTS - dbt tables]
            D[dim_product / supplier / warehouse / date]
            F[fct_inventory_daily / purchase_orders / shipments]
            R[rpt_inventory_position / kpis / supplier / logistics / budget / utilisation]
          end
          APP[Streamlit in Snowflake - Inventory 360]
          WB[(APP.REPLENISHMENT_REQUESTS)]
          ERP & WMS & POS & TMS & FIN --> R1 --> S1 --> D & F
          D & F --> R --> APP
          APP -- planner approvals --> WB -- outbox --> ERP
        """,
        alt="Data lineage from source systems to the Inventory 360 app",
    )
    st.caption("Transformations are version-controlled in `dbt_inventory/` and deployed via CI/CD (GitHub Actions).")

with tab_catalog:
    cols = st.columns(4)
    for col, schema in zip(cols, ["RAW", "STAGING", "MARTS", "APP"]):
        s = freshness[freshness["table_schema"] == schema]
        col.metric(f"{schema} objects", len(s), border=True,
                   help=f"{int(s['row_count'].fillna(0).sum()):,} rows")
    st.dataframe(
        freshness, hide_index=True, alt="Data catalogue", height=460,
        column_config={
            "table_schema": "Schema", "table_name": "Object", "table_type": "Type",
            "row_count": st.column_config.NumberColumn("Rows", format="%,d"),
            "bytes": st.column_config.NumberColumn("Size", format="bytes"),
            "last_altered": st.column_config.DatetimeColumn("Last refreshed", format="DD MMM YYYY HH:mm"),
            "comment": st.column_config.TextColumn("Description", width="large"),
        },
    )

with tab_kpis:
    kpis = pd.DataFrame(
        [
            ("Stock value at cost", "Σ on-hand qty × standard unit cost", "Inventory", "Lower is better at constant availability"),
            ("On-shelf availability", "1 − (SKU-locations with zero stock ÷ ranged SKU-locations)", "Inventory", "Target ≥ 96%"),
            ("Demand fill rate", "Units sold ÷ units demanded", "Inventory", "Target ≥ 97%"),
            ("Lost sales", "(Units demanded − units sold) × retail price", "Inventory", "Opportunity cost of stockouts"),
            ("Stock turn", "Annualised cost of sales ÷ average stock value", "Inventory", "Higher is better"),
            ("Days of cover", "Stock value ÷ average daily cost of sales (network) or on-hand ÷ avg daily demand (SKU)", "Inventory", "Policy band 7-60 days"),
            ("Safety stock", "z(service level) × σ(daily demand) × √(lead time)", "Replenishment", "A 95% / B 90% / C 85% service"),
            ("Reorder point", "Mean daily demand × lead time + safety stock", "Replenishment", "Order when inventory position falls below"),
            ("Inventory position", "On hand − allocated + open and in-transit PO quantity", "Replenishment", ""),
            ("OTIF", "PO lines received on or before due date AND in full ÷ PO lines received", "Supplier", "Target ≥ 90%"),
            ("Supplier score", "50% OTIF + 25% unit fill + 15% lead-time stability + 10% landed-cost efficiency", "Supplier", "≥85 Low risk, 72-85 Medium, <72 High"),
            ("Landed cost uplift", "(Freight + duty) ÷ purchase value", "Logistics", ""),
            ("Cost per unit dispatched", "Warehouse operating cost ÷ units dispatched", "Warehouse", ""),
            ("Budget variance", "Actual − budget (positive = overspend)", "Finance", "Amber > 3%, Red > 7%"),
        ],
        columns=["KPI", "Definition", "Domain", "Target / note"],
    )
    st.dataframe(kpis, hide_index=True, alt="KPI dictionary",
                 column_config={"Definition": st.column_config.TextColumn(width="large")})

with tab_access:
    roles = pd.DataFrame(
        [
            ("INV360_VIEWER", "Management, finance", "Read MARTS and app"),
            ("INV360_PLANNER", "Supply & replenishment planners", "Viewer + submit replenishment orders"),
            ("INV360_ENGINEER", "Data engineering", "Planner + build RAW / STAGING / MARTS"),
            ("INV360_ADMIN", "Platform owner", "Engineer + app deployment, warehouse admin"),
        ],
        columns=["Role", "Persona", "Capability"],
    )
    st.dataframe(roles, hide_index=True, alt="Role-based access model")
    audit = run_query(
        f"select event_ts, user_name, event_type, event_detail from {APP_SCHEMA}.APP_AUDIT_LOG order by event_ts desc limit 200",
        ttl=0,
    )
    st.subheader("Audit log", anchor=False)
    if audit.empty:
        st.caption("No application events recorded yet.")
    else:
        st.dataframe(audit, hide_index=True, alt="Application audit log",
                     column_config={"event_ts": st.column_config.DatetimeColumn("Time", format="DD MMM YYYY HH:mm:ss")})
