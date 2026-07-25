"""阿联酋经济数据库加载器。"""

from dashboard.preview.modules.industrial.loader import IndustrialLoader


class UAELoader(IndustrialLoader):
    """使用统一工作簿协议加载阿联酋数据。"""

    module_name = "uae"
    state_namespace = "preview.uae"
