"""Shared PortWatch field definitions and daily-record indexing."""

from __future__ import annotations

SHIP_TYPE_LABELS = {
    "container": "集装箱船",
    "dry_bulk": "干散货船",
    "general_cargo": "普通货船",
    "roro": "滚装船",
    "tanker": "油轮/液货船",
}
SHIP_TYPES = tuple(SHIP_TYPE_LABELS)
EXPORT_SHIP_LABELS = {**SHIP_TYPE_LABELS, "cargo": "货船合计"}
PORT_METRICS = ["portcalls", "import", "export"] + [
    f"{metric}_{ship}"
    for metric in ("portcalls", "import", "export")
    for ship in EXPORT_SHIP_LABELS
]
CHOKE_METRICS = ["n_total", "capacity"] + [
    f"{metric}_{ship}" for metric in ("n", "capacity") for ship in EXPORT_SHIP_LABELS
]


def latest_by_node(rows: list[dict], *, require_date: bool = True) -> dict[str, dict]:
    """Keep the first record on ties; optionally retain undated catalog records."""
    latest = {}
    for row in rows:
        node_id = str(row.get("portid", ""))
        day = str(row.get("date", ""))
        if (
            node_id
            and (day or not require_date)
            and (node_id not in latest or day > str(latest[node_id].get("date", "")))
        ):
            latest[node_id] = row
    return latest
