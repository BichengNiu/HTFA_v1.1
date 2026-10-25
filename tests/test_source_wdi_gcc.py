"""Verify fixed-country GCC arithmetic averages and World Bank response validation."""

import json

import duckdb
import pandas as pd
import pytest

from htfa.jobs.uae_data import db, source_wdi_gcc as source
from htfa.monitoring.uae.annual_comparison_contracts import GDP_SHEET, GCC_NAME, LEVEL_SUFFIX, GROWTH_SUFFIX


def _payload(indicator):
    rows = []
    for i, country in enumerate(source.COUNTRIES, 1):
        for year in (2010, 2011):
            value = i * 1e9 if indicator == source.GDP_LEVEL else i
            if country == "KWT" and year == 2011:
                value = None
            rows.append({"countryiso3code": country, "indicator": {"id": indicator},
                         "date": str(year), "value": value, "decimal": 0})
    return [{"page": 1, "pages": 1, "sourceid": "2", "total": len(rows), "lastupdated": "2026-10-08"}, rows]


def test_wdi_parser_rejects_incomplete_pagination_and_wrong_indicator():
    payload = _payload(source.GDP_LEVEL)
    payload[0]["pages"] = 2
    with pytest.raises(ValueError, match="分页"):
        source.parse_payload(json.dumps(payload), source.GDP_LEVEL)
    payload[0]["pages"] = 1
    payload[1][0]["indicator"]["id"] = source.GDP_GROWTH
    with pytest.raises(ValueError, match="指标身份"):
        source.parse_payload(json.dumps(payload), source.GDP_LEVEL)


def test_six_country_mean_is_unweighted_and_missing_country_never_becomes_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "DATA_DIR", tmp_path)
    raw = tmp_path / "raw" / "wdi_gcc"
    raw.mkdir(parents=True)
    for indicator in source.INDICATORS:
        (raw / f"{indicator}.json").write_text(json.dumps(_payload(indicator)))
    with duckdb.connect() as con:
        db.init_schema(con)
        assert source.update(con, skip_download=True)["rows"] == 60
        frames = source.comparison_frames(con)
        gdp = frames[GDP_SHEET]
        assert gdp.loc["2010-12-31", GCC_NAME + LEVEL_SUFFIX] == 3.5
        assert gdp.loc["2010-12-31", GCC_NAME + GROWTH_SUFFIX] == 3.5
        assert gdp.loc["2010-12-31", "阿联酋" + LEVEL_SUFFIX] == 1
        assert pd.isna(gdp.loc["2011-12-31", GCC_NAME + LEVEL_SUFFIX])
        assert pd.isna(gdp.loc["2011-12-31", GCC_NAME + GROWTH_SUFFIX])
        for sheet, _ in source.SECTOR_INDICATORS.values():
            assert frames[sheet].loc["2010-12-31", GCC_NAME] == 3.5
            assert pd.isna(frames[sheet].loc["2011-12-31", GCC_NAME])
        specs = source.sheet_specs(con)
        assert len(specs) == 4
        assert len(specs[0]["indicators"]) == 14
        assert {m["unit"] for m in specs[0]["metadata"].values()} == {"十亿美元", "%"}
        assert con.execute(f"SELECT value FROM {source.TABLE} WHERE country='ARE' AND indicator=? LIMIT 1", [source.GDP_LEVEL]).fetchone()[0] == 1e9
