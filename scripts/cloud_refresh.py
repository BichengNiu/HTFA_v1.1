"""Daily UAE monthly-page refresh, staged atomically and independent of keepalive."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA = ROOT / "data/UAE"
MONTHLY_SOURCES = (
    "baker_hughes", "oil", "cbuae", "ded", "dld", "employment", "foreign_labour",
    "pmi", "portwatch", "public_market", "steel", "fcsc", "wam", "dubai_customs_air", "dot_t100",
)
COMMIT_PREFIX = "data: refresh UAE monthly data "
T100_TOOL = Path("raw/t100/download_uae_years.mjs")


def local_day():
    return datetime.now(ZoneInfo("Asia/Dubai")).date().isoformat()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def refresh_due(day, *, force=False):
    if force:
        return True
    messages = git("log", "origin/main", "-50", "--format=%s", "--", "data/UAE/uae.duckdb").splitlines()
    return COMMIT_PREFIX + day not in messages


def preflight(data, sources):
    tracked_helper = ROOT / "htfa/jobs/uae_data/download_uae_years.mjs"
    native_helper = ROOT / "htfa/jobs/uae_data/download_t100.py"
    if "dot_t100" in sources and not native_helper.is_file() and not tracked_helper.is_file() and not (data / T100_TOOL).is_file():
        raise RuntimeError(
            "BTS T-100 download helper is absent: data/UAE/" + str(T100_TOOL)
            + ". Existing data is preserved; restore it as htfa/jobs/uae_data/download_uae_years.mjs for reproducible full refresh."
        )


def protect_history(baseline, candidate):
    """Reject lost non-null observations even if a source passed its own checks."""
    import duckdb
    from htfa.monitoring.uae.database import published_source

    published_source(candidate)
    quoted = str(Path(baseline).resolve()).replace("'", "''")
    def keys(schema):
        return (
            "SELECT s.sheet_name, json_extract_string(s.heading,'$[1][' || o.column_index || ']') AS indicator, "
            "json_extract_string(s.heading,'$[3][' || o.column_index || ']') AS unit,o.period "
            f"FROM {schema}.observations o JOIN {schema}.sheets s USING(sheet_index)"
        )
    with duckdb.connect(str(candidate), read_only=True) as con:
        con.execute(f"ATTACH '{quoted}' AS previous (READ_ONLY)")
        missing = con.execute(f"SELECT * FROM ({keys('previous.report')} EXCEPT {keys('report')}) LIMIT 5").fetchall()
        if missing:
            raise RuntimeError(f"Refusing to remove existing report history: {missing}")


def sanitized(text):
    # Existing source libraries may include URL query parameters in exceptions.
    return re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[redacted]", text)


def run_worker(candidate, sources, *, merge_only=False, timeout=2400):
    env = {**os.environ, "HTFA_UAE_DATA_DIR": str(candidate), "PYTHONDONTWRITEBYTECODE": "1"}
    command = [sys.executable, "-m", "htfa.jobs.uae_data.cloud_worker", "--sources", ",".join(sources)]
    if merge_only:
        command.append("--merge-only")
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
        print(sanitized(output), flush=True)
        raise RuntimeError("Refresh timed out; live database is unchanged")
    print(sanitized(output), flush=True)
    if process.returncode:
        raise RuntimeError("Source or report validation failed; live database is unchanged")


def refresh(sources, *, validate_only=False, merge_only=False, timeout=2400, day=None):
    import duckdb
    from htfa.jobs.uae_data.portable_workbook import materialize_report
    from htfa.monitoring.uae.database import published_source

    day = day or local_day()
    if merge_only and not validate_only:
        raise ValueError("Offline merge validation cannot publish or mark an online refresh successful")
    if not merge_only:
        preflight(DATA, sources)
    baseline = DATA / "uae.duckdb"
    base_commit = git("rev-parse", "HEAD")
    with tempfile.TemporaryDirectory(prefix="htfa-refresh-", dir=DATA.parent.parent.parent) as directory:
        candidate = Path(directory)
        database = candidate / "uae.duckdb"
        shutil.copy2(baseline, database)
        if "dot_t100" in sources and (DATA / T100_TOOL).exists():
            (candidate / T100_TOOL).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(DATA / T100_TOOL, candidate / T100_TOOL)
        materialize_report(database, candidate / "阿联酋.xlsx")
        run_worker(candidate, sources, merge_only=merge_only, timeout=timeout)
        protect_history(baseline, database)
        version = published_source(database).version
        if validate_only:
            return {"status": "validated_only", "sources": list(sources), "version": version}
        git("fetch", "origin", "main")
        if git("rev-parse", "origin/main") != base_commit:
            raise RuntimeError("Remote main changed during refresh; do not overwrite it, retry next run")
        with duckdb.connect(str(database)) as con:
            con.execute("CREATE TABLE IF NOT EXISTS cloud_refresh_runs (refresh_date DATE PRIMARY KEY, "
                        "finished_at TIMESTAMP, sources_json VARCHAR, report_version VARCHAR)")
            con.execute("INSERT OR REPLACE INTO cloud_refresh_runs VALUES (?,?,?,?)", [
                day, datetime.now(timezone.utc).replace(tzinfo=None), json.dumps(list(sources)), version,
            ])
            con.execute("CHECKPOINT")
        os.replace(database, baseline)
    return {"status": "refreshed", "date": day, "sources": list(sources), "version": version}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "run"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sources", default=",".join(MONTHLY_SOURCES))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--merge-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=2400)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)
    sources = tuple(dict.fromkeys(s.strip() for s in args.sources.split(",") if s.strip()))
    if not sources or set(sources) - set(MONTHLY_SOURCES):
        parser.error("Only sources used by the UAE monthly page may be refreshed")
    day = local_day()
    if args.command == "plan":
        due = refresh_due(day, force=args.force)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write(f"due={str(due).lower()}\ndate={day}\n")
        print(json.dumps({"due": due, "date": day, "sources": sources}))
        return 0
    result = {}
    try:
        result = refresh(sources, validate_only=args.validate_only, merge_only=args.merge_only,
                         timeout=args.timeout, day=day)
        print(json.dumps(result), flush=True)
        return 0
    except Exception as error:
        result = {"status": "failed", "date": day, "error": sanitized(str(error))}
        print(json.dumps(result), flush=True)
        return 1
    finally:
        if args.result:
            args.result.parent.mkdir(parents=True, exist_ok=True)
            args.result.write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
