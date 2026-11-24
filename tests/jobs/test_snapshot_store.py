import hashlib

import duckdb
import pytest
from requests import HTTPError

from htfa.monitoring.uae.data.snapshot_cache import SnapshotCache
from htfa.monitoring.uae.data.snapshot_store import DATABASE_NAME, WORKBOOK_NAME, ReleaseStore
from htfa.monitoring.uae.jobs import publish_snapshot


class Response:
    def __init__(self, code=200, value=None):
        self.status_code = code
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def json(self):
        return self.value

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError(str(self.status_code), response=self)

    def iter_content(self, chunk_size):
        yield self.value


class Release:
    def __init__(self):
        self.assets = {}
        self.exists = False
        self.reject_upload = False

    def get(self, url, **kwargs):
        if "/releases/tags/" in url:
            if not self.exists:
                return Response(404)
            return Response(value={"id": 1, "assets": [a for a, _ in self.assets.values()]})
        _, data = next((asset, data) for asset, data in self.assets.values() if url.endswith(asset["name"]))
        return Response(value=data)

    def post(self, url, **kwargs):
        if url.endswith("/releases"):
            self.exists = True
            return Response(201, {"id": 1, "assets": []})
        if self.reject_upload:
            return Response(502)
        data = kwargs["data"].read()
        asset = {"name": kwargs["params"]["name"], "state": "uploaded",
                 "id": max(self.assets, default=0) + 1, "size": len(data),
                 "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
        self.assets[asset["id"]] = (asset, data)
        return Response(201, asset)

    def delete(self, url, **kwargs):
        del self.assets[int(url.rsplit("/", 1)[-1])]
        return Response(204)


def write_snapshot(directory, version):
    with duckdb.connect(str(directory / DATABASE_NAME)) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS report")
        connection.execute("CREATE OR REPLACE TABLE report.release AS SELECT ? AS version", [version])
        connection.execute("CREATE SCHEMA IF NOT EXISTS energy_supply")
        connection.execute("CREATE TABLE IF NOT EXISTS energy_supply.ais_reports (observed TIMESTAMP)")
    (directory / WORKBOOK_NAME).write_bytes(version.encode())


def test_release_replacement_preserves_verified_snapshot_on_upload_failure(tmp_path, monkeypatch):
    release = Release()
    monkeypatch.setattr("htfa.monitoring.uae.data.snapshot_store.requests.get", release.get)
    store = ReleaseStore()
    store.session = release
    assert store.current() is None
    write_snapshot(tmp_path, "first")
    first = store.publish(tmp_path, previous=None)

    cache = SnapshotCache(store)
    with cache.directory:
        first_path = cache.database_path()
        write_snapshot(tmp_path, "second")
        release.reject_upload = True
        with pytest.raises(HTTPError, match="502"):
            store.publish(tmp_path, previous=first)
        assert store.current() == first
        assert list(release.assets) == [first.asset_id]

        release.reject_upload = False
        second = store.publish(tmp_path, previous=first)
        assert store.current() == second
        assert list(release.assets) == [second.asset_id]
        with pytest.raises(RuntimeError, match="远端快照已变化"):
            store.publish(tmp_path, previous=first)

        target = tmp_path / "download"
        store.download(second, target, include_workbook=True)
        assert (target / WORKBOOK_NAME).read_bytes() == b"second"
        cache.check_after = 0
        second_path = cache.database_path()
        assert first_path.is_file() and first_path != second_path
        with duckdb.connect(str(second_path), read_only=True) as connection:
            assert connection.execute("SELECT version FROM report.release").fetchone() == ("second",)

        asset, data = release.assets[second.asset_id]
        release.assets[second.asset_id] = ({**asset, "size": len(data) - 1}, data)
        cache.check_after = 0
        assert cache.database_path() == second_path


def test_release_discards_stale_upload_when_another_writer_publishes(tmp_path, monkeypatch):
    release = Release()
    store = ReleaseStore()
    store.session = release
    write_snapshot(tmp_path, "first")
    first = store.publish(tmp_path, previous=None)

    post = release.post
    competing_digest = "a" * 64
    competing = {
        "name": f"htfa-snapshot-{competing_digest}.zip",
        "state": "uploaded", "id": 3, "size": 5,
        "digest": f"sha256:{competing_digest}",
    }

    def publish_concurrently(url, **kwargs):
        response = post(url, **kwargs)
        release.assets[3] = (competing, b"other")
        return response

    monkeypatch.setattr(release, "post", publish_concurrently)
    write_snapshot(tmp_path, "second")
    with pytest.raises(RuntimeError, match="远端快照已变化"):
        store.publish(tmp_path, previous=first)
    assert set(release.assets) == {first.asset_id, competing["id"]}
    assert store.current().asset_id == competing["id"]


@pytest.mark.parametrize("local", [True, False])
def test_publisher_splits_data_dubai_from_cloud_sources(tmp_path, monkeypatch, local):
    from types import SimpleNamespace

    def collect(results_dir, *, sources, collect_energy):
        assert set(sources) == (
            publish_snapshot.DATA_DUBAI_SOURCES if local
            else set(publish_snapshot.HIGH_FREQUENCY_SOURCES) - publish_snapshot.DATA_DUBAI_SOURCES
        )
        assert collect_energy is not local
        return {"installed": True}

    baseline = object()
    store = SimpleNamespace(
        current=lambda: baseline,
        download=lambda snapshot, path, *, include_workbook: None,
        publish=lambda path, *, previous: SimpleNamespace(size=10, sha256="digest"),
    )
    monkeypatch.setattr(publish_snapshot, "refresh", collect)
    result = publish_snapshot.publish_daily(store, tmp_path, data_dubai_only=local)
    assert result["status"] == "verified"
