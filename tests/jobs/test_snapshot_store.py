import hashlib
import io

from botocore.exceptions import ClientError
from botocore.response import StreamingBody
import duckdb
import pytest

from htfa.monitoring.uae.data.snapshot_cache import SnapshotCache
from htfa.monitoring.uae.data.snapshot_store import DATABASE_NAME, WORKBOOK_NAME, SnapshotStore


class Bucket:
    def __init__(self):
        self.objects = {}

    def head_object(self, *, Bucket, Key):
        try:
            data, tag, metadata = self.objects[Bucket, Key]
        except KeyError:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject") from None
        return {"ETag": tag, "ContentLength": len(data), "Metadata": metadata}

    def put_object(self, *, Bucket, Key, Body, Metadata, **params):
        old = self.objects.get((Bucket, Key))
        if old and params.get("IfMatch") != old[1]:
            raise ClientError({"Error": {"Code": "412"}}, "PutObject")
        if not old:
            assert params["IfNoneMatch"] == "*"
        data = Body.read()
        tag = f'"{hashlib.sha256(data).hexdigest()}"'
        self.objects[Bucket, Key] = (data, tag, Metadata)
        return {"ETag": tag}

    def get_object(self, *, Bucket, Key, IfMatch):
        data, tag, _ = self.objects[Bucket, Key]
        assert tag == IfMatch
        return {"Body": StreamingBody(io.BytesIO(data), len(data))}


def write_snapshot(directory, version):
    with duckdb.connect(str(directory / DATABASE_NAME)) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS report")
        connection.execute("CREATE OR REPLACE TABLE report.release AS SELECT ? AS version", [version])
        connection.execute("CREATE SCHEMA IF NOT EXISTS energy_supply")
        connection.execute("CREATE TABLE IF NOT EXISTS energy_supply.ais_reports (observed TIMESTAMP)")
    (directory / WORKBOOK_NAME).write_bytes(version.encode())


def test_single_key_rejects_a_stale_writer_and_keeps_a_verified_read_cache(tmp_path):
    bucket = Bucket()
    store = SnapshotStore(bucket, "private")
    assert store.current() is None
    write_snapshot(tmp_path, "first")
    first = store.publish(tmp_path, previous=None)
    cache = SnapshotCache(store)
    with cache.directory:
        first_path = cache.database_path()
        write_snapshot(tmp_path, "second")
        second = store.publish(tmp_path, previous=first)
        assert store.current() == second
        assert len(bucket.objects) == 1
        with pytest.raises(ClientError, match="412"):
            store.publish(tmp_path, previous=first)

        target = tmp_path / "download"
        store.download(second, target, include_workbook=True)
        assert (target / WORKBOOK_NAME).read_bytes() == b"second"
        cache.check_after = 0
        second_path = cache.database_path()
        assert first_path.is_file() and first_path != second_path
        with duckdb.connect(str(second_path), read_only=True) as connection:
            assert connection.execute("SELECT version FROM report.release").fetchone() == ("second",)

        location = ("private", "htfa/latest.zip")
        data, tag, metadata = bucket.objects[location]
        bucket.objects[location] = (data[:-1], tag, metadata)
        cache.check_after = 0
        assert cache.database_path() == second_path
