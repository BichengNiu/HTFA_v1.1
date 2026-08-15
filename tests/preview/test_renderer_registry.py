from pathlib import Path

import pytest

from dashboard.preview.modules import PREVIEW_MODULES, create_preview_renderer
from dashboard.preview.shared.loader import PreviewWorkbookLoader
from dashboard.preview.shared.renderer import PreviewRenderer


def test_preview_modules_are_declared_config_not_class_per_module():
    assert set(PREVIEW_MODULES) == {"industrial", "uae"}

    industrial = create_preview_renderer("industrial")
    assert isinstance(industrial, PreviewRenderer)
    assert isinstance(industrial.loader, PreviewWorkbookLoader)
    assert industrial.module_title == "工业数据预览"
    assert industrial.state_namespace == "preview.industrial"
    assert industrial.default_relative_path is None

    uae = create_preview_renderer("uae")
    assert uae.module_title == "阿联酋数据预览"
    assert uae.state_namespace == "preview.uae"
    assert uae.default_relative_path == Path("data") / "阿联酋.xlsx"


def test_preview_renderer_rejects_unknown_module():
    with pytest.raises(ValueError, match="未找到子模块"):
        create_preview_renderer("unknown")


def test_preview_plugin_abstraction_layer_is_absent():
    assert not Path("dashboard/preview/core/base_loader.py").exists()
    assert not Path("dashboard/preview/core/base_renderer.py").exists()
    assert not Path("dashboard/preview/modules/industrial").exists()
    assert not Path("dashboard/preview/modules/uae").exists()
