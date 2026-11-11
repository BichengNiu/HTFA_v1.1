# 本地数据目录 —— UAE 统一数据管线

UAE 模块的数据资产与维护作业分区管理：

- `htfa/monitoring/uae/assets/`：**数据区** —— 数据库、工作簿、原始件、文档与自动运行配置；
- `htfa/monitoring/uae/jobs/`：**作业区** —— 全部管线脚本（update/merge 总控、各源模块、
  Excel 写表助手）统一集中于此。

原始文件、缓存、备份、日志和凭据只保存在本机；正式脚本以及 `uae.duckdb`、`阿联酋.xlsx`
按仓库规则跟踪和管理。

## 统一数据管理（htfa/monitoring/uae/assets/）

阿联酋高频数据库的有效来源由 `source_registry.py` 统一管理；作业入口会抓取或读取有效缓存、写入
DuckDB，并自动同步到工作簿；完整来源清单与口径见 `数据说明.md`。

- `uae.duckdb`：唯一数据库（通过 Git LFS 跟踪）；
- `阿联酋.xlsx`：本地合并与导出工作簿；UAE 页面直接读取数据库中的完整报告发布版本；
- `数据说明.md`：**完整数据说明文档**（表结构、各源口径、更新与合并方法、故障排查），
  使用前请先阅读；
- `raw/`：各源原始下载件与缓存（本地文件，不入 Git）；
- `auto_update_all.bat`：手动在线更新入口（更新 + 合并一步完成，不创建或依赖定时任务）；
- `.env`：数据源密钥（如 `COMTRADE_API_KEY`，不入 Git）。

## 作业区（htfa/monitoring/uae/jobs/）

- `update_data.py` / `update_data.bat`：抓取 → 清洗 → 入库 → 按来源合并对应工作簿 sheet；
- `merge_workbook.py` / `merge_workbook.bat`：单独重建工作簿 sheet（用于修复或重跑合并）；
- `db.py`：共享 DuckDB 连接 / 建表 / 运行日志；
- `source_*.py`：每个数据源一个模块（下载器、解析清洗、入库、写表）；
- `write_*.ps1` / `merge_*.ps1`：Excel COM 写表助手（保留工作簿批注、链接等部件）；

> 说明：`raw/t100/*.mjs`（US DOT T-100 原始下载器）按源随 raw 数据存放，不随脚本
> 迁入 scripts/；`raw/<源>/download_*.py` 同理属于各源原始工具。

## 日常操作

```powershell
htfa\monitoring\uae\assets\auto_update_all.bat                 # 在线更新全部来源并合并（务必先关闭 Excel）
.\htfa\monitoring\uae\jobs\update_data.bat --source cbuae,gfs  # 更新指定来源并自动合并对应 sheet
```

也可用 `runtime\python.exe -m htfa.monitoring.uae.jobs.update_data --source cbuae --skip-download`
离线读取缓存并同步对应 sheet。`auto_update_all.bat` 只在用户运行时执行，不设置定时任务。

## 其他本地数据（data/ 根目录，与 UAE 管线无关）

- `工业/`：中国宏观与 DFM 预处理数据，不属于上述统一管线，保持原样；
- `users.db`：历史遗留文件，与数据管线无关。

## 在线报告数据

Streamlit 在线版和本地 UAE 页面自动只读 `uae.duckdb`，无需上传 Excel。
数据库通过 Git LFS 随 `main` 部署。`report` schema 保存完整报告的历史指标、
来源、单位和观测；统一更新/合并成功后自动原子发布，缓存随内容版本更新。
发布失败保留上一成功版本；缺库或 LFS 文件未拉取时明确报错，不回退到 Excel。
`阿联酋.xlsx` 继续保留为本地维护产物。

## 原始资料管理规则

原始资料按是否参与当前 UAE 统一更新链路管理。判定范围包括 `source_registry.py` 中的全部有效来源及其辅助脚本，也包括未纳入每日调度的手动季度、年度来源。

- 保留有效来源实际读取的原始输入、缓存、完整下载分片及清单。是否被页面直接展示，不作为删除依据。
- 不参与统一更新的停用来源、独立研究资料及旧诊断输出，按用户明确的清理指令移除；不因资料曾独立入库就继续保留。
- RTA、DLD、航空、贸易及各类公报的现用输入仍参与解析、离线重算或历史合并，不属于闲置文件。不得把仅保存聚合或字段子集的主库当作这些输入的完整替代品。
- 不把“未参与每日调度”误判为“未参与数据更新”；GFS、Salik、FCSC 年度与季度等手动来源继续保留。
- 清理前核对全部有效来源的路径及辅助依赖，使用明确目录名单；禁止按文件年龄或单次未命中引用直接批量删除。
- 数据库、工作簿、密钥及有效来源目录不在闲置资料清理范围内。清理后核对数据库／工作簿校验和、有效来源目录和输入完整性。
