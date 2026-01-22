# -*- coding: utf-8 -*-
"""
用户管理界面组件
提供用户管理和系统统计功能
"""

import streamlit as st
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging
import time

# 导入认证相关模块
from dashboard.auth.authentication import AuthManager
from dashboard.auth.permissions import PermissionManager
from dashboard.auth.models import User
from dashboard.auth.security import SecurityUtils
from dashboard.auth.database import AuthDatabase


class UserManagementPage:
    """用户管理页面组件"""
    
    def __init__(self):
        """初始化用户管理页面"""
        self.auth_manager = AuthManager()
        self.permission_manager = PermissionManager()
        self.db = AuthDatabase()
        self.logger = logging.getLogger(__name__)
    
    def render(self, current_user: User) -> None:
        """
        渲染用户管理页面

        Args:
            current_user: 当前登录用户（调试模式下可以为None）
        """
        # 检查调试模式
        debug_mode = st.session_state.get('auth.debug_mode', False)

        # 在调试模式下跳过管理员权限检查
        if not debug_mode:
            # 生产模式：检查管理员权限
            if not current_user or not self.permission_manager.is_admin(current_user):
                st.error("权限不足：只有管理员可以访问用户管理功能")
                st.info("如需管理权限，请联系系统管理员")
                return
        
        
        # 创建标签页
        tab1, tab2 = st.tabs(["用户管理", "使用统计"])
        
        with tab1:
            self._render_user_list()
        
        with tab2:
            self._render_system_stats()
    
    def _render_user_list(self):
        """渲染用户列表"""
        st.markdown("###### 用户列表")
        
        try:
            # 获取所有用户
            users = self.db.get_all_users()
            
            if not users:
                st.info("暂无用户数据")
                return
            
            # 创建用户数据表格
            user_data = []
            for user in users:
                # 获取用户可访问的模块名称（直接基于权限）
                accessible_modules = self.permission_manager.get_accessible_modules(user)
                permissions_str = "、".join(accessible_modules) if accessible_modules else "无权限"

                # 使用期限显示
                if user.is_permanent:
                    validity_str = "永久有效"
                elif user.valid_from and user.valid_until:
                    validity_str = f"{user.valid_from.strftime('%Y-%m-%d')} 至 {user.valid_until.strftime('%Y-%m-%d')}"
                    if user.is_expired():
                        validity_str += " (已过期)"
                    elif user.is_expiring_soon(30):
                        days_left = user.days_until_expiry()
                        validity_str += f" (剩{days_left}天)"
                else:
                    validity_str = "未设置"

                user_data.append({
                    "ID": user.id,
                    "用户名": user.username,
                    "邮箱": user.email or "未设置",
                    "微信号": user.wechat or "未设置",
                    "手机号": user.phone or "未设置",
                    "单位名称": user.organization or "未设置",
                    "创建时间": user.created_at.strftime("%Y-%m-%d %H:%M"),
                    "最后登录": user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "从未登录",
                    "使用期限": validity_str,
                    "权限": permissions_str,
                    "状态": "激活" if user.is_active else "失效"
                })
            
            df = pd.DataFrame(user_data)
            
            # 显示数据表格
            st.dataframe(
                df,
                width='stretch',
                hide_index=True,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", width="small"),
                    "用户名": st.column_config.TextColumn("用户名", width="medium"),
                    "邮箱": st.column_config.TextColumn("邮箱", width="medium"),
                    "微信号": st.column_config.TextColumn("微信号", width="medium"),
                    "手机号": st.column_config.TextColumn("手机号", width="medium"),
                    "单位名称": st.column_config.TextColumn("单位名称", width="large"),
                    "创建时间": st.column_config.TextColumn("创建时间", width="medium"),
                    "最后登录": st.column_config.TextColumn("最后登录", width="medium"),
                    "使用期限": st.column_config.TextColumn("使用期限", width="large"),
                    "权限": st.column_config.TextColumn("权限", width="large"),
                    "状态": st.column_config.TextColumn("状态", width="small")
                }
            )
            
            # 添加分割线
            st.markdown("---")
            
            # 用户操作功能
            self._render_user_operations(users)
            
        except Exception as e:
            st.error(f"加载用户列表失败: {e}")
            self.logger.error(f"加载用户列表失败: {e}")
    
    def _render_user_operations(self, users: List[User]):
        """渲染用户操作功能区域"""
        st.markdown("###### 用户操作")
        
        if not users:
            st.info("暂无用户可操作")
            return
        
        # 用户选择（单选）
        
        user_options = ["请选择用户..."]
        user_mapping = {}
        
        for user in users:
            display_name = f"{user.username} (ID: {user.id})"
            user_options.append(display_name)
            user_mapping[display_name] = user
        
        selected_user_display = st.selectbox(
            "选择一个用户进行修改：",
            options=user_options,
            key="selected_user_for_operation"
        )
        
        if selected_user_display == "请选择用户...":
            st.info("请先选择要操作的用户")
            return
            
        selected_user = user_mapping[selected_user_display]
        
        st.info(f"当前操作用户：{selected_user.username}")
        
        # 生成表单key，用于重置
        form_key = f"user_operation_form_{selected_user.id}"
        reset_key = f"reset_form_{selected_user.id}"
        
        # 检查是否需要重置
        if st.session_state.get(reset_key, False):
            # 重置标志
            st.session_state[reset_key] = False
            # 使用新的key来重置表单
            form_key = f"user_operation_form_{selected_user.id}_{int(time.time() * 1000000)}"
        
        # 用户信息修改表单
        with st.form(form_key, clear_on_submit=False):
            st.markdown("**修改用户信息：**")

            col1, col2 = st.columns(2)

            with col1:
                # 用户名（只读显示）
                st.text_input(
                    "用户名",
                    value=selected_user.username,
                    disabled=True
                )

                # 邮箱修改
                new_email = st.text_input(
                    "邮箱",
                    value=selected_user.email or "",
                    placeholder=f"当前值：{selected_user.email or '未设置'}"
                )

                # 微信号修改
                new_wechat = st.text_input(
                    "微信号",
                    value=selected_user.wechat or "",
                    placeholder=f"当前值：{selected_user.wechat or '未设置'}"
                )

            with col2:
                # 手机号修改
                new_phone = st.text_input(
                    "手机号",
                    value=selected_user.phone or "",
                    placeholder=f"当前值：{selected_user.phone or '未设置'}"
                )

                # 单位名称修改
                new_organization = st.text_input(
                    "单位名称",
                    value=selected_user.organization or "",
                    placeholder=f"当前值：{selected_user.organization or '未设置'}"
                )

                # 状态修改
                status_options = {
                    "激活": True,
                    "非激活": False
                }
                current_status_display = "激活" if selected_user.is_active else "非激活"

                selected_status_key = st.selectbox(
                    "用户状态",
                    options=list(status_options.keys()),
                    index=list(status_options.keys()).index(current_status_display)
                )
                new_is_active = status_options[selected_status_key]

            # 用户信息与权限模块之间添加分割线
            st.divider()

            # 用户权限模块标题
            st.markdown("**用户权限模块：**")

            # 权限修改（单列布局，每个主模块及其子模块和tab占一行）
            from dashboard.auth.permissions import GRANULAR_PERMISSION_MAP
            from dashboard.auth.permission_builder import PermissionTreeBuilder

            # 获取当前用户的权限集合
            current_permissions = set(selected_user.permissions)

            # 收集新权限
            new_permissions = []

            # 渲染函数：渲染单个主模块及其子模块（一行显示）
            def render_permission_module(main_name, main_config, current_perms, perm_list):
                main_code = main_config["code"]
                has_main = main_code in current_perms

                # 主模块checkbox（直接显示名称）
                main_checked = st.checkbox(
                    main_name,
                    value=has_main,
                    key=f"perm_main_{main_code}_{selected_user.id}"
                )

                if main_checked:
                    perm_list.append(main_code)

                # 子模块和Tab（横向排列在同一行，使用缩进）
                if main_config.get("sub_modules"):
                    sub_modules = main_config["sub_modules"]

                    # 计算总列数：每个子模块一列
                    sub_cols = st.columns(len(sub_modules))

                    for idx, (sub_name, sub_config) in enumerate(sub_modules.items()):
                        sub_code = sub_config["code"]
                        has_sub = sub_code in current_perms

                        with sub_cols[idx]:
                            # 子模块使用缩进显示
                            sub_checked = st.checkbox(
                                f"　{sub_name}",
                                value=has_sub,
                                key=f"perm_sub_{sub_code}_{selected_user.id}"
                            )

                            if sub_checked:
                                perm_list.append(sub_code)

                            # Tab级别（垂直排列在子模块下方）
                            if sub_config.get("tabs"):
                                tabs = sub_config["tabs"]

                                for tab_name, tab_code in tabs.items():
                                    has_tab = tab_code in current_perms

                                    # Tab使用更多缩进显示
                                    tab_checked = st.checkbox(
                                        f"　　{tab_name}",
                                        value=has_tab,
                                        key=f"perm_tab_{tab_code}_{selected_user.id}"
                                    )

                                    if tab_checked:
                                        perm_list.append(tab_code)

                # 分隔线
                st.markdown("---")

            # 遍历所有主模块，每个占一行
            for main_name, main_config in GRANULAR_PERMISSION_MAP.items():
                render_permission_module(
                    main_name,
                    main_config,
                    current_permissions,
                    new_permissions
                )

            # 去重权限列表
            new_permissions = list(set(new_permissions))

            # 显示当前权限预览
            if new_permissions:
                perm_display = [PermissionTreeBuilder.get_permission_display_name(p) for p in new_permissions]
                st.info(f"已选权限数量: {len(new_permissions)}")
                with st.expander("查看详细权限"):
                    for display_name in sorted(perm_display):
                        st.text(f"- {display_name}")
            else:
                st.warning("无权限访问任何模块")

            # 权限模块与使用期限管理之间添加分割线
            st.divider()

            # 使用期限管理
            st.markdown("**使用期限管理：**")
            is_permanent = st.checkbox(
                "永久有效",
                value=selected_user.is_permanent,
                key=f"permanent_{selected_user.id}"
            )

            valid_from = None
            valid_until = None
            if not is_permanent:
                col_start, col_end = st.columns(2)
                with col_start:
                    valid_from = st.date_input(
                        "生效日期",
                        value=selected_user.valid_from if selected_user.valid_from else None,
                        key=f"valid_from_{selected_user.id}"
                    )
                with col_end:
                    valid_until = st.date_input(
                        "过期日期",
                        value=selected_user.valid_until if selected_user.valid_until else None,
                        key=f"valid_until_{selected_user.id}"
                    )
            
            # 提交按钮
            st.markdown("---")
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                submitted = st.form_submit_button("保存修改", type="primary", width='stretch')
            
            with col_cancel:
                reset_clicked = st.form_submit_button("重置", width='stretch')
                if reset_clicked:
                    # 设置重置标志，下次渲染时将使用新的表单key来重置表单
                    st.session_state[reset_key] = True
                    st.rerun()
            
            # 处理表单提交
            if submitted:
                self._handle_single_user_operation(
                    selected_user,
                    new_email,
                    new_wechat,
                    new_phone,
                    new_organization,
                    new_permissions,
                    new_is_active,
                    is_permanent,
                    valid_from,
                    valid_until
                )
    
    def _handle_single_user_operation(self, user: User, new_email: str, new_wechat: str,
                                    new_phone: str, new_organization: str,
                                    new_permissions: List[str], new_is_active: bool,
                                    is_permanent: bool, valid_from, valid_until):
        """处理单用户信息修改"""
        try:
            # 记录原始信息
            original_info = f"{user.username} (ID: {user.id})"
            changes = []

            # 邮箱验证和更新
            if new_email != (user.email or ""):
                if new_email:
                    from dashboard.auth.security import SecurityUtils
                    is_valid, msg = SecurityUtils.validate_email(new_email)
                    if not is_valid:
                        st.error(f"邮箱格式错误: {msg}")
                        return False
                user.email = new_email if new_email else None
                changes.append("邮箱")

            # 微信号更新
            if new_wechat != (user.wechat or ""):
                user.wechat = new_wechat if new_wechat else None
                changes.append("微信号")

            # 手机号验证和更新
            if new_phone != (user.phone or ""):
                if new_phone:
                    import re
                    if not re.match(r'^1[3-9]\d{9}$', new_phone):
                        st.error("手机号格式错误，请输入11位数字")
                        return False
                user.phone = new_phone if new_phone else None
                changes.append("手机号")

            # 单位名称更新
            if new_organization != (user.organization or ""):
                user.organization = new_organization if new_organization else None
                changes.append("单位名称")

            # 权限更新
            if set(new_permissions) != set(user.permissions):
                user.permissions = new_permissions
                changes.append("权限")

            # 状态更新
            if new_is_active != user.is_active:
                user.is_active = new_is_active
                status_change = "激活" if new_is_active else "禁用"
                changes.append(f"状态({status_change})")

            # 使用期限更新
            if is_permanent != user.is_permanent:
                user.is_permanent = is_permanent
                changes.append("永久有效状态")

            if not is_permanent:
                # 验证日期有效性
                if valid_from and valid_until and valid_from >= valid_until:
                    st.error("生效日期必须早于过期日期")
                    return False

                if valid_from != user.valid_from:
                    user.valid_from = valid_from
                    changes.append("生效日期")

                if valid_until != user.valid_until:
                    user.valid_until = valid_until
                    changes.append("过期日期")
            else:
                # 永久有效时清空日期字段
                if user.valid_from is not None or user.valid_until is not None:
                    user.valid_from = None
                    user.valid_until = None
                    changes.append("清除期限限制")

            # 如果没有任何变化
            if not changes:
                st.info("用户信息未发生变化")
                return True
            
            # 保存到数据库
            self.logger.info(f"准备更新用户: {original_info}")
            self.logger.info(f"更新数据: email={user.email}, wechat={user.wechat}, phone={user.phone}, organization={user.organization}, permissions={user.permissions}, is_active={user.is_active}")
            
            if self.db.update_user(user):
                change_text = "、".join(changes)
                
                # 验证更新是否成功 - 重新从数据库读取用户信息
                updated_user = self.db.get_user_by_id(user.id)
                if updated_user:
                    self.logger.info(f"数据库验证: email={updated_user.email}, wechat={updated_user.wechat}, phone={updated_user.phone}, organization={updated_user.organization}")
                    st.success(f"用户 {user.username} 信息更新成功！\n修改项目：{change_text}")
                    self.logger.info(f"单用户信息更新成功: {original_info}, 修改项目: {change_text}")
                else:
                    st.warning("更新成功但验证读取失败")
                    self.logger.warning(f"更新成功但无法验证: {original_info}")
                
                # 刷新页面显示更新后的信息
                st.rerun()
                return True
            else:
                st.error("用户信息更新失败，请稍后重试")
                self.logger.error(f"单用户信息更新失败: {original_info}")
                return False
                
        except Exception as e:
            st.error(f"更新用户信息时发生错误: {e}")
            self.logger.error(f"单用户操作失败 {user.username}: {e}")
            return False
    
    def _render_system_stats(self):
        """渲染使用统计界面"""
        
        try:
            users = self.db.get_all_users()
            current_time = datetime.now()
            
            # 计算各时间段的统计数据
            stats_data = self._calculate_user_statistics(users, current_time)
            
            # 第一行：主要统计指标
            st.markdown("##### 用户活动统计")
            
            # 创建6列显示各项统计
            cols = st.columns(6)
            metrics = [
                ("总用户数", stats_data["total_users"], stats_data["total_users_growth"]),
                ("激活用户数", stats_data["active_users"], stats_data["active_users_growth"]),
                ("今日活动用户数", stats_data["today_active"], stats_data["today_active_growth"]),
                ("本周活动用户数", stats_data["week_active"], stats_data["week_active_growth"]),
                ("本月活动用户数", stats_data["month_active"], stats_data["month_active_growth"]),
                ("本年活动用户数", stats_data["year_active"], stats_data["year_active_growth"])
            ]
            
            for i, (label, value, growth) in enumerate(metrics):
                with cols[i]:
                    # 决定箭头颜色和方向
                    if growth > 0:
                        arrow = "↗️"
                        color = "red"
                        growth_text = f"+{growth:.1f}%"
                    elif growth < 0:
                        arrow = "↘️"
                        color = "green"
                        growth_text = f"{growth:.1f}%"
                    else:
                        arrow = "→"
                        color = "gray"
                        growth_text = "0.0%"
                    
                    # 显示指标
                    st.metric(
                        label=label,
                        value=value,
                        delta=None
                    )
                    
                    # 在指标下方添加增长信息
                    st.markdown(
                        f'<div style="text-align: center; font-size: 12px; color: {color};">'
                        f'{arrow} {growth_text}</div>',
                        unsafe_allow_html=True
                    )
            
            st.markdown("---")
            
            # 当天活动用户列表
            st.markdown("##### 今日活动用户")
            today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            today_users = [u for u in users if u.last_login and u.last_login >= today_start]
            today_users.sort(key=lambda x: x.last_login, reverse=True)
            
            if today_users:
                today_data = []
                for user in today_users:
                    today_data.append({
                        "用户名": user.username,
                        "登录时间": user.last_login.strftime("%H:%M:%S"),
                        "状态": "激活" if user.is_active else "非激活"
                    })
                
                st.dataframe(
                    pd.DataFrame(today_data), 
                    width='stretch', 
                    hide_index=True
                )
            else:
                st.info("今日暂无用户活动")
                
        except Exception as e:
            st.error(f"加载使用统计失败: {e}")
            self.logger.error(f"加载使用统计失败: {e}")
    
    def _calculate_user_statistics(self, users: List, current_time: datetime) -> Dict[str, Any]:
        """计算用户统计数据"""
        try:
            # 计算当前时间段的边界
            today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=current_time.weekday())
            month_start = current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            year_start = current_time.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # 计算上个周期的时间边界（用于同比计算）
            last_today_start = today_start - timedelta(days=1)
            last_today_end = today_start
            last_week_start = week_start - timedelta(days=7)
            last_week_end = week_start
            last_month_start = (month_start - timedelta(days=1)).replace(day=1)
            last_month_end = month_start
            last_year_start = year_start.replace(year=year_start.year - 1)
            last_year_end = year_start
            
            # 当前统计
            total_users = len(users)
            active_users = len([u for u in users if u.is_active])
            
            # 活动用户统计（基于last_login）
            today_active = len([u for u in users if u.last_login and u.last_login >= today_start])
            week_active = len([u for u in users if u.last_login and u.last_login >= week_start])
            month_active = len([u for u in users if u.last_login and u.last_login >= month_start])
            year_active = len([u for u in users if u.last_login and u.last_login >= year_start])
            
            # 上期统计（用于计算增长率）
            # 注意：由于我们只有last_login字段，无法准确计算历史同期数据
            # 这里使用简化的逻辑来模拟增长率
            last_today_active = len([u for u in users if u.last_login and 
                                   last_today_start <= u.last_login < last_today_end])
            last_week_active = len([u for u in users if u.last_login and 
                                  last_week_start <= u.last_login < last_week_end])
            last_month_active = len([u for u in users if u.last_login and 
                                   last_month_start <= u.last_login < last_month_end])
            last_year_active = len([u for u in users if u.last_login and 
                                  last_year_start <= u.last_login < last_year_end])
            
            # 计算增长率
            def calculate_growth_rate(current: int, previous: int) -> float:
                if previous == 0:
                    return 100.0 if current > 0 else 0.0
                return ((current - previous) / previous) * 100
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "today_active": today_active,
                "week_active": week_active,
                "month_active": month_active,
                "year_active": year_active,
                "total_users_growth": calculate_growth_rate(total_users, max(1, total_users - 1)),  # 简化逻辑
                "active_users_growth": calculate_growth_rate(active_users, max(1, active_users - 1)),  # 简化逻辑
                "today_active_growth": calculate_growth_rate(today_active, last_today_active),
                "week_active_growth": calculate_growth_rate(week_active, last_week_active),
                "month_active_growth": calculate_growth_rate(month_active, last_month_active),
                "year_active_growth": calculate_growth_rate(year_active, last_year_active)
            }
            
        except Exception as e:
            self.logger.error(f"计算用户统计数据失败: {e}")
            # 返回默认数据
            return {
                "total_users": len(users),
                "active_users": len([u for u in users if u.is_active]),
                "today_active": 0,
                "week_active": 0,
                "month_active": 0,
                "year_active": 0,
                "total_users_growth": 0.0,
                "active_users_growth": 0.0,
                "today_active_growth": 0.0,
                "week_active_growth": 0.0,
                "month_active_growth": 0.0,
                "year_active_growth": 0.0
            }
    
    
def render_user_management_page(current_user: User) -> None:
    """
    渲染用户管理页面的便捷函数
    
    Args:
        current_user: 当前登录用户
    """
    user_mgmt = UserManagementPage()
    user_mgmt.render(current_user)
