# HTFA Streamlit Cloud 数据更新与保活

应用：https://fyjpjytbgdretgzufqnxte.streamlit.app/

调度由 `.github/workflows/streamlit-keepalive.yml` 管理，不依赖本地电脑、聊天窗口
或当前云任务的进程常驻。每天迪拜时间 04:17、10:17、16:17、22:17 运行，
即 UTC 00:17、06:17、12:17、18:17。GitHub 定时触发可能延迟，不构成可用性保证。

工作流保存到 main 时自动执行首次检查，也可从 GitHub Actions 的
**HTFA data refresh and keepalive → Run workflow** 手动运行；勾选
`force_refresh` 可重试当天已成功的数据库更新。空提交没有文件变更，
不匹配 push 路径过滤器，因此不会无限触发本工作流。

每个迪拜自然日首次运行先刷新 UAE 月度页使用的15个来源：Baker Hughes、石油、
CBUAE、DED、DLD、就业、外籍劳工、PMI、PortWatch、金融市场、钢铁、FCSC、
WAM、迪拜海关航空、BTS T-100。这些公开来源无需新增私密 API 密钥。
年度、季度来源不参与下载；同一来源中的日度序列随月度页一起更新。

更新在临时 DuckDB 中进行：从现有数据库恢复临时工作簿，抓取数据先入库，
再经库更新临时工作簿和完整报告发布表。所有来源和元数据必须成功，且已发布
历史观测不得丢失，才原子替换 `data/UAE/uae.duckdb`。跟踪的 Excel 不修改。
失败时保留原数据库，任务报告失败；同日下次运行会重试，不把旧值算作更新成功。
BTS 下载器已纳入源码，直接使用官方表单获取最近三年，保留库内更早历史。

随后按 AGENTS.md 清理、核对只有数据库发生修改，并在 main 推送
`data: refresh UAE monthly data YYYY-MM-DD` 和对应 LFS 对象。当天后续运行
检查该成功提交后跳过数据下载，只推送 `chore: Streamlit keep-alive` 空提交。
数据库内部的 `cloud_refresh_runs` 同步记录成功日期、来源和报告版本。
刷新期间远端有新提交则拒绝覆盖，留待下次重试；不强制推送。

浏览器打开公开应用，发现休眠按钮就点击；必须实际渲染“阿联酋经济监测”标题和
指标值，并保持15秒后仍正常，才报告 VERIFIED。仅 HTTP 200、前端壳、空白页、
休眠页、超时或应用报错均不算成功。应用为私有或要求登录时，任务会失败，不绕过认证。

数据更新或推送失败时仍尝试唤醒，但该次工作流保持失败。失败截图和更新结果 JSON 保存3天，
不保存 HTML、Cookie、浏览器存储或登录凭据。截图位于 GitHub Actions 本次运行的
Artifacts；运行日志和 Summary 会记录实际推送哈希及浏览器验证结果。

如果工作流未执行，检查 Actions 是否启用、定时任务是否被 GitHub 停用。如果推送
失败，检查 GITHUB_TOKEN 的 contents:write 权限和 main 分支保护；不要使用强制推送。
本配置只使用 Actions 内置令牌，不需要另行保存个人令牌。浏览器验证失败应查看
截图和 Streamlit 部署日志；数据或依赖故障需要修复应用，空提交不能代替修复。

每日一次表示成功运行频率，不表示官方每天发布新一期；源站公布滞后按原口径保留。
GitHub Actions 延迟、源站限制和 Streamlit 自身故障仍可能影响更新及访问。

本地检查数据流程（须先安装项目锁定依赖和 Ts）：

```bash
python scripts/cloud_refresh.py plan
python scripts/cloud_refresh.py run --validate-only
python scripts/cloud_refresh.py run --merge-only --validate-only
```

第二条在线下载但不替换正式数据库；第三条只验证现有入库数据的合并与历史保留，
不算在线刷新成功。正式应用由 Actions 执行不带验证参数的 `run`。

本地验证（系统已有 Chromium 时可用 --browser-executable 指定其路径）：

```bash
python -m pip install -r tooling/requirements/requirements-keepalive.txt
python -m playwright install chromium
python scripts/cloud_keepalive.py
```

本地检查需要正常的代理和 CA 信任；不要关闭 TLS 验证来绕过证书错误。
