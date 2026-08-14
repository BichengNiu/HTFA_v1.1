"""Clean MEsteel range quotes and merge historical origin segments by product."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, NamedTuple


BASE_DIR = Path(__file__).resolve().parent
RAW_PATH = BASE_DIR / "raw" / "mesteel_monthly_prices.json"
PROCESSED_DIR = BASE_DIR / "processed"
LONG_PATH = PROCESSED_DIR / "mesteel_monthly_long.csv"
WIDE_PATH = PROCESSED_DIR / "mesteel_monthly_midpoint_wide.csv"
QUALITY_PATH = PROCESSED_DIR / "quality_report.json"
SOURCE_NAME = "MEsteel"
SOURCE_BASIS = "CFR/CPT UAE"
UNIT = "美元/吨"


class Product(NamedTuple):
    code: str
    english: str
    chinese: str

    @property
    def indicator_name(self) -> str:
        return (
            f"阿联酋:钢材进口报价:{self.chinese}:"
            "CFR/CPT:区间中值"
        )


PRODUCTS = (
    Product("billets_blooms", "Billets Blooms", "钢坯及方坯"),
    Product("reinforcing_bars", "Reinforcing Bars", "螺纹钢"),
    Product("angles", "Angles", "角钢"),
    Product("beams_jis", "Beams (JIS-Sizes)", "JIS规格型钢梁"),
    Product(
        "beams_channels_en",
        "Beams - Channels (EN + UB/UC)",
        "EN及UB/UC型钢梁和槽钢",
    ),
    Product("wire_rod", "Wire Rod", "线材"),
    Product("hot_rolled_plates", "Hot Rolled Plates", "热轧钢板"),
    Product("hot_rolled_coils_3mm", "Hot Rolled Coils, 3mm", "3mm热轧卷"),
    Product("cold_rolled_coils_1mm", "Cold Rolled Coils, 1mm", "1mm冷轧卷"),
    Product(
        "hdg_hr_2mm_275",
        "Hot Dip Galv. Coils, HR base, 2mm, 275g/m2",
        "2mm热基热镀锌卷(275g/m2)",
    ),
    Product(
        "hdg_cr_1mm_275",
        "Hot Dip Galv. Coils, CR base, 1mm, 275g/m2",
        "1mm冷基热镀锌卷(275g/m2)",
    ),
    Product(
        "prepainted_galv_035mm_90",
        "Prepainted Galv. Coils 0.35mm 90g",
        "0.35mm预涂镀锌卷(90g)",
    ),
    Product("tinplate_032mm", "Tinplate 0.32MM", "0.32mm马口铁"),
    Product(
        "stainless_hr_304",
        "Stainless HR Coils 304 base",
        "304基价不锈钢热轧卷",
    ),
    Product(
        "stainless_hr_316l",
        "Stainless HR Coils 316L base",
        "316L基价不锈钢热轧卷",
    ),
)
PRODUCT_BY_ENGLISH = {product.english: product for product in PRODUCTS}
NUMBER_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def parse_quote(value: Any) -> tuple[float, float, float]:
    """Return low, high and midpoint for a scalar or range quote."""
    text = str(value).strip().replace(",", "")
    numbers = [float(item) for item in NUMBER_PATTERN.findall(text)]
    if len(numbers) == 1:
        low = high = numbers[0]
    elif len(numbers) == 2:
        low, high = numbers
    else:
        raise ValueError(f"Unsupported MEsteel quote: {value!r}")
    if low > high:
        raise ValueError(f"MEsteel quote has descending bounds: {value!r}")
    return low, high, (low + high) / 2


def month_end(source_date: str) -> str:
    parsed = datetime.strptime(source_date, "%Y-%m-%d").date()
    last_day = monthrange(parsed.year, parsed.month)[1]
    return date(parsed.year, parsed.month, last_day).isoformat()


def load_payload(path: Path = RAW_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload.get("dates"), list):
        raise ValueError("Raw MEsteel payload has no dates list")
    if not isinstance(payload.get("data"), list):
        raise ValueError("Raw MEsteel payload has no data list")
    return payload


def clean_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Create long records, a midpoint wide table and quality statistics."""
    source_products = {record["product"] for record in payload["data"]}
    segment_counts = Counter(record["product"] for record in payload["data"])
    expected_products = set(PRODUCT_BY_ENGLISH)
    unknown = sorted(source_products - expected_products)
    missing = sorted(expected_products - source_products)
    if unknown or missing:
        raise ValueError(
            "MEsteel product catalogue changed; "
            f"unknown={unknown}, missing={missing}"
        )

    long_rows: list[dict[str, Any]] = []
    values_by_month: dict[str, dict[str, float]] = defaultdict(dict)
    seen_product_month: set[tuple[str, str]] = set()
    coverage: dict[str, dict[str, Any]] = {}

    for record in payload["data"]:
        product = PRODUCT_BY_ENGLISH[record["product"]]
        origin = str(record["origin"]).strip()
        for source_month, raw_quote in record["prices"].items():
            if raw_quote in (None, "", "-"):
                continue
            key = (product.code, source_month)
            if key in seen_product_month:
                raise ValueError(
                    "Overlapping MEsteel origin segments for "
                    f"{product.english} in {source_month}"
                )
            seen_product_month.add(key)
            low, high, midpoint = parse_quote(raw_quote)
            period_end = month_end(source_month)
            values_by_month[period_end][product.indicator_name] = midpoint
            long_rows.append(
                {
                    "month_end": period_end,
                    "source_month": source_month,
                    "product_code": product.code,
                    "product_en": product.english,
                    "product_zh": product.chinese,
                    "indicator_name": product.indicator_name,
                    "origin": origin,
                    "quote_text": str(raw_quote).strip(),
                    "low_usd_per_mt": low,
                    "high_usd_per_mt": high,
                    "midpoint_usd_per_mt": midpoint,
                    "currency": "USD",
                    "unit": "metric tonne",
                    "basis": SOURCE_BASIS,
                }
            )

    long_rows.sort(key=lambda row: (row["month_end"], row["product_code"]))
    wide_rows = []
    for period_end in sorted(values_by_month, reverse=True):
        row: dict[str, Any] = {"month_end": period_end}
        for product in PRODUCTS:
            row[product.indicator_name] = values_by_month[period_end].get(
                product.indicator_name
            )
        wide_rows.append(row)

    for product in PRODUCTS:
        rows = [
            row for row in long_rows if row["product_code"] == product.code
        ]
        coverage[product.code] = {
            "product_en": product.english,
            "product_zh": product.chinese,
            "indicator_name": product.indicator_name,
            "observation_count": len(rows),
            "first_month": rows[0]["source_month"],
            "last_month": rows[-1]["source_month"],
            "origin_segment_count": segment_counts[product.english],
        }

    quality = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": SOURCE_NAME,
        "basis": SOURCE_BASIS,
        "workbook_unit": UNIT,
        "raw_date_count": len(payload["dates"]),
        "raw_record_count": len(payload["data"]),
        "product_count": len(PRODUCTS),
        "long_row_count": len(long_rows),
        "wide_row_count": len(wide_rows),
        "first_month": min(row["source_month"] for row in long_rows),
        "last_month": max(row["source_month"] for row in long_rows),
        "overlapping_product_month_count": 0,
        "unparsed_quote_count": 0,
        "coverage": coverage,
    }
    return long_rows, wide_rows, quality


def write_outputs(
    long_rows: list[dict[str, Any]],
    wide_rows: list[dict[str, Any]],
    quality: dict[str, Any],
    *,
    raw_path: Path = RAW_PATH,
) -> tuple[Path, Path, Path]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with LONG_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(long_rows[0]))
        writer.writeheader()
        writer.writerows(long_rows)

    wide_fields = ["month_end"] + [
        product.indicator_name for product in PRODUCTS
    ]
    with WIDE_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=wide_fields)
        writer.writeheader()
        writer.writerows(wide_rows)

    quality["raw_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    quality["long_csv"] = str(LONG_PATH)
    quality["wide_csv"] = str(WIDE_PATH)
    QUALITY_PATH.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return LONG_PATH, WIDE_PATH, QUALITY_PATH


def process(path: Path = RAW_PATH) -> tuple[Path, Path, Path]:
    payload = load_payload(path)
    long_rows, wide_rows, quality = clean_payload(payload)
    return write_outputs(
        long_rows,
        wide_rows,
        quality,
        raw_path=path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=RAW_PATH,
        help=f"Raw JSON path (default: {RAW_PATH})",
    )
    args = parser.parse_args()
    for output in process(args.input):
        print(output)


if __name__ == "__main__":
    main()
