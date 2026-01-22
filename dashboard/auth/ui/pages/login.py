# -*- coding: utf-8 -*-
"""
登录页面组件
提供用户登录界面
"""

import streamlit as st
from typing import Optional, Tuple
import logging

# 导入认证模块
from dashboard.auth.authentication import AuthManager
from dashboard.auth.security import SecurityUtils


class LoginPage:
    """登录页面组件"""

    def __init__(self):
        """初始化登录页面"""
        self.auth_manager = AuthManager()
        self.logger = logging.getLogger(__name__)

    def render(self) -> Optional[Tuple[bool, dict]]:
        """
        渲染登录页面

        Returns:
            (是否登录成功, 用户信息和会话信息的字典) 或 None
        """

        # 检查是否需要显示注册页面
        if st.session_state.get('show_register_page', False):
            from dashboard.auth.ui.pages.register import render_register_page
            register_success = render_register_page()
            if register_success:
                # 注册成功后清除注册页面标识，返回登录页面
                del st.session_state['show_register_page']
                st.rerun()
            return None

        # 注入自定义CSS样式
        self._inject_login_styles()

        # 渲染平台标题头部（与欢迎页面相同）
        self._render_platform_header()

        # 添加间距
        st.markdown("<br>", unsafe_allow_html=True)

        # 登录表单容器
        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            # 登录表单（移除白色背景框）

            # 错误消息显示区域
            error_placeholder = st.empty()

            # 用户名输入
            username = st.text_input(
                "用户名",
                placeholder="请输入用户名",
                key="login_username",
                help="请输入您的用户名"
            )

            # 密码输入
            password = st.text_input(
                "密码",
                type="password",
                placeholder="请输入密码",
                key="login_password",
                help="请输入您的密码"
            )

            # 记住登录状态（可选功能）
            remember_me = st.checkbox(
                "记住登录状态",
                key="remember_login",
                help="保持较长时间的登录状态"
            )

            # 登录和注册按钮
            col1, col2 = st.columns(2)

            with col1:
                login_clicked = st.button(
                    "登录",
                    key="login_submit",
                    width='stretch',
                    type="primary"
                )

            with col2:
                register_clicked = st.button(
                    "注册新用户",
                    key="register_submit",
                    width='stretch',
                    type="primary"
                )

            # 处理注册逻辑
            if register_clicked:
                # 设置session state来标识要显示注册页面
                st.session_state['show_register_page'] = True
                st.rerun()

            # 处理登录逻辑
            if login_clicked:
                result = self._handle_login(username, password, remember_me, error_placeholder)
                if result:
                    return result

            # 帮助信息
            st.markdown("---")
            with st.expander("登录帮助"):
                st.markdown("""
                **注意事项：**
                - 首次登录后请立即修改密码
                - 连续登录失败会暂时锁定账户
                - 如需帮助请联系系统管理员
                """)

        return None

    def _handle_login(self, username: str, password: str, remember_me: bool, error_placeholder) -> Optional[Tuple[bool, dict]]:
        """
        处理登录逻辑

        Args:
            username: 用户名
            password: 密码
            remember_me: 是否记住登录
            error_placeholder: 错误信息显示占位符

        Returns:
            (是否成功, 用户和会话信息) 或 None
        """
        try:
            # 输入验证
            if not username or not password:
                error_placeholder.error("请输入用户名和密码")
                return None

            # 清理输入
            username = SecurityUtils.sanitize_input(username.strip())

            # 显示登录中状态
            with st.spinner("正在验证用户信息..."):
                # 执行认证
                success, user, message = self.auth_manager.authenticate(username, password)

                if success and user:
                    # 创建会话
                    session_hours = 24 if remember_me else 8  # 记住登录状态时延长会话时间
                    session = self.auth_manager.create_session(user, session_hours)

                    if session:
                        # 登录成功
                        success_msg = "登录成功！正在跳转..."
                        if message:
                            # 有警告信息(如过期提醒)
                            error_placeholder.warning(f"{success_msg}\n\n{message}")
                        else:
                            error_placeholder.success(success_msg)

                        self.logger.info(f"用户 {username} 登录成功")

                        # 返回用户和会话信息
                        return True, {
                            'user': user,
                            'session': session,
                            'remember_me': remember_me
                        }
                    else:
                        error_placeholder.error("会话创建失败，请重试")
                        return None
                else:
                    # 登录失败
                    error_placeholder.error(f"{message}")
                    self.logger.warning(f"用户 {username} 登录失败: {message}")
                    return None

        except Exception as e:
            error_placeholder.error("系统错误，请稍后重试")
            self.logger.error(f"登录处理异常: {e}")
            return None

    def _render_platform_header(self):
        """渲染平台标题头部（与欢迎页面相同）"""
        st.markdown("""
        <div class="platform-header">
            <h1 class="platform-title">经济运行分析平台</h1>
            <hr class="platform-divider">
            <p class="platform-subtitle">国家信息中心经济预测部政策仿真实验室</p>
        </div>
        """, unsafe_allow_html=True)

    def _inject_login_styles(self):
        """注入登录页面的CSS样式"""
        st.markdown("""
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

        /* 登录表单样式（移除白色背景框） */
        .login-form {
            /* 移除所有背景和边框样式 */
            padding: 1rem 0;
            margin: 1rem 0;
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

        /* 按钮通用样式 */
        .stButton > button {
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 1.1rem !important;
            padding: 0.75rem 2rem !important;
            transition: all 0.3s ease !important;
            width: 100% !important;
            margin-top: 1rem !important;
            transform: translateY(0) !important;
        }

        .stButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 25px rgba(52, 152, 219, 0.3) !important;
        }

        /* 确保所有按钮类型的文字都是白色 */
        .stButton > button[data-baseweb="button"][kind="primary"],
        .stButton > button[data-baseweb="button"][kind="secondary"],
        .stButton > button[kind="primary"],
        .stButton > button[kind="secondary"],
        .stButton > button {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%) !important;
            color: white !important;
            border: none !important;
        }

        .stButton > button:hover {
            background: linear-gradient(135deg, #2980b9 0%, #1e6a96 100%) !important;
            color: white !important;
        }

        /* 复选框样式 */
        .stCheckbox > label {
            font-size: 0.9rem;
            color: #666;
        }

        /* 错误和成功消息样式 */
        .stAlert {
            border-radius: 8px;
            margin: 1rem 0;
        }

        /* 展开器样式 */
        .streamlit-expanderHeader {
            border-radius: 8px;
            background-color: #f8f9fa;
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

            .login-form {
                padding: 1.5rem;
                margin: 1rem 0;
            }
        }
        </style>
        """, unsafe_allow_html=True)


def render_login_page() -> Optional[Tuple[bool, dict]]:
    """
    渲染登录页面的便捷函数

    Returns:
        (是否登录成功, 用户信息) 或 None
    """
    login_page = LoginPage()
    return login_page.render()
