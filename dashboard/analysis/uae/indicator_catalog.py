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
        "growth.nominal_gdp_yoy",
        ("阿联酋: GDP: 现价: 当季同比",),
        "名义GDP当季同比",
    ),
    IndicatorSpec(
        "growth.real_gdp_yoy",
        ("阿联酋: GDP: 不变价: 当季同比",),
        "实际GDP当季同比",
    ),
    IndicatorSpec(
        "growth.nonoil_nominal_gdp_yoy",
        ("阿联酋: GDP: 现价: 非石油: 当季同比",),
        "名义非石油GDP当季同比",
    ),
    IndicatorSpec(
        "growth.nonoil_real_gdp_yoy",
        ("阿联酋: GDP: 不变价: 非石油: 当季同比",),
        "实际非石油GDP当季同比",
    ),
    IndicatorSpec(
        "growth.nonfinancial_nominal_gdp_yoy",
        ("阿联酋: GDP: 现价: 非金融公司: 当季同比",),
        "名义非金融公司增加值当季同比",
    ),
    IndicatorSpec(
        "growth.nonfinancial_real_gdp_yoy",
        ("阿联酋: GDP: 不变价: 非金融公司: 当季同比",),
        "实际非金融公司增加值当季同比",
    ),
    IndicatorSpec(
        "oil.crude_production",
        (
            "阿联酋: 产量: 石油及其他液体",
            "阿联酋: 产量: 原油",
        ),
        "石油及其他液体产量",
    ),
    IndicatorSpec(
        "oil.dubai_crude_price",
        ("全球: 名义商品价格: 迪拜原油",),
        "迪拜原油价格",
        coverage="全球",
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
    "agriculture_forestry_fishing": (
        "农业、林业和渔业",
        "农业、林业和渔业",
    ),
    "manufacturing": ("制造业", "制造业"),
    "utilities_waste": (
        "电力、煤气、供水及废物管理",
        "电力、煤气、供水及废物管理",
    ),
    "construction": ("建筑业", "建筑业"),
    "wholesale_retail": (
        "批发零售业、汽车及摩托车修理",
        "批发零售与机动车维修",
    ),
    "transport_storage": ("运输和仓储", "运输和仓储"),
    "accommodation_food": ("住宿和餐饮服务业", "住宿和餐饮"),
    "information_communication": ("信息和通信", "信息和通信"),
    "finance_insurance": ("金融保险业", "金融保险"),
    "real_estate": ("房地产业", "房地产业"),
    "professional_scientific": ("专业、科技活动", "专业和科技活动"),
    "public_admin_defense": (
        "公共行政和国防、强制性社会保障",
        "公共行政、国防与社保",
    ),
    "education": ("教育类", "教育"),
    "health_social_work": (
        "人类健康和社会工作活动",
        "健康和社会工作",
    ),
    "arts_other_services": (
        "艺术、娱乐及其他服务活动",
        "艺术、娱乐及其他服务",
    ),
    "household_employers": ("家庭作为雇主的活动", "家庭雇主活动"),
}


REAL_INDUSTRY_INDICATOR_SPECS = tuple(
    IndicatorSpec(
        f"industry.{industry_id}.real",
        (f"阿联酋: GDP: 不变价: {workbook_name}",),
        f"{display_name}实际增加值",
    )
    for industry_id, (workbook_name, display_name) in INDUSTRY_NAMES.items()
)
NOMINAL_INDUSTRY_INDICATOR_SPECS = tuple(
    IndicatorSpec(
        f"industry.{industry_id}.nominal",
        (f"阿联酋: GDP: 现价: {workbook_name}",),
        f"{display_name}现价增加值",
    )
    for industry_id, (workbook_name, display_name) in INDUSTRY_NAMES.items()
)
INDUSTRY_INDICATOR_SPECS = (
    REAL_INDUSTRY_INDICATOR_SPECS
    + NOMINAL_INDUSTRY_INDICATOR_SPECS
)


INDICATOR_SPECS = BASE_INDICATOR_SPECS + INDUSTRY_INDICATOR_SPECS
UAE_SIGNATURE_IDS = frozenset(
    {
        "growth.real_gdp",
        "growth.nonoil_real_gdp",
    }
)
REAL_INDUSTRY_IDS = tuple(
    f"industry.{industry_id}.real"
    for industry_id in INDUSTRY_NAMES
)
NOMINAL_INDUSTRY_IDS = tuple(
    f"industry.{industry_id}.nominal"
    for industry_id in INDUSTRY_NAMES
)
