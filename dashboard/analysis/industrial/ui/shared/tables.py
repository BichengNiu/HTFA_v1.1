"""
数据表格组件模块
提供各种类型的数据表格组件，基于Streamlit和Pandas实现
"""

import pandas as pd
import numpy as np
import streamlit as st
from typing import Dict, Any, Optional, List, Union
import io
import logging
from datetime import datetime

from dashboard.analysis.industrial.ui.shared.base import BaseAnalysisComponent

logger = logging.getLogger(__name__)


class TableComponent(BaseAnalysisComponent):
    """
    基础表格组件类
    提供通用的表格创建和格式化功能
    """

    def __init__(self, state_manager):
        """初始化表格组件"""
        super().__init__(state_manager)

        self.table_config = {
            'hide_index': True,
            'use_container_width': True,
            'height': None
        }

        self.default_style = {
            'positive_color': '#ffcdd2',
            'negative_color': '#c8e6c9',
            'decimal_places': 2,
            'percentage_format': '{:.2%}'
        }

    def set_table_config(self, config: Dict[str, Any]):
        """
        设置表格配置

        Args:
            config: 表格配置字典
        """
        self.table_config.update(config)
        logger.debug(f"更新表格配置: {config}")

    def format_numeric_columns(
        self,
        df: pd.DataFrame,
        decimal_places: int = 2,
        exclude_columns: List[str] = None
    ) -> pd.DataFrame:
        """
        格式化数值列

        Args:
            df: 数据框
            decimal_places: 小数位数
            exclude_columns: 排除的列名列表

        Returns:
            格式化后的数据框
        """
        try:
            df_formatted = df.copy()
            exclude_columns = exclude_columns or []

            numeric_columns = df_formatted.select_dtypes(include=[np.number]).columns
            numeric_columns = [col for col in numeric_columns if col not in exclude_columns]

            for col in numeric_columns:
                df_formatted[col] = df_formatted[col].round(decimal_places)

            return df_formatted

        except Exception as e:
            self.handle_error(e, "格式化数值列")
            return df

    def format_percentage_columns(
        self,
        df: pd.DataFrame,
        percentage_columns: List[str]
    ) -> pd.DataFrame:
        """
        格式化百分比列

        Args:
            df: 数据框
            percentage_columns: 百分比列名列表

        Returns:
            格式化后的数据框
        """
        try:
            df_formatted = df.copy()

            for col in percentage_columns:
                if col in df_formatted.columns:
                    df_formatted[col] = pd.to_numeric(df_formatted[col], errors='coerce')

            return df_formatted

        except Exception as e:
            self.handle_error(e, "格式化百分比列")
            return df

    def apply_color_coding(
        self,
        df: pd.DataFrame,
        color_columns: List[str] = None
    ):
        """
        应用颜色编码

        Args:
            df: 数据框
            color_columns: 需要颜色编码的列名列表

        Returns:
            带样式的数据框
        """
        try:
            color_columns = color_columns or []

            styled_df = df.style

            if color_columns:
                styled_df = styled_df.apply(
                    lambda x: x.map(self.highlight_positive_negative),
                    subset=color_columns
                )

            return styled_df

        except Exception as e:
            self.handle_error(e, "应用颜色编码")
            return df.style

    def highlight_positive_negative(self, val: Union[float, str]) -> str:
        """
        高亮正负值

        Args:
            val: 数值

        Returns:
            CSS样式字符串
        """
        try:
            if isinstance(val, str):
                val_str = val.replace('%', '')
            else:
                val_str = str(val)

            val_float = float(val_str)

            if val_float > 0:
                return f'background-color: {self.default_style["positive_color"]}'
            elif val_float < 0:
                return f'background-color: {self.default_style["negative_color"]}'
            return ''

        except (ValueError, TypeError):
            return ''

    def sort_dataframe(
        self,
        df: pd.DataFrame,
        sort_column: str,
        ascending: bool = True
    ) -> pd.DataFrame:
        """
        排序数据框

        Args:
            df: 数据框
            sort_column: 排序列名
            ascending: 是否升序

        Returns:
            排序后的数据框
        """
        try:
            if sort_column not in df.columns:
                logger.warning(f"排序列 '{sort_column}' 不存在")
                return df

            df_sorted = df.copy()

            if df_sorted[sort_column].dtype == 'object':
                sort_values = pd.to_numeric(
                    df_sorted[sort_column].astype(str).str.replace('%', ''),
                    errors='coerce'
                )
                df_sorted[f'{sort_column}_numeric'] = sort_values
                df_sorted = df_sorted.sort_values(
                    by=f'{sort_column}_numeric',
                    ascending=ascending,
                    na_position='last'
                ).drop(columns=[f'{sort_column}_numeric'])
            else:
                df_sorted = df_sorted.sort_values(
                    by=sort_column,
                    ascending=ascending,
                    na_position='last'
                )

            return df_sorted

        except Exception as e:
            self.handle_error(e, f"排序数据框 (列: {sort_column})")
            return df

    def render_table(
        self,
        df: pd.DataFrame,
        key: str = None,
        **kwargs
    ):
        """
        在Streamlit中渲染表格

        Args:
            df: 数据框或样式化数据框
            key: Streamlit组件的唯一键
            **kwargs: 额外的streamlit参数
        """
        try:
            config = {**self.table_config, **kwargs}

            st.dataframe(df, key=key, **config)

        except Exception as e:
            self.handle_error(e, "渲染表格")

    def render(self):
        """基础渲染方法 - 子类需要重写"""
        st.info("请使用具体的表格组件类")


class SummaryTableComponent(TableComponent):
    """
    摘要表格组件
    用于显示数据摘要表格，包含统计信息和颜色编码
    """

    def create_summary_table(
        self,
        data: pd.DataFrame,
        title: str = "",
        sort_column: str = "环比昨日",
        ascending: bool = False,
        show_summary_sentence: bool = True
    ):
        """
        创建摘要表格

        Args:
            data: 摘要数据
            title: 表格标题
            sort_column: 排序列
            ascending: 是否升序
            show_summary_sentence: 是否显示摘要句子

        Returns:
            样式化的表格
        """
        try:
            if data.empty:
                st.warning("没有可用的摘要数据")
                return data.style

            if title:
                st.markdown(f"**{title}**")

            if show_summary_sentence:
                summary_sentence = self.generate_summary_sentence(data)
                st.markdown(f'<p style="color:red;">{summary_sentence}</p>', unsafe_allow_html=True)

            display_columns = [
                '日度指标名称', '最新日期', '最新值', '昨日值', '环比昨日',
                '上周均值', '上月均值'
            ]
            available_columns = [col for col in display_columns if col in data.columns]
            data_display = data[available_columns].copy()

            data_sorted = self.sort_dataframe(data_display, sort_column, ascending)

            data_formatted = self.format_numeric_columns(
                data_sorted,
                exclude_columns=['环比昨日']
            )

            format_dict = {}

            numeric_cols = ['最新值', '昨日值', '上周均值', '上月均值']
            for col in numeric_cols:
                if col in data_formatted.columns:
                    format_dict[col] = '{:.2f}'

            if '环比昨日' in data_formatted.columns:
                format_dict['环比昨日'] = '{:.2%}'

            styled_table = data_formatted.style.format(format_dict)

            if '环比昨日' in data_formatted.columns:
                styled_table = styled_table.apply(
                    lambda x: x.map(self.highlight_positive_negative),
                    subset=['环比昨日']
                )

            return styled_table

        except Exception as e:
            self.handle_error(e, "创建摘要表格")
            return data.style if not data.empty else pd.DataFrame().style

    def generate_summary_sentence(self, data: pd.DataFrame) -> str:
        """
        生成摘要句子

        Args:
            data: 摘要数据

        Returns:
            摘要句子
        """
        try:
            stats = self.calculate_statistics(data)

            summary_sentence = (
                f"共{stats['total_indicators']}个指标，"
                f"{stats['increase_count']}个上涨（占比{stats['increase_pct']:.1f}%），"
                f"{stats['decrease_count']}个下跌（占比{stats['decrease_pct']:.1f}%）；"
                f"{stats['above_week_mean_count']}个高于上周均值（占比{stats['above_week_mean_pct']:.1f}%），"
                f"{stats['above_month_mean_count']}个高于上月均值（占比{stats['above_month_mean_pct']:.1f}%）。"
            )

            return summary_sentence

        except Exception as e:
            logger.error(f"生成摘要句子失败: {e}")
            return "数据摘要生成失败"

    def calculate_statistics(self, data: pd.DataFrame) -> Dict[str, float]:
        """
        计算统计信息

        Args:
            data: 摘要数据

        Returns:
            统计信息字典
        """
        try:
            total_indicators = len(data)

            dod_numeric = pd.to_numeric(
                data['环比昨日'].astype(str).str.replace('%', ''),
                errors='coerce'
            ) if '环比昨日' in data.columns else pd.Series(dtype=float)

            latest_val = pd.to_numeric(data['最新值'], errors='coerce') if '最新值' in data.columns else pd.Series(dtype=float)
            week_mean = pd.to_numeric(data.get('上周均值', pd.Series(dtype=float)), errors='coerce')
            month_mean = pd.to_numeric(data.get('上月均值', pd.Series(dtype=float)), errors='coerce')

            increase_count = (dod_numeric > 0).sum()
            decrease_count = (dod_numeric < 0).sum()
            above_week_mean_count = (latest_val > week_mean).sum()
            above_month_mean_count = (latest_val > month_mean).sum()

            increase_pct = (increase_count / total_indicators * 100) if total_indicators > 0 else 0
            decrease_pct = (decrease_count / total_indicators * 100) if total_indicators > 0 else 0
            above_week_mean_pct = (above_week_mean_count / total_indicators * 100) if total_indicators > 0 else 0
            above_month_mean_pct = (above_month_mean_count / total_indicators * 100) if total_indicators > 0 else 0

            return {
                'total_indicators': total_indicators,
                'increase_count': increase_count,
                'decrease_count': decrease_count,
                'above_week_mean_count': above_week_mean_count,
                'above_month_mean_count': above_month_mean_count,
                'increase_pct': increase_pct,
                'decrease_pct': decrease_pct,
                'above_week_mean_pct': above_week_mean_pct,
                'above_month_mean_pct': above_month_mean_pct
            }

        except Exception as e:
            logger.error(f"计算统计信息失败: {e}")
            return {
                'total_indicators': 0,
                'increase_count': 0,
                'decrease_count': 0,
                'above_week_mean_count': 0,
                'above_month_mean_count': 0,
                'increase_pct': 0,
                'decrease_pct': 0,
                'above_week_mean_pct': 0,
                'above_month_mean_pct': 0
            }

    def render(self):
        """渲染摘要表格组件"""
        st.subheader("数据摘要表格")

        summary_data = self.get_data_from_state('summary_table_data')

        if self.validate_data(summary_data):
            styled_table = self.create_summary_table(
                data=summary_data,
                title="数据摘要"
            )

            self.render_table(styled_table, key="summary_table")
        else:
            st.warning("没有可用的摘要数据")


class DataTableComponent(TableComponent):
    """
    数据表格组件
    用于显示大型数据集，支持搜索、分页和导出功能
    """

    def create_data_table(
        self,
        data: pd.DataFrame,
        title: str = "",
        page_size: int = 50,
        enable_search: bool = True,
        enable_export: bool = True
    ):
        """
        创建数据表格

        Args:
            data: 数据框
            title: 表格标题
            page_size: 每页显示行数
            enable_search: 是否启用搜索
            enable_export: 是否启用导出
        """
        try:
            if data.empty:
                st.warning("没有可用的数据")
                return

            if title:
                st.markdown(f"**{title}**")

            filtered_data = data
            if enable_search:
                search_term = st.text_input("搜索数据", key=f"search_{title}")
                if search_term:
                    filtered_data = self.filter_data_by_search(data, search_term)

            if len(filtered_data) > page_size:
                total_pages = (len(filtered_data) - 1) // page_size + 1
                page_number = st.selectbox(
                    "选择页面",
                    range(1, total_pages + 1),
                    key=f"page_{title}"
                )
                paginated_data = self.paginate_data(filtered_data, page_number, page_size)
            else:
                paginated_data = filtered_data

            st.info(f"显示 {len(paginated_data)} / {len(filtered_data)} 行数据")

            self.render_table(paginated_data, key=f"data_table_{title}")

            if enable_export:
                self.render_export_buttons(filtered_data, title)

        except Exception as e:
            self.handle_error(e, "创建数据表格")

    def filter_data_by_search(self, data: pd.DataFrame, search_term: str) -> pd.DataFrame:
        """
        根据搜索词过滤数据

        Args:
            data: 数据框
            search_term: 搜索词

        Returns:
            过滤后的数据框
        """
        try:
            if not search_term:
                return data

            mask = data.astype(str).apply(
                lambda x: x.str.contains(search_term, case=False, na=False)
            ).any(axis=1)

            return data[mask]

        except Exception as e:
            logger.error(f"搜索数据失败: {e}")
            return data

    def paginate_data(
        self,
        data: pd.DataFrame,
        page_number: int,
        page_size: int
    ) -> pd.DataFrame:
        """
        分页数据

        Args:
            data: 数据框
            page_number: 页码（从1开始）
            page_size: 每页大小

        Returns:
            分页后的数据框
        """
        try:
            start_idx = (page_number - 1) * page_size
            end_idx = start_idx + page_size
            return data.iloc[start_idx:end_idx]

        except Exception as e:
            logger.error(f"分页数据失败: {e}")
            return data

    def export_to_csv(self, data: pd.DataFrame) -> bytes:
        """
        导出为CSV

        Args:
            data: 数据框

        Returns:
            CSV字节数据（UTF-8编码）
        """
        try:
            csv_string = data.to_csv(index=False, encoding='utf-8-sig')
            return csv_string.encode('utf-8-sig')
        except Exception as e:
            logger.error(f"导出CSV失败: {e}")
            return b""

    def export_to_excel(self, data: pd.DataFrame) -> bytes:
        """
        导出为Excel

        Args:
            data: 数据框

        Returns:
            Excel字节数据
        """
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                data.to_excel(writer, index=False, sheet_name='数据')
            return output.getvalue()
        except Exception as e:
            logger.error(f"导出Excel失败: {e}")
            return b""

    def render_export_buttons(self, data: pd.DataFrame, title: str):
        """
        渲染导出按钮

        Args:
            data: 数据框
            title: 标题
        """
        try:
            col1, col2 = st.columns(2)

            with col1:
                csv_data = self.export_to_csv(data)
                if csv_data:
                    st.download_button(
                        label="下载 CSV",
                        data=csv_data,
                        file_name=f"{title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        key=f"csv_{title}",
                        type="primary"
                    )

            with col2:
                excel_data = self.export_to_excel(data)
                if excel_data:
                    st.download_button(
                        label="下载 Excel",
                        data=excel_data,
                        file_name=f"{title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"excel_{title}",
                        type="primary"
                    )

        except Exception as e:
            self.handle_error(e, "渲染导出按钮")

    def render(self):
        """渲染数据表格组件"""
        st.subheader("数据表格")

        table_data = self.get_data_from_state('table_data')

        if self.validate_data(table_data):
            self.create_data_table(
                data=table_data,
                title="数据表格",
                page_size=50
            )
        else:
            st.warning("没有可用的表格数据")
