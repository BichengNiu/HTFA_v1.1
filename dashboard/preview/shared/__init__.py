"""
数据预览共享组件层

提供跨子模块的通用工具和组件
"""

__all__ = [
    'get_indicator_frequencies',
    'filter_indicators_by_frequency',
    'iter_all_frequencies',
    'create_empty_frequency_dict',
    'get_all_frequency_names',
]


def __getattr__(name):
    """按需暴露频率工具，避免包初始化阶段的渲染器循环导入。"""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from dashboard.preview.shared import frequency_utils

    return getattr(frequency_utils, name)
