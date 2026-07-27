from dashboard.core.backend.config.core_config import ResourcePathsConfig
from dashboard.preview.modules.industrial.loader import IndustrialLoader
from dashboard.preview.modules.industrial.renderer import IndustrialRenderer
from dashboard.preview.modules.uae.loader import UAELoader
from dashboard.preview.modules.uae.renderer import UAERenderer
from dashboard.preview.shared.loader import PreviewWorkbookLoader
from dashboard.preview.shared.renderer import PreviewRenderer


def test_domain_modules_depend_on_shared_preview_components():
    assert IndustrialLoader.__bases__ == (PreviewWorkbookLoader,)
    assert UAELoader.__bases__ == (PreviewWorkbookLoader,)
    assert IndustrialRenderer.__bases__ == (PreviewRenderer,)
    assert UAERenderer.__bases__ == (PreviewRenderer,)
    assert IndustrialRenderer.default_relative_path is None


def test_resource_preloader_targets_active_preview_modules():
    paths = ResourcePathsConfig().module_paths

    assert paths["preview_parser"] == "dashboard.preview.core.workbook_parser"
    assert paths["preview_registry"] == "dashboard.preview.modules"
    assert "data_loader" not in paths
    assert "preview_main" not in paths
