# HTFA 数据概览 UI

这是 HTFA 内部复用的 Streamlit 数据概览 UI，负责把数据源、读取设置、变量选择、数据表和时间序列图组织成一个页面片段。它不是独立可复制的组件包，也不拥有普通表格解析规则。

## 所有权边界

- `htfa/data/tabular/`：纯 pandas 的普通表格读取、原始行解析、数据集契约和数值变量识别，不依赖 Streamlit。
- `htfa/ui_shared/data_overview/`：共享 UI 编排、控件、表格/图表面板、绘图选项和数据源协议。
- `htfa/exploration/ui/shared_dataset_source.py`：探索页把全局共享文件适配到 `DataSource` 协议；探索页自己的零值处理仍由探索领域拥有。
- `htfa/models/`：模型页面只组合共享 UI 和自己的模型输入/状态，不反向成为共享模块的依赖。

依赖方向固定为：

```text
探索页 / 模型页
    └── htfa.ui_shared.data_overview
            └── htfa.data.tabular
```

文件内容指纹由 `htfa.data.file_content` 提供，因此经济工作簿不会依赖数据概览 UI。

## 使用

```python
from htfa.ui_shared.data_overview import create_data_overview

overview = create_data_overview(
    key_prefix="sarimax",
    state_namespace="model_analysis.sarimax",
    data_source=my_data_source,
    show_preview=False,
)
overview(st)
```

共享 UI 的公共入口仅包括 `DataOverview`、`DataOverviewConfig`、`create_data_overview`、`DataSource`、`BuiltinDataSource` 和控件键函数。解析与数据集对象必须从 `htfa.data.tabular` 导入，避免 UI 反向拥有数据能力。

## 验证

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\data\tabular tests\ui_shared\data_overview -q
```

`tests\data\tabular` 验证无 Streamlit 的纯数据边界；`tests\ui_shared\data_overview` 验证 UI 工厂、数据源、表格和绘图行为。
