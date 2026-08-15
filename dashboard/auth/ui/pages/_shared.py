# -*- coding: utf-8 -*-
"""
认证页面共享 UI 组件

登录页与注册页共用的平台标题头部与基础 CSS。
"""

import streamlit as st

PLATFORM_HEADER_MARKDOWN = """
<div class="platform-header">
    <h1 class="platform-title">经济运行分析平台</h1>
    <hr class="platform-divider">
    <p class="platform-subtitle">国家信息中心经济预测部政策仿真实验室</p>
</div>
"""

# 登录/注册页共享的基础样式（表单与按钮细节由各页面自行注入）
BASE_AUTH_CSS = """
<style>
/* 平台标题样式（与欢迎页面一致） */
.platform-header {
    text-align: center;
    margin: 2rem 0;
}

.platform-title {
    font-size: 3rem;
    color: #2c3e50;
    margin-bottom: 1rem;
    font-weight: 700;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
}

.platform-divider {
    width: 60%;
    margin: 1.5rem auto;
    border: none;
    border-top: 3px solid #3498db;
    border-radius: 2px;
}

.platform-subtitle {
    font-size: 1.2rem;
    color: #7f8c8d;
    margin-bottom: 2rem;
    font-weight: 400;
}

/* 输入框样式 */
.stTextInput > div > div > input {
    border-radius: 8px;
    border: 2px solid #e1e8ed;
    padding: 0.75rem;
    font-size: 1rem;
    transition: all 0.3s ease;
}

.stTextInput > div > div > input:focus {
    border-color: #3498db;
    box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.1);
}

/* 错误和成功消息样式 */
.stAlert {
    border-radius: 8px;
    margin: 1rem 0;
}

/* 整体页面样式 */
.main .block-container {
    padding-top: 2rem;
    max-width: 1200px;
}

/* 隐藏默认的Streamlit样式元素 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stApp > header {visibility: hidden;}

/* 响应式设计 */
@media (max-width: 768px) {
    .platform-title {
        font-size: 2.5rem;
    }

    .platform-subtitle {
        font-size: 1rem;
    }
}
</style>
"""


def render_platform_header() -> None:
    """渲染平台标题头部（与欢迎页面相同）"""
    st.markdown(PLATFORM_HEADER_MARKDOWN, unsafe_allow_html=True)


def inject_base_auth_styles() -> None:
    """注入认证页面的基础CSS样式"""
    st.markdown(BASE_AUTH_CSS, unsafe_allow_html=True)


__all__ = [
    'BASE_AUTH_CSS',
    'PLATFORM_HEADER_MARKDOWN',
    'inject_base_auth_styles',
    'render_platform_header',
]
