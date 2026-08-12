from dashboard.preview.modules import PreviewModuleRegistry
from dashboard.preview.modules.industrial.loader import IndustrialLoader
from dashboard.preview.modules.industrial.renderer import IndustrialRenderer
from dashboard.preview.modules.uae.loader import UAELoader
from dashboard.preview.modules.uae.renderer import UAERenderer
from dashboard.preview.shared.loader import PreviewWorkbookLoader
from dashboard.preview.shared.renderer import PreviewRenderer
from dashboard.preview.shared.config import FREQUENCY_CONFIGS


def test_domain_modules_depend_on_shared_preview_components():
    assert IndustrialLoader.__bases__ == (PreviewWorkbookLoader,)
    assert UAELoader.__bases__ == (PreviewWorkbookLoader,)
    assert IndustrialRenderer.__bases__ == (PreviewRenderer,)
    assert UAERenderer.__bases__ == (PreviewRenderer,)
    assert IndustrialRenderer.default_relative_path is None


def test_registry_exposes_only_active_preview_modules():
    modules = PreviewModuleRegistry.get_all_modules()

    assert set(modules) == {"industrial", "uae"}
    assert modules["industrial"]["loader"] is IndustrialLoader
    assert modules["uae"]["renderer"] is UAERenderer


def test_frequency_metadata_has_one_typed_source():
    from dashboard.preview.core.base_config import FrequencyConfig

    assert FREQUENCY_CONFIGS
    assert all(isinstance(config, FrequencyConfig) for config in FREQUENCY_CONFIGS.values())
