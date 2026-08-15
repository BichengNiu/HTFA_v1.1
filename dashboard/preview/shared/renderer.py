"""多频率数据预览的共享 Streamlit 渲染器。"""

import streamlit as st
import pandas as pd
import io
from pathlib import Path
from typing import Optional, Any
import logging

from dashboard.preview.core.base_renderer import BaseRenderer
from dashboard.preview.core.base_loader import BaseDataLoader
from dashboard.preview.domain.models import LoadedPreviewData
from dashboard.preview.shared.tabs import display_time_series_tab, display_overview_tab
from dashboard.core.ui.utils.state_helpers import (
    clear_preview_data,
    get_preview_state,
    set_preview_state,
)
from dashboard.core.ui.utils.shared_dataset import (
    fingerprint_file,
    get_shared_dataset_file,
)

logger = logging.getLogger(__name__)


class PreviewRenderer(BaseRenderer):
    """统一模板预览渲染器。"""

    module_title: str
    default_relative_path: Optional[Path] = None
    tab_names = ['数据概览', '日度', '周度', '旬度', '月度', '季度', '年度']
    frequency_tabs = {
        '日度': 'daily',
        '周度': 'weekly',
        '旬度': 'ten_day',
        '月度': 'monthly',
        '季度': 'quarterly',
        '年度': 'yearly',
    }

    def __init__(self, loader: BaseDataLoader):
        """初始化渲染器

        Args:
            loader: 数据加载器对象
        """
        super().__init__(loader)
        self.state_namespace = loader.get_state_namespace()

    def render_sidebar(self) -> Optional[Any]:
        """渲染侧边栏

        Returns:
            Optional[Any]: 默认文件对象或None
        """
        with st.sidebar:
            # 优先使用全局共享数据集；未上传时才使用默认文件。
            uploaded_file = get_shared_dataset_file() or self._load_default_data_file()
            if uploaded_file is None:
                st.error("请先上传符合正式模板格式的数据文件")
                clear_preview_data(namespace=self.state_namespace)
                return None

            if self._should_reprocess_file(uploaded_file):
                with st.spinner("正在加载数据..."):
                    self._process_uploaded_data(uploaded_file)

            return uploaded_file

    def _load_default_data_file(self) -> Optional[io.BytesIO]:
        """加载默认数据文件

        Returns:
            Optional[io.BytesIO]: 文件对象或None
        """
        if self.default_relative_path is None:
            return None

        project_root = Path(__file__).resolve().parents[3]
        default_path = project_root / self.default_relative_path

        if default_path.exists():
            with open(default_path, 'rb') as f:
                file_obj = io.BytesIO(f.read())
                file_obj.name = default_path.name
                return file_obj

        logger.warning(f"默认数据文件不存在: {default_path}")
        return None

    def render_main_content(self):
        """渲染主内容区域"""
        import streamlit as st
        st.title(self.module_title)

        # 检查是否有数据
        has_data = self._has_any_data()

        # 始终创建Tab页（无论是否有数据）
        tab_objects = st.tabs(self.tab_names)

        # 数据概览Tab
        with tab_objects[0]:
            if has_data:
                self._render_overview_tab()
            else:
                st.info("请在左侧上传数据文件")

        # 时间序列Tab
        for idx, (_, freq) in enumerate(self.frequency_tabs.items(), start=1):
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
            return False

        current_fingerprint = fingerprint_file(uploaded_file)
        cached_fingerprint = get_preview_state(
            'data_loaded_file_fingerprint',
            namespace=self.state_namespace,
        )

        if current_fingerprint != cached_fingerprint:
            logger.info("[Cache] 文件内容变化，需要重新处理")
            return True

        for frequency in self.frequency_tabs.values():
            data = get_preview_state(
                f"{frequency}_df",
                namespace=self.state_namespace,
            )
            if data is not None and not data.empty:
                logger.info("[Cache] 使用缓存数据: %s", uploaded_file.name)
                return False

        logger.info("[Cache] 没有缓存数据")
        return True

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
            set_preview_state(
                'data_loaded_files',
                uploaded_file.name,
                namespace=self.state_namespace,
            )
            set_preview_state(
                'data_loaded_file_fingerprint',
                fingerprint_file(uploaded_file),
                namespace=self.state_namespace,
            )

            st.success(f"数据加载成功：{uploaded_file.name}")

        except Exception as e:
            logger.error(f"数据处理失败: {e}", exc_info=True)
            clear_preview_data(namespace=self.state_namespace)
            st.error(f"数据处理失败: {e}")

    def _save_to_state(self, preview_data: LoadedPreviewData):
        """保存数据到session_state

        Args:
            preview_data: 预览数据对象
        """
        # 保存DataFrame
        for freq, df in preview_data.dataframes.items():
            set_preview_state(
                f'{freq}_df',
                df,
                namespace=self.state_namespace,
            )

            # 提取行业列表
            if not df.empty:
                industries = self._extract_industries_from_df(df, preview_data)
                set_preview_state(
                    f'{freq}_industries',
                    industries,
                    namespace=self.state_namespace,
                )

        # 保存映射关系
        set_preview_state(
            'source_map',
            preview_data.source_map,
            namespace=self.state_namespace,
        )
        set_preview_state(
            'indicator_industry_map',
            preview_data.indicator_industry_map,
            namespace=self.state_namespace,
        )
        set_preview_state(
            'indicator_unit_map',
            preview_data.indicator_unit_map,
            namespace=self.state_namespace,
        )
        set_preview_state(
            'indicator_type_map',
            preview_data.indicator_type_map,
            namespace=self.state_namespace,
        )
        set_preview_state(
            'indicator_freq_map',
            preview_data.indicator_freq_map,
            namespace=self.state_namespace,
        )
        set_preview_state(
            'indicator_metadata_map',
            preview_data.indicator_metadata_map,
            namespace=self.state_namespace,
        )
        set_preview_state(
            'custom_maps',
            preview_data.custom_maps,
            namespace=self.state_namespace,
        )

        # 保存clean_industry_map
        clean_industry_map = self._build_clean_industry_map(preview_data)
        set_preview_state(
            'clean_industry_map',
            clean_industry_map,
            namespace=self.state_namespace,
        )

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
            industry_name = (
                preview_data.indicator_industry_map.get(indicator)
                or self.loader.extract_industry_name(source)
            )
            if industry_name not in clean_industry_map:
                clean_industry_map[industry_name] = []
            clean_industry_map[industry_name].append(source)

        return clean_industry_map

    def _has_any_data(self) -> bool:
        """检查是否有任意数据

        Returns:
            bool: 是否有数据
        """
        for key in self.frequency_tabs.values():
            state_key = f'{key}_df'
            data = get_preview_state(state_key, namespace=self.state_namespace)
            if data is not None and not data.empty:
                return True

        return False

    def _render_overview_tab(self):
        """渲染数据概览Tab"""
        import streamlit as st
        display_overview_tab(st, state_namespace=self.state_namespace)

    def _render_time_series_tab(self, frequency: str):
        """渲染时间序列Tab

        Args:
            frequency: 频率名称 (如 'weekly', 'monthly')
        """
        import streamlit as st
        display_time_series_tab(
            st,
            frequency,
            state_namespace=self.state_namespace,
        )
