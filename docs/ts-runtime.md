# HTFA 本地运行时

HTFA 使用项目根目录中的 `runtime/`，因此复制整个项目目录后，无需另外安装 Python。正常启动运行：

```powershell
scripts\windows\start.bat
```

仅在 `runtime/` 缺失、损坏或依赖发生变化时重建：

```powershell
scripts\windows\setup_runtime.bat
```

重建脚本下载固定版本的 CPython 和依赖，校验下载文件，构建候选运行时，并在关键导入成功后替换现有 `runtime/`。替换失败会恢复旧运行时。

启动时会检查 `BichengNiu/Ts` 的 `main`。发现新提交时更新本地 Ts；断网、下载失败或替换失败时继续使用现有版本。该过程不依赖系统 Git。

需要测试某项改动时，使用项目运行时只执行相关测试：

```powershell
runtime\python.exe -m pytest tests\相关测试文件.py -q -c tooling\pytest.ini
```

Docker 配置位于 `tooling/docker/`，使用同一份精确依赖锁文件。
