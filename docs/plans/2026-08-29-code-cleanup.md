# 项目失效、冗余与旧兼容代码清理计划

## 目标

在不触碰用户已有工作区修改、运行时副本、数据文件和本地研究文件的前提下，删除 HTFA 项目中已证明无调用方的代码、重复实现、无效参数、旧会话状态迁移和旧模型字段回退；每一批修改后运行针对性测试，最后重复静态审计，直到没有新的可证明清理项。

当前基线：

- 分支为 `main`，不创建功能分支，不推送远端。
- 工作区已有修改：`AGENTS.md`、`docs/开发任务.txt`，以及未跟踪的 `docs/agents/`；这些不是本次清理目标。
- 完整测试基线：`505 passed, 25 warnings`。
- `compileall` 已通过。

## 已确认的清理项

### 1. 明确无调用方的公共/内部代码

- `htfa/ui_shared/data_overview/core/parsing.py`
  - 删除无调用方的 `parse_color_sequence` 及其 `__all__`、组件包重导出。
  - 同步删除仅由该函数使用的 `is_color_like` 和对应导入；保留 `COLOR_HEX_MAP`，因为 `options.py` 仍在使用。
- `dashboard/models/DFM/prep/utils/date_utils.py`
  - 删除无调用方的 `parse_date_range`、`filter_by_date_range` 及其导出。
  - 删除随之失效的 `Tuple` 导入。
- `dashboard/models/DFM/prep/utils/friday_utils.py`
  - 删除无调用方的 `get_friday_with_lag` 及三个仅供它使用的 `_get_friday_within_*` 私有函数和导出项。
  - 保留月/季/年/旬对齐及闰年同比日期处理。
- `dashboard/explore/core/data_source.py`
  - 删除只包装 `load_stationarity_data`、且没有生产调用方的 `load_stationarity_tables`。
  - 将现有数据源测试改为直接验证 `load_stationarity_data` 的返回值。
- `dashboard/models/SARIMAX/ui/state.py`
  - 删除无调用方的 `clear_dataset_state`、`get_fitted_result` 及 `Any` 导入和导出项。

### 2. 已确认的旧会话/控件兼容残留

- `dashboard/explore/ui/data_overview.py`、`dashboard/explore/ui/univariate_page.py`、`tests/explore/test_data_overview.py`
  - 删除把旧 `sarimax_*` 概览状态迁移到 `univariate_overview_*` 的函数、常量、调用和专门测试。
  - 保留当前页面自己的 handoff 保存/恢复逻辑。
- `dashboard/explore/ui/stationarity.py`
  - `_RESULT_STATE_KEYS` 只保留当前 `test_results`、`test_signature`；删除从旧批量工作流遗留的五个无生产写入状态键。
- `dashboard/models/SARIMAX/ui/pages/sections/training_section.py`、`dashboard/models/SARIMAX/ui/state.py`
  - 删除自动选阶范围从旧的 `*_min`/`*_max` 键恢复的逻辑。
  - 从 widget 状态注册表删除旧的自动选阶 `*_min`/`*_max` 键及无调用方的 `sarimax_auto_criterion`；保留当前 `*_range` 和 `sarimax_auto_selection_criterion`。
- `htfa/ui_shared/data_overview/ui/chart_options_tabs.py`
  - 删除旧图例外置锚点默认值、旧复选框状态的清理分支；当前输入控件只使用现行图例设置。

### 3. 明确冗余实现/参数和无效导入

- `dashboard/analysis/uae/transport/renderer.py`、`tests/analysis/uae/test_transport.py`
  - 删除没有缓存装饰器且只透传 `load_transport_data` 的 `_load_transport_cached`、无效的 `schema_version` 参数和版本常量；测试改为 monkeypatch 当前加载函数。
- `dashboard/core/ui/components/sidebar/renderer.py`
  - 合并对“数据探索”和“监测分析”执行完全相同操作的两个分支。
- `dashboard/models/DFM/train/utils/environment.py`
  - NumPy 是项目必需依赖，删除静默吞掉 `ImportError` 的可选依赖回退，改为直接导入并设置随机种子。
- 删除已核对的无效导入：
  - `htfa/data/tabular/dataset.py` 的 `Any`；
  - `htfa/ui_shared/data_overview/ui/chart_options_tabs.py` 的 `DEFAULT_LINESTYLES`；
  - `htfa/ui_shared/data_overview/ui/section.py` 的未使用 `OverviewDataset`；
  - UAE 多个 renderer/calculator/tabs 文件中未使用的 `streamlit as st`；
  - 已核对的测试文件中的未使用 `pytest`、`date` 和未使用展示常量导入。
- `dashboard/explore/metrics/dtw.py` 删除当前调用链未使用的 `window_size`、`use_window` 旧参数和参数适配分支，仅保留 UI 实际使用的 `radius`。
- DFM 导出不再写入已无消费者的 `training_means`、`training_variable_names` 元数据字段；均值只作为构建当前 `reconstruction_comparison` 的局部中间值。
- 合并 UAE 图表测试中完全相同的 `_data_lines` 辅助函数，放入 `tests/analysis/uae/_helpers.py`。
- 修复 DFM 空元数据校验在记录错误后再次执行 `in None` 的异常路径，并补充回归测试。

### 4. 测试辅助代码

在前述生产代码完成并通过测试后，再合并已确认函数体完全相同的测试辅助函数；只有在不改变测试语义、fixture 作用域和可读性的情况下执行，避免为了减少几行代码引入跨目录测试耦合。

## 需要按“删除旧兼容”原则处理的模型契约项

这些不是简单无调用方代码，但当前源码明确标注为旧模型兼容，需要在同一批中统一迁移，不能只删其中一半：

- `dashboard/models/DFM/train/export/exporter.py` 写出的 `best_variables`、`best_params` 是 `selected_variables`、`model_params` 的兼容别名；
- `dashboard/models/DFM/results/ui/pages/domain/metadata_accessor.py`、`dashboard/models/DFM/decomp/core/model_loader.py` 当前仍读取/优先读取上述旧字段，并且模型类型还会回退到顶层 `algorithm`；
- `dashboard/models/DFM/results/ui/pages/model_analysis_page.py` 在缺少 `reconstruction_comparison` 时执行“兼容旧模型”的动态重构。

处理方式：以当前 exporter 生成的 `selected_variables`、`model_params`、完整 `reconstruction_comparison` 为唯一契约，迁移 accessor、loader、验证器、页面和相关测试后删除别名、顶层算法回退和动态旧模型重构。旧序列化模型将明确要求重新训练，不再静默兼容。

## 明确保留项及原因

以下代码虽含有兼容/回退表述，但目前仍承担现行功能或产品契约，本轮不删除：

- 组件与 dashboard 各自保留 Matplotlib 告警抑制：组件必须可独立复制，不能引入 `dashboard` 依赖。
- UAE 外劳、DLD 房地产的两种正式工作簿元数据布局：属于当前输入数据契约，不是无调用方的旧 API。
- 交通/房地产“最新完整月”规则、工业贡献缺列时的可验证计算路径：属于业务数据边界。
- DTW 的 `radius`：当前 UI 仍提供并传入该参数。
- `future_dates` 无日期时的 `RangeIndex`、模型输入校验、显式 `ValueError`/`NotImplementedError`：属于运行时失败边界，不是回退兼容。
- 数据源迁移测试和旧数据库表清理：仍用于正式数据管线迁移验证。

## 实施顺序

1. 先按第 1、2、3 节修改并更新相关导出和测试。
2. 运行组件、Explore、SARIMAX、DFM 和 UAE 受影响测试。
3. 合并已确认的测试辅助重复项，并删除 DTW 旧参数及 DFM 无消费者元数据字段。
4. 统一迁移 DFM 当前模型元数据契约，删除旧字段回退和旧模型动态重构。
5. 重复 `rg`/AST 调用方扫描，检查死导出、旧键、兼容分支、无效导入和未引用模块。
6. 运行完整测试、编译检查、`git diff --check`，复核只包含本次正式源文件和测试修改；不提交、不推送。

## 验证命令

```powershell
runtime\python.exe -B -m pytest -c tooling\pytest.ini tests\exploration tests\models tests\analysis\uae tests\ui_shared\data_overview -q
runtime\python.exe -m pytest -c tooling\pytest.ini -q
runtime\python.exe -B -m compileall -q app.py htfa scripts tests
git diff --check
rg -n -i "legacy|fallback|回退|兼容旧|旧键|旧字段|旧模型|parse_color_sequence|parse_date_range|filter_by_date_range|get_friday_with_lag|load_stationarity_tables|clear_dataset_state|get_fitted_result|schema_version" htfa scripts tests
```

预期结果：目标符号不再有生产调用方；保留项的命中均有明确现行契约解释；完整测试不低于当前基线，且不产生新的异常。
