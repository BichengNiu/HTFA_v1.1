from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from htfa.exploration.analysis import structural_break
from htfa.exploration.analysis.structural_break import (
    STRUCTURAL_BREAK_LAG_METHODS,
    STRUCTURAL_BREAK_MODELS,
    run_zivot_andrews_test,
)


def test_zivot_andrews_reports_break_timestamp_and_alpha_decision(
    monkeypatch,
):
    calls = {}

    class FakeZivotAndrews:
        def __init__(self, data, **kwargs):
            calls["data"] = data
            calls["kwargs"] = kwargs

        def fit(self):
            return SimpleNamespace(
                statistic=-5.1,
                pvalue=None,
                lags=2,
                nobs=57,
                cv_01=-5.34,
                cv_05=-4.80,
                cv_10=-4.58,
                break_index=3,
            )

    monkeypatch.setattr(
        structural_break,
        "ZivotAndrewsTest",
        FakeZivotAndrews,
    )
    series = pd.Series(
        np.arange(60.0),
        index=pd.date_range("2020-01-31", periods=60, freq="ME"),
        name="value",
    )

    result = run_zivot_andrews_test(
        series,
        alpha=0.05,
        model="both",
        lag_method="bic",
    ).iloc[0]

    assert calls["kwargs"]["model"] == "both"
    assert calls["kwargs"]["lag_method"] == "bic"
    assert result["临界值"] == -4.8
    assert result["判定"] == "拒绝原假设"
    assert result["结构突变点"] == pd.Timestamp("2020-04-30")


def test_structural_break_options_match_ts_package():
    assert set(STRUCTURAL_BREAK_MODELS) == {"intercept", "slope", "both"}
    assert set(STRUCTURAL_BREAK_LAG_METHODS) == {"tstat", "aic", "bic"}


def test_structural_break_rejects_unknown_model():
    with pytest.raises(ValueError, match="突变形式"):
        run_zivot_andrews_test(
            pd.Series(np.arange(40.0)),
            model="unknown",
        )


def test_real_zivot_andrews_runs_end_to_end():
    rng = np.random.default_rng(9)
    series = pd.Series(
        rng.normal(size=80),
        index=pd.date_range("2019-01-31", periods=80, freq="ME"),
        name="value",
    )

    result = run_zivot_andrews_test(series)

    assert result.loc[0, "统计量"] is not None
    assert result.loc[0, "结构突变点"] in series.index
