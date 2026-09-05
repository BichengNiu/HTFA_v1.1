# 五个内部领域模块的模块化单体

**Status:** accepted

HTFA 继续作为一个本地模块化单体运行，但内部领域固定拆为 `data`、`monitoring`、`exploration`、`models/univariate` 和 `models/dfm` 五个领域模块；`app`、`workspace`、`ui_shared` 与 `jobs` 是横向基础设施。领域模块按业务能力划分，不按导航 tab 或页面数量划分，因为页面会组合多个领域能力，而领域规则必须能脱离页面独立验证。

**Considered Options:** 保留以 `dashboard` 为中心的页面目录；按导航 tab 拆分；按五个业务能力拆分。选择最后一种，能够约束依赖方向并让领域迁移按 seam 分阶段完成。

**Consequences:** 应用组装层可以依赖领域 UI，但领域 core 不得依赖应用组装层、Streamlit 或其他领域页面。迁移完成后旧 `dashboard` 命名空间不再存在。
