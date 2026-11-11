"""统一模板的数据加载入口。"""

from collections.abc import Collection, Iterator
from contextlib import contextmanager
from typing import Any

import pandas as pd

from htfa.data.economic_workbook.parser import parse_economic_workbook
from htfa.data.economic_workbook.contracts.models import EconomicWorkbookSnapshot
from htfa.data.economic_workbook.tables import TableWorkbook
from htfa.data.economic_workbook.target_reader import open_workbook as open_economic_workbook


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
                sheet_name: excel_file.parse(
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
    ) -> Iterator[tuple[pd.ExcelFile | TableWorkbook, str]]:
        """打开供主题读取的正式经济工作簿。"""
        with open_economic_workbook(file_input, file_name=file_name) as opened:
            yield opened


__all__ = ["EconomicWorkbookReader"]
