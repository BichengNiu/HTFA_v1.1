# Dashboard Preview 模块初始化

# 核心抽象层
from dashboard.preview.core import (
    BasePreviewConfig,
    FrequencyConfig,
    BaseDataLoader,
    BaseRenderer
)

# 领域模型层
from dashboard.preview.domain import LoadedPreviewData

# 子模块管理
from dashboard.preview.modules import PreviewModuleRegistry

# 工业子模块
from dashboard.preview.modules.industrial import (
    IndustrialConfig,
    IndustrialLoader,
    IndustrialRenderer
)

# 共享组件
from dashboard.preview.shared.frequency_utils import (
    get_indicator_frequencies,
    filter_indicators_by_frequency,
    iter_all_frequencies,
    create_empty_frequency_dict,
    get_all_frequency_names
)
from dashboard.preview.shared.calculators import calculate_summary
from dashboard.preview.shared.plotting import plot_indicator
from dashboard.preview.shared.components import create_filter_ui, display_summary_table
from dashboard.preview.shared.tabs import display_time_series_tab, display_overview_tab

# 配置接口
from dashboard.preview.modules.industrial.config import (
    COLORS,
    UI_TEXT,
    UNIFIED_FREQUENCY_CONFIGS,
    PLOT_CONFIGS,
    SUMMARY_CONFIGS,
    FREQUENCY_ORDER
)

# 数据加载接口
from dashboard.preview.modules.industrial.loader import (
    load_and_process_data,
    normalize_string,
    LoadedIndustrialData
)

__all__ = [
    # 核心抽象层
    'BasePreviewConfig',
    'FrequencyConfig',
    'BaseDataLoader',
    'BaseRenderer',

    # 领域模型层
    'LoadedPreviewData',

    # 子模块管理
    'PreviewModuleRegistry',

    # 工业子模块
    'IndustrialConfig',
    'IndustrialLoader',
    'IndustrialRenderer',

    # 数据加载接口
    'load_and_process_data',
    'normalize_string',
    'LoadedIndustrialData',

    # 配置接口
    'COLORS',
    'UI_TEXT',
    'UNIFIED_FREQUENCY_CONFIGS',
    'PLOT_CONFIGS',
    'SUMMARY_CONFIGS',
    'FREQUENCY_ORDER',

    # 共享组件
    'calculate_summary',
    'plot_indicator',
    'create_filter_ui',
    'display_summary_table',
    'display_time_series_tab',
    'display_overview_tab',

    # 频率工具
    'get_indicator_frequencies',
    'filter_indicators_by_frequency',
    'iter_all_frequencies',
    'create_empty_frequency_dict',
    'get_all_frequency_names',
] 