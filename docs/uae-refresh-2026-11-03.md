# UAE 高频数据刷新核查：2026-11-03

本次先将本地 `main` 快进同步至 `db45716`，再运行高频模块的 26 个来源。
年度投资、WDI GCC、FCSC 季度 GDP 和 EIA 季度液体产量不在本次范围内。
25 个来源采集及入库成功；MESteel 新报价仍受新版站点的订阅权限限制。

本次发布更新 25 个成功来源的数据，保留 MESteel 原值及原观测期。
DuckDB 与 Excel 同步替换为已验证的版本。

正式工作簿和报告快照已完成核验：45 张表、637,991 条观测，内容版本
`d407f6d239a5905f7d799dc076b3b1257e74ff8729416ba649ebaf5645985300`。
与原发布版本比较，没有原有非空历史观测变为空值；MESteel 的 4,101 条观测
（含缺失值）与原版本完全一致。

| 访问问题 | 原因与证据 | 处理 |
|---|---|---|
| IMF PortWatch 的 HDX 镜像 | CSV 下载返回 HTTP 202、`x-amzn-waf-action: challenge`，即 AWS WAF 浏览器验证。响应不能进一步确定究竟由 IP、地区或其他规则触发 | 已改接发布者为 `IMF-portwatch_imf_dataviz`、访问级别为 `public` 的官方 ArcGIS 服务 |
| MESteel 月度钢材报价 | 旧 JSON 和图表 JSON 地址均 HTTP 301 跳转至 `/prices`。新版月度页明确要求 Silver、Gold 或 News + Prices 权限，匿名页面没有价格数据 | 保留原价格及原观测期；遇到 HTML 跳转时报告接口迁移，保护已有价格缓存 |

MESteel 旧接口确曾公开：本地 `source_manifest.json` 记录 2026-10-13 匿名下载成功，
覆盖 15 个产品、286 个月。[网站自己的价格脚本](https://mesteel.com/js/prices.js)
也说明旧页面使用无需认证的全历史 JSON，而新版由服务器鉴权后将价格内嵌到页面，
未获权限的页面没有数字。因此原因是接口迁移和服务器端权限收紧，无法仅靠更换解析器恢复匿名报价。
[当前月度报价页](https://mesteel.com/prices/monthly)列明了所需订阅权限；具体改版日期尚未核实。

PortWatch 直接源字段与原库一致，保持 15 个 UAE 港口和 28 个海峡的完整范围。
原始数据通过逐分区分页抓取、行数和唯一键校验；个别 API 请求返回瞬时查询错误，
增加有限重试。本次所有 43 个分区均取得有效快照，且与当前官方 `dataLastEditDate`
一致；验证同一版本后，显式复用本次新抓取的 CSV 完成入库和工作簿合并，没有使用旧库数据代替抓取。
港口共 42,795 行，覆盖至 2026-10-23；海峡共 79,940 行，覆盖至 2026-10-25。
两项均未覆盖完整 10 月，因此月度工作表按既有规则仍截止 2026-09。

本次修复：

- 海关下载改用有界 HTTP Range 请求。核对分段偏移、对象长度、响应长度和最终 gzip CRC；保留断点续传、原子替换及失败保护。
- DED 仅为官网实际出现的 `novemebr` 月份路径增加明确别名。仍要求月份与路径中的数字月份一致，日期无效继续失败。
- PMI 下载 S&P Global 最新官方 PDF，读取独立的参考月份。网页更新时间在次月时，必须同时由官方参考期验证，避免把发布日期当成观测期；样本与官方月份冲突仍失败。
- PortWatch 改接官方 ArcGIS，校验分页行数、唯一键、请求分区、源版本和历史键完整性后事务写库；13 个指标的来源元数据同步改为官方服务。

已核对的来源事实：

- 海关最新快照共 34 个分片、35,370,935 条原始记录，生成 1,120 条月度指标观测，覆盖 2019-08 至 2026-10；质量检查通过。
- [S&P 官方 2026-10-05 发布 PDF](https://www.pmi.spglobal.com/Public/Home/PressRelease/e9385c6415754eddaa87f166c487c1a4) 的参考期为 2026-09，PMI 为 55.3；本次图表样本的最新期及数值相符。
- CBUAE 官网发现的最新公报仍为 2026-08；没有人为补造后续月份。
- T-100 最近三年重新抓取后，当前数据仍至 2026-07。
- 房地产原始交易快照覆盖至 2026-10-30；该日期不代表所有月度房地产指标均已有完整 10 月观测。

验证命令：

```powershell
runtime/python.exe -B -m pytest -c tooling/pytest.ini tests/test_source_portwatch.py tests/test_source_steel.py tests/test_uae_detail_writes.py tests/jobs/test_uae_data_jobs.py tests/test_uae_database_report.py tests/test_uae_metadata.py -q
```

本次追加验证：88 passed；首轮提交的相关检查为 108 passed。
原始下载、运行日志、临时数据库及临时 Excel 不进入 Git。
