"""阿联酋数据预览加载器。"""

from dashboard.preview.shared.loader import PreviewWorkbookLoader


class UAELoader(PreviewWorkbookLoader):
    """阿联酋预览模块身份适配器。"""

    module_name = "uae"
    state_namespace = "preview.uae"
