"""Cached UI queries; processing services remain framework independent."""

import json

from htfa.monitoring.energy_supply.processing import (
    dashboard_data,
    dashboard_service,
    report_data,
    reporting,
    vessel_charts,
)

from . import print_report
from .cache_policy import snapshot_cache
from .config import sea_history_config

dashboard_data_port_time_series = snapshot_cache(**{"max_entries": 8})(
    dashboard_data.port_time_series
)


vessel_charts_history = snapshot_cache(**{"max_entries": 12})(vessel_charts.history)


@snapshot_cache(ttl=60, max_entries=12)
def _sea_history(data_revision, selected_day, config):
    return report_data.card_sea_history(data_revision, selected_day, config=config)


def report_data_card_sea_history(data_revision=0, selected_day=None):
    return _sea_history(data_revision, selected_day, sea_history_config())


@snapshot_cache(
    ttl=900,
    max_entries=8,
    hash_funcs={
        dict: lambda value: json.dumps(
            value, sort_keys=True, ensure_ascii=False, default=str
        )
    },
)
def report_html(report_inputs):
    return print_report.build_report_html(**report_inputs)


report_data_card_sea_history.clear = _sea_history.clear

dashboard_context = snapshot_cache(ttl=60, max_entries=4)(dashboard_service.load_context)
report_inputs = snapshot_cache(ttl=60, max_entries=8)(reporting.prepare_report)
