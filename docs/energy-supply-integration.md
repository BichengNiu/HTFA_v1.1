# 能源保供原生整合

入口为“监测分析 → 能源保供”，与工业、阿联酋并列。四个页面直接调用本地 Python
模块；地图 HTML 在本地生成，只向地图服务请求底图，不嵌入线上 Streamlit 应用。

## 数据与发布

所有事实保存在 `data/UAE/uae.duckdb` 的 `energy_supply` schema。
页面默认且只能只读连接，不初始化表、不下载源快照、不启动采集。
维护作业通过显式候选库上下文写入；线程池传递该上下文。

采集迁入 `htfa/jobs/energy_supply/`，由 `.github/workflows/energy-supply.yml`
每日迪拜时间 08:00、13:00 及每小时第 17 分检查本窗口未成功来源。
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
原始日记录、油气／管线目录及逐船档案保留在数据库和原有下载功能中。

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
