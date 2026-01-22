# -*- coding: utf-8 -*-
"""
数据库迁移脚本: 添加用户使用期限字段
执行时间: 2025-01-XX
功能: 为users表添加valid_from, valid_until, is_permanent三个字段
"""

import sqlite3
import os
import logging
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_path():
    """获取数据库路径"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    data_dir = os.path.join(project_root, 'data')
    return os.path.join(data_dir, 'users.db')


def check_column_exists(cursor, table_name, column_name):
    """检查列是否已存在"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def migrate():
    """执行数据库迁移"""
    db_path = get_db_path()

    if not os.path.exists(db_path):
        logger.error(f"数据库文件不存在: {db_path}")
        return False

    logger.info(f"开始迁移数据库: {db_path}")

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 检查字段是否已存在
            if check_column_exists(cursor, 'users', 'valid_from'):
                logger.warning("字段 valid_from 已存在,跳过迁移")
                return True

            logger.info("添加字段: valid_from, valid_until, is_permanent")

            # 添加新字段
            cursor.execute('ALTER TABLE users ADD COLUMN valid_from TEXT')
            cursor.execute('ALTER TABLE users ADD COLUMN valid_until TEXT')
            cursor.execute('ALTER TABLE users ADD COLUMN is_permanent INTEGER DEFAULT 0')

            logger.info("字段添加成功")

            # 更新现有用户数据
            logger.info("更新现有用户数据...")

            # 获取所有用户
            cursor.execute('SELECT id, username FROM users')
            users = cursor.fetchall()

            logger.info(f"找到 {len(users)} 个现有用户")

            # 计算日期
            today = date.today()
            trial_end_date = today + timedelta(days=7)

            for user_id, username in users:
                if username.lower() == 'admin':
                    # 管理员账户设置为永久有效
                    cursor.execute('''
                        UPDATE users
                        SET is_permanent = 1, valid_from = NULL, valid_until = NULL
                        WHERE id = ?
                    ''', (user_id,))
                    logger.info(f"设置管理员账户 '{username}' 为永久有效")
                else:
                    # 普通用户设置7天试用期
                    cursor.execute('''
                        UPDATE users
                        SET is_permanent = 0,
                            valid_from = ?,
                            valid_until = ?
                        WHERE id = ?
                    ''', (today.isoformat(), trial_end_date.isoformat(), user_id))
                    logger.info(f"设置用户 '{username}' 试用期: {today} ~ {trial_end_date}")

            conn.commit()
            logger.info("数据库迁移完成")
            return True

    except Exception as e:
        logger.error(f"迁移失败: {e}")
        return False


def rollback():
    """回滚迁移(移除添加的字段)"""
    db_path = get_db_path()

    logger.info(f"开始回滚迁移: {db_path}")
    logger.warning("SQLite不支持DROP COLUMN,需要手动重建表")
    logger.info("回滚步骤:")
    logger.info("1. 备份现有数据")
    logger.info("2. 删除users表")
    logger.info("3. 重新创建users表(不包含新字段)")
    logger.info("4. 恢复数据")

    return False


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        success = rollback()
    else:
        success = migrate()

    if success:
        logger.info("操作成功")
        sys.exit(0)
    else:
        logger.error("操作失败")
        sys.exit(1)
