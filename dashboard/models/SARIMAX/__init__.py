"""SARIMAX 系列模型子模块。

基于 Ts 包的 SARIMAX / AutoSARIMAX 建模工作流，数据概览位于
“数据探索 → 单变量分析 → 数据概览”，模型页包含三个环节：
① 模型训练 → ② 残差诊断 → ③ 模型预测。
"""

from dashboard.models.SARIMAX.ui.pages import render_sarimax_model_page

__all__ = ["render_sarimax_model_page"]
