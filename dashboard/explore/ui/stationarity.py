# -*- coding: utf-8 -*-
"""
平稳性分析组件
重构为三功能区布局：上传数据、平稳性检验、数据处理
"""

import streamlit as st
import pandas as pd
import logging
import io
from datetime import datetime
from typing import Tuple

from dashboard.explore.ui.base import TimeSeriesAnalysisComponent
from dashboard.explore import run_stationarity_tests

logger = logging.getLogger(__name__)


class StationarityAnalysisComponent(TimeSeriesAnalysisComponent):
    """平稳性分析组件 - 三功能区布局"""

    def __init__(self):
        super().__init__("stationarity", "平稳性分析")

    def render_analysis_interface(self, st_obj, data: pd.DataFrame, data_name: str):
        """实现基类抽象方法 - 渲染分析界面"""
        return self._render_main(st_obj, data, data_name)

    def render(self, st_obj, tab_index: int = 0):
        """渲染平稳性分析界面（覆盖基类方法以支持自定义数据上传）"""
        # ==================== 功能区1: 上传数据 ====================
        st_obj.markdown("### 上传数据")

        uploaded_file = st_obj.file_uploader(
            "选择数据文件",
            type=['csv', 'xlsx', 'xls'],
            key="stationarity_file_uploader"
        )

        data = None
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    data = pd.read_csv(uploaded_file)
                else:
                    data = pd.read_excel(uploaded_file)

                self.set_state('uploaded_data', data)
                self.set_state('file_name', uploaded_file.name)
                st_obj.success(f"已加载: {uploaded_file.name}, 形状: {data.shape}")
            except Exception as e:
                st_obj.error(f"文件读取失败: {e}")
                return
        else:
            data = self.get_state('uploaded_data')
            file_name = self.get_state('file_name')
            if data is not None:
                st_obj.info(f"当前数据: {file_name}, 形状: {data.shape}")

        if data is None:
            st_obj.info("请上传数据文件")
            return

        # 渲染主分析界面
        return self._render_main(st_obj, data, self.get_state('file_name') or 'data')

    def _render_main(self, st_obj, data: pd.DataFrame, data_name: str):
        """渲染主分析界面"""
        # ==================== 功能区2: 平稳性检验 ====================
        st_obj.markdown("---")
        st_obj.markdown("### 平稳性检验")

        # 显著性水平下拉菜单
        alpha = st_obj.selectbox(
            "显著性水平:",
            options=[0.01, 0.05, 0.10],
            index=1,
            key="stationarity_alpha_select"
        )
        self.set_state('alpha', alpha)

        # 开始检验按钮
        if st_obj.button("开始检验", type="primary", key="stationarity_test_btn"):
            with st_obj.spinner("正在执行平稳性检验..."):
                test_results = run_stationarity_tests(data, alpha)
                self.set_state('test_results', test_results)
                st_obj.success("检验完成")

        # 显示检验结果
        test_results = self.get_state('test_results')
        if test_results is not None and len(test_results) > 0:
            st_obj.dataframe(test_results, use_container_width=True)

            # 下载按钮
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_data = test_results.to_csv(index=False, encoding='utf-8-sig')
            st_obj.download_button(
                label="下载数据",
                data=csv_data.encode('utf-8-sig'),
                file_name=f"平稳性检验结果_{timestamp}.csv",
                mime="text/csv",
                type="primary",
                key="stationarity_download_test_btn"
            )

        # ==================== 功能区3: 数据处理 ====================
        st_obj.markdown("---")
        st_obj.markdown("### 数据处理")

        if test_results is None or len(test_results) == 0:
            st_obj.info("请先执行平稳性检验")
            return

        # 筛选非平稳变量
        nonstationary_vars = test_results[
            test_results['ADF检验结果'] == '非平稳'
        ]['变量名'].tolist()

        if len(nonstationary_vars) == 0:
            st_obj.success("所有变量均通过平稳性检验，无需处理")
            return

        st_obj.info(f"发现 {len(nonstationary_vars)} 个非平稳变量需要处理")

        # 自动检测差分方案（无需按钮，自动执行）
        options_df = self.get_state('diff_options')
        cached_vars = self.get_state('diff_options_vars')

        # 当非平稳变量列表变化时重新检测
        if options_df is None or cached_vars != nonstationary_vars:
            from dashboard.explore.analysis.stationarity import auto_detect_differencing_options
            alpha = self.get_state('alpha') or 0.05
            options_df = auto_detect_differencing_options(data, nonstationary_vars, alpha)
            self.set_state('diff_options', options_df)
            self.set_state('diff_options_vars', nonstationary_vars)
            # 清除之前的处理结果
            self.set_state('process_results', None)
            self.set_state('failed_vars', None)

        # 显示差分方案表格
        if options_df is not None and len(options_df) > 0:
            # 添加用户选择列
            if '用户选择' not in options_df.columns:
                options_df = options_df.copy()
                options_df['用户选择'] = options_df['推荐处理']

            # 表格配置
            column_config = {
                '变量名': st.column_config.TextColumn('变量名', disabled=True),
                '频率': st.column_config.TextColumn('频率', disabled=True),
                '环比差分': st.column_config.TextColumn('环比差分', disabled=True),
                '同比差分': st.column_config.TextColumn('同比差分', disabled=True),
                '推荐处理': st.column_config.TextColumn('推荐处理', disabled=True),
                '用户选择': st.column_config.SelectboxColumn(
                    '用户选择',
                    options=['不处理', '环比差分', '同比差分'],
                    required=True
                )
            }

            edited_options = st_obj.data_editor(
                options_df,
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
                key="diff_options_editor"
            )

            # 约束：环比和同比都非平稳时强制"不处理"
            for idx in range(len(edited_options)):
                mom = edited_options.loc[idx, '环比差分']
                yoy = edited_options.loc[idx, '同比差分']
                if mom != '平稳' and yoy != '平稳':
                    if edited_options.loc[idx, '用户选择'] != '不处理':
                        st_obj.warning(f"变量'{edited_options.loc[idx, '变量名']}'的环比和同比差分均非平稳，已自动设为'不处理'")
                        edited_options.loc[idx, '用户选择'] = '不处理'

            self.set_state('diff_options', edited_options)

            # 执行处理按钮
            if st_obj.button("执行处理", type="primary", key="apply_diff_btn"):
                with st_obj.spinner("正在应用差分处理并检验..."):
                    from dashboard.explore.analysis.stationarity import apply_automated_transformations
                    alpha = self.get_state('alpha') or 0.05
                    processed_df, results_df, failed_vars = apply_automated_transformations(
                        data, edited_options, alpha
                    )
                    self.set_state('processed_data', processed_df)
                    self.set_state('process_results', results_df)
                    self.set_state('failed_vars', failed_vars)

        # 显示处理结果
        process_results = self.get_state('process_results')
        failed_vars = self.get_state('failed_vars')

        if process_results is not None:
            st_obj.markdown("---")
            st_obj.markdown("#### 处理结果")

            if failed_vars is None or len(failed_vars) == 0:
                st_obj.success("所有变量均通过平稳性检验")
            else:
                st_obj.warning(f"以下变量未通过检验：{', '.join(failed_vars)}")

            # 数据下载按钮
            self._render_download_button(st_obj, data, test_results, process_results)

    def _prepare_export_data(
        self,
        original_data: pd.DataFrame,
        test_results: pd.DataFrame,
        process_results: pd.DataFrame,
        processed_data: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        准备导出数据

        Returns:
            Tuple[最终数据DataFrame, 元数据DataFrame]
        """
        # 识别原本平稳的变量
        stationary_vars = test_results[
            test_results['ADF检验结果'] == '平稳'
        ]['变量名'].tolist()

        # 整合最终数据
        final_columns = {}
        metadata_rows = []

        # 原本平稳的变量 - 使用原始数据
        for var in stationary_vars:
            if var in original_data.columns:
                final_columns[var] = original_data[var]
                metadata_rows.append({
                    '变量名': var,
                    '处理方法': '不处理',
                    '平稳性': '平稳'
                })

        # 被处理的变量 - 使用处理后数据
        for _, row in process_results.iterrows():
            var = row['变量名']
            if var in processed_data.columns:
                final_columns[var] = processed_data[var]
                metadata_rows.append({
                    '变量名': var,
                    '处理方法': row['处理方法'],
                    '平稳性': row['ADF检验结果']
                })

        final_data = pd.DataFrame(final_columns)
        final_data['日期'] = original_data.iloc[final_data.index, 0].values
        final_data = final_data[['日期'] + [c for c in final_data.columns if c != '日期']]
        final_data = final_data.sort_values('日期', ascending=False).reset_index(drop=True)
        metadata = pd.DataFrame(metadata_rows)

        return final_data, metadata

    def _render_download_button(
        self,
        st_obj,
        original_data: pd.DataFrame,
        test_results: pd.DataFrame,
        process_results: pd.DataFrame
    ):
        """渲染数据下载按钮"""
        processed_data = self.get_state('processed_data')

        # 整合最终数据
        final_data, metadata = self._prepare_export_data(
            original_data, test_results, process_results, processed_data
        )

        # 生成Excel文件
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            final_data.to_excel(writer, sheet_name='数据', index=False)
            metadata.to_excel(writer, sheet_name='处理信息', index=False)
        excel_buffer.seek(0)

        # 下载按钮
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st_obj.download_button(
            label="下载数据",
            data=excel_buffer.getvalue(),
            file_name=f"平稳性处理结果_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            key="download_final_data_btn"
        )


__all__ = ['StationarityAnalysisComponent']
