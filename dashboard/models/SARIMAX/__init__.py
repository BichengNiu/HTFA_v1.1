"""SARIMAX 系列模型子模块。

基于 Ts 包的 SARIMAX / AutoSARIMAX 建模工作流；模型页使用自身的
数据读取入口，包含模型训练、残差诊断和模型预测三个环节：
① 模型训练 → ② 残差诊断 → ③ 模型预测。
"""

from dashboard.models.SARIMAX.ui.pages import render_sarimax_model_page

__all__ = ["render_sarimax_model_page"]
