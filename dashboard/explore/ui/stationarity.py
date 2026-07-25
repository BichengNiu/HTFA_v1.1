# -*- coding: utf-8 -*-
"""平稳性检验的 Streamlit 单变量工作流。"""

from __future__ import annotations

import logging
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd

from dashboard.explore.analysis.stationarity import (
    TABLE_FREQUENCIES,
    TEST_LABELS,
    TEST_TREND_LABELS,
    TEST_TREND_OPTIONS,
    TRANSFORMATIONS,
    create_correlogram_figure,
    create_time_series_figure,
    normalize_frequency,
    numeric_variable_names,
    prepare_selected_series,
    resolve_correlation_lags,
    resolve_year_over_year_lag,
    run_selected_stationarity_tests,
    summarize_series,
    transform_series,
)
from dashboard.explore.core.data_source import (
    FREQUENCY_LABELS,
    fingerprint_uploaded_file,
    format_table_option,
    load_stationarity_tables,
)
from dashboard.explore.core.constants import FREQUENCY_DISPLAY_NAMES
from dashboard.explore.preprocessing.frequency_alignment import (
    infer_series_frequency,
)
from dashboard.explore.ui.base import TimeSeriesAnalysisComponent


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
        # 清理旧版批量工作流可能遗留的状态。
        "diff_options",
        "diff_options_vars",
        "processed_data",
        "process_results",
        "failed_vars",
    )

    _DEPENDENT_WIDGET_SUFFIXES = (
        "table_select",
        "variable_select",
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

    def render_analysis_interface(
        self,
        st_obj,
        data: pd.DataFrame,
        data_name: str,
    ):
        """兼容基类入口：将外部 DataFrame 视为单表数据。"""
        return self._render_variable_workflow(
            st_obj,
            data,
            table_key="table",
            data_name=data_name,
        )

    def render(self, st_obj, tab_index: int = 0):
        """渲染独立上传和三段式单变量分析流程。"""
        st_obj.markdown("### 1. 数据与变量选择")
        uploaded_file = st_obj.file_uploader(
            "上传数据集",
            type=["csv", "xlsx", "xls"],
            key=self._widget_key("file_uploader"),
            help="经济数据库工作簿将解析为不同频率的数据表；CSV 作为单表读取。",
        )

        if uploaded_file is None:
            if self.get_state("file_fingerprint") is not None:
                self._reset_uploaded_data(st_obj)
            st_obj.info("请先上传 CSV、XLS 或 XLSX 数据集")
            return None

        try:
            fingerprint = fingerprint_uploaded_file(uploaded_file)
            if fingerprint != self.get_state("file_fingerprint"):
                tables = load_stationarity_tables(uploaded_file)
                self.set_state("data_tables", tables)
                self.set_state("file_fingerprint", fingerprint)
                self.set_state("file_name", uploaded_file.name)
                self.set_state("selected_table_key", None)
                self.set_state("selected_variable", None)
                self.set_state("selected_transformation", None)
                self._clear_analysis_results()
                self._clear_widget_state(
                    st_obj,
                    self._dependent_widget_keys(),
                )
        except Exception as exc:
            self._reset_uploaded_data(st_obj)
            st_obj.error(f"文件读取或数据库解析失败：{exc}")
            return None

        tables = self.get_state("data_tables", {})
        if not tables:
            st_obj.error("数据集没有可分析的数据表")
            return None

        selected_table_key = st_obj.selectbox(
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
        return self._render_variable_workflow(
            st_obj,
            data,
            table_key=selected_table_key,
            data_name=f"{file_name}-{table_label}",
        )

    def _render_variable_workflow(
        self,
        st_obj,
        data: pd.DataFrame,
        *,
        table_key: str,
        data_name: str,
    ):
        variables = numeric_variable_names(data)
        if not variables:
            st_obj.error("所选数据表没有实数型变量")
            return None

        selected_variable = st_obj.selectbox(
            "选择变量",
            options=variables,
            key=self._widget_key("variable_select"),
        )
        self._remember_selection("selected_variable", selected_variable)

        try:
            original_series, time_label = prepare_selected_series(
                data,
                selected_variable,
            )
        except Exception as exc:
            st_obj.error(f"变量准备失败：{exc}")
            return None

        frequency = resolve_table_frequency(table_key, original_series)
        self._render_series_status(
            st_obj,
            original_series,
            frequency=frequency,
            time_label=time_label,
        )
        self._render_original_diagnostics(
            st_obj,
            original_series,
            selected_variable,
        )
        processed_series, transformation = self._render_preprocessing(
            st_obj,
            original_series,
            selected_variable,
            frequency,
        )
        self._render_stationarity_tests(
            st_obj,
            original_series=original_series,
            processed_series=processed_series,
            variable=selected_variable,
            transformation=transformation,
            data_name=data_name,
            table_key=table_key,
        )
        return None

    def _render_series_status(
        self,
        st_obj,
        series: pd.Series,
        *,
        frequency: str,
        time_label: Optional[str],
    ) -> None:
        valid = int(series.notna().sum())
        missing = int(series.isna().sum())
        columns = st_obj.columns(4)
        columns[0].metric("总观测数", f"{len(series):,}")
        columns[1].metric("有效观测数", f"{valid:,}")
        columns[2].metric("缺失值", f"{missing:,}")
        columns[3].metric(
            "识别频率",
            FREQUENCY_DISPLAY_NAMES.get(frequency, "未确定"),
        )
        if isinstance(series.index, pd.DatetimeIndex):
            st_obj.caption(
                f"时间轴：{time_label or '时间索引'}；"
                f"{series.index.min():%Y-%m-%d} 至 "
                f"{series.index.max():%Y-%m-%d}"
            )
        else:
            st_obj.warning(
                "未识别到时间列，当前按行位置绘图；同比处理将不可用。"
            )

    def _render_original_diagnostics(
        self,
        st_obj,
        series: pd.Series,
        variable: str,
    ) -> None:
        st_obj.markdown("---")
        st_obj.markdown("### 2. 序列诊断与预处理")
        st_obj.markdown("#### 2.1 原始变量")

        plot_column, summary_column = st_obj.columns([1.35, 1])
        with plot_column:
            try:
                figure = create_time_series_figure(
                    series,
                    title=f"{variable} · 原始序列",
                )
                try:
                    st_obj.pyplot(
                        figure,
                        width="stretch",
                        clear_figure=True,
                    )
                finally:
                    plt.close(figure)
            except Exception as exc:
                st_obj.warning(f"原始序列图无法绘制：{exc}")

        with summary_column:
            try:
                summary = summarize_series(series)
                st_obj.code(summary, language=None)
            except Exception as exc:
                st_obj.warning(f"Ts 统计摘要无法生成：{exc}")

        self._render_correlogram(
            st_obj,
            series,
            title_prefix=f"{variable} · 原始序列",
            include_acf=True,
            include_pacf=True,
        )

    def _render_preprocessing(
        self,
        st_obj,
        series: pd.Series,
        variable: str,
        frequency: str,
    ) -> tuple[Optional[pd.Series], str]:
        st_obj.markdown("#### 2.2 可选预处理")
        options = transformation_options_for_frequency(frequency)
        transformation = st_obj.selectbox(
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
        except Exception as exc:
            st_obj.error(f"预处理失败：{exc}")
            return None, transformation

        lost = int(processed.isna().sum() - series.isna().sum())
        st_obj.success(
            f"已生成“{TRANSFORMATIONS[transformation].label}”序列；"
            f"差分新增 {max(0, lost)} 个前置缺失值。"
        )
        try:
            figure = create_time_series_figure(
                processed,
                title=(
                    f"{variable} · "
                    f"{TRANSFORMATIONS[transformation].label}"
                ),
            )
            try:
                st_obj.pyplot(
                    figure,
                    width="stretch",
                    clear_figure=True,
                )
            finally:
                plt.close(figure)
        except Exception as exc:
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
    ) -> None:
        try:
            nlags, maximum = resolve_correlation_lags(series)
            st_obj.caption(
                f"相关图使用 {series.notna().sum():,} 个有效观测，"
                f"自动选择 {nlags} 阶滞后（PACF 最大允许 {maximum} 阶）。"
            )
            figure = create_correlogram_figure(
                series,
                nlags=nlags,
                title_prefix=title_prefix,
                include_acf=include_acf,
                include_pacf=include_pacf,
            )
            try:
                st_obj.pyplot(
                    figure,
                    width="stretch",
                    clear_figure=True,
                )
            finally:
                plt.close(figure)
        except Exception as exc:
            st_obj.warning(f"ACF/PACF 无法绘制：{exc}")

    def _render_stationarity_tests(
        self,
        st_obj,
        *,
        original_series: pd.Series,
        processed_series: Optional[pd.Series],
        variable: str,
        transformation: str,
        data_name: str,
        table_key: str,
    ) -> None:
        st_obj.markdown("---")
        st_obj.markdown("### 3. 平稳性检验")

        sources = {"original": original_series}
        source_labels = {"original": "原始变量"}
        if processed_series is not None:
            sources["processed"] = processed_series
            source_labels["processed"] = (
                f"处理后变量（{TRANSFORMATIONS[transformation].label}）"
            )

        source = st_obj.radio(
            "检验对象",
            options=list(sources),
            format_func=lambda key: source_labels[key],
            horizontal=True,
            key=self._widget_key("test_source"),
        )
        selected_tests = st_obj.multiselect(
            "选择检验方法",
            options=list(TEST_LABELS),
            default=["adf", "kpss"],
            format_func=lambda key: TEST_LABELS[key],
            key=self._widget_key("test_methods"),
        )
        alpha = st_obj.selectbox(
            "显著性水平",
            options=[0.01, 0.05, 0.10],
            index=1,
            key=self._widget_key("test_alpha"),
        )
        test_trends = {}
        if selected_tests:
            trend_columns = st_obj.columns(min(3, len(selected_tests)))
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
            source,
            tuple(selected_tests),
            float(alpha),
            tuple(sorted(test_trends.items())),
        )
        if st_obj.button(
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
            except Exception as exc:
                self.set_state("test_results", None)
                self.set_state("test_signature", None)
                st_obj.error(f"平稳性检验无法执行：{exc}")

        results = self.get_state("test_results")
        saved_signature = self.get_state("test_signature")
        if results is None or saved_signature != signature:
            st_obj.info("请选择检验方法并运行；参数变化后需要重新检验。")
            return

        st_obj.caption(
            f"当前结果对象：{source_labels[source]}；"
            f"显著性水平 {alpha:g}。各检验按表中所列确定性项执行。"
        )
        failed = results.loc[results["错误"].ne(""), ["检验", "错误"]]
        for _, row in failed.iterrows():
            st_obj.warning(f"{row['检验']}未完成：{row['错误']}")

        display = results.drop(columns=["检验代码"]).copy()
        for column in ["统计量", "P值", "临界值"]:
            display[column] = display[column].map(
                lambda value: (
                    None if pd.isna(value) else round(float(value), 6)
                )
            )
        st_obj.dataframe(
            display,
            width="stretch",
            hide_index=True,
        )
        st_obj.download_button(
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
