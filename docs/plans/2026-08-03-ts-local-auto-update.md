# Ts Local Auto-Update Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 Windows 本地启动 HTFA 时安全检查并激活 `Ts` 的最新 `main` 提交，同时保持已验证缓存和仓库内置版本的离线回退能力。

**Architecture:** 新增由 Python 标准库协调本机 Git 的更新器和同进程 Streamlit 启动器。更新器把候选版本下载到 `%LOCALAPPDATA%` 的版本化缓存，经过结构与子进程导入验证后才发布；启动器预加载所选 `Ts` 后调用 Streamlit CLI，仓库内 `Ts/` 永不被覆盖。

**Tech Stack:** Python 3.11+ 标准库、Git Credential Manager、Streamlit、pytest、Windows batch

---

### Task 1: Add machine-readable vendored metadata

**Files:**
- Create: `Ts/VENDORED.json`
- Modify: `tests/test_vendored_ts.py`

**Steps:**
1. 写入固定仓库、分支和内置 commit。
2. 增加测试，验证 JSON 与 `VENDORED.md` 的 commit 一致。
3. 运行 `python -m pytest tests/test_vendored_ts.py -q`，预期全部通过。

### Task 2: Implement version discovery, download, validation, and cache

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/ts_runtime.py`
- Test: `tests/test_ts_runtime.py`

**Steps:**
1. 为状态读取、原子写入、缓存版本发现和内置回退编写失败测试。
2. 实现 `RuntimeSelection`、`RuntimeState` 和缓存路径解析。
3. 为 GitHub HEAD 查询、Git 缺失、凭据失败和离线回退编写失败测试。
4. 使用非交互 Git 命令实现 3 秒 `ls-remote` 和 30 秒固定 commit 浅层获取；
   不调用 pip，也不把凭据写入命令、日志或状态。
5. 为 ZIP 路径穿越、缺失文件和运行时文件筛选编写失败测试。
6. 从已获取 commit 生成本地 ZIP，并使用 `zipfile` 只提取允许的运行时
   `.py` 文件。
7. 为独立子进程导入检查、候选发布和最近两个版本保留编写失败测试。
8. 实现验证、同文件系统原子发布、状态记录和成功后缓存清理。
9. 运行 `python -m pytest tests/test_ts_runtime.py -q`，预期全部通过。

### Task 3: Implement activation and the Streamlit launcher

**Files:**
- Create: `scripts/run_htfa.py`
- Modify: `start.bat`
- Test: `tests/test_ts_launcher.py`

**Steps:**
1. 为优先加载缓存版本和导入失败回退内置版本编写失败测试。
2. 实现 `activate_ts_runtime()`：把目标根目录放到 `sys.path` 首位、清理部分
   `Ts` 导入、预加载并验证真实导入路径。
3. 实现启动器：执行更新一次、打印简明状态、预加载 `Ts`、在同一进程调用
   `streamlit.web.cli.main()`。
4. 把 `start.bat` 的 Streamlit 命令替换为 `py scripts\run_htfa.py`，保留端口参数。
5. 运行 `python -m pytest tests/test_ts_launcher.py -q`，预期全部通过。

### Task 4: Verify online, offline, and regression behavior

**Files:**
- Verify only; do not modify UAE modules or Excel files.

**Steps:**
1. 运行 `python -m pytest tests/test_vendored_ts.py tests/test_ts_runtime.py tests/test_ts_launcher.py -q`。
2. 运行 Ts 相关 Explore 回归测试，预期全部通过。
3. 运行 `python -m compileall app.py dashboard Ts scripts`。
4. 使用临时缓存和模拟网络运行离线/在线集成检查。
5. 对真实 GitHub 执行一次只读 HEAD 检查和候选版本验证；不得修改内置 `Ts/`。
6. 运行 `git diff --check` 并确认 UAE 文件不在本功能差异中。
