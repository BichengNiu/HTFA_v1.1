"""可复用的数据导入和行列选择模块。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from data_overview import create_data_overview
from data_overview.ui.data_source import DataSource


@dataclass(frozen=True)
class DataInputModule:
    """由 data overview 驱动的可复用数据输入模块。

    Parameters
    ----------
    key_prefix : str
        Streamlit 控件键前缀。
    state_namespace : str
        数据源和共享状态使用的命名空间。
    data_source : DataSource
        文件读取和工作表选择适配器。
    on_dataset_replaced : callable or None
        数据集身份变化时调用的状态清理函数。
    title : str
        数据输入模块标题。
    show_preview : bool
        是否显示数据预览和图表设置。
    """

    key_prefix: str
    state_namespace: str
    data_source: DataSource
    on_dataset_replaced: Callable[[object], None] | None = None
    title: str = ""
    show_preview: bool = False
    _renderer: Callable[[object], None] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        renderer = create_data_overview(
            key_prefix=self.key_prefix,
            state_namespace=self.state_namespace,
            data_source=self.data_source,
            on_dataset_replaced=self.on_dataset_replaced,
            title=self.title,
            show_preview=self.show_preview,
        )
        object.__setattr__(self, "_renderer", renderer)

    def render(self, st_obj) -> None:
        """渲染文件读取设置、行列选择和可选预览。"""
        self._renderer(st_obj)


def create_data_input_module(
    *,
    key_prefix: str,
    state_namespace: str,
    data_source: DataSource,
    on_dataset_replaced: Callable[[object], None] | None = None,
    title: str = "",
    show_preview: bool = False,
) -> DataInputModule:
    """创建一个独立的数据导入和变量选择模块。"""
    return DataInputModule(
        key_prefix=key_prefix,
        state_namespace=state_namespace,
        data_source=data_source,
        on_dataset_replaced=on_dataset_replaced,
        title=title,
        show_preview=show_preview,
    )


__all__ = ["DataInputModule", "create_data_input_module"]
