"""Annual observations retain frequency, source units and dimensional identity."""

import csv
import io
from datetime import date

import duckdb
import pytest

from htfa.jobs.uae_data import db, source_fcsc_annual as source


def _csv(dataset, *, years=(2010, 2011), frequency="A"):
    foreign = dataset.startswith("DF_FI")
    record = {
        "DATAFLOW": f"FCSA:{dataset}(1.0)", "REF_AREA": "AE", "FREQ": frequency,
        "UNIT_MEASURE": "AED" if foreign else "MILAED", "UNIT_MULT": "",
        "MEASURE": "FDI" if foreign else "CAPITAL", "EXPEND": "EXPEND4",
        "COUNTRY": "826" if dataset == "DF_FI_COUNTRY" else "_T",
        "OBS_VALUE": "1000000000" if foreign else "1000", "TIME_PERIOD": "2010",
    }
    record["ECON_ACTIV" if foreign else "ISIC"] = "_T" if dataset == "DF_FI_COUNTRY" else "C"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(record))
    writer.writeheader()
    for year in years:
        writer.writerow({**record, "TIME_PERIOD": str(year)})
    return output.getvalue().encode()


def test_annual_parser_rejects_frequency_and_duplicate_dimensions():
    with pytest.raises(ValueError, match="频率"):
        source.parse_csv(_csv("DF_NA_FIX_CUR", frequency="Q"), "DF_NA_FIX_CUR")
    with pytest.raises(ValueError, match="重复"):
        source.parse_csv(_csv("DF_NA_FIX_CUR", years=(2010, 2010)), "DF_NA_FIX_CUR")


def test_update_normalizes_only_after_database_load_and_rejects_coverage_regression(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "DATA_DIR", tmp_path)
    raw = tmp_path / "raw" / "fcsc_annual"
    raw.mkdir(parents=True)
    for dataset in source.DATASETS:
        (raw / f"{dataset}.csv").write_bytes(_csv(dataset))
    with duckdb.connect() as con:
        db.init_schema(con)
        assert source.update(con, skip_download=True)["rows"] == 12
        specs = source.sheet_specs(con)
        assert len(specs) == 5
        assert all(value == 1 for spec in specs for _, values in spec["rows"] for value in values.values())
        assert con.execute(f"SELECT value FROM {source.TABLE} WHERE dataset='DF_FI_TYPE' LIMIT 1").fetchone()[0] == 1e9
        (raw / "DF_NA_FIX_CUR.csv").write_bytes(_csv("DF_NA_FIX_CUR", years=(2011,)))
        with pytest.raises(ValueError, match="覆盖回退"):
            source.update(con, skip_download=True)
        assert con.execute(f"SELECT min(period),count(*) FROM {source.TABLE}").fetchone() == (date(2010, 12, 31), 12)
