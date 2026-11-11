"""经济工作簿预览的读取与展示数据准备。"""
import re
from htfa.data.economic_workbook import EconomicWorkbookReader

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



class EconomicPreviewWorkflow:
    """读取工作簿并生成预览所需的频率表与指标映射。"""

    def __init__(self, module_name: str, state_namespace: str):
        self.state_namespace = state_namespace
        self._reader = EconomicWorkbookReader(module_name, state_namespace)

    def load(self, file_input) -> dict:
        """按经济协议解析输入并构建完整预览载荷。"""
        snapshot = self._reader.read(file_input)
        payload = {}
        for frequency, frame in snapshot.dataframes.items():
            payload[f"{frequency}_df"] = frame
            if not frame.empty:
                payload[f"{frequency}_industries"] = sorted({
                    industry for indicator in frame.columns
                    if (industry := snapshot.indicator_industry_map.get(indicator))
                })
        for name in ["source_map", "indicator_industry_map", "indicator_unit_map", "indicator_type_map"]:
            payload[name] = getattr(snapshot, name)
        clean = {}
        for indicator, source in snapshot.source_map.items():
            industry = snapshot.indicator_industry_map.get(indicator) or extract_industry_name(source)
            clean.setdefault(industry, []).append(source)
        payload["clean_industry_map"] = clean
        return payload
