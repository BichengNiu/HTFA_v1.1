# Unified Tabular Input Parsing Implementation Plan

> **Archive:** 历史计划，仅保留迁移前路径记录；其中路径不可作为运行入口。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将组件和 dashboard 中重复的 CSV/Excel 读取、原始行解析、DataFrame 构建与文件指纹逻辑收敛为一个纯的 canonical parser，并删除所有旧实现与 `allow_unparsed` 兼容回退。

**Architecture:** 在 `htfa/data/tabular/file_parsing.py` 建立不依赖 Streamlit/session state 的深 module。它接收文件内容和明确的解析参数，负责文件格式读取、工作表枚举、原始行构建和表头/数值/时间解析；文件内容指纹位于 `htfa/data/file_content.py`，UI 与领域 adapter 只负责 session state、上传控件、状态清理和错误展示。迁移完成后，旧 helper、旧 loader、旧 wrapper 与 `allow_unparsed` 参数全部删除，不保留双路径。

**Tech Stack:** Python 3、pandas、openpyxl/xlrd、Streamlit、pytest。

---

### Task 1: Write the canonical parser contract tests

**Files:**
- Create: `tests/data/tabular/test_file_parsing.py`
- Reference: `htfa/ui_shared/data_overview/ui/data_source.py`
- Reference: `dashboard/core/ui/utils/shared_dataset.py`

**Step 1: Write the failing tests**

覆盖以下行为：

- 内容 SHA-256 指纹不包含文件名和大小；
- UTF-8、GBK、GB2312 CSV 读取；
- XLS/XLSX 工作表枚举与原始行读取；
- 指定变量名行、数据起始行和默认首列时间自动识别；
- 显式时间列、`None` 表示不解析时间列；
- 数值列推断、重复列名后缀和不规则行宽；
- 空表头、越界行、无数据、无效时间和不支持格式统一抛出解析错误。

**Step 2: Run tests to verify they fail**

Run from `D:\HTFA_v1.1`:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\data\tabular\test_file_parsing.py -p no:cacheprovider -q
```

Expected: FAIL because `htfa.data.tabular.file_parsing` does not exist yet.

### Task 2: Implement the pure parser

**Files:**
- Create: `htfa/data/tabular/file_parsing.py`
- Create: `CONTEXT.md`
- Modify: `htfa/data/tabular/__init__.py`

**Step 1: Implement the minimal canonical module**

集中实现内容指纹、Excel 工作表列表、原始行读取、带行号的 DataFrame 构建和文件内容加载。使用 module-private 自动时间标记；保留 `None` 的显式“不解析时间列”语义。可预期的读取/结构/时间错误统一为 parser 层解析错误，底层异常作为原因链保留。

**Step 2: Run parser tests**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\data\tabular\test_file_parsing.py -p no:cacheprovider -q
```

Expected: all new parser tests pass.

### Task 3: Migrate the component data source

**Files:**
- Modify: `htfa/ui_shared/data_overview/ui/data_source.py`
- Modify: `htfa/ui_shared/data_overview/ui/section.py`
- Modify: `tests/exploration/test_shared_dataset_source.py`

**Step 1: Replace local parsing calls with the canonical module**

删除组件内的重复 helper、`_load_dataframe` 和文件名参与的指纹逻辑；`BuiltinDataSource` 直接调用 canonical parser，并在读取失败时清理当前数据及下游组件数据，不再保留未解析数据回退。`DataOverview` 的 dataset fingerprint 明确包含工作表和读取参数，文件内容 fingerprint 只表示文件内容。

**Step 2: Update adapter tests**

测试 adapter 的 session state、上传、工作表切换和错误展示；纯解析行为改由 `test_file_parsing.py` 覆盖。旧 helper import 和旧 loader 测试全部改为 canonical parser 或 adapter 行为测试。

### Task 4: Migrate shared dashboard state and callers

**Files:**
- Modify: `dashboard/core/ui/utils/shared_dataset.py`
- Modify: `dashboard/explore/ui/shared_dataset_source.py`
- Modify: `dashboard/explore/ui/standalone_data_overview.py`
- Modify: `dashboard/core/ui/components/sidebar/renderer.py`
- Modify: `dashboard/preview/shared/renderer.py`
- Modify: `tests/exploration/test_shared_dataset.py`
- Modify: `tests/models/test_sarimax_modeling.py`

**Step 1: Use the canonical parser directly**

删除 shared dataset 中重复的读取、指纹、DataFrame 构建 helper 和 `load_shared_dataframe`；保留共享状态读写、快照、清理和 uploader。所有加载失败路径清空共享数据和依赖分析状态，且不再接受或传递 `allow_unparsed`。

**Step 2: Update all callers and tests**

把 Explore adapter、独立交接页、侧边栏、预览 renderer 与测试迁移到新的 canonical parser/明确 adapter 行为。旧函数名、旧参数和兼容性断言不得残留。

### Task 5: Validate the migration

**Files:**
- Inspect: all changed files and `git diff`

**Step 1: Run focused component and HTFA tests**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\data\tabular tests\ui_shared\data_overview -p no:cacheprovider -q
runtime\python.exe -m pytest -c tooling\pytest.ini tests\exploration tests\models tests\architecture -p no:cacheprovider -q
```

Expected: both commands pass; the second command should preserve the previously verified 208-test scope or report only justified test-count changes.

**Step 2: Run static residue checks**

```powershell
rg -n "allow_unparsed|load_shared_dataframe|_load_dataframe|def _read_raw_rows|def _build_dataframe_from_rows|def fingerprint_file|def list_excel_sheets" htfa tests -g "*.py"
```

Expected: no obsolete compatibility parameter/function or duplicate parser definition remains outside the canonical module.

**Step 3: Review the worktree**

```powershell
git status --short
git diff --check
git diff --stat
git diff -- htfa/data/tabular htfa/ui_shared/data_overview tests
```

Expected: only the approved parser migration, tests, and this plan are changed; existing unrelated worktree changes remain untouched; no cache/temp artifacts are staged or added.
