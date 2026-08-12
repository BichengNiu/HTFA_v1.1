# HTFA 单一 Python 运行时设计

**状态：** 已批准

**日期：** 2026-08-11

**取代：** `2026-08-11-portable-python-runtime-design.md` 中开发 `.venv` 与发布
`runtime` 分离的设计

## 目标

HTFA 的开发、测试、本地启动和 Windows 发布统一使用项目根目录的
`runtime/python.exe` 及 `runtime/Lib/site-packages`。项目不再创建、维护或调用
`.venv`。`pip` 和 `pytest` 作为正式锁定依赖保留在 `runtime` 中并随发布包交付。

Docker 使用相同的 Python 3.13.4 基线和相同的精确依赖版本；平台相关的二进制
文件仍由各平台分别安装，不能共享物理文件。

## 非目标

- 不把 `runtime/` 或下载缓存提交到 Git。
- 不在 `start.bat` 启动过程中静默安装或升级普通依赖。
- 不改变现有 Ts 启动时 HTTPS 更新策略。
- 不引入 Conda、Poetry、uv 或系统 Git。

## 唯一环境

项目只有一个 Python 环境：

```text
runtime/
├─ python.exe
├─ python313._pth
├─ runtime-manifest.json
└─ Lib/site-packages/
   ├─ 应用依赖
   ├─ pip
   ├─ pytest
   └─ Ts
```

开发、测试、启动和发布命令均调用 `runtime/python.exe`：

```powershell
runtime\python.exe -m pip check
runtime\python.exe -m pytest -q
runtime\python.exe -m compileall app.py dashboard scripts
runtime\python.exe scripts\run_htfa.py
```

`requirements.txt` 继续表达人工维护的支持范围。唯一精确锁文件表达实际安装
版本；Windows runtime、开发测试和 Docker 都从该锁文件安装，不允许从
`requirements.txt` 直接解析一个新的环境。

## 引导与重建

首次创建和后续重建由根目录批处理入口调用 PowerShell 引导器，不要求系统
Python：

1. 将下载内容写入项目内固定的 `build/portable/`。
2. 下载官方 CPython 3.13.4 Windows x64 嵌入式 ZIP并校验固定 SHA-256。
3. 在 `build/runtime-candidate/` 解压并写入 `python313._pth`。
4. 下载官方 PyPA pip 引导产物并校验固定 SHA-256。
5. 使用候选 `python.exe` 按唯一锁文件安装全部依赖，包括固定版本的 pip 和
   pytest。
6. 将固定 Ts 基线安装到候选 `Lib/site-packages`。
7. 使用候选解释器完成导入检查、`pip check`、pytest 自检和项目测试。
8. 所有验证通过后，PowerShell 才替换根目录 `runtime/`。

候选解释器完成工作并退出后才允许替换目录。不得让当前
`runtime/python.exe` 删除或覆盖自身，因为 Windows 会锁定正在执行的程序。

## 安全替换与失败处理

引导器只允许操作以下已解析且验证位于项目根目录内的生成目录：

- `build/portable/`
- `build/runtime-candidate/`
- `build/runtime-backup/`
- `runtime/`

替换顺序为：候选验证通过、当前 runtime 改名为备份、候选改名为 runtime、
新 runtime 启动验证、删除备份。如果任一改名或最终验证失败，恢复备份并返回
非零退出码。下载失败、哈希不符、锁文件安装失败或测试失败都不得改变当前
runtime。

`start.bat` 只负责检查和启动已有 runtime。缺少 runtime 时明确提示运行引导
命令，不在普通启动路径中自动下载依赖。

## 组件调整

- 新增根目录运行时初始化入口及 PowerShell 引导脚本。
- 重构 `scripts/build_portable.py`，使其构建候选环境而不是依赖 `.venv` 直接
  覆盖活动 runtime。
- 扩展运行时规格，固定 pip 引导产物的 URL 和 SHA-256。
- 将 pip、pytest 及其传递依赖加入唯一精确锁文件。
- 更新 `AGENTS.md`、`docs/ts-runtime.md`、数据更新说明和所有当前命令示例。
- 更新 Docker 到 Python 3.13.4，并从相同精确锁文件安装。
- 保留 `.gitignore` 和 `.dockerignore` 对 `.venv` 的防御性忽略，但项目不再
  创建或引用它。

## 测试与验收

自动化测试覆盖：

- 引导器拒绝项目目录外的删除或替换目标。
- Python 和 pip 引导产物哈希不符时保留旧 runtime。
- 安装、候选测试、改名和最终烟测任一失败时正确回滚。
- 锁文件包含 pip、pytest 且所有条目精确固定。
- 启动器和当前文档命令不调用 `.venv`、系统 Python 或系统 pip。
- Docker 与 Windows runtime 使用相同 Python 基线和精确依赖文件。

最终验证使用 `runtime/python.exe` 完成完整 pytest、compileall、pip check、Ts
导入及 Streamlit 启动烟测。全部通过后，最后删除且只删除项目根目录已确认的
`.venv/`；保留用户数据、日志、导出文件及其他无关改动。
