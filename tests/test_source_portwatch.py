"""PortWatch 日度转月度的完整自然月边界测试。"""

from datetime import date

import duckdb

from htfa.jobs.uae_data import source_portwatch as source


def test_monthly_aggregation_ignores_partial_latest_month() -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE SCHEMA detail")
        con.execute(source.UAE_TABLE_DDL)
        con.execute(source.CHOKEPOINT_TABLE_DDL)
        uae_rows = [
            (
                date(2026, 7, 31),
                "p1",
                "Port 1",
                "United Arab Emirates",
                "ARE",
                *([10] * 21),
            ),
            (
                date(2026, 8, 10),
                "p1",
                "Port 1",
                "United Arab Emirates",
                "ARE",
                *([20] * 21),
            ),
        ]
        choke_rows = [
            (
                date(2026, 7, 31),
                "chokepoint6",
                "Hormuz",
                *([5] * 14),
            ),
            (
                date(2026, 8, 9),
                "chokepoint6",
                "Hormuz",
                *([6] * 14),
            ),
        ]
        con.executemany(
            "INSERT INTO detail.portwatch_uae_daily VALUES ("
            + ",".join("?" for _ in uae_rows[0])
            + ")",
            uae_rows,
        )
        con.executemany(
            "INSERT INTO detail.portwatch_chokepoint_daily VALUES ("
            + ",".join("?" for _ in choke_rows[0])
            + ")",
            choke_rows,
        )

        observations = source._monthly_observations(con)

        assert [item.period for item in observations] == ["2026-07"]
        assert observations[0].values[:3] == (10, 10, 10)
        assert observations[0].values[-4:] == (5, 5, 5, 5)
    finally:
        con.close()
