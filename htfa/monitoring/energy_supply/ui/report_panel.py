"""Print layout consumes prepared report data only."""

import streamlit as st

from htfa.monitoring.energy_supply.contracts import DashboardViewState

from . import cache, dashboard_rows, print_report


def render_print_report(
    available_ports,
    available_chokepoints,
    state: DashboardViewState,
    *,
    data_revisions=None,
):
    report_inputs = cache.report_inputs(
        available_ports, available_chokepoints, state, data_revisions=data_revisions
    )
    report_inputs["asset_table"] = [
        dashboard_rows.print_asset_record(asset) for asset in report_inputs["assets"]
    ]
    st.html(print_report.PRINT_CSS + cache.report_html(report_inputs))
