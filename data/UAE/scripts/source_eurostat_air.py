"""Eurostat EU↔UAE 月度航空客、货运数据入库。

数据源（Eurostat 官方 dissemination API，公开免密钥）：
- ``avia_paexcc``：International extra-EU air passenger transport by reporting
  country and partner country（月度，2008-01 起；geo=EU27_2020, partner=AE）。
- ``avia_goexcc``：International extra-EU freight and mail air transport by
  reporting country and partner country（月度，2008-01 起；geo=EU27_2020,
  partner=AE）。

解析后的细粒度长表入 ``detail.eurostat_air_monthly``（(period, dataset, geo, partner,
schedule, unit, tra_meas) 主键），tra_meas 含全部 9 个口径（如 PAS_CRD 旅客数、
PAS_CRD_ARR/DEP 抵达/离港、FRM_LD_NLD 装+卸、FRM_LD/FRM_NLD 方向口径与
CAF_* 航班数）。原始 JSON 缓存于 ``data/UAE/raw/eurostat_air/``。

注意：Eurostat 此「伙伴国」月度数据集自 2008-01 起（用户表格中 1993 起的是
不区分伙伴国的 ``avia_paoc`` 总量，如需另行扩展）。
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from urllib.request import Request, urlopen
import ssl

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402


def _ssl_context() -> ssl.SSLContext:
    """构造带 CA 的 SSL 上下文：优先 certifi 的 cacert.pem，退化默认。"""
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - certifi 缺失时用系统默认
        return ssl.create_default_context()

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "eurostat_air"
METADATA_PATH = RAW_DIR / "source_metadata.json"

API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TARGET_SHEET = "月度_Eurostat航空"  # 预留（写表暂未实现）
INDICATORS_CN = {
    "avia_paexcc": "EU27↔阿联酋航空旅客",
    "avia_goexcc": "EU27↔阿联酋航空货运与邮件",
}

# EU27_2020 的 27 个成员国（官方聚合 = 27 国之和，2025 年实测零差）
MEMBER_GEOS = (
    "BE", "BG", "CZ", "DK", "DE", "EE", "IE", "EL", "ES", "FR", "HR", "IT",
    "CY", "LV", "LT", "LU", "HU", "MT", "NL", "AT", "PL", "PT", "RO",
    "SI", "SK", "FI", "SE",
)

DATASETS = (
    # (dataset, unit, 输出文件名-聚合, 输出文件名-成员国)
    ("avia_paexcc", "PAS", "avia_paexcc.json", "avia_paexcc_members.json"),
    ("avia_goexcc", "T", "avia_goexcc.json", "avia_goexcc_members.json"),
)


# ---------------------------------------------------------------------------
# 下载器（urllib 直连 Eurostat dissemination API）
# ---------------------------------------------------------------------------


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=90, context=_ssl_context()) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} while downloading {url}")
        return json.loads(response.read().decode("utf-8"))


def _dataset_url(code: str, unit: str) -> str:
    """官方 EU27_2020 聚合查询 URL。"""
    return (
        f"{API_BASE}{code}?format=JSON&lang=EN&freq=M&geo=EU27_2020"
        f"&partner=AE&schedule=TOTAL&unit={unit}"
    )


def _members_url(code: str, unit: str) -> str:
    """全部 27 个成员国的查询 URL（Eurostat API 多值过滤须用重复参数）。"""
    geo_params = "&".join(f"geo={g}" for g in MEMBER_GEOS)
    return (
        f"{API_BASE}{code}?format=JSON&lang=EN&freq=M&{geo_params}"
        f"&partner=AE&schedule=TOTAL&unit={unit}"
    )


def atomic_json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, encoding="utf-8", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def download(output_dir: Path) -> dict[str, Path]:
    """下载两个数据集的过滤查询 JSON 并写缓存（聚合 + 27 成员国共 4 个文件）。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for code, unit, agg_filename, members_filename in DATASETS:
        agg = fetch_json(_dataset_url(code, unit))
        agg_path = output_dir / agg_filename
        atomic_json_dump(agg_path, agg)
        paths[f"{code}:agg"] = agg_path
        members = fetch_json(_members_url(code, unit))
        members_path = output_dir / members_filename
        atomic_json_dump(members_path, members)
        paths[f"{code}:members"] = members_path
    atomic_json_dump(
        METADATA_PATH,
        {
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "datasets": {
                "avia_paexcc": {
                    "name": "International extra-EU air passenger transport by "
                            "reporting country and partner country",
                    "agg_filter": "freq=M, geo=EU27_2020, partner=AE, schedule=TOTAL, unit=PAS",
                    "agg_url": _dataset_url("avia_paexcc", "PAS"),
                    "members_filter": f"freq=M, geo=27 成员国, partner=AE, schedule=TOTAL, unit=PAS",
                    "members_url": _members_url("avia_paexcc", "PAS"),
                },
                "avia_goexcc": {
                    "name": "International extra-EU freight and mail air transport "
                            "by reporting country and partner country",
                    "agg_filter": "freq=M, geo=EU27_2020, partner=AE, schedule=TOTAL, unit=T",
                    "agg_url": _dataset_url("avia_goexcc", "T"),
                    "members_filter": "freq=M, geo=27 成员国, partner=AE, schedule=TOTAL, unit=T",
                    "members_url": _members_url("avia_goexcc", "T"),
                },
            },
            "note": (
                "Eurostat 伙伴国月度序列自 2008-01 起；EU27_2020 官方聚合滞后约半年发布"
                "（2026-08 时最新 2025-12），成员国明细逐月先发（最新 2026-06 前几个月仅"
                "部分国家报齐，2026-03 起缺报大国如 FR/IT/ES，按成员国求和会低估，估算"
                "需按 2025 年各国份额做覆盖率修正）。2025 年实测：27 国求和 = 官方聚合，"
                "零差。早于 2008 的 EU 总量见 avia_paoc。"
            ),
        },
    )
    return paths


# ---------------------------------------------------------------------------
# 解析 / 质检
# ---------------------------------------------------------------------------


def decode_eurostat(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """把 dissemination JSON 解码为记录列表。

    维度顺序取 ``payload["id"]``；``payload["size"]`` 与 id 同位。``value``
    可能是全量数组（含 null）或稀疏字典 {flat_index: 值}（仅非空观测），
    两种形态都按 C 顺序（第一维最慢）解码。
    """
    dim_ids = list(payload["id"])
    sizes = [int(s) for s in payload["size"]]
    if len(sizes) != len(dim_ids):
        raise ValueError("Eurostat payload size/id 长度不一致")
    index = {
        d: payload["dimension"][d]["category"]["index"]
        for d in dim_ids
    }
    # 每维 code 按 pos 排序（index 值即其在 C 顺序中的位置）
    codes_by_dim = {
        d: sorted(index[d], key=lambda c: index[d][c])
        for d in dim_ids
    }

    values = payload.get("value") or []
    if isinstance(values, dict):
        lookup = {int(k): v for k, v in values.items()}
    elif isinstance(values, list):
        lookup = {i: v for i, v in enumerate(values)}
    else:
        raise ValueError("Eurostat payload value 形态未知")

    total = 1
    for s in sizes:
        total *= s

    records: list[dict[str, Any]] = []
    for flat in range(total):
        coords: dict[str, str] = {}
        rem = flat
        for pos_idx, d in enumerate(reversed(dim_ids)):
            pos = rem % sizes[len(dim_ids) - 1 - pos_idx]
            rem //= sizes[len(dim_ids) - 1 - pos_idx]
            coords[d] = codes_by_dim[d][pos]
        if rem:
            raise ValueError("Eurostat payload decode overflow")
        records.append({**coords, "value": lookup.get(flat)})
    return records


def _parse_period_int(time_value: str) -> int:
    """'2008-01' 或 '200801' -> 200801。"""
    digits = "".join(ch for ch in str(time_value) if ch.isdigit())
    if len(digits) != 6:
        raise ValueError(f"无法解析 Eurostat 月度 time: {time_value!r}")
    return int(digits)


def load_and_validate(
    payload: dict[str, Any],
    dataset: str,
    *,
    today: date | None = None,
    expected_geo: str | tuple[str, ...] | None = "EU27_2020",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """校验维度与时间范围，返回记录与覆盖信息。

    ``expected_geo``：聚合文件传 "EU27_2020"（必须存在）；成员国文件传
    ``None``（不强制，允许任意成员集合）或成员列表。
    """
    as_of = today or date.today()
    records = decode_eurostat(payload)
    if not records:
        raise ValueError(f"{dataset}: no records decoded")

    time_steps = sorted({_parse_period_int(r["time"]) for r in records})
    missing: list[str] = []
    if time_steps:
        current = datetime.strptime(str(time_steps[0]), "%Y%m")
        end = datetime.strptime(str(time_steps[-1]), "%Y%m")
        while current <= end:
            key = int(current.strftime("%Y%m"))
            if key not in set(time_steps):
                missing.append(str(key))
            current = current.replace(
                year=current.year + (1 if current.month == 12 else 0),
                month=1 if current.month == 12 else current.month + 1,
            )

    # 实测非空观测的 tra_meas 与其时间覆盖（Eurostat 在 partner 过滤下
    # 实际发布哪些指标；月份可能滞后发布，最终以非空观测为准）
    non_null_records = [r for r in records if r["value"] is not None]
    measures = sorted({r["tra_meas"] for r in non_null_records})
    nn_time_steps = sorted({_parse_period_int(r["time"]) for r in non_null_records})
    geo_set = {r["geo"] for r in records}
    partner_set = {r["partner"] for r in records}
    if "AE" not in partner_set:
        raise ValueError(f"{dataset}: partner=AE missing")
    if expected_geo:
        expected = (expected_geo,) if isinstance(expected_geo, str) else expected_geo
        missing_geo = [g for g in expected if g not in geo_set]
        if missing_geo:
            raise ValueError(f"{dataset}: 缺少 geo {missing_geo}")

    per_measure_missing: dict[str, list[str]] = {}
    for meas in measures:
        months = sorted(
            {_parse_period_int(r["time"]) for r in non_null_records if r["tra_meas"] == meas}
        )
        if len(months) < 2:
            continue
        current = datetime.strptime(str(months[0]), "%Y%m")
        end = datetime.strptime(str(months[-1]), "%Y%m")
        gaps = []
        while current <= end:
            key = int(current.strftime("%Y%m"))
            if key not in set(months):
                gaps.append(str(key))
            current = current.replace(
                year=current.year + (1 if current.month == 12 else 0),
                month=1 if current.month == 12 else current.month + 1,
            )
        if gaps:
            per_measure_missing[meas] = gaps

    coverage = {
        "dataset": dataset,
        "start_period": (str(nn_time_steps[0]) if nn_time_steps else None),
        "end_period": (str(nn_time_steps[-1]) if nn_time_steps else None),
        "months": len(nn_time_steps),
        "missing_months": missing,
        "geo": sorted(geo_set),
        "geo_count": len(geo_set),
        "partner": sorted(partner_set),
        "tra_meas": measures,
        "tra_meas_missing_months": per_measure_missing,
        "non_null_values": len(non_null_records),
        "total_values": len(records),
        "as_of": as_of.isoformat(),
        "note": (
            "Eurostat 伙伴国月度航空数据：EU27_2020 官方聚合滞后约半年发布；"
            "成员国明细逐月先发（最近数月可能部分国家缺报，按成员国求和需按 "
            "2025 年各国份额做覆盖率修正）。CAF_*（航班数）指标在 partner 过滤"
            "口径下不发布。"
        ),
    }
    return records, coverage


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


def _month_end(period_int: int) -> date:
    year, month = divmod(period_int, 100)
    if month == 12:
        y, m = year + 1, 1
    else:
        y, m = year, month + 1
    nxt = date(y, m, 1)
    from datetime import timedelta
    return nxt - timedelta(days=1)


TRA_MEAS_CN = {
    "PAS_BRD": "机上旅客数(人)",
    "PAS_BRD_ARR": "机上旅客数-抵达(人)",
    "PAS_BRD_DEP": "机上旅客数-离港(人)",
    "PAS_CRD": "载客数(人)",
    "PAS_CRD_ARR": "载客数-抵达(人)",
    "PAS_CRD_DEP": "载客数-离港(人)",
    "FRM_BRD": "机上货运与邮件(吨)",
    "FRM_BRD_ARR": "机上货运与邮件-抵达(吨)",
    "FRM_BRD_DEP": "机上货运与邮件-离港(吨)",
    "FRM_LD_NLD": "货运与邮件装+卸(吨)",
    "FRM_LD": "货运与邮件装载(吨)",
    "FRM_NLD": "货运与邮件卸载(吨)",
}

DATASET_CN = {
    "avia_paexcc": "EU27↔阿联酋航空旅客",
    "avia_goexcc": "EU27↔阿联酋航空货运与邮件",
}


def _dictionary_rows() -> list[dict[str, Any]]:
    rows = []
    for code, cn in DATASET_CN.items():
        for tra_meas, meas_cn in TRA_MEAS_CN.items():
            if (code == "avia_paexcc") != (tra_meas.startswith("PAS")):
                continue
            rows.append(
                {
                    "indicator_name": f"{cn}:{meas_cn}",
                    "frequency": "月",
                    "unit": "人" if tra_meas.startswith("PAS") else "吨",
                    "source": "Eurostat avia_paexcc/avia_goexcc（EU27_2020→AE，官方 API）",
                    "type": "交通",
                    "industry": "交通运输",
                    "updated_at": date.today(),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载（按需）→ 解析 → 质检 → 事务内入库 eurostat_air_monthly。

    入库内容：EU27_2020 官方聚合行 + 27 个成员国明细行（geo 维度区分）。
    """
    needed = [
        filename
        for _code, _unit, agg_file, members_file in DATASETS
        for filename in (agg_file, members_file)
    ]
    cached = all((RAW_DIR / filename).is_file() for filename in needed) \
        and METADATA_PATH.is_file()
    if skip_download:
        if not cached:
            raise FileNotFoundError(
                f"--skip-download 但缺少缓存文件: {RAW_DIR}（缺失 .json）"
            )
    elif force or not cached:
        download(RAW_DIR)

    rows: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}
    for code, _unit, agg_file, members_file in DATASETS:
        # 1) 官方 EU27_2020 聚合
        agg_payload = json.loads((RAW_DIR / agg_file).read_text(encoding="utf-8"))
        agg_records, agg_cov = load_and_validate(
            agg_payload, f"{code}:agg", expected_geo="EU27_2020"
        )
        coverage[f"{code}:agg"] = agg_cov
        for rec in agg_records:
            if rec["value"] is None:
                continue
            rows.append(
                {
                    "period": _month_end(_parse_period_int(rec["time"])),
                    "dataset": code,
                    "geo": rec["geo"],
                    "partner": rec["partner"],
                    "schedule": rec["schedule"],
                    "unit": rec["unit"],
                    "tra_meas": rec["tra_meas"],
                    "value": float(rec["value"]),
                }
            )
        # 2) 27 成员国明细
        members_payload = json.loads(
            (RAW_DIR / members_file).read_text(encoding="utf-8")
        )
        member_records, member_cov = load_and_validate(
            members_payload,
            f"{code}:members",
            expected_geo=None,  # 不强制某国（结构性无航线的国家可整体缺席）
        )
        coverage[f"{code}:members"] = member_cov
        for rec in member_records:
            if rec["value"] is None:
                continue
            rows.append(
                {
                    "period": _month_end(_parse_period_int(rec["time"])),
                    "dataset": code,
                    "geo": rec["geo"],
                    "partner": rec["partner"],
                    "schedule": rec["schedule"],
                    "unit": rec["unit"],
                    "tra_meas": rec["tra_meas"],
                    "value": float(rec["value"]),
                }
            )

    if not rows:
        raise ValueError("eurostat_air_monthly: 无观测值可入库")

    # 交叉校验：27 国求和 vs 官方聚合（PAS_CRD；2025 年实测零差，此处留痕）
    cross: dict[str, float] = {}
    sum_by_month: dict[str, float] = {}
    for row in rows:
        if row["tra_meas"] != "PAS_CRD":
            continue
        key = row["period"].strftime("%Y-%m")
        if row["geo"] == "EU27_2020":
            cross[key] = float(row["value"])
        elif row["geo"] in MEMBER_GEOS:
            sum_by_month[key] = sum_by_month.get(key, 0.0) + float(row["value"])
    common = sorted(set(cross) & set(sum_by_month))
    diffs = [abs(cross[m] - sum_by_month[m]) for m in common]
    cross_check = {
        "common_months": len(common),
        "max_abs_diff": max(diffs) if diffs else None,
    }
    if common and max(diffs) > 1.0:
        worst = max(common, key=lambda m: abs(cross[m] - sum_by_month[m]))
        raise ValueError(
            "Eurostat 成员国求和与 EU27_2020 聚合不一致: "
            f"{worst} diff={cross[worst] - sum_by_month[worst]:.0f}"
        )

    with _transaction(con):
        db.replace(con, "eurostat_air_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    parts = []
    for code, _unit, _agg_file, _members_file in DATASETS:
        agg_cov = coverage[f"{code}:agg"]
        member_cov = coverage[f"{code}:members"]
        parts.append(
            f"{code}(聚合): {agg_cov['non_null_values']} 条 "
            f"({agg_cov['start_period'] or '-'} 至 {agg_cov['end_period'] or '-'})"
        )
        parts.append(
            f"{code}(成员国 {member_cov['geo_count']} 国): "
            f"{member_cov['non_null_values']} 条 "
            f"({member_cov['start_period'] or '-'} 至 {member_cov['end_period'] or '-'})"
        )
    note = "；".join(parts) + f"；成员国求和=聚合校验通过({cross_check['common_months']} 月)"
    return {"status": "ok", "rows": len(rows), "note": note}


def merge(workbook_path: Path) -> dict:
    """Eurostat 航空数据暂未接入 Excel 写表（预留占位）。"""
    return {
        "status": "skipped",
        "note": (
            "eurostat_air_monthly 尚未接入 Excel 写表；"
            "如需合并请实现 write_eurostat_air_sheet.ps1 并注册到 merge_workbook.py"
        ),
    }


if __name__ == "__main__":
    print("source_eurostat_air.py 自检：")
    print("  update(con, force=, skip_download=) 下载→解析→质检→入库 eurostat_air_monthly")
    print("  merge(workbook_path) 暂未接入 Excel 写表")
