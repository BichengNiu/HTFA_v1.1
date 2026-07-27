"""工业数据预览加载器。"""

from dashboard.preview.shared.loader import PreviewWorkbookLoader


class IndustrialLoader(PreviewWorkbookLoader):
    """工业预览模块身份适配器。"""

    module_name = "industrial"
    state_namespace = "preview.industrial"
