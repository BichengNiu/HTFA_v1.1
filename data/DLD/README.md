# DLD 全量数据一键下载器

## 输出文件

1. `DLD_Transactions_ALL.csv`  
   Data Dubai 官方 bulk 数据中的全部房地产交易记录。
2. `DLD_Land_Transactions_ALL.csv`  
   从全部交易中筛选 `property_type_en = Land` 得到的土地交易记录。
3. `DLD_Land_Registry_ALL.csv`  
   DLD Land Registry（地块登记库，不等同于“土地成交”）。
4. `DLD_download_manifest.json`  
   实际记录数、日期范围、异常日期计数、快照时间、来源文件、文件大小和 SHA-256 校验值。

## 使用方法（Windows）

双击：

`run_download_dld_all.bat`

或在命令行运行：

```powershell
python -u download_dld_all.py
```

脚本只使用 Python 标准库，不需要安装 pandas 或 requests。下载过程中会临时保存官方 `.csv.gz` 分片，合并完成后自动清理；最终 CSV 体积超过 1 GB 属于正常现象。

## DuckDB 数据库

项目已包含官方便携版 DuckDB。生成或更新CSV后，双击：

`build_dld_database.bat`

生成：`DLD_data/DLD.duckdb`。数据库包含：

- `transactions`：强类型交易表；
- `land_registry`：强类型土地登记表；
- `land_transactions`：土地交易视图，不重复存储数据；
- `transaction_year_summary`：常用年度汇总视图；
- `metadata.column_dictionary`：全部79个物理字段的中文解释；
- `metadata.relationships`：跨表关系、可靠性和限制。

同时生成 `DLD_data/DLD_database_manifest.json`，记录数据库SHA-256、DuckDB版本、来源文件校验值和行数验证结果。

双击 `open_dld_database.bat` 可进入 DuckDB 命令行。图形化浏览可使用 DBeaver 的 DuckDB 连接直接打开 `DLD_data/DLD.duckdb`。

详细说明见 `数据库字段关系说明.md`，示例SQL见 `example_queries.sql`。

## 官方数据源

- [Data Dubai — Real Estate Transactions](https://data.dubai/en/l/470061?com_dda_data_and_statistics_ThemeId=62035)
- [Data Dubai — Land Registry](https://data.dubai/en/l/465348?com_dda_data_and_statistics_ThemeId=62035)
- [DLD — Real Estate Data](https://dubailand.gov.ae/en/open-data/real-estate-data/)

脚本从 Data Dubai 页面获取当前 CSRF token，再通过官方 dataset-download 接口取得短时有效的 bulk 文件地址。它只下载 CSV 分片，不下载重复的 JSON 格式。

## 为什么旧脚本没有 2025 年及以前数据

DLD 实时页面的官方 JavaScript 将交易日期控件限制为当年：

- `minDate` = 当年 1 月 1 日；
- `maxDate` = 当年 12 月 31 日。

因此 `/open-data/transactions` 是“本年度实时查询接口”，不是历史全量接口。旧脚本虽然从 1900 年开始探测，但接口返回的最早记录仍是当年 1 月 1 日，于是最终文件只有 2026 年数据。

旧 README 中的 Dubai Pulse CSV 地址也已失效，目前会重定向到 Data Dubai 首页。新版脚本改用新门户的官方 bulk 数据集，其中包含 2025 年及更早记录。

## 说明

- **Land Transactions**：土地的成交、抵押及其他交易记录。
- **Land Registry**：当前登记地块的属性资料。
- 输出 CSV 使用 UTF-8 with BOM，可由 Excel 识别；但交易主文件很大，建议使用 DuckDB、Polars 或分块读取。
- 下载采用 `.part` 临时文件，只有完整合并成功后才替换正式输出，避免把中断结果误当成完整数据。
- 官方 bulk 数据中的原始异常日期不会被静默删除；清单会同时记录原始最早日期、1900 年以来的最早日期及 1900 年以前的记录数。
