"""与平稳性检验并列的结构突变检验界面。"""

from __future__ import annotations

import pandas as pd

from htfa.data.tabular import numeric_variable_names
from htfa.exploration.analysis.stationarity import (
    prepare_selected_series,
)
from htfa.exploration.analysis.structural_break import (
    STRUCTURAL_BREAK_LAG_METHODS,
    STRUCTURAL_BREAK_MODELS,
    run_zivot_andrews_test,
)
from htfa.exploration.ui.stationarity import (
    StationarityAnalysisComponent,
)


class StructuralBreakAnalysisComponent(StationarityAnalysisComponent):
    """单变量 Zivot–Andrews 结构突变检验组件。"""

    _DEPENDENT_WIDGET_SUFFIXES = (
        *StationarityAnalysisComponent._DEPENDENT_WIDGET_SUFFIXES,
        "model",
        "lag_method",
        "alpha",
        "run_test",
        "download_test",
    )

    def __init__(self):
        super().__init__("structural_break", "结构突变检验")

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
            return

        variable = st_obj.selectbox(
            "选择变量",
            options=variables,
            key=self._widget_key("variable_select"),
        )
        self._remember_selection("selected_variable", variable)
        try:
            series, _ = prepare_selected_series(data, variable)
        except Exception as exc:  # noqa: BLE001 - user-facing variable preparation boundary
            st_obj.error(f"变量准备失败：{exc}")
            return

        self._render_structural_break_test(
            st_obj,
            series=series,
            variable=variable,
            data_name=data_name,
            table_key=table_key,
        )
        return

    def _render_structural_break_test(
        self,
        st_obj,
        *,
        series: pd.Series,
        variable: str,
        data_name: str,
        table_key: str,
    ) -> None:
        st_obj.markdown("---")
        st_obj.markdown("### 结构突变检验")
        st_obj.caption(
            "Zivot–Andrews 检验在未知突变时点下检验单位根，"
            "原假设为“允许一个结构突变时序列仍存在单位根”。"
        )

        option_columns = st_obj.columns(3)
        model = option_columns[0].selectbox(
            "突变形式",
            options=list(STRUCTURAL_BREAK_MODELS),
            format_func=lambda key: STRUCTURAL_BREAK_MODELS[key],
            key=self._widget_key("model"),
        )
        lag_method = option_columns[1].selectbox(
            "滞后选择方法",
            options=list(STRUCTURAL_BREAK_LAG_METHODS),
            format_func=lambda key: STRUCTURAL_BREAK_LAG_METHODS[key],
            key=self._widget_key("lag_method"),
        )
        alpha = option_columns[2].selectbox(
            "显著性水平",
            options=[0.01, 0.05, 0.10],
            index=1,
            key=self._widget_key("alpha"),
        )

        signature = (
            self.get_state("file_fingerprint"),
            data_name,
            table_key,
            variable,
            model,
            lag_method,
            float(alpha),
        )
        if st_obj.button(
            "运行检验",
            type="primary",
            key=self._widget_key("run_test"),
        ):
            try:
                with st_obj.spinner(
                    "正在调用 Ts.ZivotAndrewsTest 执行检验..."
                ):
                    result = run_zivot_andrews_test(
                        series,
                        alpha=alpha,
                        model=model,
                        lag_method=lag_method,
                    )
                self.set_state("test_results", result)
                self.set_state("test_signature", signature)
            except Exception as exc:  # noqa: BLE001 - selected statistical test boundary
                self.set_state("test_results", None)
                self.set_state("test_signature", None)
                st_obj.error(f"结构突变检验无法执行：{exc}")

        result = self.get_state("test_results")
        if result is None or self.get_state("test_signature") != signature:
            st_obj.info("设置突变形式和滞后选择方法后运行检验。")
            return

        display = result.copy()
        for column in ["统计量", "临界值"]:
            display[column] = display[column].map(
                lambda value: round(float(value), 6)
            )
        st_obj.dataframe(display, width="stretch", hide_index=True)
        st_obj.download_button(
            "下载结果",
            data=result.to_csv(index=False, encoding="utf-8-sig").encode(
                "utf-8-sig"
            ),
            file_name=f"{variable}_结构突变检验.csv",
            mime="text/csv",
            type="primary",
            key=self._widget_key("download_test"),
        )


__all__ = ["StructuralBreakAnalysisComponent"]
