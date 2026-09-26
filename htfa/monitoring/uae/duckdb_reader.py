"""阿联酋监测页面的只读 DuckDB 查询工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from htfa.jobs.uae_data.paths import DB_PATH


def resolve_database_path(path: str | Path | None = None) -> Path:
    """返回可读数据库路径，并给出面向页面的明确错误。"""

    database_path = Path(path) if path is not None else DB_PATH
    if not database_path.is_file():
        raise FileNotFoundError(
            f"阿联酋 DuckDB 数据库不存在：{database_path}；请先运行数据更新任务。"
        )
    return database_path


def read_query(
    query: str,
    parameters: Iterable[object] = (),
    *,
    database_path: str | Path | None = None,
) -> pd.DataFrame:
    """在只读连接中执行查询，避免页面意外创建或修改数据库。"""

    import duckdb

    path = resolve_database_path(database_path)
    with duckdb.connect(str(path), read_only=True) as connection:
        return connection.execute(query, list(parameters)).fetchdf()


def database_snapshot_key(database_path: str | Path | None = None) -> str:
    """返回随数据库更新变化的缓存键。"""

    path = resolve_database_path(database_path)
    stat = path.stat()
    return f"{path}:{stat.st_mtime_ns}:{stat.st_size}"


def read_long_indicators(
    *,
    table: str,
    period_column: str,
    indicator_column: str,
    value_column: str,
    targets: dict[str, str],
) -> pd.DataFrame:
    """读取受控长表并转换为按月份索引的宽表。

    ``table`` 和列名只由代码中的固定常量传入；指标名仍通过 SQL 参数绑定。
    """

    if not targets:
        return pd.DataFrame()
    requested = list(targets.values())
    markers = ", ".join("?" for _ in requested)
    raw = read_query(
        f"SELECT {period_column} AS period, {indicator_column} AS indicator, "
        f"{value_column} AS value FROM {table} "
        f"WHERE {indicator_column} IN ({markers}) ORDER BY {period_column}",
        requested,
    )
    if raw.empty:
        raise ValueError(f"DuckDB 表 {table} 缺少所需指标")
    reverse = {indicator: display for display, indicator in targets.items()}
    raw["display"] = raw["indicator"].map(reverse)
    values = raw.pivot(index="period", columns="display", values="value")
    values.index = pd.DatetimeIndex(pd.to_datetime(values.index))
    values = values.reindex(columns=list(targets)).sort_index()
    missing = [name for name in targets if values[name].dropna().empty]
    if missing:
        raise ValueError("DuckDB 缺少指标：" + "、".join(missing))
    return values


__all__ = [
    "database_snapshot_key",
    "read_long_indicators",
    "read_query",
    "resolve_database_path",
]
