"""IMF PortWatch 日度海运数据（UAE 港口活动 + 全球海峡过境）入库。

数据来源：IMF PortWatch（https://portwatch.imf.org，基于 ArcGIS Hub 发布），
在线更新直接读取 IMF 官方 ArcGIS 服务；HDX 历史镜像：
- "United Arab Emirates: Daily Port Activity Data and Shipment Estimates"
  https://data.humdata.org/dataset/united-arab-emirates-daily-port-activity-data-and-shipment-estimates
  （日度，2019-01-01 至今，全量 CSV：15 个 UAE 港口 × 每日分层到港次数与进出口吨位）
- "Daily Chokepoint Transit Calls and Shipment Volume Estimates"
  https://data.humdata.org/dataset/daily-chokepoint-transit-calls-and-shipment-volume-estimates
  （日度，2019-01-01 至今，全量 CSV：28 个海峡 × 每日分层过境次数与载货容量，
   含霍尔木兹海峡 chokepoint6）

``update()``：从 IMF 港口目录定位 UAE 港口，分页校验官方数据并保存 CSV →
``data/UAE/raw/portwatch/`` 下缓存的 CSV →
逐行解析（列名全量校验防漂移，数值缺失即 fail loud）→ 事务内整表替换：

- ``portwatch_uae_daily``：宽表镜像，主键 (date, portid)，每行一日一港口，
  含 7 类到港次数（portcalls_*）与 7 类进口/7 类出口吨位（import_*/export_*）；
- ``portwatch_chokepoint_daily``：宽表镜像，主键 (date, portid)，每行一日一海峡，
  含 7 类过境次数（n_*）与 7 类载货容量吨位（capacity_*）。

与 cbuae 等月度源不同，本表保存的是原始日度观测而非抽象指标，以宽表镜像
原样落库，之后按需用 SQL 透视（如全 UAE 每日总到港/总进口、霍尔木兹过境量）。

其中替代方案不存在：全部海峡仅保留霍尔木兹（chokepoint6），UAE 港口与霍尔木兹
合并到单一 sheet ``月度_PortWatch``（每月一行 × 13 指标 = UAE 9 + 霍尔木兹 4）。
写表走
``write_indicator_sheet.ps1``（Excel COM），并在指标字典 sheet 补录指标名；
与其它源一致，数据永远先入 duckdb 再从库读取聚合写 Excel。
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from htfa.data.temporal import last_complete_month_end

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
_TIMEOUT = 120

HDX_API = "https://data.humdata.org/api/3/action/package_show"
UAE_PACKAGE_ID = "united-arab-emirates-daily-port-activity-data-and-shipment-estimates"
CHOKEPOINT_PACKAGE_ID = "daily-chokepoint-transit-calls-and-shipment-volume-estimates"
ARCGIS_BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTS_SERVICE = f"{ARCGIS_BASE}/Daily_Ports_Data/FeatureServer/0"
CHOKEPOINT_SERVICE = f"{ARCGIS_BASE}/Daily_Chokepoints_Data/FeatureServer/0"
PORTS_REFERENCE = f"{ARCGIS_BASE}/PortWatch_ports_database/FeatureServer/0"
CHOKEPOINT_REFERENCE = f"{ARCGIS_BASE}/PortWatch_chokepoints_database/FeatureServer/0"

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


def resolve_resource_url(package_id: str) -> str:
    """经 HDX package_show API 解析该数据集第一个资源的下载 URL。"""

    url = f"{HDX_API}?id={package_id}"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    resources = payload.get("result", {}).get("resources") or []
    for resource in resources:
        download_url = resource.get("url")
        if download_url:
            return download_url
    raise ValueError(f"HDX package_show 未发现资源下载 URL: {package_id}")


def _download_to(url: str, destination: Path) -> str:
    """在线下载 URL 到 destination。

    返回 "downloaded"。写临时文件后原子改名，避免半截文件落盘。
    """

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"HDX CSV download returned HTTP {response.status}; "
                    f"WAF action={response.headers.get('x-amzn-waf-action', 'none')}"
                )
            if "html" in response.headers.get("Content-Type", "").lower():
                raise ValueError("HDX CSV download returned an HTML page")
            expected = int(response.headers.get("Content-Length") or 0)
            received = 0
            with open(temporary, "wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    received += len(chunk)
            if not received or (expected and received != expected):
                raise OSError(
                    f"Incomplete HDX CSV download: {received}/{expected} bytes"
                )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return "downloaded"


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def _arcgis_json(service: str, params: dict) -> dict:
    """Read public IMF ``service`` JSON with the supplied query ``params``."""

    for attempt in range(3):
        request = urllib.request.Request(
            service + "?" + urlencode({
                "f": "json" if attempt == 0 else "pjson", **params
            }),
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                if response.status != 200:
                    raise RuntimeError(f"IMF ArcGIS returned HTTP {response.status}")
                payload = json.loads(response.read())
            if "error" not in payload:
                return payload
            error = payload["error"]
            retryable = error.get("code") in {429, 500, 502, 503, 504} or (
                error.get("code") == 400 and error.get("message") in {
                    "Invalid URL", "Cannot perform query. Invalid query parameters."
                }
            )
            if not retryable or attempt == 2:
                raise RuntimeError(f"IMF ArcGIS query failed at {service}: {error}")
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("IMF ArcGIS retries exhausted")


def _download_arcgis_csv(
    service: str, destination: Path, columns: tuple[str, ...], where: str
) -> str:
    """Save ``service`` rows matching ``where`` to ``destination`` using ``columns``.

    Verify schema, pagination, unique keys, stable counts and CSV values before
    atomically replacing the previous cache. All original chokepoints are kept.
    """

    metadata = _arcgis_json(service, {})
    fields = {field["name"]: field["type"] for field in metadata["fields"]}
    if missing := set(columns) - fields.keys():
        raise ValueError(f"IMF ArcGIS schema is missing fields: {sorted(missing)}")
    oid = next(name for name, kind in fields.items() if kind == "esriFieldTypeOID")
    query = {"where": where}
    expected = _arcgis_json(service + "/query", {**query, "returnCountOnly": "true"})["count"]
    if not isinstance(expected, int) or expected <= 0:
        raise ValueError("IMF ArcGIS returned an empty dataset")
    page_size = min(int(metadata.get("maxRecordCount", 1000)), 1000)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    offset = 0
    previous_oid = -1
    seen = set()
    try:
        with temporary.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            while offset < expected:
                payload = _arcgis_json(service + "/query", {
                    # Request the public row as-is, then validate/select the
                    # established CSV schema rather than project reserved names.
                    **query, "outFields": "*",
                    "returnGeometry": "false", "orderByFields": oid + " ASC",
                    "resultOffset": offset, "resultRecordCount": page_size,
                })
                features = payload.get("features", [])
                if not features or len(features) > page_size:
                    raise ValueError("IMF ArcGIS pagination is incomplete")
                for feature in features:
                    attributes = feature["attributes"]
                    current_oid = attributes[oid]
                    if current_oid <= previous_oid:
                        raise ValueError("IMF ArcGIS repeated or unordered object IDs")
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
                if not payload.get("exceededTransferLimit", False) and offset != expected:
                    raise ValueError("IMF ArcGIS stopped before the advertised row count")
        final_count = _arcgis_json(
            service + "/query", {**query, "returnCountOnly": "true"}
        )["count"]
        if offset != expected or final_count != expected:
            raise ValueError("IMF ArcGIS row count changed during download")
        string_columns = UAE_STRING_COLUMNS if "ISO3" in columns else ()
        value_columns = UAE_VALUE_COLUMNS if "ISO3" in columns else CHOKEPOINT_VALUE_COLUMNS
        parsed = parse_portwatch_csv(
            temporary, columns, value_columns, string_columns=string_columns
        )
        partition = re.fullmatch(r"portid='([^']+)'", where)
        if partition and any(row["portid"] != partition[1] for row in parsed):
            raise ValueError("IMF ArcGIS returned rows outside the requested port")
        temporary.replace(destination)
        write_json_atomic(destination.with_suffix(".source.json"), {
            "service": service, "where": where, "rows": expected,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "editing_info": metadata.get("editingInfo"),
        })
    finally:
        temporary.unlink(missing_ok=True)
    return "downloaded/IMF ArcGIS"


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
        # Equality filters use the published portid indexes. Global/IN queries
        # can time out even though individual-port queries work normally.
        cache = RAW_DIR / "arcgis"
        cache.mkdir(parents=True, exist_ok=True)
        groups = [
            (PORTS_SERVICE, UAE_FILE, UAE_REQUIRED_COLUMNS, portids),
            (CHOKEPOINT_SERVICE, CHOKEPOINT_FILE, CHOKEPOINT_REQUIRED_COLUMNS, choke_ids),
        ]
        errors = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_download_arcgis_csv, service, cache / f"{pid}.csv",
                            columns, f"portid='{pid}'"): pid
                for service, destination, columns, ids in groups for pid in ids
            }
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    future.result()
                    print(f"[portwatch] {pid}: verified", flush=True)
                except Exception as exc:
                    errors.append(f"{pid}: {exc}")
                    print(f"[portwatch] {pid}: failed: {exc}", flush=True)
        if errors:
            raise RuntimeError("IMF ArcGIS partitions failed: " + "; ".join(errors))
        for service, destination, columns, ids in groups:
            vintages = {
                json.loads((cache / f"{pid}.source.json").read_text(encoding="utf-8"))["editing_info"].get(
                    "dataLastEditDate"
                ) for pid in ids
            }
            if len(vintages) != 1 or None in vintages:
                raise ValueError("IMF ArcGIS partitions have inconsistent source vintages")
            temporary = destination.with_suffix(".csv.tmp")
            try:
                with temporary.open("w", encoding="utf-8", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=columns)
                    writer.writeheader()
                    for pid in ids:
                        with (cache / f"{pid}.csv").open(encoding="utf-8", newline="") as part:
                            writer.writerows(csv.DictReader(part))
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
            write_json_atomic(destination.with_suffix(".source.json"), {
                "service": service, "portids": ids,
                "dataLastEditDate": next(iter(vintages)),
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            })
        uae_state = chokepoint_state = "downloaded/IMF ArcGIS"

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
