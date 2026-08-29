"""平稳性检验的 Streamlit 单变量工作流。"""

from __future__ import annotations

import logging

import pandas as pd

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.explore.analysis.stationarity import (
    TABLE_FREQUENCIES,
    TEST_LABELS,
    TEST_TREND_LABELS,
    TEST_TREND_OPTIONS,
    TRANSFORMATIONS,
    create_time_series_figure,
    matplotlib_date_compatibility,
    normalize_frequency,
    numeric_variable_names,
    prepare_selected_series,
    resolve_year_over_year_lag,
    run_selected_stationarity_tests,
    transform_series,
)
from dashboard.explore.core.data_source import (
    FREQUENCY_LABELS,
    ExploreDataset,
    format_table_option,
)
from dashboard.explore.preprocessing.frequency_alignment import (
    infer_series_frequency,
)
from dashboard.explore.ui.base import TimeSeriesAnalysisComponent
from dashboard.explore.ui.chart_controls import (
    chart_scope,
    get_applied_config,
    render_correlogram_chart,
    render_time_series_config_expander,
)
from dashboard.explore.ui.dataset_context import get_explore_dataset

logger = logging.getLogger(__name__)


def resolve_table_frequency(table_key: str, series: pd.Series) -> str:
    """优先采用已解析频率表；普通单表数据再从时间索引推断。"""
    mapped = normalize_frequency(TABLE_FREQUENCIES.get(table_key, table_key))
    if mapped != "Undetermined":
        return mapped
    if isinstance(series.index, pd.DatetimeIndex):
        return infer_series_frequency(series.dropna())
    return "Undetermined"


def transformation_options_for_frequency(frequency: str) -> list[str]:
    """返回当前频率下可计算的变换，隐藏无可靠周期的同比选项。"""
    supports_year_over_year = True
    try:
        resolve_year_over_year_lag(frequency)
    except ValueError:
        supports_year_over_year = False

    return [
        key
        for key, spec in TRANSFORMATIONS.items()
        if supports_year_over_year or not spec.year_over_year
    ]


class StationarityAnalysisComponent(TimeSeriesAnalysisComponent):
    """上传、单变量诊断、预处理和检验的一体化组件。"""

    _RESULT_STATE_KEYS = (
        "test_results",
        "test_signature",
    )

    _DEPENDENT_WIDGET_SUFFIXES = (
        "table_select",
        "variable_select",
        "date_range",
        "transformation_select",
        "test_source",
        "test_methods",
        "test_alpha",
        "run_tests",
        "download_tests",
        "adf_trend",
        "kpss_trend",
        "pp_trend",
    )

    def __init__(
        self,
        analysis_type: str = "stationarity",
        title: str = "平稳性检验",
    ):
        super().__init__(analysis_type, title)

    def _widget_key(self, suffix: str) -> str:
        return f"{self.analysis_type}_{suffix}"

    def _dependent_widget_keys(self) -> tuple[str, ...]:
        return tuple(
            self._widget_key(suffix)
            for suffix in self._DEPENDENT_WIDGET_SUFFIXES
        )

    def render(
        self,
        st_obj,
        uploaded_file=None,
        dataset: ExploreDataset | None = None,
    ):
        """使用侧边栏共享数据集渲染单变量分析流程。"""
        if self.analysis_type == "stationarity":
            st_obj.markdown("### 选择数据")

        if uploaded_file is None:
            if self.get_state("file_fingerprint") is not None:
                self._reset_uploaded_data(st_obj)
            st_obj.info("请先在侧边栏上传 CSV、XLS 或 XLSX 共享数据集。")
            return None

        try:
            dataset = dataset or get_explore_dataset(st_obj, uploaded_file)
            if dataset.fingerprint != self.get_state("file_fingerprint"):
                self.set_state("data_tables", dataset.tables)
                self.set_state("file_fingerprint", dataset.fingerprint)
                self.set_state("file_name", dataset.file_name)
                self.set_state("selected_table_key", None)
                self.set_state("selected_variable", None)
                self.set_state("selected_transformation", None)
                self._clear_analysis_results()
                self._clear_widget_state(
                    st_obj,
                    self._dependent_widget_keys(),
                )
        except Exception as exc:  # noqa: BLE001 - user-facing file load boundary
            self._reset_uploaded_data(st_obj)
            st_obj.error(f"文件读取或数据库解析失败：{exc}")
            return None

        tables = self.get_state("data_tables", {})
        if not tables:
            st_obj.error("数据集没有可分析的数据表")
            return None

        selection_columns = st_obj.columns(3) if self.analysis_type == "stationarity" else None
        table_container = selection_columns[0] if selection_columns else st_obj
        selected_table_key = table_container.selectbox(
            "选择要分析的数据表",
            options=list(tables),
            format_func=lambda key: format_table_option(key, tables),
            key=self._widget_key("table_select"),
        )
        if self._remember_selection("selected_table_key", selected_table_key):
            self.set_state("selected_variable", None)
            self.set_state("selected_transformation", None)
            self._clear_widget_state(
                st_obj,
                self._dependent_widget_keys()[1:],
            )

        data = tables[selected_table_key]
        file_name = self.get_state("file_name") or "data"
        table_label = FREQUENCY_LABELS.get(selected_table_key, "数据表")
        st_obj.caption(
            f"当前数据：{file_name} · {table_label} · "
            f"{len(data):,} 行 × {len(data.columns):,} 列"
        )
        workflow_kwargs = {}
        if selection_columns:
            workflow_kwargs = {
                "variable_container": selection_columns[1],
                "preprocessing_container": selection_columns[2],
            }
        return self._render_variable_workflow(
            st_obj,
            data,
            table_key=selected_table_key,
            data_name=f"{file_name}-{table_label}",
            **workflow_kwargs,
        )

    def _render_variable_workflow(
        self,
        st_obj,
        data: pd.DataFrame,
        *,
        table_key: str,
        data_name: str,
        variable_container=None,
        preprocessing_container=None,
    ):
        variables = numeric_variable_names(data)
        if not variables:
            st_obj.error("所选数据表没有实数型变量")
            return

        variable_container = variable_container or st_obj
        selected_variable = variable_container.selectbox(
            "选择变量",
            options=variables,
            key=self._widget_key("variable_select"),
        )
        self._remember_selection("selected_variable", selected_variable)

        try:
            original_series, _ = prepare_selected_series(
                data,
                selected_variable,
            )
        except Exception as exc:  # noqa: BLE001 - user-facing variable preparation boundary
            st_obj.error(f"变量准备失败：{exc}")
            return

        st_obj.markdown("---")
        st_obj.markdown("### 平稳性检验")
        test_options_container = st_obj.container()
        test_output_container = st_obj.container()
        date_source_columns = test_options_container.columns(2)
        method_alpha_columns = test_options_container.columns(2)
        trend_options_container = test_options_container.container()
        selected_tests = method_alpha_columns[0].multiselect(
            "选择检验方法",
            options=list(TEST_LABELS),
            default=["adf", "kpss"],
            format_func=lambda key: TEST_LABELS[key],
            key=self._widget_key("test_methods"),
        )
        alpha = method_alpha_columns[1].selectbox(
            "显著性水平",
            options=[0.01, 0.05, 0.10],
            index=1,
            key=self._widget_key("test_alpha"),
        )
        analysis_series, date_range = self._render_date_range(
            st_obj,
            original_series,
            input_container=date_source_columns[0],
        )
        if analysis_series is None:
            return

        frequency = resolve_table_frequency(table_key, analysis_series)
        processed_series, transformation = self._render_preprocessing(
            st_obj,
            analysis_series,
            selected_variable,
            frequency,
            input_container=preprocessing_container,
            correlogram_alpha=alpha,
            chart_context=(table_key, selected_variable),
        )
        self._render_stationarity_tests(
            st_obj,
            original_series=analysis_series,
            processed_series=processed_series,
            variable=selected_variable,
            transformation=transformation,
            data_name=data_name,
            table_key=table_key,
            date_range=date_range,
            source_container=date_source_columns[1],
            selected_tests=selected_tests,
            alpha=alpha,
            trend_options_container=trend_options_container,
            output_container=test_output_container,
        )
        return

    def _render_date_range(
        self,
        st_obj,
        series: pd.Series,
        *,
        input_container=None,
    ) -> tuple[pd.Series | None, tuple[str, str] | None]:
        """筛选平稳性检验的样本区间，并返回可签名的起止日期。"""
        if not isinstance(series.index, pd.DatetimeIndex):
            st_obj.info("未识别到时间索引，平稳性检验将使用全部观测。")
            return series, None

        start_date = series.index.min().date()
        end_date = series.index.max().date()
        input_container = input_container or st_obj
        selected_range = input_container.date_input(
            "检验时间范围",
            value=(start_date, end_date),
            min_value=start_date,
            max_value=end_date,
            key=self._widget_key("date_range"),
        )
        if not isinstance(selected_range, (tuple, list)) or len(selected_range) != 2:
            st_obj.info("请选择检验起止日期。")
            return None, None

        selected_start, selected_end = selected_range
        if selected_start > selected_end:
            st_obj.error("检验起始日期不能晚于结束日期。")
            return None, None

        filtered = series.loc[
            (series.index >= pd.Timestamp(selected_start))
            & (series.index <= pd.Timestamp(selected_end))
        ]
        if filtered.empty:
            st_obj.error("所选时间范围内没有观测值。")
            return None, None

        return filtered, (str(selected_start), str(selected_end))

    def _render_preprocessing(
        self,
        st_obj,
        series: pd.Series,
        variable: str,
        frequency: str,
        input_container=None,
        correlogram_alpha: float = 0.05,
        chart_context: tuple[str, str] = ("table", "variable"),
    ) -> tuple[pd.Series | None, str]:
        options = transformation_options_for_frequency(frequency)
        input_container = input_container or st_obj
        transformation = input_container.selectbox(
            "预处理方法",
            options=options,
            format_func=lambda key: TRANSFORMATIONS[key].label,
            key=self._widget_key("transformation_select"),
        )
        self._remember_selection(
            "selected_transformation",
            transformation,
        )

        if transformation == "original":
            st_obj.info("当前不生成处理后变量；平稳性检验将针对原始变量。")
            return None, transformation

        try:
            processed = transform_series(
                series,
                transformation,
                frequency=frequency,
            )
        except Exception as exc:  # noqa: BLE001 - user-facing preprocessing boundary
            st_obj.error(f"预处理失败：{exc}")
            return None, transformation

        try:
            time_scope = chart_scope(
                "stationarity", *chart_context, transformation, "processed_time_series"
            )
            time_defaults = {
                "title": (
                    f"{variable} · {TRANSFORMATIONS[transformation].label}"
                ),
                "x_title": "时间",
                "y_title": str(processed.name or "数值"),
                "line_width": 3.0,
                "marker_size": 0.0,
                "max_ticks": 12,
                "y_tick_count": 8,
                "x_start": (
                    processed.index.min().date()
                    if isinstance(processed.index, pd.DatetimeIndex)
                    else None
                ),
                "y_start": None,
                "grid_mode": "both",
                "grid_line_style": "solid",
            }
            config = get_applied_config(time_scope, time_defaults)
            with matplotlib_date_compatibility():
                figure = create_time_series_figure(
                    processed,
                    **config,
                )
                render_pyplot_figure(st_obj, figure)
            render_time_series_config_expander(
                st_obj,
                scope=time_scope,
                defaults=time_defaults,
            )
        except Exception as exc:  # noqa: BLE001 - optional chart boundary
            st_obj.warning(f"处理后序列图无法绘制：{exc}")

        self._render_correlogram(
            st_obj,
            processed,
            title_prefix=(
                f"{variable} · "
                f"{TRANSFORMATIONS[transformation].label}"
            ),
            include_acf=True,
            include_pacf=True,
            alpha=correlogram_alpha,
            scope=chart_scope(
                "stationarity", *chart_context, transformation, "processed_correlogram"
            ),
        )
        return processed, transformation

    def _render_correlogram(
        self,
        st_obj,
        series: pd.Series,
        *,
        title_prefix: str,
        include_acf: bool,
        include_pacf: bool,
        alpha: float,
        scope: str,
    ) -> None:
        render_correlogram_chart(
            st_obj,
            series,
            title_prefix=title_prefix,
            include_acf=include_acf,
            include_pacf=include_pacf,
            alpha=alpha,
            scope=scope,
        )

    def _render_stationarity_tests(
        self,
        st_obj,
        *,
        original_series: pd.Series,
        processed_series: pd.Series | None,
        variable: str,
        transformation: str,
        data_name: str,
        table_key: str,
        date_range: tuple[str, str] | None,
        source_container,
        selected_tests,
        alpha,
        trend_options_container,
        output_container,
    ) -> None:
        sources = {"original": original_series}
        source_labels = {"original": "原始变量"}
        if processed_series is not None:
            sources["processed"] = processed_series
            source_labels["processed"] = (
                f"处理后变量（{TRANSFORMATIONS[transformation].label}）"
            )

        source = source_container.selectbox(
            "检验对象",
            options=list(sources),
            format_func=lambda key: source_labels[key],
            key=self._widget_key("test_source"),
        )
        test_trends = {}
        if selected_tests:
            trend_columns = trend_options_container.columns(min(3, len(selected_tests)))
            for index, test_key in enumerate(selected_tests):
                options = list(TEST_TREND_OPTIONS[test_key])
                default_index = options.index("c")
                test_trends[test_key] = trend_columns[
                    index % len(trend_columns)
                ].selectbox(
                    f"{TEST_LABELS[test_key]}",
                    options=options,
                    index=default_index,
                    format_func=lambda value, key=test_key: (
                        TEST_TREND_LABELS[key][value]
                    ),
                    key=self._widget_key(f"{test_key}_trend"),
                )

        signature = (
            self.get_state("file_fingerprint"),
            data_name,
            table_key,
            variable,
            transformation,
            date_range,
            source,
            tuple(selected_tests),
            float(alpha),
            tuple(sorted(test_trends.items())),
        )
        if output_container.button(
            "运行检验",
            type="primary",
            disabled=not selected_tests,
            key=self._widget_key("run_tests"),
        ):
            try:
                with st_obj.spinner("正在调用 TsTests 执行检验..."):
                    results = run_selected_stationarity_tests(
                        sources[source],
                        selected_tests,
                        alpha=alpha,
                        test_trends=test_trends,
                    )
                self.set_state("test_results", results)
                self.set_state("test_signature", signature)
            except Exception as exc:  # noqa: BLE001 - selected statistical test boundary
                self.set_state("test_results", None)
                self.set_state("test_signature", None)
                output_container.error(f"平稳性检验无法执行：{exc}")

        results = self.get_state("test_results")
        saved_signature = self.get_state("test_signature")
        if results is None or saved_signature != signature:
            return

        output_container.caption(
            f"当前结果对象：{source_labels[source]}；"
            f"显著性水平 {alpha:g}。各检验按表中所列确定性项执行。"
        )
        failed = results.loc[results["错误"].ne(""), ["检验", "错误"]]
        for _, row in failed.iterrows():
            output_container.warning(f"{row['检验']}未完成：{row['错误']}")

        display = results.drop(columns=["检验代码"]).copy()
        for column in ["统计量", "P值", "临界值"]:
            display[column] = display[column].map(
                lambda value: (
                    None if pd.isna(value) else round(float(value), 6)
                )
            )
        output_container.dataframe(
            display,
            width="stretch",
            hide_index=True,
        )
        output_container.download_button(
            "下载结果",
            data=results.to_csv(index=False, encoding="utf-8-sig").encode(
                "utf-8-sig"
            ),
            file_name=f"{variable}_平稳性检验.csv",
            mime="text/csv",
            type="primary",
            key=self._widget_key("download_tests"),
        )

    def _remember_selection(self, key: str, value) -> bool:
        """记录选择；变化时统一清除所有派生结果。"""
        if self.get_state(key) == value:
            return False
        self.set_state(key, value)
        self._clear_analysis_results()
        return True

    def _clear_analysis_results(self) -> None:
        for key in self._RESULT_STATE_KEYS:
            self.set_state(key, None)

    def _reset_uploaded_data(self, st_obj) -> None:
        for key in (
            "data_tables",
            "file_fingerprint",
            "file_name",
            "selected_table_key",
            "selected_variable",
            "selected_transformation",
        ):
            self.set_state(key, None)
        self._clear_analysis_results()
        self._clear_widget_state(st_obj, self._dependent_widget_keys())

    @staticmethod
    def _clear_widget_state(st_obj, keys) -> None:
        state = getattr(st_obj, "session_state", None)
        if state is None:
            return
        for key in keys:
            state.pop(key, None)


__all__ = [
    "StationarityAnalysisComponent",
    "resolve_table_frequency",
    "transformation_options_for_frequency",
]
