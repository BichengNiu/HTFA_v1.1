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


def test_portable_data_overview_does_not_depend_on_host_application() -> None:
    package_root = PROJECT_ROOT / "components/data_overview"
    source_files = (
        source_file
        for source_file in package_root.rglob("*.py")
        if "tests" not in source_file.parts
    )

    for source_file in source_files:
        source = source_file.read_text(encoding="utf-8")
        assert "dashboard" not in source_file.parts
        assert "dashboard." not in source
        assert "from dashboard" not in source
        assert "import dashboard" not in source
        assert "from htfa" not in source
        assert "import htfa" not in source


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
    files.extend(
        path
        for path in (PROJECT_ROOT / "components").rglob("*.py")
        if "tests" not in path.parts
    )
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
    core_modules = (
        "htfa.data.tabular_input",
        "htfa.data.economic_workbook.core.workbook_parser",
        "htfa.monitoring.uae.contracts",
        "htfa.monitoring.uae.services",
        "htfa.exploration.core.data_source",
        "htfa.exploration.analysis.stationarity",
        "htfa.models.univariate.common.contracts",
        "htfa.models.univariate.sarimax.core.modeling",
        "htfa.models.dfm.train.core.models",
        "htfa.models.dfm.decomp.core.impact_analyzer",
    )
    module_literal = repr(core_modules)
    code = (
        "import importlib, sys; "
        f"sys.path.insert(0, {str(PROJECT_ROOT)!r}); "
        f"[importlib.import_module(name) for name in {module_literal}]; "
        "assert 'streamlit' not in sys.modules; "
        "assert 'dashboard' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
