"""PortWatch 日度转月度的完整自然月边界测试。"""

from datetime import date
from io import BytesIO
import json
import csv

import duckdb
import pytest

from htfa.jobs.uae_data import source_portwatch as source


def test_official_transient_error_retries_the_same_query(monkeypatch):
    class Response(BytesIO):
        status = 200

    urls = []
    def read(request, **kwargs):
        urls.append(request.full_url)
        payload = {"error": {"code": 400, "message": "Invalid URL"}} if len(urls) == 1 else {"count": 2853}
        return Response(json.dumps(payload).encode())
    monkeypatch.setattr(source.urllib.request, "urlopen", read)
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    assert source._arcgis_json("https://example.com/query", {"where": "portid='port5'"}) == {"count": 2853}
    assert "f=json" in urls[0] and "f=pjson" in urls[1]


@pytest.mark.parametrize("status,body,headers,error", [
    (202, b"", {"x-amzn-waf-action": "challenge"}, RuntimeError),
    (200, b"", {}, OSError),
    (200, b"short", {"Content-Length": "100"}, OSError),
    (200, b"<html>challenge</html>", {"Content-Type": "text/html"}, ValueError),
])
def test_invalid_download_preserves_cache(
    monkeypatch, tmp_path, status, body, headers, error
):
    class Response(BytesIO):
        pass

    response = Response(body)
    response.status = status
    response.headers = headers
    monkeypatch.setattr(source.urllib.request, "urlopen", lambda *a, **k: response)
    target = tmp_path / "ports.csv"
    target.write_bytes(b"previous validated CSV")
    with pytest.raises(error):
        source._download_to("https://example.com/ports.csv", target)
    assert target.read_bytes() == b"previous validated CSV"
    assert not target.with_suffix(".csv.tmp").exists()


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


def _official_page_rows():
    return [
        {
            "date": f"2026-09-{i:02d}", "portid": "port5",
            "portname": "Abu Dhabi", "country": "United Arab Emirates",
            "ISO3": "ARE", "ObjectId": i,
            **{name: i for name in source.UAE_VALUE_COLUMNS},
        }
        for i in range(1, 4)
    ]


def _official_server(monkeypatch, fault=None):
    rows = _official_page_rows()
    if fault == "duplicate_key":
        rows[-1]["date"] = rows[0]["date"]
    if fault == "repeated_oid":
        rows[-1]["ObjectId"] = 1
    if fault == "unexpected_port":
        rows[-1]["portid"] = "port13"
    count_calls = []
    offsets = []

    def read(service, params):
        if not params:
            return {"maxRecordCount": 2, "fields": [
                {"name": name, "type": "esriFieldTypeOID" if name == "ObjectId" else "value"}
                for name in (*source.UAE_REQUIRED_COLUMNS, "ObjectId")
            ]}
        if params.get("returnCountOnly"):
            count_calls.append(1)
            return {"count": 4 if fault == "changed_count" and len(count_calls) > 1 else 3}
        offset = params["resultOffset"]
        offsets.append(offset)
        page = rows[offset:offset + 2]
        if fault == "empty_page" and offset:
            page = []
        return {"features": [{"attributes": row} for row in page],
                "exceededTransferLimit": offset == 0}

    monkeypatch.setattr(source, "_arcgis_json", read)
    return offsets


def test_official_pagination_validates_and_writes_complete_csv(monkeypatch, tmp_path):
    offsets = _official_server(monkeypatch)
    target = tmp_path / "uae.csv"
    source._download_arcgis_csv("https://example.com", target, source.UAE_REQUIRED_COLUMNS, "portid='port5'")
    rows = source.parse_portwatch_csv(target, source.UAE_REQUIRED_COLUMNS,
                                    source.UAE_VALUE_COLUMNS, string_columns=source.UAE_STRING_COLUMNS)
    assert offsets == [0, 2]
    assert len(rows) == 3
    assert rows[-1]["date"] == date(2026, 9, 3)


def test_official_csv_loads_with_published_uppercase_iso3(monkeypatch, tmp_path):
    _official_server(monkeypatch)
    uae_file, choke_file = tmp_path / "uae.csv", tmp_path / "choke.csv"
    source._download_arcgis_csv("https://example.com", uae_file, source.UAE_REQUIRED_COLUMNS, "portid='port5'")
    with choke_file.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=source.CHOKEPOINT_REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerow({"date": "2026-09-01", "portid": "chokepoint6", "portname": "Hormuz",
                         **{name: 1 for name in source.CHOKEPOINT_VALUE_COLUMNS}})
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    monkeypatch.setattr(source, "UAE_FILE", uae_file)
    monkeypatch.setattr(source, "CHOKEPOINT_FILE", choke_file)
    with source.db.connect(":memory:") as con:
        source.db.init_schema(con)
        assert source.update(con, skip_download=True)["status"] == "ok"
        assert con.execute("SELECT DISTINCT iso3 FROM detail.portwatch_uae_daily").fetchall() == [("ARE",)]


@pytest.mark.parametrize("fault", [
    "empty_page", "repeated_oid", "duplicate_key", "changed_count", "unexpected_port"
])
def test_invalid_official_pages_preserve_previous_cache(monkeypatch, tmp_path, fault):
    _official_server(monkeypatch, fault)
    target = tmp_path / "uae.csv"
    target.write_bytes(b"validated previous data")
    with pytest.raises(ValueError):
        source._download_arcgis_csv("https://example.com", target, source.UAE_REQUIRED_COLUMNS, "portid='port5'")
    assert target.read_bytes() == b"validated previous data"
    assert not target.with_suffix(".csv.tmp").exists()


def test_update_rejects_lost_historical_keys_before_replacing_tables(monkeypatch, tmp_path):
    uae_file, choke_file = tmp_path / "uae.csv", tmp_path / "choke.csv"
    for path in [uae_file, choke_file]:
        path.touch()
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    monkeypatch.setattr(source, "UAE_FILE", uae_file)
    monkeypatch.setattr(source, "CHOKEPOINT_FILE", choke_file)
    uae = {
        "date": date(2026, 9, 30), "portid": "port5", "portname": "Abu Dhabi",
        "country": "United Arab Emirates", "iso3": "ARE",
        **{name: 1 for name in source.UAE_VALUE_COLUMNS},
    }
    choke = {
        "date": date(2026, 9, 30), "portid": "chokepoint6", "portname": "Hormuz",
        **{name: 1 for name in source.CHOKEPOINT_VALUE_COLUMNS},
    }
    monkeypatch.setattr(source, "parse_portwatch_csv", lambda path, *a, **k:
                        [uae.copy()] if path == uae_file else [choke.copy()])
    with source.db.connect(":memory:") as con:
        source.db.init_schema(con)
        source.update(con, skip_download=True)
        uae["date"] = date(2026, 10, 1)
        with pytest.raises(ValueError, match="remove historical keys"):
            source.update(con, skip_download=True)
        assert con.execute("SELECT date FROM detail.portwatch_uae_daily").fetchall() == [
            (date(2026, 9, 30),)
        ]
