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


__all__ = ["database_snapshot_key", "read_query", "resolve_database_path"]
