# HTFA Streamlit Cloud 保活

应用：https://fyjpjytbgdretgzufqnxte.streamlit.app/

调度由 `.github/workflows/streamlit-keepalive.yml` 管理，不依赖本地电脑、聊天窗口
或当前云任务的进程常驻。每天迪拜时间 04:17、10:17、16:17、22:17 运行，
即 UTC 00:17、06:17、12:17、18:17。GitHub 定时触发可能延迟，不构成可用性保证。

工作流保存到 main 时自动执行首次检查，也可从 GitHub Actions 的
**HTFA Streamlit keepalive → Run workflow** 手动运行。空提交没有文件变更，
不匹配 push 路径过滤器，因此不会无限触发本工作流。

每次运行先安装隔离的浏览器依赖（不安装 HTFA 或下载数据库），按 AGENTS.md
执行清理，然后在 main 创建并推送 `chore: Streamlit keep-alive` 空提交，核对远端。
浏览器打开公开应用，发现休眠按钮就点击；必须实际渲染“阿联酋经济监测”标题和
指标值，并保持15秒后仍正常，才报告 VERIFIED。仅 HTTP 200、前端壳、空白页、
休眠页、超时或应用报错均不算成功。应用为私有或要求登录时，任务会失败，不绕过认证。

空提交失败时仍尝试唤醒，但该次工作流保持失败。浏览器失败时保存3天的失败截图，
不保存 HTML、Cookie、浏览器存储或登录凭据。截图位于 GitHub Actions 本次运行的
Artifacts；运行日志和 Summary 会记录实际推送哈希及浏览器验证结果。

如果工作流未执行，检查 Actions 是否启用、定时任务是否被 GitHub 停用。如果推送
失败，检查 GITHUB_TOKEN 的 contents:write 权限和 main 分支保护；不要使用强制推送。
本配置只使用 Actions 内置令牌，不需要另行保存个人令牌。浏览器验证失败应查看
截图和 Streamlit 部署日志；数据或依赖故障需要修复应用，空提交不能代替修复。

本工作流只保活，不刷新数据库。数据更新继续由独立维护作业负责。

本地验证（系统已有 Chromium 时可用 --browser-executable 指定其路径）：

```bash
python -m pip install -r tooling/requirements/requirements-keepalive.txt
python -m playwright install chromium
python scripts/cloud_keepalive.py
```

本地检查需要正常的代理和 CA 信任；不要关闭 TLS 验证来绕过证书错误。
