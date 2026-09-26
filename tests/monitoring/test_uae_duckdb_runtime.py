from __future__ import annotations

import pandas as pd

from htfa.monitoring.uae.government_finance import credit
from htfa.monitoring.uae.government_finance import ded
from htfa.monitoring.uae.transport import data as transport_data


def test_foreign_inflow_duckdb_loader_derives_nonresident_deposits(monkeypatch) -> None:
    dates = pd.to_datetime(["2026-05-31", "2026-06-30"])
    raw = pd.DataFrame(
        {
            credit.FOREIGN_LIABILITIES_DISPLAY: [10.0, 11.0],
            credit.FOREIGN_CURRENCIES_DISPLAY: [20.0, 21.0],
            credit.NONRESIDENT_CORPORATE_DISPLAY: [30.0, 31.0],
            credit.NONRESIDENT_INDIVIDUALS_DISPLAY: [40.0, 41.0],
            credit.NONRESIDENT_GOVERNMENT_DISPLAY: [50.0, 51.0],
        },
        index=dates,
    )
    monkeypatch.setattr(credit, "read_long_indicators", lambda **_kwargs: raw)

    result = credit.load_foreign_inflow_from_duckdb()

    assert result.source_name == "uae.duckdb"
    assert result.values[credit.NONRESIDENT_DEPOSITS].tolist() == [120.0, 123.0]
    assert result.metadata[credit.NONRESIDENT_DEPOSITS].sheet_name == "cbuae_monthly"


def test_ded_duckdb_loader_filters_future_snapshot_months(monkeypatch) -> None:
    raw = pd.DataFrame(
        {
            ded.ENTERPRISES_DISPLAY: [10.0, 11.0, 12.0],
            ded.LICENCES_DISPLAY: [20.0, 21.0, 22.0],
        },
        index=pd.to_datetime(["1906-01-01", "2026-06-01", "2027-02-01"]),
    )
    monkeypatch.setattr(ded, "read_long_indicators", lambda **_kwargs: raw)

    result = ded.load_ded_from_duckdb(through="2026-06")

    assert result.values.index.tolist() == [pd.Timestamp("1906-01-01"), pd.Timestamp("2026-06-01")]
    assert result.values[ded.ENTERPRISES_DISPLAY].tolist() == [10.0, 11.0]


def test_transport_duckdb_loader_reads_air_tables_and_keeps_ports_on_optional_failure(monkeypatch) -> None:
    def read_query(query, *_args, **_kwargs):
        if "detail.portwatch_uae_daily" in query:
            return pd.DataFrame(
                {
                    "period": ["2026-06-30"],
                    "import_total": [100.0],
                    "export_total": [120.0],
                    "tanker_import": [40.0],
                    "tanker_export": [50.0],
                }
            )
        return pd.DataFrame(
            {
                "period": ["2026-06-30"],
                "total_calls": [15.0],
                "tanker_calls": [6.0],
            }
        )

    def read_long_indicators(**kwargs):
        table = kwargs["table"]
        if table == "dot_t100_monthly":
            raise RuntimeError("DOT fixture unavailable")
        targets = kwargs["targets"]
        return pd.DataFrame(
            {column: [index + 1.0] for index, column in enumerate(targets)},
            index=pd.to_datetime(["2026-06-30"]),
        )

    monkeypatch.setattr(transport_data, "read_query", read_query)
    monkeypatch.setattr(transport_data, "read_long_indicators", read_long_indicators)

    result = transport_data.load_transport_from_duckdb()

    assert transport_data.UAE_PORT_IMPORT_TOTAL in result.values
    assert transport_data.DUBAI_AIR_IMPORT_AWBS in result.monthly_values
    assert transport_data.US_UAE_AIR_PASSENGERS not in result.monthly_values
    assert transport_data.DOTT100_ERROR_KEY in result.load_errors
    assert transport_data.DUBAI_CUSTOMS_AIR_AWB_ERROR_KEY not in result.load_errors
