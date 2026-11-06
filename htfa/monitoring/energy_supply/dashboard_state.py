"""Typed inputs passed from dashboard data preparation to its page views."""
from __future__ import annotations

from dataclasses import dataclass
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
