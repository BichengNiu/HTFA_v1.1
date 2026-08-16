# 模型分析 - 单变量时间序列（SARIMAX）模块设计说明

## 1. 模块定位

在「模型分析」主模块下新增 **单变量时间序列** 子模块，其下第一个 tab 为
**SARIMAX 模型**，提供基于 Ts 运行时（`Ts.TsModels` / `Ts.TsTests` /
`Ts.TsPlots`）的 ARIMA 家族建模工作流。该 tab 是一个**单页四环节工作流**，
各环节之间以分割线分隔，后续可在同一子模块下扩展其他单变量模型 tab：

1. **① 数据导入**：文件上传、数据预览、目标/外生变量选择；
2. **② 模型训练**：手动 SARIMAX（`(p,d,q)×(P,D,Q,s)`、趋势、外生变量、
   log 变换）或 AutoSARIMAX 自动选阶；
3. **③ 模型分析**：参数估计表、拟合效果图、残差诊断图、残差检验
   （Ljung-Box、Jarque-Bera、Engle LM）与稳定性结论；
4. **④ 模型预测**：样本外预测与置信区间、动态/静态预测、含外生变量时的
   未来值录入、CSV 下载。

所有统计计算均调用 Ts 包 API，不直接使用 statsmodels；Ts 包本身
（`runtime/Lib/site-packages/Ts`）由 ts_runtime 机制管理，本模块只消费其
公开接口，不修改包内容。

## 2. 目录结构

```
dashboard/models/SARIMAX/
├── __init__.py                  # 包入口，导出 render_sarimax_model_page
├── core/                        # 纯逻辑层（无 streamlit 依赖，可单测）
│   ├── __init__.py
│   ├── data_loader.py           # 上传文件解析、指纹、变量准备
│   ├── model_config.py          # SARIMAXConfig / AutoSARIMAXConfig 与校验
│   └── modeling.py              # 唯一调用 Ts 包的拟合/诊断/预测编排
└── ui/
    ├── __init__.py
    ├── state.py                 # 共享会话状态 NamespacedStateManager
    └── pages/
        ├── __init__.py          # 导出 render_sarimax_model_page
        ├── sarimax_page.py      # 主页面：四环节顺序渲染 + 分割线
        └── sections/            # 四环节组件
            ├── __init__.py
            ├── data_section.py      # ① 数据导入
            ├── training_section.py  # ② 模型训练
            ├── analysis_section.py  # ③ 模型分析
            └── forecast_section.py  # ④ 模型预测
```

## 3. 导航与权限

- `dashboard/navigation_config.py` 的 `GRANULAR_PERMISSION_MAP` 中注册：

  | 子模块 | 权限码 | Tabs |
  | --- | --- | --- |
  | 单变量时间序列 | `model_analysis.univariate_ts` | SARIMAX 模型 |

  Tab「SARIMAX 模型」的权限码为 `model_analysis.univariate_ts.sarimax`，
  由 `PermissionTreeBuilder` 自动生成显示名（如「模型分析 - 单变量时间序列 -
  SARIMAX 模型」），无需额外注册。
- `dashboard/core/ui/components/content_router.py` 的
  `render_model_analysis_content()` 分派「单变量时间序列」子模块；Tab 权限
  过滤逻辑由 `_filter_tabs_by_permission()` 与 `_render_model_submodule_tabs()`
  统一处理，DFM 与单变量时间序列共用。当前仅一个 tab，未来增加其他单变量
  模型 tab（如 GARCH）只需扩展导航配置。

## 4. 页面布局（参考 DFM 设计特点）

SARIMAX 模型 tab 为单页四环节工作流，环节间以 `st.markdown("---")` 分割线
分隔，环节标题采用 `#### ①/②/③/④ …` 样式；未满足前置条件的环节显示一行
`st.info` 引导提示并跳过，不报错、不中断后续环节。布局规范与 DFM 对齐：

- 参数控件一律 `st.columns(2~4)` 紧凑并排，每个 widget 带 `help` 说明；
- 长内容与详情进 `st.expander`（默认折叠）：高级优化器设置、参数摘要、
  候选模型表等；
- 运行反馈用 `st.spinner`；关键结果用 `st.metric` 指标卡（AIC/BIC/对数
  似然、AR 平稳性/MA 可逆性）与 `st.dataframe`；
- 操作按钮与下载按钮并排（columns），条件不满足时按钮 `disabled` 并给出
  warning（同 DFM 训练页的训练条件检查模式）。

## 4. 数据流

```
上传文件(CSV/XLSX/XLS)
  → load_shared_dataframe（编码回退 utf-8/gbk/gb2312；首列日期解析）
  → ModelingDataset（内容指纹 + 宽表 + 时间列标记）存入 session_state
  → 选择目标变量 + 外生变量
  → prepare_modeling_inputs → (目标 Series, 外生 DataFrame, 索引)
  → SARIMAXConfig / AutoSARIMAXConfig（signature 用于结果失效）
  → Ts.TsModels.SARIMAX(...).fit() 或 AutoSARIMAX(...).fit()
  → SARIMAXResult / AutoModelResult 存入 session_state
  → ③ 模型分析：参数表 / plot_fit / plot_diagnostics / test_residuals
  → ④ 模型预测：result.predict(...) → 预测表 + 区间图 + CSV
```

状态签名 =（文件指纹, 目标变量, 外生变量, 配置 signature）。任一变化即清除
旧拟合结果、诊断表与预测，避免展示陈旧结果。

## 5. Ts 包 API 对照

| 功能 | 调用 |
| --- | --- |
| 手动拟合 | `Ts.TsModels.SARIMAX(data, order, seasonal_order, trend, exog, log, enforce_stationarity, enforce_invertibility).fit(method, maxiter, cov_type)` |
| 自动选阶 | `Ts.TsModels.AutoSARIMAX(data, p, d, q, P, D, Q, s, trend, criterion, exog, log).fit()` |
| 参数/指标 | `result.params / std_errors / p_values / aic / bic / log_likelihood / nobs / effective_nobs / converged / optimizer` |
| 拟合/诊断图 | `result.plot_fit()` / `result.plot_diagnostics()`（返回 `(fig, ax)`） |
| 残差检验 | `result.test_residuals(lags)` → `ResidualTestResults`（white_noise / normality / ljung_box / engle_lm） |
| 稳定性 | `result.is_stationary / is_invertible` |
| 预测 | `result.predict(start=nobs, end=nobs+steps-1, dynamic, alpha, future_exog)` → `PredictResult.mean / lower / upper` |

## 6. 边界与失败模式

- 文件解析失败（编码、空表、无数值列）：页面报错，保留旧文件状态。
- 样本少于 10 个有效观测、log 变换遇非正值、季节周期 s 过大：拟合前
  `validate_fit_inputs()` 预检并提示；Ts 包自身的 `ValueError` 由
  `translate_ts_error()` 转译为中文。
- 优化不收敛：`require_convergence=True` 抛出 `RuntimeError`，页面展示
  optimizer 详情，提示更换优化器、加大 maxiter 或简化阶数。
- 外生变量要求：观测日期与目标序列完全对齐、无缺失（缺失按
  `missing="drop"` 丢弃并提示）；与趋势项冲突或秩亏时由 Ts 校验并转译。
- AutoSARIMAX 网格组合数预估展示；超过 200 个组合给出耗时警告。
- 预测时含外生变量：必须为每个预测期填写全部未来值（列名严格一致），
  未填完整时预测按钮禁用。

## 7. 明确不做（YAGNI）

- 不修改 Ts 包、不新增第三方依赖。
- 不做模型文件导出/加载、不做 compare_models 多模型比较。
- 不暴露干预事件（EventSpec）与有理分布滞后（RationalLagSpec）的 UI
  （Ts API 已支持，留待后续扩展）。
