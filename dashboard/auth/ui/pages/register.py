# -*- coding: utf-8 -*-
"""
用户注册页面组件
提供用户自助注册功能
"""

import streamlit as st
from typing import Optional, Tuple
import logging
import re

# 导入认证模块
from dashboard.auth.authentication import AuthManager
from dashboard.auth.security import SecurityUtils
from dashboard.auth.models import User
from dashboard.auth.database import AuthDatabase


class RegisterPage:
    """用户注册页面组件"""
    
    def __init__(self):
        """初始化注册页面"""
        self.auth_manager = AuthManager()
        self.db = AuthDatabase()
        self.security_utils = SecurityUtils()
        self.logger = logging.getLogger(__name__)
    
    def render(self) -> Optional[bool]:
        """
        渲染用户注册页面
        
        Returns:
            是否注册成功
        """
        
        # 注入自定义CSS样式
        self._inject_register_styles()
        
        # 渲染平台标题头部
        self._render_platform_header()
        
        # 添加间距
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 注册表单容器
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            # 注册表单
            st.markdown("### 用户注册")
            
            # 错误消息显示区域
            error_placeholder = st.empty()
            success_placeholder = st.empty()
            
            # 使用动态表单key来实现重置功能
            form_reset_counter = st.session_state.get("register_form_reset_counter", 0)
            form_key = f"user_register_form_{form_reset_counter}"
            
            with st.form(form_key, clear_on_submit=False):
                # 第一行：用户名和邮箱
                col_a, col_b = st.columns(2)
                
                with col_a:
                    username = st.text_input(
                        "用户名 *",
                        placeholder="请输入用户名",
                        help="用户名只能包含字母、数字和下划线，3-20位，不能以数字开头"
                    )
                
                with col_b:
                    email = st.text_input(
                        "邮箱",
                        placeholder="user@example.com",
                        help="如不填写邮箱，则必须填写微信号或手机号"
                    )
                
                # 第二行：密码
                col_c, col_d = st.columns(2)
                
                with col_c:
                    password = st.text_input(
                        "密码 *",
                        type="password",
                        placeholder="请输入密码",
                        help="请输入密码（支持任意长度和字符）"
                    )
                
                with col_d:
                    confirm_password = st.text_input(
                        "确认密码 *",
                        type="password",
                        placeholder="请再次输入密码"
                    )
                
                # 第三行：微信号和手机号
                col_e, col_f = st.columns(2)
                
                with col_e:
                    wechat = st.text_input(
                        "微信号",
                        placeholder="请输入微信号",
                        help="如不填写邮箱，则微信号和手机号至少填写一项"
                    )
                
                with col_f:
                    phone = st.text_input(
                        "手机号",
                        placeholder="请输入手机号",
                        help="如不填写邮箱，则微信号和手机号至少填写一项"
                    )
                
                # 第四行：单位名称
                organization = st.text_input(
                    "单位名称",
                    placeholder="请输入单位名称",
                    help="单位名称（可选）"
                )
                
                # 按钮行
                col_submit, col_reset = st.columns(2)
                
                with col_submit:
                    submitted = st.form_submit_button("提交", type="primary", width='stretch')
                
                with col_reset:
                    reset_clicked = st.form_submit_button("重置", type="primary", width='stretch')
                
                # 处理重置
                if reset_clicked:
                    # 使用动态表单key方法重置表单：递增计数器强制创建新表单
                    st.session_state["register_form_reset_counter"] = form_reset_counter + 1
                    
                    # 清除可能的表单相关状态
                    keys_to_delete = []
                    for key in list(st.session_state.keys()):
                        # 清除所有与表单相关的键
                        if ('user_register_form' in key or 
                            key.startswith('FormSubmitter:') or
                            key.startswith('textinput_') or
                            key.startswith('TextInput_')):
                            keys_to_delete.append(key)
                    
                    # 删除找到的键
                    for key in keys_to_delete:
                        try:
                            del st.session_state[key]
                        except KeyError:
                            pass
                    
                    # 清空消息占位符
                    error_placeholder.empty()
                    success_placeholder.empty()
                    
                    # 强制重新运行以创建新表单
                    st.rerun()
                
                # 处理注册提交
                if submitted:
                    success = self._handle_register(
                        username, email, password, confirm_password, 
                        wechat, phone, organization, 
                        error_placeholder, success_placeholder
                    )
                    if success:
                        return True
            
            # 返回登录按钮
            st.markdown("---")
            if st.button("返回登录页面", width='stretch', type="primary"):
                # 清除注册页面标识
                if 'show_register_page' in st.session_state:
                    del st.session_state['show_register_page']
                st.rerun()
        
        return None
    
    def _handle_register(self, username: str, email: str, password: str, confirm_password: str,
                        wechat: str, phone: str, organization: str, 
                        error_placeholder, success_placeholder) -> bool:
        """
        处理用户注册逻辑
        
        Returns:
            是否注册成功
        """
        try:
            # 清空之前的消息
            error_placeholder.empty()
            success_placeholder.empty()
            
            # 基本验证
            if not username or not password:
                error_placeholder.error("用户名和密码不能为空")
                return False
            
            if password != confirm_password:
                error_placeholder.error("两次输入的密码不一致")
                return False
            
            # 用户名格式验证
            is_valid, msg = self.security_utils.validate_username(username)
            if not is_valid:
                error_placeholder.error(f"用户名格式错误: {msg}")
                return False
            
            # 检查用户名是否已存在
            existing_user = self.db.get_user_by_username(username)
            if existing_user:
                error_placeholder.error(f"用户名 '{username}' 已使用，请重新输入用户名")
                return False
            
            # 联系方式验证：如果没有邮箱，必须有微信号或手机号
            if not email and not wechat and not phone:
                error_placeholder.error("如不填写邮箱，则微信号和手机号至少需要填写一项")
                return False
            
            # 邮箱格式验证
            if email:
                is_valid, msg = SecurityUtils.validate_email(email)
                if not is_valid:
                    error_placeholder.error(f"邮箱格式错误: {msg}")
                    return False
            
            # 手机号格式验证
            if phone:
                if not self._validate_phone(phone):
                    error_placeholder.error("手机号格式错误，请输入11位数字")
                    return False
            
            # 微信号格式验证
            if wechat:
                if not self._validate_wechat(wechat):
                    error_placeholder.error("微信号格式错误，长度应为6-20位，可包含字母、数字、下划线和连字符")
                    return False
            
            # 创建用户
            from datetime import datetime, date, timedelta
            hashed_password = SecurityUtils.hash_password(password)

            # 设置使用期限
            today = date.today()
            if username.lower() == 'admin':
                # 管理员账户永久有效
                is_permanent = True
                valid_from = None
                valid_until = None
            else:
                # 普通用户7天试用期
                is_permanent = False
                valid_from = today
                valid_until = today + timedelta(days=7)

            new_user = User(
                id=0,  # 将由数据库自动分配
                username=username,
                password_hash=hashed_password,
                email=email if email else None,
                wechat=wechat if wechat else None,
                phone=phone if phone else None,
                organization=organization if organization else None,
                permissions=[],  # 新用户默认没有任何权限，需要管理员分配
                created_at=datetime.now(),
                is_active=True,  # 新注册用户默认激活
                failed_login_attempts=0,
                locked_until=None,
                valid_from=valid_from,
                valid_until=valid_until,
                is_permanent=is_permanent
            )
            
            # 保存到数据库
            if self.db.create_user(new_user):
                if is_permanent:
                    success_msg = f"用户 {username} 注册成功！\n\n账户类型：永久有效\n\n请注意：新用户默认没有模块权限，需要联系系统管理员分配相应权限后才能使用各功能模块。\n\n现在可以返回登录页面进行登录。"
                else:
                    success_msg = f"用户 {username} 注册成功！\n\n使用期限：{valid_from.strftime('%Y-%m-%d')} 至 {valid_until.strftime('%Y-%m-%d')}（7天试用期）\n\n请注意：新用户默认没有模块权限，需要联系系统管理员分配相应权限后才能使用各功能模块。\n\n现在可以返回登录页面进行登录。"
                success_placeholder.success(success_msg)
                self.logger.info(f"新用户注册: {username}, 永久={is_permanent}, 有效期={valid_from}~{valid_until}")
                return True
            else:
                error_placeholder.error("用户注册失败，请稍后重试")
                return False
                
        except Exception as e:
            error_placeholder.error("注册过程中发生错误，请稍后重试")
            self.logger.error(f"用户注册失败: {e}")
            return False
    
    def _validate_phone(self, phone: str) -> bool:
        """验证手机号格式"""
        # 简单的11位数字验证
        return re.match(r'^1[3-9]\d{9}$', phone) is not None
    
    def _validate_wechat(self, wechat: str) -> bool:
        """验证微信号格式"""
        # 微信号格式：6-20位，字母开头，可包含字母、数字、下划线、连字符
        return (6 <= len(wechat) <= 20 and 
                re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', wechat) is not None)
    
    def _render_platform_header(self):
        """渲染平台标题头部"""
        st.markdown("""
        <div class="platform-header">
            <h1 class="platform-title">经济运行分析平台</h1>
            <hr class="platform-divider">
            <p class="platform-subtitle">国家信息中心经济预测部政策仿真实验室</p>
        </div>
        """, unsafe_allow_html=True)
    
    def _inject_register_styles(self):
        """注入注册页面的CSS样式"""
        st.markdown("""
        <style>
        /* 平台标题样式 */
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
        
        /* 注册表单样式 */
        .register-form {
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
        
        /* 按钮样式 */
        .stButton > button {
            border-radius: 8px;
            font-weight: 600;
            font-size: 1.1rem;
            padding: 0.75rem 2rem;
            transition: all 0.3s ease;
            margin-top: 1rem;
            color: white !important;
        }
        
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            border: none;
            color: white !important;
        }
        
        .stButton > button[kind="primary"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(52, 152, 219, 0.3);
            color: white !important;
        }
        
        .stButton > button[kind="secondary"] {
            background: linear-gradient(135deg, #95a5a6 0%, #7f8c8d 100%);
            border: none;
            color: white !important;
        }
        
        .stButton > button[kind="secondary"]:hover {
            color: white !important;
        }
        
        /* 表单提交按钮的primary样式 - 使用更强的选择器 */
        .stFormSubmitButton > button[data-testid="stBaseButton-primaryFormSubmit"],
        .stFormSubmitButton > button[data-testid="stBaseButton-secondaryFormSubmit"],
        .stFormSubmitButton > button[kind="primary"],
        .stFormSubmitButton > button {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%) !important;
            border: none !important;
            color: white !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 1.1rem !important;
            padding: 0.75rem 2rem !important;
            transition: all 0.3s ease !important;
            margin-top: 1rem !important;
            box-shadow: none !important;
        }
        
        .stFormSubmitButton > button[data-testid="stBaseButton-primaryFormSubmit"]:hover,
        .stFormSubmitButton > button[data-testid="stBaseButton-secondaryFormSubmit"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 25px rgba(52, 152, 219, 0.3) !important;
            background: linear-gradient(135deg, #2980b9 0%, #1e6a96 100%) !important;
            color: white !important;
            border: none !important;
        }
        
        /* 确保所有按钮类型的文字都是白色 - 更强的选择器 */
        .stButton > button[data-baseweb="button"],
        .stButton > button[data-baseweb="button"][kind="primary"],
        .stButton > button[data-baseweb="button"][kind="secondary"],
        .stFormSubmitButton > button,
        .stFormSubmitButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="secondary"] {
            color: white !important;
        }
        
        /* 确保按钮悬停状态也是白色 */
        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            color: white !important;
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
        """, unsafe_allow_html=True)


def render_register_page() -> Optional[bool]:
    """
    渲染用户注册页面的便捷函数
    
    Returns:
        是否注册成功
    """
    register_page = RegisterPage()
    return register_page.render()