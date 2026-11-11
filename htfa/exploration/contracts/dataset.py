from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class ExploreDataset:
    """一次解析后供整个数据探索模块共享的数据集。"""

    fingerprint: str
    file_name: str
    tables: dict[str, pd.DataFrame]
