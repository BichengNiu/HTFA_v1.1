# 石油及银行指标未到10月的原因核对（2026-11-10）

核验日期：2026年11月10日。结论须区分源站观测月份、下载执行日期、已入库月份和图表实际展示月份。上一次作业返回成功，代表所请求的数据已抓取、解析及发布成功，不代表所有来源均已提供10月数据。

## 逐项结论

| 指标 | 原图末期 | 当前源数据末期 | 原因及处理 |
| --- | --- | --- | --- |
| 阿联酋原油产量 | 2026-09 | OPEC 2026-09 | 官方当前最新为10月版MOMR，其实际产量观察期到9月；下一期计划11月11日发布。截至核验日没有从当前OPEC月报读到10月产量 |
| 月度估算石油收入 | 2026-09 | 可计算至2026-09 | 依赖布伦特月均价×同月OPEC产量×当月天数；缺10月产量，不能补算10月收入。不以9月产量前向填充 |
| 布伦特原油月均价格 | 2026-09 | 库内日度至2026-11-03，完整月可到2026-10 | 程序错误：从收入表取价格，且按收入/迪拜价格的共同末期截断，导致已有10月价格未展示。已修复，曲线和下载均推进到10月，10月均价123.92727272727274美元/桶 |
| 迪拜原油月均价格 | 2026-09 | IMF PCPS 2026-09 | 11月10日直接重取当前IMF API，417个观测中最后一期仍为9月；官方商品价格页面的Excel下载亦标为September 2026。没有把其他机构价格直接混入该序列 |
| 银行外债 | 2026-08 | CBUAE 2026-08 | 最新《Statistical Bulletin August 2026》的原始观察期为8月 |
| 外币存款 | 2026-08 | CBUAE 2026-08 | 同一公报，原始观察期为8月 |
| 外国主体存款 | 2026-08 | CBUAE 2026-08 | 非居民私人企业、个人、政府及非商业实体三项存款合计；三项输入都到8月，按三项齐全才求和 |
| 政府贷款 | 2026-08 | CBUAE 2026-08 | 同一公报的Domestic Credit表，源数据到8月 |
| 政府控股企业贷款 | 2026-08 | CBUAE 2026-08 | 同一公报的Domestic Credit表，源数据到8月 |
| 私人企业信贷 | 2026-08 | CBUAE 2026-08 | 同一公报的Domestic Credit表，源数据到8月 |
| 工商业贷款 | 2026-08 | CBUAE 2026-08 | 同一公报，沿用已核实的Corporate减Other Financial Corporations口径；不存在由该推算补出9、10月的依据 |
| 个人信贷 | 2026-08 | CBUAE 2026-08 | 同一公报的Domestic Credit表，源数据到8月 |

央行最新统计列表中的“06 October 2026”是8月公报的发布日期，不能解释为10月数据。在线列表接口本次返回75份统计公报，按观察月份排序的最新一期仍为2026-08。重新下载该期官方Excel并用现有解析器读取，79个观测月的最后一期也是2026-08；库内23项银行指标的最后非空记录均为2026-08-31。未发现程序拿到9、10月原文后漏解析的证据。

## 已修复的价格展示限制

原有两层截断分别位于：

1. `htfa/monitoring/uae/ui/oil/renderer.py::_render_charts`：价格输入来自收入表，收入表日期受产量限制；又以收入与迪拜油价的共同末期决定价格窗口。
2. `htfa/monitoring/uae/ui/oil/charts.py::build_oil_price_figure`：再次按两条油价中较早的末期裁掉整张图。

修复后，布伦特按其原始日度观测独立计算完整自然月均值，迪拜按其自身月度观测展示；两条曲线共享坐标轴，但各自保留实际末期。10月迪拜值留空，不填零、不沿用9月值。图表下载与绘图输入一致。收入窗口只取收入自身可计算的完整月份，不再由与该估算无关的迪拜报价决定。

本次未新增指标、改动源数据或换用其他机构的油价，也未修改图表样式、控件和Ts参数；数据库及Excel保留已有观测，界面重新使用库内已存在的10月布伦特数据。

## 官方核验来源

- [OPEC月报及2026年发布日历](https://www.opec.org/monthly-oil-market-report.html)：当前页面为MOMR October 2026；日历列出下一期11月11日。
- [OPEC当前数字月报](https://publications.opec.org/momr/)及[当前World oil supply表](https://publications.opec.org/momr/chapter/162/3037)：本次解析阿联酋最新观察月2026-09，3,917,000桶/日。
- [IMF商品价格页面](https://www.imf.org/en/research/commodity-prices)：Excel Database: September 2026。
- [IMF PCPS数据集](https://data.imf.org/en/datasets/IMF.RES:PCPS)及项目当前使用的[Dubai月度API](https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/G001.POILDUB.USD.M?startPeriod=1992-01)：本次最新为2026-09-30，111.8252380952381美元/桶。
- [CBUAE最新统计目录](https://centralbank.ae/en/research-and-statistics/latest-statistics/)及[Statistical Bulletin August 2026官方Excel](https://centralbank.ae/media/wvzpz5qo/statistical-bulletin-august-2026.xlsx)：观察月8月，目录发布日期10月6日。目录实际内容由官网MediaListing API动态返回，不能把静态HTML的No Record当作无公报。
- 布伦特日度使用[美国EIA官方XLS](https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls)及项目既有EIA API系列；本次核对的是已发布库内观测，没有将11月未完结日度数据作为11月完整均价。

## 验证

- 先检查实际Ts源码位置 `D:/programs/Ts`，现有 `plot_series` 已能保留不等长序列的缺失尾值；Ts测试527项通过。未修改Ts源码，因此无需新增Ts提交或复制运行时文件。
- HTFA石油面板、月份边界和共享选项检查35项通过。新增回归覆盖：两条油价末期不同、价格比产量更新、收入比迪拜报价更新、未完结当月排除、下载与图表一致。
- 原有Ts调用参数及默认值未改动，无新增控件或WIDGET_KEYS；共享参数映射检查通过。
- 对真实发布库运行石油面板AppTest，无异常、错误或数据警告；实际四图渲染及价格图预览通过。
- 真实数据验证：布伦特图/下载末期2026-10-31，迪拜曲线最后非空值2026-09-30，10月迪拜下载值为空；原油产量、估算收入仍到2026-09-30；外国主体存款仍到2026-08-31。
- 在线原文、解析结果、截图与查询工作记录保存在本机 `.cache/uae-source-audit-2026-11-10/`，不入Git。原始数据及凭据不提交。

银行覆盖核对SQL：

```sql
SELECT indicator, MAX(period), COUNT(*)
FROM cbuae_monthly
WHERE value IS NOT NULL
GROUP BY indicator
ORDER BY indicator;
```
