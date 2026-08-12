from dashboard.auth.permissions import GRANULAR_PERMISSION_MAP
from dashboard.core.ui.components.content_router import (
    detect_navigation_level,
)
from dashboard.core.ui.constants import UIConstants
from dashboard.navigation_config import MODULE_CONFIG


def test_uae_monitoring_is_available_in_navigation():
    assert "阿联酋" in MODULE_CONFIG["监测分析"]
    assert "阿联酋" in UIConstants.MAIN_MODULES["监测分析"]["sub_modules"]
    assert (
        detect_navigation_level("监测分析", "阿联酋")
        == "FUNCTION_ACTIVE"
    )


def test_uae_monitoring_has_granular_permission():
    permission = GRANULAR_PERMISSION_MAP["监测分析"]["sub_modules"]["阿联酋"]

    assert permission == {
        "code": "monitoring_analysis.uae",
        "tabs": None,
    }


def test_preview_uae_permission_remains_unchanged():
    permission = GRANULAR_PERMISSION_MAP["数据预览"]["sub_modules"]["阿联酋"]

    assert permission == {
        "code": "data_preview.uae",
        "tabs": None,
    }
