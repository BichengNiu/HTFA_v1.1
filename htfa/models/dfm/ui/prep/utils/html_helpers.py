# -*- coding: utf-8 -*-
"""
HTML生成辅助函数模块

提供Streamlit页面中常用的HTML元素生成功能，包括：
- 标签样式的span元素
- 流式布局的标签组
"""

from typing import List


# 默认标签样式
DEFAULT_TAG_STYLE = (
    "display:inline-block;"
    "margin:2px 8px 2px 0;"
    "padding:2px 6px;"
    "background:#f0f2f6;"
    "border-radius:4px;"
)


def render_tag(content: str, style: str = DEFAULT_TAG_STYLE) -> str:
    """
    渲染单个标签span元素

    Args:
        content: 标签内容文本
        style: CSS样式字符串，默认使用浅灰背景圆角样式

    Returns:
        str: HTML span元素字符串

    Example:
        >>> render_tag("变量A")
        '<span style="display:inline-block;...">变量A</span>'
    """
    return f'<span style="{style}">{content}</span>'


def render_tag_group(items: List[str], style: str = DEFAULT_TAG_STYLE) -> str:
    """
    渲染标签组（多个标签横向流式排列）

    Args:
        items: 标签内容列表
        style: CSS样式字符串

    Returns:
        str: 合并后的HTML字符串，可直接用于st.markdown(unsafe_allow_html=True)

    Example:
        >>> render_tag_group(["变量A", "变量B", "变量C"])
        '<span style="...">变量A</span><span style="...">变量B</span>...'
    """
    return ''.join(render_tag(item, style) for item in items)


__all__ = [
    'DEFAULT_TAG_STYLE',
    'render_tag',
    'render_tag_group'
]
