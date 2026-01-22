# -*- coding: utf-8 -*-
"""
认证模块数据库操作，提供用户与会话管理的 CRUD 能力
"""

import sqlite3
import json
import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from dashboard.auth.models import User, UserSession


class AuthDatabase:
    """认证数据库管理器"""

    # SQL字段列表常量
    USER_COLUMNS = (
        'id', 'username', 'password_hash', 'email', 'wechat', 'phone',
        'organization', 'permissions', 'created_at', 'last_login',
        'is_active', 'failed_login_attempts', 'locked_until',
        'valid_from', 'valid_until', 'is_permanent'
    )

    def __init__(self, db_path: str = None):
        """初始化数据库连接"""
        if db_path is None:
            # 默认数据库路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            data_dir = os.path.join(project_root, 'data')
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, 'users.db')

        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._init_database()

    def _build_user_from_row(self, row) -> User:
        """从数据库行构建User对象"""
        permissions = json.loads(row[7]) if row[7] else []
        return User(
            id=row[0],
            username=row[1],
            password_hash=row[2],
            email=row[3],
            wechat=row[4],
            phone=row[5],
            organization=row[6],
            permissions=permissions,
            created_at=datetime.fromisoformat(row[8]),
            last_login=datetime.fromisoformat(row[9]) if row[9] else None,
            is_active=bool(row[10]),
            failed_login_attempts=row[11],
            locked_until=datetime.fromisoformat(row[12]) if row[12] else None,
            valid_from=date.fromisoformat(row[13]) if row[13] else None,
            valid_until=date.fromisoformat(row[14]) if row[14] else None,
            is_permanent=bool(row[15]) if len(row) > 15 else False
        )

    def _init_database(self):
        """初始化数据库表结构"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建用户表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        email TEXT,
                        wechat TEXT,
                        phone TEXT,
                        organization TEXT,
                        permissions TEXT DEFAULT '[]',
                        created_at TEXT NOT NULL,
                        last_login TEXT,
                        is_active INTEGER DEFAULT 1,
                        failed_login_attempts INTEGER DEFAULT 0,
                        locked_until TEXT
                    )
                ''')

                # 创建会话表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                
                conn.commit()
                self.logger.info("数据库初始化完成")
                
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            raise
    
    # 用户操作
    def create_user(self, user: User) -> bool:
        """创建用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (username, password_hash, email, wechat, phone, organization,
                                     permissions, created_at, last_login, is_active, failed_login_attempts, locked_until,
                                     valid_from, valid_until, is_permanent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user.username,
                    user.password_hash,
                    user.email,
                    user.wechat,
                    user.phone,
                    user.organization,
                    json.dumps(user.permissions),
                    user.created_at.isoformat(),
                    user.last_login.isoformat() if user.last_login else None,
                    int(user.is_active),
                    user.failed_login_attempts,
                    user.locked_until.isoformat() if user.locked_until else None,
                    user.valid_from.isoformat() if user.valid_from else None,
                    user.valid_until.isoformat() if user.valid_until else None,
                    int(user.is_permanent)
                ))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            self.logger.warning(f"用户名 {user.username} 已存在")
            return False
        except Exception as e:
            self.logger.error(f"创建用户失败: {e}")
            return False
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    SELECT {', '.join(self.USER_COLUMNS)}
                    FROM users WHERE username = ?
                ''', (username,))

                row = cursor.fetchone()
                return self._build_user_from_row(row) if row else None
        except Exception as e:
            self.logger.error(f"获取用户失败: {e}")
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    SELECT {', '.join(self.USER_COLUMNS)}
                    FROM users WHERE id = ?
                ''', (user_id,))

                row = cursor.fetchone()
                return self._build_user_from_row(row) if row else None
        except Exception as e:
            self.logger.error(f"获取用户失败: {e}")
            return None
    
    def update_user(self, user: User) -> bool:
        """更新用户信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET password_hash = ?, email = ?, wechat = ?, phone = ?,
                           organization = ?, permissions = ?, last_login = ?, is_active = ?,
                           failed_login_attempts = ?, locked_until = ?,
                           valid_from = ?, valid_until = ?, is_permanent = ?
                    WHERE id = ?
                ''', (
                    user.password_hash,
                    user.email,
                    user.wechat,
                    user.phone,
                    user.organization,
                    json.dumps(user.permissions),
                    user.last_login.isoformat() if user.last_login else None,
                    int(user.is_active),
                    user.failed_login_attempts,
                    user.locked_until.isoformat() if user.locked_until else None,
                    user.valid_from.isoformat() if user.valid_from else None,
                    user.valid_until.isoformat() if user.valid_until else None,
                    int(user.is_permanent),
                    user.id
                ))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"更新用户失败: {e}")
            return False
    
    def get_all_users(self) -> List[User]:
        """获取所有用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    SELECT {', '.join(self.USER_COLUMNS)}
                    FROM users ORDER BY created_at DESC
                ''')

                return [self._build_user_from_row(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"获取所有用户失败: {e}")
            return []
    
    # 会话操作
    def create_session(self, session: UserSession) -> bool:
        """创建会话"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_sessions (session_id, user_id, created_at, expires_at, 
                                             last_accessed, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    session.session_id,
                    session.user_id,
                    session.created_at.isoformat(),
                    session.expires_at.isoformat(),
                    session.last_accessed.isoformat(),
                    int(session.is_active)
                ))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"创建会话失败: {e}")
            return False
    
    def get_session(self, session_id: str) -> Optional[UserSession]:
        """获取会话"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT session_id, user_id, created_at, expires_at, last_accessed, is_active
                    FROM user_sessions WHERE session_id = ?
                ''', (session_id,))
                
                row = cursor.fetchone()
                if row:
                    return UserSession(
                        session_id=row[0],
                        user_id=row[1],
                        created_at=datetime.fromisoformat(row[2]),
                        expires_at=datetime.fromisoformat(row[3]),
                        last_accessed=datetime.fromisoformat(row[4]),
                        is_active=bool(row[5])
                    )
                return None
        except Exception as e:
            self.logger.error(f"获取会话失败: {e}")
            return None
    
    def update_session(self, session: UserSession) -> bool:
        """更新会话"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE user_sessions SET expires_at = ?, last_accessed = ?, is_active = ?
                    WHERE session_id = ?
                ''', (
                    session.expires_at.isoformat(),
                    session.last_accessed.isoformat(),
                    int(session.is_active),
                    session.session_id
                ))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"更新会话失败: {e}")
            return False
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_sessions WHERE session_id = ?', (session_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"删除会话失败: {e}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        try:
            current_time = datetime.now().isoformat()
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM user_sessions WHERE expires_at < ? OR is_active = 0
                ''', (current_time,))
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            self.logger.error(f"清理过期会话失败: {e}")
            return 0
