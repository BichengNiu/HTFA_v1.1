from __future__ import annotations

import duckdb


def test_oil_market_data_reads_native_duckdb_tables(monkeypatch, tmp_path) -> None:
    from htfa.monitoring.uae.oil import data

    database_path = tmp_path / "uae.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            "CREATE TABLE eia_brent_spot_daily (period DATE, price_usd_bbl DOUBLE)"
        )
        connection.execute(
            "INSERT INTO eia_brent_spot_daily VALUES ('2026-08-01', 72.5)"
        )
        connection.execute(
            "CREATE TABLE opec_crude_production_monthly "
            "(period DATE, production_bpd DOUBLE)"
        )
        connection.execute(
            "INSERT INTO opec_crude_production_monthly VALUES ('2026-08-01', 3200000)"
        )
        connection.execute(
            "CREATE TABLE imf_dubai_crude_monthly (period DATE, price_usd_bbl DOUBLE)"
        )
        connection.execute(
            "INSERT INTO imf_dubai_crude_monthly VALUES ('2026-08-01', 70.0)"
        )
        connection.execute(
            "CREATE TABLE baker_hughes_monthly (period DATE, oil_rigs BIGINT)"
        )
        connection.execute(
            "INSERT INTO baker_hughes_monthly VALUES ('2026-08-01', 45)"
        )

    monkeypatch.setattr(data, "read_query", lambda sql: _read(sql, database_path))
    result = data.load_oil_market_from_duckdb()

    assert result.source_name == "uae.duckdb"
    assert result.prices.loc["2026-08-01", "布伦特现货"] == 72.5
    assert result.production.iloc[0] == 3200000
    assert result.rig_count is not None and result.rig_count.iloc[0] == 45


def _read(sql: str, database_path):
    from htfa.monitoring.uae.duckdb_reader import read_query

    return read_query(sql, database_path=database_path)


def test_real_estate_data_reads_dld_monthly_aggregate(monkeypatch, tmp_path) -> None:
    from htfa.monitoring.uae.real_estate import data

    database_path = tmp_path / "uae.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            "CREATE TABLE dld_sales_monthly "
            "(period DATE, indicator VARCHAR, count BIGINT, value_aed DOUBLE)"
        )
        connection.executemany(
            "INSERT INTO dld_sales_monthly VALUES (?, ?, ?, ?)",
            [
                ("2026-08-31", "residential_offplan_sales", 10, 1_000_000),
                ("2026-08-31", "residential_ready_sales", 20, 2_000_000),
                ("2026-08-31", "commercial_offplan_sales", 3, 500_000),
                ("2026-08-31", "commercial_ready_sales", 4, 800_000),
            ],
        )
    monkeypatch.setattr(data, "read_query", lambda sql: _read(sql, database_path))

    result = data.load_real_estate_from_duckdb()

    assert result.source_name == "uae.duckdb"
    assert result.values.loc["2026-08-31", "期房销售笔数"] == 13
    assert result.values.loc["2026-08-31", "现房销售金额"] == 2.8
