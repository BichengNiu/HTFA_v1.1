"""PortWatch 日度转月度的完整自然月边界测试。"""

from datetime import date
from io import BytesIO
import json
import csv
from urllib.parse import parse_qs, urlsplit

import duckdb
import pytest

from htfa.jobs.uae_data import source_portwatch as source


def _hub_payload(service, layer):
    item_id = source.HUB_DATASETS[service]
    return {"data": {"id": item_id + "_0", "attributes": {
        "access": "public", "owner": "IMF-portwatch_imf_dataviz", "url": service,
        "errors": [], "layer": {
            "id": 0, "serviceItemId": item_id,
            "editingInfo": {"dataLastEditDate": 100}, **layer,
        },
    }}}


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
    queries = [parse_qs(urlsplit(url).query) for url in urls]
    assert queries[0]["f"] == queries[1]["f"] == ["json"]
    assert queries[0]["where"] == ["portid='port5'"]
    assert queries[1]["where"] == queries[0]["where"]
    assert queries[0]["cacheHint"] == queries[1]["cacheHint"] == ["false"]
    assert urls[0] == urls[1]


def test_object_id_batches_use_post_to_avoid_url_length_limit(monkeypatch):
    class Response(BytesIO):
        status = 200

    requests = []
    def read(request, **kwargs):
        requests.append(request)
        return Response(b'{"features": []}')
    monkeypatch.setattr(source.urllib.request, "urlopen", read)
    ids = ",".join(str(i) for i in range(500))
    source._arcgis_json("https://example.com/query", {"objectIds": ids})
    request = requests[0]
    assert request.get_method() == "POST"
    assert len(request.full_url) < 200
    assert parse_qs(request.data.decode())["objectIds"] == [ids]


def test_query_retry_can_use_post_with_identical_filter(monkeypatch):
    class Response(BytesIO):
        status = 200

    requests = []

    def read(request, **kwargs):
        requests.append(request)
        payload = (
            {"count": 365} if request.get_method() == "POST"
            else {"error": {"code": 400, "message": "Invalid URL"}}
        )
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr(source.urllib.request, "urlopen", read)
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    where = "year=2019 AND portid='chokepoint2'"
    assert source._arcgis_json(
        "https://example.com/query", {"where": where, "returnCountOnly": "true"}
    ) == {"count": 365}
    assert [r.get_method() for r in requests] == ["GET", "GET", "POST"]
    params = parse_qs(requests[-1].data.decode())
    assert params["f"] == ["json"]
    assert params["where"] == [where]
    assert params["returnCountOnly"] == ["true"]


def test_hub_json_does_not_receive_feature_service_format_parameters(monkeypatch):
    class Response(BytesIO):
        status = 200

    requests = []
    def read(request, **kwargs):
        requests.append(request)
        return Response(b'{"data": {}}')
    monkeypatch.setattr(source.urllib.request, "urlopen", read)
    url = source.HUB_DATASET_API + "item_0"
    source._arcgis_json(url, {})
    assert requests[0].full_url == url


@pytest.mark.parametrize("fault", [None, "owner", "url", "layer"])
def test_hub_metadata_verifies_publisher_service_and_layer(monkeypatch, fault):
    calls = []
    def read(service, params):
        calls.append((service, params))
        payload = _hub_payload(source.PORTS_SERVICE, {})
        attrs = payload["data"]["attributes"]
        if fault == "layer":
            attrs["layer"]["id"] = 1
        elif fault:
            attrs[fault] = "different publisher or URL"
        return payload
    monkeypatch.setattr(source, "_arcgis_json", read)
    if fault is None:
        assert source._arcgis_metadata(source.PORTS_SERVICE)["id"] == 0
    else:
        with pytest.raises(ValueError, match="identity or source version"):
            source._arcgis_metadata(source.PORTS_SERVICE)
    assert calls == [(source.HUB_DATASET_API + source.HUB_DATASETS[source.PORTS_SERVICE] + "_0", {})]


@pytest.mark.parametrize("code,message,expected_attempts", [
    (400, "Invalid URL", source._ARCGIS_ATTEMPTS),
    (499, "Token Required", 1),
])
def test_official_errors_have_bounded_retries_and_reject_authentication(
    monkeypatch, code, message, expected_attempts
):
    class Response(BytesIO):
        status = 200

    calls = []
    def read(request, **kwargs):
        calls.append(request.full_url)
        return Response(json.dumps({"error": {"code": code, "message": message}}).encode())
    monkeypatch.setattr(source.urllib.request, "urlopen", read)
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match=message):
        source._arcgis_json("https://example.com/query", {})
    assert len(calls) == expected_attempts
    assert len(set(calls)) <= 2


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
            "ISO3": "ARE", "ObjectId": i, "year": 2026,
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
    inventory_calls = []

    def read(service, params):
        if not params:
            metadata = {"id": 0, "maxRecordCount": 2, "fields": [
                {"name": name, "type": "esriFieldTypeOID" if name == "ObjectId" else "value"}
                for name in (*source.UAE_REQUIRED_COLUMNS, "ObjectId", "year")
            ]}
            return _hub_payload(source.PORTS_SERVICE, metadata)
        if params.get("returnIdsOnly"):
            assert "returnGeometry" not in params
            inventory_calls.append(1)
            selected = rows
            if "year=" in params["where"]:
                year = int(params["where"].split(" AND ", 1)[0].split("=")[1])
                selected = [row for row in rows if row["year"] == year]
            ids = [row["ObjectId"] for row in selected]
            if fault == "changed_ids" and len(inventory_calls) > 1:
                ids[-1] = 4
            return {"objectIdFieldName": "ObjectId", "objectIds": ids}
        if params.get("returnCountOnly"):
            assert params["returnGeometry"] == "false"
            count_calls.append(1)
            return {"count": 4 if fault == "changed_count" and len(count_calls) > 1 else 3}
        if "objectIds" not in params:
            assert params["where"].startswith("year=")
            year = int(params["where"].split(" AND ", 1)[0].split("=")[1])
            page = [row for row in rows if row["year"] == year]
            if fault == "missing_year_row":
                page = page[:-1]
            return {"features": [{"attributes": row} for row in reversed(page)]}
        assert "resultOffset" not in params
        batch = [int(value) for value in params["objectIds"].split(",")]
        offsets.append(batch)
        page = [row for row in rows if row["ObjectId"] in batch]
        if fault == "wrong_ids":
            page = rows[:len(batch)]
        if fault == "empty_page" and batch[0] > 1:
            page = []
        return {"features": [{"attributes": row} for row in reversed(page)]}

    monkeypatch.setattr(source, "_arcgis_json", read)
    return offsets


def test_official_pagination_validates_and_writes_complete_csv(monkeypatch, tmp_path):
    offsets = _official_server(monkeypatch)
    target = tmp_path / "uae.csv"
    source._download_arcgis_csv(source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "portid='port5'")
    rows = source.parse_portwatch_csv(target, source.UAE_REQUIRED_COLUMNS,
                                    source.UAE_VALUE_COLUMNS, string_columns=source.UAE_STRING_COLUMNS)
    assert offsets == [[1, 2], [3]]
    assert len(rows) == 3
    assert rows[-1]["date"] == date(2026, 9, 3)


def test_whole_table_batches_preserve_order_under_parallel_fetch(monkeypatch, tmp_path):
    batches = _official_server(monkeypatch)
    target = tmp_path / "all.csv"
    source._download_arcgis_csv(source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "1=1")
    rows = source.parse_portwatch_csv(
        target, source.UAE_REQUIRED_COLUMNS, source.UAE_VALUE_COLUMNS,
        string_columns=source.UAE_STRING_COLUMNS,
    )
    assert sorted(batches) == [[1, 2], [3]]
    assert [row["date"].day for row in rows] == [1, 2, 3]


@pytest.mark.parametrize("fault", [None, "missing_year_row"])
def test_port_year_queries_reconcile_with_the_unfiltered_id_inventory(monkeypatch, tmp_path, fault):
    _official_server(monkeypatch, fault)
    metadata = source._arcgis_metadata(source.PORTS_SERVICE)
    metadata["maxRecordCount"] = 1000
    target = tmp_path / "years.csv"
    target.write_bytes(b"previous complete cache")
    if fault:
        with pytest.raises(ValueError, match="rows or object IDs changed"):
            source._download_arcgis_csv(
                source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "1=1",
                metadata=metadata, portids=["port5"],
            )
        assert target.read_bytes() == b"previous complete cache"
        cached = json.loads((tmp_path / "years_years" / "port5_2026.json").read_text())
        assert cached["requires_refresh"] is True
        _official_server(monkeypatch)
        source._download_arcgis_csv(
            source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "1=1",
            metadata=metadata, portids=["port5"], force=False,
        )
        assert not json.loads((tmp_path / "years_years" / "port5_2026.json").read_text()).get("requires_refresh")
    else:
        source._download_arcgis_csv(
            source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "1=1",
            metadata=metadata, portids=["port5"],
        )
        assert len(source.parse_portwatch_csv(
            target, source.UAE_REQUIRED_COLUMNS, source.UAE_VALUE_COLUMNS,
            string_columns=source.UAE_STRING_COLUMNS,
        )) == 3


def test_verified_year_partitions_resume_after_combined_file_is_missing(monkeypatch, tmp_path):
    _official_server(monkeypatch)
    original = source._arcgis_json
    metadata = source._arcgis_metadata(source.PORTS_SERVICE)
    metadata["maxRecordCount"] = 1000
    target = tmp_path / "years.csv"
    source._download_arcgis_csv(
        source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "1=1",
        metadata=metadata, portids=["port5"],
    )
    target.unlink()
    def read(service, params):
        assert "year=2026" not in params.get("where", ""), "verified year was downloaded again"
        return original(service, params)
    monkeypatch.setattr(source, "_arcgis_json", read)
    source._download_arcgis_csv(
        source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "1=1",
        metadata=metadata, portids=["port5"], force=False,
    )
    assert len(source.parse_portwatch_csv(
        target, source.UAE_REQUIRED_COLUMNS, source.UAE_VALUE_COLUMNS,
        string_columns=source.UAE_STRING_COLUMNS,
    )) == 3


@pytest.mark.parametrize("fault", [None, "corrupt", "version", "force"])
def test_cache_reuse_requires_same_official_version_and_hash(monkeypatch, tmp_path, fault):
    _official_server(monkeypatch)
    target = tmp_path / "cached.csv"
    metadata = source._arcgis_metadata(source.PORTS_SERVICE)
    source._download_arcgis_csv(
        source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS,
        "portid='port5'", metadata=metadata,
    )
    if fault == "corrupt":
        target.write_bytes(target.read_bytes() + b"modified")
    elif fault == "version":
        metadata["editingInfo"] = {"dataLastEditDate": 200}
    def network_required(*args, **kwargs):
        raise AssertionError("network refresh required")
    monkeypatch.setattr(source, "_arcgis_json", network_required)
    if fault:
        with pytest.raises(AssertionError, match="network refresh required"):
            source._download_arcgis_csv(
                source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS,
                "portid='port5'", metadata=metadata, force=fault == "force",
            )
    else:
        result = source._download_arcgis_csv(
            source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS,
            "portid='port5'", metadata=metadata, force=False,
        )
        assert result == "reused/verified official version"


@pytest.mark.parametrize("fault", [None, "hash", "version"])
def test_resume_inventory_cache_still_requires_live_final_reconciliation(
    monkeypatch, tmp_path, fault
):
    _official_server(monkeypatch)
    target = tmp_path / "cached.csv"
    metadata = source._arcgis_metadata(source.PORTS_SERVICE)
    source._download_arcgis_csv(
        source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "1=1",
        metadata=metadata, portids=["port5"],
    )
    target.unlink()
    inventory = target.with_suffix(".ids.json")
    saved = json.loads(inventory.read_text(encoding="utf-8"))
    if fault == "hash":
        saved["sha256"] = "invalid"
    elif fault == "version":
        saved["version"] += 1
    inventory.write_text(json.dumps(saved), encoding="utf-8")
    original = source._arcgis_json
    calls = []

    def read(service, params):
        calls.append(params)
        return original(service, params)

    monkeypatch.setattr(source, "_arcgis_json", read)
    source._download_arcgis_csv(
        source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "1=1",
        metadata=metadata, portids=["port5"], force=False,
    )
    assert sum("returnIdsOnly" in p for p in calls) == (2 if fault else 1)
    assert sum("returnCountOnly" in p for p in calls) == 2
    assert "returnIdsOnly" in calls[-1]


def test_official_csv_loads_with_published_uppercase_iso3(monkeypatch, tmp_path):
    _official_server(monkeypatch)
    uae_file, choke_file = tmp_path / "uae.csv", tmp_path / "choke.csv"
    source._download_arcgis_csv(source.PORTS_SERVICE, uae_file, source.UAE_REQUIRED_COLUMNS, "portid='port5'")
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
    "empty_page", "repeated_oid", "duplicate_key", "changed_count", "unexpected_port",
    "changed_ids", "wrong_ids",
])
def test_invalid_official_pages_preserve_previous_cache(monkeypatch, tmp_path, fault):
    _official_server(monkeypatch, fault)
    target = tmp_path / "uae.csv"
    target.write_bytes(b"validated previous data")
    with pytest.raises(ValueError):
        source._download_arcgis_csv(source.PORTS_SERVICE, target, source.UAE_REQUIRED_COLUMNS, "portid='port5'")
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


@pytest.mark.parametrize("fault", [None, "changed_vintage", "unexpected_chokepoint"])
def test_online_update_verifies_registry_and_vintage_before_publishing_caches(
    monkeypatch, tmp_path, fault
):
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    uae_file, choke_file = tmp_path / "uae.csv", tmp_path / "choke.csv"
    monkeypatch.setattr(source, "UAE_FILE", uae_file)
    monkeypatch.setattr(source, "CHOKEPOINT_FILE", choke_file)
    for path in (uae_file, choke_file):
        path.write_bytes(b"previous complete cache")
    metadata_calls = {}
    def read(service, params):
        if service == source.PORTS_REFERENCE + "/query":
            return {"features": [{"attributes": {"portid": "port5", "ISO3": "ARE"}}]}
        if service == source.CHOKEPOINT_REFERENCE + "/query":
            return {"features": [{"attributes": {"portid": "chokepoint6"}}]}
        metadata_calls[service] = metadata_calls.get(service, 0) + 1
        vintage = 200 if fault == "changed_vintage" and metadata_calls[service] > 1 else 100
        target = next(
            target for target, item_id in source.HUB_DATASETS.items()
            if service == source.HUB_DATASET_API + item_id + "_0"
        )
        return _hub_payload(target, {"editingInfo": {"dataLastEditDate": vintage}})

    filters = []
    def download(service, destination, columns, where, *, metadata, force, portids):
        filters.append(where)
        portid = "port5" if service == source.PORTS_SERVICE else "chokepoint6"
        if fault == "unexpected_chokepoint" and service == source.CHOKEPOINT_SERVICE:
            portid = "chokepoint999"
        row = {name: 1 for name in columns}
        row.update(date="2026-09-30", portid=portid, portname=portid)
        if service == source.PORTS_SERVICE:
            row.update(country="United Arab Emirates", ISO3="ARE")
        with destination.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerow(row)
        destination.with_suffix(".source.json").write_text(
            json.dumps({"editing_info": metadata["editingInfo"]}), encoding="utf-8"
        )
        return "downloaded/IMF ArcGIS"
    monkeypatch.setattr(source, "_arcgis_json", read)
    monkeypatch.setattr(source, "_download_arcgis_csv", download)
    with source.db.connect(":memory:") as con:
        source.db.init_schema(con)
        con.execute(source.UAE_TABLE_DDL)
        con.execute(source.CHOKEPOINT_TABLE_DDL)
        if fault:
            message = "vintage changed" if fault == "changed_vintage" else "disagree with the registry"
            with pytest.raises(ValueError, match=message):
                source.update(con)
            assert uae_file.read_bytes() == choke_file.read_bytes() == b"previous complete cache"
            assert con.execute("SELECT count(*) FROM detail.portwatch_uae_daily").fetchone()[0] == 0
        else:
            assert source.update(con)["rows"] == 2
            assert con.execute("SELECT portid FROM detail.portwatch_chokepoint_daily").fetchall() == [("chokepoint6",)]
        assert sorted(filters) == ["1=1", "portid='port5'"]
