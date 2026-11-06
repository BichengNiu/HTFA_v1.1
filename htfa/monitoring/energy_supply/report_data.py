"""Cached data preparation for the full-project browser print report."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
import os

import streamlit as st

from htfa.monitoring.energy_supply import portwatch_downloads
from htfa.monitoring.energy_supply import print_report
from htfa.monitoring.energy_supply.portwatch_records import latest_by_node
from htfa.monitoring.energy_supply import data_store
from htfa.monitoring.energy_supply.monitoring_cards import windows


@st.cache_data(ttl=900, max_entries=12, show_spinner=False)
def history_window(kind: str, node_ids: tuple[str, ...], end_day: str,
                   data_revision: int = 0, allow_network: bool = False) -> list[dict]:
    """Return cached report history, using the upstream only when explicitly enabled."""
    if not node_ids:
        return []
    end = date.fromisoformat(end_day)
    rows, _ = portwatch_downloads.fetch_window(
        kind, node_ids, end - timedelta(days=89), end,
        cache_revision=0, cache_ttl_seconds=86_400,
        allow_stale=True, cache_only=not allow_network)
    return rows


@st.cache_data(ttl=900, max_entries=24, show_spinner=False)
def card_activity_history(kind: str, node_ids: tuple[str, ...], end_day: str,
                          data_revision: int = 0) -> list[dict]:
    """Read the latest observed calendar week for the selected nodes and cutoff."""
    if not node_ids:
        return []
    selected = date.fromisoformat(end_day)
    with data_store.connect() as conn:
        latest = conn.execute(
            "SELECT MAX(day) FROM portwatch_daily WHERE kind=? AND day<=? AND node_id IN ("
            + ','.join('?' for _ in node_ids) + ')', [kind, selected, *node_ids]).fetchone()[0]
    if latest is None:
        return []
    return data_store.cached_portwatch_periods(
        kind, node_ids, [(latest - timedelta(days=latest.weekday()), latest)])


def merge_latest_rows(catalog: list[dict], history: list[dict]) -> list[dict]:
    """Attach each node's latest observed historical row, preserving empty nodes."""
    latest = latest_by_node(history, require_date=False)
    return [
        {**point, **latest.get(str(point.get("portid")), {})}
        for point in catalog
    ]


@st.cache_data(
    ttl=900, max_entries=8, show_spinner=False,
    # Hash every input value using the C JSON encoder rather than recursively
    # traversing thousands of history dictionaries in Streamlit's hasher.
    # Dates and exact Decimal asset values retain their textual representation.
    hash_funcs={dict: lambda value: json.dumps(
        value, sort_keys=True, ensure_ascii=False, default=str)},
)
def cached_print_report(report_inputs: dict) -> str:
    """Reuse report HTML while its source data and report inputs are unchanged."""
    return print_report.build_report_html(**report_inputs)


@st.cache_data(ttl=900, max_entries=12, show_spinner=False)
def comparison_history(kind: str, node_ids: tuple[str, ...], end_day: str,
                       data_revision: int = 0, allow_network: bool = False) -> list[dict]:
    """Read last year's matching month for the cover card year-on-year comparison."""
    start, end = windows(date.fromisoformat(end_day))[-1]
    rows, _ = portwatch_downloads.fetch_window(
        kind, node_ids, start, end, cache_revision=0, cache_ttl_seconds=86_400,
        allow_stale=True, cache_only=not allow_network)
    return rows


def sea_history_config() -> dict:
    config = {}
    for key in ("SEA_HISTORY_ARCHIVE_PATH", "SEA_HISTORY_BUNDLE_PATH",
                "SEA_HISTORY_BUNDLE_URL", "SEA_HISTORY_BEARER_TOKEN", "SEA_HISTORY_IMPORT_TOKEN"):
        try:
            secret = st.secrets.get(key)
        except Exception:
            secret = None
        config[key] = str(secret or os.environ.get(key) or "").strip()
    return config


@st.cache_data(ttl=60, max_entries=12, show_spinner=False)
def card_sea_history(data_revision: int = 0, selected_day: str | None = None) -> dict:
    """Read provider history or observed local runs at the nearest real source day."""
    from htfa.monitoring.energy_supply import sea_history
    from htfa.monitoring.energy_supply import sea_tracking
    from htfa.monitoring.energy_supply.historical_dates import nearest_day, nearest_sea_day
    try:
        config = sea_history_config()
        result = sea_history.read_history(sea_history.archive_path(config))
        effective_day = None
        if result["source"]:
            if selected_day:
                effective_day = nearest_sea_day(result["rows"], date.fromisoformat(selected_day))
        elif selected_day:
            # Generated month rows are not proof of an observation on that day.
            # Anchor local partial-month cards only to actual successful collection days.
            with data_store.connect() as conn:
                days = [row[0] for row in conn.execute("""
                    SELECT DISTINCT CAST(started_at AT TIME ZONE 'Asia/Shanghai' AS DATE)
                    FROM collection_runs WHERE provider='Open Waters' AND status IN ('ok','partial')
                      AND reports>0
                """).fetchall()]
            effective_day = nearest_day(days, date.fromisoformat(selected_day))
            result = (sea_tracking.observation_summary(
                datetime.combine(effective_day, time.max, sea_tracking.TZ)) if effective_day
                else {"rows": [], "source": None, "card": None})
        else:
            result = sea_tracking.observation_summary()
        return {**result, "selected_day": effective_day, "error": None}
    except Exception as exc:
        return {"rows": [], "card": None, "source": None, "selected_day": None,
                "error": f"{type(exc).__name__}: {exc}"}
