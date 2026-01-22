# -*- coding: utf-8 -*-
"""
样式加载器
优化CSS加载性能，实现样式缓存
迁移自dashboard.core.style_loader
"""

import streamlit as st
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class StyleLoader:
    """样式加载器 - 简化版本"""

    def __init__(self):
        # 调整路径指向ui/static目录
        self.static_dir = Path(__file__).parent.parent / "static"

    def load_styles(self, css_file: str = "styles.css") -> str:
        """加载样式文件"""
        file_path = self.static_dir / css_file

        if not file_path.exists():
            logger.warning(f"CSS file not found: {file_path}")
            return ""

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.debug(f"Loaded CSS file: {css_file}")
                return content
        except Exception as e:
            logger.error(f"Failed to load CSS file {css_file}: {e}")
            return ""
    
    def inject_styles(self, css_file: str = "styles.css"):
        """注入样式到Streamlit应用"""
        css_content = self.load_styles(css_file)

        if css_content:
            st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

# 全局样式加载器实例
@st.cache_resource
def get_style_loader() -> StyleLoader:
    """获取全局样式加载器实例"""
    return StyleLoader()

def load_cached_styles(css_file: str = "styles.css") -> str:
    """加载样式文件 - 优化版本，使用智能缓存"""
    loader = get_style_loader()  # 使用全局实例
    return loader.load_styles(css_file)

def inject_cached_styles(css_file: str = "styles.css"):
    """注入样式到Streamlit应用"""
    loader = get_style_loader()
    loader.inject_styles(css_file)
