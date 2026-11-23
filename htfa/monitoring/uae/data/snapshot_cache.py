"""Share a verified, read-only cloud snapshot between the monitoring pages."""

from functools import lru_cache
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import time

import duckdb

from .snapshot_store import DATABASE_NAME, configured_store


class SnapshotCache:
    def __init__(self, store):
        self.store = store
        self.directory = TemporaryDirectory(prefix="htfa-published-")
        self.lock = Lock()
        self.snapshot = None
        self.path = None
        self.check_after = 0.0

    def database_path(self):
        with self.lock:
            if time.monotonic() < self.check_after and self.path is not None:
                return self.path
            try:
                current = self.store.current()
                if current is None:
                    raise FileNotFoundError("对象存储中还没有发布快照")
                if current != self.snapshot:
                    self._load(current)
            except Exception as exc:
                if self.path is None:
                    raise RuntimeError("无法读取对象存储中的监测快照") from exc
                logging.warning("刷新监测快照失败，继续使用已验证的缓存 (%s)", type(exc).__name__)
                self.check_after = time.monotonic() + 30
            else:
                self.check_after = time.monotonic() + 300
            self._prune()
            return self.path

    def _load(self, snapshot):
        root = Path(self.directory.name)
        with TemporaryDirectory(dir=root) as temporary:
            self.store.download(snapshot, temporary)
            candidate = Path(temporary) / DATABASE_NAME
            with duckdb.connect(str(candidate), read_only=True) as connection:
                connection.execute("SELECT version FROM report.release").fetchone()
                connection.execute("SELECT observed FROM energy_supply.ais_reports LIMIT 1").fetchone()
            # Keep the previous path valid for page renders already using it.
            path = root / f"{time.monotonic_ns()}.duckdb"
            candidate.replace(path)
            if self.path:
                self.path.touch()
        self.snapshot = snapshot
        self.path = path

    def _prune(self):
        for file in Path(self.directory.name).glob("*.duckdb"):
            if file != self.path and file.stat().st_mtime < time.time() - 3600:
                try:
                    file.unlink()
                except OSError:
                    logging.warning("旧快照仍在使用，稍后清理本地缓存")


@lru_cache(maxsize=1)
def _configured_cache():
    store = configured_store()
    return SnapshotCache(store) if store else None


def published_database_path(local_path):
    cache = _configured_cache()
    return cache.database_path() if cache else local_path
