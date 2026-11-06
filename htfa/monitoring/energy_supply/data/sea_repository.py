"""Sea event, replay checkpoint and sampling-run persistence."""

from __future__ import annotations

from contextlib import contextmanager

from . import storage


@contextmanager
def transaction():
    with storage.connect() as connection:
        yield connection


def checkpoint(connection, mmsi, definition, earliest_new):
    return connection.execute(
        "SELECT through_at,state FROM sea_vessel_checkpoints WHERE mmsi=? AND definition=? "
        "AND through_at<? ORDER BY through_at DESC LIMIT 1",
        [mmsi, definition, earliest_new],
    ).fetchone()


def positions_since(connection, mmsi, lower, *, exclusive):
    operator = ">" if exclusive else ">="
    return connection.execute(
        f"SELECT observed,lat,lon,source FROM ais_positions WHERE mmsi=? AND observed{operator}? "
        "ORDER BY observed,source",
        [mmsi, lower],
    ).fetchall()


def replace_replay(connection, provider, definition, mmsi, lower, events, checkpoint):
    connection.execute(
        "DELETE FROM sea_entries WHERE provider=? AND definition=? AND mmsi=? "
        "AND TRY_CAST(json_extract_string(evidence,'$.confirmed_at') AS TIMESTAMPTZ)>?",
        [provider, definition, mmsi, lower],
    )
    if events:
        connection.executemany(
            "INSERT OR IGNORE INTO sea_entries VALUES (?,?,?,?,?,?,?)", events
        )
    connection.execute(
        "DELETE FROM sea_vessel_checkpoints WHERE mmsi=? AND definition=? AND through_at>?",
        [mmsi, definition, lower],
    )
    if checkpoint:
        connection.execute(
            "INSERT OR REPLACE INTO sea_vessel_checkpoints VALUES (?,?,?,?,?)",
            checkpoint,
        )


def sampling_runs(connection, start, end):
    return connection.execute(
        "SELECT started_at,status FROM collection_runs WHERE provider='Open Waters' "
        "AND started_at>=? AND started_at<=? ORDER BY started_at",
        [start, end],
    ).fetchall()


def event_count(connection, provider, definition, start, end):
    return connection.execute(
        "SELECT COUNT(*) FROM sea_entries WHERE provider=? AND definition=? "
        "AND entered_at>=? AND entered_at<?",
        [provider, definition, start, end],
    ).fetchone()[0]


def valid_run_count(connection, start, end):
    return connection.execute(
        "SELECT COUNT(*) FROM collection_runs WHERE provider='Open Waters' "
        "AND status IN ('ok','partial') AND started_at>=? AND started_at<=?",
        [start, end],
    ).fetchone()[0]


def daily_counts(connection, provider, start, end):
    return dict(
        connection.execute(
            "SELECT sea,COUNT(*) FROM sea_entries WHERE provider=? AND entered_at>=? "
            "AND entered_at<? GROUP BY sea",
            [provider, start, end],
        ).fetchall()
    )
