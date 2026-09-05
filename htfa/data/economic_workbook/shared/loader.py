"""统一模板的数据加载入口。"""

import re
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from typing import Any

import pandas as pd

from ..core.workbook_parser import parse_economic_workbook
from ..domain.models import EconomicWorkbookSnapshot
from .target_reader import (
    SheetSeriesMetadata,
    open_workbook as open_economic_workbook,
    parse_target_sheet,
    validate_sheet,
)


_SOURCE_TOKENS = {
    "日度",
    "周度",
    "旬度",
    "月度",
    "季度",
    "年度",
    "Wind",
    "wind",
    "同花顺",
    "TongHuaShun",
    "tonghuashun",
    "Mysteel",
    "mysteel",
    "Myteel",
    "myteel",
}


def extract_industry_name(source: str) -> str:
    """从“文件名|sheet名”来源中提取可展示的分类名称。"""
    sheet_name = str(source).split("|")[-1].strip()
    tokens = [
        token
        for token in re.split(r"[_\-\s]+", sheet_name)
        if token
    ]
    return next(
        (token for token in tokens if token not in _SOURCE_TOKENS),
        tokens[0] if tokens else sheet_name or "未知",
    )


class EconomicWorkbookReader:
    """调用唯一经济工作簿协议的共享读取器。"""

    def __init__(
        self,
        module_name: str,
        state_namespace: str,
        indicator_allowlist: Collection[str] | None = None,
    ):
        self.module_name = module_name
        self.state_namespace = state_namespace
        self.indicator_allowlist = indicator_allowlist

    def read(self, file_input: Any) -> EconomicWorkbookSnapshot:
        """按模块规则读取一个正式经济工作簿。"""
        return parse_economic_workbook(
            file_input,
            module_name=self.module_name,
            indicator_allowlist=self.indicator_allowlist,
        )

    def read_tables(
        self,
        file_input: Any,
        *,
        header: int | None = 0,
    ) -> dict[str, pd.DataFrame]:
        """读取工作簿各 sheet 的表格视图，供领域处理器消费。"""
        with self.open_workbook(file_input) as (excel_file, _):
            return {
                sheet_name: pd.read_excel(
                    excel_file,
                    sheet_name=sheet_name,
                    header=header,
                )
                for sheet_name in excel_file.sheet_names
            }

    def get_state_namespace(self) -> str:
        """返回模块隔离的状态命名空间。"""
        return self.state_namespace

    @contextmanager
    def open_workbook(
        self,
        file_input: Any,
        *,
        file_name: str | None = None,
    ) -> Iterator[tuple[pd.ExcelFile, str]]:
        """打开供主题读取的正式经济工作簿。"""
        with open_economic_workbook(file_input, file_name=file_name) as opened:
            yield opened

    def read_target_sheet(
        self,
        excel_file: pd.ExcelFile,
        *,
        sheet_name: str,
        targets: tuple[tuple[str, str], ...],
        allowed_frequencies: set[str],
        expected_unit: str,
        zero_is_missing: bool = True,
    ) -> tuple[pd.DataFrame, dict[str, SheetSeriesMetadata]]:
        """按目标指标和元数据约束读取一个经济工作簿 sheet。"""
        return parse_target_sheet(
            excel_file,
            sheet_name=sheet_name,
            targets=targets,
            allowed_frequencies=allowed_frequencies,
            expected_unit=expected_unit,
            zero_is_missing=zero_is_missing,
        )

    def validate_target_sheet(self, raw: Any, sheet_name: str) -> None:
        """校验一个经济数据 sheet 的元数据结构。"""
        validate_sheet(raw, sheet_name)

    def read_raw_sheet(
        self,
        excel_file: pd.ExcelFile,
        *,
        sheet_name: str,
    ) -> pd.DataFrame:
        """读取一个经济数据 sheet 的原始二维表。"""
        if sheet_name not in excel_file.sheet_names:
            raise ValueError(f"工作簿缺少“{sheet_name}”sheet")
        return pd.read_excel(excel_file, sheet_name=sheet_name, header=None)


__all__ = ["EconomicWorkbookReader", "extract_industry_name"]
