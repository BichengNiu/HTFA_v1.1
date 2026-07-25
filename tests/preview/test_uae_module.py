from pathlib import Path

from dashboard.preview.modules import PreviewModuleRegistry
from dashboard.preview.modules.uae.renderer import UAERenderer


def test_uae_module_is_registered_with_isolated_configuration():
    module = PreviewModuleRegistry.get_module("uae")

    assert module is not None
    renderer = PreviewModuleRegistry.create_renderer("uae")
    assert isinstance(renderer, UAERenderer)
    assert renderer.module_title == "阿联酋数据预览"
    assert renderer.default_relative_path == Path("data") / "阿联酋.xlsx"
    assert renderer.state_namespace == "preview.uae"
    assert renderer.tab_names == [
        "数据概览",
        "日度",
        "周度",
        "旬度",
        "月度",
        "季度",
        "年度",
    ]
