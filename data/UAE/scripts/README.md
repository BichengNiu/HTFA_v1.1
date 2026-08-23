# data/UAE/scripts —— UAE 数据管线脚本区

`data/UAE/` 数据管线的全部脚本统一集中在本目录；数据（`uae.duckdb`、
`阿联酋.xlsx`、`raw/`、`.env`）与定时自动运行入口 `data/UAE/auto_update_all.bat`
位于上一级 `data/UAE/`。脚本通过锚点 `SCRIPTS_DIR`（本目录）与 `DATA_DIR`（`SCRIPTS_DIR.parent`，
即 `data/UAE/`）定位，`import db` / `from source_* import ...` 均为同目录互引用。

## 入口

```powershell
runtime\python.exe data\UAE\scripts\update_data.py      # 抓取→清洗→入库
runtime\python.exe data\UAE\scripts\merge_workbook.py   # 库→阿联酋.xlsx
.\data\UAE\scripts\update_data.bat                      # 双击等价入口（同上）
.\data\UAE\scripts\merge_workbook.bat
```

常用参数：`--source cbuae,gfs`、`--skip-download`（只用 raw 缓存）、`--force`。

## 文件

- `update_data.py` / `update_data.bat`：更新总控（全部源或按 `--source`）；
- `merge_workbook.py` / `merge_workbook.bat`：合并总控（写回工作簿各 sheet）；
- `source_extended.py` / `workbook_sheet_writer.py`：从 DuckDB 重建此前未接入工作簿的 Eurostat、DOT、Dubai Customs、Salik、搜索热度、Comtrade 和 DED sheet；外籍劳动力由专用 `source_foreign_labour.py` 独占写回；
- `fetch_wam.py` / `source_wam.py`：归档 WAM 日度军事打击登记表引用的来源页，校验每日三类武器数量，计算战争压力指标并写入 `月度_WAM`；来源页清单失败逐条记录，不覆盖审核后的数值登记表；
- `db.py`：共享 DuckDB 连接 / 建表 / 运行日志；`_excel_helpers.py`：COM 写表基础设施；
- `source_*.py`：每源一个模块（download → parse → load → merge）；
- `write_*.ps1`：Excel COM 写表助手（baker_hughes/cbuae/emirates_post/portwatch/
  uaewps/pmi）；
- `merge_with_excel.ps1`（comtrade）、`merge_workbook.ps1`（steel）、
  `merge_dld_indices_into_uae_workbook.ps1`（dld）：旧写表通道脚本（py 通过
  `SCRIPTS_DIR` 定位，`processed/` 中间产物也落在本目录下）；
- `fetch_official_news.py`：DED 官方数字半自动提取。

## ⚠️ 维护注意

- 本目录入 Git 跟踪；`processed/`、`backups/`、`__pycache__/` 为中间产物，不入 Git。
- `.bat` / `.ps1` 必须保持 **UTF-8 带 BOM**（PowerShell 按 GBK 读中文会乱码/删表失败）。
- `raw/t100/*.mjs` 与 `raw/<源>/download_*.py` 属各源原始下载工具，随 raw 数据存放，
  不迁入本目录。
