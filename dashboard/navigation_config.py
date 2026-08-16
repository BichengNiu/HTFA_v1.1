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
            "单变量时间序列": {
                "code": "model_analysis.univariate_ts",
                "tabs": {
                    "SARIMAX 模型": "model_analysis.univariate_ts.sarimax",
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
    name: config["code"]
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

__all__ = [
    "GRANULAR_PERMISSION_MAP",
    "PERMISSION_MODULE_MAP",
    "MODULE_CONFIG",
]
