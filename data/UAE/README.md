# 本地数据目录 —— UAE 统一数据管线

`data/UAE/` 集中管理阿联酋经济监测所需的全部数据、workflow 脚本与文档；本目录内容
（除脚本与说明文档外）只保存在本机，不推送到 GitHub。

## 统一数据管理

十个阿联酋数据源（Baker Hughes、CBUAE、GFS、LSEG/PMI、UN Comtrade 资本品进口、
MEsteel 钢材价格、DED 执照、DLD 房地产、外籍劳工、工作搜索热度）已整合进一个
DuckDB 数据库 `uae.duckdb` 统一管理：

- `uae.duckdb`：唯一数据库（本地文件，不入 Git）；
- `数据说明.md`：**完整数据说明文档**（表结构、各源口径、更新与合并方法、自动运行
  配置、故障排查），使用前请先阅读；
- `raw/`：各源原始下载件与缓存（本地文件，不入 Git）；
- `update_data.py` / `update_data.bat`：抓取 → 清洗 → 入库（一键更新全部或指定源）；
- `merge_workbook.py` / `merge_workbook.bat`：从库查询 → 合并进 `阿联酋.xlsx` 对应 sheet；
- `source_*.py`：每个数据源一个模块（下载器、解析清洗、入库、写表）；
- `write_*.ps1` / `merge_*.ps1`：Excel COM 写表助手（保留工作簿批注、链接等部件）；
- `阿联酋.xlsx`：目标工作簿（HTFA 仪表盘读取；本目录下 `工作搜索热度.csv` 也是其输入）；
- `.env`：数据源密钥（如 `COMTRADE_API_KEY`，不入 Git）。

## 日常操作

```powershell
.\data\UAE\update_data.bat          # 更新数据到 uae.duckdb（离线用 --skip-download）
.\data\UAE\merge_workbook.bat       # 合并进 阿联酋.xlsx（务必先关闭 Excel）
```

也可用 `runtime\python.exe data\UAE\update_data.py --source cbuae --skip-download`
只更新指定源或跳过网络下载；**如何定时自动运行见 `数据说明.md` 第 7 节**。

## 其他本地数据（data/ 根目录，与 UAE 管线无关）

- `工业/`、`暂存/`：中国宏观与 DFM 预处理数据，不属于上述统一管线，保持原样；
- `sheet.txt`、`users.db`：历史遗留文件，与数据管线无关。
