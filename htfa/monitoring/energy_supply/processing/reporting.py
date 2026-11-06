"""Monitoring summaries and complete print-report input preparation."""

from htfa.monitoring.energy_supply.contracts import DashboardViewState
from htfa.monitoring.energy_supply.processing import monitoring_cards, report_data
from htfa.monitoring.energy_supply.processing import portwatch as PORTWATCH


def prepare_monitoring_cards(
    available_ports,
    available_chokepoints,
    state,
    port_history=None,
    choke_history=None,
    data_revisions=None,
    port_comparison=None,
    choke_comparison=None,
):
    """Prepare summary cards from local data or explicitly supplied report data."""
    errors = []
    revisions = data_revisions or {}
    port_ids = tuple(
        sorted(
            str(p["portid"])
            for p in available_ports
            if PORTWATCH.has_independent_statistics(p)
        )
    )
    choke_ids = tuple(sorted(str(p["portid"]) for p in available_chokepoints))
    histories = []
    for kind, ids, day, supplied in (
        ("ports", port_ids, state.selected_day, port_history),
        ("chokepoints", choke_ids, state.selected_chokepoint_day, choke_history),
    ):
        rows = supplied
        if rows is None:
            rows = []
            if ids and day:
                try:
                    rows = report_data.card_activity_history(
                        kind, ids, day.isoformat(), revisions.get(kind, 0)
                    )
                except Exception as exc:
                    errors.append(f"{kind} 本地历史窗口：{type(exc).__name__}: {exc}")
        histories.append(rows)
    port_history, choke_history = histories
    comparison_ports = port_comparison or []
    comparison_chokes = choke_comparison or []
    cards = monitoring_cards.build_cards(
        available_ports,
        available_chokepoints,
        port_history + comparison_ports,
        choke_history + comparison_chokes,
        state.selected_day,
        state.selected_chokepoint_day,
        assets=state.map_assets,
    )
    return cards, errors


def prepare_report(
    available_ports: list[dict],
    available_chokepoints: list[dict],
    state: DashboardViewState,
    *,
    data_revisions: dict[str, int] | None = None,
) -> dict:
    selected_day = state.selected_day
    selected_chokepoint_day = state.selected_chokepoint_day
    live_positions = state.live_positions
    port_error = state.port_error
    chokepoint_error = state.chokepoint_error
    open_state = state.open_state
    report_port_catalog = list(available_ports)
    report_choke_catalog = list(available_chokepoints)
    report_assets = list(state.assets)
    report_vessels = [
        {
            key: vessel.get(key)
            for key in (
                "mmsi",
                "name",
                "lat",
                "lon",
                "region",
                "category",
                "category_label",
                "moving",
                "observed_at",
                "received_at",
            )
        }
        for vessel in live_positions
    ]

    report_port_ids = tuple(
        sorted(
            str(port["portid"])
            for port in report_port_catalog
            if PORTWATCH.has_independent_statistics(port)
        )
    )
    report_choke_ids = tuple(
        sorted(str(point["portid"]) for point in report_choke_catalog)
    )
    report_errors = []
    revisions = data_revisions or {}
    if port_error:
        report_errors.append(f"港口最新数据：{port_error}")
    if chokepoint_error:
        report_errors.append(f"咽喉点最新数据：{chokepoint_error}")
    if open_state.get("error"):
        report_errors.append(f"Open Waters：{open_state['error']}")

    report_port_history = []
    report_choke_history = []
    if selected_day is not None and report_port_ids:
        try:
            report_port_history = report_data.history_window(
                "ports",
                report_port_ids,
                selected_day.isoformat(),
                revisions.get("ports", 0),
                allow_network=False,
            )
        except Exception as exc:
            report_errors.append(f"ports 历史窗口：{type(exc).__name__}: {exc}")
    if selected_chokepoint_day is not None and report_choke_ids:
        try:
            report_choke_history = report_data.history_window(
                "chokepoints",
                report_choke_ids,
                selected_chokepoint_day.isoformat(),
                revisions.get("chokepoints", 0),
                allow_network=False,
            )
        except Exception as exc:
            report_errors.append(f"chokepoints 历史窗口：{type(exc).__name__}: {exc}")

    report_port_comparison, report_choke_comparison = [], []
    for kind, ids, day, target in (
        ("ports", report_port_ids, selected_day, report_port_comparison),
        (
            "chokepoints",
            report_choke_ids,
            selected_chokepoint_day,
            report_choke_comparison,
        ),
    ):
        if day is None or not ids:
            continue
        try:
            target.extend(
                report_data.comparison_history(
                    kind,
                    ids,
                    day.isoformat(),
                    revisions.get(kind, 0),
                    allow_network=False,
                )
            )
        except Exception as exc:
            report_errors.append(f"{kind} 同比记录：{type(exc).__name__}: {exc}")

    cards, card_errors = prepare_monitoring_cards(
        report_port_catalog,
        report_choke_catalog,
        state,
        report_port_history,
        report_choke_history,
        data_revisions=revisions,
        port_comparison=report_port_comparison,
        choke_comparison=report_choke_comparison,
    )
    report_errors.extend(card_errors)

    report_latest_ports = report_data.merge_latest_rows(
        report_port_catalog, report_port_history
    )

    report_ais_state = state.ais_status
    report_ais_status = str(report_ais_state.get("status") or "等待数据")
    report_observed_at = max(
        (vessel.get("observed_at") or "" for vessel in live_positions), default=""
    )
    report_ais_note = (
        f"Open Waters 快照 {len(open_state.get('vessels') or [])} 艘；"
        f"观测截至 {report_observed_at or '未提供'}；"
        f"AISStream 状态：{report_ais_status}"
    )
    return {
        "scope_label": "全部监测对象",
        "monitoring_summary_cards": cards,
        "generated_at": None,
        "port_catalog": report_port_catalog,
        "choke_catalog": report_choke_catalog,
        "latest_ports": report_latest_ports,
        "port_history": report_port_history,
        "choke_history": report_choke_history,
        "assets": report_assets,
        "vessels": report_vessels,
        "regions": PORTWATCH.REGIONS,
        "port_day": selected_day,
        "choke_day": selected_chokepoint_day,
        "ais_status": report_ais_status,
        "ais_source_note": report_ais_note,
        "errors": report_errors,
    }
