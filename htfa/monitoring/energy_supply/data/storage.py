"""One DuckDB for source evidence, catalogs, daily facts, AIS and sea events.

Presentation connections are short-lived and strictly read-only. Maintenance
jobs select a separate writable candidate through an explicit context; the
publication entry point serializes writers with an OS file lock.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from pathlib import Path

import duckdb
from htfa.monitoring.uae.contracts.paths import ASSETS_DIR

DB_PATH = ASSETS_DIR / "uae.duckdb"

ROOT = Path(__file__).resolve().parents[1]
_LOCK = threading.RLock()
_LOCAL = threading.local()
_READY = set()
_PORTWATCH_BATCH_IDS = count()


_JOB_DATABASE = ContextVar("energy_job_database", default=None)


@contextmanager
def job_database(path):
    """Allow writes only within an explicitly selected maintenance candidate."""
    token = _JOB_DATABASE.set(Path(path).resolve())
    try:
        yield
    finally:
        _JOB_DATABASE.reset(token)


def read_only():
    return _JOB_DATABASE.get() is None


def database_path():
    return _JOB_DATABASE.get() or DB_PATH


def database_identity():
    """Identify the physical published file and any active maintenance WAL."""
    path = database_path()
    stat = path.stat()
    wal = Path(str(path) + ".wal")
    wal_stat = wal.stat() if wal.exists() else None
    return (
        str(path),
        stat.st_ino,
        stat.st_mtime_ns,
        stat.st_size,
        (wal_stat.st_mtime_ns, wal_stat.st_size) if wal_stat else None,
    )


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS app_meta (key VARCHAR PRIMARY KEY, value JSON);
CREATE TABLE IF NOT EXISTS documents (
    path VARCHAR PRIMARY KEY, sha256 VARCHAR, media_type VARCHAR, content BLOB,
    row_count BIGINT, ingested_at TIMESTAMPTZ DEFAULT current_timestamp);
CREATE TABLE IF NOT EXISTS document_rows (
    path VARCHAR, section VARCHAR, row_no BIGINT, payload JSON,
    PRIMARY KEY(path,section,row_no));
CREATE TABLE IF NOT EXISTS catalogs (
    kind VARCHAR, id VARCHAR, payload JSON, updated_at TIMESTAMPTZ DEFAULT current_timestamp,
    PRIMARY KEY(kind,id));
CREATE TABLE IF NOT EXISTS portwatch_daily (
    kind VARCHAR, node_id VARCHAR, day DATE, payload JSON, source_url VARCHAR,
    fetched_at TIMESTAMPTZ DEFAULT current_timestamp, PRIMARY KEY(kind,node_id,day));
CREATE TABLE IF NOT EXISTS portwatch_cache (key VARCHAR PRIMARY KEY, saved DOUBLE, payload BLOB);
CREATE TABLE IF NOT EXISTS source_queries (
    id VARCHAR PRIMARY KEY, endpoint VARCHAR, params JSON, response JSON,
    retrieved_at TIMESTAMPTZ DEFAULT current_timestamp);
CREATE TABLE IF NOT EXISTS ais_reports (
    mmsi VARCHAR, observed TIMESTAMPTZ, source VARCHAR, payload JSON,
    PRIMARY KEY(mmsi,observed,source));
CREATE TABLE IF NOT EXISTS archive_imports (sha256 VARCHAR PRIMARY KEY, metadata JSON);
CREATE TABLE IF NOT EXISTS sea_manifests (provider VARCHAR PRIMARY KEY, manifest JSON);
CREATE TABLE IF NOT EXISTS sea_entries (
    provider VARCHAR, definition VARCHAR, sea VARCHAR, mmsi VARCHAR,
    entered_at TIMESTAMPTZ, day DATE, evidence JSON,
    PRIMARY KEY(provider,definition,sea,mmsi,entered_at));
CREATE TABLE IF NOT EXISTS sea_coverage (
    provider VARCHAR, definition VARCHAR, sea VARCHAR, day DATE, status VARCHAR,
    event_count BIGINT, PRIMARY KEY(provider,definition,sea,day));
CREATE TABLE IF NOT EXISTS sea_vessel_checkpoints (
    mmsi VARCHAR, definition VARCHAR, day DATE, through_at TIMESTAMPTZ, state JSON,
    PRIMARY KEY(mmsi,definition,day));
CREATE TABLE IF NOT EXISTS collection_runs (
    id VARCHAR PRIMARY KEY, provider VARCHAR, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
    status VARCHAR, reports BIGINT, details JSON);
CREATE INDEX IF NOT EXISTS ais_time ON ais_reports(observed);
CREATE INDEX IF NOT EXISTS sea_day ON sea_entries(provider,day);
CREATE VIEW IF NOT EXISTS ais_positions AS
    SELECT mmsi,observed,source,
           TRY_CAST(json_extract_string(payload,'$.lat') AS DOUBLE) AS lat,
           TRY_CAST(json_extract_string(payload,'$.lon') AS DOUBLE) AS lon,payload FROM ais_reports;
CREATE VIEW IF NOT EXISTS sea_daily_observed AS
    SELECT provider,definition,sea,day,COUNT(*) AS passages FROM sea_entries
    GROUP BY provider,definition,sea,day;
CREATE VIEW IF NOT EXISTS asset_catalog AS
    SELECT id,
           json_extract_string(payload,'$.country') AS country,
           json_extract_string(payload,'$.name') AS name,
           json_extract_string(payload,'$.asset_level') AS asset_level,
           json_extract_string(payload,'$.commodity') AS commodity,
           json_extract_string(payload,'$.data_date') AS measurement_date,
           json_extract_string(payload,'$.metric_type') AS metric_type,
           TRY_CAST(json_extract_string(payload,'$.value_numeric') AS DECIMAL(24,8)) AS value_numeric,
           json_extract_string(payload,'$.unit') AS unit,
           json_extract_string(payload,'$.source_url') AS source_url,payload
    FROM catalogs WHERE kind='assets';
CREATE VIEW IF NOT EXISTS portwatch_metrics AS
    SELECT kind,node_id,day,
           TRY_CAST(json_extract_string(payload,'$.portcalls') AS DOUBLE) AS portcalls,
           TRY_CAST(json_extract_string(payload,'$.n_total') AS DOUBLE) AS passages,
           source_url,payload FROM portwatch_daily;
"""


@contextmanager
def connect(path=None):
    path = Path(path).resolve() if path is not None else database_path()
    if not read_only() and path != database_path():
        raise RuntimeError("维护作业只能写入显式选择的候选数据库")
    nested = getattr(_LOCAL, "connections", {})
    if str(path) in nested:
        yield nested[str(path)]
        return
    with _LOCK:
        with duckdb.connect(str(path), read_only=read_only()) as conn:
            if not read_only():
                conn.execute("CREATE SCHEMA IF NOT EXISTS energy_supply")
            conn.execute("SET schema='energy_supply'")
            if not read_only():
                conn.execute(SCHEMA)
            if not hasattr(_LOCAL, "connections"):
                _LOCAL.connections = {}
            _LOCAL.connections[str(path)] = conn
            conn.execute("BEGIN TRANSACTION")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                _LOCAL.connections.pop(str(path), None)


def meta(key, default=None, conn=None):
    if conn is None:
        with connect() as handle:
            return meta(key, default, handle)
    row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_meta(key, value, conn=None):
    if conn is None:
        with connect() as handle:
            return set_meta(key, value, handle)
    conn.execute("INSERT OR REPLACE INTO app_meta VALUES (?,?)", (key, encode(value)))


def save_query(endpoint, params, response, conn=None):
    """Retain an upstream response and its request parameters as source evidence."""
    if conn is None:
        with connect() as handle:
            return save_query(endpoint, params, response, handle)
    query_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO source_queries (id,endpoint,params,response) VALUES (?,?,?,?)",
        (query_id, endpoint, encode(params), encode(response)),
    )
    return query_id


def revision(kind, conn=None):
    """Read the current version of one persisted data family."""
    return meta(f"data_revision:{kind}", 0, conn)


def revisions(kinds, conn=None):
    """Read several data versions in one short transaction."""
    if conn is None:
        with connect() as handle:
            return revisions(kinds, handle)
    keys = [f"data_revision:{kind}" for kind in kinds]
    if not keys:
        return {}
    rows = conn.execute(
        "SELECT key,value FROM app_meta WHERE key IN ("
        + ",".join("?" for _ in keys)
        + ")",
        keys,
    ).fetchall()
    found = {key: json.loads(value) for key, value in rows}
    return {kind: found.get(f"data_revision:{kind}", 0) for kind in kinds}


def bump_revision(kind, conn=None):
    """Advance a data version in the same transaction as its facts."""
    if conn is None:
        with connect() as handle:
            return bump_revision(kind, handle)
    value = revision(kind, conn) + 1
    set_meta(f"data_revision:{kind}", value, conn)
    return value


def _rows(value, section="$"):
    if isinstance(value, list):
        for i, item in enumerate(value):
            yield section, i, item
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                yield from _rows(item, section + "." + str(key))


def ingest_document(relative, path=None, conn=None):
    """Versioned source files are bootstrap evidence; runtime reads use DuckDB."""
    original = ROOT / relative
    content = original.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if conn is None:
        with connect(path) as handle:
            return ingest_document(relative, path, handle)
    old = conn.execute(
        "SELECT sha256 FROM documents WHERE path=?", (relative,)
    ).fetchone()
    if old and old[0] == digest:
        return
    suffix = original.suffix.lower()
    if suffix in (".json", ".geojson"):
        values = list(_rows(json.loads(content.decode("utf-8-sig"))))
        media = "application/json"
    elif suffix == ".csv":
        values = [
            ("$", i, row)
            for i, row in enumerate(
                csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            )
        ]
        media = "text/csv"
    else:
        values, media = [], "application/octet-stream"
    conn.execute("DELETE FROM document_rows WHERE path=?", (relative,))
    if values:
        conn.executemany(
            "INSERT INTO document_rows VALUES (?,?,?,?)",
            [(relative, section, i, encode(row)) for section, i, row in values],
        )
    conn.execute(
        "INSERT OR REPLACE INTO documents(path,sha256,media_type,content,row_count) VALUES (?,?,?,?,?)",
        (relative, digest, media, content, len(values)),
    )


def read_json(relative):
    with connect() as conn:
        row = conn.execute(
            "SELECT content FROM documents WHERE path=?", (relative,)
        ).fetchone()
    if row is None:
        raise FileNotFoundError(relative)
    return json.loads(bytes(row[0]).decode("utf-8-sig"))


def save_catalog(kind, rows, key="portid"):
    with connect() as conn:
        if kind == "assets":
            pairs = [(row["country"] + "\x1f" + row["name"], row) for row in rows]
        else:
            pairs = [(str(row[key]), row) for row in rows]
        if len({pid for pid, _ in pairs}) != len(pairs):
            raise ValueError("目录主键重复：" + kind)
        encoded = [(kind, pid, encode(row)) for pid, row in pairs]
        existing = conn.execute(
            "SELECT kind,id,payload FROM catalogs WHERE kind=? ORDER BY id", (kind,)
        ).fetchall()
        if existing == sorted(encoded, key=lambda row: row[1]):
            return
        conn.execute("DELETE FROM catalogs WHERE kind=?", (kind,))
        if encoded:
            conn.executemany(
                "INSERT INTO catalogs(kind,id,payload) VALUES (?,?,?)", encoded
            )
        if kind in {"ports", "chokepoints", "assets"}:
            bump_revision(
                "ports"
                if kind == "ports"
                else "chokepoints"
                if kind == "chokepoints"
                else "assets",
                conn,
            )


def load_catalog(kind):
    with connect() as conn:
        rows = [
            json.loads(r[0])
            for r in conn.execute(
                "SELECT payload FROM catalogs WHERE kind=? ORDER BY id", (kind,)
            ).fetchall()
        ]
    if kind == "assets":

        def restore(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "value_numeric" and item is not None:
                        value[key] = Decimal(str(item))
                    else:
                        restore(item)
            elif isinstance(value, list):
                for item in value:
                    restore(item)

        restore(rows)
    return rows


def cached_catalog(kind, max_age_seconds=86_400, allow_stale=False):
    """Return a persisted catalog, optionally regardless of its age."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT payload, updated_at FROM catalogs WHERE kind=? ORDER BY id", (kind,)
        ).fetchall()
    if not rows:
        return None
    updated_at = min(row[1] for row in rows)
    if (
        not allow_stale
        and (datetime.now(timezone.utc) - updated_at).total_seconds() > max_age_seconds
    ):
        return None
    decoded = [json.loads(row[0]) for row in rows]
    return decoded


def put_binary_document(relative, content, media, conn=None):
    if conn is None:
        with connect() as handle:
            return put_binary_document(relative, content, media, handle)
    conn.execute(
        "INSERT OR REPLACE INTO documents(path,sha256,media_type,content,row_count) VALUES (?,?,?,?,0)",
        (relative, hashlib.sha256(content).hexdigest(), media, content),
    )


def binary_document(relative):
    with connect() as conn:
        row = conn.execute(
            "SELECT content FROM documents WHERE path=?", (relative,)
        ).fetchone()
    return bytes(row[0]) if row else None


def save_portwatch(kind, rows, source_url, conn=None):
    if conn is None:
        with connect() as handle:
            return save_portwatch(kind, rows, source_url, handle)
    if rows:
        import pyarrow as pa

        batch_name = f"portwatch_incoming_{next(_PORTWATCH_BATCH_IDS)}"
        incoming = pa.Table.from_pylist(
            [
                {
                    "kind": kind,
                    "node_id": str(row["portid"]),
                    "day": str(row["date"])[:10],
                    "payload": encode(row),
                    "source_url": source_url,
                }
                for row in rows
            ]
        )
        conn.register(batch_name, incoming)
        try:
            changed = conn.execute(
                f"""SELECT EXISTS(
                    SELECT 1 FROM {batch_name} incoming
                    LEFT JOIN portwatch_daily facts
                      ON facts.kind=incoming.kind AND facts.node_id=incoming.node_id
                     AND facts.day=CAST(incoming.day AS DATE)
                    WHERE facts.node_id IS NULL OR facts.payload IS DISTINCT FROM incoming.payload
                       OR facts.source_url IS DISTINCT FROM incoming.source_url
                )"""
            ).fetchone()[0]
            conn.execute(
                "INSERT OR REPLACE INTO portwatch_daily(kind,node_id,day,payload,source_url) "
                f"SELECT kind,node_id,CAST(day AS DATE),payload,source_url FROM {batch_name}"
            )
        finally:
            conn.unregister(batch_name)
        if changed:
            bump_revision(kind, conn)


def portwatch_window_latest_fetch(kind, node_ids, first, last):
    node_ids = tuple(sorted(set(str(node_id) for node_id in node_ids)))
    if kind not in ("ports", "chokepoints") or not node_ids:
        return None
    placeholders = ",".join("?" for _ in node_ids)
    with connect() as conn:
        return conn.execute(
            f"""SELECT MAX(fetched_at) FROM portwatch_daily
                WHERE kind=? AND node_id IN ({placeholders}) AND day BETWEEN ? AND ?""",
            [kind, *node_ids, first, last],
        ).fetchone()[0]


def cached_portwatch_rows_since(kind, node_ids, first, last, since):
    """Return validated facts fetched after a compressed window snapshot."""
    node_ids = tuple(sorted(set(str(node_id) for node_id in node_ids)))
    if kind not in ("ports", "chokepoints") or not node_ids:
        return []
    placeholders = ",".join("?" for _ in node_ids)
    with connect() as conn:
        result = conn.execute(
            f"""SELECT node_id,day,payload FROM portwatch_daily
                WHERE kind=? AND node_id IN ({placeholders})
                  AND day BETWEEN ? AND ? AND fetched_at > ?
                ORDER BY day,node_id""",
            [kind, *node_ids, first, last, since],
        ).fetchall()
    rows = []
    for node_id, day, payload in result:
        row = json.loads(payload) if isinstance(payload, str) else dict(payload)
        row.setdefault("portid", str(node_id))
        row.setdefault("date", day.isoformat())
        rows.append(row)
    return rows


def cached_portwatch_window(
    kind,
    node_ids,
    first,
    last,
    max_age_seconds=86_400,
    with_metadata=False,
    allow_stale=False,
):
    """Read a fully populated node/day window from the persistent fact table.

    A partially stored window is not a cache hit: missing days must remain
    distinguishable from zero-valued observations, so callers can fetch and
    verify the complete source window instead.
    """
    node_ids = tuple(sorted(set(str(node_id) for node_id in node_ids)))
    if kind not in ("ports", "chokepoints") or not node_ids or first > last:
        return None

    placeholders = ",".join("?" for _ in node_ids)
    with connect() as conn:
        result = conn.execute(
            f"""SELECT node_id, day, payload, fetched_at FROM portwatch_daily
                WHERE kind=? AND node_id IN ({placeholders})
                  AND day BETWEEN ? AND ? ORDER BY day, node_id""",
            [kind, *node_ids, first, last],
        ).fetchall()

    expected = {
        (node_id, (first + timedelta(days=offset)).isoformat())
        for node_id in node_ids
        for offset in range((last - first).days + 1)
    }
    rows_by_key = {}
    last_day_fetched = []
    for node_id, day, payload, fetched_at in result:
        key = (str(node_id), day.isoformat())
        row = json.loads(payload) if isinstance(payload, str) else dict(payload)
        row.setdefault("portid", str(node_id))
        row.setdefault("date", key[1])
        rows_by_key[key] = row
        if day == last:
            last_day_fetched.append(fetched_at)
    if rows_by_key.keys() != expected:
        return None
    if not last_day_fetched or (
        not allow_stale
        and (datetime.now(timezone.utc) - min(last_day_fetched)).total_seconds()
        > max_age_seconds
    ):
        return None
    rows = [rows_by_key[key] for key in sorted(expected)]
    if with_metadata:
        return rows, min(row[3] for row in result)
    return rows


def cached_portwatch_observations(kind, node_ids, first, last):
    """Return whatever local daily facts exist in a date window, including gaps.

    This serves offline reads and failed-refresh fallbacks. Missing days remain missing;
    callers must not interpret them as zero or fall back to the network.
    """
    node_ids = tuple(sorted(set(str(node_id) for node_id in node_ids)))
    if kind not in ("ports", "chokepoints") or not node_ids or first > last:
        return []
    placeholders = ",".join("?" for _ in node_ids)
    with connect() as conn:
        result = conn.execute(
            f"""SELECT node_id, day, payload FROM portwatch_daily
                WHERE kind=? AND node_id IN ({placeholders})
                  AND day BETWEEN ? AND ? ORDER BY day, node_id""",
            [kind, *node_ids, first, last],
        ).fetchall()
    rows = []
    for node_id, day, payload in result:
        row = json.loads(payload) if isinstance(payload, str) else dict(payload)
        row.setdefault("portid", str(node_id))
        row.setdefault("date", day.isoformat())
        rows.append(row)
    return rows


def portwatch_daily_totals(node_ids, last):
    """Aggregate local daily calls, preserving a gap if any covered port is missing."""
    from htfa.monitoring.energy_supply.contracts.records import SHIP_TYPES

    node_ids = tuple(sorted(set(str(value) for value in node_ids)))
    if not node_ids or last is None:
        return []
    fields = ["portcalls", *(f"portcalls_{kind}" for kind in SHIP_TYPES)]
    values = ",".join(
        f"TRY_CAST(json_extract_string(payload, '$.{field}') AS DOUBLE) AS {field}"
        for field in fields
    )
    sums = ",".join(
        f"CASE WHEN COUNT(*) FILTER (WHERE {field} >= 0 AND isfinite({field})) = {len(node_ids)} "
        f"THEN SUM({field}) END AS {field}"
        for field in fields
    )
    placeholders = ",".join("?" for _ in node_ids)
    with connect() as conn:
        rows = conn.execute(
            f"""
            WITH observations AS (
                SELECT day, {values} FROM portwatch_daily
                WHERE kind='ports' AND node_id IN ({placeholders}) AND day <= ?
            ), daily AS (SELECT day, {sums} FROM observations GROUP BY day)
            SELECT CAST(calendar.day AS DATE), {",".join("daily." + field for field in fields)}
            FROM generate_series((SELECT MIN(day) FROM observations), CAST(? AS DATE), INTERVAL 1 DAY) AS calendar(day)
            LEFT JOIN daily ON daily.day=calendar.day ORDER BY calendar.day
        """,
            [*node_ids, last, last],
        ).fetchall()
    return [dict(zip(["date", *fields], row)) for row in rows]


def cached_portwatch_periods(kind, node_ids, periods):
    """Read sparse local facts across several disjoint indicator windows."""
    node_ids = tuple(sorted(set(str(node_id) for node_id in node_ids)))
    periods = tuple((start, end) for start, end in periods if start <= end)
    if kind not in ("ports", "chokepoints") or not node_ids or not periods:
        return []
    placeholders = ",".join("?" for _ in node_ids)
    clauses = " OR ".join("(day BETWEEN ? AND ?)" for _ in periods)
    args = [kind, *node_ids, *(value for pair in periods for value in pair)]
    with connect() as conn:
        result = conn.execute(
            f"SELECT node_id,day,payload FROM portwatch_daily WHERE kind=? "
            f"AND node_id IN ({placeholders}) AND ({clauses}) ORDER BY day,node_id",
            args,
        ).fetchall()
    rows = []
    for node_id, day, payload in result:
        row = json.loads(payload) if isinstance(payload, str) else dict(payload)
        row.setdefault("portid", str(node_id))
        row.setdefault("date", day.isoformat())
        rows.append(row)
    return rows


def cached_portwatch_latest_day(kind, max_age_seconds=86_400, allow_stale=False):
    """Return the latest persisted source day, optionally regardless of age."""
    if kind not in ("ports", "chokepoints"):
        return None
    with connect() as conn:
        result = conn.execute(
            """SELECT MAX(day), MIN(fetched_at) FROM portwatch_daily
               WHERE kind=? AND day=(SELECT MAX(day) FROM portwatch_daily WHERE kind=?)""",
            [kind, kind],
        ).fetchone()
    day, fetched_at = result
    if day is None or fetched_at is None:
        return None
    if (
        not allow_stale
        and (datetime.now(timezone.utc) - fetched_at).total_seconds() > max_age_seconds
    ):
        return None
    return day


def initialize():
    """Validate the explicitly selected maintenance database."""
    with connect() as conn:
        conn.execute("SELECT key FROM app_meta LIMIT 1")
    return {"database": str(database_path())}


def initialize_runtime():
    """Read the published schema without creating or migrating any data."""
    if not read_only():
        raise RuntimeError("页面禁止使用可写数据库连接")
    with connect() as conn:
        conn.execute("SELECT key FROM app_meta LIMIT 1")
    return {"database": str(database_path()), "read_only": True}


def status():
    with connect() as conn:
        counts = {
            name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in (
                "documents",
                "document_rows",
                "catalogs",
                "portwatch_daily",
                "ais_reports",
                "sea_entries",
                "collection_runs",
            )
        }
        start = meta("local_collection_started_at", conn=conn)
        latest = conn.execute("SELECT MAX(observed) FROM ais_reports").fetchone()[0]
    return {
        "counts": counts,
        "started_at": start,
        "latest_observed_at": latest.isoformat() if latest else None,
    }


def backup_bytes():
    """Consistent portable database snapshot under the same reader/writer lock."""
    if read_only():
        return database_path().read_bytes()
    with connect() as conn:
        conn.execute("CHECKPOINT")
        return database_path().read_bytes()


if __name__ == "__main__":
    print(encode({"migration": initialize(), "status": status()}))
