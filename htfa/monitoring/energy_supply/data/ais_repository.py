"""AIS persistence and canonical report queries within energy transactions."""

from __future__ import annotations

import json
from contextlib import contextmanager

from . import storage


@contextmanager
def transaction():
    """Share the archive write and derived sea events in one transaction."""
    with storage.connect() as connection:
        yield connection


def save_reports(rows, connection):
    connection.execute(
        "CREATE TEMP TABLE incoming_reports AS SELECT * FROM ais_reports LIMIT 0"
    )
    connection.executemany(
        "INSERT INTO incoming_reports VALUES (?, ?, ?, ?)",
        [
            (
                row["mmsi"],
                row["observed_at"],
                row["source"],
                json.dumps(row, ensure_ascii=False),
            )
            for row in rows
        ],
    )
    inserted = connection.execute(
        "INSERT OR IGNORE INTO ais_reports SELECT * FROM incoming_reports RETURNING mmsi,observed",
    ).fetchall()
    updated = connection.execute("""
        UPDATE ais_reports AS stored
        SET payload=json_merge_patch(stored.payload, json_object(
            'flag',json_extract_string(incoming.payload,'$.flag'),
            'flag_country',json_extract_string(incoming.payload,'$.flag_country'),
            'flag_source',json_extract_string(incoming.payload,'$.flag_source')))
        FROM incoming_reports AS incoming
        WHERE stored.mmsi=incoming.mmsi AND stored.observed=incoming.observed
          AND stored.source=incoming.source
          AND json_extract_string(incoming.payload,'$.flag') IS NOT NULL
          AND (json_extract_string(stored.payload,'$.flag') IS DISTINCT FROM
               json_extract_string(incoming.payload,'$.flag') OR
               json_extract_string(stored.payload,'$.flag_country') IS DISTINCT FROM
               json_extract_string(incoming.payload,'$.flag_country'))
        RETURNING stored.mmsi
    """).fetchall()
    connection.execute("DROP TABLE incoming_reports")
    return inserted, bool(updated)


def reports_between(start, end, *, latest_per_vessel=False):
    with storage.connect() as connection:
        if latest_per_vessel:
            rows = connection.execute(
                """
                SELECT payload FROM (
                    SELECT payload, observed,
                           ROW_NUMBER() OVER (PARTITION BY mmsi ORDER BY observed DESC,
                               TRY_CAST(json_extract_string(payload,'$.received_at') AS TIMESTAMPTZ) DESC NULLS LAST,
                               source ASC) AS source_rank
                    FROM ais_reports WHERE observed >= ? AND observed < ?
                ) ranked WHERE source_rank=1 ORDER BY observed DESC
            """,
                [start, end],
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT payload FROM ais_reports WHERE observed >= ? AND observed < ? ORDER BY observed",
                [start, end],
            ).fetchall()
    return [json.loads(row[0]) for row in rows]


def track_points(selected):
    with storage.connect() as connection:
        return connection.execute(
            """
            WITH selected AS (
                SELECT UNNEST(?::VARCHAR[]) mmsi, UNNEST(?::TIMESTAMPTZ[]) cutoff
            ), ranked AS (
                SELECT a.mmsi, a.observed,
                       TRY_CAST(json_extract_string(a.payload,'$.lat') AS DOUBLE) lat,
                       TRY_CAST(json_extract_string(a.payload,'$.lon') AS DOUBLE) lon,
                       ROW_NUMBER() OVER (PARTITION BY a.mmsi,a.observed ORDER BY
                           TRY_CAST(json_extract_string(a.payload,'$.received_at') AS TIMESTAMPTZ) DESC NULLS LAST,
                           a.source ASC) source_rank
                FROM ais_reports a JOIN selected s ON a.mmsi=s.mmsi WHERE a.observed<=s.cutoff
            ) SELECT mmsi,observed,lat,lon FROM ranked WHERE source_rank=1
                AND lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180
            ORDER BY mmsi,observed
        """,
            [list(selected), [v["observed_at"] for v in selected.values()]],
        ).fetchall()


def latest_observed():
    with storage.connect() as connection:
        return connection.execute("SELECT MAX(observed) FROM ais_reports").fetchone()[0]


def positions_since(cutoff):
    with storage.connect() as connection:
        rows = connection.execute(
            """
            SELECT payload FROM (
                SELECT payload, observed,
                       ROW_NUMBER() OVER (PARTITION BY mmsi ORDER BY observed DESC,
                           TRY_CAST(json_extract_string(payload,'$.received_at') AS TIMESTAMPTZ) DESC NULLS LAST,
                           source ASC) AS source_rank
                FROM ais_reports WHERE observed >= ?
            ) ranked WHERE source_rank=1 ORDER BY observed DESC
        """,
            [cutoff],
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def known_mmsis():
    with storage.connect() as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT mmsi FROM ais_reports GROUP BY mmsi ORDER BY MAX(observed) DESC LIMIT 1000",
            ).fetchall()
        ]
