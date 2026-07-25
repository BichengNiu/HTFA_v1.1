"""阿联酋数据预览渲染器。"""

from pathlib import Path

from dashboard.preview.modules.industrial.renderer import IndustrialRenderer


class UAERenderer(IndustrialRenderer):
    """复用工业布局，仅替换模块身份和默认数据源。"""

    module_title = "阿联酋数据预览"
    default_relative_path = Path("data") / "阿联酋.xlsx"
