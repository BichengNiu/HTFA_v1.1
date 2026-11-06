"""Import provider-confirmed sea entries; positions and unique MMSIs are not events.

Bundles contain manifest.json, events.csv, coverage.csv. Coverage is a provider
declaration of complete days, with independently supplied event counts. No
coverage or zeroes are inferred from the absence of position/event records.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import htfa.monitoring.energy_supply.data.storage as data_store
from htfa.monitoring.energy_supply.data import sea_deliveries as deliveries
from htfa.monitoring.energy_supply.data.sea_delivery import download_bundle
from htfa.monitoring.energy_supply.processing.monitoring_cards import (
    SEA_MONITORING_AREAS,
)

MAX_BYTES = 50 * 1024 * 1024
TZ = ZoneInfo("Asia/Shanghai")
EVENT_COLUMNS = ("sea", "mmsi", "entered_at")
COVERAGE_COLUMNS = ("sea", "date", "status", "event_count")


def archive_path(config=None):
    return data_store.database_path()


def _csv(data, columns):
    reader = csv.DictReader(StringIO(data.decode("utf-8-sig")))
    if not set(columns).issubset(reader.fieldnames or []):
        raise ValueError("历史文件缺少字段：" + ", ".join(columns))
    return list(reader)


def parse_bundle(data):
    """Validate every row before any database mutation; duplicate exports count once."""
    if len(data) > MAX_BYTES:
        raise ValueError("历史ZIP超过50MB，请拆分为多个完整日批次")
    with ZipFile(BytesIO(data)) as bundle:
        required = ("manifest.json", "events.csv", "coverage.csv")
        if any(bundle.namelist().count(name) != 1 for name in required):
            raise ValueError("ZIP必须各包含一个manifest.json、events.csv和coverage.csv")
        if sum(bundle.getinfo(name).file_size for name in required) > MAX_BYTES:
            raise ValueError("解压后的历史文件超过50MB")
        manifest = json.loads(bundle.read("manifest.json"))
        events = _csv(bundle.read("events.csv"), EVENT_COLUMNS)
        coverage = _csv(bundle.read("coverage.csv"), COVERAGE_COLUMNS)
    if (manifest.get("schema_version") != 1 or manifest.get("event_basis") != "sea_entry"
            or manifest.get("timezone") != "Asia/Shanghai"
            or set(manifest.get("seas", [])) != set(SEA_MONITORING_AREAS)):
        raise ValueError("需要四海域进入事件口径及Asia/Shanghai统计日；不能导入AIS位置或去重船只数")
    for key in ("source", "source_url", "definition_id"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f"manifest缺少{key}，须注明供应商及固定海域边界版本")
    if urlparse(manifest["source_url"]).scheme != "https":
        raise ValueError("source_url必须为供应商的HTTPS来源页")
    if manifest["source"] == "local-ais":
        raise ValueError("local-ais是本地观测保留名称，不能作为交付供应商")
    today = datetime.now(TZ).date()
    cells = {}
    for row in coverage:
        sea, day = row["sea"], date.fromisoformat(row["date"])
        if sea not in SEA_MONITORING_AREAS or day >= today or row["status"] != "complete":
            raise ValueError("coverage只接受已结束且供应商确认完整的四海域自然日")
        if not re.fullmatch(r"0|[1-9][0-9]*", row["event_count"]):
            raise ValueError("coverage.event_count必须是非负整数")
        cell = (sea, day.isoformat())
        if cell in cells:
            raise ValueError("coverage有重复海域日期")
        cells[cell] = int(row["event_count"])
    if not cells:
        raise ValueError("未提供经过确认的完整日期覆盖，不能计算海域卡")
    clean = set()
    for row in events:
        sea, mmsi = row["sea"], row["mmsi"].strip()
        if sea not in SEA_MONITORING_AREAS or not re.fullmatch(r"[1-9][0-9]{8}", mmsi):
            raise ValueError("events含未知海域或无效九位MMSI")
        entered = datetime.fromisoformat(row["entered_at"].replace("Z", "+00:00"))
        if entered.tzinfo is None or entered.utcoffset() is None:
            raise ValueError("entered_at必须带UTC Z或时区偏移，不能以接收时间替代事件时间")
        day = entered.astimezone(TZ).date().isoformat()
        if (sea, day) not in cells:
            raise ValueError("事件日期没有对应的完整coverage记录")
        clean.add((sea, mmsi, entered.astimezone(timezone.utc).isoformat(), day))
    counts = Counter((row[0], row[3]) for row in clean)
    if any(counts[cell] != count for cell, count in cells.items()):
        raise ValueError("事件数与供应商coverage.event_count不一致，拒绝截断或混合文件")
    return manifest, sorted(clean), cells


def import_bundle(data, path=None):
    """Validate a complete delivery before writing its events atomically."""
    manifest, events, cells = parse_bundle(data)
    return deliveries.save_bundle(data, manifest, events, cells, path)


def read_history(path=None):
    return deliveries.read_history(path)


def sync_source(config):
    data = download_bundle(config, MAX_BYTES)
    return import_bundle(data, archive_path(config)) if data is not None else False


def template_bundle():
    """Empty schema only: no fabricated events or false zero-day coverage."""
    manifest = {"schema_version": 1, "source": "", "source_url": "",
                "definition_id": "", "event_basis": "sea_entry",
                "timezone": "Asia/Shanghai", "seas": list(SEA_MONITORING_AREAS)}
    output = BytesIO()
    with ZipFile(output, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        bundle.writestr("events.csv", ",".join(EVENT_COLUMNS) + "\n")
        bundle.writestr("coverage.csv", ",".join(COVERAGE_COLUMNS) + "\n")
    return output.getvalue()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="导入四海域历史进入事件ZIP")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--database", type=Path, default=archive_path())
    args = parser.parse_args()
    print(json.dumps(import_bundle(args.bundle.read_bytes(), args.database), ensure_ascii=False))
