"""Executable checks for the current domain and dependency contracts."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


from tooling.source_tree import python_sources

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_NAMES = (
    "preview",
    "monitoring",
    "exploration",
    "models/univariate",
    "models/dfm",
)


def test_architecture_contracts_are_recorded_in_domain_docs() -> None:
    context = (PROJECT_ROOT / "CONTEXT.md").read_text(encoding="utf-8")

    for term in (
        "经济工作簿",
        "普通表格数据集",
        "经济工作簿输入协议",
        "普通表格输入协议",
        "领域模块",
        "逻辑 seam",
    ):
        assert term in context

    for relative_path in (
        "docs/architecture.md",
        "docs/model-contracts.md",
        "docs/data-pipeline.md",
        "docs/runtime.md",
        "docs/development.md",
    ):
        assert (PROJECT_ROOT / relative_path).is_file()

    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(
        encoding="utf-8"
    )
    for domain_name in DOMAIN_NAMES:
        assert f"`{domain_name}`" in architecture
        assert (PROJECT_ROOT / "htfa" / domain_name).is_dir()


def test_data_overview_has_one_internal_ownership_boundary() -> None:
    assert (PROJECT_ROOT / "htfa/exploration/data/tabular/__init__.py").is_file()
    assert (PROJECT_ROOT / "htfa/ui_shared/data_overview/__init__.py").is_file()
    assert not (PROJECT_ROOT / "htfa/exploration/data/tabular_input.py").exists()
    assert not (PROJECT_ROOT / "components/__init__.py").exists()
    assert not list(python_sources((PROJECT_ROOT / "components")))

    for source_file in _production_python_files():
        source = source_file.read_text(encoding="utf-8")
        assert "components.data_overview" not in source
        assert "from data_overview" not in source
        assert "import data_overview" not in source


def _imported_modules(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _production_python_files() -> tuple[Path, ...]:
    files = list(python_sources((PROJECT_ROOT / "htfa")))
    files.extend(python_sources((PROJECT_ROOT / "scripts")))
    files.append(PROJECT_ROOT / "app.py")
    return tuple(files)


def test_legacy_dashboard_imports_and_source_paths_are_gone() -> None:
    assert not (PROJECT_ROOT / "dashboard/__init__.py").exists()
    assert not list(python_sources((PROJECT_ROOT / "dashboard")))

    for source_file in _production_python_files():
        assert all(
            not module.startswith("dashboard")
            for module in _imported_modules(source_file)
        ), source_file


def test_uae_maintenance_jobs_have_one_package_boundary() -> None:
    jobs_root = PROJECT_ROOT / "htfa/jobs/uae_data"
    assert (jobs_root / "update_data.py").is_file()
    assert (jobs_root / "merge_workbook.py").is_file()
    assert (jobs_root / "paths.py").is_file()
    assert not list(python_sources((PROJECT_ROOT / "htfa/monitoring/uae/assets/scripts")))

    for source_file in jobs_root.glob("*.py"):
        modules = _imported_modules(source_file)
        assert not any(
            module.startswith("dashboard") for module in modules
        ), source_file
        assert "sys.path" not in source_file.read_text(encoding="utf-8")

    for relative_path in (
        "htfa/jobs/uae_data/update_data.bat",
        "htfa/jobs/uae_data/merge_workbook.bat",
        "htfa/monitoring/uae/assets/auto_update_all.bat",
    ):
        launcher = (PROJECT_ROOT / relative_path).read_text(
            encoding="utf-8-sig"
        )
        assert "sys.path.insert" not in launcher
        assert "htfa.jobs.uae_data" in launcher
        assert "-m htfa.jobs.uae_data" in launcher


def test_model_domains_have_no_cross_family_or_application_imports() -> None:
    dfm_files = python_sources((PROJECT_ROOT / "htfa/models/dfm"))
    for source_file in dfm_files:
        modules = _imported_modules(source_file)
        assert not any(
            module.startswith("htfa.models.univariate")
            for module in modules
        ), source_file
        if "ui" not in source_file.parts:
            assert not any(
                module.startswith("htfa.app")
                for module in modules
            ), source_file

    univariate_files = python_sources((PROJECT_ROOT / "htfa/models/univariate"))
    for source_file in univariate_files:
        modules = _imported_modules(source_file)
        assert not any(
            module.startswith("htfa.models.dfm")
            for module in modules
        ), source_file


def test_domain_core_imports_do_not_preload_streamlit() -> None:
    explicit_modules = {
        "preview": {
            "htfa.workspace.data.files",
            "htfa.exploration.data.tabular",
            "htfa.preview.data.economic_workbook.parser",
        },
        "monitoring": {
            "htfa.monitoring.uae.contracts.records",
            "htfa.monitoring.uae.processing.services",
            "htfa.monitoring.industrial.processing.data_input",
        },
        "exploration": {"htfa.exploration.processing.analysis.stationarity"},
        "models/univariate": {"htfa.models.univariate.common.contracts"},
        "models/dfm": set(),
    }
    for domain_name, module_names in _discovered_core_modules().items():
        core_modules = module_names | explicit_modules[domain_name]
        module_literal = repr(tuple(sorted(core_modules)))
        code = (
            "import importlib, sys\n"
            f"sys.path.insert(0, {str(PROJECT_ROOT)!r})\n"
            f"for name in {module_literal}:\n"
            "    importlib.import_module(name)\n"
            "    assert 'streamlit' not in sys.modules, name\n"
            "    assert 'dashboard' not in sys.modules, name\n"
            "    assert 'components' not in sys.modules, name\n"
            "    assert 'htfa.app' not in sys.modules, name\n"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{domain_name}: {result.stderr}"


def _discovered_core_modules() -> dict[str, set[str]]:
    roots = {
        "preview": PROJECT_ROOT / "htfa/preview",
        "monitoring": PROJECT_ROOT / "htfa/monitoring",
        "exploration": PROJECT_ROOT / "htfa/exploration",
        "models/univariate": PROJECT_ROOT / "htfa/models/univariate",
        "models/dfm": PROJECT_ROOT / "htfa/models/dfm",
    }
    discovered: dict[str, set[str]] = {}
    for domain_name, root in roots.items():
        modules: set[str] = set()
        for source_file in python_sources(root):
            if source_file.name == "__init__.py":
                continue
            relative = source_file.relative_to(PROJECT_ROOT).with_suffix("")
            parts = [part for part in relative.parts if part != "__init__"]
            if not _is_core_source_file(source_file, parts):
                continue
            modules.add(".".join(parts))
        discovered[domain_name] = modules
    return discovered


_NON_CORE_PATH_PARTS = {"ui", "pages", "components", "modules", "charts"}
_NON_CORE_FILE_NAMES = {
    "charts.py",
    "download_utils.py",
    "data_cache.py",
    "downloads.py",
    "enterprise_analysis.py",
    "fragment_components.py",
    "industrial_analysis.py",
    "macro_analysis.py",
    "plotting.py",
    "report.py",
    "renderer.py",
    "standalone_data_overview.py",
    "standalone_model.py",
    "state_manager.py",
    "tabs.py",
}


def _is_core_source_file(source_file, parts: list[str]) -> bool:
    """识别五个领域中不应加载 Streamlit 的规则/数据核心模块。"""
    if _NON_CORE_PATH_PARTS.intersection(parts):
        return False
    return source_file.name not in _NON_CORE_FILE_NAMES


def test_industrial_data_loader_is_pure_and_cache_adapter_is_explicit() -> None:
    loader = PROJECT_ROOT / "htfa/monitoring/industrial/processing/data_input.py"
    cache_adapter = PROJECT_ROOT / "htfa/monitoring/industrial/ui/data_cache.py"

    loader_source = loader.read_text(encoding="utf-8")
    cache_source = cache_adapter.read_text(encoding="utf-8")
    assert "import streamlit" not in loader_source
    assert "st.cache_data" not in loader_source
    assert "import streamlit" in cache_source
    assert "st.cache_data" in cache_source
