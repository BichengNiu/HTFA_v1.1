"""Typed inputs shared by energy processing and presentation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class DashboardViewState:
    live_positions: list[dict[str, Any]]
    ais_status: dict[str, Any]
    open_state: dict[str, Any]
    archive_error: str | None
    port_error: str | None
    chokepoint_error: str | None
    map_assets: list[dict[str, Any]]
    map_ports: list[dict[str, Any]]
    map_chokepoints: list[dict[str, Any]]
    selected_day: date | None
    selected_chokepoint_day: date | None
    snapshot_day: date | None = None
    selected_sea_day: date | None = None
    vessel_tracks: dict | None = None
    assets: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DashboardQuery:
    """User selections passed to the snapshot preparation service."""

    selected_day: date | None = None
    include_tracks: bool = False
    countries: tuple[str, ...] = ()
    products: tuple[str, ...] | None = None


@dataclass(frozen=True)
class DashboardContext:
    """Published catalogs and source dates used to prepare one dashboard."""

    assets: list[dict[str, Any]]
    ports: list[dict[str, Any]]
    chokepoints: list[dict[str, Any]]
    newest_day: date | None
    newest_chokepoint_day: date | None
    first_day: date | None
    last_day: date | None
    revisions: dict[str, int]
    port_error: str | None
    chokepoint_error: str | None
