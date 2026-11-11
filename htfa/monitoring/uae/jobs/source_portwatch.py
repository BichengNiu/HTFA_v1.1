"""IMF PortWatch 日度海运数据（UAE 港口活动 + 全球海峡过境）入库。

数据来源：IMF PortWatch（https://portwatch.imf.org，基于 ArcGIS Hub 发布）。
在线更新从 IMF 官方 ArcGIS 服务获取港口活动和海峡过境数据。

``update()``：从 IMF 港口目录定位 UAE 港口，分页校验官方数据并保存 CSV →
``htfa/monitoring/uae/assets/raw/portwatch/`` 下缓存的 CSV →
逐行解析（列名全量校验防漂移，数值缺失即 fail loud）→ 事务内整表替换：

- ``portwatch_uae_daily``：宽表镜像，主键 (date, portid)，每行一日一港口，
  含 7 类到港次数（portcalls_*）与 7 类进口/7 类出口吨位（import_*/export_*）；
- ``portwatch_chokepoint_daily``：宽表镜像，主键 (date, portid)，每行一日一海峡，
  含 7 类过境次数（n_*）与 7 类载货容量吨位（capacity_*）。

与 cbuae 等月度源不同，本表保存的是原始日度观测而非抽象指标，以宽表镜像
原样落库，之后按需用 SQL 透视（如全 UAE 每日总到港/总进口、霍尔木兹过境量）。

底库保留所有海峡，报告工作表只提取霍尔木兹（chokepoint6）。UAE 港口与霍尔木兹
合并到单一 sheet ``月度_PortWatch``（每月一行 × 13 指标 = UAE 9 + 霍尔木兹 4）。
写表走
``write_indicator_sheet.ps1``（Excel COM），并在指标字典 sheet 补录指标名；
与其它源一致，数据永远先入 duckdb 再从库读取聚合写 Excel。
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import urllib.request
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlencode

from htfa.monitoring.uae.processing.temporal import last_complete_month_end

from .paths import DATA_DIR


from . import db  # noqa: E402
from ._official_download import write_json_atomic
from ._excel_helpers import (  # noqa: E402
    payload_json_file,
    records_latest_first,
    run_powershell_sheet_writer,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "portwatch"
SOURCE_NAME = "IMF PortWatch (official ArcGIS)"
SOURCE_LABEL = "IMF PortWatch"
FREQUENCY = "日"
FREQUENCY_EXCEL = "月"
INDUSTRY = "海运"

TARGET_SHEET = "月度_PortWatch"
DICTIONARY_SHEET = "指标字典"

# (指标名, 类型, 单位)；类型沿用字典既有取值「数量」
UAE_INDICATORS = (
    ("阿联酋:港口到港总次数:当月值", "数量", "艘次"),
    ("阿联酋:港口集装箱到港次数:当月值", "数量", "艘次"),
    ("阿联酋:港口油轮到港次数:当月值", "数量", "艘次"),
    ("阿联酋:港口进口总量:当月值", "数量", "吨"),
    ("阿联酋:港口集装箱进口量:当月值", "数量", "吨"),
    ("阿联酋:港口油轮进口量:当月值", "数量", "吨"),
    ("阿联酋:港口出口总量:当月值", "数量", "吨"),
    ("阿联酋:港口集装箱出口量:当月值", "数量", "吨"),
    ("阿联酋:港口油轮出口量:当月值", "数量", "吨"),
)
# 海峡侧只保留霍尔木兹（chokepoint6），指标名加「霍尔木兹:」前缀自明
CHOKEPOINT_INDICATORS = (
    ("霍尔木兹:过境总次数:当月值", "数量", "艘次"),
    ("霍尔木兹:载货容量:当月值", "数量", "吨"),
    ("霍尔木兹:油轮过境次数:当月值", "数量", "艘次"),
    ("霍尔木兹:油轮载货容量:当月值", "数量", "吨"),
)
ALL_INDICATORS = UAE_INDICATORS + CHOKEPOINT_INDICATORS


@dataclass
class Observation:
    """一次月度聚合观测（每月一行：UAE 9 + 霍尔木兹 4 个指标值）。"""

    period: str
    values: tuple

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
)
_ARCGIS_ATTEMPTS = 10
_ARCGIS_TIMEOUT = 45
_ARCGIS_REQUESTS = BoundedSemaphore(8)

ARCGIS_BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTS_SERVICE = f"{ARCGIS_BASE}/Daily_Ports_Data/FeatureServer/0"
CHOKEPOINT_SERVICE = f"{ARCGIS_BASE}/Daily_Chokepoints_Data/FeatureServer/0"
PORTS_REFERENCE = f"{ARCGIS_BASE}/PortWatch_ports_database/FeatureServer/0"
CHOKEPOINT_REFERENCE = f"{ARCGIS_BASE}/PortWatch_chokepoints_database/FeatureServer/0"
HUB_DATASETS = {
    PORTS_SERVICE: "83b1bbc7b3354c5fb1f40673bb8f852e",
    CHOKEPOINT_SERVICE: "3da2b9ca97684916b75c4013f95d18ab",
}
HUB_DATASET_API = "https://hub.arcgis.com/api/v3/datasets/"

UAE_FILE = RAW_DIR / "uae_daily_port_activity.csv"
CHOKEPOINT_FILE = RAW_DIR / "chokepoint_transit_calls.csv"

# 期望列名（全量校验；来源改列即 fail loud，防止静默错列）
UAE_REQUIRED_COLUMNS = (
    "date", "portid", "portname", "country", "ISO3",
    "portcalls_container", "portcalls_dry_bulk", "portcalls_general_cargo",
    "portcalls_roro", "portcalls_tanker", "portcalls_cargo", "portcalls",
    "import_container", "import_dry_bulk", "import_general_cargo",
    "import_roro", "import_tanker", "import_cargo", "import",
    "export_container", "export_dry_bulk", "export_general_cargo",
    "export_roro", "export_tanker", "export_cargo", "export",
)
CHOKEPOINT_REQUIRED_COLUMNS = (
    "date", "portid", "portname",
    "n_container", "n_dry_bulk", "n_general_cargo", "n_roro", "n_tanker",
    "n_cargo", "n_total",
    "capacity_container", "capacity_dry_bulk", "capacity_general_cargo",
    "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity",
)

# 值列（整数计数/吨位）；date/portid/portname 等镜像列单独处理
UAE_VALUE_COLUMNS = tuple(UAE_REQUIRED_COLUMNS[5:])
CHOKEPOINT_VALUE_COLUMNS = tuple(CHOKEPOINT_REQUIRED_COLUMNS[3:])

UAE_STRING_COLUMNS = ("country", "ISO3")

# ---------------------------------------------------------------------------
# 表 DDL（放在本模块，与 dld.* 的先例一致；db.ensure 幂等创建）
# ---------------------------------------------------------------------------

UAE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS detail.portwatch_uae_daily (
    date                DATE    NOT NULL,
    portid              VARCHAR NOT NULL,
    portname            VARCHAR NOT NULL,
    country             VARCHAR NOT NULL,
    iso3                VARCHAR,
    portcalls_container BIGINT,
    portcalls_dry_bulk  BIGINT,
    portcalls_general_cargo BIGINT,
    portcalls_roro      BIGINT,
    portcalls_tanker    BIGINT,
    portcalls_cargo     BIGINT,
    portcalls           BIGINT,
    import_container    BIGINT,
    import_dry_bulk     BIGINT,
    import_general_cargo BIGINT,
    import_roro         BIGINT,
    import_tanker       BIGINT,
    import_cargo        BIGINT,
    import              BIGINT,
    export_container    BIGINT,
    export_dry_bulk     BIGINT,
    export_general_cargo BIGINT,
    export_roro         BIGINT,
    export_tanker       BIGINT,
    export_cargo        BIGINT,
    export              BIGINT,
    PRIMARY KEY (date, portid)
)
"""

CHOKEPOINT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS detail.portwatch_chokepoint_daily (
    date                DATE    NOT NULL,
    portid              VARCHAR NOT NULL,
    portname            VARCHAR NOT NULL,
    n_container         BIGINT,
    n_dry_bulk          BIGINT,
    n_general_cargo     BIGINT,
    n_roro              BIGINT,
    n_tanker            BIGINT,
    n_cargo             BIGINT,
    n_total             BIGINT,
    capacity_container  BIGINT,
    capacity_dry_bulk   BIGINT,
    capacity_general_cargo BIGINT,
    capacity_roro       BIGINT,
    capacity_tanker     BIGINT,
    capacity_cargo      BIGINT,
    capacity            BIGINT,
    PRIMARY KEY (date, portid)
)
"""


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def _arcgis_json(service: str, params: dict) -> dict:
    """Read public IMF ``service`` JSON with the supplied query ``params``."""

    for attempt in range(_ARCGIS_ATTEMPTS):
        parameters = dict(params) if service.startswith(HUB_DATASET_API) else {
            "f": "pjson" if attempt % 4 == 3 else "json", **params,
        }
        if "where" in parameters:
            parameters["cacheHint"] = "false"
        use_post = "objectIds" in params or (
            service.endswith("/query") and attempt % 4 >= 2
        )
        headers = {
            "User-Agent": _USER_AGENT, "Accept": "application/json",
            "Cache-Control": "no-cache",
        }
        if use_post:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request_url = service
        if not use_post and parameters:
            request_url += "?" + urlencode(parameters)
        request = urllib.request.Request(
            request_url,
            data=urlencode(parameters).encode("utf-8") if use_post else None,
            headers=headers,
        )
        try:
            with _ARCGIS_REQUESTS, urllib.request.urlopen(
                request, timeout=_ARCGIS_TIMEOUT
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"IMF ArcGIS returned HTTP {response.status}")
                payload = json.loads(response.read())
            if "error" not in payload:
                return payload
            error = payload["error"]
            message = " ".join([
                str(error.get("message", "")),
                *map(str, error.get("details", [])),
            ])
            retryable = error.get("code") in {429, 500, 502, 503, 504} or (
                error.get("code") == 400 and any(text in message for text in (
                    "Invalid URL", "Cannot perform query", "Unable to perform query",
                    "was not found", "does not exist or is inaccessible",
                    "Object reference not set", "service is not available",
                ))
            )
            if not retryable or attempt == _ARCGIS_ATTEMPTS - 1:
                operation = ", ".join(sorted(params)) or "metadata"
                raise RuntimeError(
                    f"IMF ArcGIS query failed at {service} "
                    f"({operation}, where={params.get('where', '')!r}): {error}"
                )
        except HTTPError as exc:
            if (exc.code not in {429, 500, 502, 503, 504}
                    or attempt == _ARCGIS_ATTEMPTS - 1):
                raise
        except (URLError, TimeoutError):
            if attempt == _ARCGIS_ATTEMPTS - 1:
                raise
        time.sleep(min(attempt + 1, 4))
    raise RuntimeError("IMF ArcGIS retries exhausted")


def _arcgis_metadata(service: str) -> dict:
    """Read and verify the official Hub catalog metadata for ``service``."""
    item_id = HUB_DATASETS[service]
    url = HUB_DATASET_API + item_id + "_0"
    payload = _arcgis_json(url, {})
    data = payload.get("data", {})
    attrs = data.get("attributes", {})
    layer = attrs.get("layer", {})
    vintage = layer.get("editingInfo", {}).get("dataLastEditDate")
    if (data.get("id") != item_id + "_0" or attrs.get("errors")
            or attrs.get("access") != "public"
            or attrs.get("owner") != "IMF-portwatch_imf_dataviz"
            or attrs.get("url") != service
            or layer.get("id") != 0 or layer.get("serviceItemId") != item_id
            or type(vintage) is not int or vintage <= 0):
        raise ValueError("IMF ArcGIS Hub metadata identity or source version is invalid")
    return {**layer, "metadata_url": url, "catalog_composed_at": attrs.get("composedAt")}


def _download_arcgis_csv(
    service: str, destination: Path, columns: tuple[str, ...], where: str,
    *, metadata: dict | None = None, force: bool = True, portids: list[str] | None = None,
) -> str:
    """Save ``service`` rows matching ``where`` to ``destination`` using ``columns``.

    Verify schema, pagination, unique keys, stable counts and CSV values before
    atomically replacing the previous cache. All original chokepoints are kept.
    ``metadata`` optionally shares the same service-version snapshot across ports.
    ``force=False`` permits a hash-verified cache of that same official version.
    ``portids`` selects indexed port/year queries, reconciled to the full ID list.
    """

    metadata = _arcgis_metadata(service) if metadata is None else metadata
    fields = {field["name"]: field["type"] for field in metadata["fields"]}
    if missing := set(columns) - fields.keys():
        raise ValueError(f"IMF ArcGIS schema is missing fields: {sorted(missing)}")
    string_columns = UAE_STRING_COLUMNS if "ISO3" in columns else ()
    value_columns = UAE_VALUE_COLUMNS if "ISO3" in columns else CHOKEPOINT_VALUE_COLUMNS
    if not force and _same_version_cache(
        destination, service, where, columns, value_columns, string_columns, metadata
    ):
        return "reused/verified official version"
    oid = next(name for name, kind in fields.items() if kind == "esriFieldTypeOID")
    query = {"where": where}

    inventory_path = destination.with_suffix(".ids.json")
    version = metadata["editingInfo"]["dataLastEditDate"]

    def parse_inventory(payload) -> list[int]:
        ids = payload.get("objectIds")
        if (not isinstance(ids, list) or not ids
                or any(type(value) is not int or value < 0 for value in ids)
                or len(ids) != len(set(ids))
                or payload.get("exceededTransferLimit", False)
                or payload.get("objectIdFieldName", oid) != oid):
            raise ValueError("IMF ArcGIS returned an invalid object ID inventory")
        return sorted(ids)

    def object_ids(*, reuse: bool = False) -> list[int]:
        if reuse:
            try:
                saved = json.loads(inventory_path.read_text(encoding="utf-8"))
                content = json.dumps(saved["ids"]).encode()
                if (saved["service"] == service and saved["where"] == where
                        and saved["version"] == version
                        and saved["sha256"] == hashlib.sha256(content).hexdigest()):
                    return parse_inventory({
                        "objectIds": saved["ids"], "objectIdFieldName": saved["oid"],
                    })
            except (OSError, ValueError, KeyError, TypeError):
                pass
        ids = parse_inventory(_arcgis_json(
            service + "/query", {**query, "returnIdsOnly": "true"}
        ))
        write_json_atomic(inventory_path, {
            "service": service, "where": where, "version": version, "oid": oid,
            "ids": ids, "sha256": hashlib.sha256(json.dumps(ids).encode()).hexdigest(),
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        return ids

    ids = object_ids(reuse=not force)
    print(f"[portwatch] {where}: verified {len(ids)} object IDs", flush=True)
    expected = _arcgis_json(service + "/query", {
        **query, "returnCountOnly": "true", "returnGeometry": "false",
    })["count"]
    if not isinstance(expected, int) or expected <= 0:
        raise ValueError("IMF ArcGIS returned an empty dataset")
    if expected != len(ids):
        raise ValueError("IMF ArcGIS object ID inventory disagrees with row count")
    page_size = min(int(metadata.get("maxRecordCount", 1000)), 100 if where == "1=1" else 500)
    if page_size <= 0:
        raise ValueError("IMF ArcGIS returned an invalid page size")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    offset = 0
    previous_oid = -1
    seen = set()
    seen_oids = set()
    allowed_ids = set(ids)

    def fetch_batch(batch):
        payload = _arcgis_json(service + "/query", {
            **query, "outFields": "*", "returnGeometry": "false",
            "orderByFields": oid + " ASC", "resultRecordCount": len(batch),
            "objectIds": ",".join(map(str, batch)),
        })
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError("IMF ArcGIS query has no feature array")
        returned_ids = [feature["attributes"][oid] for feature in features]
        if (len(features) != len(batch) or set(returned_ids) != set(batch)
                or payload.get("exceededTransferLimit", False)):
            raise ValueError("IMF ArcGIS pagination is incomplete")
        return sorted(features, key=lambda item: item["attributes"][oid])

    def fetch_year(partition):
        pid, year = partition
        cache = destination.parent / (destination.stem + "_years")
        cache.mkdir(parents=True, exist_ok=True)
        cache_path = cache / f"{pid}_{year}.json"
        version = metadata["editingInfo"]["dataLastEditDate"]

        def validate(features, inventory):
            returned = [feature["attributes"][oid] for feature in features]
            if (len(returned) != len(set(returned)) or set(returned) != set(inventory)
                    or not set(returned) <= allowed_ids):
                raise ValueError(f"IMF ArcGIS port/year ID inventory mismatch: {pid}/{year}")
            for feature in features:
                row = feature["attributes"]
                day = (
                    datetime.fromtimestamp(row["date"] / 1000, timezone.utc).date()
                    if type(row["date"]) in (int, float)
                    else date.fromisoformat(str(row["date"])[:10])
                )
                if row["portid"] != pid or row.get("year") != year or day.year != year:
                    raise ValueError("IMF ArcGIS returned rows outside the requested port/year")

        if not force:
            try:
                saved = json.loads(cache_path.read_text(encoding="utf-8"))
                content = json.dumps(saved["features"], sort_keys=True).encode()
                if (saved["service"] == service and saved["version"] == version
                        and saved["portid"] == pid and saved["year"] == year
                        and saved["features"] and not saved.get("requires_refresh", False)
                        and saved["sha256"] == hashlib.sha256(content).hexdigest()):
                    validate(saved["features"], saved["ids"])
                    return saved["features"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        query = {"where": f"year={year} AND portid='{pid}'"}
        payload = _arcgis_json(service + "/query", {
            **query, "outFields": "*",
            "returnGeometry": "false", "resultRecordCount": metadata["maxRecordCount"],
        })
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError(f"IMF ArcGIS port/year query has no feature array: {pid}/{year}")
        if payload.get("exceededTransferLimit", False):
            raise ValueError("IMF ArcGIS port/year query exceeded the transfer limit")
        features = sorted(features, key=lambda item: item["attributes"][oid])
        year_ids = [feature["attributes"][oid] for feature in features]
        validate(features, year_ids)
        if features:
            write_json_atomic(cache_path, {
                "service": service, "version": version, "portid": pid, "year": year,
                "ids": year_ids, "features": features,
                "sha256": hashlib.sha256(json.dumps(features, sort_keys=True).encode()).hexdigest(),
            })
        return features

    try:
        with ThreadPoolExecutor(max_workers=8 if where == "1=1" else 1) as pages, temporary.open(
            "w", encoding="utf-8", newline=""
        ) as output:
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            if portids is not None:
                if "year" not in fields:
                    raise ValueError("IMF ArcGIS schema is missing the year partition field")
                # The documented dataset begins in 2019. Reconciliation with
                # the unfiltered ID inventory catches any out-of-range rows.
                jobs = (
                    (pid, year)
                    for pid in portids
                    for year in range(2019, date.today().year + 1)
                )
                fetch = fetch_year
            else:
                jobs = (ids[start:start + page_size] for start in range(0, expected, page_size))
                fetch = fetch_batch
            errors = []
            if portids is not None:
                futures = [pages.submit(fetch, job) for job in jobs]

                def completed():
                    for future in as_completed(futures):
                        try:
                            yield future.result()
                        except Exception as exc:
                            errors.append(exc)
                results = completed()
            else:
                results = pages.map(fetch, jobs)
            for features in results:
                for feature in features:
                    attributes = feature["attributes"]
                    current_oid = attributes[oid]
                    if (current_oid in seen_oids or current_oid not in allowed_ids
                            or (portids is None and current_oid <= previous_oid)):
                        raise ValueError("IMF ArcGIS repeated or unordered object IDs")
                    seen_oids.add(current_oid)
                    previous_oid = current_oid
                    row = {column: attributes[column] for column in columns}
                    if isinstance(row["date"], (int, float)) and not isinstance(row["date"], bool):
                        row["date"] = datetime.fromtimestamp(
                            row["date"] / 1000, timezone.utc
                        ).date().isoformat()
                    key = (row["date"], row["portid"])
                    if key in seen:
                        raise ValueError("IMF ArcGIS returned duplicate date/port keys")
                    seen.add(key)
                    writer.writerow(row)
                offset += len(features)
                if offset == expected or (features and portids is not None) or offset % 10000 == 0:
                    print(f"[portwatch] {where}: {offset}/{expected} rows", flush=True)
            if errors:
                raise errors[0]
        final_count = _arcgis_json(
            service + "/query",
            {**query, "returnCountOnly": "true", "returnGeometry": "false"},
        )["count"]
        if (offset != expected or final_count != expected or object_ids() != ids
                or seen_oids != allowed_ids):
            if portids is not None:
                cache = destination.parent / (destination.stem + "_years")
                for cache_path in cache.glob("*.json"):
                    saved = json.loads(cache_path.read_text(encoding="utf-8"))
                    if saved.get("version") == metadata["editingInfo"]["dataLastEditDate"]:
                        saved["requires_refresh"] = True
                        write_json_atomic(cache_path, saved)
            raise ValueError("IMF ArcGIS rows or object IDs changed during download")
        parsed = parse_portwatch_csv(
            temporary, columns, value_columns, string_columns=string_columns
        )
        partition = re.fullmatch(r"portid='([^']+)'", where)
        if partition and any(row["portid"] != partition[1] for row in parsed):
            raise ValueError("IMF ArcGIS returned rows outside the requested port")
        temporary.replace(destination)
        write_json_atomic(destination.with_suffix(".source.json"), {
            "service": service, "where": where, "rows": expected,
            "pagination": "objectIds/port-year" if portids is not None else "objectIds",
            "object_id_field": oid,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "editing_info": metadata.get("editingInfo"),
            "metadata_url": metadata.get("metadata_url"),
            "catalog_composed_at": metadata.get("catalog_composed_at"),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        })
    finally:
        temporary.unlink(missing_ok=True)
    return "downloaded/IMF ArcGIS"


def _same_version_cache(path, service, where, columns, value_columns, string_columns, metadata):
    """Verify cached ``path`` against the live official ``metadata`` version."""
    try:
        manifest = json.loads(path.with_suffix(".source.json").read_text(encoding="utf-8"))
        version = metadata.get("editingInfo", {}).get("dataLastEditDate")
        if (version is None or manifest.get("service") != service
                or manifest.get("where") != where
                or manifest.get("pagination") not in {"objectIds", "objectIds/port-year"}
                or manifest.get("editing_info", {}).get("dataLastEditDate") != version
                or manifest.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest()):
            return False
        rows = parse_portwatch_csv(path, columns, value_columns, string_columns=string_columns)
        partition = re.fullmatch(r"portid='([^']+)'", where)
        return (len(rows) == manifest.get("rows")
                and len({(row["date"], row["portid"]) for row in rows}) == len(rows)
                and (not partition or all(row["portid"] == partition[1] for row in rows)))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def parse_portwatch_csv(
    path: Path,
    required_columns: tuple[str, ...],
    value_columns: tuple[str, ...],
    *,
    string_columns: tuple[str, ...] = (),
) -> list[dict]:
    """解析 PortWatch CSV 为入库行字典列表。

    - 列名必须与 required_columns 完全一致（顺序不限），缺列即抛错；
    - date 容忍 "YYYY-MM-DD HH:MM:SS+00:00" 形式，取前 10 位；
    - 所有数值列为十进制整数，空值/非数即抛错（fail loud，防静默错数）；
    - string_columns 中的列按原文本镜像（strip），如 country / ISO3。
    """

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path.name}: 空 CSV（无表头）")
        missing = [name for name in required_columns if name not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"{path.name}: 缺少必需列 {missing}（实际表头 {reader.fieldnames}）"
            )
        rows: list[dict] = []
        for line_number, record in enumerate(reader, start=2):
            raw_date = (record["date"] or "").strip()
            try:
                day = date.fromisoformat(raw_date[:10])
            except ValueError as exc:
                raise ValueError(
                    f"{path.name}: 第 {line_number} 行日期非法 {raw_date!r}"
                ) from exc
            row: dict = {
                "date": day,
                "portid": record["portid"],
                "portname": record["portname"],
            }
            for column in string_columns:
                row[column] = (record[column] or "").strip()
            for column in value_columns:
                raw = (record[column] or "").strip()
                try:
                    row[column] = int(raw)
                except ValueError as exc:
                    raise ValueError(
                        f"{path.name}: 第 {line_number} 行列 {column} 非整数 {raw!r}"
                    ) from exc
            if row["portid"] in {"", None}:
                raise ValueError(f"{path.name}: 第 {line_number} 行 portid 为空")
            rows.append(row)
    if not rows:
        raise ValueError(f"{path.name}: CSV 无数据行")
    return rows


# ---------------------------------------------------------------------------
# 入库 / 写表
# ---------------------------------------------------------------------------


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载（或复用缓存）→ 解析 → 事务内整表替换两张 PortWatch 宽表。"""

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if skip_download:
        missing = [
            str(path) for path in (UAE_FILE, CHOKEPOINT_FILE) if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "skip_download 模式下缺少缓存文件: " + "; ".join(missing)
            )
        uae_state = chokepoint_state = "reused"
    else:
        registry = _arcgis_json(PORTS_REFERENCE + "/query", {
            "where": "ISO3='ARE'", "outFields": "portid,ISO3",
            "returnGeometry": "false",
        })
        attributes = [feature["attributes"] for feature in registry.get("features", [])]
        portids = sorted(row["portid"] for row in attributes)
        if (not portids or len(set(portids)) != len(portids)
                or registry.get("exceededTransferLimit", False)
                or any(row["ISO3"] != "ARE" for row in attributes)
                or any(not re.fullmatch(r"port\d+", pid) for pid in portids)):
            raise ValueError("IMF UAE port registry is incomplete or invalid")
        choke_registry = _arcgis_json(CHOKEPOINT_REFERENCE + "/query", {
            "where": "1=1", "outFields": "portid", "returnGeometry": "false",
        })
        choke_ids = sorted(
            row["attributes"]["portid"] for row in choke_registry.get("features", [])
        )
        if (not choke_ids or len(set(choke_ids)) != len(choke_ids)
                or choke_registry.get("exceededTransferLimit", False)
                or any(not re.fullmatch(r"chokepoint\d+", pid) for pid in choke_ids)):
            raise ValueError("IMF chokepoint registry is incomplete or invalid")
        # Keep ports on their selective indexes. Reconcile chokepoint/year
        # partitions against one complete, unfiltered object ID inventory.
        cache = RAW_DIR / "arcgis"
        cache.mkdir(parents=True, exist_ok=True)
        groups = [
            (PORTS_SERVICE, UAE_FILE, UAE_REQUIRED_COLUMNS, portids,
             [(pid, f"portid='{pid}'") for pid in portids]),
            (CHOKEPOINT_SERVICE, CHOKEPOINT_FILE, CHOKEPOINT_REQUIRED_COLUMNS, choke_ids,
             [("chokepoints_all", "1=1")]),
        ]
        service_metadata = {
            service: _arcgis_metadata(service) for service, *_ in groups
        }
        errors = []
        states = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_download_arcgis_csv, service, cache / f"{key}.csv",
                            columns, where,
                            metadata=service_metadata[service], force=force,
                            portids=ids if service == CHOKEPOINT_SERVICE else None): key
                for service, destination, columns, ids, partitions in groups
                for key, where in partitions
            }
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    states[pid] = future.result()
                    print(f"[portwatch] {pid}: verified ({states[pid]})", flush=True)
                except Exception as exc:
                    errors.append(f"{pid}: {exc}")
                    print(f"[portwatch] {pid}: failed: {exc}", flush=True)
        if errors:
            raise RuntimeError("IMF ArcGIS partitions failed: " + "; ".join(errors))
        for service, destination, columns, ids, partitions in groups:
            vintages = {
                json.loads((cache / f"{key}.source.json").read_text(encoding="utf-8"))["editing_info"].get(
                    "dataLastEditDate"
                ) for key, _ in partitions
            }
            if len(vintages) != 1 or None in vintages:
                raise ValueError("IMF ArcGIS partitions have inconsistent source vintages")
            final_metadata = _arcgis_metadata(service)
            if final_metadata.get("editingInfo", {}).get("dataLastEditDate") != next(iter(vintages)):
                raise ValueError("IMF ArcGIS source vintage changed during download")
            actual_ports = set()
            for key, _ in partitions:
                with (cache / f"{key}.csv").open(encoding="utf-8", newline="") as part:
                    actual_ports.update(row["portid"] for row in csv.DictReader(part))
            if actual_ports != set(ids):
                raise ValueError("IMF ArcGIS downloaded ports disagree with the registry")

        for service, destination, columns, ids, partitions in groups:
            temporary = destination.with_suffix(".csv.tmp")
            try:
                with temporary.open("w", encoding="utf-8", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=columns)
                    writer.writeheader()
                    for key, _ in partitions:
                        with (cache / f"{key}.csv").open(encoding="utf-8", newline="") as part:
                            writer.writerows(csv.DictReader(part))
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
            write_json_atomic(destination.with_suffix(".source.json"), {
                "service": service, "portids": ids,
                "dataLastEditDate": service_metadata[service]["editingInfo"]["dataLastEditDate"],
                "pagination": "objectIds",
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            })
        uae_state, chokepoint_state = (
            ", ".join(sorted({states[key] for key, _ in partitions}))
            for *_, partitions in groups
        )

    uae_rows = parse_portwatch_csv(
        UAE_FILE,
        UAE_REQUIRED_COLUMNS,
        UAE_VALUE_COLUMNS,
        string_columns=UAE_STRING_COLUMNS,
    )
    chokepoint_rows = parse_portwatch_csv(
        CHOKEPOINT_FILE, CHOKEPOINT_REQUIRED_COLUMNS, CHOKEPOINT_VALUE_COLUMNS
    )

    db.ensure(con, "detail.portwatch_uae_daily", UAE_TABLE_DDL)
    db.ensure(con, "detail.portwatch_chokepoint_daily", CHOKEPOINT_TABLE_DDL)

    if any(row.get("ISO3", row.get("iso3")) != "ARE" for row in uae_rows):
        raise ValueError("IMF UAE port data contains a different country")
    for table, rows in (
        ("detail.portwatch_uae_daily", uae_rows),
        ("detail.portwatch_chokepoint_daily", chokepoint_rows),
    ):
        old_keys = set(con.execute(f"SELECT date,portid FROM {table}").fetchall())
        new_keys = {(row["date"], row["portid"]) for row in rows}
        if old_keys - new_keys:
            raise ValueError(f"{table}: official download would remove historical keys")

    with db.transaction(con):
        db.replace(con, "detail.portwatch_uae_daily", uae_rows)
        db.replace(con, "detail.portwatch_chokepoint_daily", chokepoint_rows)

    uae_dates = sorted({row["date"] for row in uae_rows})
    chokepoint_dates = sorted({row["date"] for row in chokepoint_rows})
    note = (
        f"UAE {len(uae_rows)} 行 × {len({r['portid'] for r in uae_rows})} 港口 "
        f"({uae_dates[0]} 至 {uae_dates[-1]})；"
        f"海峡 {len(chokepoint_rows)} 行 × {len({r['portid'] for r in chokepoint_rows})} 个 "
        f"({chokepoint_dates[0]} 至 {chokepoint_dates[-1]})；"
        f"UAE 文件 {uae_state}，海峡文件 {chokepoint_state}"
    )
    return {
        "status": "ok",
        "rows": len(uae_rows) + len(chokepoint_rows),
        "note": note,
    }


def _monthly_observations(con) -> list["Observation"]:
    """从两张日度宽表按月聚合，合并为每月一行的观测列表。

    UAE 部分：9 个指标 = 总/集装箱/油轮 到港次数 + 进口/出口吨位（三类）。
    海峡部分：只取霍尔木兹（chokepoint6），4 个指标 = 过境总次数、载货容量、
    油轮过境次数、油轮载货容量；按月份与 UAE 合并（缺失月份补 None）。
    """

    max_dates = [
        row[0]
        for row in con.execute(
            """
            SELECT max(date) FROM detail.portwatch_uae_daily
            UNION ALL
            SELECT max(date) FROM detail.portwatch_chokepoint_daily
            WHERE portid = 'chokepoint6'
            """
        ).fetchall()
        if row[0] is not None
    ]
    cutoffs = [
        cutoff
        for cutoff in (
            last_complete_month_end(observed_through)
            for observed_through in max_dates
        )
        if cutoff is not None
    ]
    if not cutoffs:
        return []
    # UAE 港口与霍尔木兹必须使用共同完整月份，避免一行月度数据混入
    # 两个不同的覆盖边界。
    cutoff = min(cutoffs)

    uae_rows = con.execute(
        """
        SELECT strftime(date_trunc('month', date), '%Y-%m') AS month,
               SUM(portcalls) AS v0,
               SUM(portcalls_container) AS v1,
               SUM(portcalls_tanker) AS v2,
               SUM(import) AS v3,
               SUM(import_container) AS v4,
               SUM(import_tanker) AS v5,
               SUM(export) AS v6,
               SUM(export_container) AS v7,
               SUM(export_tanker) AS v8
        FROM detail.portwatch_uae_daily
        WHERE date <= ?
        GROUP BY month
        ORDER BY month
        """,
        [cutoff],
    ).fetchall()
    hormuz_rows = con.execute(
        """
        SELECT strftime(date_trunc('month', date), '%Y-%m') AS month,
               SUM(n_total) AS v0,
               SUM(capacity) AS v1,
               SUM(n_tanker) AS v2,
               SUM(capacity_tanker) AS v3
        FROM detail.portwatch_chokepoint_daily
        WHERE portid = 'chokepoint6'
          AND date <= ?
        GROUP BY month
        ORDER BY month
        """,
        [cutoff],
    ).fetchall()
    hormuz_by_month = {row[0]: tuple(row[1:]) for row in hormuz_rows}
    return [
        Observation(
            period=row[0],
            values=tuple(row[1:]) + hormuz_by_month.get(row[0], (None,) * 4),
        )
        for row in uae_rows
    ]


def _sheet_payload(
    observations: list["Observation"],
) -> dict:
    """构造 write_indicator_sheet.ps1 的 payload（含指标字典同步信息）。"""

    return {
        "source_label": SOURCE_LABEL,
        "number_format": "#,##0",
        "column_width": 42,
        "period_format": "month",
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": FREQUENCY_EXCEL,
        "unit": "",
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {"name": name, "type": indicator_type, "industry": INDUSTRY, "unit": unit}
            for name, indicator_type, unit in ALL_INDICATORS
        ],
        "records": records_latest_first(observations),
    }


def merge(workbook_path: Path) -> dict:
    """把 PortWatch 日度数据按月聚合，写回 月度_PortWatch（UAE 9 + 霍尔木兹 4 指标）。

    数据全部从 uae.duckdb 读取（先 duckdb 后 Excel）；每次调用重建该 sheet，
    写表走
    write_indicator_sheet.ps1（Excel COM），失败即抛错。
    """

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_indicator_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    con = db.connect(read_only=True)
    try:
        observations = _monthly_observations(con)
    finally:
        con.close()
    if not observations:
        raise ValueError("portwatch_uae_daily is empty; nothing to merge")

    payload = _sheet_payload(observations)
    with payload_json_file(
        payload,
        prefix=".portwatch-sheet-",
        directory=DATA_DIR,
    ) as payload_path:
        run_powershell_sheet_writer(
            helper_path, workbook_path, payload_path, TARGET_SHEET
        )

    return {
        "status": "ok",
        "note": (
            f"{len(observations)} 个月 × {len(ALL_INDICATORS)} 指标写入 "
            f"{TARGET_SHEET}（{observations[0].period} 至 {observations[-1].period}）；"
        ),
    }
