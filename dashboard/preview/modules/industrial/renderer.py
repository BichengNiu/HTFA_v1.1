"""工业数据预览渲染器。"""

from dashboard.preview.shared.renderer import PreviewRenderer


class IndustrialRenderer(PreviewRenderer):
    """工业预览模块身份适配器。"""

    module_title = "工业数据预览"
