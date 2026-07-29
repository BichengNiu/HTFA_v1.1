"""阿联酋工作簿指标名到稳定语义ID的显式映射。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorSpec:
    """一个工作簿指标的语义映射。"""

    indicator_id: str
    aliases: tuple[str, ...]
    display_name: str
    coverage: str = "阿联酋全国"


BASE_INDICATOR_SPECS = (
    IndicatorSpec(
        "growth.real_gdp",
        ("阿联酋: GDP: 不变价",),
        "实际GDP",
    ),
    IndicatorSpec(
        "growth.nominal_gdp",
        ("阿联酋: GDP: 现价",),
        "名义GDP",
    ),
    IndicatorSpec(
        "growth.nonoil_real_gdp",
        ("阿联酋: GDP: 不变价: 非石油",),
        "实际非油GDP",
    ),
    IndicatorSpec(
        "growth.nonoil_nominal_gdp",
        ("阿联酋: GDP: 现价: 非石油",),
        "名义非油GDP",
    ),
    IndicatorSpec(
        "growth.nonfinancial_real_gdp",
        ("阿联酋: GDP: 不变价: 非金融公司",),
        "实际非金融公司增加值",
    ),
    IndicatorSpec(
        "growth.nonfinancial_nominal_gdp",
        ("阿联酋: GDP: 现价: 非金融公司",),
        "名义非金融公司增加值",
    ),
    IndicatorSpec(
        "oil.crude_production",
        ("阿联酋: 产量: 原油",),
        "原油产量",
    ),
    IndicatorSpec(
        "market.dfm_index",
        ("阿联酋DFM综合股票指数",),
        "DFM综合股票指数",
        coverage="迪拜金融市场",
    ),
    IndicatorSpec(
        "bilateral.china_odi_flow",
        ("中国: 对外直接投资流量: 亚洲: 阿联酋",),
        "中国对阿联酋直接投资流量",
        coverage="中国至阿联酋双边",
    ),
    IndicatorSpec(
        "bilateral.china_odi_stock",
        ("中国: 对外直接投资存量: 亚洲: 阿联酋",),
        "中国对阿联酋直接投资存量",
        coverage="中国至阿联酋双边",
    ),
)


INDUSTRY_NAMES = {
    "mining": ("采矿和采石(包括原油和天然气)", "采矿和采石"),
    "manufacturing": ("制造业", "制造业"),
    "construction": ("建筑业", "建筑业"),
    "real_estate": ("房地产业", "房地产业"),
    "wholesale_retail": (
        "批发零售业、汽车及摩托车修理",
        "批发零售与机动车维修",
    ),
    "transport_storage": ("运输和仓储", "运输和仓储"),
    "accommodation_food": ("住宿和餐饮服务业", "住宿和餐饮"),
    "information_communication": ("信息和通信", "信息和通信"),
    "finance_insurance": ("金融保险业", "金融保险"),
    "professional_scientific": ("专业、科技活动", "专业和科技活动"),
    "household_employers": ("家庭作为雇主的活动", "家庭雇主活动"),
}


INDUSTRY_INDICATOR_SPECS = tuple(
    spec
    for industry_id, (workbook_name, display_name) in INDUSTRY_NAMES.items()
    for spec in (
        IndicatorSpec(
            f"industry.{industry_id}.real",
            (f"阿联酋: GDP: 不变价: {workbook_name}",),
            f"{display_name}实际增加值",
        ),
        IndicatorSpec(
            f"industry.{industry_id}.nominal",
            (f"阿联酋: GDP: 现价: {workbook_name}",),
            f"{display_name}名义增加值",
        ),
    )
)


INDICATOR_SPECS = BASE_INDICATOR_SPECS + INDUSTRY_INDICATOR_SPECS
UAE_SIGNATURE_IDS = frozenset(
    {
        "growth.real_gdp",
        "growth.nominal_gdp",
        "growth.nonoil_real_gdp",
        "growth.nonoil_nominal_gdp",
    }
)
REAL_INDUSTRY_IDS = tuple(
    f"industry.{industry_id}.real"
    for industry_id in INDUSTRY_NAMES
)

