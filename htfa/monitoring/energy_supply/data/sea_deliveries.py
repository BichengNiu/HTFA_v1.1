"""Atomic persistence and verified reads of provider sea event deliveries."""

import hashlib
import json
from pathlib import Path

from . import storage as data_store


def save_bundle(data, manifest, events, cells, path=None):
    path = Path(path) if path is not None else data_store.database_path()
    provider, definition = manifest["source"], manifest["definition_id"]
    with data_store.connect(path) as conn:
        previous = conn.execute(
            "SELECT manifest FROM sea_manifests WHERE provider=?", (provider,)
        ).fetchone()
        if previous:
            old = json.loads(previous[0])
            if any(
                old[key] != manifest[key]
                for key in ("source", "definition_id", "timezone", "event_basis")
            ):
                raise ValueError(
                    "历史库的供应商或海域边界口径不同；请使用独立档案，不能混算同比"
                )
        # Each validated day replaces the earlier delivery atomically; corrected
        # provider reports and repeated uploads do not accumulate duplicates.
        for sea, day in cells:
            conn.execute(
                "DELETE FROM sea_entries WHERE provider=? AND definition=? AND sea=? AND day=?",
                (provider, definition, sea, day),
            )
        if events:
            conn.executemany(
                "INSERT INTO sea_entries VALUES (?,?,?,?,?,?,?)",
                [
                    (provider, definition, sea, mmsi, stamp, day, "{}")
                    for sea, mmsi, stamp, day in events
                ],
            )
        conn.executemany(
            "INSERT OR REPLACE INTO sea_coverage VALUES (?,?,?,?,?,?)",
            [
                (provider, definition, sea, day, "complete", count)
                for (sea, day), count in cells.items()
            ],
        )
        conn.execute(
            "INSERT OR REPLACE INTO sea_manifests VALUES (?,?)",
            (provider, json.dumps(manifest, ensure_ascii=False)),
        )
        data_store.set_meta("selected_sea_history_provider", provider, conn)
        data_store.bump_revision("sea", conn)
        data_store.put_binary_document(
            "deliveries/sea-" + hashlib.sha256(data).hexdigest() + ".zip",
            data,
            "application/zip",
            conn,
        )
    return {
        "events": len(events),
        "days": len(cells),
        "source": manifest["source"],
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def read_history(path=None):
    path = Path(path) if path is not None else data_store.database_path()
    if not path.exists():
        return {"rows": [], "source": None, "definition_id": None}
    with data_store.connect(path) as conn:
        provider = data_store.meta("selected_sea_history_provider", conn=conn)
        if not provider:
            return {"rows": [], "source": None, "definition_id": None}
        metadata = conn.execute(
            "SELECT manifest FROM sea_manifests WHERE provider=?", (provider,)
        ).fetchone()
        manifest = json.loads(metadata[0]) if metadata else {}
        rows = [
            {"sea": sea, "date": day.isoformat(), "passages": count}
            for sea, day, count in conn.execute(
                "SELECT c.sea,c.day,COUNT(e.entered_at) FROM sea_coverage c "
                "LEFT JOIN sea_entries e ON e.provider=c.provider AND e.definition=c.definition AND e.sea=c.sea AND e.day=c.day "
                "WHERE c.provider=? AND c.status='complete' "
                "GROUP BY c.sea,c.day,c.event_count HAVING COUNT(e.entered_at)=c.event_count ORDER BY c.day,c.sea",
                (provider,),
            ).fetchall()
        ]
    return {
        "rows": rows,
        "source": manifest.get("source"),
        "definition_id": manifest.get("definition_id"),
    }
