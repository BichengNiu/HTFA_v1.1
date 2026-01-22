# -*- coding: utf-8 -*-
"""
定义用户、会话等数据结构
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Any
import uuid
import json

@dataclass
class User:
    """用户数据模型"""
    id: int
    username: str
    password_hash: str
    email: Optional[str] = None
    wechat: Optional[str] = None  # 微信号
    phone: Optional[str] = None  # 手机号
    organization: Optional[str] = None  # 单位名称
    permissions: List[str] = field(default_factory=list)  # 用户直接拥有的权限列表
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    is_active: bool = True
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    valid_from: Optional[date] = None  # 使用期限开始日期
    valid_until: Optional[date] = None  # 使用期限结束日期
    is_permanent: bool = False  # 是否永久有效(默认非永久)

    def is_locked(self) -> bool:
        """检查用户是否被锁定"""
        return self.locked_until and datetime.now() < self.locked_until
    
    def lock_account(self, duration_minutes: int = 30):
        """锁定账户"""
        self.locked_until = datetime.now() + timedelta(minutes=duration_minutes)
        self.failed_login_attempts = 0
    
    def unlock_account(self):
        """解锁账户"""
        self.locked_until = None
        self.failed_login_attempts = 0

    def is_expired(self) -> bool:
        """检查账户是否已过期"""
        if self.is_permanent:
            return False
        if self.valid_until is None:
            return False
        return date.today() > self.valid_until

    def is_not_yet_valid(self) -> bool:
        """检查账户是否尚未生效"""
        if self.is_permanent:
            return False
        if self.valid_from is None:
            return False
        return date.today() < self.valid_from

    def days_until_expiry(self) -> Optional[int]:
        """计算距离过期的天数,如果是永久账户或已过期返回None"""
        if self.is_permanent or self.valid_until is None:
            return None
        if self.is_expired():
            return None
        delta = self.valid_until - date.today()
        return delta.days

    def is_expiring_soon(self, days: int = 30) -> bool:
        """检查账户是否即将过期(默认30天内)"""
        days_left = self.days_until_expiry()
        if days_left is None:
            return False
        return 0 <= days_left <= days

    def to_dict(self) -> Dict[str, Any]:
        """
        将用户对象转换为字典（用于序列化）
        注意: datetime对象将被转换为ISO格式字符串
        """
        data = asdict(self)
        # 将datetime对象转换为字符串
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.last_login:
            data['last_login'] = self.last_login.isoformat()
        if self.locked_until:
            data['locked_until'] = self.locked_until.isoformat()
        # 将date对象转换为字符串
        if self.valid_from:
            data['valid_from'] = self.valid_from.isoformat()
        if self.valid_until:
            data['valid_until'] = self.valid_until.isoformat()
        # 移除密码哈希，不应暴露给前端
        data.pop('password_hash', None)
        return data


@dataclass
class UserSession:
    """用户会话数据模型"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=8))
    last_accessed: datetime = field(default_factory=datetime.now)
    is_active: bool = True

    def is_expired(self) -> bool:
        """检查会话是否过期"""
        return datetime.now() > self.expires_at
    
    def extend_session(self, hours: int = 8):
        """延长会话时间"""
        now = datetime.now()
        self.expires_at = now + timedelta(hours=hours)
        self.last_accessed = now
