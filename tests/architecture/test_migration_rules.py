"""Executable phase-A checks for the five-domain migration decisions."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_NAMES = (
    "data",
    "monitoring",
    "exploration",
    "models/univariate",
    "models/dfm",
)


def test_migration_decisions_are_recorded_in_domain_docs() -> None:
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
        "docs/adr/0006-five-domain-modular-monolith.md",
        "docs/adr/0007-economic-workbook-and-tabular-input-seams.md",
        "docs/adr/0008-direct-cutover-without-migration-compatibility.md",
    ):
        assert (PROJECT_ROOT / relative_path).is_file()

    plan = (
        PROJECT_ROOT / "docs/plans/2026-09-05-five-domain-module-migration.md"
    ).read_text(encoding="utf-8")
    for domain_name in DOMAIN_NAMES:
        assert f"`htfa/{domain_name}`" in plan


def test_data_overview_has_one_internal_ownership_boundary() -> None:
    assert (PROJECT_ROOT / "htfa/data/tabular/__init__.py").is_file()
    assert (PROJECT_ROOT / "htfa/ui_shared/data_overview/__init__.py").is_file()
    assert not (PROJECT_ROOT / "htfa/data/tabular_input.py").exists()
    assert not (PROJECT_ROOT / "components/__init__.py").exists()
    assert not list((PROJECT_ROOT / "components").rglob("*.py"))

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
    files = list((PROJECT_ROOT / "htfa").rglob("*.py"))
    files.extend((PROJECT_ROOT / "scripts").rglob("*.py"))
    files.append(PROJECT_ROOT / "app.py")
    return tuple(files)


def test_legacy_dashboard_imports_and_source_paths_are_gone() -> None:
    assert not (PROJECT_ROOT / "dashboard/__init__.py").exists()
    assert not list((PROJECT_ROOT / "dashboard").rglob("*.py"))

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
    assert not list((PROJECT_ROOT / "data/UAE/scripts").rglob("*.py"))

    for source_file in jobs_root.glob("*.py"):
        modules = _imported_modules(source_file)
        assert not any(
            module.startswith("dashboard") for module in modules
        ), source_file
        assert "sys.path" not in source_file.read_text(encoding="utf-8")

    for relative_path in (
        "htfa/jobs/uae_data/update_data.bat",
        "htfa/jobs/uae_data/merge_workbook.bat",
        "data/UAE/auto_update_all.bat",
    ):
        launcher = (PROJECT_ROOT / relative_path).read_text(
            encoding="utf-8-sig"
        )
        assert "sys.path.insert(0" in launcher
        assert "htfa.jobs.uae_data" in launcher
        assert "-m htfa.jobs.uae_data" not in launcher


def test_model_domains_have_no_cross_family_or_application_imports() -> None:
    dfm_files = (PROJECT_ROOT / "htfa/models/dfm").rglob("*.py")
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

    univariate_files = (PROJECT_ROOT / "htfa/models/univariate").rglob("*.py")
    for source_file in univariate_files:
        modules = _imported_modules(source_file)
        assert not any(
            module.startswith("htfa.models.dfm")
            for module in modules
        ), source_file


def test_domain_core_imports_do_not_preload_streamlit() -> None:
    explicit_modules = {
        "data": {
            "htfa.data.file_content",
            "htfa.data.tabular",
            "htfa.data.economic_workbook.core.workbook_parser",
        },
        "monitoring": {
            "htfa.monitoring.uae.contracts",
            "htfa.monitoring.uae.services",
            "htfa.monitoring.industrial.utils.data_loader",
        },
        "exploration": {"htfa.exploration.analysis.stationarity"},
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
        "data": PROJECT_ROOT / "htfa/data",
        "monitoring": PROJECT_ROOT / "htfa/monitoring",
        "exploration": PROJECT_ROOT / "htfa/exploration",
        "models/univariate": PROJECT_ROOT / "htfa/models/univariate",
        "models/dfm": PROJECT_ROOT / "htfa/models/dfm",
    }
    discovered: dict[str, set[str]] = {}
    for domain_name, root in roots.items():
        modules: set[str] = set()
        for source_file in root.rglob("*.py"):
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
    loader = PROJECT_ROOT / "htfa/monitoring/industrial/utils/data_loader.py"
    cache_adapter = PROJECT_ROOT / "htfa/monitoring/industrial/utils/data_cache.py"

    loader_source = loader.read_text(encoding="utf-8")
    cache_source = cache_adapter.read_text(encoding="utf-8")
    assert "import streamlit" not in loader_source
    assert "st.cache_data" not in loader_source
    assert "import streamlit" in cache_source
    assert "st.cache_data" in cache_source
