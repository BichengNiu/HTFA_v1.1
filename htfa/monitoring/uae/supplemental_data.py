"""新增报告图的数据契约与变换，复用已发布的 DuckDB 表。"""

from dataclasses import dataclass

import pandas as pd

from htfa.monitoring.uae.database import PublishedUAEData, require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet

from htfa.monitoring.uae.periods import through_last_complete_month


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
    ChartSpec("dfm", "迪拜与阿布扎比股市综合指数（月均）", "日度_Wind", "日",
              (("DFM综合股指", "阿联酋DFM综合股票指数", "点"),
               ("FTSE ADX综合股指", "阿联酋FTSE ADX综合股票指数", "点"))),
    ChartSpec("cny_aed", "人民币兑迪拉姆汇率（月均）", "日度_Wind", "日",
              (("人民币兑迪拉姆", "人民币兑阿联酋迪拉姆", "AED/CNY"),)),
)
PROPERTY_CHARTS = (
    ChartSpec(
        "project_launch",
        "确认新期房项目数与活跃项目数（近28天口径，月均）",
        "周度_迪拜房地产",
        "周",
        (("确认新期房项目数", "经确认新期房项目数_近28天", "个"),
         ("活跃期房项目数", "活跃期房项目数_近28天", "个")),
        right=("活跃期房项目数",),
    ),
)
TRANSPORT_CHARTS = (
    ChartSpec("containers", "阿联酋港口集装箱进出口量", "月度_PortWatch", "月",
              (("集装箱进口量", "阿联酋:港口集装箱进口量:当月值", "吨"),
               ("集装箱出口量", "阿联酋:港口集装箱出口量:当月值", "吨"))),
    ChartSpec("port_calls", "阿联酋港口到港次数", "月度_PortWatch", "月",
              (("到港总次数", "阿联酋:港口到港总次数:当月值", "艘次"),
               ("集装箱到港次数", "阿联酋:港口集装箱到港次数:当月值", "艘次"),
               ("油轮到港次数", "阿联酋:港口油轮到港次数:当月值", "艘次"))),
    ChartSpec("air_transit", "迪拜航空货运转运量与转运占比", "月度_迪拜海关航空", "月",
              (("转运量", "迪拜航空货运_转运总量(吨)", "吨"),
               ("合计货量", "迪拜航空货运_合计总量(吨)", "吨")),
              right=("转运占比",)),
)
PRICE_CHARTS = (
    ChartSpec("steel", "阿联酋钢材进口报价（CFR/CPT区间中值）", "月度_MEsteel", "月",
              tuple((name, f"阿联酋:钢材进口报价:{name}:CFR/CPT:区间中值", "美元/吨")
                    for name in ("螺纹钢", "钢坯及方坯", "3mm热轧卷"))),
    ChartSpec(
        "cpi",
        "阿联酋居民消费价格同比变化（月度，%）",
        "月度_FCSC",
        "月",
        (("总体 CPI 同比", "阿联酋:消费者价格指数:总体同比变化(%)", "%"),
         ("食品与饮料 CPI 同比", "阿联酋:消费者价格指数:食品与饮料同比变化(%)", "%")),
        window_months=None,
    ),
)


def load_chart_data(
    content: PublishedUAEData, spec: ChartSpec,
    *, today: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict, dict[str, str]]:
    """校验原始频率与单位，日度和周度序列按有效观测转换为月均。"""
    with require_published_source(content).open() as book:
        values, metadata = parse_target_sheet(
            book, sheet_name=spec.sheet,
            targets=tuple((label, indicator) for label, indicator, _ in spec.series),
            allowed_frequencies={spec.frequency},
            expected_unit={label: unit for label, _, unit in spec.series},
            zero_is_missing=spec.sheet == "日度_Wind",
        )
    reference = pd.Timestamp.today().normalize() if today is None else pd.Timestamp(today).normalize()
    values = values.loc[values.index <= reference]
    if spec.frequency == "月":
        values = values.loc[values.index.to_period("M") < reference.to_period("M")]
    elif spec.frequency == "日":
        values = pd.DataFrame({
            name: through_last_complete_month(
                values[name], today=reference,
            ).resample("ME").mean()
            for name in values
        })
    elif spec.frequency == "周":
        # DLD 源表已限定完整周及完整自然月；按周末日期归月取均值。
        values = values.loc[
            values.index.to_period("M") < reference.to_period("M")
        ].resample("ME").mean()
    units = {label: unit for label, _, unit in spec.series}
    if spec.key == "air_transit":
        values["转运占比"] = values["转运量"].div(values["合计货量"].where(values["合计货量"] > 0)) * 100
        units = {"转运量": "吨", "转运占比": "%"}
    values = values.dropna(how="all")
    if values.empty:
        raise ValueError(f"{spec.title}没有可用观测")
    end = values.index.max()
    if spec.window_months is not None:
        values = values.loc[
            values.index >= end - pd.DateOffset(months=spec.window_months)
        ]
    return values, metadata, units
