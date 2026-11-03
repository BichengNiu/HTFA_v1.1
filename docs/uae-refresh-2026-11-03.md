# UAE 高频数据刷新核查：2026-11-03

本次先将本地 `main` 快进同步至 `db45716`，再运行高频模块的 26 个来源。
年度投资、WDI GCC、FCSC 季度 GDP 和 EIA 季度液体产量不在本次范围内。
24 个来源采集及入库成功；两个外部访问阻点尚未解除。

本次发布更新 24 个成功来源的数据，并保留 PortWatch、MESteel 两个失败来源的
原值及原观测期。DuckDB 与 Excel 同步替换为已验证的版本；两个未更新来源的
限制见下表。

正式工作簿和报告快照已完成核验：45 张表、637,991 条观测，内容版本
`d373dfe5c7343231e86d9d9d9fd008d73a180d274d5869467e89ee56a3293367`。
与原发布版本比较，没有原有非空历史观测变为空值；PortWatch 的 1,209 条
和 MESteel 的 4,101 条观测（含缺失值）与原版本完全一致。

| 未完成来源 | 实际响应 | 处理 |
|---|---|---|
| IMF PortWatch 的 HDX 镜像 | CSV 下载返回 HTTP 202、`x-amzn-waf-action: challenge`，没有有效 CSV；urllib 和 Chrome 传输均复现 | 不使用空响应或旧缓存冒充本次抓取成功 |
| MESteel 月度钢材报价 | 旧 JSON 地址重定向至新闻页面；新版 `/prices/monthly` 标记 `MESTEEL_LOCKED=true`、`MESTEEL_AUTHED=false`，未提供报价 | 保留原价格及原观测期，未绕过登录限制 |

本次修复：

- 海关下载改用有界 HTTP Range 请求。核对分段偏移、对象长度、响应长度和最终 gzip CRC；保留断点续传、原子替换及失败保护。
- DED 仅为官网实际出现的 `novemebr` 月份路径增加明确别名。仍要求月份与路径中的数字月份一致，日期无效继续失败。
- PMI 下载 S&P Global 最新官方 PDF，读取独立的参考月份。网页更新时间在次月时，必须同时由官方参考期验证，避免把发布日期当成观测期；样本与官方月份冲突仍失败。
- PortWatch 拒绝 HTTP 非 200、HTML、空响应和长度不完整的响应，在这些情况下保留原缓存。

已核对的来源事实：

- 海关最新快照共 34 个分片、35,370,935 条原始记录，生成 1,120 条月度指标观测，覆盖 2019-08 至 2026-10；质量检查通过。
- [S&P 官方 2026-10-05 发布 PDF](https://www.pmi.spglobal.com/Public/Home/PressRelease/e9385c6415754eddaa87f166c487c1a4) 的参考期为 2026-09，PMI 为 55.3；本次图表样本的最新期及数值相符。
- CBUAE 官网发现的最新公报仍为 2026-08；没有人为补造后续月份。
- T-100 最近三年重新抓取后，当前数据仍至 2026-07。
- 房地产原始交易快照覆盖至 2026-10-30；该日期不代表所有月度房地产指标均已有完整 10 月观测。

验证命令：

```powershell
runtime/python.exe -B -m pytest -c tooling/pytest.ini tests/jobs/test_uae_data_jobs.py tests/test_uae_database_report.py tests/test_dubai_customs_download.py tests/test_source_automated_downloads.py tests/test_source_pmi.py tests/test_source_portwatch.py tests/test_uae_source_repairs.py tests/test_source_ded.py -q
```

结果：108 passed。原始下载、运行日志、临时数据库及临时 Excel 不进入 Git。
