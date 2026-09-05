# 普通表格能力与数据概览 UI 内部化拆分

**Status:** accepted

## Context

原 `components/data_overview` 同时包含普通表格文件解析、数据集契约、图表选项、Streamlit 控件和页面编排。生产代码通过 `components.data_overview` 导入，测试又通过路径注入以顶层 `data_overview` 导入；同一文件因此可以形成两个 Python 模块身份。该目录没有独立发布或安装生命周期，却被描述为可移植组件，所有权和依赖方向不清晰。

## Decision

直接切换为两个 HTFA 内部边界：

- `htfa.data.tabular` 拥有普通表格文件读取、原始行解析、数据集契约和数值变量识别；它只依赖 pandas 等数据处理库，不依赖 Streamlit。
- `htfa.ui_shared.data_overview` 拥有共享数据概览 UI、控件键、表格/图表面板、绘图选项和 `DataSource` 协议；它依赖 `htfa.data.tabular`。
- 文件内容指纹位于 `htfa.data.file_content`，供普通表格和经济工作簿共同使用。
- 探索页的 `SharedDatasetSource`、零值处理和状态清理留在探索领域；模型页面只组合这些入口，不成为共享模块的依赖。

依赖方向为：

```text
探索页 / 模型页
    -> htfa.ui_shared.data_overview
    -> htfa.data.tabular
```

旧 `components/`、顶层 `data_overview`、路径注入、alias、wrapper、双路径和运行时 fallback 全部删除，不保留兼容入口。

## Consequences

- 普通表格能力可以从 UI 冷启动和单独测试，数据域不再被共享 UI 反向污染。
- UI 复用仍保留，但复用对象明确是 HTFA 内部 UI 模块，而不是伪装成可复制的外部包。
- 任何未来真正需要跨项目发布时，必须另行建立明确的包元数据、版本和发布决策；当前不提前承担外部包维护成本。
- 迁移测试必须同时验证旧入口不存在、生产导入唯一，以及纯数据入口不加载 Streamlit。
