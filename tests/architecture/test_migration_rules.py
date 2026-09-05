"""Executable phase-A checks for the five-domain migration decisions."""

from __future__ import annotations

from pathlib import Path


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
