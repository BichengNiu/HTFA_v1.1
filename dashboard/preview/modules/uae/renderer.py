"""阿联酋数据预览渲染器。"""

from pathlib import Path

from dashboard.preview.shared.renderer import PreviewRenderer


class UAERenderer(PreviewRenderer):
    """阿联酋预览模块身份适配器。"""

    module_title = "阿联酋数据预览"
    default_relative_path = Path("data") / "阿联酋.xlsx"
