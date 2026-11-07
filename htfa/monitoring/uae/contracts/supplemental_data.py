from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ChartSpec:
    """一张图的稳定标识、来源和序列单位。"""

    key: str
    title: str
    sheet: str
    frequency: str
    series: tuple[tuple[str, str, str], ...]
    right: tuple[str, ...] = ()
    window_months: int | None = 36


FINANCE_CHARTS = (
    ChartSpec(
        "dfm",
        "迪拜与阿布扎比股市综合指数（月均）",
        "日度_Wind",
        "日",
        (
            ("DFM综合股指", "阿联酋DFM综合股票指数", "点"),
            ("FTSE ADX综合股指", "阿联酋FTSE ADX综合股票指数", "点"),
        ),
    ),
    ChartSpec(
        "cny_aed",
        "人民币兑迪拉姆汇率（月均）",
        "日度_Wind",
        "日",
        (("人民币兑迪拉姆", "人民币兑阿联酋迪拉姆", "AED/CNY"),),
    ),
)
PROPERTY_CHARTS = (
    ChartSpec(
        "project_launch",
        "确认新期房项目数与活跃项目数（近28天口径，月均）",
        "周度_迪拜房地产",
        "周",
        (
            ("确认新期房项目数", "经确认新期房项目数_近28天", "个"),
            ("活跃期房项目数", "活跃期房项目数_近28天", "个"),
        ),
        right=("活跃期房项目数",),
    ),
)
TRANSPORT_CHARTS = (
    ChartSpec(
        "containers",
        "阿联酋港口集装箱进出口量",
        "月度_PortWatch",
        "月",
        (
            ("集装箱进口量", "阿联酋:港口集装箱进口量:当月值", "吨"),
            ("集装箱出口量", "阿联酋:港口集装箱出口量:当月值", "吨"),
        ),
    ),
    ChartSpec(
        "port_calls",
        "阿联酋港口到港次数",
        "月度_PortWatch",
        "月",
        (
            ("到港总次数", "阿联酋:港口到港总次数:当月值", "艘次"),
            ("集装箱到港次数", "阿联酋:港口集装箱到港次数:当月值", "艘次"),
            ("油轮到港次数", "阿联酋:港口油轮到港次数:当月值", "艘次"),
        ),
    ),
    ChartSpec(
        "air_transit",
        "迪拜航空货运转运量与转运占比",
        "月度_迪拜海关航空",
        "月",
        (
            ("转运量", "迪拜航空货运_转运总量(吨)", "吨"),
            ("合计货量", "迪拜航空货运_合计总量(吨)", "吨"),
        ),
        right=("转运占比",),
    ),
)
PRICE_CHARTS = (
    ChartSpec(
        "steel",
        "Emsteel钢筋月度公开报价（EXW，汇编含推算）",
        "月度_EMSTEEL",
        "月",
        (
            (
                "Emsteel钢筋",
                "阿联酋:Emsteel钢筋月度公开报价:EXW:汇编含推算",
                "迪拉姆/吨",
            ),
        ),
    ),
    ChartSpec(
        "cpi",
        "阿联酋居民消费价格同比变化（月度，%）",
        "月度_FCSC",
        "月",
        (
            ("总体 CPI 同比", "阿联酋:消费者价格指数:总体同比变化(%)", "%"),
            ("食品与饮料 CPI 同比", "阿联酋:消费者价格指数:食品与饮料同比变化(%)", "%"),
        ),
        window_months=None,
    ),
)
