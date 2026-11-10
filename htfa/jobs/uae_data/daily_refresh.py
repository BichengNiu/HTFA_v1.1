"""One cloud writer for UAE high-frequency sources and energy observations.

Each source runs in a separate process against a candidate pair. Failed sources
restore their checkpoint; the validated pair is installed only at the end.
"""

import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

from .paths import DATA_DIR, DB_PATH, WORKBOOK_PATH
from .source_registry import SOURCES
from .history_validation import validate_history

# The quarterly/annual jobs remain manual. Energy has its own live collector;
# source_energy_supply.update alone only rebuilds existing facts.
HIGH_FREQUENCY_SOURCES = tuple(name for name in SOURCES if name not in {
    "energy_supply", "eia_liquids", "fcsc_gdp", "fcsc_annual",
    "wdi_gcc", "gfs", "salik",
})


def worker(name):
    """Run one source or final publication in its isolated process."""
    from . import db
    if name == "energy":
        from htfa.jobs.energy_supply.publish import run
        outcome = run(publish=True, retry_only=False)
        if outcome.get("status") == "skipped_no_successful_source":
            raise RuntimeError(json.dumps(outcome, ensure_ascii=False, default=str))
        return outcome
    if name == "finalize":
        from .publish_report import publish_workbook
        from .uae_metadata import sync_workbook_dictionary
        dictionary = sync_workbook_dictionary(WORKBOOK_PATH)
        with db.connect() as con:
            report = publish_workbook(con, WORKBOOK_PATH)
        return {"status": "ok", "dictionary": dictionary, "report": report}
    if name not in HIGH_FREQUENCY_SOURCES:
        raise ValueError(f"Unsupported scheduled source: {name}")
    from .update_data import run_sources
    results = run_sources([name])
    if any(item["status"] != "ok" for item in results.values()):
        raise RuntimeError(json.dumps(results, ensure_ascii=False, default=str))
    module = importlib.import_module(f".source_{name}", package=__package__)
    result = module.merge(WORKBOOK_PATH)
    if result.get("status") not in {"ok", "skipped"}:
        raise RuntimeError(f"Workbook merge failed: {result}")
    return {"status": "ok", "update": results[name], "merge": result}


def run_worker(name, directory, results_dir, *, timeout=None):
    """Execute a bounded worker; keep logs and structured results outside Git."""
    result_path = results_dir / f"{name}.json"
    if timeout is None:
        timeout = 2700 if name == "energy" else 1800 if name in {
            "ded", "dld", "dubai_customs_air",
        } else 600
    # A remote-main retry must never consume a previous attempt's result.
    result_path.unlink(missing_ok=True)
    env = {**os.environ, "HTFA_UAE_DATA_DIR": str(directory),
           "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        with (results_dir / f"{name}.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                [sys.executable, "-m", "htfa.jobs.uae_data.daily_refresh",
                 "--worker", name, "--result", str(result_path)],
                env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout,
            )
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            result = {"status": "error", "error": f"Worker exited {completed.returncode} without result"}
        if completed.returncode:
            result["status"] = "error"
        return result
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"Source exceeded {timeout} seconds"}


def copy_pair(source, destination):
    for name in (DB_PATH.name, WORKBOOK_PATH.name):
        shutil.copy2(source / name, destination / name)


def refresh(results_dir, *, sources=HIGH_FREQUENCY_SOURCES, collect_energy=True):
    """Install one validated pair while preserving every failed source baseline."""
    from htfa.jobs.energy_supply.publish import install_pair, publication_lock
    from htfa.jobs.energy_supply.snapshot_update import inspect, validate_progress

    results_dir = Path(results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    with publication_lock(DB_PATH), tempfile.TemporaryDirectory(prefix="daily-candidate-", dir=DATA_DIR) as temporary:
        candidate = Path(temporary)
        copy_pair(DATA_DIR, candidate)
        # Raw downloads remain an untracked, reusable cache. Secrets are never
        # copied into a publication, result file or log.
        (DATA_DIR / "raw").mkdir(exist_ok=True)
        (candidate / "raw").symlink_to(DATA_DIR / "raw", target_is_directory=True)
        if (DATA_DIR / ".env").is_file():
            (candidate / ".env").symlink_to(DATA_DIR / ".env")
        checkpoint = candidate / "checkpoint"
        checkpoint.mkdir()
        successful = []
        for name in [*sources, *(["energy"] if collect_energy else [])]:
            copy_pair(candidate, checkpoint)
            print(f"[daily] {name}: started", flush=True)
            outcome = run_worker(name, candidate, results_dir)
            if outcome.get("status") != "error":
                try:
                    outcome["history_validation"] = validate_history(
                        checkpoint / DB_PATH.name, candidate / DB_PATH.name,
                    )
                except Exception as exc:
                    outcome = {"status": "error", "error": str(exc), "collection": outcome}
            summary["sources"][name] = outcome
            if outcome.get("status") == "error":
                # A killed DuckDB writer can leave a WAL for the rejected
                # candidate. Never replay it onto the restored checkpoint.
                (candidate / (DB_PATH.name + ".wal")).unlink(missing_ok=True)
                copy_pair(checkpoint, candidate)
                print(f"[daily] {name}: failed; checkpoint restored", flush=True)
            else:
                successful.append(name)
                print(f"[daily] {name}: {outcome.get('status', 'ok')}", flush=True)
        if successful:
            final = run_worker("finalize", candidate, results_dir)
            if final.get("status") != "error":
                try:
                    final["history_validation"] = validate_history(
                        DB_PATH, candidate / DB_PATH.name, include_report=True,
                    )
                    validate_progress(inspect(DB_PATH), inspect(candidate / DB_PATH.name))
                except Exception as exc:
                    final = {"status": "error", "error": str(exc)}
            summary["publication"] = final
            if final.get("status") == "error":
                summary["status"] = "error"
            else:
                install_pair(candidate / DB_PATH.name, candidate / WORKBOOK_PATH.name, DB_PATH, WORKBOOK_PATH)
                summary["status"] = "partial" if any(
                    result.get("status") == "error" or any(
                        item.get("status") == "error" for item in result.get("source_results", {}).values()
                    ) for result in summary["sources"].values()
                ) else "ok"
                summary["installed"] = True
        else:
            summary["status"] = "error"
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    (results_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--results-dir", type=Path, default=Path(".cache/daily-refresh"))
    args = parser.parse_args()
    if args.worker:
        try:
            result = worker(args.worker)
            code = 0
        except Exception as exc:
            traceback.print_exc()
            result = {"status": "error", "error": str(exc)}
            code = 1
        args.result.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
        return code
    result = refresh(args.results_dir)
    print(json.dumps(result, ensure_ascii=False, default=str))
    # Partial validated results are committed before the workflow reports a
    # failed source. A total/finalization failure never installs either asset.
    return 0 if result.get("installed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
