"""阿联酋 V2 七条高频传导链的展示配置。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorSpec:
    """单个待接入高频指标的展示元数据。"""

    name: str
    frequency: str
    source: str
    source_url: str | None


@dataclass(frozen=True)
class ChannelSpec:
    """单条经济传导链的页面配置。"""

    key: str
    tab_label: str
    title: str
    objective: str
    transmission: tuple[str, ...]
    indicators: tuple[IndicatorSpec, ...]
    downstream_signals: tuple[str, ...]
    chart_slots: tuple[str, ...]


FRED_BRENT = "https://fred.stlouisfed.org/series/DCOILBRENTEU"
FRED_EFFR = "https://fred.stlouisfed.org/series/EFFR"
FRED_VIX = "https://fred.stlouisfed.org/series/VIXCLS"
FRED_USD = "https://fred.stlouisfed.org/series/DTWEXBGS"
CBUAE_STATS = (
    "https://www.centralbank.ae/en/research-and-statistics/latest-statistics/"
)
CBUAE_POLICY = (
    "https://www.centralbank.ae/en/our-operations/"
    "monetary-policy-and-domestic-markets/"
)
CBUAE_EIBOR = "https://www.centralbank.ae/en/forex-eibor/eibor-rates/"
DLD_DATA = "https://dubailand.gov.ae/en/open-data/real-estate-data/"
DFM_DATA = (
    "https://www.dfm.ae/the-exchange/statistics-reports/historical-data/dfmgi"
)
ADX_DATA = "https://www.adx.ae/Resources/Report%20Center/Overview"
PORTWATCH = "https://portwatch.imf.org/"
SCAD_DATA = "https://scad.gov.ae/download-publications"
PMI_RELEASES = "https://www.pmi.spglobal.com/Public/Release/PressReleases"
DUBAI_POPULATION = (
    "https://www.dsc.gov.ae/en-us/EServices/Pages/"
    "Display-Population-Clock.aspx"
)
DUBAI_TOURISM = "https://www.dubaidet.gov.ae/en/research-and-insights"
RIG_COUNT = "https://rigcount.bakerhughes.com/intl-rig-count"


CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec(
        key="oil_fiscal",
        tab_label="1 石油—财政",
        title="石油生产与收入",
        objective="跟踪油价和产量冲击如何经财政能力、政府支出传导至非油部门。",
        transmission=(
            "油价与产量",
            "石油收入",
            "财政能力",
            "政府投资与支出",
            "建筑与服务业",
            "订单、支付与就业",
            "非油 GDP",
        ),
        indicators=(
            IndicatorSpec("Brent 原油价格", "日度", "ICE/金联创", None),
            IndicatorSpec("UAE 原油产量", "月度", "OPEC", None),
            IndicatorSpec("估算石油收入", "月度", "油价 × 产量", None),
            IndicatorSpec("UAE 活跃钻机数", "月度", "Baker Hughes", RIG_COUNT),
            IndicatorSpec("政府存款", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("政府及 GRE 信贷", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("PMI 产出/新订单/就业", "月度", "S&P Global", PMI_RELEASES),
            IndicatorSpec("客户及银行转账", "月度", "CBUAE", CBUAE_STATS),
        ),
        downstream_signals=(
            "政府流动性与财政支出空间",
            "建筑、基建和服务业订单",
            "企业支付与就业活动",
            "非油经济增长动能",
        ),
        chart_slots=("油价与产量冲击", "估算石油收入"),
    ),
    ChannelSpec(
        key="monetary_credit",
        tab_label="2 货币—信贷",
        title="Fed → CBUAE → EIBOR → 信贷 → 国内需求",
        objective="监测美元联系汇率下，海外利率变化向本地融资成本和内需的传导。",
        transmission=(
            "Fed Funds",
            "CBUAE 基础利率",
            "EIBOR",
            "银行融资成本",
            "企业/住房/消费信贷",
            "投资与消费",
            "非油 GDP",
        ),
        indicators=(
            IndicatorSpec("有效联邦基金利率", "日度", "FRED", FRED_EFFR),
            IndicatorSpec("CBUAE 基础利率", "政策日", "CBUAE", CBUAE_POLICY),
            IndicatorSpec("EIBOR 1M/3M/6M/12M", "日度", "CBUAE", CBUAE_EIBOR),
            IndicatorSpec("私营部门信贷", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("房地产与建筑信贷", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("个人贷款", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("M1/M2/M3", "月度", "CBUAE", CBUAE_STATS),
        ),
        downstream_signals=(
            "政策利率与市场利率利差",
            "私营部门信用扩张",
            "房地产、建筑和居民融资需求",
            "货币与内需拐点",
        ),
        chart_slots=("政策利率与 EIBOR 曲线", "信贷、货币与国内需求"),
    ),
    ChannelSpec(
        key="capital_assets",
        tab_label="3 资本—资产",
        title="全球资本 → UAE 流动性 → 房地产/股票 → 投资",
        objective="识别全球风险偏好、跨境流动性和本地资产价格之间的联动。",
        transmission=(
            "全球流动性与风险",
            "资本流入 UAE",
            "居民/非居民存款",
            "信贷与资产配置",
            "房地产与股票",
            "投资及财富效应",
            "非油 GDP",
        ),
        indicators=(
            IndicatorSpec("VIX", "日度", "FRED", FRED_VIX),
            IndicatorSpec("广义美元指数", "日度", "FRED", FRED_USD),
            IndicatorSpec("居民及非居民存款", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("银行国外资产及负债", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("Dubai 房地产成交", "日度/逐笔", "DLD", DLD_DATA),
            IndicatorSpec("DFM 指数与成交", "日度", "DFM", DFM_DATA),
            IndicatorSpec("ADX 指数与成交", "日度", "ADX", ADX_DATA),
        ),
        downstream_signals=(
            "非居民资金流入与银行外部融资",
            "房地产成交量、金额和单价",
            "ADX/DFM 市场成交与风险偏好",
            "建筑投资和居民财富效应",
        ),
        chart_slots=("全球风险与 UAE 流动性", "房地产及股票资产温度"),
    ),
    ChannelSpec(
        key="trade_logistics",
        tab_label="4 贸易—物流",
        title="全球需求 → UAE 贸易 → 港口物流 → 企业活动",
        objective="用港口、海运、贸易和订单数据捕捉外需变化向企业活动的传导。",
        transmission=(
            "全球/中国/印度需求",
            "进出口与转口",
            "港口和海运",
            "物流/批零/仓储",
            "企业订单与支付",
            "非油 GDP",
        ),
        indicators=(
            IndicatorSpec("UAE 主要港口靠港量", "日度", "IMF PortWatch", PORTWATCH),
            IndicatorSpec("估算海运贸易量", "日度", "IMF PortWatch", PORTWATCH),
            IndicatorSpec("Jebel Ali/Khalifa/Fujairah 活动", "日度", "IMF PortWatch", PORTWATCH),
            IndicatorSpec("Abu Dhabi 非油商品贸易", "月度", "SCAD", SCAD_DATA),
            IndicatorSpec("PMI 新订单/出口订单", "月度", "S&P Global", PMI_RELEASES),
            IndicatorSpec("客户及银行转账", "月度", "CBUAE", CBUAE_STATS),
        ),
        downstream_signals=(
            "主要贸易伙伴需求强弱",
            "港口吞吐、靠港和海运量",
            "物流、批零及仓储景气",
            "企业新订单与支付活动",
        ),
        chart_slots=("外需与海运高频脉冲", "贸易订单与企业活动"),
    ),
    ChannelSpec(
        key="population_consumption",
        tab_label="5 人口—消费",
        title="人口/迁移 → 住房 → 消费 → 服务业",
        objective="观察人口流入如何推升住房需求，并进一步传导至居民消费和服务业。",
        transmission=(
            "人口流入与迁移",
            "住房需求",
            "租金与房产交易",
            "家庭消费",
            "零售/交通/餐饮/服务",
            "非油 GDP",
        ),
        indicators=(
            IndicatorSpec("Dubai Population Clock", "近实时", "DSC", DUBAI_POPULATION),
            IndicatorSpec("DLD 房地产销售", "日度/逐笔", "DLD", DLD_DATA),
            IndicatorSpec("DLD 租赁/Ejari", "日度/逐笔", "DLD", DLD_DATA),
            IndicatorSpec("成交金额/单价/面积", "日度/逐笔", "DLD", DLD_DATA),
            IndicatorSpec("个人贷款", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("客户转账/支票清算", "月度", "CBUAE", CBUAE_STATS),
        ),
        downstream_signals=(
            "人口净流入与住房新增需求",
            "销售、租赁和价格压力",
            "居民信贷和支付活跃度",
            "零售、交通、餐饮及服务业需求",
        ),
        chart_slots=("人口与住房需求", "居民消费和服务活动"),
    ),
    ChannelSpec(
        key="tourism_services",
        tab_label="6 旅游—服务",
        title="旅游 → 酒店 → 零售/交通 → 服务业",
        objective="通过游客、酒店量价和支付指标追踪旅游对服务业的即时拉动。",
        transmission=(
            "国际游客/商务旅行",
            "酒店客人及间夜",
            "入住率/ADR/价格",
            "零售/餐饮/交通",
            "就业与支付",
            "非油 GDP",
        ),
        indicators=(
            IndicatorSpec("Abu Dhabi 酒店客人", "月度", "SCAD", SCAD_DATA),
            IndicatorSpec("Abu Dhabi 客人间夜", "月度", "SCAD", SCAD_DATA),
            IndicatorSpec("酒店入住率/设施数", "月度", "SCAD", SCAD_DATA),
            IndicatorSpec("Abu Dhabi 酒店价格指数", "月度", "SCAD", SCAD_DATA),
            IndicatorSpec("Dubai 旅游表现", "月度/报告", "Dubai DET", DUBAI_TOURISM),
            IndicatorSpec("客户转账/支付活动", "月度", "CBUAE", CBUAE_STATS),
        ),
        downstream_signals=(
            "国际休闲与商务客流",
            "酒店入住率、间夜与价格",
            "零售、餐饮和交通消费",
            "服务业就业与支付",
        ),
        chart_slots=("游客与酒店经营", "旅游向服务业的传导"),
    ),
    ChannelSpec(
        key="geopolitical_risk",
        tab_label="7 地缘风险",
        title="地缘政治风险 → 物流冲击/避险资本 → UAE",
        objective="同时监测物流成本上行的负向冲击与避险资本流入的正向效应。",
        transmission=(
            "区域地缘风险",
            "霍尔木兹/航运扰动",
            "贸易物流与成本",
            "避险资本分流",
            "存款/房地产/金融资产",
            "非油活动与金融稳定",
        ),
        indicators=(
            IndicatorSpec("霍尔木兹海峡船舶流量", "日度", "IMF PortWatch", PORTWATCH),
            IndicatorSpec("Fujairah/UAE 港口活动", "日度", "IMF PortWatch", PORTWATCH),
            IndicatorSpec("Brent 原油价格", "日度", "FRED", FRED_BRENT),
            IndicatorSpec("VIX 与广义美元指数", "日度", "FRED", FRED_VIX),
            IndicatorSpec("非居民存款/银行国外负债", "月度", "CBUAE", CBUAE_STATS),
            IndicatorSpec("Dubai 房地产成交", "日度/逐笔", "DLD", DLD_DATA),
            IndicatorSpec("ADX/DFM 市场成交", "日度", "ADX/DFM", ADX_DATA),
        ),
        downstream_signals=(
            "航运中断、物流时效与成本压力",
            "油价和全球风险偏好变化",
            "避险资金流入银行及本地资产",
            "非油活动与金融稳定净效应",
        ),
        chart_slots=("航运扰动与成本冲击", "避险资本与本地资产"),
    ),
)
