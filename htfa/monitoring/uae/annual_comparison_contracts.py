"""Pure data contract for harmonized GCC annual national accounts."""

COUNTRIES = {"ARE": "阿联酋", "SAU": "沙特阿拉伯", "BHR": "巴林", "KWT": "科威特", "OMN": "阿曼", "QAT": "卡塔尔"}
GDP_LEVEL = "NY.GDP.MKTP.CD"
GDP_GROWTH = "NY.GDP.MKTP.KD.ZG"
SECTOR_INDICATORS = {
    "NV.AGR.TOTL.ZS": ("年度_第一产业对比", "第一产业GDP占比（农业林业渔业）"),
    "NV.IND.TOTL.ZS": ("年度_第二产业对比", "第二产业GDP占比（工业含油气和建筑）"),
    "NV.SRV.TOTL.ZS": ("年度_第三产业对比", "第三产业GDP占比（服务业）"),
}
GDP_SHEET = "年度_GDP海合会对比"
GCC_NAME = "海合会六国平均"
LEVEL_SUFFIX = "GDP（现价）"
GROWTH_SUFFIX = "GDP增速（不变价）"
GDP_COMPARE_COLUMNS = [f"{name}{suffix}" for suffix in (LEVEL_SUFFIX, GROWTH_SUFFIX)
                       for name in ("阿联酋", GCC_NAME)]
REPORT_UNITS = {
    GDP_SHEET: {f"{name}{suffix}": unit
                for suffix, unit in ((LEVEL_SUFFIX, "十亿美元"), (GROWTH_SUFFIX, "%"))
                for name in (*COUNTRIES.values(), GCC_NAME)},
    **{sheet: {name: "%" for name in (*COUNTRIES.values(), GCC_NAME)}
       for sheet, _ in SECTOR_INDICATORS.values()},
}
COMPARISON_CHARTS = (
    (GDP_SHEET, "GDP现价总量与实际增速：阿联酋与海合会平均", False),
    *((sheet, title, False) for sheet, title in SECTOR_INDICATORS.values()),
)
