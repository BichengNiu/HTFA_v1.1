"""统一模板的数据加载入口。"""

import re
from typing import Any, List

from dashboard.preview.core.base_loader import BaseDataLoader
from dashboard.preview.core.workbook_parser import parse_preview_workbook
from dashboard.preview.domain.models import LoadedPreviewData


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


class PreviewWorkbookLoader(BaseDataLoader):
    """调用唯一工作簿协议的共享加载器。"""

    module_name: str
    state_namespace: str

    def load_and_process_data(self, files: List[Any]) -> LoadedPreviewData:
        """解析一个正式模板工作簿。"""
        if len(files) != 1:
            raise ValueError("每个预览模块必须提供且只能提供一个经济数据库文件")

        return parse_preview_workbook(
            files[0],
            module_name=self.module_name,
        )

    def extract_industry_name(self, source: str) -> str:
        """提取来源中的分类名称。"""
        return extract_industry_name(source)

    def get_state_namespace(self) -> str:
        """返回模块隔离的状态命名空间。"""
        return self.state_namespace


__all__ = ["PreviewWorkbookLoader", "extract_industry_name"]
