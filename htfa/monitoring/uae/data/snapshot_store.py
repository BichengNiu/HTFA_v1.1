"""Read and publish the monitoring snapshot attached to a GitHub Release."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

import requests

from htfa.monitoring.uae.contracts.paths import PROJECT_ROOT


DATABASE_NAME = "uae.duckdb"
WORKBOOK_NAME = "阿联酋.xlsx"
REPOSITORY = "BichengNiu/HTFA_v1.1"
RELEASE_TAG = "htfa-data"
ASSET_NAME = re.compile(r"htfa-snapshot-([0-9a-f]{64})\.zip")
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class Snapshot:
    asset_id: int
    name: str
    size: int
    sha256: str


def _snapshot(asset):
    match = ASSET_NAME.fullmatch(asset["name"])
    if not match or asset["state"] != "uploaded":
        return None
    digest = match[1]
    if asset.get("digest") != f"sha256:{digest}":
        return None
    return Snapshot(asset["id"], asset["name"], asset["size"], digest)


class ReleaseStore:
    def __init__(self, repository=REPOSITORY, *, token=None):
        self.repository = repository
        self.api = f"https://api.github.com/repos/{repository}"
        self.upload = f"https://uploads.github.com/repos/{repository}/releases"
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/vnd.github+json"
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _release(self):
        with self.session.get(f"{self.api}/releases/tags/{RELEASE_TAG}", timeout=30) as response:
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _current(release):
        assets = () if release is None else release["assets"]
        return max(
            (snapshot for asset in assets if (snapshot := _snapshot(asset))),
            key=lambda snapshot: snapshot.asset_id,
            default=None,
        )

    def current(self):
        return self._current(self._release())

    def download(self, snapshot, destination, *, include_workbook=False):
        """Download and verify the complete archive before unpacking it."""
        url = f"https://github.com/{self.repository}/releases/download/{RELEASE_TAG}/{snapshot.name}"
        with requests.get(url, stream=True, timeout=(15, 60)) as response, tempfile.TemporaryFile() as archive:
            response.raise_for_status()
            digest = hashlib.sha256()
            size = 0
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                archive.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            if size != snapshot.size or digest.hexdigest() != snapshot.sha256:
                raise ValueError("GitHub 快照的大小或 SHA-256 校验失败")
            with ZipFile(archive) as bundle:
                if sorted(bundle.namelist()) != sorted((DATABASE_NAME, WORKBOOK_NAME)):
                    raise ValueError("快照必须包含一份数据库和对应工作簿")
                bundle.extract(DATABASE_NAME, destination)
                if include_workbook:
                    bundle.extract(WORKBOOK_NAME, destination)

    def publish(self, directory, *, previous):
        """Upload under a unique name, verify it, then remove older snapshots."""
        release = self._release()
        if self._current(release) != previous:
            raise RuntimeError("远端快照已变化，请重新采集")
        if release is None:
            response = self.session.post(
                f"{self.api}/releases",
                json={"tag_name": RELEASE_TAG, "name": "HTFA Data Snapshot",
                      "prerelease": True, "make_latest": "false"},
                timeout=30,
            )
            response.raise_for_status()
            release = response.json()
        with tempfile.TemporaryFile() as archive:
            with ZipFile(archive, mode="w", compression=ZIP_DEFLATED, compresslevel=1) as bundle:
                for name in (DATABASE_NAME, WORKBOOK_NAME):
                    bundle.write(Path(directory) / name, name)
            size = archive.tell()
            archive.seek(0)
            digest = hashlib.file_digest(archive, "sha256").hexdigest()
            archive.seek(0)
            name = f"htfa-snapshot-{digest}.zip"
            release = self._release()
            if self._current(release) != previous:
                raise RuntimeError("远端快照已变化，请重新采集")
            if previous and previous.name == name:
                self._remove_older_assets(release, previous)
                return previous
            for asset in release["assets"]:
                if asset["name"] == name and asset["state"] == "starter":
                    self._delete_asset(asset["id"])
            response = self.session.post(
                f"{self.upload}/{release['id']}/assets",
                params={"name": name},
                headers={"Content-Type": "application/zip"},
                data=archive,
                timeout=(15, 600),
            )
            response.raise_for_status()
            published = _snapshot(response.json())
        if published is None or published.name != name or published.size != size:
            raise RuntimeError("GitHub 发布附件的名称、大小或 SHA-256 校验失败")
        latest = self._release()
        other_assets = {"assets": [
            asset for asset in latest["assets"] if asset["id"] != published.asset_id
        ]}
        if self._current(other_assets) != previous:
            self._delete_asset(published.asset_id)
            raise RuntimeError("远端快照已变化，请重新采集")
        self._remove_older_assets(release, published)
        return published

    def _remove_older_assets(self, release, current):
        for asset in release["assets"]:
            if ASSET_NAME.fullmatch(asset["name"]) and asset["id"] != current.asset_id:
                self._delete_asset(asset["id"])

    def _delete_asset(self, asset_id):
        response = self.session.delete(f"{self.api}/releases/assets/{asset_id}", timeout=30)
        if response.status_code != 404:
            response.raise_for_status()


def configured_store():
    """Enable GitHub snapshot reads in Streamlit Cloud and explicit deployments."""
    if PROJECT_ROOT.is_relative_to(Path("/mount/src")) or os.getenv("HTFA_RELEASE_SNAPSHOT") == "1":
        return ReleaseStore()
    return None
