"""Unified DuckDB infrastructure for the ``data/`` pipeline.

Every ``source_*.py`` module uses the helpers here so that all ten data
sources land in one database (``data/UAE/uae.duckdb``) with one metadata
convention. The database is local-only and never committed to Git.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb

DATA_DIR = Path(__file__).resolve().parent
DB_PATH = DATA_DIR / "uae.duckdb"

# --------------------------------------------------------------------------
# Base DDL.  Each statement is idempotent; dld.* objects live in
# source_dld.py because their full typed schema is large.
# --------------------------------------------------------------------------

_BASE_DDL = (
    # --- monthly / quarterly / annual observation tables ---
    """
    CREATE TABLE IF NOT EXISTS baker_hughes_monthly (
        period   DATE    PRIMARY KEY,
        oil_rigs BIGINT  NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cbuae_monthly (
        period        DATE           NOT NULL,
        indicator     VARCHAR        NOT NULL,
        value         DECIMAL(28, 3),
        source_period VARCHAR,
        source_file   VARCHAR,
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gfs_quarterly (
        year      SMALLINT      NOT NULL,
        quarter   TINYINT       NOT NULL,
        indicator VARCHAR       NOT NULL,
        value     DECIMAL(28, 3),
        PRIMARY KEY (year, quarter, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gfs_annual (
        year      SMALLINT      NOT NULL,
        indicator VARCHAR       NOT NULL,
        value     DECIMAL(28, 3),
        PRIMARY KEY (year, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pmi_monthly (
        period       DATE    PRIMARY KEY,
        value        DOUBLE,
        source_label VARCHAR,
        source_url   VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS foreign_labour_monthly (
        period       DATE    NOT NULL,
        series       VARCHAR NOT NULL,
        value        DOUBLE,
        quality_flag VARCHAR,
        PRIMARY KEY (period, series)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comtrade_monthly (
        period   DATE    NOT NULL,
        category VARCHAR NOT NULL,
        value    DOUBLE,
        units    DOUBLE,
        PRIMARY KEY (period, category)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comtrade_partner_detail (
        period   DATE    NOT NULL,
        category VARCHAR NOT NULL,
        reporter VARCHAR NOT NULL,
        partner  VARCHAR NOT NULL,
        value    DOUBLE,
        PRIMARY KEY (period, category, reporter, partner)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comtrade_quantity_detail (
        period                DATE    NOT NULL,
        hs6                   VARCHAR NOT NULL,
        item_count            DOUBLE,
        source_type           VARCHAR,
        reported_estimated    VARCHAR,
        mirror_reporter_count BIGINT,
        PRIMARY KEY (period, hs6)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mesteel_monthly (
        period       DATE    NOT NULL,
        product      VARCHAR NOT NULL,
        lower        DOUBLE,
        upper        DOUBLE,
        midpoint     DOUBLE,
        origin_label VARCHAR,
        PRIMARY KEY (period, product)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ded_monthly (
        month  DATE    NOT NULL,
        series VARCHAR NOT NULL,
        value  DOUBLE,
        PRIMARY KEY (month, series)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dld_sales_monthly (
        period    DATE            NOT NULL,
        indicator VARCHAR         NOT NULL,
        count     BIGINT,
        value_aed DECIMAL(24, 2),
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dld_lease_monthly (
        period     DATE    NOT NULL,
        indicator  VARCHAR NOT NULL,
        value      DOUBLE,
        source_url VARCHAR,
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ded_monthly_by_type (
        month      DATE    NOT NULL,
        legal_form VARCHAR NOT NULL,
        records    BIGINT,
        PRIMARY KEY (month, legal_form)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS employment_search_index (
        month   DATE    NOT NULL,
        keyword VARCHAR NOT NULL,
        value   DOUBLE,
        PRIMARY KEY (month, keyword)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dld_investment_pipeline_weekly (
        week_end                          DATE PRIMARY KEY,
        confirmed_new_projects_28d        DOUBLE,
        offplan_sales_28d                 DOUBLE,
        active_projects_28d               DOUBLE,
        project_launch_index              DOUBLE,
        offplan_absorption_index          DOUBLE,
        project_commercial_transition_index DOUBLE
    )
    """,
    # --- metadata ---
    """
    CREATE TABLE IF NOT EXISTS meta_indicator_dictionary (
        indicator_name VARCHAR PRIMARY KEY,
        frequency      VARCHAR,
        unit           VARCHAR,
        source         VARCHAR,
        type           VARCHAR,
        industry       VARCHAR,
        updated_at     DATE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta_column_dictionary (
        object_name VARCHAR NOT NULL,
        column_name VARCHAR NOT NULL,
        data_type   VARCHAR,
        group_cn    VARCHAR,
        meaning_cn  VARCHAR,
        relates_to  VARCHAR,
        caveat_cn   VARCHAR,
        PRIMARY KEY (object_name, column_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta_source_runs (
        source      VARCHAR   NOT NULL,
        started_at  TIMESTAMP NOT NULL,
        finished_at TIMESTAMP,
        status      VARCHAR,
        inputs      VARCHAR,
        note        VARCHAR
    )
    """,
)


def connect(path: Path | str | None = None, *, read_only: bool = False):
    """Open (and create on first use) the unified database."""

    return duckdb.connect(str(path or DB_PATH), read_only=read_only)


def init_schema(con) -> None:
    """Create every base table once; safe to call repeatedly."""

    for statement in _BASE_DDL:
        con.execute(statement)


def table_exists(con, name: str) -> bool:
    """Return whether ``name`` (optionally schema-qualified) exists."""

    if "." in name:
        schema, table = name.split(".", 1)
        row = con.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()
    else:
        row = con.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = ?",
            [name],
        ).fetchone()
    return row is not None


def ensure(con, name: str, ddl: str) -> None:
    """Create a table from its DDL when it does not exist yet."""

    if not table_exists(con, name):
        con.execute(ddl)


def replace(con, table: str, rows: Iterable[dict[str, Any]]) -> int:
    """Replace all rows of ``table`` inside one transaction.

    The caller should wrap the call in ``con.begin()`` when several tables
    form one atomic refresh.  Returns the inserted row count.
    """

    records = [dict(row) for row in rows]
    if not records:
        con.execute(f"DELETE FROM {table}")
        return 0
    columns = list(records[0])
    column_sql = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    con.execute(f"DELETE FROM {table}")
    con.executemany(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        [tuple(record[column] for column in columns) for record in records],
    )
    return len(records)


def upsert_dictionary_rows(con, rows: Iterable[dict[str, Any]]) -> None:
    """Merge indicator dictionary rows keyed on ``indicator_name``."""

    for row in rows:
        record = dict(row)
        con.execute(
            """
            INSERT OR REPLACE INTO meta_indicator_dictionary
                (indicator_name, frequency, unit, source, type, industry, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record["indicator_name"],
                record.get("frequency"),
                record.get("unit"),
                record.get("source"),
                record.get("type"),
                record.get("industry"),
                record.get("updated_at"),
            ],
        )


def log_run(
    con,
    source: str,
    status: str,
    *,
    inputs: str = "",
    note: str = "",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    """Record one pipeline run in ``meta_source_runs``."""

    con.execute(
        """
        INSERT INTO meta_source_runs
            (source, started_at, finished_at, status, inputs, note)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            source,
            started_at or datetime.now(),
            finished_at or datetime.now(),
            status,
            inputs,
            note,
        ],
    )


__all__ = [
    "DATA_DIR",
    "DB_PATH",
    "connect",
    "ensure",
    "init_schema",
    "log_run",
    "replace",
    "table_exists",
    "upsert_dictionary_rows",
]
