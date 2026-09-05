"""Regression tests for the RTA raw-to-aggregate pipeline."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb

from htfa.jobs.uae_data import source_rta  # noqa: E402
from htfa.jobs.uae_data import db  # noqa: E402


def _csv(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def test_rta_schema_contains_aggregates_only() -> None:
    assert set(source_rta._TABLE_DDL) == {
        "rta_transport_monthly",
        "rta_transport_daily",
    }
    legacy_names = (
        "rta_bus_trips_route_monthly",
        "rta_marine_trips_station_monthly",
        "rta_taxi_trips_monthly",
        "rta_bus_speed_daily_detail",
        "rta_marine_ridership_raw",
        "rta_bus_ridership_raw",
    )
    assert source_rta._LEGACY_TABLES == legacy_names
    assert all(
        not any(name in statement for name in legacy_names)
        for statement in db._BASE_DDL
    )


def test_monthly_aggregators_read_raw_csv_without_detail_tables(tmp_path: Path) -> None:
    bus = _csv(
        tmp_path,
        "bus.csv",
        "month,route,trips,year,load_timestamp\n"
        "Jan,R1,10,2025,2025-02-01\n"
        "Jan,R2,15,2025,2025-02-01\n",
    )
    marine = _csv(
        tmp_path,
        "marine.csv",
        "mode,station,month,passengers,year,load_timestamp\n"
        "Metro,S1,Jan,20,2025,2025-02-01\n"
        "Metro,S2,Jan,5,2025,2025-02-01\n",
    )
    taxi = _csv(
        tmp_path,
        "taxi.csv",
        "carrier,fleet_size,report_date,trips,load_timestamp\n"
        "A,10,2025-01-31,100,2025-02-01\n"
        "A,12,2025-01-31,50,2025-02-01\n"
        "B,4,2025-01-31,25,2025-02-01\n",
    )

    period = date(2025, 1, 31)
    assert source_rta._aggregate_bus_route_monthly([bus]) == {period: 25}
    assert source_rta._aggregate_marine_station_monthly([marine]) == {period: 25.0}
    assert source_rta._aggregate_taxi_monthly([taxi]) == ({period: 175}, {period: 16})


def test_daily_aggregators_and_rebuild_preserve_aggregate_contract(tmp_path: Path) -> None:
    speed = _csv(
        tmp_path,
        "speed.csv",
        "average_speed,date,route_direction,route_name,service_type,time_period,load_timestamp\n"
        "10,2025-01-01,N,R1,Bus,AM,2025-01-02\n"
        "20,2025-01-01,S,R2,Bus,PM,2025-01-02\n",
    )
    marine = _csv(
        tmp_path,
        "marine_ridership.csv",
        "line_name,location,txn_date,txn_time,txn_type,zone,load_timestamp\n"
        "L1,S1,2025-01-01,08:00,IN,1,2025-01-02\n"
        "L1,S2,2025-01-01,08:01,OUT,1,2025-01-02\n",
    )
    con = duckdb.connect(":memory:")
    try:
        speed_values = source_rta._aggregate_bus_speed(con, [speed])
        marine_values = source_rta._aggregate_marine_daily(con, [marine])
        assert speed_values == {date(2025, 1, 1): 15.0}
        assert marine_values == {date(2025, 1, 1): 2}

        for ddl in source_rta._TABLE_DDL.values():
            con.execute(ddl)
        source_rta._rebuild_aggregates(
            con,
            monthly={"月度指标": {date(2025, 1, 31): 25}},
            daily={"日度指标": {date(2025, 1, 1): 15.0}},
        )
        assert con.execute("SELECT count(*) FROM rta_transport_monthly").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM rta_transport_daily").fetchone()[0] == 1
    finally:
        con.close()
