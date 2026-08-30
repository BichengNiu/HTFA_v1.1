"""可复用的目标变量、外生变量和训练样本输入模块。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from data_overview.core.dataset import numeric_variable_names

from dashboard.models.common.contracts import ModelingInput
from dashboard.models.common.state import StateStore


PrepareInputs = Callable[..., tuple[pd.Series, pd.DataFrame | None, pd.Index]]
EffectiveBounds = Callable[..., tuple[pd.Timestamp, pd.Timestamp] | None]
DatasetTimeIndex = Callable[[Any], pd.DatetimeIndex | None]
ClearFitResults = Callable[[], None]
ClearWidgetState = Callable[[object, tuple[str, ...]], None]


@dataclass(frozen=True)
class ModelInputModule:
    """渲染跨模型共用的建模变量、日期和预处理输入。

    Parameters
    ----------
    state : StateStore
        当前模型页面的命名空间状态存储。
    clear_fit_results : callable
        输入变化时清除拟合及下游结果的回调。
    clear_widget_state : callable
        清除指定 Streamlit 控件状态的回调。
    prepare_inputs : callable
        将数据集和用户选择转换为对齐建模输入的纯函数。
    effective_date_bounds : callable
        计算预处理后共同有效日期边界的纯函数。
    dataset_time_index : callable
        返回数据集完整日期索引的纯函数。
    preprocessing_options : tuple[str, ...]
        可选的数据预处理规则。
    key_prefix : str, default="model"
        Streamlit 控件键前缀。
    default_forecast_sample_size : int, default=12
        默认从共同有效样本末端预留的期数。
    show_response_log : bool, default=True
        是否显示通用目标变量对数变换控件。
    """

    state: StateStore
    clear_fit_results: ClearFitResults
    clear_widget_state: ClearWidgetState
    prepare_inputs: PrepareInputs
    effective_date_bounds: EffectiveBounds
    dataset_time_index: DatasetTimeIndex
    preprocessing_options: tuple[str, ...]
    key_prefix: str = "model"
    default_forecast_sample_size: int = 12
    show_response_log: bool = True

    def render(
        self,
        st_obj,
        dataset,
        *,
        dataset_fingerprint: str = "",
    ) -> ModelingInput | None:
        """渲染输入控件并返回已对齐的通用建模输入。"""
        variables = numeric_variable_names(dataset.frame)
        if not variables:
            st_obj.error("数据中没有可用的数值型变量。")
            return None
        if dataset.time_column is None:
            st_obj.error("没有找到有效时间列，请在数据读取设置中选择有效的时间列。")
            return None

        target_key = f"{self.key_prefix}_target_select"
        exog_key = f"{self.key_prefix}_exog_select"
        preprocessing_key = f"{self.key_prefix}_data_preprocessing"
        training_range_key = f"{self.key_prefix}_train_forecast_window"
        response_log_key = f"{self.key_prefix}_response_log"

        select_columns = st_obj.columns(3)
        with select_columns[0]:
            target = st_obj.selectbox(
                "目标变量",
                options=variables,
                index=(
                    variables.index(self.state.get("target_variable"))
                    if self.state.get("target_variable") in variables
                    else 0
                ),
                key=target_key,
            )
        if target != self.state.get("target_variable"):
            self.state.set("target_variable", target)
            self.state.set("exog_variables", ())
            self.clear_fit_results()
            self.clear_widget_state(st_obj, (exog_key,))

        with select_columns[1]:
            exog_options = [name for name in variables if name != target]
            exog = st_obj.multiselect(
                "外生变量",
                options=exog_options,
                key=exog_key,
                help="外生变量的观测日期必须与目标变量完全对齐。",
            )
        if tuple(exog) != self.state.get("exog_variables", ()):
            self.state.set("exog_variables", tuple(exog))
            self.clear_fit_results()

        preprocessing = tuple(
            st_obj.session_state.get(
                preprocessing_key,
                self.preprocessing_options,
            )
        )
        if preprocessing != self.state.get("data_preprocessing", ()):
            self.clear_fit_results()
        with select_columns[2]:
            preprocessing = tuple(
                st_obj.multiselect(
                    "数据预处理",
                    options=self.preprocessing_options,
                    default=list(self.preprocessing_options),
                    key=preprocessing_key,
                    help="可多选：去零将 0 值视为缺失，去负将负值视为缺失。",
                )
            )
        if preprocessing != self.state.get("data_preprocessing", ()):
            self.state.set("data_preprocessing", preprocessing)
            self.clear_fit_results()

        try:
            effective_bounds = self.effective_date_bounds(
                dataset,
                target,
                tuple(exog),
                preprocessing=preprocessing,
            )
            dataset_dates = self.dataset_time_index(dataset)
        except Exception as exc:  # noqa: BLE001 - 用户可读的数据准备边界
            st_obj.error(f"数据准备失败：{exc}")
            return None
        if effective_bounds is None or dataset_dates is None or len(dataset_dates) == 0:
            st_obj.error("当前变量和数据预处理规则下没有有效观测值。")
            return None

        effective_start, effective_end = effective_bounds
        modeling_dates = dataset_dates[
            (dataset_dates >= effective_start) & (dataset_dates <= effective_end)
        ]
        date_min, date_max = effective_start.date(), effective_end.date()
        if len(modeling_dates) > self.default_forecast_sample_size:
            default_train_end = modeling_dates[
                -self.default_forecast_sample_size - 1
            ].date()
        else:
            default_train_end = date_max
        default_range = (date_min, default_train_end)
        existing_range = st_obj.session_state.get(training_range_key)
        try:
            existing_range = tuple(
                pd.Timestamp(value).date() for value in existing_range
            )
        except (TypeError, ValueError):
            existing_range = ()
        if (
            len(existing_range) == 2
            and date_min <= existing_range[0] <= existing_range[1] <= date_max
        ):
            range_value = existing_range
        else:
            range_value = default_range
        with st_obj.container():
            selected_range = st_obj.slider(
                "训练样本范围（日期）",
                min_value=date_min,
                max_value=date_max,
                value=range_value,
                step=pd.Timedelta(days=1).to_pytimedelta(),
                format="YYYY-MM-DD",
                key=training_range_key,
                help=(
                    "左端和右端定义训练样本闭区间；预测区间请在模型拟合后"
                    "通过预测页滑轨单独设置。"
                ),
            )
        if not isinstance(selected_range, (tuple, list)) or len(selected_range) != 2:
            st_obj.warning("请选择完整的训练起始日期和结束日期。")
            return None
        time_range = tuple(pd.Timestamp(value) for value in selected_range)
        if time_range != self.state.get("training_time_range"):
            self.state.set("training_time_range", time_range)
            self.clear_fit_results()

        if self.show_response_log:
            response_log = bool(
                st_obj.checkbox(
                    "目标变量取对数",
                    key=response_log_key,
                    help="勾选时要求目标变量严格为正，预测结果将回到原始刻度。",
                )
            )
        else:
            response_log = False
        if response_log != self.state.get("response_log"):
            self.state.set("response_log", response_log)
            self.clear_fit_results()

        try:
            series, exog_frame, index = self.prepare_inputs(
                dataset,
                target,
                tuple(exog),
                time_range=time_range,
                preprocessing=preprocessing,
            )
        except Exception as exc:  # noqa: BLE001 - 用户可读的数据准备边界
            st_obj.error(f"数据准备失败：{exc}")
            return None

        return ModelingInput(
            series=series,
            exog=exog_frame,
            index=index,
            target=target,
            exog_names=(
                tuple(exog_frame.columns) if exog_frame is not None else ()
            ),
            training_range=time_range,
            dataset_fingerprint=dataset_fingerprint,
            preprocessing=preprocessing,
            response_log=response_log,
        )


__all__ = ["ModelInputModule"]
