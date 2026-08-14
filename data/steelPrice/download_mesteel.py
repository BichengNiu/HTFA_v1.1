"""Download the public MEsteel monthly UAE steel-price dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
RAW_PATH = RAW_DIR / "mesteel_monthly_prices.json"
MANIFEST_PATH = RAW_DIR / "source_manifest.json"
SOURCE_URL = "https://mesteel.com/newsletter/get_monthly_prices.php"
LANDING_PAGE_URL = (
    "https://mesteel.com/newsletter/monthly_prices_latest4.php"
)


def validate_payload(payload: Any) -> dict[str, Any]:
    """Validate the stable fields needed by the downstream processor."""
    if not isinstance(payload, dict):
        raise ValueError("MEsteel response must be a JSON object")

    dates = payload.get("dates")
    records = payload.get("data")
    if not isinstance(dates, list) or not dates:
        raise ValueError("MEsteel response has no dates")
    if not isinstance(records, list) or not records:
        raise ValueError("MEsteel response has no data records")
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("MEsteel dates must be sorted and unique")

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"MEsteel record {index} is not an object")
        for field in ("product", "origin", "prices"):
            if field not in record:
                raise ValueError(
                    f"MEsteel record {index} is missing {field}"
                )
        if not isinstance(record["prices"], dict):
            raise ValueError(
                f"MEsteel record {index} prices must be an object"
            )
    return payload


def download(timeout: int = 30) -> tuple[Path, Path]:
    """Download, validate, and atomically persist the current JSON payload."""
    request = Request(
        SOURCE_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "HTFA-MEsteel-data-collector/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw_bytes = response.read()
    payload = validate_payload(json.loads(raw_bytes.decode("utf-8-sig")))

    canonical_bytes = (
        json.dumps(payload, ensure_ascii=False, indent=2)
        .encode("utf-8")
    )
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    products = sorted({record["product"] for record in payload["data"]})
    downloaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {
        "downloaded_at_utc": downloaded_at,
        "source_url": SOURCE_URL,
        "landing_page_url": LANDING_PAGE_URL,
        "sha256": digest,
        "date_count": len(payload["dates"]),
        "record_count": len(payload["data"]),
        "product_count": len(products),
        "products": products,
        "first_source_month": payload["dates"][0],
        "last_source_month": payload["dates"][-1],
    }

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_temporary = RAW_PATH.with_suffix(".json.tmp")
    manifest_temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    raw_temporary.write_bytes(canonical_bytes)
    manifest_temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    raw_temporary.replace(RAW_PATH)
    manifest_temporary.replace(MANIFEST_PATH)
    return RAW_PATH, MANIFEST_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30)",
    )
    args = parser.parse_args()
    raw_path, manifest_path = download(timeout=args.timeout)
    print(f"Raw data: {raw_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
