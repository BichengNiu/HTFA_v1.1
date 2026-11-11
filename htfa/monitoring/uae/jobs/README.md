# htfa/monitoring/uae/jobs —— UAE 数据维护作业

本目录是 `htfa.monitoring.uae.jobs` 包；数据资产（`uae.duckdb`、`阿联酋.xlsx`、
`raw/`、`.env`）仍位于 `htfa/monitoring/uae/assets/`。所有路径由 `paths.py` 集中解析，作业模块
使用包内相对导入，不依赖运行时 `sys.path` 注入。

## 入口

```powershell
runtime\python.exe -m htfa.monitoring.uae.jobs.update_data      # 抓取→清洗→入库→合并对应工作簿工作表
runtime\python.exe -m htfa.monitoring.uae.jobs.merge_workbook   # 单独重跑库→阿联酋.xlsx 合并
.\htfa\monitoring\uae\jobs\update_data.bat                    # 双击等价入口（同上）
.\htfa\monitoring\uae\jobs\merge_workbook.bat
```

常用参数：`--source cbuae,gfs`、`--skip-download`（只用 raw 缓存）、`--force`。

`--source emsteel` 将 Quanto 的 Emsteel 月度公开报价与缺月的 SteelOrbis、
SEAISI、AISU 当期报道合并，先写 `emsteel_monthly`，再重建 `月度_EMSTEEL`。
它是含推算的名义报价汇编，非成交均价；逐月质量标记、原币、汇率、来源 URL 和原文哈希入库，
Excel 数值批注保留来源与限制。不会插值补月；本地EXW序列使用独立指标名称。
详见 [数据管线约束](../../../docs/data-pipeline.md)。

活动与退役来源以 `source_registry.py` 为准。标准更新／合并入口按退役规则清理
生产库表、受管工作表和指标字典；不得从旧资料恢复已停用来源。原始资料仅作为
本地审计证据，不参加发布。

T-100 统一采用仓库内 `download_t100.py` 直接访问BTS官方表单，强制重抓最近
三年年包，不依赖 raw 目录里的浏览器脚本。`uae_<year>.source.json` 分别记录
官网“Latest Available Data”与实际美阿航段月份，便于识别源站滞后和下载漏月。

每日云端数据更新已恢复，UAE 高频来源与能源保供统一在迪拜时间09:00运行；
Linux 使用 OOXML 写表，无需 Windows Excel。范围、失败保护、凭据与运行记录见
[数据管线约束](../../../docs/data-pipeline.md)。上述本地维护入口继续可用。

PortWatch 从官方 ArcGIS Hub 在线目录读取字段和源版本，严格核对公开权限、
发布者、图层及服务 URL；实际观测仍从原 FeatureServer 的行 ID 清单分批抓取，
长批次用 POST，校验前后 ID 集合、行数、业务唯一键、港口目录和源版本。
UAE 港口逐港读取，海峡按港口和年份受控并发读取并与整表 ID 清单核对，
底库保留全部15个UAE港口及28个海峡。
在线确认源版本后，只复用版本相同、内容哈希及记录校验通过的分片；`--force` 强制重新抓取。
同版本 ID 清单也可用于续传起点，结束时仍强制在线核对全量 ID 与计数；
GET 临时失败时尝试等价 POST JSON 请求。
服务临时错误采用有限重试，筛选条件保持不变；任何完整性校验失败仍停止合并，
不回退到不同或未知版本的旧缓存。指标是否展示、参与计算或仅供下载须按当前
调用方分别核对，不能用整表读取代替使用情况判断。

`--source wdi_gcc` 从世界银行 WDI（source=2）抓取海合会六国的现价美元 GDP、
不变价 GDP 增速及农业林渔/工业（含建筑）/服务业增加值占 GDP 比重，保留原始
国家、指标、年份、缺失值、来源 URL 和修订日期到 `wdi_gcc_annual`。
报告按年对六国简单平均（含阿联酋），不足六国就留空，不进行变样本平均、加权或插值。
先入 DuckDB，再写四张 `年度_` 对比表、指标字典及完整发布版本。
GDP 图以十亿美元为左轴、实际增速百分比为右轴；产业占比为相邻柱形对比。
图表下载保留六国输入和均值，不把现价增速混作实际增速，也不把三产业占比强制归一为100%。

`--source fcsc_annual` 下载 FCSC 的年度行业资本形成、现价支出法资本形成、
外资类型、外资行业和来源国×行业六张官方表。原始观测及维度、单位、来源 URL
写入 `fcsc_investment_annual`，再经 DuckDB 同步五张 `年度_` 工作表、指标字典及
报告发布表。页面只读发布快照，不在线下载。FCSC 国家标签归档在
`fcsc_country_labels.json`（官方 `CL_COUNTRY` 1.3.0）。
2026-10-25 核验：资本形成年度表覆盖2010—2025年，外资细分历史表覆盖2007—2016年。
资本形成总额不改称固定资产投资；缺失值不补零，也不将外资历史表直接当作新增流量。

宏观概览与行业分析的季度数据使用 `--source fcsc_gdp,eia_liquids`：
`source_fcsc_gdp.py` 从 FCSC UAE.Stat 的 `DF_QGDP_CON` / `DF_QGDP_CUR`
接入 GDP、非油 GDP、16 个行业增加值及实际 GDP/非油 GDP 官方同比，共 38 项。
金额由百万 AED 转为工作簿标注的十亿 AED，保留官方历史修订值；同比自官方
开始发布的 2013Q1 起保留，不补造首年的同比。现价与不变价独立保留发布季度。
`source_eia_liquids.py` 使用 EIA International 的 UAE / product 53 / production，
将月度石油及其他液体日产量按每月日数加权为完整季度均值（百万桶/天），
保留原定义，不以 OPEC 原油产量替代，不发布缺月季度。
两项任务均先入 DuckDB，再只更新 `季度_Wind` 的对应列、同步指标字典并发布
完整报告快照；工作簿其他列不变。2026-10-18 核验：不变价及 EIA 季度数据至
2026Q2，现价至 2026Q1；需要两种价格的量价图只使用共同有效季度。

阿联酋监测页面默认只读 `htfa/monitoring/uae/assets/uae.duckdb`，本地与 Streamlit Cloud 均无需上传
工作簿。统一合并在全部来源和指标字典成功后，由 `publish_report.py` 将完整工作簿
按原列位置和日期发布到 `report.sheets`、`report.periods`、`report.observations` 长表，
`report.release` 记录内容版本和 UTC 发布时间。首次发布同时补入仅存于工作簿的
宏观历史数据；0、缺失值、重复名称但不同口径的列均保留。任一校验或写入失败，
旧发布版本不变并返回失败，禁止把部分更新发布到在线报告。

在线读取器不打开或生成 Excel，不运行 Windows COM，不抓取原始来源；只读取 LFS
部署后的数据库文件。缓存按完整发布版本区分，缺库、LFS 指针、未发布版本均明确报错，
不自动回退到旧 Excel 或上传文件。部署绑定 `main`；每次更新后正常推送数据库 LFS
对象与源文件。Excel 仍保留为本地维护和导出产物，其他模块的上传功能不受影响。

`--source public_market` 自动下载 DFM、CBUAE 和纽约联储的公开数据，更新 DFM
综合指数、FTSE ADX 综合指数、EIBOR 隔夜/1 年、EFFR、人民币兑迪拉姆六条日度序列，先写入
`public_market_daily` 再合并 Excel。`日度_Wind` 表名保留兼容，匹配列的来源和频率
元数据同步改成公开源。报告使用的覆盖前历史数据保留。覆盖区间内
无官方观测的交易休息日留空，不延续历史零值填充。

ADX 使用交易所官网 FADGI 五年历史接口。同日同值记录去重，同日不同收盘值
保留日期但数值写 NULL，不任取一个值。报告中的 DFM、ADX 和人民币兑迪拉姆
均按有效日度观测计算已结束月份的算术平均，下载数据与图表一致。

Salik 投资者 PDF 使用固定的 Chrome 请求方式；抓取失败直接
报错。Salik 同时读取财报及投资者演示目录，支持 Q/H/FY/9M 文件名并补抓历史
缺季。UAEWPS、邮政和 Eurostat 航空已停止采集，相关模块及工作表已删除。

尼泊尔同时识别原“劳工审批详情”标题和新“月度进展报告”标题；后者从该卡片
的发布日期读取尼历年份。实际统计区间仍以 PDF 的起止日期为准，不能将
尼历月份直接解释成公历自然月。

DED 发证月份超过当前月份的记录保留在原始快照及
`htfa/monitoring/uae/assets/raw/ded/DED_data/future_issue_dates.json` 审计件中，不进入月度指标。
不猜测或修正源站日期。DOT 在线 update 已强制重抓最近三年年包；是否能到
最新自然月取决于 BTS 的 T-100 International Segment 公布进度。

公开替代源的覆盖和限制见 [public-source-coverage.md](public-source-coverage.md)。

更新命令会尝试运行所有请求来源并报告各自状态。只要任一来源或元数据更新失败，就以异常和非零退出码结束、跳过工作簿合并，避免将旧库数据误写成刚抓取的数据。`merge_workbook` 保留为单独修复或重建工作簿的入口。

WAM 会保存本次完整的英文月度 sitemap 扫描证据；缺少所需月份时拒绝补零。新闻正文由 JavaScript 生成时用本机 Chrome/Edge 渲染，可用 `WAM_CHROME_PATH` 指定浏览器。第三方历史引文的归档错误写入 manifest 和运行日志；官方 WAM 抓取或解析失败仍终止更新。

CBUAE 从官网统计列表动态获取 ContentId，再调用官网 MediaListing 接口发现最新公报，优先下载 Excel。OPEC 从官网当前月报与历史月报自动发现并下载。两个来源固定使用 `curl_cffi` 的 Chrome 请求方式；不先发普通请求，也不在失败后切换请求方式。手工报告链接、CBUAE 公报链接、OPEC 表格捕获入口已删除。下载失败直接报错，保留原始数据与数据库；CBUAE 下载文件核对实际观察月份后才替换 raw 文件。运行时依赖已列入 requirements 和版本锁。

EIA Brent 同时读取官方 XLS 和 RBRTE daily API 完整分页，校验系列、单位、唯一日期和总行数。API 补足 XLS 未提供的日期；两个出口同日值有差异时保留项目原 XLS 口径，并在运行日志中报告数量。两个出口均缺少库内既有日期时拒绝删行更新。默认使用 EIA 公共 `DEMO_KEY`，频繁更新可在进程环境中设置 `HTFA_EIA_API_KEY`；密钥不写入 raw 或运行日志。

## 文件

- `update_data.py` / `update_data.bat`：更新总控（全部源或按 `--source`）；
- `merge_workbook.py` / `merge_workbook.bat`：合并总控（写回工作簿各 sheet）；
- `workbook_sheet_writer.py`：共享长表透视、元数据读取和原子写表；各来源自己的 `merge()` 独占对应工作表，不存在跨来源的 extended 合并阶段；
- `fetch_wam.py` / `source_wam.py`：从 WAM 官方 sitemap 自动发现公告、解析每日导弹/无人机数字；没有人工登记表时从 `2026-02-28` 引导，补齐至阿联酋昨日并先写 DuckDB，再由合并流程写入 `月度_WAM`；累计值和区间值不分摊到单日；
- `source_registry.py`：更新和合并共用的数据源清单与名称校验；
- `db.py`：共享 DuckDB 连接 / 建表 / 事务 / 运行日志；`_excel_helpers.py`：COM 写表基础设施；
- `_official_download.py`：显式下载传输及原子 JSON 写入；失败保留旧文件并清理临时文件；
- `source_*.py`：每源一个模块（download → parse → load → merge）；
- `write_indicator_sheet.ps1`：8 个来源共用的 Excel COM 宽表写入，载荷显式提供
  `number_format`、`column_width`、`period_format`（`month` / `day`），保留各源原有格式；
- `write_baker_hughes_sheet.ps1` / `write_cbuae_sheet.ps1` / `write_uae_pmi_sheet.ps1`：
  保留各自的字典更新、工作簿修复打开和校验回滚契约；
- `source_dld.py`：只计算两个周度项目计数和八个月度销售指标，通过共享写表器原子合并；租赁抓取及三个周度指数的计算已删除。
- `source_ded.py`：Data Dubai 快照聚合为记录数、发证企业数和新发执照数；官方新闻执照指标及其新闻扫描器已删除。
- `retired_indicators.json` / `retired_sources.py`：显式停用名单先写 DuckDB，再按指标名合并删除工作簿列及同步字典；名称匹配不依赖旧列号。

## ⚠️ 维护注意

- 本目录入 Git 跟踪；`processed/`、`backups/`、`__pycache__/` 为中间产物，不入 Git。
- `.bat` / `.ps1` 必须保持 **UTF-8 带 BOM**（PowerShell 按 GBK 读中文会乱码/删表失败）。
- `raw/<源>/download_*.py` 等既有本地工具随 raw 数据存放。
  BTS 本地更新使用 `download_t100.py` 获取官方最近三年数据，无需本地 raw 脚本；
  既有 T-100 Node 下载器存在时仍兼容调用。

来源模块仅供总控导入，不提供独立执行或内嵌自检入口；维护检查使用 `tests/`
中的来源测试。更新和合并各注册同一组 25 个来源，`--source salik` 等单来源
命令只写该来源的工作表。搜索热度直接从 DuckDB 写入工作簿，不再导出页面
已不使用的 `工作搜索热度.csv`；本地既有 CSV 不删除。汽车进口工作表仅由
专用来源写入乘用车、商用车两列台数，金额及零件明细仍保存在 DuckDB。

Comtrade 仅由 `source_comtrade.merge()` 写入工作表，使用共享原子写表 helper，
备份保存在 `htfa/monitoring/uae/assets/backups/`；不再导出中间 CSV，也不在 extended 合并中重复写表。

DED 仅由 `source_ded.merge()` 使用共享原子写表工具写入四个指标，保留写前备份；旧三指标写表器与 extended 中的重复写表入口已删除。

### 官方来源读取约定

- RTA 公交速度 CSV 先统一换行格式，保留全部字段和记录；水运固定使用官方 JSON 导出，逐条读取原文完整的 `txn_date` 字段计数。JSON 拼接分隔符不计为记录，每条记录缺日期、重复日期字段或日期无效均报错，不启用忽略错误行。
- RTA 在线运行保存各数据集的 `download_manifest.json`；显式离线模式只读取清单指定文件并核对大小，不访问元数据接口、不扫描混用历史版本。缺失清单或文件即报错。
- TDRA 旧解析器作为归档工具保留，不参加活动更新。
- Google Trends 使用同一 Chrome 请求会话获取查询令牌和时间线；429 有限退避重试，仍失败则报错，不自动转用缓存。
- 迪拜海关航空下载器为正式源码 `download_dubai_customs_air.py`：按当前完整清单下载，支持 HTTP Range 断点续传，校验响应长度及 gzip CRC 后原子替换。单次请求和重试次数有限，不再按整批累计 30 分钟强制终止；缺少任一分片即拒绝入库。
- 嵌入式运行时的 `python313._pth` 包含项目根目录，支持直接执行 `runtime\python.exe -m htfa.monitoring.uae.jobs.update_data`；运行时生成脚本同步维护此配置。
