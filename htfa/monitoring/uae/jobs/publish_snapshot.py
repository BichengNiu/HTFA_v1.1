"""Refresh all scheduled sources against the latest published GitHub Release snapshot."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

from htfa.monitoring.uae.contracts.paths import ASSETS_DIR, PROJECT_ROOT
from htfa.monitoring.uae.data.database import published_source
from htfa.monitoring.uae.data.snapshot_store import REPOSITORY, ReleaseStore

from .daily_refresh import refresh
from .paths import DATA_DIR, DB_PATH, WORKBOOK_PATH


def seed_from_repository():
    """Use the existing validated release once, when the object key is empty."""
    seed_database = ASSETS_DIR / DB_PATH.name
    relative = seed_database.relative_to(PROJECT_ROOT).as_posix()
    pointer = subprocess.check_output(
        ["git", "show", f"HEAD:{relative}"], cwd=PROJECT_ROOT, text=True,
    )
    expected = next(
        line.removeprefix("oid sha256:") for line in pointer.splitlines()
        if line.startswith("oid sha256:")
    )
    subprocess.run(
        ["git", "lfs", "pull", f"--include={relative}"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    with seed_database.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError("Git LFS 基准数据库 SHA-256 校验失败")
    seed_workbook = ASSETS_DIR / WORKBOOK_PATH.name
    with ZipFile(seed_workbook) as workbook:
        if workbook.testzip() is not None:
            raise ValueError("基准工作簿校验失败")
    published_source(seed_database)
    from htfa.monitoring.energy_supply.jobs.snapshot_update import inspect

    inspect(seed_database)
    shutil.copy2(seed_database, DB_PATH)
    shutil.copy2(seed_workbook, WORKBOOK_PATH)


def publish_daily(store, results_dir, *, bootstrap=False):
    previous = store.current()
    if previous is None:
        if not bootstrap:
            raise FileNotFoundError("未找到最近一次云端快照；首次迁移请手动选择 bootstrap")
        seed_from_repository()
        previous = store.publish(DATA_DIR, previous=None)
        print("已发布验证通过的基准快照", flush=True)
    else:
        store.download(previous, DATA_DIR, include_workbook=True)
    summary = refresh(results_dir)
    print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)
    if not summary.get("installed"):
        raise RuntimeError("本次采集没有生成通过验证的快照")
    published = store.publish(DATA_DIR, previous=previous)
    return {"status": "verified", "bytes": published.size, "sha256": published.sha256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()
    if DATA_DIR == ASSETS_DIR:
        parser.error("HTFA_UAE_DATA_DIR 必须指向独立的云端候选目录")
    token = os.environ.get("GH_TOKEN")
    if not token:
        parser.error("缺少 GitHub Release 发布凭据")
    store = ReleaseStore(os.environ.get("GITHUB_REPOSITORY") or REPOSITORY, token=token)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = publish_daily(store, args.results_dir, bootstrap=args.bootstrap)
    (args.results_dir / "remote-verification.json").write_text(
        json.dumps(result), encoding="utf-8",
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
