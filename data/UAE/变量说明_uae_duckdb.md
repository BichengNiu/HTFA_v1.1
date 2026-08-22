# `uae.duckdb` 变量说明

> 检查日期：2026-08-22
> 数据库：`data/UAE/uae.duckdb`
> 说明：本文件根据 DuckDB 实际表内容、`meta_indicator_dictionary`、`meta_column_dictionary` 和 `meta_source_runs` 整理。缺失月份不会自动补 0，也不会前向填充；没有记录的月份与记录存在但数值为 `NULL` 分开统计。

## 一、数据库概况

数据库包含 24 张 `main` 聚合业务表、3 张 `main` 元数据表、7 张 `detail` 细粒度派生表，以及 `dld` 下 3 个业务视图和 1 个旧名兼容视图。`main` 中另保留 6 个只读兼容视图，供旧查询名称平滑过渡。当前已登记 250 个业务指标和 90 条 `meta_column_dictionary` 字段说明；Excel 指标字典有 293 个指标，全部 250 个 DuckDB 业务指标均已进入对应数据 sheet。

数据分层规则如下：`raw/` 只保存原始下载件、原始缓存和源下载工具；`main` 只保存仪表盘和工作簿使用的聚合指标；`detail` 保存为可追溯分析保留的细粒度派生数据，不是原始文件副本。旧的 `main.<表名>` 与 `dld.transactions` 名称均为只读兼容视图，物理数据不再位于这些旧名称下。

### 主要变量说明

| 数据源 / 表 | 变量名或变量族 | 频率与时间范围 | 缺失情况 | 数据来源 |
|---|---|---|---|---|
| Baker Hughes / `baker_hughes_monthly` | `阿联酋石油活跃钻机数` | 月；2024-01—2026-07；31 期 | 31 期均有值，无 NULL、无区间缺月 | Baker Hughes WorldWide Rig Count Report；Oil 口径，阿布扎比、迪拜、沙迦合计 |
| CBUAE / `cbuae_monthly` | 23 项：FTS 国内资金转账 6 项；国内信贷 3 项；外币存款 1 项；支票清算 2 项；银行国外资产/负债 2 项；非居民存款 5 项；政府及政府控股企业信贷/存款 4 项 | 月；大部分 2020-03—2026-06；每项 76 期 | 前 19 项无缺月、无 NULL；政府/政府控股企业 4 项为 2020-01—2026-06，共 77 期，但缺 2020-02；空值以不插行表达 | 阿联酋中央银行 CBUAE 月度公报；新旧公报口径已在 `source_cbuae.py` 统一 |
| Cloudflare Radar / `cloudflare_radar_daily` | `阿联酋:Cloudflare Radar网络流量(相对水平%)`、周度相对水平 | 日/周；共 142 条观测，2025-08-18—2026-08-18；日度 90 条、周度 52 条 | 已入库值无 NULL；指标为各自窗口内 min-max 归一化代理指标，不是绝对流量 | Cloudflare Radar UAE；原始 JSON/CSV 保存在 `data/UAE/raw/cloudflare_radar/` |
| GFS / `gfs_quarterly`、`gfs_annual` | 29 个政府财政科目：收入、税收、社会缴款、赠款、其他收入；费用及其子项；总/净营业余额；支出；净贷款或净借款；金融资产净获得及子项；非金融资产净投资及子项；负债净发生及子项。完整变量名为 `阿联酋:GFS:季度:<科目>` 或 `阿联酋:GFS:年度:<科目>` | 季度：28 个科目 2012Q1—2026Q1，共 57 期；“支出”科目 2016Q1—2026Q1，共 41 期。年度：28 个科目 2012—2025，共 14 年；“支出”科目 2016—2025，共 10 年 | 已入库值均非 NULL；“支出”在 2012—2015 年源文件中没有发布，不应视为异常缺报 | UAE Ministry of Finance（MOF）Government Finance Statistics；官方 PDF 提取 |
| PMI / `pmi_monthly` | `阿联酋非油私营部门采购经理人指数(PMI)` | 月；2023-07—2026-07；37 期 | 连续、无 NULL | S&P Global / Trading Economics 公开样本 |
| UN Comtrade 资本品 / `comtrade_monthly` | 金额与数量各 5 项：制造业设备、土木及基建施工设备、能源项目设备、钻探设备、港口及铁路专项设备；变量名分别为 `阿联酋:进口:<类别>:当月值` 和 `阿联酋:进口:<类别>:台数:当月值` | 月；土木、制造、港口铁路 2017-01—2026-06，共 114 期；能源项目、钻探 2017-01—2026-05，共 113 期 | 各系列在自身时间范围内连续，无 NULL；2026-06 对能源项目和钻探尚未入库 | UN Comtrade；设备分类由 HS6 组合，金额为百万美元，数量为台/件 |
| UN Comtrade 车辆金额 / `comtrade_vehicles_monthly` | `阿联酋:进口:车辆(HS87)总量:当月值`、乘用车、客车及巴士、货车、车辆零件；底层键为 HS `87`、`8703`、`8702`、`8704`、`8708` | 月；底层数据 2015-01—2026-07 | `units` 为空主要出现在 HS87 总量及 HS8708 零件；目标乘用车 HS8703 数量完整；商用车由 HS8702+8704 汇总，HS8702 有 1 个月数量缺失，需注意 2026-06 可能低估 | UN Comtrade HS87；以镜像口径 `all_mirror` 为主；已写入 `月度_汽车进口` |
| MEsteel / `mesteel_monthly` | 15 个钢材进口报价中值：0.32mm 马口铁、0.35mm 预涂镀锌卷、1mm 冷基热镀锌卷、1mm 冷轧卷、2mm 热基热镀锌卷、304/316L 不锈钢热轧卷、3mm 热轧卷、EN/UB/UC 型钢梁和槽钢、JIS 型钢梁、热轧钢板、线材、螺纹钢、角钢、钢坯及方坯 | 月；总体 2002-09—2026-08；单个产品起止月份不同 | 价格字段无 NULL；各产品存在 3—10 个未报价月份；0.32mm 马口铁最后一期为 2022-05；未报价月份不补值 | MEsteel；`lower`/`upper` 为报价区间，`midpoint` 为区间中值，单位美元/吨 |
| DLD 周度 / `dld_investment_pipeline_weekly` | `经确认新期房项目数_近28天`、`期房销售笔数_近28天`、`活跃期房项目数_近28天`、`项目启动指数`、`期房销售吸收指数`、`项目商业转化指数` | 周；2015-01-11—2026-08-09；605 周 | 6 个变量均完整、无 NULL、周序列连续 | Dubai Land Department；由 DLD 交易明细按项目和 28 天窗口计算 |
| DLD 月度销售 / `dld_sales_monthly` | 8 项：期房/现房 × 住宅/商业，各有“笔数”和“金额(百万AED)” | 月；住宅期房 2003-06—2026-08（234 期，区间缺 45 月）；住宅现房 1975-01—2026-08（350 期，缺 270 月）；商业期房 2006-02—2026-08（212 期，缺 35 月）；商业现房 1997-09—2026-08（348 期，连续） | 已有记录的金额和笔数无 NULL；缺少的月份代表该聚合结果没有生成记录，不应直接当作 0 | Dubai Land Department 交易明细；`Sales` × `Off-Plan/Existing` × `Residential/Commercial` 聚合 |
| DLD 租赁 / `dld_lease_monthly` | `迪拜:租赁合同总数(份)`、新签占比、续签占比、住宅占比、商业占比 | 月；2022-01—2024-11；35 个时间点 | 总数、新签、续签均完整；住宅占比和商业占比在 2022-03 各 1 个 NULL；月份本身连续 | Dubai Land Department Mo'asher；由 Property Finder Insights Hub 的 Official Rental Performance Index 镜像解析 |
| Dubai Customs 航空货运 / `dubai_airway_bill_monthly` | 13 项：进口/出口/合计的件数、体积、总量、运单数，以及境内总量、转运总量 | 月；2019-08—2026-08；85 个月 | 12 项连续、无 NULL；`迪拜航空货运_境内总量(吨)` 有 74 期，缺 11 个月：2020-09、2021-04、2021-06、2021-08、2022-10、2022-12、2023-01、2023-05、2023-06、2023-11、2023-12 | Dubai Customs Airway Bill Details；data.dubai 开放数据，数据集 ID 459114 |
| Emirates Post / `detail.emirates_post_monthly` | `阿联酋:国内邮政服务量(总件数)`；服务细分 EMS、Emirates ID、Express Mail、Flat Rate、Parcel Delivery、Parcel、Registered Mail | 月；总体可见 2022-01—2025-12，但实际有记录的月份为 47 个 | 2025-06 整月没有源记录；EMS 仅 2025-12；其他服务按自身发布区间变化。已入库的 `volume` 无 NULL；源文件同键重复 235 组，已按同键求和，原始行数保存在 `raw_rows` | Emirates Post / bay anat.ae 开放数据集 `Domestic_Volume_2022_2025`；明细按出发城市、到达城市和服务类型保存 |
| Eurostat / `detail.eurostat_air_monthly` | 12 项 EU27↔阿联酋航空指标：旅客 6 项（机上旅客数、载客数及抵达/离港）；货运与邮件 6 项（机上量、装载、卸载、装+卸及抵达/离港） | 聚合指标：旅客 2009-01—2025-12，共 204 期；货运 2008-01—2025-12，共 216 期 | EU27_2020 聚合序列连续、无 NULL；成员国明细存在各国不同时段缺报，不能直接等同于 EU 聚合缺失 | Eurostat 官方 API，`avia_paexcc`/`avia_goexcc`，`geo=EU27_2020`、`partner=AE`、`schedule=TOTAL` |
| US DOT / `dot_t100_monthly` | 10 项：执行航班；航空旅客合计、美→阿、阿→美；航空货运合计、美→阿、阿→美；航空邮件合计、美→阿、阿→美 | 月；1991-02—2026-05。合计 4 项各 348 期；美→阿 3 项各 344 期；阿→美 3 项各 345 期 | 该历史跨度应有 424 个月；合计项缺 76 月，美→阿缺 80 月，阿→美缺 79 月；已有记录无 NULL。2026-05 为当前库最新月份，存在约 2—3 个月发布滞后 | US DOT BTS T-100 International Segment（All Carriers）；双向航段聚合，旅客为人次，货运/邮件为磅 |
| UAEWPS / `uaewps_monthly` | `阿联酋:WPS平均工资同比%(3个月移动平均)`、`阿联酋:WPS覆盖员工数同比%(3个月移动平均)` | 季；2024Q2—2026Q1；9 期 | 工资指标完整；覆盖员工数在 2024Q2 为 1 个 NULL；QER 报告有额外源警告，缺值不应插补 | CBUAE Quarterly Economic Review（QER）WPS 图表 |
| Salik / `salik_active_vehicles_quarterly` | `阿联酋:Salik注册活跃车辆:季末值` | 季；2022Q1—2025Q1；13 期 | 连续、无 NULL；仅季末，不是月度数据；已写入 `季度_Salik` | Salik Company PJSC 投资者关系报告/演示材料 |
| 工作搜索热度 / `employment_search_index` | `work in dubai`、`work in uae` | 月；2004-01—2026-08；每项 272 期 | 连续、无 NULL；日期按输入 CSV 的 `Time` 原值保存，可能是月初，不强制改为月末 | `data/UAE/raw/employment/` 最新 CSV；人工维护的工作搜索热度数据，`visa uae` 未进入管线 |
| RTA / `rta_transport_monthly`、`rta_transport_daily` | 月度公交、水运、出租车趟次/车队；日度水运人次、公交平均速度，共 6 项 | 月度 222 行（公交 78、水运 42、出租车趟次/车队各 51）；日度 3,943 行（水运 2,828、公交速度 1,115），日度范围 2016-12—2026-08 | DuckDB 只保存聚合长表；RTA 明细 CSV 全部保存在 `data/UAE/raw/rta/`，不复制进主库，缺失月份/日期按缺行表达 | RTA Open Data（Data Dubai）；聚合逻辑见 `data/UAE/scripts/source_rta.py` |

## 二、数据库字典补全后的变量边界

本次已将数据库中的 250 个业务指标全部补入 `meta_indicator_dictionary` 和 Excel 对应数据 sheet；其中 Cloudflare、Eurostat、DOT、Dubai Customs、Salik、Google 搜索热度、Comtrade 设备/车辆等此前未接入工作簿的来源，已通过扩展合并阶段生成独立 sheet。细粒度派生表的字段、维度字段、质量标记仍补入 `meta_column_dictionary`。以下表保留变量族说明，使用时应同时查看两套字典和来源脚本。

| 表 | 变量 / 维度 | 时间范围与缺失 | 数据来源 |
|---|---|---|---|
| `foreign_labour_monthly` | `bangladesh_clearance`、`source_count`；`nepal_with_reentry`、`nepal_without_reentry`；`philippines_total`、`philippines_new_hires`、`philippines_rehires`；`proxy_sum`、`proxy_index`；辅助 `quality_flag` | 孟加拉和来源计数 2023-07—2026-07，37 期；尼泊尔 2025-05—2026-07，15 期；菲律宾 2025-01—2026-06，缺 2025-12、2026-02；代理指标 2025-05—2026-06，缺 2025-12、2026-02。2026-02 有一条质量标记，说明菲律宾官方累计值环比回落，不能可靠差分 | 菲律宾 DMW、尼泊尔 DOFE、孟加拉 BMET/OEP 官方页面及公告 |
| `ded_monthly` | `records`、`enterprises`、`licences`、`official_new_licenses` | 三个快照聚合序列有 622 行，实际存储日期为 1906-01—2027-02；官方序列 5 行，2020-12—2022-06，期间稀疏 | Dubai Department of Economy and Tourism / DED，data.dubai 数据集；单期快照按发照日期聚合 |
| `ded_monthly_by_type` | 25 个 `legal_form` 分类，如 `Limited Liability Company(LLC)`、`Sole Establishment`、`Branch of Foreign Company` 等；数值列 `records` | 4,264 行；各法律形式只在有记录月份出现，时间范围从 1906-01 到 2027-02，不能把类别缺行理解为 0 | 同上，DED 单期快照 |
| `detail.comtrade_partner_detail` | `category`、`reporter`、`partner`、`value`；5 个资本品类别的国家/伙伴明细 | 6,958 行；2017-01—2026-06；国家维度存在不规则覆盖，适合做来源拆分，不适合直接当作完整面板 | UN Comtrade |
| `detail.comtrade_quantity_detail` | `hs6`、`item_count`、`source_type`、`reported_estimated`、`mirror_reporter_count` | 5,307 行；与资本品数量明细对应；`source_type`/估算标志用于判断直报与镜像口径 | UN Comtrade |
| `detail.eurostat_air_monthly` | `dataset`、`geo`、`partner`、`schedule`、`unit`、`tra_meas`、`value` | 62,162 行；2008-01—2026-06；含 EU27_2020 聚合及 27 个成员国明细。聚合序列与成员国序列的发布时间不同 | Eurostat 官方 API |
| `detail.portwatch_uae_daily` | 15 个港口；`portcalls_*` 到港次数、`import_*` 进口吨位、`export_*` 出口吨位，另有 `portcalls`、`import`、`export` | 41,640 行；2019-01-01—2026-08-07；日度镜像字段目前无 NULL | IMF PortWatch，HDX 镜像；UAE 港口日度活动数据 |
| `detail.portwatch_chokepoint_daily` | 28 个海峡；`n_*` 过境次数、`capacity_*` 载货容量，另有 `n_total`、`capacity` | 77,784 行；2019-01-01—2026-08-09；日度镜像字段目前无 NULL。当前业务聚合只取霍尔木兹海峡 `chokepoint6` | IMF PortWatch，HDX 镜像；海峡日度过境数据 |
| `detail.dld_transactions` | `transaction_id`、`instance_date`、`trans_group_en`、`reg_type_en`、`project_number`、`actual_worth`、`property_type_en`、`property_usage_en`、`load_timestamp` | 1,763,793 条；交易日期 1416-07-02—2026-08-10。`transaction_id` 唯一；`project_number` 有 467,456 条 NULL；有 4 条 1900 年以前异常日期，已进入 `dld.transaction_date_quality_issues` 视图 | Dubai Land Department / Data Dubai bulk 交易快照 |

## 三、缺失和质量结论

1. **缺失主要通过“缺行”表达。** CBUAE、DOT、DLD 销售、MEsteel、Emirates Post 等表通常不会为缺报月份写一行，因此 `COUNT(value)` 为 0 不代表该月经济指标为 0。
2. **明确的 NULL 共 5 类重点问题：** DLD 租赁住宅/商业占比各 1 个（2022-03）；UAEWPS 覆盖员工数 1 个（2024Q2）；车辆底层数量字段主要在 HS87/8708，且 HS8702 有 1 个目标分类月份缺失；外籍劳动力表 2026-02 通过质量标记表达不可可靠差分。
3. **时间范围异常需要优先处理：** DED 三个快照序列出现 1906 年和 2027 年日期；DLD 交易明细有 4 条 1900 年以前日期。它们可能来自源快照中的异常发照日期或日期解析结果，使用 DED/DLD 长期趋势前应单独过滤或核实。
4. **指标字典与工作簿已完成对齐。** 当前 DuckDB 已登记 250 个业务指标、90 条字段说明；Excel 指标字典 293 个指标，250 个数据库指标均有真实数据列支撑，孤立字典项为 0。新增来源按 `日度_CloudflareRadar`、`周度_CloudflareRadar`、`月度_Eurostat航空`、`月度_DOTT100`、`月度_迪拜海关航空`、`季度_Salik`、`月度_工作搜索热度` 等独立 sheet 写入；后续新增变量仍应先写入 DuckDB，再由合并流程同步 Excel。
5. **已完成的结构性检查：** 主键/唯一键冲突未发现于已检查的核心长表；DLD `detail.dld_transactions.transaction_id` 无重复；DLD 周度序列连续；GFS 季度/年度序列连续；EU27 聚合序列连续；Emirates Post 源文件重复键已在入库前求和并保留 `raw_rows` 审计字段。

## 四、建议的使用规则

- 月度分析前按指标自身的时间范围建立日历表，显式保留缺报月份；不要统一把缺行填成 0。
- 需要连续序列的模型优先使用 CBUAE、PMI、GFS、DLD 周度、Dubai Customs 合计项等完整度较高的变量；对 DOT、MEsteel、DLD 销售、外籍劳动力、Emirates Post 先做覆盖率检查。
- DED 应增加“有效日期范围/未来日期”质检；DLD 应继续保留异常日期视图，不要让异常交易进入长期趋势聚合。
- 若新增变量或把未登记变量接入工作簿，遵循项目规定：先写入 `data/UAE/uae.duckdb`，再由 DuckDB 合并到 `data/UAE/阿联酋.xlsx`，不要直接改 Excel 指标数据。

## 五、复核 SQL

```sql
-- 已登记业务指标
SELECT * FROM meta_indicator_dictionary ORDER BY source, indicator_name;

-- 最近一次各来源运行状态
WITH ranked AS (
    SELECT *, row_number() OVER (PARTITION BY source ORDER BY started_at DESC) AS rn
    FROM meta_source_runs
)
SELECT source, started_at, status, note
FROM ranked
WHERE rn = 1
ORDER BY source;

-- 典型长表的时间范围、记录数和数值缺失
SELECT indicator, COUNT(*) AS rows, COUNT(value) AS nonnull_values,
       COUNT(*) - COUNT(value) AS null_values,
       MIN(period) AS first_period, MAX(period) AS last_period
FROM cbuae_monthly
GROUP BY indicator
ORDER BY indicator;
```
