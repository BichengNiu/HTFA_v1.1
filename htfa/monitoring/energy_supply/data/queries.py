"""Published snapshot queries, with no UI or statistical presentation rules."""

from __future__ import annotations

import json

from . import storage


def snapshot_date_bounds():
    with storage.connect() as connection:
        return connection.execute("""
            SELECT MIN(first_day), MAX(last_day) FROM (
                SELECT MIN(day) first_day, MAX(day) last_day FROM portwatch_daily
                UNION ALL
                SELECT CAST(MIN(observed) AT TIME ZONE 'UTC' AS DATE),
                       CAST(MAX(observed) AT TIME ZONE 'UTC' AS DATE) FROM ais_reports
            ) dates
        """).fetchone()


def nearest_portwatch_dates(kind, selected):
    metric = {"ports": "portcalls", "chokepoints": "n_total"}[kind]
    with storage.connect() as connection:
        return connection.execute(
            f"""
            SELECT MAX(day) FILTER (WHERE day<=?), MIN(day) FILTER (WHERE day>=?)
            FROM (SELECT day, TRY_CAST(json_extract_string(payload,'$.{metric}') AS DOUBLE) metric_value
                  FROM portwatch_daily WHERE kind=?) observations
            WHERE metric_value>=0 AND isfinite(metric_value)
        """,
            [selected, selected, kind],
        ).fetchone()


def portwatch_latest_before(kind, selected, node_ids):
    if not node_ids:
        return None
    with storage.connect() as connection:
        return connection.execute(
            "SELECT MAX(day) FROM portwatch_daily WHERE kind=? AND day<=? AND node_id IN ("
            + ",".join("?" for _ in node_ids)
            + ")",
            [kind, selected, *node_ids],
        ).fetchone()[0]


def observed_collection_days():
    with storage.connect() as connection:
        return [
            row[0]
            for row in connection.execute("""
            SELECT DISTINCT CAST(started_at AT TIME ZONE 'Asia/Shanghai' AS DATE)
            FROM collection_runs WHERE provider='Open Waters' AND status IN ('ok','partial')
              AND reports>0
        """).fetchall()
        ]


def vessel_history(last):
    with storage.connect() as connection:
        rows = connection.execute(
            """
            SELECT payload FROM ais_reports
            WHERE observed < CAST(? AS DATE) + INTERVAL 1 DAY
            ORDER BY observed, source
        """,
            [last],
        ).fetchall()
    return [json.loads(row[0]) if isinstance(row[0], str) else row[0] for row in rows]


def portwatch_date_bounds(kind):
    with storage.connect() as connection:
        return connection.execute(
            "SELECT MIN(day),MAX(day) FROM portwatch_daily WHERE kind=?",
            [kind],
        ).fetchone()


def portwatch_keys(kind, ids, first, last):
    if not ids:
        return set()
    with storage.connect() as connection:
        return set(
            connection.execute(
                "SELECT node_id,day FROM portwatch_daily WHERE kind=? AND day BETWEEN ? AND ? "
                "AND node_id IN (" + ",".join("?" for _ in ids) + ")",
                [kind, first, last, *ids],
            ).fetchall()
        )
