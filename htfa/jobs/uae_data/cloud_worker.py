"""Isolated online refresh using the existing source validators and merge contracts."""

import argparse
import csv

from . import db
from ._excel_helpers import portable_workbook_writes
from .merge_workbook import main as merge_workbook
from .update_data import run_sources
from .uae_metadata import complete_metadata


def seed_wam_registry():
    """Restore existing reviewed/automatic rows and citations from the baseline DB."""
    from . import source_wam as wam

    if wam.DAILY_PATH.exists():
        return
    with db.connect(read_only=True) as con:
        cursor = con.execute("SELECT * FROM detail.wam_military_strike_daily ORDER BY date")
        fields = [column[0] for column in cursor.description]
        rows = [dict(zip(fields, row, strict=True)) for row in cursor.fetchall()]
    if not rows:
        raise RuntimeError("WAM baseline has no daily history to restore")
    wam.RAW_DIR.mkdir(parents=True, exist_ok=True)
    with wam.DAILY_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=wam.REQUIRED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: int(row[field]) if isinstance(row[field], bool) else row[field]
                             for field in wam.REQUIRED_COLUMNS})
    with wam.ASSET_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", "source_url"])
        writer.writeheader()
        writer.writerows({"date": row["date"], "source_url": row["source_url_3"]}
                         for row in rows if row["source_url_3"])
    restored = wam.load_daily_observations(wam.DAILY_PATH)
    if restored != rows:
        raise RuntimeError("WAM restored history differs from the published baseline")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--merge-only", action="store_true")
    args = parser.parse_args(argv)
    names = args.sources.split(",")
    if args.merge_only:
        with db.connect() as con:
            db.init_schema(con)
            complete_metadata(con)
    else:
        if "wam" in names:
            seed_wam_registry()
        results = run_sources(names, force=True)
        failed = []
        for name, result in results.items():
            print(f"[cloud refresh] {name}: {result['status']} {result.get('note', '')}", flush=True)
            if result["status"] != "ok":
                failed.append(name)
        if failed:
            raise RuntimeError("Source refresh failed; publication cancelled: " + ", ".join(failed))
    with portable_workbook_writes():
        if merge_workbook(["--source", args.sources]):
            raise RuntimeError("Workbook/report validation failed; publication cancelled")
    with db.connect() as con:
        con.execute("CHECKPOINT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
