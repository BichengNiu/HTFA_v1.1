# 能源保供原生整合

入口为“监测分析 → 能源保供”，与工业、阿联酋并列。四个页面直接调用本地 Python
模块；地图 HTML 在本地生成，只向地图服务请求底图，不嵌入线上 Streamlit 应用。

## 三层架构

`htfa/monitoring/energy_supply/` 采用进程内三层架构，依赖方向固定为
`ui → processing → data`。`contracts` 是共享的数据类型和来源字段定义，不执行 I/O。

| 层 | 职责与主要入口 |
| --- | --- |
| `data` | `storage` 管理连接、候选库上下文和原始事实；专用 repository 保存 AIS、海域事件及来源交付；client 管理网络请求、限流与分页校验 |
| `processing` | `dashboard_service` 组装页面快照，`reporting` 组装报告；港口、船舶、资产、海域及管线模块实现各自口径；`workbook_reporting` 生成月度指标 |
| `ui` | `renderer` 组合独立的地图、港口、船舶、油气和打印面板；`cache` 管理查询缓存，`charts` 复用 Ts 输出 PNG |

页面向计算服务传入 `DashboardQuery`，计算层返回 `DashboardContext` 和
`DashboardViewState`。页面不执行 SQL、写库或调用数据源客户端；计算层不加载
Streamlit、Matplotlib 或直接发送网络请求。维护作业继续由 `htfa/jobs/energy_supply/`
调度，不由页面触发。

资产构建通过 `processing.field_catalog.build_catalog()` 显式执行。`asset_spec` 保存
静态来源规范，审计材料在一次构建的 `evidence_scope` 中读取；构建函数返回全新记录，
不保存目录。维护作业随后调用 `processing.catalogs.save_catalog()` 完成业务补全和入库。
存储层本身不执行名称补全或港口分类规则，也不依赖维护作业包。

所有层导入时均不访问数据库或网络。Streamlit 查询缓存包含数据库路径、文件身份及
相关事实版本；船舶翻译、船旗和海域几何缓存同样按快照隔离。相同版本号的不同候选库
以及同路径替换的已发布快照不会共用过期结果。

旧的平铺模块已直接移除；新增调用方应从所属层导入，不提供旧路径兼容包装。
依赖方向、循环依赖和导入安全由 `tests/architecture/test_energy_supply_boundaries.py`
验证。目录构建、缓存隔离和跨层事务行为由 `test_layer_services.py` 验证。

## 数据与发布

所有事实保存在 `data/UAE/uae.duckdb` 的 `energy_supply` schema。
页面默认且只能只读连接，不初始化表、不下载源快照、不启动采集。
维护作业通过显式候选库上下文写入；线程池传递该上下文。

采集迁入 `htfa/jobs/energy_supply/`，由 `.github/workflows/energy-supply.yml`
每日迪拜时间09:00，与UAE高频来源统一执行（2026-11-10起）；旧08:00、13:00及
每小时补检已由本每日任务替换，详见 [daily-data-refresh.md](daily-data-refresh.md)。
原仓库的计划触发已移除，手动发布 job 也已禁用（`b79b695`），HTFA 是唯一计划采集端。
HTFA 保活与数据发布工作流共用 `htfa-main-writer` 并发组。

```powershell
# 只验证候选，不安装；自动跳过本窗口全部已成功的来源。
runtime\python.exe -m htfa.jobs.energy_supply.publish
# 收集、校验、更新本地数据库和 Excel。
runtime\python.exe -m htfa.jobs.energy_supply.publish --publish
# 仅从库内事实重建 Excel 与报告表，不向上游请求数据。
runtime\python.exe -m htfa.jobs.energy_supply.publish --prepare-only --publish
```

港口、通道、AIS 独立回滚并保留上次成功时间；全部失败不发布。
候选库验证后从 DuckDB 生成 Excel、指标字典及 HTFA 报告表，再安装成对文件。
工作流仅提交这两份数据文件，并验证远端 main。远端在采集中前进时丢弃本轮候选，
从最新版本重试，禁止合并数据库二进制或强制推送。

新增工作表为“月度_能源港口”“月度_能源通道”“月度_能源船舶”。PortWatch 指标为
已观测日期的月合计，不宣称完整月份；若已有日期内字段缺失，该月指标保留空值。
AIS 指标为分水域月内已观测 MMSI 去重数，不是海域全部通行量。
原始日记录、油气／管线目录及逐船档案保留在数据库；页面只保留迁入版本已有的
列表、图表及油气 CSV 下载，不新增历史数据下载入口。

## 验证

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\monitoring\energy_supply -q
runtime\python.exe scripts\check_energy_supply.py --url http://127.0.0.1:8511
```

浏览器检查覆盖原生地图、底图、图层、对象弹窗、地图 PNG、四页切换、油气 CSV、
原生打印以及返回阿联酋。截图和导出写入 `.cache/energy-browser/`，不提交。
升级 Streamlit 到 1.64.0 以统一原项目标签页接口及 HTFA 本地／云端版本；共享
Matplotlib 渲染改为先生成 PNG 再交给 Streamlit，保留图例与导出参数并避免弃用提示。

更改代码或 runtime 后须重启 `htfa.bat`，页面刷新不能清除 Python 模块缓存。
