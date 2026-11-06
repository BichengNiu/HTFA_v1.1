"""Dashboard page renderers with explicit current-view inputs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import htfa.monitoring.energy_supply.processing.csv_export as csv_export
from htfa.monitoring.energy_supply.ui.widget_keys import energy_key


def render_assets_panel(assets: list[dict]) -> None:
    import htfa.monitoring.energy_supply.processing.production_units as production

    assets = [asset for asset in assets if asset["country"] != "土耳其"]
    metrics_container = st.container()
    c1, c2 = st.columns(2)
    country_options = sorted(
        {
            c
            for a in assets
            for c in (a.get("countries") or [a["country"]])
            if c != "土耳其"
        }
    )
    if energy_key("production_countries") in st.session_state:
        st.session_state[energy_key("production_countries")] = [
            c
            for c in st.session_state[energy_key("production_countries")]
            if c in country_options
        ]
    saved = st.session_state.get(energy_key("production_saved_filters"), {})
    countries = c1.multiselect(
        "国家",
        country_options,
        default=[c for c in saved.get("countries", []) if c in country_options],
        key=energy_key("production_countries"),
    )
    product_labels = c2.multiselect(
        "商品",
        list(production.STATISTICAL_PRODUCTS.values()),
        default=[
            production.STATISTICAL_PRODUCTS[p]
            for p in saved.get("products", list(production.STATISTICAL_PRODUCTS))
            if p in production.STATISTICAL_PRODUCTS
        ],
        key=energy_key("production_products"),
    )
    products = [
        key
        for key, label in production.STATISTICAL_PRODUCTS.items()
        if label in product_labels
    ]
    st.session_state[energy_key("production_saved_filters")] = {
        "countries": countries,
        "products": products,
    }
    chosen, rows, daily_column, _ = production.statistical_view(
        assets, countries, products
    )
    with metrics_container:
        a1, active, a2, a3, a4 = st.columns([1, 1, 1, 1, 2])
        a1.metric("油田资产数量", len(rows))
        active.metric("在产数量", production.producing_count(chosen))
        a2.metric("国家数量", len({c for o in chosen for c in o["countries"]}))
        a3.metric("油田类型数量", len({row["类型"] for row in rows}))
        crude_values = [
            row[daily_column]
            for row in rows
            if row["商品"] == "原油" and row[daily_column] is not None
        ]
        amount = f"{sum(crude_values):.1f}万桶/日" if crude_values else "—"
        with a4.container(key=energy_key("production_daily_metric")):
            st.metric("原油产量", amount)
    table = pd.DataFrame(
        rows,
        columns=[
            "名称",
            "国家",
            "类型",
            "包含资产",
            daily_column,
            "商品",
            "状态",
            "备注",
            "数据时间",
            "数据来源",
        ],
    )
    table[daily_column] = pd.to_numeric(table[daily_column], errors="coerce")
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        height=620,
        column_config={
            "数据来源": st.column_config.LinkColumn("数据来源"),
            daily_column: st.column_config.NumberColumn(daily_column),
        },
    )

    st.download_button(
        "下载数据",
        csv_export.csv_bytes(rows, list(table.columns)),
        file_name="oil_gas_production.csv",
        mime="text/csv",
        type="primary",
        key=energy_key("production_download"),
        on_click="ignore",
    )
