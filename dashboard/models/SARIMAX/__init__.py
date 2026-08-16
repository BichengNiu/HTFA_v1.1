"""SARIMAX 系列模型子模块。

基于 Ts 包的 SARIMAX / AutoSARIMAX 建模工作流，单页四环节：
① 数据导入 → ② 模型训练 → ③ 模型分析 → ④ 模型预测。
"""

from dashboard.models.SARIMAX.ui.pages import render_sarimax_model_page

__all__ = ["render_sarimax_model_page"]
