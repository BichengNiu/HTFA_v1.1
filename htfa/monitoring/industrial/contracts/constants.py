"""
工业分析常量定义
Industrial Analysis Constants

集中管理硬编码常量，避免魔法值分散在代码中
"""

# ============================================================================
# 数据列名常量
# ============================================================================

# 宏观工业数据列名
TOTAL_INDUSTRIAL_GROWTH_COLUMN = "中国:工业增加值:规模以上工业企业:当月同比"
CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN = "中国:工业增加值:规模以上工业企业:累计同比"

# 三大产业列名
MINING_INDUSTRY_COLUMN = "中国:工业增加值:规模以上工业企业:采矿业:当月同比"
MANUFACTURING_INDUSTRY_COLUMN = "中国:工业增加值:规模以上工业企业:制造业:当月同比"
UTILITIES_INDUSTRY_COLUMN = "中国:工业增加值:规模以上工业企业:电力、热力、燃气及水生产和供应业:当月同比"

# 企业利润数据列名
PROFIT_TOTAL_COLUMN = "中国:利润总额:规模以上工业企业:累计同比"
PROFIT_MARGIN_COLUMN_YOY = "中国:营业收入利润率:规模以上工业企业:累计同比"

# 价格指数列名
PPI_COLUMN = "中国:PPI:累计同比"

# 工作表名称
SHEET_NAME_MACRO_DATA = "分行业工业增加值同比增速"
SHEET_NAME_OVERALL_INDUSTRIAL = "总体工业增加值同比增速"
SHEET_NAME_ENTERPRISE_PROFIT = "工业企业利润"
SHEET_NAME_INDUSTRY_PROFIT = "分行业工业企业利润"

# ============================================================================
# 企业经营指标常量
# ============================================================================

# 企业指标图例名称映射
ENTERPRISE_INDICATOR_LEGEND_MAPPING = {
    PROFIT_TOTAL_COLUMN: "利润总额累计同比",
    PPI_COLUMN: "PPI累计同比",
    CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN: "工业增加值累计同比",
    PROFIT_MARGIN_COLUMN_YOY: "营业收入利润率累计同比"
}

# 条形图指标（使用堆积显示）
BAR_CHART_INDICATORS = [
    CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN,
    PPI_COLUMN,
    PROFIT_MARGIN_COLUMN_YOY
]

# 线图指标
LINE_CHART_INDICATORS = [
    PROFIT_TOTAL_COLUMN
]


# ============================================================================
# 图表配置常量
# ============================================================================

# 图表颜色列表（企业四指标图专用；通用 10 色调色板见 utils/chart_config.py 的 CHART_COLORS）
ENTERPRISE_INDICATOR_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']


# ============================================================================
# 状态管理常量
# ============================================================================

# 工业分析模块的统一命名空间
STATE_NAMESPACE_INDUSTRIAL = "industrial.analysis"

# 状态键常量 - 数据相关
STATE_KEY_MACRO_DATA = "macro_data"
STATE_KEY_WEIGHTS_DATA = "weights_data"
STATE_KEY_FILE_NAME = "file_name"

# 状态键常量 - 拉动率数据
STATE_KEY_CONTRIBUTION_EXPORT = "contribution_export"
STATE_KEY_CONTRIBUTION_STREAM = "contribution_stream"
STATE_KEY_CONTRIBUTION_INDUSTRY = "contribution_industry"
STATE_KEY_CONTRIBUTION_INDIVIDUAL = "contribution_individual"
STATE_KEY_TOTAL_GROWTH = "total_growth"
STATE_KEY_VALIDATION_RESULT = "validation_result"


# ============================================================================
# 内部数据文件路径
# ============================================================================

# 工业分行业属性及权重数据文件（内部配置文件，不需要用户上传）
INTERNAL_WEIGHTS_FILE_PATH = "data/工业分行业属性及权重.csv"
