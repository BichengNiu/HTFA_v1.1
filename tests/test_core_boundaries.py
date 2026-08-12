from pathlib import Path

from dashboard.auth.config import AuthConfig
from dashboard.auth.permissions import (
    GRANULAR_PERMISSION_MAP,
    PERMISSION_MODULE_MAP,
)
from dashboard.navigation_config import MODULE_CONFIG


def test_debug_mode_requires_explicit_environment_flag(monkeypatch):
    monkeypatch.delenv("HTFA_DEBUG_MODE", raising=False)
    assert AuthConfig.is_debug_mode() is False

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    assert AuthConfig.is_debug_mode() is True


def test_navigation_and_permission_views_share_one_hierarchy():
    assert tuple(MODULE_CONFIG) == tuple(GRANULAR_PERMISSION_MAP)
    assert tuple(MODULE_CONFIG) == tuple(PERMISSION_MODULE_MAP)

    for main_name, config in GRANULAR_PERMISSION_MAP.items():
        expected_submodules = list(config.get("sub_modules") or {})
        actual = MODULE_CONFIG[main_name]
        assert ([] if actual is None else list(actual)) == expected_submodules


def test_app_has_no_embedded_launcher_and_local_start_defaults_to_debug():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "subprocess" not in source
    assert "render_tracking" not in source
    assert "get_resource_loader" not in source

    launcher = Path("scripts/windows/start.bat").read_text(encoding="utf-8")
    assert 'if not defined HTFA_DEBUG_MODE set "HTFA_DEBUG_MODE=true"' in launcher


def test_incomplete_uae_v2_navigation_was_removed():
    assert "阿联酋V2" not in repr(MODULE_CONFIG)


def test_navigation_only_tracks_current_main_and_submodule():
    source = Path("dashboard/core/backend/navigation/manager.py").read_text(
        encoding="utf-8"
    )
    for obsolete_name in (
        "PREVIOUS_MAIN",
        "PREVIOUS_SUB",
        "TRANSITIONING",
        "LAST_NAVIGATION_TIME",
        "clear_navigation_cache",
        "get_navigation_state_info",
        "is_transitioning",
        "set_transitioning",
    ):
        assert obsolete_name not in source


def test_sidebar_does_not_build_an_unused_result_object():
    source = Path(
        "dashboard/core/ui/components/sidebar/renderer.py"
    ).read_text(encoding="utf-8")
    assert "main_module_result" not in source
    assert "sub_module_result" not in source
    assert "upload_info" not in source


def test_content_router_renders_directly_without_result_protocol():
    source = Path(
        "dashboard/core/ui/components/content_router.py"
    ).read_text(encoding="utf-8")

    assert "def render_main_content() -> None" in source
    assert "get_content_config" not in source
    assert "validate_content_config" not in source
    assert "content_result" not in source
