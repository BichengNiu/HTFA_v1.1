"""Isolated online refresh using the existing source validators and merge contracts."""

import argparse

from . import db
from ._excel_helpers import portable_workbook_writes
from .merge_workbook import main as merge_workbook
from .update_data import run_sources
from .uae_metadata import complete_metadata


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
