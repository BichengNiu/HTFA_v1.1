# data_overview

可移植的「数据预览」Streamlit 组件包：**数据上传 → 读取设置 → 变量选择 → 数据表（筛选/统计量）→ 时间序列图（5-tab 图形高级选项）** 一体化的可复用组件。

## 特性

- **自包含**：零宿主项目内部依赖（只依赖 streamlit / pandas / matplotlib / 外部工具包 `Ts`），整个文件夹拷到任何项目即可用
- **多实例隔离**：`key_prefix`（widget 键）与 `state_namespace`（数据集缓存）双隔离，同一页面可挂多个实例互不冲突
- **数据源可注入**：默认内置上传器（csv/xlsx/xls + 工作表切换 + 指纹缓存）；也可注入自定义 `DataSource`（如宿主项目的共享数据集）
- **读取设置**：支持选择工作表、输入变量名行和数据开始行、选择时间列；行号从 1 开始，变量名行必须早于数据开始行；重复变量名自动追加 `__2`、`__3` 等后缀
- **绘图契约与 Ts 一致**：`build_chart_options` 输出与 `Ts.TsPlots.plot_series` 的全部折线预览参数一一对应（测试自动断言）；数据管线参数与柱线混合参数暂不作为高级选项
- **Ts 参数分组**：画布、标题、坐标轴、线条样式、图例与图注五个 tab 分别承载分面、标题间距、自动多纵轴、序列颜色、自定义图例、参考线宽度等设置

## 环境依赖

- streamlit、pandas、matplotlib、plotly
- **Ts 包**（绘图底层）：`C:\Users\NIU\Desktop\Ts`，需在 sys.path 或已安装

## 导入

```python
from data_overview import (
    create_data_overview,      # 工厂：返回渲染函数
    DataOverview,              # 类式入口
    build_chart_options,       # 状态 → 绘图参数
    parse_vlines, parse_shade, # 参考线/阴影解析
    draw_series_plot,          # 绘图渲染收口
)
```

## 用法

```python
import streamlit as st
from data_overview import create_data_overview

# 默认实例：内置上传器，键前缀 sarimax
overview = create_data_overview()
overview(st)

# 自定义实例：隔离的键与状态命名空间
overview = create_data_overview(
    key_prefix="dfm",
    state_namespace="model_analysis.dfm",
)
overview(st)

# 注入外部数据源 + 换文件回调
overview = create_data_overview(
    key_prefix="sarimax",
    data_source=MySharedDatasetSource(),   # 实现 data_overview.DataSource
    on_dataset_replaced=clear_model_state, # 换文件时清理模型结果等
)
overview(st)
```

## 复用到宿主项目的接线

1. 把整个 `data_overview/` 文件夹拷到宿主项目根目录（或加入 sys.path）
2. `from data_overview import create_data_overview` 即可用
3. 多个 tab/模型：各自用不同的 `key_prefix` 与 `state_namespace`
4. 宿主项目特有的副作用（如模型结果清理）通过 `on_dataset_replaced` 回调注入

### 输入变量名行和数据开始行

例如文件前两行是说明文字、第三行是 `date,sales,exog`，第四行开始是数据，
在数据预览中输入“变量名行=3、数据开始行=4”，再选择 `date` 作为时间列后，变量名即为 `sales` 和 `exog`，`date` 会被解析为时间索引列。

## 测试

```bash
python -m pytest tests -q
```

## 目录结构

```
data_overview/
├── core/            # 纯逻辑（无 streamlit）：constants / parsing / options / dataset / compat
├── ui/              # Streamlit 组件：section（编排）/ 5-tab 控件 / 表与图面板 / 上传器 / 图例
└── tests/           # 自带测试
```
