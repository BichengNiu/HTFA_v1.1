# UAE 公开来源替代进度（2026-10-18）

统一脚本现登记 28 个来源。已自动替代 55 个原 Wind 工作表指标；保留历史表名
仅为兼容现有读取器，不代表这些列仍需要 Wind 更新。其他列尚未全部替代。

| 指标 | 公开来源及处理 | 本次观察期 |
|---|---|---|
| DFM 综合股票指数 | [DFM 官方历史页](https://www.dfm.ae/the-exchange/statistics-reports/historical-data/dfmgi)，动态发现公开 API | 2026-10-14 |
| EIBOR 隔夜、1 年 | [CBUAE EIBOR](https://www.centralbank.ae/en/forex-eibor/eibor-rates/)，官方图表 JSON | 2026-10-14 |
| EFFR | [纽约联储 API 文档](https://markets.newyorkfed.org/static/docs/markets-api.html)，effectiveDate 为观察日 | 2026-10-09 |
| USD/AED、CNY/AED | [CBUAE 汇率](https://www.centralbank.ae/en/forex-eibor/exchange-rates/)，人民币只取在岸 Chinese Yuan；AED/每单位外币 | 2026-10-13 |
| 政府及政府相关实体存贷款（4 列） | 库内 CBUAE 公报序列，百万 AED 除以 1000 转为十亿 AED | 2026-08 |
| 季度 GDP、非油 GDP、非金融公司增加值及 16 个行业（44 列） | FCSC UAE.Stat `DF_QGDP_CON` / `DF_QGDP_CUR` → `fcsc_gdp_quarterly`；保留官方修订与同比，百万 AED 转十亿 AED | 不变价 2026Q2；现价 2026Q1 |
| 石油及其他液体产量（1 列） | EIA International，UAE / product 53 / production → 月表、季度表；季度按日数加权，保留完整季度与原有百万桶/天单位 | 2026Q2 |

以上日度数据保存在 `public_market_daily`，月度存贷款保存在 `cbuae_monthly`，
季度 GDP 保存在 `fcsc_gdp_quarterly`，EIA 月度和季度产量分别保存在
`eia_liquids_monthly` 与 `eia_liquids_quarterly`。
Excel 匹配列只由 merge 从库写入；指标字典由统一合并流程同步。

利率报告只使用阿联酋央行 EIBOR 隔夜/1年及美联储纽约分行 EFFR，按月平均
并统一到三条序列共同的最新完整月份。旧 12 个月 Term SOFR 列保留历史数据，
不参与报告，不冒充纽约联储官方一年期利率。

| 尚未全部替代的类别 | 已找到的公开来源 | 实际限制 |
|---|---|---|
| GDP、行业增加值、CPI | [FCSC NSDP](https://fcsc.gov.ae/national-summary-data/)、[UAE.Stat CPI SDMX](https://releaseeuaestat.fcsc.gov.ae/rest/data/FCSA,DF_CPI/all?startPeriod=2021-01&dimensionAtObservation=AllDimensions) | 全国总体 CPI 与食品饮料 CPI 以月度同比变化（%）接入 `fcsc_monthly`，最新至 2026-06。已发布同比值优先直接采用；FCSC 未给出的 2022 年由同基期指数推算，2026 年由跨越基期更新的最近 12 个月官方环比变化复合计算。UAE.Stat 目前仅发布到 2026-06；GDP 与行业增加值已接入，见上表 |
| 中国与 UAE 双边贸易 | [中国海关月度统计](https://english.customs.gov.cn/statics/report/monthly.html) | 有按国家贸易表，但还没有完成金额单位、累计/当月及重复金额列的映射和自动适配 |
| DXB 旅客、货邮、起降 | [Dubai Airports 官方媒体页](https://media.dubaiairports.ae/dxb-enters-stronger-second-half-as-capacity-returns-and-investment-continues/) | 部分月份公布旅客数据，货运/起降常给季度或半年数；不能平均分摊冒充月度观察 |
| 印度对 UAE 咖啡出口 | [Coffee Board](https://coffeeboard.gov.in/database-coffee.html) | 有出口许可/目的地统计，尚未验证与工作簿累计指标完全一致的日期、财年和再出口口径 |
| SCAD 酒店、银行存贷款、原油产量 | 既有 SCAD、CBUAE、OPEC 独立来源已可自动更新 | 不同酒店类型、原油定义及单位需逐列核对；独立指标已更新不等于所有 Wind 别名已同步 |
| 穆尔班、石脑油、汽油、柴油、煤油、聚乙烯等报价 | 部分 EIA 等公开基准 | 原指标为金联创/隆众资讯特定地区、规格或报价。没有核实免费、同口径连续数据；不得用其他地区报价冒充 |
| ICE 布伦特连续期货 | ICE 官方及其他市场公开报价 | 连续合约换月规则和结算口径未验证；EIA 布伦特现货已有独立自动源，但不能当成期货 |
| 12 个月 Term SOFR | [CME Term SOFR](https://www.cmegroup.com/market-data/cme-group-benchmark-administration/term-sofr.html) | CME 历史数据通过 DataMine 提供；网页注明 view-only。纽约联储隔夜 SOFR、180 天平均均不是 12 个月前瞻 Term SOFR |

其他调查结果：

- Salik 在线修复完成，补齐 2025Q2/Q3/Q4，现为 18 个季末观察，最新 2026Q2。
- WPS 在线抓到 September 2026 QER；正文观察期 2026-06，员工同比 +11.2%，工资同比
  -2.3%。共 10 个观察期、20 行，保留 2024-06 员工同比没有具体数字的缺失值。
- 菲律宾 DMW 官方接口共列出 2026 年 1–8 月八期，没有 9 月；其中 6 月 Tab 11
  的 PDF/Excel 文件对象为空，现有本地历史文件保留，不把空链接当成零值。
- 尼泊尔新标题报告覆盖 2026-08-17 至 09-16，赴 UAE 审批含再入境 18,477、不含
  再入境 12,451。按项目原规则归到结束日期所在的 9 月；并非完整公历 9 月。
- DED 原始快照中有一条 `issue_date=2027-02-23`、`expiry_date=2026-02-04`、
  `load_timestamp=2026-08-04` 的矛盾记录。本次隔离，三个月度序列和分类型表
  均移除其未来月份贡献；原始快照不改。其他很早的年份未因年龄自动删除。
- [BTS 对应表](https://www.transtats.bts.gov/TableInfo.asp?gnoyr_VQ=FJE) 本次显示
  Latest Available Data: July 2026。当前 updater 已强制刷新最近三年，上一轮
  审计关于“默认复用导致当前落后”的判断不准确；9 月还未在该表公布。
