"""Build and validate a matching energy database/workbook publication.

Run scheduled collection only through this entry point. Without --publish,
the candidate is validated and discarded. No UI operation invokes this job.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile

from htfa.monitoring.uae.jobs import db, source_energy_supply
from htfa.monitoring.uae.jobs.paths import DB_PATH, WORKBOOK_PATH
from htfa.monitoring.uae.jobs.publish_report import publish_workbook
from htfa.monitoring.uae.jobs.history_validation import validate_history
from htfa.monitoring.uae.jobs.uae_metadata import complete_metadata, sync_workbook_dictionary
from .snapshot_retry import decision
from .snapshot_update import collect_candidate, inspect, validate_progress


@contextmanager
def publication_lock(database: Path):
    """Reject concurrent writers on Windows and Linux."""
    lock_path = database.with_suffix(".publication.lock")
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if not lock_path.stat().st_size:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def install_pair(candidate_db, candidate_workbook, database, workbook):
    """Replace both validated assets, restoring the originals on failure."""
    with tempfile.TemporaryDirectory(prefix="energy-backup-", dir=database.parent) as temporary:
        backup_db = Path(temporary) / "before.duckdb"
        backup_workbook = Path(temporary) / "before.xlsx"
        shutil.copy2(database, backup_db)
        shutil.copy2(workbook, backup_workbook)
        changed_db = False
        try:
            os.replace(candidate_db, database)
            changed_db = True
            os.replace(candidate_workbook, workbook)
        except BaseException:
            if changed_db:
                os.replace(backup_db, database)
            raise


def run(*, publish=False, retry_only=True, prepare_only=False,
        database=DB_PATH, workbook=WORKBOOK_PATH):
    """Collect, derive and validate candidates before optional installation."""
    database, workbook = Path(database).resolve(), Path(workbook).resolve()
    if (workbook.parent / f"~${workbook.name}").exists():
        raise RuntimeError("请先关闭 Excel 工作簿")
    with publication_lock(database):
        before = inspect(database)
        if retry_only and not prepare_only:
            with db.connect(database, read_only=True) as con:
                row = con.execute(
                    "SELECT value FROM energy_supply.app_meta WHERE key='published_snapshot'"
                ).fetchone()
            gate = decision(json.loads(row[0]) if row else None)
            if not gate["pending_sources"]:
                return gate
        with tempfile.TemporaryDirectory(prefix="energy-candidate-", dir=database.parent) as temporary:
            candidate = Path(temporary) / "uae.duckdb"
            candidate_workbook = Path(temporary) / "report.xlsx"
            if prepare_only:
                shutil.copy2(database, candidate)
                summary = {"status": "prepared_existing_facts"}
            else:
                summary = collect_candidate(database, candidate, retry_only=retry_only)
                if not any(r["status"] == "ok" for r in summary["source_results"].values()):
                    return {**summary, "status": "skipped_no_successful_source"}
            with db.connect(candidate) as con:
                con.execute("SET memory_limit='512MB'")
                con.execute("SET threads=2")
                summary["indicators"] = source_energy_supply.update(con, skip_download=True)
                summary["metadata"] = complete_metadata(con)
            shutil.copy2(workbook, candidate_workbook)
            summary["workbook"] = source_energy_supply.merge(candidate_workbook, database=candidate)
            summary["dictionary"] = sync_workbook_dictionary(candidate_workbook, database=candidate)
            with db.connect(candidate) as con:
                summary["report"] = publish_workbook(con, candidate_workbook)
            validate_progress(before, inspect(candidate))
            summary["history_validation"] = validate_history(database, candidate, include_report=True)
            if publish:
                install_pair(candidate, candidate_workbook, database, workbook)
            summary["installed"] = publish
            return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--collect", action="store_true", help="强制尝试本窗口所有来源")
    parser.add_argument("--prepare-only", action="store_true", help="仅从已入库事实重建报告，不采集")
    args = parser.parse_args()
    print(json.dumps(run(publish=args.publish, retry_only=not args.collect,
                         prepare_only=args.prepare_only), default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
