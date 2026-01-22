# -*- coding: utf-8 -*-
"""
UI组件库常量定义
"""

from enum import Enum
from typing import Dict, List, Any

class NavigationLevel(Enum):
    """导航层级枚举"""
    MAIN_MODULE = "main_module"      # 第一层：主模块选择
    SUB_MODULE = "sub_module"        # 第二层：子模块选择  
    FUNCTION = "function"            # 第三层：具体功能

class UIConstants:
    """UI常量定义"""

    # 数据探索模块列表（用于数据共享）
    EXPLORATION_ANALYSIS_MODULES = ['stationarity', 'time_lag_corr', 'lead_lag']

    # 主模块配置
    MAIN_MODULES = {
        "数据预览": {
            "icon": "[DATA]",
            "description": "查看和预览各类经济数据，提供工业数据的全面展示和分析",
            "sub_modules": ["工业"]
        },
        "监测分析": {
            "icon": "[CHART]",
            "description": "对经济运行数据进行深度监测和分析，提供专业的分析报告",
            "sub_modules": ["工业"]
        },
        "模型分析": {
            "icon": "[MODEL]",
            "description": "使用先进的机器学习模型进行经济预测和分析",
            "sub_modules": ["DFM 模型"]
        },
        "数据探索": {
            "icon": "[EXPLORE]",
            "description": "深入探索时间序列数据的统计特性和内在规律，包括平稳性分析和相关性分析",
            "sub_modules": []
        }
    }

    # 子模块配置
    SUB_MODULES = {
        "工业": {
            "icon": "[INDUSTRY]",
            "description": "工业数据的预览和分析，支持多频率数据展示（日度、周度、旬度、月度、年度）"
        },
        "DFM 模型": {
            "icon": "[MODEL]",
            "description": "动态因子模型分析工具，支持数据准备、模型训练、结果分析和新闻分解"
        },
        "数据探索": {
            "icon": "🔍",
            "description": "深入探索时间序列数据的统计特性和内在规律"
        },
        "时序性质": {
            "icon": "📊",
            "description": "分析单个变量的平稳性特征，包括ADF检验和KPSS检验"
        },
        "时序关系": {
            "icon": "🔗",
            "description": "分析两个变量之间的相关性和领先滞后关系"
        }
    }

    # HTML模板常量
    HTML_TEMPLATES = {
        # 子模块卡片模板
        "sub_module_card": """
        <div style="
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 1.5rem;
            margin: 1rem 0;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
            height: 200px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        ">
            <div style="font-size: 3em; margin-bottom: 0.5rem;">{icon}</div>
            <h3 style="margin: 0.5rem 0; color: #333;">{title}</h3>
            <p style="color: #666; font-size: 0.9em; margin: 0;">{description}</p>
        </div>
        """,

        # 功能卡片模板
        "function_card": """
        <div style="
            border: 1px solid #f0f0f0;
            border-radius: 6px;
            padding: 1.5rem;
            margin: 0.5rem 0;
            background: #fafafa;
            text-align: center;
            height: 180px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        ">
            <div style="font-size: 2.5em; margin-bottom: 0.5rem;">{icon}</div>
            <h4 style="margin: 0.5rem 0; color: #333;">{title}</h4>
            <p style="color: #666; font-size: 0.85em; margin: 0;">{description}</p>
        </div>
        """,

        # 模块卡片模板（带悬停效果）
        "module_card": """
        <div style="
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 1.5rem;
            margin: 1rem 0;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
            height: {height};
            display: flex;
            flex-direction: column;
            justify-content: center;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 8px rgba(0,0,0,0.15)';"
           onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 4px rgba(0,0,0,0.1)';">
            <div style="font-size: 3em; margin-bottom: 0.5rem;">{icon}</div>
            <h3 style="margin: 0.5rem 0; color: #333; font-weight: 600;">{title}</h3>
            <p style="color: #666; font-size: 0.9em; margin: 0; line-height: 1.4;">{description}</p>
        </div>
        """
    }

# 简化的模板工具函数
def get_template(template_name: str) -> str:
    """获取HTML模板"""
    if template_name not in UIConstants.HTML_TEMPLATES:
        raise ValueError(f"模板 '{template_name}' 不存在")
    return UIConstants.HTML_TEMPLATES[template_name]


def render_template(template_name: str, **kwargs) -> str:
    """渲染HTML模板"""
    template = get_template(template_name)
    return template.format(**kwargs)
