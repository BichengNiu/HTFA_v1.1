# -*- coding: utf-8 -*-
"""
安全工具模块
提供密码加密、验证等安全功能
"""

import bcrypt
import re
import logging

from dashboard.auth.config import AuthConfig, DEFAULT_CONFIG


class SecurityUtils:
    """安全工具类"""

    def __init__(self, config: AuthConfig = None):
        """初始化安全工具"""
        self.config = config or DEFAULT_CONFIG

    @staticmethod
    def hash_password(password: str) -> str:
        """密码哈希加密"""
        try:
            # 生成盐值并加密密码
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        except Exception as e:
            logging.error(f"密码加密失败: {e}")
            raise

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """验证密码"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception as e:
            logging.error(f"密码验证失败: {e}")
            return False

    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """
        验证密码强度

        Returns:
            (是否通过, 错误信息)
        """
        if len(password) < self.config.min_password_length:
            return False, f"密码长度至少{self.config.min_password_length}位"

        if len(password) > self.config.max_password_length:
            return False, f"密码长度不能超过{self.config.max_password_length}位"

        if self.config.require_letter and not re.search(r'[a-zA-Z]', password):
            return False, "密码必须包含字母"

        if self.config.require_digit and not re.search(r'\d', password):
            return False, "密码必须包含数字"

        if self.config.require_special_char and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "密码建议包含特殊字符以提高安全性"

        return True, "密码强度合格"

    def validate_username(self, username: str) -> tuple[bool, str]:
        """
        验证用户名格式

        Returns:
            (是否通过, 错误信息)
        """
        if not username:
            return False, "用户名不能为空"

        if len(username) < self.config.min_username_length:
            return False, f"用户名长度至少{self.config.min_username_length}位"

        if len(username) > self.config.max_username_length:
            return False, f"用户名长度不能超过{self.config.max_username_length}位"

        # 只允许字母、数字、下划线
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return False, "用户名只能包含字母、数字和下划线"

        # 不能以数字开头
        if username[0].isdigit():
            return False, "用户名不能以数字开头"

        return True, "用户名格式正确"

    @staticmethod
    def validate_email(email: str) -> tuple[bool, str]:
        """
        验证邮箱格式

        Returns:
            (是否通过, 错误信息)
        """
        if not email:
            return True, ""  # 邮箱可选

        # 简单的邮箱格式验证
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return False, "邮箱格式不正确"

        return True, "邮箱格式正确"

    @staticmethod
    def sanitize_input(input_str: str) -> str:
        """清理用户输入，防止注入攻击"""
        if not input_str:
            return ""

        # 移除危险字符（使用str.translate一次性处理，更高效）
        dangerous_chars = '<>"\'&;()|`'
        translation_table = str.maketrans('', '', dangerous_chars)
        cleaned = input_str.translate(translation_table)

        # 限制长度
        return cleaned[:200]
