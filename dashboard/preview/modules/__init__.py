"""
数据预览子模块实现层

提供子模块注册和管理机制
"""

from typing import Dict, Type
from dashboard.preview.core.base_loader import BaseDataLoader
from dashboard.preview.core.base_renderer import BaseRenderer


class PreviewModuleRegistry:
    """预览子模块注册表

    用于管理和查找所有预览子模块

    设计原则:
    - 单一职责: 只负责模块注册和查找
    - 工厂模式: 提供统一的渲染器创建接口
    """

    _modules: Dict[str, Dict[str, Type]] = {}
    _defaults_registered = False

    @classmethod
    def _ensure_default_modules(cls) -> None:
        """首次查询时注册内置模块，避免包初始化循环导入。"""
        if cls._defaults_registered:
            return

        from dashboard.preview.modules.industrial.loader import IndustrialLoader
        from dashboard.preview.modules.industrial.renderer import IndustrialRenderer
        from dashboard.preview.modules.uae.loader import UAELoader
        from dashboard.preview.modules.uae.renderer import UAERenderer

        cls.register(
            "industrial",
            IndustrialLoader,
            IndustrialRenderer,
        )
        cls.register("uae", UAELoader, UAERenderer)
        cls._defaults_registered = True

    @classmethod
    def register(
        cls,
        module_name: str,
        loader_class: Type[BaseDataLoader],
        renderer_class: Type[BaseRenderer],
    ):
        """注册子模块

        Args:
            module_name: 子模块名称 (如 'industrial', 'energy')
            loader_class: 加载器类
            renderer_class: 渲染器类
        """
        cls._modules[module_name] = {
            'loader': loader_class,
            'renderer': renderer_class
        }

    @classmethod
    def get_module(cls, module_name: str) -> Dict[str, Type]:
        """获取子模块

        Args:
            module_name: 子模块名称

        Returns:
            Dict[str, Type]: 子模块组件字典
        """
        cls._ensure_default_modules()
        return cls._modules.get(module_name)

    @classmethod
    def get_all_modules(cls) -> Dict[str, Dict[str, Type]]:
        """获取所有注册的子模块

        Returns:
            Dict[str, Dict[str, Type]]: 所有子模块
        """
        cls._ensure_default_modules()
        return cls._modules

    @classmethod
    def create_renderer(cls, module_name: str) -> BaseRenderer:
        """创建子模块渲染器实例

        工厂方法，自动组装依赖

        Args:
            module_name: 子模块名称

        Returns:
            BaseRenderer: 渲染器实例

        Raises:
            ValueError: 未找到指定的子模块
        """
        module = cls.get_module(module_name)
        if not module:
            raise ValueError(f"未找到子模块: {module_name}")

        loader = module['loader']()
        renderer = module['renderer'](loader)
        return renderer


__all__ = [
    'PreviewModuleRegistry',
]
