# -*- coding: utf-8 -*-
"""
DFM数据预览组件

提供文件结构诊断、数据预览和格式检测功能
"""

import streamlit as st
import pandas as pd
import io
import logging
from typing import Dict, Any, Optional, List, Tuple

from dashboard.models.DFM.ui import DFMComponent
from dashboard.models.DFM.prep.modules.format_detection import detect_sheet_format


logger = logging.getLogger(__name__)


class DataPreviewComponent(DFMComponent):
    """DFM数据预览组件"""

    def __init__(self):
        """初始化数据预览组件 - 优化版本"""
        super().__init__()
        self._preview_modes = ['基本预览', '详细分析', '格式检测', '性能预览']
        self._max_preview_rows = 100  # 增加预览行数
        self._cache_enabled = True
        self._large_file_threshold = 10 * 1024 * 1024  # 10MB

    def get_component_id(self) -> str:
        """获取组件ID"""
        return "data_preview"

    def get_state_keys(self) -> list:
        """
        获取组件相关的状态键

        Returns:
            List[str]: 状态键列表
        """
        return [
            'dfm_training_data_file',
            'dfm_preview_mode',
            'dfm_preview_sheet_selected',
            'dfm_preview_rows_count'
        ]

    def validate_input(self, data: Dict) -> bool:
        """
        验证输入数据

        Args:
            data: 输入数据字典，包含uploaded_file键

        Returns:
            bool: 验证是否通过
        """
        try:
            uploaded_file = data.get('uploaded_file')

            if uploaded_file is None:
                return False

            # 检查文件是否为Excel格式
            if not uploaded_file.name.lower().endswith(('.xlsx', '.xls')):
                logger.warning(f"不支持的文件格式: {uploaded_file.name}")
                return False

            return True

        except Exception as e:
            logger.error(f"输入验证失败: {e}")
            return False

    def handle_service_error(self, error: Exception) -> None:
        """
        处理服务错误

        Args:
            error: 异常对象
        """
        error_msg = f"数据预览服务错误: {str(error)}"
        logger.error(error_msg)
        st.error(error_msg)

    def render(self, st_obj) -> Optional[Dict[str, Any]]:
        """
        渲染数据预览组件 - 优化版本，支持性能监控

        Args:
            st_obj: Streamlit对象

        Returns:
            预览结果字典或None
        """
        try:
            return self._render_with_monitoring(st_obj)
        except Exception as e:
            self.handle_service_error(e)
            return None

    def _render_with_monitoring(self, st_obj) -> Optional[Dict[str, Any]]:
        """带监控的渲染方法"""
        st_obj.markdown("### [VIEW] 数据文件预览 (优化版)")

        # 获取上传的文件
        uploaded_file = self._get_state('dfm_training_data_file')

        if uploaded_file is None:
            st_obj.info("请先上传数据文件以进行预览。")
            return None

        # 验证输入
        if not self.validate_input({'uploaded_file': uploaded_file}):
            st_obj.error("文件验证失败，无法进行预览。")
            return None

        # 显示文件信息和性能提示
        file_size = len(uploaded_file.getvalue()) if hasattr(uploaded_file, 'getvalue') else 0
        file_size_mb = file_size / (1024 * 1024)

        col1, col2 = st_obj.columns(2)
        with col1:
            st_obj.info(f"[DATA] 当前文件: {uploaded_file.name}")
        with col2:
            st_obj.info(f"[DATA] 文件大小: {file_size_mb:.2f} MB")

        # 大文件警告
        if file_size_mb > 10:
            st_obj.warning(f"[WARNING] 大文件警告：文件大小 {file_size_mb:.2f} MB，预览可能需要较长时间")

        # 渲染文件结构诊断工具
        return self._render_file_diagnosis_tool(st_obj, uploaded_file)

    def _render_file_diagnosis_tool(self, st_obj, uploaded_file) -> Optional[Dict[str, Any]]:
        """
        渲染文件结构诊断工具

        Args:
            st_obj: Streamlit对象
            uploaded_file: 上传的文件对象

        Returns:
            诊断结果字典或None
        """
        with st_obj.expander("[VIEW] 文件结构诊断工具 (可选)", expanded=False):
            if st_obj.button("检查文件结构",
                           key=f"{self.get_state_key_prefix()}_diagnosis",
                           help="查看已上传文件的内部结构，帮助诊断格式问题"):
                try:
                    return self._perform_file_diagnosis(st_obj, uploaded_file)
                except Exception as e:
                    st_obj.error(f"文件结构检查出错: {e}")
                    logger.error(f"文件诊断失败: {e}")
                    return None

        return None

    def _perform_file_diagnosis(self, st_obj, uploaded_file) -> Dict[str, Any]:
        """
        执行文件结构诊断

        Args:
            st_obj: Streamlit对象
            uploaded_file: 上传的文件对象

        Returns:
            诊断结果字典
        """
        if not uploaded_file:
            st_obj.warning("没有找到已上传的文件")
            return {}

        # 读取文件内容
        file_bytes = uploaded_file.getvalue()
        excel_file = io.BytesIO(file_bytes)

        if uploaded_file.name.lower().endswith('.xlsx'):
            return self._diagnose_excel_file(st_obj, excel_file)
        else:
            st_obj.warning("当前只支持Excel文件的结构诊断")
            return {}

    def _diagnose_excel_file(self, st_obj, excel_file) -> Dict[str, Any]:
        """
        诊断Excel文件结构

        Args:
            st_obj: Streamlit对象
            excel_file: Excel文件对象

        Returns:
            诊断结果字典
        """
        try:
            xl_file = pd.ExcelFile(excel_file)
            sheet_names = xl_file.sheet_names

            st_obj.write(f"**[INFO] 文件包含 {len(sheet_names)} 个工作表:**")

            diagnosis_results = {
                'sheet_count': len(sheet_names),
                'sheets': {}
            }

            # 分析每个工作表（不使用嵌套expander）
            for i, sheet_name in enumerate(sheet_names):
                st_obj.markdown(f"**工作表 {i+1}: {sheet_name}**")
                try:
                    sheet_result = self._analyze_sheet(st_obj, excel_file, sheet_name)
                    diagnosis_results['sheets'][sheet_name] = sheet_result

                except Exception as e:
                    st_obj.error(f"读取工作表 '{sheet_name}' 出错: {e}")
                    diagnosis_results['sheets'][sheet_name] = {'error': str(e)}

                # 添加分隔线
                if i < len(sheet_names) - 1:
                    st_obj.markdown("---")

            return diagnosis_results

        except Exception as e:
            st_obj.error(f"Excel文件诊断失败: {e}")
            logger.error(f"Excel诊断失败: {e}")
            return {'error': str(e)}

    def _analyze_sheet(self, st_obj, excel_file, sheet_name: str) -> Dict[str, Any]:
        """
        分析单个工作表

        Args:
            st_obj: Streamlit对象
            excel_file: Excel文件对象
            sheet_name: 工作表名称

        Returns:
            工作表分析结果
        """
        # 检测格式
        format_info = self._detect_sheet_format(excel_file, sheet_name)
        st_obj.write(f"**检测到的格式:** {format_info['format']} (来源: {format_info['source']})")
        st_obj.write(f"**建议参数:** header={format_info['header']}, skiprows={format_info['skiprows']}")

        # 获取数据预览
        df_preview = self._get_sheet_preview(excel_file, sheet_name, nrows=5)

        if df_preview is not None:
            st_obj.write(f"**数据形状:** {df_preview.shape}")
            st_obj.write("**前5行预览:**")
            st_obj.dataframe(df_preview)

            # 分析第一列（可能的日期列）
            if len(df_preview.columns) > 0:
                first_col = df_preview.columns[0]
                date_analysis = self._analyze_date_column(df_preview, first_col)

                st_obj.write(f"**第一列 '{first_col}' 的样本值:** {date_analysis['sample_values']}")

                if date_analysis['is_date']:
                    st_obj.success(f"[SUCCESS] 第一列可以转换为日期: {date_analysis['converted_sample']}")
                else:
                    st_obj.warning("[WARNING] 第一列无法转换为日期")

            return {
                'format_info': format_info,
                'shape': df_preview.shape,
                'columns': list(df_preview.columns),
                'date_analysis': date_analysis if 'date_analysis' in locals() else None
            }
        else:
            st_obj.warning("无法读取工作表数据")
            return {
                'format_info': format_info,
                'error': '无法读取数据'
            }

    def _detect_sheet_format(self, excel_file, sheet_name: str) -> Dict[str, Any]:
        """
        检测工作表格式

        Args:
            excel_file: Excel文件对象
            sheet_name: 工作表名称

        Returns:
            格式信息字典
        """
        try:
            # 使用格式检测函数
            return detect_sheet_format(excel_file, sheet_name)
        except Exception as e:
            logger.error(f"格式检测失败: {e}")
            return {
                'format': 'error',
                'header': 0,
                'skiprows': None,
                'data_start_row': 1,
                'source': 'error',
                'error': str(e)
            }

    def _get_sheet_preview(self, excel_file, sheet_name: str, nrows: int = 5) -> Optional[pd.DataFrame]:
        """
        获取工作表预览数据 - 优化版本，支持缓存

        Args:
            excel_file: Excel文件对象
            sheet_name: 工作表名称
            nrows: 预览行数

        Returns:
            预览数据DataFrame或None
        """
        try:
            # 限制预览行数以提升性能
            max_preview_rows = min(nrows, self._max_preview_rows)

            # 尝试从缓存获取
            cache_key = f"sheet_preview_{sheet_name}_{max_preview_rows}"
            if self._cache_enabled:
                cached_data = self._get_state(f"cache_{cache_key}")
                if cached_data is not None:
                    logger.debug(f"从缓存获取工作表预览: {sheet_name}")
                    return cached_data

            # 读取数据
            df = pd.read_excel(excel_file, sheet_name=sheet_name, nrows=max_preview_rows)

            # 缓存结果（仅缓存小数据）
            if self._cache_enabled and df is not None:
                memory_usage = df.memory_usage(deep=True).sum() / 1024 / 1024
                if memory_usage < 5:  # 小于5MB才缓存
                    self._set_state(f"cache_{cache_key}", df)

            return df

        except Exception as e:
            logger.error(f"读取工作表预览失败: {e}")
            return None

    def _analyze_date_column(self, df: pd.DataFrame, column_name: str) -> Dict[str, Any]:
        """
        分析日期列

        Args:
            df: 数据DataFrame
            column_name: 列名

        Returns:
            日期分析结果
        """
        try:
            if column_name not in df.columns:
                return {
                    'is_date': False,
                    'sample_values': [],
                    'error': 'Column not found'
                }

            # 获取样本值
            sample_values = df[column_name].dropna().head(3).tolist()

            # 尝试转换为日期
            try:
                date_converted = pd.to_datetime(df[column_name].dropna().head(3), errors='coerce')
                if not date_converted.isna().all():
                    return {
                        'is_date': True,
                        'sample_values': sample_values,
                        'converted_sample': date_converted.dropna().iloc[0] if len(date_converted.dropna()) > 0 else None
                    }
                else:
                    return {
                        'is_date': False,
                        'sample_values': sample_values,
                        'error': 'Cannot convert to date'
                    }
            except Exception as e:
                return {
                    'is_date': False,
                    'sample_values': sample_values,
                    'error': f'Date conversion error: {e}'
                }

        except Exception as e:
            logger.error(f"日期列分析失败: {e}")
            return {
                'is_date': False,
                'sample_values': [],
                'error': str(e)
            }

    def _render_sheet_analysis(self, st_obj, sheet_name: str, df_preview: pd.DataFrame,
                              format_info: Dict[str, Any]) -> None:
        """
        渲染工作表分析结果

        Args:
            st_obj: Streamlit对象
            sheet_name: 工作表名称
            df_preview: 预览数据
            format_info: 格式信息
        """
        st_obj.write(f"**检测到的格式:** {format_info['format']} (来源: {format_info['source']})")
        st_obj.write(f"**建议参数:** header={format_info['header']}, skiprows={format_info['skiprows']}")
        st_obj.write(f"**数据形状:** {df_preview.shape}")
        st_obj.write("**数据预览:**")
        st_obj.dataframe(df_preview)

    def _get_state(self, key: str, default: Any = None) -> Any:
        """获取状态值"""
        import streamlit as st
        full_key = f'data_prep.{key}'
        return st.session_state.get(full_key, default)

    def _set_state(self, key: str, value: Any) -> None:
        """设置状态值"""
        import streamlit as st
        full_key = f'data_prep.{key}'
        st.session_state[full_key] = value
