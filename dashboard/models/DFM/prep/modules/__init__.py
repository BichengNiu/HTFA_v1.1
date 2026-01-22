"""
数据准备模块包

这个包包含了数据准备过程中的各个模块化组件：
- config_constants: 配置和常量
- format_detection: 格式检测
- data_loader: 数据加载
- data_aligner: 数据对齐
- data_cleaner: 数据清理
- detrend_processor: 去趋势处理
- variable_transformer: 变量转换
- publication_calibrator: 发布日期校准
"""

# 数据加载
from dashboard.models.DFM.prep.modules.data_loader import DataLoader

# 数据对齐
from dashboard.models.DFM.prep.modules.data_aligner import (
    DataAligner,
    align_to_theoretical_index
)

# 数据清理
from dashboard.models.DFM.prep.modules.data_cleaner import (
    DataCleaner,
    clean_dataframe
)

# 格式检测
from dashboard.models.DFM.prep.modules.format_detection import (
    detect_sheet_format,
    parse_sheet_info
)

# 去趋势处理
from dashboard.models.DFM.prep.modules.detrend_processor import (
    DetrendProcessor,
    DetrendError,
    InsufficientDataError,
    RegressionFailedError
)

# 变量转换
from dashboard.models.DFM.prep.modules.variable_transformer import (
    VariableTransformer,
    get_default_transform_config,
    FREQUENCY_PERIOD_MAP
)

# 发布日期校准
from dashboard.models.DFM.prep.modules.publication_calibrator import (
    PublicationCalibrator,
    calibrate_publication_dates
)

__version__ = "2.1.0"
__author__ = "Data Preparation Module"

__all__ = [
    # 数据加载
    'DataLoader',
    # 数据对齐
    'DataAligner',
    'align_to_theoretical_index',
    # 数据清理
    'DataCleaner',
    'clean_dataframe',
    # 格式检测
    'detect_sheet_format',
    'parse_sheet_info',
    # 去趋势处理
    'DetrendProcessor',
    'DetrendError',
    'InsufficientDataError',
    'RegressionFailedError',
    # 变量转换
    'VariableTransformer',
    'get_default_transform_config',
    'FREQUENCY_PERIOD_MAP',
    # 发布日期校准
    'PublicationCalibrator',
    'calibrate_publication_dates',
]
