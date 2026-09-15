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

from .paths import DATA_DIR, SCRIPTS_DIR

DB_PATH = DATA_DIR / "uae.duckdb"

# 这些表保留的是可追溯的细粒度派生数据，而不是仪表盘最终指标。
# 物理表统一放入 detail schema；旧名称由只读兼容视图承接。
DETAIL_TABLE_ALIASES = {
    "comtrade_partner_detail": "detail.comtrade_partner_detail",
    "comtrade_quantity_detail": "detail.comtrade_quantity_detail",
    "eurostat_air_monthly": "detail.eurostat_air_monthly",
    "emirates_post_monthly": "detail.emirates_post_monthly",
    "portwatch_uae_daily": "detail.portwatch_uae_daily",
    "portwatch_chokepoint_daily": "detail.portwatch_chokepoint_daily",
    "dld.transactions": "detail.dld_transactions",
    "wam_military_strike_daily": "detail.wam_military_strike_daily",
}

_DETAIL_MIGRATIONS = (
    ("main", "comtrade_partner_detail", "comtrade_partner_detail"),
    ("main", "comtrade_quantity_detail", "comtrade_quantity_detail"),
    ("main", "eurostat_air_monthly", "eurostat_air_monthly"),
    ("main", "emirates_post_monthly", "emirates_post_monthly"),
    ("main", "portwatch_uae_daily", "portwatch_uae_daily"),
    ("main", "portwatch_chokepoint_daily", "portwatch_chokepoint_daily"),
    ("dld", "transactions", "dld_transactions"),
)

_DETAIL_PRIMARY_KEYS = {
    "comtrade_partner_detail": "period, category, reporter, partner",
    "comtrade_quantity_detail": "period, hs6",
    "eurostat_air_monthly": "period, dataset, geo, partner, schedule, unit, tra_meas",
    "emirates_post_monthly": "period, origin_city, destn_city, service",
    "portwatch_uae_daily": "date, portid",
    "portwatch_chokepoint_daily": "date, portid",
    "wam_military_strike_daily": "date",
}

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
    CREATE TABLE IF NOT EXISTS opec_crude_production_monthly (
        period        DATE PRIMARY KEY,
        production_bpd DOUBLE NOT NULL,
        source_period VARCHAR,
        source_file   VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS eia_brent_spot_daily (
        period        DATE PRIMARY KEY,
        price_usd_bbl DOUBLE NOT NULL,
        source_file   VARCHAR
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
    CREATE TABLE IF NOT EXISTS detail.comtrade_partner_detail (
        period   DATE    NOT NULL,
        category VARCHAR NOT NULL,
        reporter VARCHAR NOT NULL,
        partner  VARCHAR NOT NULL,
        value    DOUBLE,
        PRIMARY KEY (period, category, reporter, partner)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS detail.comtrade_quantity_detail (
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
    CREATE TABLE IF NOT EXISTS uaewps_monthly (
        period      DATE           NOT NULL,
        indicator   VARCHAR        NOT NULL,
        value       DECIMAL(28, 3),
        source_file VARCHAR,
        note        VARCHAR,
        PRIMARY KEY (period, indicator)
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
    # --- EU↔UAE / US↔UAE 航空客货运（月度） ---
    """
    CREATE TABLE IF NOT EXISTS detail.eurostat_air_monthly (
        period   DATE           NOT NULL,
        dataset  VARCHAR        NOT NULL,
        geo      VARCHAR        NOT NULL,
        partner  VARCHAR        NOT NULL,
        schedule VARCHAR        NOT NULL,
        unit     VARCHAR        NOT NULL,
        tra_meas VARCHAR        NOT NULL,
        value    DECIMAL(28, 3),
        PRIMARY KEY (period, dataset, geo, partner, schedule, unit, tra_meas)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dot_t100_monthly (
        period      DATE           NOT NULL,
        indicator   VARCHAR        NOT NULL,
        value       DECIMAL(28, 3),
        source_file VARCHAR,
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS detail.emirates_post_monthly (
        period      DATE    NOT NULL,
        origin_city VARCHAR NOT NULL,
        destn_city  VARCHAR NOT NULL,
        service     VARCHAR NOT NULL,
        volume      BIGINT,
        raw_rows    BIGINT,
        PRIMARY KEY (period, origin_city, destn_city, service)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tdra_telecom_monthly (
        period      DATE           NOT NULL,
        indicator   VARCHAR        NOT NULL,
        value       DECIMAL(20, 4),
        source_file VARCHAR,
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cloudflare_radar_daily (
        period      DATE           NOT NULL,
        indicator   VARCHAR        NOT NULL,
        value       DECIMAL(12, 3),
        source_file VARCHAR,
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rta_transport_monthly (
        period    DATE    NOT NULL,
        indicator VARCHAR NOT NULL,
        value     DECIMAL(20, 3),
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rta_transport_daily (
        period    DATE    NOT NULL,
        indicator VARCHAR NOT NULL,
        value     DECIMAL(20, 3),
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scad_monthly (
        period      DATE           NOT NULL,
        indicator   VARCHAR        NOT NULL,
        value       DECIMAL(28, 3),
        source_file VARCHAR,
        PRIMARY KEY (period, indicator)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS detail.wam_military_strike_daily (
        date                    DATE PRIMARY KEY,
        ballistic_missiles      BIGINT NOT NULL,
        cruise_missiles         BIGINT NOT NULL,
        uavs                    BIGINT NOT NULL,
        unclassified_missiles  BIGINT NOT NULL,
        strike_intensity_log    DOUBLE NOT NULL,
        attack_any              BOOLEAN NOT NULL,
        uae_asset_attack        BOOLEAN NOT NULL,
        origin                  VARCHAR,
        observation_status      VARCHAR NOT NULL,
        count_basis             VARCHAR,
        external_threat_alert   BOOLEAN NOT NULL,
        source_url              VARCHAR,
        source_url_2            VARCHAR,
        source_url_3            VARCHAR,
        notes                   VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS wam_military_strike_monthly (
        period                   DATE PRIMARY KEY,
        observation_days         BIGINT NOT NULL,
        ballistic_missiles       BIGINT NOT NULL,
        cruise_missiles          BIGINT NOT NULL,
        uavs                     BIGINT NOT NULL,
        unclassified_missiles   BIGINT NOT NULL,
        strike_intensity_log     DOUBLE NOT NULL,
        strike_intensity_index   DOUBLE NOT NULL,
        attack_days              BIGINT NOT NULL,
        asset_attack_days        BIGINT NOT NULL,
        external_threat_alert_days BIGINT NOT NULL
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

    migrate_detail_schema(con)
    for statement in _BASE_DDL:
        con.execute(statement)
    # The WAM monthly table was introduced before the partial-month audit
    # column.  Keep existing local databases upgradeable without rebuilding
    # the full DuckDB file.
    if _object_exists(con, "main", "wam_military_strike_monthly"):
        con.execute(
            "ALTER TABLE wam_military_strike_monthly "
            "ADD COLUMN IF NOT EXISTS observation_days BIGINT DEFAULT 0"
        )
        con.execute(
            "ALTER TABLE wam_military_strike_monthly "
            "ADD COLUMN IF NOT EXISTS strike_intensity_index DOUBLE DEFAULT 0"
        )
    _rewrite_detail_metadata_names(con)
    create_detail_compatibility_views(con)


def _base_table_exists(con, schema: str, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = ? AND table_name = ? AND table_type = 'BASE TABLE'",
        [schema, table],
    ).fetchone()
    return row is not None


def _object_exists(con, schema: str, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = ? AND table_name = ?",
        [schema, table],
    ).fetchone()
    return row is not None


def migrate_detail_schema(con) -> None:
    """Move legacy detail tables into ``detail`` without losing rows.

    Existing releases created the fine-grained tables in ``main`` and
    ``dld.transactions``.  The migration is idempotent.  If both the legacy
    table and its target already exist with rows, it aborts instead of guessing
    which copy is authoritative.
    """

    con.execute("CREATE SCHEMA IF NOT EXISTS detail")
    con.execute("CREATE SCHEMA IF NOT EXISTS dld")
    for schema, old_name, new_name in _DETAIL_MIGRATIONS:
        old_exists = _base_table_exists(con, schema, old_name)
        target_exists = _object_exists(con, "detail", new_name)
        if not old_exists:
            continue
        if target_exists:
            old_count = con.execute(
                f'SELECT count(*) FROM "{schema}"."{old_name}"'
            ).fetchone()[0]
            target_count = con.execute(
                f'SELECT count(*) FROM detail."{new_name}"'
            ).fetchone()[0]
            if old_count:
                raise RuntimeError(
                    f"detail 迁移冲突：{schema}.{old_name} 与 detail.{new_name} "
                    f"同时存在（{old_count}/{target_count} 行），拒绝覆盖"
                )
            con.execute(f'DROP TABLE "{schema}"."{old_name}"')
            continue
        if schema == "dld":
            for view in (
                "land_transactions",
                "transaction_year_summary",
                "transaction_date_quality_issues",
            ):
                con.execute(f"DROP VIEW IF EXISTS dld.{view}")
        con.execute(
            f'CREATE TABLE detail."{new_name}" AS '
            f'SELECT * FROM "{schema}"."{old_name}"'
        )
        primary_key = _DETAIL_PRIMARY_KEYS.get(new_name)
        if primary_key and all(
            con.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'detail' AND table_name = ? "
                "AND column_name = ?",
                [new_name, column.strip()],
            ).fetchone()
            for column in primary_key.split(",")
        ):
            con.execute(
                f'ALTER TABLE detail."{new_name}" '
                f'ADD PRIMARY KEY ({primary_key})'
            )
        con.execute(f'DROP TABLE "{schema}"."{old_name}"')


def _rewrite_detail_metadata_names(con) -> None:
    """Keep column metadata keyed to physical detail-table names."""

    if not _object_exists(con, "main", "meta_column_dictionary"):
        return
    for legacy, physical in DETAIL_TABLE_ALIASES.items():
        con.execute(
            "UPDATE main.meta_column_dictionary SET object_name = ? "
            "WHERE object_name = ?",
            [physical, legacy],
        )


def create_detail_compatibility_views(con) -> None:
    """Expose legacy names as read-only views after detail migration."""

    for legacy, physical in DETAIL_TABLE_ALIASES.items():
        if "." in legacy:
            schema, view_name = legacy.split(".", 1)
        else:
            schema, view_name = "main", legacy
        physical_schema, physical_name = physical.split(".", 1)
        if not _object_exists(con, physical_schema, physical_name):
            continue
        if schema == "dld":
            con.execute(
                f'CREATE OR REPLACE VIEW dld."{view_name}" AS '
                f'SELECT * FROM "{physical_schema}"."{physical_name}"'
            )
        else:
            con.execute(
                f'CREATE OR REPLACE VIEW main."{view_name}" AS '
                f'SELECT * FROM "{physical_schema}"."{physical_name}"'
            )


def canonical_table_name(name: str) -> str:
    """Return the writable physical name for a logical table name."""

    if name in DETAIL_TABLE_ALIASES:
        return DETAIL_TABLE_ALIASES[name]
    if name.startswith("main.") and name[5:] in DETAIL_TABLE_ALIASES:
        return DETAIL_TABLE_ALIASES[name[5:]]
    return name


def table_exists(con, name: str) -> bool:
    """Return whether `
ame`` (optionally schema-qualified) exists."""

    name = canonical_table_name(name)
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

    name = canonical_table_name(name)
    if not table_exists(con, name):
        con.execute(ddl)


def replace(con, table: str, rows: Iterable[dict[str, Any]]) -> int:
    """Replace all rows of ``table`` inside one transaction.

    The caller should wrap the call in ``con.begin()`` when several tables
    form one atomic refresh.  Returns the inserted row count.
    """

    table = canonical_table_name(table)
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
