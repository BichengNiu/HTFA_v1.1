# 本地数据目录 —— UAE 统一数据管线

`data/` 下的阿联酋经济监测数据分为两个区管理：

- `data/UAE/`：**数据区** —— 数据库、工作簿、原始件、文档与自动运行配置；
- `htfa/jobs/uae_data/`：**作业区** —— 全部管线脚本（update/merge 总控、各源模块、
  Excel 写表助手）统一集中于此。

本目录内容（除脚本与说明文档外）只保存在本机，不推送到 GitHub。

## 统一数据管理（data/UAE/）

十五个阿联酋数据源（Baker Hughes、CBUAE、GFS、LSEG/PMI、UN Comtrade 资本品进口、
MEsteel 钢材价格、DED 执照、DLD 房地产、外籍劳工、工作搜索热度、Eurostat 航空
客货运、US DOT T-100 航空客货运、Emirates Post 国内邮政服务量、SCAD 酒店统计、
WAM军事打击与战争压力）
已整合进一个 DuckDB 数据库 `uae.duckdb` 统一管理：

- `uae.duckdb`：唯一数据库（本地文件，不入 Git）；
- `阿联酋.xlsx`：目标工作簿（HTFA 仪表盘读取；`工作搜索热度.csv` 也是其输入）；
- `数据说明.md`：**完整数据说明文档**（表结构、各源口径、更新与合并方法、自动运行
  配置、故障排查），使用前请先阅读；
- `raw/`：各源原始下载件与缓存（本地文件，不入 Git）；
- `auto_update_all.bat`：定时自动运行入口（更新 + 合并一步完成，供任务计划程序调用）；
- `.env`：数据源密钥（如 `COMTRADE_API_KEY`，不入 Git）。

## 作业区（htfa/jobs/uae_data/）

- `update_data.py` / `update_data.bat`：抓取 → 清洗 → 入库（一键更新全部或指定源）；
- `merge_workbook.py` / `merge_workbook.bat`：从库查询 → 合并进 `阿联酋.xlsx` 对应 sheet；
- `db.py`：共享 DuckDB 连接 / 建表 / 运行日志；
- `source_*.py`：每个数据源一个模块（下载器、解析清洗、入库、写表）；
- `write_*.ps1` / `merge_*.ps1`：Excel COM 写表助手（保留工作簿批注、链接等部件）；
- `fetch_official_news.py`：DED 官方数字半自动提取（人工确认后入库）。

> 说明：`raw/t100/*.mjs`（US DOT T-100 原始下载器）按源随 raw 数据存放，不随脚本
> 迁入 scripts/；`raw/<源>/download_*.py` 同理属于各源原始工具。

## 日常操作

```powershell
.\htfa\jobs\uae_data\update_data.bat        # 更新数据到 uae.duckdb（离线用 --skip-download）
.\htfa\jobs\uae_data\merge_workbook.bat     # 合并进 阿联酋.xlsx（务必先关闭 Excel）
```

也可用 `runtime\python.exe -m htfa.jobs.uae_data.update_data --source cbuae --skip-download`
只更新指定源或跳过网络下载；**如何定时自动运行见 `数据说明.md` 第 6 节**。

## 其他本地数据（data/ 根目录，与 UAE 管线无关）

- `工业/`：中国宏观与 DFM 预处理数据，不属于上述统一管线，保持原样；
- `users.db`：历史遗留文件，与数据管线无关。
