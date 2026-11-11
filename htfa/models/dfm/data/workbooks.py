"""DFM 数据准备和模型训练的工作簿访问。"""
from io import BytesIO
from pathlib import Path
from typing import Any, Union
from htfa.workspace.data.files import file_fingerprint, read_file_bytes

from htfa.preview.data.economic_workbook import EconomicWorkbookReader
from htfa.exploration.data.tabular import TabularInputSource

_PREPARATION_READER = EconomicWorkbookReader("dfm", "models.dfm.prep")
_TRAINING_READER = TabularInputSource()


def read_preparation_tables(file_input):
    """按经济工作簿协议读取 DFM 原始输入和指标字典。"""
    return _PREPARATION_READER.read_tables(file_input)


def read_training_tables(file_input):
    """读取 DFM 预处理产物，并校验数据表及映射表存在。"""
    tables = _TRAINING_READER.read(file_input, getattr(file_input, "name", None))
    if tables.get("数据") is None or tables.get("映射") is None:
        raise ValueError("Excel文件必须包含'数据'和'映射'两个非空sheet")
    return tables


def normalize_preparation_input(file_input: Union[str, Path, Any]) -> str | BytesIO:
    """
    处理文件输入；上传内容保留在内存中，路径输入保持为路径。

    Args:
        file_input: 文件路径（str）或文件对象

    Returns:
        文件路径或独立的内存字节流
    """
    if isinstance(file_input, str):
        return file_input
    if isinstance(file_input, Path):
        return str(file_input)
    if hasattr(file_input, "getvalue"):
        return BytesIO(file_input.getvalue())
    if hasattr(file_input, "read"):
        original_position = file_input.tell() if hasattr(file_input, "tell") else None
        if hasattr(file_input, "seek"):
            file_input.seek(0)
        content = file_input.read()
        if original_position is not None:
            file_input.seek(original_position)
        return BytesIO(content)
    raise TypeError(f"不支持的文件输入类型: {type(file_input)}")


def preparation_fingerprint(excel_input: str | BytesIO) -> str:
    """以文件内容生成稳定缓存键。"""
    return file_fingerprint(read_file_bytes(excel_input))
