"""Cached data preparation for the full-project browser print report."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import htfa.monitoring.energy_supply.data.portwatch_windows as portwatch_downloads
import htfa.monitoring.energy_supply.data.storage as data_store
from htfa.monitoring.energy_supply.contracts.records import latest_by_node
from htfa.monitoring.energy_supply.data import queries
from htfa.monitoring.energy_supply.processing.monitoring_cards import windows


def history_window(
    kind: str,
    node_ids: tuple[str, ...],
    end_day: str,
    data_revision: int = 0,
    allow_network: bool = False,
) -> list[dict]:
    """Return cached report history, using the upstream only when explicitly enabled."""
    if not node_ids:
        return []
    end = date.fromisoformat(end_day)
    rows, _ = portwatch_downloads.fetch_window(
        kind,
        node_ids,
        end - timedelta(days=89),
        end,
        cache_revision=0,
        cache_ttl_seconds=86_400,
        allow_stale=True,
        cache_only=not allow_network,
    )
    return rows


def card_activity_history(
    kind: str, node_ids: tuple[str, ...], end_day: str, data_revision: int = 0
) -> list[dict]:
    """Read the latest observed calendar week for the selected nodes and cutoff."""
    if not node_ids:
        return []
    selected = date.fromisoformat(end_day)
    latest = queries.portwatch_latest_before(kind, selected, node_ids)
    if latest is None:
        return []
    return data_store.cached_portwatch_periods(
        kind, node_ids, [(latest - timedelta(days=latest.weekday()), latest)]
    )


def merge_latest_rows(catalog: list[dict], history: list[dict]) -> list[dict]:
    """Attach each node's latest observed historical row, preserving empty nodes."""
    latest = latest_by_node(history, require_date=False)
    return [{**point, **latest.get(str(point.get("portid")), {})} for point in catalog]


def comparison_history(
    kind: str,
    node_ids: tuple[str, ...],
    end_day: str,
    data_revision: int = 0,
    allow_network: bool = False,
) -> list[dict]:
    """Read last year's matching month for the cover card year-on-year comparison."""
    start, end = windows(date.fromisoformat(end_day))[-1]
    rows, _ = portwatch_downloads.fetch_window(
        kind,
        node_ids,
        start,
        end,
        cache_revision=0,
        cache_ttl_seconds=86_400,
        allow_stale=True,
        cache_only=not allow_network,
    )
    return rows


def card_sea_history(
    data_revision: int = 0,
    selected_day: str | None = None,
    *,
    config: dict | None = None,
) -> dict:
    """Read provider history or observed local runs at the nearest real source day."""
    import htfa.monitoring.energy_supply.processing.sea_history as sea_history
    import htfa.monitoring.energy_supply.processing.sea_tracking as sea_tracking
    from htfa.monitoring.energy_supply.processing.historical_dates import (
        nearest_day,
        nearest_sea_day,
    )

    try:
        config = config or {}
        result = sea_history.read_history(sea_history.archive_path(config))
        effective_day = None
        if result["source"]:
            if selected_day:
                effective_day = nearest_sea_day(
                    result["rows"], date.fromisoformat(selected_day)
                )
        elif selected_day:
            # Generated month rows are not proof of an observation on that day.
            # Anchor local partial-month cards only to actual successful collection days.
            days = queries.observed_collection_days()
            effective_day = nearest_day(days, date.fromisoformat(selected_day))
            result = (
                sea_tracking.observation_summary(
                    datetime.combine(effective_day, time.max, sea_tracking.TZ)
                )
                if effective_day
                else {"rows": [], "source": None, "card": None}
            )
        else:
            result = sea_tracking.observation_summary()
        return {**result, "selected_day": effective_day, "error": None}
    except Exception as exc:
        return {
            "rows": [],
            "card": None,
            "source": None,
            "selected_day": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
