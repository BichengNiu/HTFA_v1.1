"""IMF PortWatch 日度海运数据（UAE 港口活动 + 全球海峡过境）入库。

数据来源：IMF PortWatch（https://portwatch.imf.org，基于 ArcGIS Hub 发布），
原始 CSV 由 HDX（OCHA Humanitarian Data Exchange）每日镜像：
- "United Arab Emirates: Daily Port Activity Data and Shipment Estimates"
  https://data.humdata.org/dataset/united-arab-emirates-daily-port-activity-data-and-shipment-estimates
  （日度，2019-01-01 至今，全量 CSV：15 个 UAE 港口 × 每日分层到港次数与进出口吨位）
- "Daily Chokepoint Transit Calls and Shipment Volume Estimates"
  https://data.humdata.org/dataset/daily-chokepoint-transit-calls-and-shipment-volume-estimates
  （日度，2019-01-01 至今，全量 CSV：28 个海峡 × 每日分层过境次数与载货容量，
   含霍尔木兹海峡 chokepoint6）

``update()``：经 HDX package_show API 解析最新资源下载 URL（失败时回退到
硬编码已知 URL）→ 下载或复用 ``data/UAE/raw/portwatch/`` 下缓存的 CSV →
逐行解析（列名全量校验防漂移，数值缺失即 fail loud）→ 事务内整表替换：

- ``portwatch_uae_daily``：宽表镜像，主键 (date, portid)，每行一日一港口，
  含 7 类到港次数（portcalls_*）与 7 类进口/7 类出口吨位（import_*/export_*）；
- ``portwatch_chokepoint_daily``：宽表镜像，主键 (date, portid)，每行一日一海峡，
  含 7 类过境次数（n_*）与 7 类载货容量吨位（capacity_*）。

与 cbuae 等月度源不同，本表保存的是原始日度观测而非抽象指标，以宽表镜像
原样落库，之后按需用 SQL 透视（如全 UAE 每日总到港/总进口、霍尔木兹过境量）。

其中替代方案不存在：全部海峡仅保留霍尔木兹（chokepoint6），UAE 港口与霍尔木兹
合并到单一 sheet ``月度_PortWatch``（每月一行 × 13 指标 = UAE 9 + 霍尔木兹 4）。
旧「月度_PortWatch_海峡」sheet 在合并时自动删除。写表走
``write_portwatch_sheet.ps1``（Excel COM），并在指标字典 sheet 补录指标名；
与其它源一致，数据永远先入 duckdb 再从库读取聚合写 Excel。
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from htfa.data.temporal import last_complete_month_end

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from ._excel_helpers import (  # noqa: E402
    payload_json_file,
    run_powershell_sheet_writer,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "portwatch"
SOURCE_NAME = "IMF PortWatch (HDX mirror)"
SOURCE_LABEL = "IMF PortWatch"
FREQUENCY = "日"
FREQUENCY_EXCEL = "月"
INDUSTRY = "海运"

TARGET_SHEET = "月度_PortWatch"
LEGACY_SHEETS = ("月度_PortWatch_海峡",)
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

# 硬编码回退 URL（dataset/resource UUID 长期稳定；优先用 API 动态解析）
UAE_FALLBACK_URL = (
    "https://data.humdata.org/dataset/9bdcced2-819a-46c3-8a7e-341a6a2afdf5/"
    "resource/4a338096-912a-40e0-8dfb-aba281929d02/download/"
    "united-arab-emirates-daily-port-activity-data-and-shipment-estimates.csv"
)
CHOKEPOINT_FALLBACK_URL = (
    "https://data.humdata.org/dataset/91d28bb8-986d-430c-961c-6a24ecbd66ee/"
    "resource/cbd17f06-8ab2-4ba4-a666-f7a4bcc9ea3f/download/"
    "daily-chokepoint-transit-calls-and-shipment-volume-estimates.csv"
)

UAE_FILE = RAW_DIR / "uae_daily_port_activity.csv"
CHOKEPOINT_FILE = RAW_DIR / "chokepoint_transit_calls.csv"

# 期望列名（全量校验；HDX 侧改列即 fail loud，防止静默错列）
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


def resolve_resource_url(package_id: str, fallback: str) -> str:
    """经 HDX package_show API 解析该数据集第一个资源的下载 URL。

    API 失败（网络/结构变化）时回退到硬编码 URL，保证管道可继续。
    """

    url = f"{HDX_API}?id={package_id}"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return fallback
    resources = payload.get("result", {}).get("resources") or []
    for resource in resources:
        download_url = resource.get("url") or resource.get("download_url")
        if download_url:
            return download_url
    return fallback


def _download_to(url: str, destination: Path, *, force: bool) -> str:
    """下载 URL 到 destination；文件已存在且非 force 时直接复用。

    返回 "downloaded" / "reused"。写临时文件后原子改名，避免半截文件落盘。
    """

    if destination.is_file() and not force:
        return "reused"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response, \
            open(temporary, "wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    temporary.replace(destination)
    return "downloaded"


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


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

    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
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
        uae_url = resolve_resource_url(UAE_PACKAGE_ID, UAE_FALLBACK_URL)
        chokepoint_url = resolve_resource_url(
            CHOKEPOINT_PACKAGE_ID, CHOKEPOINT_FALLBACK_URL
        )
        # HDX resource URLs are stable and the CSV content is revised in
        # place. Online mode therefore always re-fetches both files;
        # --skip-download remains the explicit offline mode.
        try:
            uae_state = _download_to(uae_url, UAE_FILE, force=True)
        except Exception as exc:  # noqa: BLE001 - valid cache remains usable
            if not UAE_FILE.is_file():
                raise
            uae_state = f"reused_after_error:{exc}"
        try:
            chokepoint_state = _download_to(
                chokepoint_url, CHOKEPOINT_FILE, force=True
            )
        except Exception as exc:  # noqa: BLE001 - valid cache remains usable
            if not CHOKEPOINT_FILE.is_file():
                raise
            chokepoint_state = f"reused_after_error:{exc}"

    uae_rows = parse_portwatch_csv(
        UAE_FILE,
        UAE_REQUIRED_COLUMNS,
        UAE_VALUE_COLUMNS,
        string_columns=UAE_STRING_COLUMNS,
    )
    chokepoint_rows = parse_portwatch_csv(
        CHOKEPOINT_FILE, CHOKEPOINT_REQUIRED_COLUMNS, CHOKEPOINT_VALUE_COLUMNS
    )

    db.ensure(con, "portwatch_uae_daily", UAE_TABLE_DDL)
    db.ensure(con, "portwatch_chokepoint_daily", CHOKEPOINT_TABLE_DDL)

    transaction = con.begin()
    try:
        db.replace(con, "portwatch_uae_daily", uae_rows)
        db.replace(con, "portwatch_chokepoint_daily", chokepoint_rows)
        transaction.commit()
    except BaseException:
        transaction.rollback()
        raise

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


def _serialize_records(observations: list["Observation"]) -> list[dict]:
    """按 period 倒序序列化记录（每月一行，13 个指标值）。"""

    return [
        {
            "period": observation.period,
            "values": [
                None if value is None else float(value)
                for value in observation.values
            ],
        }
        for observation in sorted(
            observations, key=lambda item: item.period, reverse=True
        )
    ]


def _sheet_payload(
    observations: list["Observation"],
) -> dict:
    """构造 write_portwatch_sheet.ps1 的 payload（含指标字典同步信息）。"""

    return {
        "source_label": SOURCE_LABEL,
        "legacy_sheet_names": list(LEGACY_SHEETS),
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": FREQUENCY_EXCEL,
        "unit": "",
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "dimension_label": None,
        "indicators": [
            {"name": name, "type": indicator_type, "industry": INDUSTRY, "unit": unit}
            for name, indicator_type, unit in ALL_INDICATORS
        ],
        "records": _serialize_records(observations),
    }


def merge(workbook_path: Path) -> dict:
    """把 PortWatch 日度数据按月聚合，写回 月度_PortWatch（UAE 9 + 霍尔木兹 4 指标）。

    数据全部从 uae.duckdb 读取（先 duckdb 后 Excel）；每次调用重建该 sheet，
    并删除遗留的旧「月度_PortWatch_海峡」sheet。写表走
    write_portwatch_sheet.ps1（Excel COM），失败即抛错。
    """

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_portwatch_sheet.ps1")
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
            f"旧 {LEGACY_SHEETS[0]} 已删除"
        ),
    }


if __name__ == "__main__":
    print("source_portwatch.py 自检：")
    print("  update(con, force=, skip_download=) 下载/复用 raw/portwatch/*.csv")
    print("    → 解析校验后整表替换 portwatch_uae_daily / portwatch_chokepoint_daily")
    print("  merge(workbook_path) 按月聚合（UAE 全港 + 霍尔木兹）→ 重建 月度_PortWatch")
    print("  本文件直接运行不执行任何下载或工作簿写入。")
