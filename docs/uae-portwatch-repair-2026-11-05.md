# PortWatch 接口修复与更新核验：2026-11-05

## 问题与处理

IMF 官方 ArcGIS 服务间歇返回 HTTP 200 中的 `400 / Invalid URL` 等错误；
图层元数据、整表和部分筛选查询的可用性并不一致。按 offset 抓取时，仅看请求成功
或行数不足以证明没有重复、遗漏。较长的 objectIds GET 请求还会遇到 URL 长度限制。

本次保留 IMF 原始观测服务，调整客户端读取方式：

- 字段、图层和数据版本从官方 ArcGIS Hub 在线目录取得，校验公开权限、
  发布者 `IMF-portwatch_imf_dataviz`、项目 ID、图层 ID 和原始服务 URL。
  Hub JSON 接口不附加 FeatureServer 专用的 `f=json` 参数。
- UAE 港口先取得完整 object ID 清单，再用 POST 按 ID 分批读取，逐批核对精确 ID 集合。
  海峡先取得不加年份限制的全表 ID 清单，再按海峡和年份读取原始行；
  各年结果必须与全表 ID 清单完全一致。所有原始港口及海峡继续保留在 DuckDB。
- 查询不返回几何数据，海峡年度条件采用年份在前的等价写法；
  GET 临时失败时按官方支持的 POST JSON 请求重试，保持筛选条件及统计含义。
- 请求最多并发 8 个；临时服务错误采用有限重试，重试不改变筛选含义。
  认证错误直接失败，不当作临时服务错误循环重试。
- 只续用同一官方版本、哈希及范围校验通过的分区。年度分区成功后单独保存，
  某一分区失败仍允许其他分区完成保存，下一次只补缺口。`--force` 强制重新读取。
- 同一版本的 ID 清单也保存来源、版本和哈希，供续传起点使用；
  下载前后计数仍在线读取，下载结束仍强制在线取得完整 ID 清单逐项核对。
  清单版本不同、哈希错误或 ID 无效时重新在线读取，不使用该缓存。
- 入库前核对全局 ID 集合、前后计数、业务主键、港口目录和前后源版本，
  并拒绝删除历史主键。完整性失败时停止合并，不把旧缓存或局部结果当作新发布。
- 数据仍按“原始服务 → DuckDB → 月度汇总 → Excel → 报告发布库”的既有通道更新，
  指标字典随 merge 同步维护。

## 官方来源

- [IMF PortWatch](https://portwatch.imf.org/)
- [港口观测服务](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0)
- [海峡观测服务](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0)
- [港口官方目录](https://hub.arcgis.com/api/v3/datasets/83b1bbc7b3354c5fb1f40673bb8f852e_0)
- [海峡官方目录](https://hub.arcgis.com/api/v3/datasets/3da2b9ca97684916b75c4013f95d18ab_0)
- [Esri Query API 文档](https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/)：
  支持 GET/POST；完整 ID 清单可用于分批获取记录。

## 实际更新结果

标准命令 `runtime/python.exe -B -m htfa.jobs.uae_data.update_data --source portwatch`
已完整执行成功，更新、元数据及工作簿合并三个阶段均为成功。

| 数据 | 完整记录数 | 覆盖范围 | 与更新前备份比较 |
| --- | ---: | --- | --- |
| UAE 港口日度 | 42,900 | 15 港口，2019-01-01 至 2026-10-30 | 新增 105 条；15,819 条历史记录有官方修订；丢失主键 0 |
| 海峡日度 | 79,940 | 28 海峡，2019-01-01 至 2026-10-25 | 重新完整抓取后，新增及修订均为 0；丢失主键 0 |
| PortWatch 月度 | 93 个月 × 13 指标 | 2019-01 至 2026-09 | 557 个历史观测值随上游修订更新；无观测丢失 |

全部港口各有 2,860 天、全部海峡各有 2,855 天，均覆盖各自完整的每日日期区间。
10 月尚未覆盖整月，月度报告继续按港口与霍尔木兹共同完整月份截至 9 月，
不把部分 10 月加总冒充完整月。

港口本轮已完整下载的分片在最后运行时按在线官方版本及哈希复核复用；
海峡 224 个年度分区最终拼接后，再在线取得全量 ID 及计数核对通过。
两侧最终官方目录版本分别为 `1793743578056`（港口）和
`1793715201792`（海峡）。后续遇到上游临时错误仍可能中止，已保存的同版本分区
可继续补抓；客户端不会把一次成功探测或局部下载当作成功发布。

发布库为 43 张表、624,741 条观测；与更新前比较，只有 `月度_PortWatch`
的观测值发生变化，其余表无观测新增、删除或数值变化。
Excel SHA-256 与 `report.release` 版本完全一致：
`0df613cbd98a3343a3f51da3e667f1174850a8faf90d4bc6cecf7787ed1790a4`。

## 验证与指标覆盖

定向回归覆盖接口临时错误、认证错误、POST 请求、官方目录身份、ID 清单分页、
错港口、重复主键、计数/版本变化、哈希缓存、逐年续传、历史保护、合并流程和发布读取。

相关测试 98 项通过：`tests/test_source_portwatch.py`、
`tests/test_uae_detail_writes.py`、`tests/jobs/test_uae_data_jobs.py`、
`tests/test_uae_database_report.py`。
最终发布版本再次实际执行五个高频主题及年度图表，41 次图表输出，
各主题状态均为成功、无数据警告。648 列的覆盖核查结果仍为完全未引用 285 列、
仅年度下载 224 列、其余进入图表或计算等 139 列。

报告指标逐列核查另见[未引用指标完整清单](uae-unreported-indicators-2026-11-05.md)。
该清单区分完全未引用、仅年度下载和用于图表/计算的列；底库未发布的细分口径单列，
不与工作表列数重复相加。
