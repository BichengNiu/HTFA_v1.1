"""SARIMAX 数据概览 ↔ HTFA 全局共享数据集适配器。

实现 data_overview.DataSource 协议：渲染 HTFA 侧边栏共享数据集
的上传控件（页面内嵌 compact 模式），并委托 shared_dataset 的
全局会话状态——数据概览与数据探索/其他模型共用同一份上传数据。
"""

from __future__ import annotations

import pandas as pd

from dashboard.core.ui.utils import shared_dataset


class SharedDatasetSource:
    """把 HTFA 全局共享数据集适配为 data_overview 数据源。"""

    def render_uploader(self, st_obj, *, compact: bool = False) -> dict:
        return shared_dataset.render_shared_dataset_uploader(
            st_obj,
            compact=compact,
            allow_unparsed=True,
        )

    def current_data(self) -> pd.DataFrame | None:
        return shared_dataset.get_shared_dataset_data()

    def load_data(
        self,
        *,
        variable_name_row: int = 0,
        data_start_row: int = 1,
        time_column: str | None = None,
    ) -> pd.DataFrame | None:
        """从共享数据集原始文件按 SARIMAX 行设置重新读取。"""
        uploaded_file = shared_dataset.get_shared_dataset_file()
        if uploaded_file is None:
            return None
        return shared_dataset.load_shared_dataframe(
            uploaded_file,
            sheet_name=self.current_sheet(),
            variable_name_row=variable_name_row,
            data_start_row=data_start_row,
            time_column=time_column,
            raw_rows=shared_dataset.get_shared_dataset_raw_rows(),
        )

    def row_count(self) -> int:
        return shared_dataset.get_shared_dataset_row_count()

    def current_fingerprint(self) -> str:
        return shared_dataset.get_shared_dataset_fingerprint()

    def current_name(self) -> str:
        return shared_dataset.get_shared_dataset_name()

    def sheets(self) -> list[str] | None:
        return shared_dataset.get_shared_dataset_sheets()

    def current_sheet(self) -> str | None:
        return shared_dataset.get_shared_dataset_sheet()

    def select_sheet(self, sheet: str) -> None:
        shared_dataset.select_shared_dataset_sheet(sheet, allow_unparsed=True)


__all__ = ["SharedDatasetSource"]
