"""SARIMAX、RDL 与 ARDL 的模型实现和页面。

页面入口位于 ``htfa.models.univariate.sarimax.ui.pages``，核心计算位于
``htfa.models.univariate.sarimax.core``。本包不在导入时组装 Streamlit 页面，
避免模型 core 因包初始化反向加载 UI。
"""
