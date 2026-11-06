"""Import provider-confirmed sea entries; positions and unique MMSIs are not events.

Bundles contain manifest.json, events.csv, coverage.csv. Coverage is a provider
declaration of complete days, with independently supplied event counts. No
coverage or zeroes are inferred from the absence of position/event records.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date, datetime, timezone
import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from htfa.monitoring.energy_supply.monitoring_cards import SEA_MONITORING_AREAS
from htfa.monitoring.energy_supply import data_store

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
    manifest, events, cells = parse_bundle(data)
    path = Path(path) if path is not None else archive_path()
    provider, definition = manifest["source"], manifest["definition_id"]
    with data_store.connect(path) as conn:
        previous = conn.execute("SELECT manifest FROM sea_manifests WHERE provider=?", (provider,)).fetchone()
        if previous:
            old = json.loads(previous[0])
            if any(old[key] != manifest[key] for key in ("source", "definition_id", "timezone", "event_basis")):
                raise ValueError("历史库的供应商或海域边界口径不同；请使用独立档案，不能混算同比")
        # Each validated day replaces the earlier delivery atomically; corrected
        # provider reports and repeated uploads do not accumulate duplicates.
        for sea, day in cells:
            conn.execute("DELETE FROM sea_entries WHERE provider=? AND definition=? AND sea=? AND day=?",
                         (provider, definition, sea, day))
        if events:
            conn.executemany("INSERT INTO sea_entries VALUES (?,?,?,?,?,?,?)",
                             [(provider, definition, sea, mmsi, stamp, day, '{}') for sea, mmsi, stamp, day in events])
        conn.executemany("INSERT OR REPLACE INTO sea_coverage VALUES (?,?,?,?,?,?)",
                         [(provider, definition, sea, day, 'complete', count) for (sea, day), count in cells.items()])
        conn.execute("INSERT OR REPLACE INTO sea_manifests VALUES (?,?)",
                     (provider, json.dumps(manifest, ensure_ascii=False)))
        data_store.set_meta("selected_sea_history_provider", provider, conn)
        data_store.bump_revision("sea", conn)
        data_store.put_binary_document("deliveries/sea-" + hashlib.sha256(data).hexdigest() + ".zip", data,
                                       "application/zip", conn)
    return {"events": len(events), "days": len(cells), "source": manifest["source"],
            "sha256": hashlib.sha256(data).hexdigest()}


def read_history(path=None):
    path = Path(path) if path is not None else archive_path()
    if not path.exists():
        return {"rows": [], "source": None, "definition_id": None}
    with data_store.connect(path) as conn:
        provider = data_store.meta("selected_sea_history_provider", conn=conn)
        if not provider:
            return {"rows": [], "source": None, "definition_id": None}
        metadata = conn.execute("SELECT manifest FROM sea_manifests WHERE provider=?", (provider,)).fetchone()
        manifest = json.loads(metadata[0]) if metadata else {}
        rows = [{"sea": sea, "date": day.isoformat(), "passages": count} for sea, day, count in conn.execute(
            "SELECT c.sea,c.day,COUNT(e.entered_at) FROM sea_coverage c "
            "LEFT JOIN sea_entries e ON e.provider=c.provider AND e.definition=c.definition AND e.sea=c.sea AND e.day=c.day "
            "WHERE c.provider=? AND c.status='complete' "
            "GROUP BY c.sea,c.day,c.event_count HAVING COUNT(e.entered_at)=c.event_count ORDER BY c.day,c.sea", (provider,)).fetchall()]
    return {"rows": rows, "source": manifest.get("source"), "definition_id": manifest.get("definition_id")}


def sync_source(config):
    """Read an authorized delivery bundle, not an invented vendor API endpoint."""
    local = config.get("SEA_HISTORY_BUNDLE_PATH")
    url = config.get("SEA_HISTORY_BUNDLE_URL")
    if local and url:
        raise ValueError("只配置一种历史交付来源：本地ZIP或HTTPS ZIP")
    if not local and not url:
        return None
    if local:
        with Path(local).expanduser().open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    else:
        import requests
        if urlparse(url).scheme != "https":
            raise ValueError("历史交付地址必须使用HTTPS")
        token = config.get("SEA_HISTORY_BEARER_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            # Do not forward secret tokens via redirects or print signed URLs.
            with requests.get(url, headers=headers, timeout=(10, 60), stream=True,
                              allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError(f"历史交付源返回HTTP {response.status_code}")
                parts, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("历史ZIP超过50MB")
                    parts.append(chunk)
                data = b"".join(parts)
        except requests.RequestException:
            raise ValueError("历史交付源连接失败，请检查地址、授权与网络") from None
    return import_bundle(data, archive_path(config))


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
