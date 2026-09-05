from pathlib import Path

import pytest

from htfa.data.economic_workbook.modules import (
    ECONOMIC_WORKBOOK_MODULES,
    create_economic_workbook_renderer,
)
from htfa.data.economic_workbook.shared.loader import EconomicWorkbookLoader
from htfa.data.economic_workbook.shared.renderer import EconomicWorkbookRenderer


def test_preview_modules_are_declared_config_not_class_per_module():
    assert set(ECONOMIC_WORKBOOK_MODULES) == {"industrial", "uae"}

    industrial = create_economic_workbook_renderer("industrial")
    assert isinstance(industrial, EconomicWorkbookRenderer)
    assert isinstance(industrial.loader, EconomicWorkbookLoader)
    assert industrial.module_title == "工业数据预览"
    assert industrial.state_namespace == "economic_workbook.industrial"
    assert industrial.default_relative_path is None

    uae = create_economic_workbook_renderer("uae")
    assert uae.module_title == "阿联酋数据预览"
    assert uae.state_namespace == "economic_workbook.uae"
    assert uae.default_relative_path == Path("data") / "UAE" / "阿联酋.xlsx"


def test_preview_renderer_rejects_unknown_module():
    with pytest.raises(ValueError, match="未找到子模块"):
        create_economic_workbook_renderer("unknown")


def test_preview_plugin_abstraction_layer_is_absent():
    assert not Path("htfa/data/economic_workbook/core/base_loader.py").exists()
    assert not Path("htfa/data/economic_workbook/core/base_renderer.py").exists()
    assert not Path("htfa/data/economic_workbook/modules/industrial").exists()
    assert not Path("htfa/data/economic_workbook/modules/uae").exists()
