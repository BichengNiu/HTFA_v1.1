# -*- coding: utf-8 -*-
"""
认证系统初始化脚本
用于初始化数据库和创建默认管理员账户
"""

import os
import sys
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from dashboard.auth.database import AuthDatabase
from dashboard.auth.models import User
from dashboard.auth.security import SecurityUtils


def init_auth_system():
    """初始化认证系统"""
    try:
        print("开始初始化认证系统...")
        
        # 初始化数据库
        db = AuthDatabase()
        print("[OK] 数据库初始化完成")
        
        # 检查是否已有管理员账户
        admin_user = db.get_user_by_username("admin")
        if admin_user:
            print("[OK] 管理员账户已存在")
        else:
            # 创建默认管理员账户
            admin_password = "admin123"  # 默认密码，建议首次登录后修改
            hashed_password = SecurityUtils.hash_password(admin_password)
            
            admin_user = User(
                id=0,  # 将由数据库自动分配
                username="admin",
                password_hash=hashed_password,
                email="admin@economic-platform.com",
                permissions=["data_preview", "monitoring_analysis", "model_analysis", "data_exploration", "user_management"],  # 管理员拥有所有权限
                created_at=datetime.now(),
                is_active=True
            )
            
            if db.create_user(admin_user):
                print("[OK] 默认管理员账户创建成功")
                print(f"  用户名: admin")
                print(f"  默认密码: {admin_password}")
                print("  [WARNING] 请在首次登录后立即修改密码")
            else:
                print("[ERROR] 管理员账户创建失败")
                return False
        
        # 验证权限系统
        print(f"[OK] 权限系统初始化完成")
        print("  可用权限模块:")
        from dashboard.auth.permissions import PERMISSION_MODULE_MAP
        for module, permissions in PERMISSION_MODULE_MAP.items():
            print(f"    - {module}: {permissions}")
        
        print("\n认证系统初始化完成！")
        return True
        
    except Exception as e:
        print(f"[ERROR] 认证系统初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_basic_functions():
    """测试基础功能"""
    try:
        print("\n开始测试基础功能...")
        
        db = AuthDatabase()
        
        # 测试用户验证
        admin_user = db.get_user_by_username("admin")
        if admin_user:
            print("[OK] 用户查询功能正常")
            
            # 测试密码验证
            if SecurityUtils.verify_password("admin123", admin_user.password_hash):
                print("[OK] 密码验证功能正常")
            else:
                print("[ERROR] 密码验证功能异常")
                return False
        else:
            print("[ERROR] 用户查询功能异常")
            return False
        
        # 测试权限查询
        if admin_user.permissions and "user_management" in admin_user.permissions:
            print("[OK] 权限系统功能正常")
        else:
            print("[ERROR] 权限系统功能异常")
            return False
        
        print("[OK] 所有基础功能测试通过")
        return True
        
    except Exception as e:
        print(f"[ERROR] 基础功能测试失败: {e}")
        return False


def main():
    """主函数"""
    print("=== 经济分析平台认证系统初始化 ===\n")
    
    # 初始化系统
    if not init_auth_system():
        sys.exit(1)
    
    # 测试基础功能
    if not test_basic_functions():
        sys.exit(1)
    
    print("\n=== 初始化完成 ===")
    print("可以开始使用认证系统了！")


if __name__ == "__main__":
    main()