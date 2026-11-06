"""Cached data boundaries and refresh callbacks for the dashboard."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import htfa.monitoring.energy_supply.data.storage as data_store
import htfa.monitoring.energy_supply.processing.ais as AIS
import htfa.monitoring.energy_supply.processing.ais_history as ais_history
import htfa.monitoring.energy_supply.processing.portwatch as PORTWATCH
from htfa.monitoring.energy_supply.data import queries
from htfa.monitoring.energy_supply.processing import catalogs
from htfa.monitoring.energy_supply.processing.ais_collector import AISCollector
from htfa.monitoring.energy_supply.processing.port_metadata import monitored_ports


def initialize_storage():
    return data_store.initialize_runtime()


def openwaters_snapshot(
    collector_version: int, selected_day: date | None = None
) -> dict:
    """Display source-dated positions from the published snapshot only."""
    rows = (
        ais_history.day_snapshot(selected_day)
        if selected_day is not None
        else ais_history.latest_snapshot(max_age_minutes=120, fallback_to_latest=True)
    )
    now = (
        datetime.combine(selected_day, time.max, timezone.utc)
        if selected_day is not None
        else AIS.utc_now()
    )
    vessels = []
    for vessel in rows:
        row = dict(vessel)
        observed = AIS.parse_utc(row.get("observed_at"))
        if observed is not None:
            age_minutes = max(0.0, (now - observed).total_seconds() / 60)
            row["age_minutes"] = age_minutes
            row["age_basis"] = (
                "距所选UTC日结束" if selected_day is not None else "源站观测时间"
            )
        else:
            row["age_minutes"] = None
            row["age_basis"] = None
        vessels.append(row)
    newest = max(
        (row.get("received_at") or row.get("observed_at") or "" for row in rows),
        default=None,
    )
    return {
        "vessels": vessels,
        "error": None,
        "archive_error": None,
        "fetched_at": newest,
        "refresh_summary": None,
    }


def vessel_tracks(positions: tuple, data_revision: int, snapshot_identity: str) -> dict:
    return ais_history.snapshot_tracks(
        [
            {"mmsi": mmsi, "observed_at": observed, "lat": lat, "lon": lon}
            for mmsi, observed, lat, lon in positions
        ]
    )


def snapshot_date_bounds(snapshot_identity: tuple) -> tuple[date | None, date | None]:
    """Calendar bounds of the currently published facts."""
    return queries.snapshot_date_bounds()


def nearest_portwatch_day(
    kind: str, selected: date, snapshot_identity: tuple
) -> date | None:
    from htfa.monitoring.energy_supply.processing.historical_dates import nearest_day

    return nearest_day(queries.nearest_portwatch_dates(kind, selected), selected)


def portwatch_state(
    kind: str,
    resource: str,
    module_version: int,
    stored_revision: int = 0,
    refresh_revision: str = "initial",
):
    """Cache both source values and short-lived failures across page reruns."""
    readers = {
        ("ports", "catalog"): PORTWATCH.port_catalog,
        ("chokepoints", "catalog"): PORTWATCH.chokepoint_catalog,
        ("ports", "latest_date"): PORTWATCH.latest_date,
        ("chokepoints", "latest_date"): PORTWATCH.latest_chokepoint_date,
    }
    reader = readers[kind, resource]

    def scoped(value):
        return (
            monitored_ports(value)
            if (kind, resource) == ("ports", "catalog")
            else value
        )

    source_error = None
    if refresh_revision != "initial" and not data_store.read_only():
        try:
            return scoped(reader(refresh_revision)), None
        except Exception as exc:
            source_error = f"{type(exc).__name__}: {exc}"
    try:
        if resource == "catalog":
            cached = catalogs.cached_catalog(kind, allow_stale=True)
        elif resource == "latest_date":
            cached = data_store.cached_portwatch_latest_day(kind, allow_stale=True)
        else:
            cached = None
        if cached is not None:
            return scoped(cached), source_error
    except Exception:
        pass
    label = "港口" if kind == "ports" else "咽喉点"
    return (
        [] if resource == "catalog" else None
    ), source_error or f"本地暂无{label}目录/日期缓存"


def port_time_series(
    node_ids: tuple[str, ...], selected_day: date, snapshot_identity: tuple
) -> list[dict]:
    return data_store.portwatch_daily_totals(node_ids, selected_day)


def collector_status(collector: AISCollector | None = None) -> dict:
    """Return the collector status shape; app mode intentionally has no worker."""

    if collector is not None:
        return collector.status()
    return {
        "status": "已暂停（未启用AISStream）",
        "last_error": None,
        "last_message_at": None,
        "last_position_message_at": None,
        "raw_event_count": 0,
        "rejected_event_count": 0,
        "message_count": 0,
        "position_message_count": 0,
        "static_message_count": 0,
        "tracked_vessels": 0,
        "compression_enabled": None,
    }


def load_ports(
    available_ports: list[dict],
    selected_day: date,
    rolling_days: int,
    *,
    with_risk: bool = False,
    refresh_revision: str = "initial",
    stored_revision: int = 0,
) -> tuple[list[dict], str | None, str | None]:
    port_error = None
    port_risk_error = None
    ids = tuple(port["portid"] for port in available_ports)
    statistical_ids = tuple(
        sorted(
            str(port["portid"])
            for port in available_ports
            if PORTWATCH.has_independent_statistics(port)
        )
    )
    activity_all, weekly_all = {}, {}
    if statistical_ids:
        try:
            activity_all = PORTWATCH.daily_activity(
                selected_day, statistical_ids, refresh_revision, stored_revision
            )
        except Exception as exc:
            port_error = f"日活动：{type(exc).__name__}: {exc}"
            try:
                activity_all = PORTWATCH.daily_activity(
                    selected_day, statistical_ids, "initial", stored_revision
                )
            except Exception:
                pass
        try:
            weekly_all = PORTWATCH.week_to_date_activity(
                selected_day, statistical_ids, refresh_revision, stored_revision
            )
        except Exception as exc:
            rolling_error = f"本周累计：{type(exc).__name__}: {exc}"
            port_error = (
                f"{port_error}；{rolling_error}" if port_error else rolling_error
            )
            try:
                weekly_all = PORTWATCH.week_to_date_activity(
                    selected_day, statistical_ids, "initial", stored_revision
                )
            except Exception:
                pass
    activity = {
        port_id: activity_all[port_id] for port_id in ids if port_id in activity_all
    }
    rolling = {port_id: weekly_all[port_id] for port_id in ids if port_id in weekly_all}

    risk_capacity = None
    if with_risk:
        saved_risk = data_store.meta("port_risk_capacity_snapshot")
        if saved_risk and tuple(saved_risk.get("port_ids", ())) == statistical_ids:
            risk_capacity = saved_risk.get("values", {})

    ports = PORTWATCH.decorate(available_ports, activity, rolling, risk_capacity)

    return ports, port_error, port_risk_error


def load_chokepoints(
    available_chokepoints: list[dict],
    selected_chokepoint_day: date,
    refresh_revision: str = "initial",
    stored_revision: int = 0,
) -> tuple[list[dict], str | None]:
    chokepoint_error = None
    values = {}
    chokepoint_ids = tuple(str(point["portid"]) for point in available_chokepoints)
    try:
        if chokepoint_ids:
            values = PORTWATCH.chokepoint_activity(
                selected_chokepoint_day,
                chokepoint_ids,
                refresh_revision,
                stored_revision,
            )
    except Exception as exc:
        chokepoint_error = f"{type(exc).__name__}: {exc}"
        try:
            values = PORTWATCH.chokepoint_activity(
                selected_chokepoint_day, chokepoint_ids, "initial", stored_revision
            )
        except Exception:
            pass

    chokepoints = PORTWATCH.decorate_chokepoints(available_chokepoints, values)
    return chokepoints, chokepoint_error
