"""全仓生产路径的直接切换门禁。"""

from __future__ import annotations

import ast
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIRECTORIES = (
    PROJECT_ROOT / "dashboard",
    PROJECT_ROOT / "components",
    PROJECT_ROOT / "data/UAE/scripts",
    PROJECT_ROOT / "htfa/data/tabular_input.py",
    PROJECT_ROOT / "htfa/monitoring/uae/sheet_reader.py",
)
ACTIVE_TEXT_ROOTS = (
    PROJECT_ROOT / "app.py",
    PROJECT_ROOT / "htfa",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "tooling",
    PROJECT_ROOT / "data/UAE",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "docs",
    PROJECT_ROOT / "CONTEXT.md",
)
TEXT_SUFFIXES = {".py", ".bat", ".ps1", ".ini", ".toml", ".md"}
INTENTIONAL_CHECK_FILES = {
    PROJECT_ROOT / "tests/architecture/test_no_legacy_paths.py",
    PROJECT_ROOT / "tests/architecture/test_migration_rules.py",
    PROJECT_ROOT / "tests/architecture/test_data_overview_boundaries.py",
    PROJECT_ROOT / "tests/test_core_boundaries.py",
}
HISTORICAL_DOCUMENT_ROOTS = (
    PROJECT_ROOT / "docs/adr",
    PROJECT_ROOT / "docs/plans",
)
LEGACY_PATH_PATTERN = re.compile(
    r"(?:from\s+dashboard\b|import\s+dashboard\b|"
    r"dashboard[/\\]|components[/\\]data_overview|"
    r"components\.data_overview|from\s+data_overview\b|"
    r"import\s+data_overview\b|sys\.path[^\n]*components|"
    r"COPY\s+components|htfa\.data\.tabular_input)"
)
LEGACY_API_PATTERN = re.compile(
    r"\b(?:SharedDatasetSnapshot|fingerprint_uploaded_file|"
    r"load_stationarity_data|read_uploaded_bytes|"
    r"render_sarimax_data_input)\b|"
    r"(?:def\s+|\.)current_(?:fingerprint|name|sheet)\s*\("
)
MIGRATION_BRIDGE_PATTERN = re.compile(
    r"\b(?:fallback|wrapper|deprecated|compatibility|dual[- ]path|"
    r"feature[- ]flag)\b|兼容层|兼容入口|兼容参数|迁移回退|运行时回退|双读|双写",
    re.IGNORECASE,
)
MIGRATION_SURFACE_ROOTS = (
    PROJECT_ROOT / "htfa/data/economic_workbook",
    PROJECT_ROOT / "htfa/data/tabular",
    PROJECT_ROOT / "htfa/ui_shared/data_overview",
    PROJECT_ROOT / "htfa/app/state/shared_dataset.py",
    PROJECT_ROOT / "htfa/exploration/core/data_source.py",
    PROJECT_ROOT / "htfa/exploration/ui/shared_dataset_source.py",
    PROJECT_ROOT / "htfa/models/univariate/sarimax/ui/data_input.py",
    PROJECT_ROOT / "htfa/monitoring/uae",
    PROJECT_ROOT / "htfa/workspace",
)


def _python_files() -> tuple[Path, ...]:
    files = [PROJECT_ROOT / "app.py"]
    for root_name in ("htfa", "scripts", "tooling", "tests"):
        files.extend((PROJECT_ROOT / root_name).rglob("*.py"))
    return tuple(path for path in files if path.is_file())


def _is_historical_document(source_file: Path) -> bool:
    if not any(root in source_file.parents for root in HISTORICAL_DOCUMENT_ROOTS):
        return False
    header = "\n".join(
        source_file.read_text(encoding="utf-8", errors="ignore").splitlines()[:8]
    )
    return "**Archive:**" in header or "**History:**" in header


def _active_text_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for root in ACTIVE_TEXT_ROOTS:
        if root.is_file():
            files.append(root)
        else:
            files.extend(path for path in root.rglob("*") if path.is_file())
    return tuple(
        path
        for path in files
        if path.suffix.lower() in TEXT_SUFFIXES
        and path not in INTENTIONAL_CHECK_FILES
        and not _is_historical_document(path)
    )


def _imported_modules(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.level == 0
        ):
            modules.add(node.module)
    return modules


def test_legacy_directories_and_modules_are_absent() -> None:
    assert all(not path.exists() for path in LEGACY_DIRECTORIES)
    for source_file in _python_files():
        imported = _imported_modules(source_file)
        assert not any(
            module == "dashboard"
            or module.startswith("dashboard.")
            or module == "components"
            or module.startswith("components.")
            or module == "data_overview"
            or module.startswith("data_overview.")
            or module == "htfa.data.tabular_input"
            for module in imported
        ), source_file


def test_active_runtime_files_have_no_legacy_path_literals() -> None:
    for source_file in _active_text_files():
        text = source_file.read_text(encoding="utf-8", errors="ignore")
        assert not LEGACY_PATH_PATTERN.search(text), source_file
        assert not LEGACY_API_PATTERN.search(text), source_file


def test_migration_surface_has_no_compatibility_bridges() -> None:
    """迁移边界不得留下 alias、fallback、wrapper 或双路径实现。"""
    files: list[Path] = []
    for root in MIGRATION_SURFACE_ROOTS:
        if root.is_file():
            files.append(root)
        else:
            files.extend(root.rglob("*.py"))

    for source_file in files:
        source = source_file.read_text(encoding="utf-8", errors="ignore")
        assert not MIGRATION_BRIDGE_PATTERN.search(source), source_file


def test_uae_monitoring_uses_the_economic_workbook_protocol() -> None:
    """UAE 主题不得重新引入监测域内的第二套工作簿读取器。"""
    forbidden = re.compile(
        r"\bopen_uae_workbook\b|\bparse_target_sheet\b|pd\.read_excel\s*\("
    )
    for source_file in (PROJECT_ROOT / "htfa/monitoring/uae").rglob("*.py"):
        assert not forbidden.search(
            source_file.read_text(encoding="utf-8", errors="ignore")
        ), source_file


def test_dfm_preparation_uses_the_economic_workbook_protocol() -> None:
    """DFM 输入处理不得再自行打开工作簿。"""
    forbidden = re.compile(r"pd\.ExcelFile|pd\.read_excel\s*\(")
    for root in (
        PROJECT_ROOT / "htfa/models/dfm/prep",
        PROJECT_ROOT / "htfa/models/dfm/train",
    ):
        for source_file in root.rglob("*.py"):
            assert not forbidden.search(
                source_file.read_text(encoding="utf-8", errors="ignore")
            ), source_file


def test_industrial_monitoring_uses_the_economic_workbook_protocol() -> None:
    """工业监测不得保留默认文件回退或自己的 Excel 读取器。"""
    analysis_source = (
        PROJECT_ROOT / "htfa/monitoring/industrial/industrial_analysis.py"
    ).read_text(encoding="utf-8", errors="ignore")
    loader_source = (
        PROJECT_ROOT / "htfa/monitoring/industrial/utils/data_loader.py"
    ).read_text(encoding="utf-8", errors="ignore")
    assert "load_default_monitoring_data" not in analysis_source
    assert not re.search(r"pd\.ExcelFile|pd\.read_excel\s*\(", loader_source)
