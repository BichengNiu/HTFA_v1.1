"""Contracts for separating versioned code from local research material."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_data_refresh_code_is_versioned_outside_local_data() -> None:
    expected_scripts = (
        "scripts/data_sources/baker_hughes/update_baker_hughes_monthly.py",
        "scripts/data_sources/cbuae/update_cbuae_monthly.py",
        "scripts/data_sources/gfs/update_gfs.py",
    )

    assert all((PROJECT_ROOT / path).is_file() for path in expected_scripts)
    assert not list((PROJECT_ROOT / "data").glob("**/update_*.py"))


def test_local_data_and_binary_references_are_ignored() -> None:
    ignore_rules = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "/data/**" in ignore_rules
    assert "!/data/**/README.md" in ignore_rules
    assert "/references-local/**" in ignore_rules
    assert "!/references-local/README.md" in ignore_rules
    assert "*.db" in ignore_rules
    assert "/docs/**/*.pdf" in ignore_rules
