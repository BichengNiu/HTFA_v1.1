# UAE 与能源保供每日云端更新

从2026-11-10起，统一使用既有 `.github/workflows/energy-supply.yml`，计划为
UTC 05:00，即 **Asia/Dubai 每日09:00**。GitHub 调度可能排队或延迟；不依赖用户电脑
在线，不创建第二个 Codex 数据采集任务。保活工作流保持独立，沿用同一个
`htfa-main-writer` 并发组，不取消正在运行的发布。

## 范围与入口

`python -m htfa.jobs.uae_data.daily_refresh --results-dir <日志目录>`

每日依次尝试19个日／周／月度来源：baker_hughes、oil、cbuae、cloudflare_radar、
comtrade、comtrade_vehicles、ded、dld、dot_t100、dubai_customs_air、emsteel、employment、
fcsc、foreign_labour、pmi、portwatch、public_market、rta、wam。
季度／年度来源维持原维护入口，不纳入每日抓取。

随后通过原 `htfa.jobs.energy_supply.publish` 真实采集港口、咽喉点和 AIS，
而不是仅调用 `source_energy_supply` 重算旧事实。港口与通道保留原历史完整性验证；
AIS保留完整交付及最近120分钟新鲜度验证。每日快照不代表连续船位覆盖，
更新任务的运行时间不替代来源实际观测日期。

## Linux 写表与失败保护

Windows 保留原 Excel COM 写表。Linux 使用 `portable_sheet_writer.py` 消费相同的
四种源 payload，用 openpyxl 原子写入对应工作表，保留其他表、零、缺失值、
指标单位及原工作表次序；月度日期仍转换为月末，日度日期保持原日。
WAM 的本地历史 CSV 缺失时，从已发布 DuckDB 读取并校验连续日期、武器数、
强度公式与事件来源链接，再在线采集后续日期；不会从空历史补造旧事件。

整个作业持有数据库发布锁。每个源使用候选库／Excel 和独立进程，先更新 DuckDB，
再从 DuckDB 合并对应工作表。失败或超时恢复该源开始前的完整候选对，
删除被终止进程留下的候选 WAL；其他成功来源继续。原始件只作为不入 Git 的缓存。

CBUAE 和外籍劳工的本次观测按主键合并，不再以短缓存整表替换历史；
新响应未覆盖的旧键保留，新响应缺值也不会抹去旧有效值及其来源。
外籍劳工的菲律宾 YTD 必须有紧邻上月才可差分；缺月时失败并保留原快照，
不能把跨月差额当成单月值。

每个来源成功返回后还要与其检查点核对全部时间序列主键及历史有效值，
包括能源 AIS、港口日事实和海域事件。即使总行数不变，只要旧键消失或数值被清空，
仍会恢复该来源检查点。日志、缓存与指标字典不属于历史事实。

最终统一同步指标字典并执行原报告协议校验与发布，再核验能源历史未减少、
来源末期未倒退，才安装两份文件。最终校验失败时生产文件不变。
最终再按工作表名、指标名（含重名出现次数）及日期核对报告历史，允许列位置改变，
但拒绝历史非空观测消失。独立能源发布入口也执行同一历史校验。
作业可发布通过验证的部分来源，但工作流会以失败状态明确提示未成功的来源，
不把部分成功描述为完整更新。全部失败时不发布。

工作流只提交数据库及工作簿，正常推送 main，不强推或合并二进制。采集期间 main
变化时放弃该候选并从最新 main 重新尝试，最多两次。推送后核对远端 main，
并从 GitHub 下载精确提交的 LFS 对象，核对大小和 SHA256。

## 凭据与日志

GitHub Actions 从 Repository Secrets 读取 `CF_RADAR_TOKEN`、`COMTRADE_API_KEY`、
可选 `HTFA_EIA_API_KEY`。凭据缺失、权限不足、源站拦截或响应不完整均按来源失败
记录，不使用旧缓存冒充在线采集。不要将 `.env` 或密钥提交到仓库。
原始缓存恢复后仍执行各采集器的源版本、哈希及完整性检查。

每次运行在 Actions 摘要列出来源结果，详细 JSON／日志保留14天 artifact。
用户电脑关机不影响 GitHub 云端运行；平台额度、调度和源站可用性仍以实际运行记录为准。
