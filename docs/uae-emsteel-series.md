# Emsteel 月度公开钢筋报价

2026-11-03 核验。目标观察期为2024—2026年，当前只发布已结束且有报价依据的
2024年1月至2026年10月，共34个月；2026年11、12月不填造数值。

指标：`阿联酋:Emsteel钢筋月度公开报价:EXW:汇编含推算`；单位：AED/吨。
这是不含VAT的名义公开报价汇编，不是逐月市场成交均价。不同报道中存在
10–40毫米及12–32毫米等规格范围差异，不能声称所有月份完全同规格。

## 来源与缺月处理

- 基础历史：[Quanto公开JSON](https://quantohq.com/assets/data/price-index.json)，
  仅采用 `emsteel-xw` 的 `published` 记录，拒绝重复月份，排除 `excluded`。
  不把三个出厂/交货序列混接。提供方已取均值的记录原样保留并标记，
  不把均值解释为生产商直接公告，也不再平均存在冲突的报价。
- 2024年1、2月：[SEAISI](https://www.seaisi.org/details/24179?type=news-rooms)。
  2月为直接EXW报价，1月由2月减原文明确涨幅回溯。
- 2024年3月：[SteelOrbis四月公告](https://www.steelorbis.com/steel-prices/steel-prices-market-analyses/longs-and-billet/uae-based-esakeeps-rebar-prices-unchanged-amid-stable-demand-1332947.htm)，
  明确3月报价延续到4月，按不变价回溯3月。
- 2024年5月：[SteelOrbis](https://www.steelorbis.com/steel-prices/steel-prices-market-analyses/longs-and-billet/uaes-esa-issues-stable-rebar-price-for-may-amid-higher-stocks-1337404.htm)。
  基础报价另列于CPT报价之前，但基础报价句未直接写EXW，因此保留口径推断标记。
- 2024年6月：[SteelOrbis](https://www.steelorbis.com/steel-prices/steel-prices-market-analyses/longs-and-billet/uae-based-esa-cuts-rebar-prices-for-june-output-1341503.htm)，直接EXW报价。
- 2024年7月：[AISU](https://aisusteel.org/en/news/emirates-steel-arkan-keeps-rebar-prices-unchanged-for-july-output/2256)，
  采用原文AED报价。其他报道可能相差1 AED，保留原发布精度，不自行平均。
  旧 `/en/archives/27858` 现重定向新闻列表，采集使用迁移后的文章地址。
- 2024年9月：[SEAISI](https://www.seaisi.org/details/25300?type=news-rooms)，明确9月交货EXW。
- 2025年2月：[SteelOrbis](https://www.steelorbis.com/steel-prices/steel-prices-market-analyses/longs-and-billet/uae-rebar-suppliers-keep-offers-for-february-stable-in-line-with-emsteel-1376679.htm)，
  保留当期明确的官方EXW报价；与其他回顾性概述之间的差异保留为注释。
- 2025年4月：[SteelOrbis](https://www.steelorbis.com/steel-prices/steel-prices-market-analyses/longs-and-billet/uaes-emsteelcontinues-to-keep-rebar-offers-unchanged-for-the-third-consecutive-month-in-april-1384295.htm)，
  USD报价乘同文汇率；原币及汇率入库，结果保留三位小数，不冒充直接AED报价。
- 2025年5月：[SteelOrbis](https://www.steelorbis.com/steel-prices/steel-prices-market-analyses/longs-and-billet/uae-based-emsteelissues-rebar-prices-for-may-amid-stable-demand-1388335.htm)，
  直接EXW报价。原文将与此前美元报价的差额联系到常客优惠调整，并称实际成交
  水平基本不变；该点须视为报价安排变化，不能直接当成市场价格跌幅。
- 2025年6月：[SteelOrbis](https://www.steelorbis.com/steel-prices/steel-prices-market-analyses/longs-and-billet/uaes-emsteel-keeps-rebar-prices-stable-for-june-amid-lively-domestic-trade-1393041.htm)，直接EXW报价。

## 质量标记与限制

| 标记 | 含义 |
|---|---|
| reported | 从当期公开报道解析的报价 |
| difference_derived | 按明确的报价差额回溯 |
| rollover_derived | 按明确的不变价关系回溯 |
| basis_inferred | 基础报价存在，但EXW口径为推断 |
| fx_converted | 原文USD报价按同文汇率折算 |
| compiled_reported | Quanto整理的已发布报价，未逐条独立复核原报道 |
| compiled_source_mean | Quanto对不同来源的报价取均值，非钢厂直接报价 |
| compiled_rollover | Quanto按不变价公告沿用的数值 |
| year_inferred | Quanto来源说明含年份推断 |

一个月份可能有多个标记。2026年10月为Quanto按不变价公告沿用的记录，
具体金额尚未从免费公告正文独立核实；不得称为10月独立成交观测。
2025年12月的Quanto记录与AISU随后1月不变价报道有差异，保留冲突说明。
2026年初部分均值同样反映来源差异，不应从微小数值波动推断真实价格变化。

## 数据管线与维护

```powershell
runtime\python.exe -m htfa.jobs.uae_data.update_data --source emsteel
runtime\python.exe -m htfa.jobs.uae_data.update_data --source emsteel --skip-download
```

`source_emsteel.py` 保存解析规则及URL，不手填月度数值；原始JSON和HTML保存在
被忽略的 `data/UAE/raw/emsteel/`。缺少来源、月份识别失败、价格不可用、目录
口径变化、重复记录或历史截断均拒绝更新，不静默前填。

所有值与逐月来源先写DuckDB `emsteel_monthly` 长表（period为月末），再由
`merge()` 从库读取数值和出处，原子重建 `月度_EMSTEEL` 并同步指标字典。
数值单元格批注包含质量标记、来源URL和限制；报告快照经统一合并入口发布。
原 `mesteel_monthly` / `月度_MEsteel` 不参与本次替代，避免混淆进口报价与本地报价。

“34个月无日期缺口”仅代表公开报价汇编的时间覆盖完整，不代表34个月均为
独立、同规格、无冲突的原始观测。严格经济计量使用时须考虑质量标记及口径断点。
