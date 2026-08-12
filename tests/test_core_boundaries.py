from pathlib import Path

from dashboard.auth.config import AuthConfig
from dashboard.auth.permissions import GRANULAR_PERMISSION_MAP, PERMISSION_MODULE_MAP
from dashboard.navigation_config import MODULE_CONFIG


def test_debug_mode_requires_explicit_environment_flag(monkeypatch):
    monkeypatch.delenv("HTFA_DEBUG_MODE", raising=False)
    assert AuthConfig.is_debug_mode() is False

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    assert AuthConfig.is_debug_mode() is True


def test_navigation_and_permissions_share_one_hierarchy():
    assert tuple(MODULE_CONFIG) == tuple(GRANULAR_PERMISSION_MAP)
    assert tuple(MODULE_CONFIG) == tuple(PERMISSION_MODULE_MAP)


def test_retired_core_and_auth_wrappers_are_absent():
    assert not Path("dashboard/core/ui/constants.py").exists()

    sidebar = Path(
        "dashboard/core/ui/components/sidebar/renderer.py"
    ).read_text(encoding="utf-8")
    middleware = Path("dashboard/auth/ui/middleware.py").read_text(
        encoding="utf-8"
    )

    assert "def filter_modules_by_permission(" not in sidebar
    assert "def require_permission(" not in middleware
    assert "def filter_accessible_modules(" not in middleware
    assert "def get_current_user(" not in middleware
    assert "def is_authenticated(" not in middleware


def test_explore_core_depends_on_workbook_contract_not_preview_ui_adapter():
    source = Path("dashboard/explore/core/data_source.py").read_text(
        encoding="utf-8"
    )

    assert "dashboard.preview.modules.uae.loader" not in source
    assert "dashboard.preview.core.workbook_parser" in source
