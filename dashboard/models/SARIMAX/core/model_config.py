"""动态回归配置 facade。

按模型族实现的配置位于 ``*_config`` module；此文件只集中重导出公开
名称，保持页面与外部调用的稳定导入路径。
"""

from dashboard.models.SARIMAX.core.ardl_config import ARDLConfig
from dashboard.models.SARIMAX.core.config_shared import (
    ARDL_CRITERIA,
    ARDL_SEARCH_METHODS,
    AUTO_CRITERIA,
    RDL_INITIALIZATIONS,
    SARIMAX_COV_TYPES,
    SARIMAX_OPTIMIZERS,
    SARIMAX_RANGE_LIMITS,
    TREND_LABELS,
    TREND_OPTIONS,
)
from dashboard.models.SARIMAX.core.rdl_config import (
    RDLConfig,
    RDLInputConfig,
    RDLInterventionConfig,
    RDL_INTERVENTION_NAME,
)
from dashboard.models.SARIMAX.core.sarimax_config import (
    AutoSARIMAXConfig,
    SARIMAXConfig,
)

__all__ = [
    "ARDL_CRITERIA",
    "ARDL_SEARCH_METHODS",
    "AUTO_CRITERIA",
    "RDL_INITIALIZATIONS",
    "SARIMAX_COV_TYPES",
    "SARIMAX_OPTIMIZERS",
    "SARIMAX_RANGE_LIMITS",
    "TREND_LABELS",
    "TREND_OPTIONS",
    "ARDLConfig",
    "AutoSARIMAXConfig",
    "RDLConfig",
    "RDLInputConfig",
    "RDLInterventionConfig",
    "RDL_INTERVENTION_NAME",
    "SARIMAXConfig",
]
