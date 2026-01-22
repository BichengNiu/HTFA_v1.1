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
PROFIT_MARGIN_COLUMN_BASE = "中国:营业收入利润率:规模以上工业企业:累计值"
PROFIT_MARGIN_COLUMN_YOY = "中国:营业收入利润率:规模以上工业企业:累计同比"

# 价格指数列名
PPI_COLUMN = "中国:PPI:累计同比"

# 工作表名称
SHEET_NAME_MACRO_DATA = "分行业工业增加值同比增速"
SHEET_NAME_WEIGHTS = "工业增加值分行业指标权重"
SHEET_NAME_OVERALL_INDUSTRIAL = "总体工业增加值同比增速"
SHEET_NAME_PROFIT_BREAKDOWN = "分上中下游利润拆解"
SHEET_NAME_ENTERPRISE_PROFIT = "工业企业利润"
SHEET_NAME_INDUSTRY_PROFIT = "分行业工业企业利润"

# ============================================================================
# 指标名称映射
# ============================================================================

# 总体工业增加值变量名映射
OVERALL_INDUSTRIAL_NAME_MAPPING = {
    "规模以上工业增加值:当月同比": "工业",
    "制造业:当月同比": "制造业",
    "采矿业:当月同比": "采矿业",
}


# ============================================================================
# 企业经营指标常量
# ============================================================================

# 必需的四个企业经营指标
REQUIRED_ENTERPRISE_INDICATORS = [
    PROFIT_TOTAL_COLUMN,
    CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN,
    PPI_COLUMN,
    PROFIT_MARGIN_COLUMN_YOY
]

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
# 权重数据列名
# ============================================================================

# 必需的权重列
REQUIRED_WEIGHT_COLUMNS = ['指标名称', '出口依赖', '上中下游']

# 权重年份列
WEIGHT_YEAR_COLUMNS = ['权重_2012', '权重_2018', '权重_2020']


# ============================================================================
# 分组前缀
# ============================================================================

# 三大产业分组前缀
INDUSTRY_PREFIX = "三大产业_"


# ============================================================================
# 时间范围选项
# ============================================================================

TIME_RANGE_OPTIONS = ["1年", "3年", "5年", "全部", "自定义"]
DEFAULT_TIME_RANGE = "3年"


# ============================================================================
# 图表配置常量
# ============================================================================

# 最小匹配指标数（用于企业经营分析）
MIN_REQUIRED_INDICATORS = 3

# 图表颜色列表
CHART_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

# 图表高度配置
CHART_ROW_HEIGHT_PIXELS = 20  # 每行数据的像素高度
CHART_MIN_HEIGHT_PIXELS = 500  # 图表最小高度

# 图例显示最大示例数
MAX_EXAMPLE_INDICATORS = 5


# ============================================================================
# 状态管理常量
# ============================================================================

# 工业分析模块的统一命名空间
STATE_NAMESPACE_INDUSTRIAL = "industrial.analysis"

# 状态键常量 - 数据相关
STATE_KEY_UPLOADED_FILE = "uploaded_file"
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

# 状态键常量 - 时间范围（宏观分析）
STATE_KEY_MACRO_TIME_RANGE_CHART1 = "macro.time_range.chart1"
STATE_KEY_MACRO_TIME_RANGE_CHART2 = "macro.time_range.chart2"
STATE_KEY_MACRO_TIME_RANGE_CHART3 = "macro.time_range.chart3"

# 状态键常量 - 时间范围（企业分析）
STATE_KEY_ENTERPRISE_TIME_RANGE_CHART1 = "enterprise.time_range.chart1"
STATE_KEY_ENTERPRISE_TIME_RANGE_CHART2 = "enterprise.time_range.chart2"
STATE_KEY_ENTERPRISE_TIME_RANGE_CHART3 = "enterprise.time_range.chart3"

# 状态键常量 - 企业利润拆解数据
STATE_KEY_PROFIT_CONTRIBUTION_STREAM = "profit_contribution_stream"
STATE_KEY_PROFIT_CONTRIBUTION_INDIVIDUAL = "profit_contribution_individual"
STATE_KEY_PROFIT_TOTAL_GROWTH = "profit_total_growth"
STATE_KEY_PROFIT_VALIDATION_RESULT = "profit_validation_result"


# ============================================================================
# 内部数据文件路径
# ============================================================================

# 工业分行业属性及权重数据文件（内部配置文件，不需要用户上传）
INTERNAL_WEIGHTS_FILE_PATH = "data/工业分行业属性及权重.csv"
