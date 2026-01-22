"""
文件读取工具模块

提供统一的数据文件读取功能，消除重复代码
"""
from pathlib import Path
from typing import Union
import pandas as pd


def read_data_file(
    file_path: Union[str, Path],
    index_col: int = 0,
    parse_dates: bool = True,
    check_exists: bool = True
) -> pd.DataFrame:
    """
    根据文件扩展名读取数据文件（CSV或Excel）

    Args:
        file_path: 数据文件路径
        index_col: 索引列位置，默认为0
        parse_dates: 是否解析日期，默认为True
        check_exists: 是否检查文件存在性，默认为True

    Returns:
        读取的DataFrame

    Raises:
        FileNotFoundError: 当check_exists=True且文件不存在时
        ValueError: 当文件格式不支持时

    Examples:
        >>> data = read_data_file('data.csv')
        >>> data = read_data_file('data.xlsx', parse_dates=False)
    """
    file_path = Path(file_path)

    if check_exists and not file_path.exists():
        raise FileNotFoundError(f"数据文件不存在: {file_path}")

    file_suffix = file_path.suffix.lower()

    if file_suffix in ['.xlsx', '.xls']:
        df = pd.read_excel(
            str(file_path),
            index_col=index_col,
            parse_dates=parse_dates
        )
    elif file_suffix == '.csv':
        df = pd.read_csv(
            str(file_path),
            index_col=index_col,
            parse_dates=parse_dates
        )
    else:
        raise ValueError(
            f"不支持的文件格式: {file_suffix}，仅支持 .xlsx, .xls, .csv"
        )

    # 确保DatetimeIndex按升序排列（关键修复：避免切片失败）
    if isinstance(df.index, pd.DatetimeIndex):
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()

    return df


__all__ = ['read_data_file']
