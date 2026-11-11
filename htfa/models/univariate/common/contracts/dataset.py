"""单变量模型使用的数据集快照。"""
from collections.abc import Hashable
from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class ModelDataset:
    """模型输入数据及其文件身份、变量表和时间列。"""

    fingerprint: str
    file_name: str
    frame: pd.DataFrame
    time_column: Hashable | None
