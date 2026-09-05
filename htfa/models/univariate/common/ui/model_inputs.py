"""可复用的目标变量、外生变量和训练样本输入模块。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from htfa.data.tabular import numeric_variable_names

from htfa.models.univariate.common.contracts import ModelingInput
from htfa.models.univariate.common.state import StateStore


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
        可选的数据替换规则。
    missing_value_options : tuple[str, ...], default=("无",)
        可选的缺失值处理方式。
    show_preprocessing : bool, default=True
        是否在本模块显示数据替换和缺失值处理控件；关闭时使用上游数据输入模块
        已提交的处理结果。
    key_prefix : str, default="model"
        Streamlit 控件键前缀。
    default_forecast_sample_size : int, default=12
        默认从共同有效样本末端预留的期数。
    show_response_log : bool, default=True
        是否显示通用目标变量对数变换控件。
    show_exog_log : bool, default=False
        是否为每个已选外生变量显示独立的对数变换控件。
    show_intervention : bool, default=False
        是否在目标变量对数控件旁显示 RDL 历史干预分析开关。
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
    show_exog_log: bool = False
    show_intervention: bool = False
    missing_value_options: tuple[str, ...] = ("无",)
    show_preprocessing: bool = True

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
        missing_value_key = f"{self.key_prefix}_missing_value_method"
        training_range_key = f"{self.key_prefix}_train_forecast_window"
        response_log_key = f"{self.key_prefix}_response_log"
        intervention_key = f"{self.key_prefix}_intervention_analysis"

        select_columns = st_obj.columns(2 if not self.show_preprocessing else 4)
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
            if self.show_response_log and self.show_intervention:
                response_column, intervention_column = st_obj.columns(2)
            elif self.show_intervention:
                response_column = st_obj
                intervention_column = st_obj
            else:
                response_column = st_obj
                intervention_column = None
            if self.show_response_log:
                response_log = bool(
                    response_column.checkbox(
                        "目标变量取对数",
                        key=response_log_key,
                        help="勾选时要求目标变量严格为正，预测结果将回到原始刻度。",
                    )
                )
            else:
                response_log = False
            if self.show_intervention:
                intervention_analysis = bool(
                    intervention_column.checkbox(
                        "干预分析",
                        key=intervention_key,
                        help=(
                            "将按历史观测日期生成 0/1 干预变量 I，"
                            "并通过 RDL 估计其对目标变量的动态影响。"
                        ),
                    )
                )
            else:
                intervention_analysis = False
        if target != self.state.get("target_variable"):
            self.state.set("target_variable", target)
            self.state.set("exog_variables", ())
            self.state.set("exog_log_names", ())
            self.clear_fit_results()
            self.clear_widget_state(st_obj, (exog_key,))
            self._clear_exog_log_widgets(st_obj)

        with select_columns[1]:
            exog_options = [name for name in variables if name != target]
            exog = st_obj.multiselect(
                "外生变量",
                options=exog_options,
                key=exog_key,
                help="外生变量的观测日期必须与目标变量完全对齐。",
            )
            exog_log_names = []
            if self.show_exog_log and exog:
                st_obj.caption("外生变量取对数（逐变量设置）")
                for name in exog:
                    if st_obj.checkbox(
                        f"{name} 取对数",
                        key=self._exog_log_key(name),
                        help="勾选后，该外生变量以自然对数进入 SARIMAX。",
                    ):
                        exog_log_names.append(name)
        if tuple(exog) != self.state.get("exog_variables", ()):
            self.state.set("exog_variables", tuple(exog))
            self.clear_fit_results()
        exog_log_names = tuple(exog_log_names)
        if exog_log_names != self.state.get("exog_log_names", ()):
            self.state.set("exog_log_names", exog_log_names)
            self.clear_fit_results()
        if response_log != self.state.get("response_log"):
            self.state.set("response_log", response_log)
            self.clear_fit_results()
        if intervention_analysis != self.state.get("intervention_analysis", False):
            self.state.set("intervention_analysis", intervention_analysis)
            self.clear_fit_results()

        if self.show_preprocessing:
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
                        "数据替换",
                        options=self.preprocessing_options,
                        default=list(self.preprocessing_options),
                        key=preprocessing_key,
                        help="可多选：去零将 0 值替换为缺失，去负将负值替换为缺失。",
                    )
                )
            if preprocessing != self.state.get("data_preprocessing", ()):
                self.state.set("data_preprocessing", preprocessing)
                self.clear_fit_results()

            missing_value_method = st_obj.session_state.get(
                missing_value_key,
                self.missing_value_options[0] if self.missing_value_options else "无",
            )
            if missing_value_method not in self.missing_value_options:
                missing_value_method = (
                    self.missing_value_options[0]
                    if self.missing_value_options
                    else "无"
                )
                st_obj.session_state[missing_value_key] = missing_value_method
            with select_columns[3]:
                missing_value_method = st_obj.selectbox(
                    "缺失值处理",
                    options=self.missing_value_options,
                    index=self.missing_value_options.index(missing_value_method),
                    key=missing_value_key,
                    help=(
                        "选择目标变量和外生变量的缺失值处理方式；"
                        "插值方法仅填补可根据现有观测推断的位置。"
                    ),
                )
            if missing_value_method != self.state.get("missing_value_method", "无"):
                self.state.set("missing_value_method", missing_value_method)
                self.clear_fit_results()
        else:
            preprocessing = tuple(self.state.get("data_preprocessing", ()))
            missing_value_method = self.state.get(
                "missing_value_method",
                self.missing_value_options[0] if self.missing_value_options else "无",
            )
            if missing_value_method not in self.missing_value_options:
                missing_value_method = (
                    self.missing_value_options[0]
                    if self.missing_value_options
                    else "无"
                )

        effective_preprocessing = (
            preprocessing if self.show_preprocessing else ()
        )
        effective_missing_value_method = (
            missing_value_method
            if self.show_preprocessing
            else (
                self.missing_value_options[0]
                if self.missing_value_options
                else "无"
            )
        )

        try:
            effective_bounds = self.effective_date_bounds(
                dataset,
                target,
                tuple(exog),
                preprocessing=effective_preprocessing,
                missing_value_method=effective_missing_value_method,
            )
            dataset_dates = self.dataset_time_index(dataset)
        except Exception as exc:  # noqa: BLE001 - 用户可读的数据准备边界
            st_obj.error(f"数据准备失败：{exc}")
            return None
        if effective_bounds is None or dataset_dates is None or len(dataset_dates) == 0:
            st_obj.error("当前变量、数据替换和缺失值处理规则下没有有效观测值。")
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

        try:
            series, exog_frame, index = self.prepare_inputs(
                dataset,
                target,
                tuple(exog),
                time_range=time_range,
                preprocessing=effective_preprocessing,
                missing_value_method=effective_missing_value_method,
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
            missing_value_method=missing_value_method,
            response_log=response_log,
            exog_log_names=exog_log_names,
            intervention_analysis=intervention_analysis,
        )

    def _exog_log_key(self, name: str) -> str:
        """Return a stable widget key for one exogenous-variable log switch."""
        return f"{self.key_prefix}_exog_log_{name}"

    def _clear_exog_log_widgets(self, st_obj) -> None:
        """Clear dynamic exogenous-log switches when the target changes."""
        session = getattr(st_obj, "session_state", None)
        if session is None:
            return
        prefix = f"{self.key_prefix}_exog_log_"
        for key in list(session.keys()):
            if isinstance(key, str) and key.startswith(prefix):
                session.pop(key, None)


__all__ = ["ModelInputModule"]
