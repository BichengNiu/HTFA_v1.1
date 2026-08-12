from pathlib import Path

import Ts


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
