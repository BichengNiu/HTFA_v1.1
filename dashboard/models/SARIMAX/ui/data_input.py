"""SARIMAX 自有的数据读取入口，不依赖数据探索页面。"""

from __future__ import annotations

from data_overview import create_data_overview
from data_overview.ui.widget_keys import overview_widget_keys

from dashboard.models.SARIMAX.ui.state import (
    clear_fit_results,
    clear_widget_state,
    state,
)

_SARIMAX_DATA_KEY_PREFIX = "sarimax_model"
SARIMAX_DATA_OVERVIEW_WIDGET_KEYS = overview_widget_keys(
    _SARIMAX_DATA_KEY_PREFIX
) + (
    f"{_SARIMAX_DATA_KEY_PREFIX}_preview_sheet",
)


def _on_dataset_replaced(st_obj) -> None:
    """模型文件或读取设置改变时，使已有模型结果和输入控件失效。"""

    state.set("target_variable", None)
    state.set("exog_variables", ())
    state.set("training_time_range", None)
    state.set("response_log", False)
    state.set("future_exog_editor_signature", None)
    clear_fit_results()
    clear_widget_state(st_obj)


_render_sarimax_data_input = create_data_overview(
    key_prefix=_SARIMAX_DATA_KEY_PREFIX,
    state_namespace="model_analysis.sarimax",
    on_dataset_replaced=_on_dataset_replaced,
    title="#### 数据文件",
)


def render_sarimax_data_input(st_obj) -> None:
    """渲染 SARIMAX 专属文件上传、读取与数据预览。"""

    _render_sarimax_data_input(st_obj)


__all__ = ["SARIMAX_DATA_OVERVIEW_WIDGET_KEYS", "render_sarimax_data_input"]
