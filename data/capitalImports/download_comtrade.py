"""Download classified UAE equipment trade data from UN Comtrade.

For every month the pipeline downloads both UAE-reported imports and exports
reported by all countries with the UAE as partner. Aggregation gives priority
to the UAE report and uses the full mirror universe only when it is absent.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scope_config import (  # noqa: E402
    CODE_DESCRIPTIONS,
    EXCLUDED_RELATED_CODES,
    SERIES,
    UAE_CODE,
    all_equipment_codes,
)

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
REFERENCE_DIR = BASE_DIR / "reference"
REPORTERS_PATH = REFERENCE_DIR / "reporters.json"
API_ROOT = "https://comtradeapi.un.org/data/v1/get"
REPORTERS_URL = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
START_YEAR = 2017


def replace_with_retry(source: Path, destination: Path) -> None:
    """Atomically replace a file, tolerating short cloud-sync locks."""
    for attempt in range(12):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(min(10.0, 0.5 * (attempt + 1)))


def load_api_key() -> str:
    """Load the API key without writing it to logs or output files."""
    key = os.environ.get("COMTRADE_API_KEY", "").strip()
    env_path = BASE_DIR / ".env"
    if not key and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("COMTRADE_API_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    if not key:
        raise RuntimeError(
            "COMTRADE_API_KEY is missing. Add it to data/capitalImports/.env."
        )
    return key


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "HTFA-UAE-equipment-pipeline/1.0"},
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    temporary.write_bytes(payload)
    replace_with_retry(temporary, destination)


class ComtradeClient:
    def __init__(self, api_key: str, min_interval: float) -> None:
        self.api_key = api_key
        self.min_interval = min_interval
        self.last_request_at = 0.0

    def get(
        self,
        frequency: str,
        params: dict[str, str | int],
        destination: Path,
        force: bool = False,
    ) -> dict[str, Any]:
        if destination.exists() and not force:
            return json.loads(destination.read_text(encoding="utf-8"))

        query = dict(params)
        query["subscription-key"] = self.api_key
        query.setdefault("maxRecords", 100000)
        query.setdefault("includeDesc", "false")
        query.setdefault("breakdownMode", "classic")
        encoded = urllib.parse.urlencode(query, safe=",")
        url = f"{API_ROOT}/C/{frequency}/HS?{encoded}"
        temporary = destination.with_suffix(".json.part")

        for attempt in range(7):
            delay = self.min_interval - (time.monotonic() - self.last_request_at)
            if delay > 0:
                time.sleep(delay)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "HTFA-UAE-equipment-pipeline/1.0"},
            )
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    payload = json.load(response)
                self.last_request_at = time.monotonic()
                rows = payload.get("data", [])
                if len(rows) >= int(query["maxRecords"]):
                    raise RuntimeError(
                        f"API result may be truncated at {len(rows):,} records"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
                replace_with_retry(temporary, destination)
                return payload
            except urllib.error.HTTPError as error:
                self.last_request_at = time.monotonic()
                if error.code not in {429, 500, 502, 503, 504} or attempt == 6:
                    message = error.read(1000).decode("utf-8", "replace")
                    raise RuntimeError(
                        f"UN Comtrade HTTP {error.code}: {message}"
                    ) from error
                time.sleep(min(90.0, 8.0 * (2**attempt)))
            except (TimeoutError, urllib.error.URLError) as error:
                self.last_request_at = time.monotonic()
                if attempt == 6:
                    raise RuntimeError("UN Comtrade request failed") from error
                time.sleep(min(90.0, 8.0 * (2**attempt)))
        raise AssertionError("unreachable")


def months_for_year(year: int) -> list[str]:
    if year < date.today().year:
        last_month = 12
    elif year == date.today().year:
        last_month = date.today().month
    else:
        return []
    return [f"{year}{month:02d}" for month in range(1, last_month + 1)]


def download_monthly(client: ComtradeClient, force: bool) -> None:
    codes = ",".join(all_equipment_codes())
    for year in range(START_YEAR, date.today().year + 1):
        periods = ",".join(months_for_year(year))
        queries = {
            "equipment_uae_reported": {
                "period": periods,
                "reporterCode": UAE_CODE,
                "partnerCode": 0,
                "flowCode": "M",
                "cmdCode": codes,
            },
            "equipment_all_mirror": {
                "period": periods,
                "partnerCode": UAE_CODE,
                "flowCode": "X",
                "cmdCode": codes,
            },
        }
        for source, parameters in queries.items():
            path = RAW_DIR / source / f"{source}_{year}.json"
            payload = client.get("M", parameters, path, force)
            print(
                f"{year} {source}: {len(payload.get('data', [])):,} rows",
                flush=True,
            )


def write_scope_file() -> None:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = REFERENCE_DIR / "commodity_scope.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["series", "code", "description", "basis"])
        for key, definition in SERIES.items():
            for code in sorted(definition["codes"]):
                writer.writerow(
                    [
                        key,
                        code,
                        CODE_DESCRIPTIONS[code],
                        definition["basis"],
                    ]
                )

    excluded_path = REFERENCE_DIR / "commodity_scope_exclusions.csv"
    with excluded_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["code_or_range", "exclusion_reason"])
        writer.writerows(EXCLUDED_RELATED_CODES.items())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-interval", type=float, default=6.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    download_file(REPORTERS_URL, REPORTERS_PATH)
    write_scope_file()
    client = ComtradeClient(load_api_key(), args.min_interval)
    download_monthly(client, args.force)
    print("Download complete.", flush=True)


if __name__ == "__main__":
    main()
