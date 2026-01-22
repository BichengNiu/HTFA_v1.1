"""
工业数据预览渲染器

封装工业数据预览的UI渲染逻辑
"""

import streamlit as st
import pandas as pd
import io
from pathlib import Path
from typing import Optional, Any
import logging

from dashboard.preview.core.base_renderer import BaseRenderer
from dashboard.preview.core.base_config import BasePreviewConfig
from dashboard.preview.core.base_loader import BaseDataLoader
from dashboard.preview.domain.models import LoadedPreviewData
from dashboard.preview.shared.tabs import display_time_series_tab, display_overview_tab
from dashboard.core.ui.utils.state_helpers import get_preview_state, set_preview_state
from dashboard.preview.shared.frequency_utils import get_all_frequency_names
from dashboard.preview.modules.industrial.config import UNIFIED_FREQUENCY_CONFIGS

logger = logging.getLogger(__name__)


class IndustrialRenderer(BaseRenderer):
    """工业数据预览渲染器

    继承BaseRenderer，实现工业数据的UI渲染
    """

    def __init__(self, config: BasePreviewConfig, loader: BaseDataLoader):
        """初始化渲染器

        Args:
            config: 配置对象
            loader: 数据加载器对象
        """
        super().__init__(config, loader)

    def render_sidebar(self) -> Optional[Any]:
        """渲染侧边栏

        Returns:
            Optional[Any]: 默认文件对象或None
        """
        with st.sidebar:
            # 自动加载默认文件
            default_file = self._load_default_data_file()
            if default_file is None:
                st.error("默认数据文件不存在：data/经济指标数据库.xlsx")
                return None

            # 检查是否需要重新处理
            if self._should_reprocess_file(default_file):
                with st.spinner("正在加载数据..."):
                    self._process_uploaded_data(default_file)

            return default_file

    def _load_default_data_file(self) -> Optional[io.BytesIO]:
        """加载默认数据文件

        Returns:
            Optional[io.BytesIO]: 文件对象或None
        """
        default_path = Path(__file__).parent.parent.parent.parent.parent / "data" / "经济指标数据库.xlsx"

        if default_path.exists():
            with open(default_path, 'rb') as f:
                file_obj = io.BytesIO(f.read())
                file_obj.name = "经济指标数据库.xlsx"
                return file_obj

        logger.warning(f"默认数据文件不存在: {default_path}")
        return None

    def render_main_content(self):
        """渲染主内容区域"""
        import streamlit as st
        st.title("工业数据预览")

        # 检查是否有数据
        has_data = self._has_any_data()

        # 始终创建Tab页（无论是否有数据）
        tabs = ['数据概览', '日度', '周度', '旬度', '月度', '季度', '年度']
        tab_objects = st.tabs(tabs)

        # 数据概览Tab
        with tab_objects[0]:
            if has_data:
                self._render_overview_tab()
            else:
                st.info("请在左侧上传数据文件")

        # 时间序列Tab
        freq_tabs = {
            '日度': 'daily',
            '周度': 'weekly',
            '旬度': 'ten_day',
            '月度': 'monthly',
            '季度': 'quarterly',
            '年度': 'yearly'
        }

        for idx, (tab_name, freq) in enumerate(freq_tabs.items(), start=1):
            with tab_objects[idx]:
                if has_data:
                    self._render_time_series_tab(freq)
                else:
                    st.info("请在左侧上传数据文件")

    def _should_reprocess_file(self, uploaded_file) -> bool:
        """判断是否需要重新处理数据

        Args:
            uploaded_file: 上传的文件对象

        Returns:
            bool: True表示需要重新处理，False表示可以使用缓存
        """
        if not uploaded_file:
            print("[DEBUG] _should_reprocess_file: 没有上传文件")
            return False

        current_name = uploaded_file.name
        cached_name = get_preview_state('data_loaded_files')
        print(f"[DEBUG] _should_reprocess_file: current={current_name}, cached={cached_name}")

        # 文件名检查
        if current_name != cached_name:
            print(f"[DEBUG] _should_reprocess_file: 文件名变化，需要重新处理")
            logger.info(f"[Cache] 文件名变化: {cached_name} -> {current_name}")
            return True

        # 检查是否有任意数据
        keys_to_check = ['weekly_df', 'monthly_df', 'daily_df', 'ten_day_df', 'quarterly_df', 'yearly_df']
        print(f"[DEBUG] _should_reprocess_file: 检查缓存数据，keys={keys_to_check}")
        has_data = any(
            get_preview_state(key) is not None and not get_preview_state(key).empty
            for key in keys_to_check
        )
        print(f"[DEBUG] _should_reprocess_file: has_data={has_data}")

        if not has_data:
            print(f"[DEBUG] _should_reprocess_file: 没有缓存数据，需要重新处理")
            logger.info(f"[Cache] 没有缓存数据")
            return True

        print(f"[DEBUG] _should_reprocess_file: 使用缓存数据")
        logger.info(f"[Cache] 使用缓存数据: {current_name}")
        return False

    def _process_uploaded_data(self, uploaded_file):
        """处理上传的数据

        Args:
            uploaded_file: 上传的文件对象
        """
        try:
            # 加载并处理数据
            preview_data = self.loader.load_and_process_data([uploaded_file])

            # 保存到session_state
            self._save_to_state(preview_data)

            # 记录文件名
            set_preview_state('data_loaded_files', uploaded_file.name)

            st.success(f"数据加载成功：{uploaded_file.name}")

        except Exception as e:
            logger.error(f"数据处理失败: {e}", exc_info=True)
            st.error(f"数据处理失败: {e}")

    def _save_to_state(self, preview_data: LoadedPreviewData):
        """保存数据到session_state

        Args:
            preview_data: 预览数据对象
        """
        # 保存DataFrame
        for freq, df in preview_data.dataframes.items():
            set_preview_state(f'{freq}_df', df)

            # 提取行业列表
            if not df.empty:
                industries = self._extract_industries_from_df(df, preview_data)
                set_preview_state(f'{freq}_industries', industries)

        # 保存映射关系
        set_preview_state('source_map', preview_data.source_map)
        set_preview_state('indicator_industry_map', preview_data.indicator_industry_map)
        set_preview_state('indicator_unit_map', preview_data.indicator_unit_map)
        set_preview_state('indicator_type_map', preview_data.indicator_type_map)

        # 保存clean_industry_map
        clean_industry_map = self._build_clean_industry_map(preview_data)
        set_preview_state('clean_industry_map', clean_industry_map)

    def _extract_industries_from_df(self, df: pd.DataFrame, preview_data: LoadedPreviewData) -> list:
        """从DataFrame提取行业列表

        Args:
            df: DataFrame
            preview_data: 预览数据对象

        Returns:
            list: 行业列表
        """
        indicators = df.columns.tolist()
        industries = set()

        for indicator in indicators:
            industry = preview_data.indicator_industry_map.get(indicator)
            if industry:
                industries.add(industry)

        return sorted(list(industries))

    def _build_clean_industry_map(self, preview_data: LoadedPreviewData) -> dict:
        """构建clean_industry_map

        Args:
            preview_data: 预览数据对象

        Returns:
            dict: {行业名: [数据源列表]}
        """
        clean_industry_map = {}

        for indicator, source in preview_data.source_map.items():
            industry_name = self.loader.extract_industry_name(source)
            if industry_name not in clean_industry_map:
                clean_industry_map[industry_name] = []
            clean_industry_map[industry_name].append(source)

        return clean_industry_map

    def _has_any_data(self) -> bool:
        """检查是否有任意数据

        Returns:
            bool: 是否有数据
        """
        keys_to_check = ['weekly', 'monthly', 'daily', 'ten_day', 'yearly']

        for key in keys_to_check:
            state_key = f'{key}_df'
            data = get_preview_state(state_key)
            if data is not None and not data.empty:
                return True

        return False

    def _render_data_status_panel(self):
        """渲染数据状态面板"""
        st.markdown("---")
        st.markdown("**数据状态：**")

        max_industries = 0
        for freq_name in get_all_frequency_names(use_english=True):
            config = UNIFIED_FREQUENCY_CONFIGS[freq_name]

            # 获取DataFrame并统计指标
            df = get_preview_state(config['df_key'], pd.DataFrame())
            indicator_count = len(df.columns) if not df.empty else 0

            # 显示指标数量
            if indicator_count > 0:
                st.markdown(f"{config['display_name']}指标：{indicator_count} 个")

            # 同时统计行业数量
            industry_count = len(get_preview_state(config['industries_key'], []))
            max_industries = max(max_industries, industry_count)

        # 显示行业数量
        if max_industries > 0:
            st.markdown(f"涵盖行业：{max_industries} 个")

    def _render_overview_tab(self):
        """渲染数据概览Tab"""
        import streamlit as st
        display_overview_tab(st)

    def _render_time_series_tab(self, frequency: str):
        """渲染时间序列Tab

        Args:
            frequency: 频率名称 (如 'weekly', 'monthly')
        """
        import streamlit as st
        display_time_series_tab(st, frequency)
