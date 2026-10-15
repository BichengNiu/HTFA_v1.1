"""新增报告图的数据契约与变换，复用已发布的 DuckDB 表。"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from htfa.data.economic_workbook import EconomicWorkbookReader


@dataclass(frozen=True)
class ChartSpec:
    """一张图的稳定标识、来源和序列单位。"""

    key: str
    title: str
    sheet: str
    frequency: str
    series: tuple[tuple[str, str, str], ...]
    right: tuple[str, ...] = ()


FINANCE_CHARTS = (
    ChartSpec("dfm", "迪拜金融市场综合股指", "日度_Wind", "日",
              (("DFM综合股指", "阿联酋DFM综合股票指数", "点"),)),
    ChartSpec("cny_aed", "人民币兑迪拉姆汇率", "日度_Wind", "日",
              (("人民币兑迪拉姆", "人民币兑阿联酋迪拉姆", "AED/CNY"),)),
)
PROPERTY_CHARTS = (
    ChartSpec("project_launch", "经确认新期房项目数（近28天）", "周度_迪拜房地产", "周",
              (("新期房项目数", "经确认新期房项目数_近28天", "个"),)),
    ChartSpec("project_sales", "期房销售与活跃项目（近28天）", "周度_迪拜房地产", "周",
              (("期房销售笔数", "期房销售笔数_近28天", "笔"),
               ("活跃期房项目数", "活跃期房项目数_近28天", "个")),
              right=("活跃期房项目数",)),
    ChartSpec("project_indices", "房地产项目启动、销售吸收与商业转化指数", "周度_迪拜房地产", "周",
              (("项目启动指数", "项目启动指数", "指数"),
               ("销售吸收指数", "期房销售吸收指数", "指数"),
               ("商业转化指数", "项目商业转化指数", "指数"))),
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
)
READER = EconomicWorkbookReader("uae_monitoring", "monitoring.uae")


def load_chart_data(
    content: Any, file_name: str, spec: ChartSpec,
    *, today: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict, dict[str, str]]:
    """校验来源、频率与单位；月度排除未结束月份，日周度保留最新观测。"""
    frames, metadata = [], {}
    with READER.open_workbook(content, file_name=file_name) as (book, _):
        for label, indicator, unit in spec.series:
            frame, meta = READER.read_target_sheet(
                book, sheet_name=spec.sheet, targets=((label, indicator),),
                allowed_frequencies={spec.frequency}, expected_unit=unit,
                zero_is_missing=spec.sheet == "日度_Wind",
            )
            frames.append(frame)
            metadata.update(meta)
    values = pd.concat(frames, axis=1, sort=False).sort_index()
    reference = pd.Timestamp.today().normalize() if today is None else pd.Timestamp(today).normalize()
    values = values.loc[values.index <= reference]
    if spec.frequency == "月":
        values = values.loc[values.index.to_period("M") < reference.to_period("M")]
    units = {label: unit for label, _, unit in spec.series}
    if spec.key == "air_transit":
        values["转运占比"] = values["转运量"].div(values["合计货量"].where(values["合计货量"] > 0)) * 100
        values = values[["转运量", "转运占比"]]
        units = {"转运量": "吨", "转运占比": "%"}
    values = values.dropna(how="all")
    if values.empty:
        raise ValueError(f"{spec.title}没有可用观测")
    end = values.index.max()
    values = values.loc[values.index >= end - pd.DateOffset(months=36)]
    return values, metadata, units
