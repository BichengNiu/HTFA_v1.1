# htfa/jobs/uae_data —— UAE 数据维护作业

本目录是 `htfa.jobs.uae_data` 包；数据资产（`uae.duckdb`、`阿联酋.xlsx`、
`raw/`、`.env`）仍位于 `data/UAE/`。所有路径由 `paths.py` 集中解析，作业模块
使用包内相对导入，不依赖运行时 `sys.path` 注入。

## 入口

```powershell
runtime\python.exe -m htfa.jobs.uae_data.update_data      # 抓取→清洗→入库→合并对应工作簿工作表
runtime\python.exe -m htfa.jobs.uae_data.merge_workbook   # 单独重跑库→阿联酋.xlsx 合并
.\htfa\jobs\uae_data\update_data.bat                    # 双击等价入口（同上）
.\htfa\jobs\uae_data\merge_workbook.bat
```

常用参数：`--source cbuae,gfs`、`--skip-download`（只用 raw 缓存）、`--force`。

更新命令会尝试运行所有请求来源并报告各自状态。只要任一来源或元数据更新失败，就以异常和非零退出码结束、跳过工作簿合并，避免将旧库数据误写成刚抓取的数据。`merge_workbook` 保留为单独修复或重建工作簿的入口。

## 文件

- `update_data.py` / `update_data.bat`：更新总控（全部源或按 `--source`）；
- `merge_workbook.py` / `merge_workbook.bat`：合并总控（写回工作簿各 sheet）；
- `source_extended.py` / `workbook_sheet_writer.py`：从 DuckDB 重建此前未接入工作簿的 Eurostat、DOT、Dubai Customs、Salik、搜索热度、Comtrade 和 DED sheet；外籍劳动力由专用 `source_foreign_labour.py` 独占写回；
- `fetch_wam.py` / `source_wam.py`：从 WAM 官方 sitemap 自动发现公告、解析每日导弹/无人机数字；没有人工登记表时从 `2026-02-28` 引导，补齐至阿联酋昨日并先写 DuckDB，再由合并流程写入 `月度_WAM`；累计值和区间值不分摊到单日；
- `db.py`：共享 DuckDB 连接 / 建表 / 运行日志；`_excel_helpers.py`：COM 写表基础设施；
- `source_*.py`：每源一个模块（download → parse → load → merge）；
- `write_*.ps1`：Excel COM 写表助手（baker_hughes/cbuae/emirates_post/portwatch/
  uaewps/pmi）；
- `merge_with_excel.ps1`（comtrade）、`merge_workbook.ps1`（steel）、
  `merge_dld_indices_into_uae_workbook.ps1`（dld）：各来源的写表通道脚本；
  `processed/` 中间产物仍落在 `data/UAE/processed/`；
- `fetch_official_news.py` / `source_ded.py`：从迪拜媒体办公室官方新闻接口扫描 2020 年以来的执照公告，将期间、数值、原文片段和来源 URL 写入 DuckDB 候选表；期间终点值无冲突时进入 `ded_monthly`，官方候选缺失或冲突时更新直接报错。

## ⚠️ 维护注意

- 本目录入 Git 跟踪；`processed/`、`backups/`、`__pycache__/` 为中间产物，不入 Git。
- `.bat` / `.ps1` 必须保持 **UTF-8 带 BOM**（PowerShell 按 GBK 读中文会乱码/删表失败）。
- `raw/t100/*.mjs` 与 `raw/<源>/download_*.py` 属各源原始下载工具，随 raw 数据存放，
  不迁入本目录。
