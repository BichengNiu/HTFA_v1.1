import json
from pathlib import Path

import Ts

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ts_import_resolves_to_environment_package():
    package_root = Path(Ts.__file__).resolve().parent
    assert package_root.parent.name == "site-packages"


def test_installed_ts_exposes_htfa_interfaces():
    from Ts import TimeSeriesSummary, difference
    from Ts.TsPlots import plot_acf, plot_pacf, plot_series
    from Ts.TsTests import (
        ADFTest,
        KPSSTest,
        PhillipsPerronTest,
        ZivotAndrewsTest,
    )

    assert all(
        callable(item)
        for item in (
            TimeSeriesSummary,
            difference,
            plot_acf,
            plot_pacf,
            plot_series,
            ADFTest,
            KPSSTest,
            PhillipsPerronTest,
            ZivotAndrewsTest,
        )
    )


def test_requirements_do_not_install_ts_from_git():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "BichengNiu/Ts" not in requirements
    assert "git+" not in requirements


def test_runtime_metadata_matches_documented_commit():
    metadata = json.loads(
        (PROJECT_ROOT / "scripts" / "ts_runtime.json").read_text(encoding="utf-8")
    )
    documentation = (PROJECT_ROOT / "docs" / "ts-runtime.md").read_text(
        encoding="utf-8"
    )

    assert metadata == {
        "repository": "https://github.com/BichengNiu/Ts",
        "branch": "main",
        "commit": "bec57a2610b38be3a8f78071d7e03850b53ca25e",
    }
    assert metadata["commit"] in documentation
