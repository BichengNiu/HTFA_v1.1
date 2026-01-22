# -*- coding: utf-8 -*-
"""
认证管理器
提供用户认证、会话管理功能
"""

from typing import Optional, Tuple
from datetime import datetime, timedelta
import logging

from dashboard.auth.database import AuthDatabase
from dashboard.auth.models import User, UserSession
from dashboard.auth.security import SecurityUtils
from dashboard.auth.config import AuthConfig, DEFAULT_CONFIG


class AuthManager:
    """认证管理器"""

    def __init__(self, db_path: str = None, config: AuthConfig = None):
        """初始化认证管理器"""
        self.config = config or DEFAULT_CONFIG
        self.db = AuthDatabase(db_path)
        self.security = SecurityUtils(self.config)
        self.logger = logging.getLogger(__name__)
        self.audit_logger = logging.getLogger('security_audit')
    
    def _handle_user_not_found(self, username: str) -> Tuple[bool, None, str]:
        """处理用户不存在的情况"""
        self.audit_logger.info(f"登录尝试 - 用户: {username}, 状态: 失败")
        return False, None, "用户名或密码错误"

    def _check_user_status(self, user: User) -> Optional[str]:
        """检查用户状态，返回错误信息（如果有）"""
        if user.is_locked():
            self.audit_logger.warning(f"安全事件 - 类型: 账户锁定, 用户: {user.username}, 详情: 尝试登录被锁定的账户")
            return f"账户已被锁定，请{user.locked_until.strftime('%Y-%m-%d %H:%M:%S')}后重试"

        if user.is_not_yet_valid():
            self.audit_logger.warning(f"安全事件 - 类型: 账户未生效, 用户: {user.username}, 详情: 尝试登录未生效的账户")
            return f"账户尚未生效，生效日期：{user.valid_from.strftime('%Y-%m-%d')}"

        if user.is_expired():
            self.audit_logger.warning(f"安全事件 - 类型: 账户过期, 用户: {user.username}, 详情: 尝试登录已过期的账户")
            return f"账户使用期限已过期，过期日期：{user.valid_until.strftime('%Y-%m-%d')}"

        if not user.is_active:
            self.audit_logger.warning(f"安全事件 - 类型: 账户禁用, 用户: {user.username}, 详情: 尝试登录被禁用的账户")
            return "登录权限未激活"

        return None

    def _handle_failed_login(self, user: User) -> Tuple[bool, None, str]:
        """处理登录失败"""
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= self.config.max_login_attempts:
            user.lock_account(self.config.lockout_duration_minutes)
            self.audit_logger.warning(f"安全事件 - 类型: 账户锁定, 用户: {user.username}, 详情: 登录失败次数过多，账户被锁定")

        self.db.update_user(user)
        self.audit_logger.info(f"登录尝试 - 用户: {user.username}, 状态: 失败")
        return False, None, "用户名或密码错误"

    def _handle_successful_login(self, user: User) -> Tuple[bool, User, str]:
        """处理登录成功"""
        user.failed_login_attempts = 0
        user.last_login = datetime.now()
        if user.locked_until:
            user.unlock_account()

        self.db.update_user(user)
        self.audit_logger.info(f"登录尝试 - 用户: {user.username}, 状态: 成功")

        warning_msg = ""
        if user.is_expiring_soon(30):
            days_left = user.days_until_expiry()
            if days_left is not None:
                warning_msg = f"提醒：您的账户将于{days_left}天后过期（{user.valid_until.strftime('%Y-%m-%d')}）"
                self.audit_logger.info(f"过期提醒 - 用户: {user.username}, 剩余天数: {days_left}")

        return True, user, warning_msg

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[User], str]:
        """
        用户认证

        Args:
            username: 用户名
            password: 密码

        Returns:
            (认证成功, 用户对象, 错误信息)
        """
        try:
            username = self.security.sanitize_input(username)

            user = self.db.get_user_by_username(username)
            if not user:
                return self._handle_user_not_found(username)

            if error := self._check_user_status(user):
                return False, None, error

            if not self.security.verify_password(password, user.password_hash):
                return self._handle_failed_login(user)

            return self._handle_successful_login(user)

        except Exception as e:
            self.logger.error(f"认证过程发生错误: {e}")
            return False, None, "系统错误，请稍后重试"
    
    def create_session(self, user: User, session_duration_hours: int = None) -> Optional[UserSession]:
        """
        创建用户会话
        
        Args:
            user: 用户对象
            session_duration_hours: 会话持续时间（小时）
            
        Returns:
            会话对象或None
        """
        try:
            # 使用config中的session_duration_hours作为默认值
            if session_duration_hours is None:
                session_duration_hours = self.config.session_duration_hours

            session = UserSession(
                user_id=user.id,
                expires_at=datetime.now() + timedelta(hours=session_duration_hours)
            )
            
            if self.db.create_session(session):
                self.logger.info(f"为用户 {user.username} 创建会话: {session.session_id}")
                return session
            else:
                self.logger.error(f"创建会话失败: 用户 {user.username}")
                return None
                
        except Exception as e:
            self.logger.error(f"创建会话时发生错误: {e}")
            return None
    
    def validate_session(self, session_id: str) -> Tuple[bool, Optional[User]]:
        """
        验证会话有效性
        
        Args:
            session_id: 会话ID
            
        Returns:
            (会话有效, 用户对象)
        """
        try:
            # 获取会话
            session = self.db.get_session(session_id)
            if not session:
                return False, None
            
            # 检查会话是否过期
            if session.is_expired() or not session.is_active:
                # 删除过期会话
                self.db.delete_session(session_id)
                return False, None
            
            # 获取用户信息
            user = self.db.get_user_by_id(session.user_id)
            if not user or not user.is_active:
                return False, None
            
            # 更新会话访问时间
            session.last_accessed = datetime.now()
            self.db.update_session(session)
            
            return True, user
            
        except Exception as e:
            self.logger.error(f"验证会话时发生错误: {e}")
            return False, None
    
    def extend_session(self, session_id: str, hours: int = None) -> bool:
        """
        延长会话时间
        
        Args:
            session_id: 会话ID
            hours: 延长的小时数
            
        Returns:
            是否延长成功
        """
        try:
            # 使用config中的session_duration_hours作为默认值
            if hours is None:
                hours = self.config.session_duration_hours

            session = self.db.get_session(session_id)
            if session and not session.is_expired():
                session.extend_session(hours)
                return self.db.update_session(session)
            return False
        except Exception as e:
            self.logger.error(f"延长会话时发生错误: {e}")
            return False
    
    def logout(self, session_id: str) -> bool:
        """
        用户登出
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否登出成功
        """
        try:
            session = self.db.get_session(session_id)
            if session:
                user = self.db.get_user_by_id(session.user_id)
                username = user.username if user else "unknown"
                
                # 删除会话
                success = self.db.delete_session(session_id)
                if success:
                    self.logger.info(f"用户 {username} 登出成功")
                    self.audit_logger.warning(f"安全事件 - 类型: 用户登出, 用户: {username}, 详情: 会话 {session_id} 已删除")
                
                return success
            return True  # 会话不存在也认为登出成功
            
        except Exception as e:
            self.logger.error(f"登出时发生错误: {e}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话
        
        Returns:
            清理的会话数量
        """
        try:
            count = self.db.cleanup_expired_sessions()
            if count > 0:
                self.logger.info(f"清理了 {count} 个过期会话")
            return count
        except Exception as e:
            self.logger.error(f"清理过期会话时发生错误: {e}")
            return 0
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        修改用户密码
        
        Args:
            user_id: 用户ID
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            (是否成功, 错误信息)
        """
        try:
            # 获取用户
            user = self.db.get_user_by_id(user_id)
            if not user:
                return False, "用户不存在"
            
            # 验证旧密码
            if not self.security.verify_password(old_password, user.password_hash):
                self.audit_logger.warning(f"安全事件 - 类型: 密码修改失败, 用户: {user.username}, 详情: 旧密码验证失败")
                return False, "旧密码错误"

            # 验证新密码强度
            is_valid, message = self.security.validate_password_strength(new_password)
            if not is_valid:
                return False, message

            # 更新密码
            user.password_hash = self.security.hash_password(new_password)

            if self.db.update_user(user):
                self.audit_logger.warning(f"安全事件 - 类型: 密码修改, 用户: {user.username}, 详情: 密码修改成功")
                self.logger.info(f"用户 {user.username} 密码修改成功")
                return True, ""
            else:
                return False, "密码更新失败"
                
        except Exception as e:
            self.logger.error(f"修改密码时发生错误: {e}")
            return False, "系统错误，请稍后重试"
    
    def get_user_by_session(self, session_id: str) -> Optional[User]:
        """
        根据会话ID获取用户信息
        
        Args:
            session_id: 会话ID
            
        Returns:
            用户对象或None
        """
        is_valid, user = self.validate_session(session_id)
        return user if is_valid else None