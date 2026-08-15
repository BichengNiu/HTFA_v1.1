"""
数据预览子模块实现层

子模块以 (加载器类, 渲染器类) 对声明，工厂函数按需创建渲染器实例。
"""

from dashboard.preview.core.base_renderer import BaseRenderer

# 模块注册表：模块ID -> (加载器类, 渲染器类)
PREVIEW_MODULES = {}


def _ensure_default_modules() -> None:
    """首次创建时注册内置模块，避免包初始化循环导入。"""
    if PREVIEW_MODULES:
        return

    from dashboard.preview.modules.industrial.loader import IndustrialLoader
    from dashboard.preview.modules.industrial.renderer import IndustrialRenderer
    from dashboard.preview.modules.uae.loader import UAELoader
    from dashboard.preview.modules.uae.renderer import UAERenderer

    PREVIEW_MODULES.update(
        {
            "industrial": (IndustrialLoader, IndustrialRenderer),
            "uae": (UAELoader, UAERenderer),
        }
    )


def create_preview_renderer(module_name: str) -> BaseRenderer:
    """创建子模块渲染器实例。

    Args:
        module_name: 子模块ID (如 'industrial', 'uae')

    Returns:
        BaseRenderer: 渲染器实例

    Raises:
        ValueError: 未找到指定的子模块
    """
    _ensure_default_modules()
    pair = PREVIEW_MODULES.get(module_name)
    if pair is None:
        raise ValueError(f"未找到子模块: {module_name}")

    loader_class, renderer_class = pair
    return renderer_class(loader_class())


__all__ = [
    'PREVIEW_MODULES',
    'create_preview_renderer',
]
