import pandas as pd
import streamlit as st

from components import charts, filters
from components.layout import day, download, filter_scope, gbp, kpi, num, page_header, pct, section, table
from inventory360.business_logic.exceptions import TARGETS, rag_for
from inventory360.business_logic.supplier import spend_concentration, supplier_actions
from inventory360.data_access import queries
from inventory360.data_access.queries import PO_COLS
from inventory360.utils.formatting import fmt_days, fmt_gbp, fmt_int, fmt_pct

f = filters.current()
page_header("Supplier performance", "Purchasing spend, OTIF, lead-time reliability and supplier risk", f, st.session_state["gf_as_of"])
filter_scope(f, PO_COLS, note="date range applies to PO order date; score and risk rating are rolling 12 months")

scorecard = queries.load_supplier_scorecard()
perf = queries.supplier_performance(f)
prior = queries.supplier_performance(f.prior())
with st.container(horizontal=True, vertical_alignment="bottom"):
    regions = st.pills("Sourcing region", sorted(scorecard["sourcing_region"].dropna().unique()), selection_mode="multi",
                       key="sup_regions")
    tiers = st.pills("Contract tier", sorted(scorecard["contract_tier"].dropna().unique()), selection_mode="multi", key="sup_tiers")
    risks = st.pills("Risk rating", ["High", "Medium", "Low"], selection_mode="multi", key="sup_risk")

meta = scorecard[["supplier_id", "country_name", "primary_category", "contract_tier", "payment_terms_days",
                  "performance_score", "risk_rating", "landed_cost_uplift_pct"]]
view = perf.merge(meta, on="supplier_id", how="left")
if regions:
    view = view[view["sourcing_region"].isin(regions)]
if tiers:
    view = view[view["contract_tier"].isin(tiers)]
if risks:
    view = view[view["risk_rating"].isin(risks)]
ids = set(view["supplier_id"])
prior = prior[prior["supplier_id"].isin(ids)]


def weighted(df: pd.DataFrame, col: str) -> float | None:
    w = df["lines_received"].sum()
    return float((df[col] * df["lines_received"]).sum() / w) if w else None


spend, spend_p = view["spend_gbp"].sum(), prior["spend_gbp"].sum()
otif, otif_p = weighted(view, "otif_rate"), weighted(prior, "otif_rate")
lead, lead_p = weighted(view, "avg_lead_time_days"), weighted(prior, "avg_lead_time_days")
high = view[view["risk_rating"] == "High"]

cols = st.columns(5)
with cols[0]:
    kpi("Purchase spend", fmt_gbp(spend), current=spend, previous=spend_p, help=f"{fmt_int(view['po_count'].sum())} POs")
with cols[1]:
    kpi("OTIF", fmt_pct(otif), current=otif, previous=otif_p, points=True, status=rag_for("otif", otif),
        status_text=f"Target ≥ {fmt_pct(TARGETS['otif'].green, 0)}", help="Received lines on time and in full.")
with cols[2]:
    kpi("Average lead time", fmt_days(lead), current=lead, previous=lead_p, inverse=True)
with cols[3]:
    kpi("Top-5 concentration", fmt_pct(spend_concentration(view)), help="Share of spend with the five largest suppliers.")
with cols[4]:
    kpi("High-risk suppliers", f"{len(high)} of {len(view)}", status="Red" if len(high) > 3 else "Amber" if len(high) else "Green",
        status_text=f"{fmt_gbp(high['spend_gbp'].sum())} spend")

monthly = queries.supplier_monthly(f)
monthly = monthly[monthly["supplier_id"].isin(ids)]
left, right = st.columns([3, 2])
with left:
    with section("Risk matrix", "Spend vs OTIF · quadrants split at median spend and the OTIF target · hover for supplier"):
        rm = view.dropna(subset=["otif_rate"]).assign(open_value_gbp=view["open_value_gbp"].clip(lower=1))
        fig = charts.scatter(rm, "spend_gbp", "otif_rate", color="risk_rating", size="open_value_gbp", hover="supplier_name",
                             height=400, size_max=14, colors={"Low": charts.GREEN, "Medium": charts.AMBER, "High": charts.RED},
                             x_title="Purchase spend (£)", y_title="OTIF (%)")
        fig.for_each_trace(lambda t: t.update(name={"Low": "Low risk", "Medium": "Medium risk", "High": "High risk"}.get(t.name, t.name)))
        fig.update_traces(marker={"opacity": 0.8, "sizemin": 5},
                          hovertemplate="<b>%{hovertext}</b><br>Spend £%{x:,.0f}<br>OTIF %{y:.1%}<extra></extra>")
        x_mid, y_mid = float(rm["spend_gbp"].median()), TARGETS["otif"].green
        for kw in ({"x": x_mid}, {"y": y_mid}):
            (fig.add_vline if "x" in kw else fig.add_hline)(**kw, line_color=charts.SLATE, line_width=1.2, line_dash="dash")
        quadrants = [(0.02, 0.98, "Low spend · on target", "left", "top"), (0.98, 0.98, "Strategic · on target", "right", "top"),
                     (0.02, 0.02, "Low spend · under target", "left", "bottom"), (0.98, 0.02, "Priority risk · under target", "right", "bottom")]
        for qx, qy, text, xa, ya in quadrants:
            fig.add_annotation(xref="paper", yref="paper", x=qx, y=qy, text=text, showarrow=False, xanchor=xa, yanchor=ya,
                               font={"size": 10, "color": charts.SLATE})
        fig.update_layout(legend={"font": {"size": 10}, "itemsizing": "constant", "title": None})
        charts.show(fig, alt="Supplier risk matrix with spend and OTIF quadrants")
with right:
    with section("OTIF trend by region", "Monthly OTIF of received PO lines · dotted line = target", height="stretch"):
        trend = monthly.groupby(["period_month", "sourcing_region"], as_index=False)[["lines_otif", "lines_received"]].sum()
        trend["otif_rate"] = trend["lines_otif"] / trend["lines_received"].where(trend["lines_received"] > 0)
        region_colours = dict(zip(sorted(trend["sourcing_region"].dropna().unique()), [charts.NAVY, charts.TEAL, charts.SLATE]))
        fig = charts.line(trend, "period_month", "otif_rate", "sourcing_region", kind="pct", height=400, markers=True,
                          colors=region_colours, target=TARGETS["otif"].green, target_label=f"Target {TARGETS['otif'].green:.0%}",
                          y_title="OTIF (%)")
        fig.update_traces(marker={"size": 5}, line={"width": 2})
        fig.update_layout(legend={"font": {"size": 10}, "title": None})
        fig.update_xaxes(title={"text": "Order month", "font": {"size": 12}}, tickformat="%b %y")
        charts.show(fig, alt="Monthly OTIF by sourcing region")

with section("Spend by month and region"):
    sp = monthly.groupby(["period_month", "sourcing_region"], as_index=False)["spend_gbp"].sum()
    charts.show(charts.bar(sp, "period_month", "spend_gbp", "sourcing_region", height=280), alt="Monthly spend by region")

with section("Supplier scorecard", "Select a supplier to drill into monthly performance and open orders"):
    view = view.assign(
        otif_status=view["otif_rate"].map(lambda v: rag_for("otif", v)),
        action=view.apply(supplier_actions, axis=1),
        share=view["spend_gbp"] / spend if spend else 0,
    ).sort_values("spend_gbp", ascending=False)
    sel = table(
        view, key="sup_table", alt="Supplier scorecard", csv_name="supplier scorecard", rag_cols=["otif_status", "risk_rating"],
        height=420,
        columns=["risk_rating", "supplier_name", "country_name", "sourcing_region", "primary_category", "contract_tier",
                 "performance_score", "spend_gbp", "share", "open_value_gbp", "otif_rate", "otif_status", "on_time_rate",
                 "in_full_rate", "avg_days_late", "contract_lead_time_days", "avg_lead_time_days", "lead_time_std_days",
                 "landed_cost_uplift_pct", "action"],
        column_config={
            "risk_rating": "Risk", "supplier_name": st.column_config.TextColumn("Supplier", width="medium"),
            "country_name": "Country", "sourcing_region": "Region", "primary_category": "Category", "contract_tier": "Tier",
            "performance_score": st.column_config.ProgressColumn("Score (12m)", min_value=0, max_value=100, format="%.0f"),
            "spend_gbp": gbp("Spend"), "share": pct("Share"), "open_value_gbp": gbp("Open orders"),
            "otif_rate": pct("OTIF"), "otif_status": "OTIF RAG", "on_time_rate": pct("On time"), "in_full_rate": pct("In full"),
            "avg_days_late": num("Days late", 1), "contract_lead_time_days": num("Contract LT", 0, " d"),
            "avg_lead_time_days": num("Actual LT", 1, " d"), "lead_time_std_days": num("LT std dev", 1, " d"),
            "landed_cost_uplift_pct": pct("Freight+duty uplift"),
            "action": st.column_config.TextColumn("Recommended action", width="large"),
        },
    )

if sel is not None:
    with section(f"Drill-down · {sel['supplier_name']} · {sel['country_name']}",
                 f"{sel['contract_tier']} · {sel['primary_category']} · payment terms {sel['payment_terms_days']:.0f} days · "
                 f"score {sel['performance_score']:.0f} ({sel['risk_rating']} risk)"):
        m = monthly[monthly["supplier_id"] == sel["supplier_id"]]
        c1, c2 = st.columns(2)
        with c1:
            charts.show(charts.combo(m, "period_month", "spend_gbp", "otif_rate", "Spend", "OTIF",
                                     line_target=TARGETS["otif"].green, height=300), alt="Monthly spend and OTIF for supplier")
        with c2:
            charts.show(charts.bar(m, "period_month", "avg_days_late", kind="dec", height=300, value_title="Avg days late",
                                   single_colour=charts.AMBER), alt="Monthly average days late for supplier")
        po = queries.open_purchase_orders(f)
        po = po[po["supplier_id"] == sel["supplier_id"]]
        st.markdown(f"**Open order book** · {fmt_int(len(po))} lines · {fmt_gbp(po['order_value_gbp'].sum())}")
        cols_po = ["po_number", "warehouse_code", "sku", "product_name", "order_date", "expected_date", "po_status",
                   "qty_ordered", "order_value_gbp"]
        st.dataframe(po[cols_po], hide_index=True, height=260, alt="Open purchase order lines for supplier",
                     column_config={"po_number": "PO", "warehouse_code": "Site", "sku": "SKU", "product_name": "Product",
                                    "order_date": day("Ordered"), "expected_date": day("Due"), "po_status": "Status",
                                    "qty_ordered": num("Qty"), "order_value_gbp": gbp("Value")})
        download(po[cols_po], f"{sel['supplier_name']} open orders", key="dl_sup_drill")
