from __future__ import annotations
import re
from dataclasses import replace
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.contracts.government_finance.ded import DedData
from htfa.monitoring.uae.data.government_finance.ded import read_ded_data


def load_ded_data(source: PublishedUAEData) -> DedData:
    """读取 ``月度_DED`` 的有发证活动企业数与当月新发执照数两列。"""
    frame, metadata = read_ded_data(source)
    metadata = {
        name: replace(item, source=_clean_source(item.source))
        for name, item in metadata.items()
    }
    return DedData(values=frame, metadata=metadata)


def _clean_source(value: str) -> str:
    """去掉来源里的括号及括号内说明（如 "(commerce_number 按发照月去重)"）。"""
    return re.sub("[（(][^）)]*[）)]", "", value).strip()
