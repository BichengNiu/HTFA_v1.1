"""应用 CSS 的读取与注入。"""

from pathlib import Path

import streamlit as st


STATIC_DIR = Path(__file__).parent.parent / "static"


@st.cache_data(show_spinner=False)
def load_cached_styles(css_file: str = "styles.css") -> str:
    """读取静态 CSS；缺失时让 Streamlit 使用默认样式。"""

    path = STATIC_DIR / css_file
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def inject_cached_styles(css_file: str = "styles.css") -> None:
    """向当前页面注入静态 CSS。"""

    content = load_cached_styles(css_file)
    if content:
        st.markdown(f"<style>{content}</style>", unsafe_allow_html=True)


__all__ = ["load_cached_styles", "inject_cached_styles"]
