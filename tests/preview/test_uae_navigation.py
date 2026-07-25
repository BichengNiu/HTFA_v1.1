import ast
from pathlib import Path

from dashboard.auth.permissions import GRANULAR_PERMISSION_MAP
from dashboard.core.ui.components.content_router import (
    PREVIEW_MODULE_MAPPING,
    detect_navigation_level,
)
from dashboard.core.ui.constants import UIConstants


def _read_app_module_config():
    module = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "MODULE_CONFIG"
                for target in node.targets
            ):
                return ast.literal_eval(node.value)
    raise AssertionError("app.py does not define MODULE_CONFIG")


def test_uae_is_available_in_sidebar_and_preview_routing():
    module_config = _read_app_module_config()

    assert "阿联酋" in module_config["数据预览"]
    assert "阿联酋" in UIConstants.MAIN_MODULES["数据预览"]["sub_modules"]
    assert PREVIEW_MODULE_MAPPING["阿联酋"] == "uae"
    assert detect_navigation_level("数据预览", "阿联酋") == "FUNCTION_ACTIVE"


def test_uae_has_granular_preview_permission():
    uae_permission = GRANULAR_PERMISSION_MAP["数据预览"]["sub_modules"]["阿联酋"]

    assert uae_permission == {
        "code": "data_preview.uae",
        "tabs": None,
    }
