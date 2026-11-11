"""本功能的表格文件序列化。"""
import pandas as pd


def serialize_csv(frame: pd.DataFrame, *, index: bool = True) -> bytes:
    """将表格序列化为 Excel 可读取的 UTF-8 BOM CSV。"""
    return frame.to_csv(index=index).encode("utf-8-sig")
