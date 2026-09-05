"""数据预览子模块的声明式配置。"""

from pathlib import Path

from ..shared.loader import EconomicWorkbookLoader
from ..shared.renderer import EconomicWorkbookRenderer

ECONOMIC_WORKBOOK_MODULES = {
    "industrial": {
        "module_name": "industrial",
        "state_namespace": "preview.industrial",
        "module_title": "工业数据预览",
        "default_relative_path": None,
    },
    "uae": {
        "module_name": "uae",
        "state_namespace": "preview.uae",
        "module_title": "阿联酋数据预览",
        "default_relative_path": Path("data") / "UAE" / "阿联酋.xlsx",
    },
}


def create_economic_workbook_renderer(module_name: str) -> EconomicWorkbookRenderer:
    """按模块配置创建共享渲染器实例。

    Args:
        module_name: 子模块ID (如 'industrial', 'uae')

    Returns:
        EconomicWorkbookRenderer: 渲染器实例

    Raises:
        ValueError: 未找到指定的子模块
    """
    config = ECONOMIC_WORKBOOK_MODULES.get(module_name)
    if config is None:
        raise ValueError(f"未找到子模块: {module_name}")

    loader = EconomicWorkbookLoader(
        config["module_name"],
        config["state_namespace"],
    )
    return EconomicWorkbookRenderer(
        loader,
        module_title=config["module_title"],
        default_relative_path=config["default_relative_path"],
    )


__all__ = [
    "ECONOMIC_WORKBOOK_MODULES",
    "create_economic_workbook_renderer",
]
