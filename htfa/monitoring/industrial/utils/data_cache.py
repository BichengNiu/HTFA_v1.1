"""工业监测资源缓存 adapter。"""

from __future__ import annotations

import streamlit as st

from htfa.monitoring.industrial.utils.data_loader import (
    read_weights_data,
)


@st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
def load_weights_data():
    """缓存固定权重资源；用户上传文件不进入进程级缓存。"""

    return read_weights_data()


__all__ = ["load_weights_data"]
