"""Transfer the published DuckDB and workbook together as one S3 object."""

from contextlib import closing
from dataclasses import dataclass
import base64
import hashlib
import os
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


DATABASE_NAME = "uae.duckdb"
WORKBOOK_NAME = "阿联酋.xlsx"
DEFAULT_KEY = "htfa/latest.zip"
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class Snapshot:
    etag: str
    size: int
    sha256: str

    @classmethod
    def from_response(cls, response):
        return cls(
            response["ETag"],
            response["ContentLength"],
            response["Metadata"]["sha256"],
        )


class SnapshotStore:
    def __init__(self, client, bucket, key=DEFAULT_KEY):
        self.client = client
        self.location = {"Bucket": bucket, "Key": key}

    def current(self):
        from botocore.exceptions import ClientError

        try:
            response = self.client.head_object(**self.location)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return Snapshot.from_response(response)

    def download(self, snapshot, destination, *, include_workbook=False):
        """Check the object hash and ZIP members before returning the files."""
        response = self.client.get_object(**self.location, IfMatch=snapshot.etag)
        with closing(response["Body"]) as body, tempfile.TemporaryFile() as archive:
            digest = hashlib.sha256()
            size = 0
            for chunk in body.iter_chunks(chunk_size=CHUNK_SIZE):
                archive.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            if size != snapshot.size or digest.hexdigest() != snapshot.sha256:
                raise ValueError("对象存储快照的大小或 SHA-256 校验失败")
            with ZipFile(archive) as bundle:
                if sorted(bundle.namelist()) != sorted((DATABASE_NAME, WORKBOOK_NAME)):
                    raise ValueError("快照必须包含一份数据库和对应工作簿")
                bundle.extract(DATABASE_NAME, destination)
                if include_workbook:
                    bundle.extract(WORKBOOK_NAME, destination)

    def publish(self, directory, *, previous):
        """Atomically replace the fixed key if its current version is the baseline."""
        with tempfile.TemporaryFile() as archive:
            with ZipFile(archive, mode="w", compression=ZIP_DEFLATED, compresslevel=1) as bundle:
                for name in (DATABASE_NAME, WORKBOOK_NAME):
                    bundle.write(Path(directory) / name, name)
            archive.seek(0)
            sha = hashlib.sha256()
            md5 = hashlib.md5(usedforsecurity=False)
            for chunk in iter(lambda: archive.read(CHUNK_SIZE), b""):
                sha.update(chunk)
                md5.update(chunk)
            size = archive.tell()
            archive.seek(0)
            condition = {"IfMatch": previous.etag} if previous else {"IfNoneMatch": "*"}
            response = self.client.put_object(
                **self.location,
                **condition,
                Body=archive,
                ContentLength=size,
                ContentType="application/zip",
                ContentMD5=base64.b64encode(md5.digest()).decode("ascii"),
                Metadata={"sha256": sha.hexdigest()},
            )
        expected = Snapshot(response["ETag"], size, sha.hexdigest())
        if self.current() != expected:
            raise RuntimeError("已上传快照的远端 ETag、大小或 SHA-256 元数据不匹配")
        return expected


def configured_store():
    """Build a client only when object storage has been configured."""
    bucket = os.getenv("HTFA_SNAPSHOT_BUCKET", "").strip()
    if not bucket:
        return None
    import boto3
    from botocore.config import Config

    endpoint = os.getenv("HTFA_SNAPSHOT_ENDPOINT") or None
    if endpoint and not endpoint.startswith("https://"):
        raise ValueError("HTFA_SNAPSHOT_ENDPOINT 必须使用 HTTPS")
    access_key = os.getenv("HTFA_SNAPSHOT_ACCESS_KEY_ID")
    secret_key = os.getenv("HTFA_SNAPSHOT_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        raise ValueError("缺少对象存储访问凭据")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.getenv("HTFA_SNAPSHOT_REGION") or ("auto" if endpoint else "us-east-1"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            s3={"addressing_style": "path"},
        ),
    )
    return SnapshotStore(client, bucket, os.getenv("HTFA_SNAPSHOT_KEY") or DEFAULT_KEY)
