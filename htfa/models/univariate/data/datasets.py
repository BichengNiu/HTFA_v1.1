"""单变量模型的数据集输入适配。"""
from htfa.exploration.data.tabular import build_overview_dataset
from htfa.models.univariate.common.contracts.dataset import ModelDataset


def build_model_dataset(frame, file_name: str, fingerprint: str) -> ModelDataset:
    """沿用普通表格解析协议，构造模型功能拥有的输入快照。"""
    source = build_overview_dataset(frame, file_name, fingerprint)
    return ModelDataset(
        fingerprint=source.fingerprint,
        file_name=source.file_name,
        frame=source.frame,
        time_column=source.time_column,
    )
