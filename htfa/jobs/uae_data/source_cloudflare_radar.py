"""Cloudflare Radar 阿联酋（AE）网络流量（source_cloudflare_radar.py）——日度入库。

数据来源：Cloudflare Radar API（https://radar.cloudflare.com/）国家级网络流量
日度序列。官方接口需**免费 API Token**（Account → Radar → Read）。

双模式：
1. **API 模式（首选，有 token 时）**：调
   `GET /client/v4/radar/netflows/timeseries?name=ae_netflows&location=AE&dateRange=52w&aggInterval=1d`
   token 从环境变量 `CF_RADAR_TOKEN` 或 `data/UAE/.env` 的 `CF_RADAR_TOKEN=` 行读取；
   原始 JSON 存 `raw/cloudflare_radar/netflows_<yyyyMMdd>.json` 留档。
2. **手动 CSV 模式（无 token 时的回落）**：解析用户从官网 Download CSV 保存的文件
   `data/UAE/raw/cloudflare_radar/uae_http_traffic_daily.csv`（容忍列名变动）。

- 值口径：国家级网络流量（流量字节/包量）相对基准的**百分比变化**，非绝对流量。
  百分比与 HTTP 请求变化量同属 Radar「数字活动」高频代理系列。
- 入库表：`cloudflare_radar_daily`（period, indicator, value, source_file 长表）。
- 目标 sheet：`日度_CloudflareRadar`（经 write_cloudflare_radar_sheet.ps1 重建）。
"""

from __future__ import annotations

import csv
import json
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

from htfa.data.temporal import last_complete_month_end

from .paths import DATA_DIR, SCRIPTS_DIR


import requests  # noqa: E402

from . import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "cloudflare_radar"
RAW_CSV = RAW_DIR / "uae_http_traffic_daily.csv"
TABLE = "cloudflare_radar_daily"
SOURCE_NAME = "Cloudflare Radar (UAE)"
FREQUENCY = "日"
INDUSTRY = "互联网/数字活动"
TARGET_SHEET = "日度_CloudflareRadar"
DICTIONARY_SHEET = "指标字典"
INDICATOR = "阿联酋:Cloudflare Radar网络流量(相对水平%)"
UNIT = "%（窗口内 min-max 归一相对水平）"
KIND = "代理指标"

INDICATOR_W = "阿联酋:Cloudflare Radar网络流量(周度相对水平%)"
UNIT_W = "%（窗口内 min-max 归一相对水平，周均）"
FREQUENCY_W = "周"
TARGET_SHEET_W = "周度_CloudflareRadar"

API_URL = "https://api.cloudflare.com/client/v4/radar/netflows/timeseries"
# 日度粒度 API 保留期约 90 天（90d/1d 可用，120d 及以上被拒退化为周度）；
# 周度可回溯 52 周。此处取日度最大值窗口。
API_PARAMS = {"name": "ae_netflows", "location": "AE", "dateRange": "90d", "aggInterval": "1d"}
API_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    period      DATE           NOT NULL,
    indicator   VARCHAR        NOT NULL,
    value       DECIMAL(12, 3),
    source_file VARCHAR,
    PRIMARY KEY (period, indicator)
)
"""


# ---------------------------------------------------------------------------
# Token / 凭据
# ---------------------------------------------------------------------------


def _load_token() -> str | None:
    """从环境变量或 data/UAE/.env 读取 CF_RADAR_TOKEN（不打印值）。"""
    token = os.environ.get("CF_RADAR_TOKEN")
    if token:
        return token.strip()
    env_path = DATA_DIR / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("CF_RADAR_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


# ---------------------------------------------------------------------------
# 解析（通用）
# ---------------------------------------------------------------------------


def _coerce_number(text: object) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    cleaned = str(text).strip().replace(",", "").replace("%", "").replace("\u00a0", "").replace(" ", "")
    if not cleaned or cleaned.lower() in {"n/a", "na", "null", "-", ""}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(text: object) -> date | None:
    if text is None:
        return None
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    cleaned = str(text).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# API 模式（netflows）
# ---------------------------------------------------------------------------


def _fetch_netflows(token: str, params: dict, dest: Path, label: str) -> dict:
    """调 Radar netflows/timeseries，成功返回 JSON dict 并存原始副本；失败抛 RuntimeError。"""
    resp = requests.get(
        API_URL,
        params=params,
        headers={**API_HEADERS, "Authorization": f"Bearer {token}"},
        timeout=180,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Cloudflare Radar API 请求失败 HTTP {resp.status_code} ({label}): "
            f"{resp.text[:300]}"
        )
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(
            f"Cloudflare Radar API 返回成功=false ({label}): "
            + json.dumps(data.get("errors", []), ensure_ascii=False)[:300]
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def _parse_netflows_json(data: dict) -> tuple[list[tuple[date, float]], dict]:
    """从 netflows timeseries 响应提取 (date, value) 日度序列与 meta。"""
    result = data.get("result") or {}
    series = {k: v for k, v in result.items() if k != "meta"}
    if not series:
        raise ValueError("Cloudflare Radar API 响应里没有 timeseries 序列")
    name = next(iter(series))
    payload = series[name] or {}
    timestamps = payload.get("timestamps") or []
    values = payload.get("values") or []
    meta = result.get("meta") or {}
    normalization = str(meta.get("normalization") or "").lower()
    # Radar netflows 用 MIN0_MAX：窗口内 min-max 归一为 0~1，转百分比 ×100
    x100 = normalization in {"min0_max", "relative", "relative0_1", "relative00"}
    pairs: list[tuple[date, float]] = []
    for ts, val in zip(timestamps, values):
        period = _parse_date(ts)
        value = _coerce_number(val)
        if period is None or value is None:
            continue
        if x100:
            value = value * 100.0
        pairs.append((period, value))
    pairs.sort(key=lambda item: item[0])
    # 同日内多个时间点（罕见的非 1d 聚合）取均值
    collapse: dict[date, list] = {}
    for p, v in pairs:
        collapse.setdefault(p, []).append(v)
    dedup = sorted(
        (p, sum(vs) / len(vs)) for p, vs in collapse.items()
    )
    return dedup, meta


def _api_rows() -> tuple[list[dict], str]:
    """API 拉取：日度（90d/1d）+ 周度（52w/1w）两个粒度，返回合并行与备注。"""
    token = _load_token()
    if not token:
        raise RuntimeError(
            "未找到 CF_RADAR_TOKEN（环境变量或 data/UAE/.env）。"
            "请到 https://dash.cloudflare.com → My Profile → API Tokens 创建免费 "
            "Token（Permissions: Account → Radar → Read），写入 data/UAE/.env：\n"
            "    CF_RADAR_TOKEN=<你的 token>"
        )
    stamp = date.today().strftime("%Y%m%d")
    rows: list[dict] = []
    notes: list[str] = []
    sweeps = [
        (INDICATOR, "日度", {"name": "ae_netflows", "location": "AE", "dateRange": "90d", "aggInterval": "1d"}, "d90"),
        (INDICATOR_W, "周度", {"name": "ae_netflows", "location": "AE", "dateRange": "52w", "aggInterval": "1w"}, "w52"),
    ]
    for indicator, freq, params, suffix in sweeps:
        filename = f"netflows_{stamp}_{suffix}.json"
        dest = RAW_DIR / filename
        data = _fetch_netflows(token, params, dest, freq)
        pairs, meta = _parse_netflows_json(data)
        if pairs:
            rows += [
                {"period": p, "indicator": indicator, "value": round(v, 3), "source_file": filename}
                for p, v in pairs
            ]
            norm = str(meta.get("normalization") or "")
            notes.append(
                f"API {freq} {len(pairs)} 点（{pairs[0][0].isoformat()}→{pairs[-1][0].isoformat()}，norm={norm or 'n/a'}）"
            )
    if not rows:
        raise ValueError("Cloudflare Radar API 返回 0 条观测")
    return rows, "；".join(notes)


HISTORY_FILE = RAW_DIR / "netflows_weekly_history.json"


def _history_rows() -> tuple[list[dict], str]:
    """用户提供的周度历史 JSON（权威底稿）→ 周度指标行；无文件则返回空。"""
    if not HISTORY_FILE.is_file():
        return [], ""
    with HISTORY_FILE.open(encoding="utf-8") as handle:
        data = json.load(handle)
    pairs, _meta = _parse_netflows_json(data)
    rows = [
        {"period": p, "indicator": INDICATOR_W, "value": round(v, 3), "source_file": HISTORY_FILE.name}
        for p, v in pairs
    ]
    note = (
        f"历史周度 {len(pairs)} 周（{pairs[0][0].isoformat()}→{pairs[-1][0].isoformat()}，来源 {HISTORY_FILE.name}）"
        if pairs else ""
    )
    return rows, note


def _ingest(con, rows: list[dict]) -> int:
    """按主键 (period, indicator) 去重增量插入（保留既有历史、只补新点）。"""
    if not rows:
        return 0
    columns = list(rows[0])
    column_sql = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    con.executemany(
        f"INSERT OR IGNORE INTO {TABLE} ({column_sql}) VALUES ({placeholders})",
        [tuple(record[column] for column in columns) for record in rows],
    )
    return len(rows)


def _read_csv(path: Path) -> list[dict]:
    """自动识别日期列与数值列，返回 (period, value) 长行。"""
    if not path.is_file():
        raise FileNotFoundError(
            f"Cloudflare Radar CSV 缺失: {path}\n"
            "请从 radar.cloudflare.com/ae 的 HTTP traffic 图表 'Download CSV' "
            "手动保存近一年日度序列为本文件。"
        )
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Cloudflare Radar CSV 为空: {path}")
    header = [str(c).strip() for c in rows[0]]
    body = rows[1:]

    # 找日期列（能解析成日期的样本占比最高者）
    date_col = -1
    for col in range(min(len(header), 6)):
        ok = sum(1 for row in body if len(row) > col and _parse_date(row[col]) is not None)
        if body and ok / len(body) > 0.5:
            date_col = col
            break
    if date_col < 0:
        raise ValueError(f"Cloudflare Radar CSV 未找到日期列: header={header}")

    # 找数值列（首列即可解数字、且非日期列）
    value_col = -1
    for col in range(min(len(header), 6)):
        if col == date_col:
            continue
        if body and all(
            len(row) <= col or _coerce_number(row[col]) is not None
            for row in body[:50]
        ):
            value_col = col
            break
    if value_col < 0:
        raise ValueError(f"Cloudflare Radar CSV 未找到数值列: header={header}")

    pairs: list[tuple[date, float]] = []
    for row in body:
        if len(row) <= max(date_col, value_col):
            continue
        period = _parse_date(row[date_col])
        value = _coerce_number(row[value_col])
        if period is None or value is None:
            continue
        pairs.append((period, value))
    pairs.sort(key=lambda item: item[0])
    return [{"period": p, "value": v} for p, v in pairs]


# ---------------------------------------------------------------------------
# 入库
# ---------------------------------------------------------------------------


def _read_rows() -> list[dict]:
    raw = _read_csv(RAW_CSV)
    return [
        {
            "period": item["period"],
            "indicator": INDICATOR,
            "value": item["value"],
            "source_file": RAW_CSV.name,
        }
        for item in raw
    ]


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": INDICATOR,
            "frequency": FREQUENCY,
            "unit": UNIT,
            "source": SOURCE_NAME,
            "type": KIND,
            "industry": INDUSTRY,
            "updated_at": date.today(),
        },
        {
            "indicator_name": INDICATOR_W,
            "frequency": FREQUENCY_W,
            "unit": UNIT_W,
            "source": SOURCE_NAME,
            "type": KIND,
            "industry": INDUSTRY,
            "updated_at": date.today(),
        },
    ]


@contextmanager
def _transaction(con) -> Iterator[None]:
    transaction = con.begin()
    try:
        yield
    except BaseException:
        transaction.rollback()
        raise
    else:
        transaction.commit()


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """Cloudflare Radar 网络流量入库（增量合并，不整表替换）。

    数据来源按序并入（主键 (period, indicator) 去重，保留既有历史只补新点）：
    1. `raw/cloudflare_radar/netflows_weekly_history.json` —— 用户提供的周度历史；
    2. 有 CF_RADAR_TOKEN 且非 ``skip_download`` → API 拉日度 90d + 周度 52w 补新；
    3. 无 token → 回落手动 CSV `uae_http_traffic_daily.csv`。
    """
    rows: list[dict] = []
    notes: list[str] = []

    hrows, hnote = _history_rows()
    rows += hrows
    if hnote:
        notes.append(hnote)

    if _load_token() and not skip_download:
        arows, anote = _api_rows()
        rows += arows
        if anote:
            notes.append(anote)
    elif not rows:
        crow = _read_rows()
        rows += crow
        if crow:
            notes.append(
                f"手动 CSV {len(crow)} 天（{crow[0]['period'].isoformat()}→"
                f"{crow[-1]['period'].isoformat()}，源文件 {RAW_CSV.name}）"
            )

    if not rows:
        raise ValueError(
            "cloudflare_radar_daily 输入为空：既没有 CF_RADAR_TOKEN，"
            "也没有历史 JSON / 手动 CSV。"
        )

    with _transaction(con):
        db.ensure(con, TABLE, _TABLE_DDL)
        _ingest(con, rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    return {"status": "ok", "rows": len(rows), "note": "；".join(notes)}


# ---------------------------------------------------------------------------
# 合并回 Excel
# ---------------------------------------------------------------------------


def merge(workbook_path: Path) -> dict:
    """把 cloudflare_radar_daily 两个指标写回 日度/周度_CloudflareRadar 两个 sheet。"""
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_cloudflare_radar_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    from ._excel_helpers import payload_json_file, records_latest_first, run_powershell_sheet_writer

    con = db.connect(read_only=True)
    try:
        daily_rows = con.execute(
            "SELECT period, value FROM cloudflare_radar_daily WHERE indicator = ? ORDER BY period",
            [INDICATOR],
        ).fetchall()
        weekly_rows = con.execute(
            "SELECT period, value FROM cloudflare_radar_daily WHERE indicator = ? ORDER BY period",
            [INDICATOR_W],
        ).fetchall()
    finally:
        con.close()

    daily_cutoff = last_complete_month_end(
        max((row[0] for row in daily_rows), default=None)
    )
    weekly_cutoff = last_complete_month_end(
        max((row[0] for row in weekly_rows), default=None)
    )
    if daily_cutoff is not None:
        daily_rows = [row for row in daily_rows if row[0] <= daily_cutoff]
    if weekly_cutoff is not None:
        # Radar 的 1w 时间戳是周一周初；只有整周落在完整自然月内才展示。
        weekly_rows = [
            row
            for row in weekly_rows
            if row[0] + timedelta(days=6) <= weekly_cutoff
        ]

    class _Obs:
        def __init__(self, period, values):
            self.period = period
            self.values = tuple(values)

    def build(sheet_name, indicator, unit, frequency, observations):
        payload = {
            "dictionary_sheet_name": DICTIONARY_SHEET,
            "source_label": SOURCE_NAME,
            "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
            "frequency": frequency,
            "unit": unit,
            "source": SOURCE_NAME,
            "updated_at": date.today().isoformat(),
            "indicators": [
                {"name": indicator, "unit": unit, "type": KIND, "industry": INDUSTRY},
            ],
            "records": records_latest_first(observations),
        }
        with payload_json_file(
            payload, prefix=".cfradar-sheet-", directory=DATA_DIR
        ) as payload_path:
            run_powershell_sheet_writer(helper_path, workbook_path, payload_path, sheet_name)

    done = []
    daily_obs = [_Obs(period=p.isoformat(), values=[v]) for p, v in daily_rows]
    if daily_obs:
        build(TARGET_SHEET, INDICATOR, UNIT, FREQUENCY, daily_obs)
        done.append(f"{TARGET_SHEET} {len(daily_obs)} 天")
    weekly_obs = [_Obs(period=p.isoformat(), values=[v]) for p, v in weekly_rows]
    if weekly_obs:
        build(TARGET_SHEET_W, INDICATOR_W, UNIT_W, FREQUENCY_W, weekly_obs)
        done.append(f"{TARGET_SHEET_W} {len(weekly_obs)} 周")
    if not done:
        raise ValueError("cloudflare_radar_daily is empty; nothing to merge")
    return {"status": "ok", "note": "；".join(done)}


if __name__ == "__main__":
    print("source_cloudflare_radar.py 自检：")
    print("  update(con, ...)")
    print("    · 有 CF_RADAR_TOKEN  → API 拉 /radar/netflows/timeseries?location=AE&dateRange=52w")
    print("    · 无 token             → 解析手动 CSV raw/cloudflare_radar/uae_http_traffic_daily.csv")
    print("    → 入日表 cloudflare_radar_daily")
    print("  merge(workbook_path) 把表写回 日度_CloudflareRadar")
