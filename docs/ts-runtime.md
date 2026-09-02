# HTFA 本地运行时

HTFA 使用项目根目录中的 `runtime/`，因此复制整个项目目录后，无需另外安装 Python。正常启动运行：

```powershell
scripts\start.bat
```

仅在 `runtime/` 缺失、损坏或依赖发生变化时重建：

```powershell
python scripts\htfa.py setup-runtime
```

重建脚本下载固定版本的 CPython 和依赖，校验下载文件，构建候选运行时，并在关键导入成功后替换现有 `runtime/`。替换失败会恢复旧运行时。

启动时会检查 `BichengNiu/Ts` 的 `main`。发现新提交时更新本地 Ts；断网、下载失败或替换失败时继续使用现有版本。该过程不依赖系统 Git。

如果项目目录本身是 Git 仓库，`scripts\start.bat` 会在上述 Ts 检查前尝试执行 `git pull --ff-only origin main` 更新 HTFA 源码。仅当当前分支是 `main` 且工作区干净时才会更新；Git 不可用、目录不是 Git 仓库、存在本地改动、无法快进或网络失败时会显示警告并继续使用当前 HTFA 源码，不会覆盖本地改动。

需要测试某项改动时，使用项目运行时只执行相关测试：

```powershell
runtime\python.exe -m pytest tests\相关测试文件.py -q -c tooling\pytest.ini
```

Docker 配置位于 `tooling/docker/`，使用同一份精确依赖锁文件。
