"""
认证系统配置模块
提供统一的安全和认证配置
"""
import os
from dataclasses import dataclass


@dataclass
class AuthConfig:
    """认证系统统一配置类"""

    # 调试模式 - 设为True时跳过认证
    debug_mode: bool = os.getenv('HTFA_DEBUG_MODE', 'false').lower() == 'true'

    # 密码策略
    min_password_length: int = 8
    max_password_length: int = 128
    require_letter: bool = True
    require_digit: bool = True
    require_special_char: bool = True

    # 用户名策略
    min_username_length: int = 3
    max_username_length: int = 20

    # 登录安全
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30

    # 会话配置
    session_duration_hours: int = 8
    remember_me_duration_hours: int = 24

    @classmethod
    def is_debug_mode(cls) -> bool:
        """检查是否处于调试模式"""
        return DEFAULT_CONFIG.debug_mode


# 全局默认配置实例
DEFAULT_CONFIG = AuthConfig()
