"""应用导航、显示元数据和权限代码的单一配置源。"""

from __future__ import annotations


GRANULAR_PERMISSION_MAP = {
    "数据预览": {
        "code": "data_preview",
        "sub_modules": {
            "工业": {"code": "data_preview.industrial", "tabs": None},
            "阿联酋": {"code": "data_preview.uae", "tabs": None},
        },
    },
    "监测分析": {
        "code": "monitoring_analysis",
        "sub_modules": {
            "工业": {
                "code": "monitoring_analysis.industrial",
                "tabs": {
                    "工业增加值分析": "monitoring_analysis.industrial.added_value",
                    "工业企业利润分析": "monitoring_analysis.industrial.profit",
                    "工业企业经营效率分析": "monitoring_analysis.industrial.efficiency",
                },
            },
            "阿联酋": {"code": "monitoring_analysis.uae", "tabs": None},
        },
    },
    "模型分析": {
        "code": "model_analysis",
        "sub_modules": {
            "DFM 模型": {
                "code": "model_analysis.dfm",
                "tabs": {
                    "数据准备": "model_analysis.dfm.prep",
                    "模型训练": "model_analysis.dfm.train",
                    "模型分析": "model_analysis.dfm.analysis",
                    "影响分解": "model_analysis.dfm.news",
                },
            },
        },
    },
    "数据探索": {
        "code": "data_exploration",
        "sub_modules": {
            "单变量分析": {
                "code": "data_exploration.univariate",
                "tabs": {
                    "平稳性检验": "data_exploration.univariate.stationarity",
                    "结构突变检验": "data_exploration.univariate.structural_break",
                },
            },
            "多变量分析": {
                "code": "data_exploration.bivariate",
                "tabs": {
                    "相关分析": "data_exploration.bivariate.correlation",
                    "领先滞后分析": "data_exploration.bivariate.lead_lag",
                },
            },
        },
    },
    "用户管理": {"code": "user_management", "sub_modules": None},
}

PERMISSION_MODULE_MAP = {
    name: [config["code"]]
    for name, config in GRANULAR_PERMISSION_MAP.items()
}

MODULE_CONFIG = {
    name: (
        {
            sub_name: (
                list(sub_config["tabs"])
                if sub_config.get("tabs")
                else None
            )
            for sub_name, sub_config in config["sub_modules"].items()
        }
        if config.get("sub_modules")
        else None
    )
    for name, config in GRANULAR_PERMISSION_MAP.items()
}

MAIN_MODULES = {
    "数据预览": {
        "icon": "[DATA]",
        "description": "查看和预览不同领域及国家的多频率经济数据",
    },
    "监测分析": {
        "icon": "[CHART]",
        "description": "对经济运行数据进行监测和分析",
    },
    "模型分析": {
        "icon": "[MODEL]",
        "description": "使用统计模型进行预测和分解分析",
    },
    "数据探索": {
        "icon": "[EXPLORE]",
        "description": "探索时间序列的统计特性和变量关系",
    },
    "用户管理": {
        "icon": "[USER]",
        "description": "管理用户及其访问权限",
    },
}
for _name, _metadata in MAIN_MODULES.items():
    sub_modules = GRANULAR_PERMISSION_MAP[_name].get("sub_modules") or {}
    _metadata["sub_modules"] = list(sub_modules)

SUB_MODULES = {
    "工业": {
        "icon": "[INDUSTRY]",
        "description": "工业数据预览与运行分析",
    },
    "阿联酋": {
        "icon": "[UAE]",
        "description": "基于工作簿真实数据的阿联酋宏观与石油财政监测",
    },
    "DFM 模型": {
        "icon": "[MODEL]",
        "description": "动态因子模型的数据准备、训练、分析和影响分解",
    },
    "数据探索": {
        "icon": "🔍",
        "description": "探索时间序列的统计特性和内在规律",
    },
    "单变量分析": {
        "icon": "📊",
        "description": "分析单个变量的平稳性与结构突变特征",
    },
    "多变量分析": {
        "icon": "🔗",
        "description": "分析两个变量的相关性和领先滞后关系",
    },
}

__all__ = [
    "GRANULAR_PERMISSION_MAP",
    "PERMISSION_MODULE_MAP",
    "MODULE_CONFIG",
    "MAIN_MODULES",
    "SUB_MODULES",
]
