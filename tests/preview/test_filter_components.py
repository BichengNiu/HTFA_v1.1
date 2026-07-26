import pandas as pd

from dashboard.preview.shared.components import (
    _filter_by_type,
    _get_industry_indicators,
)


def test_industry_filter_uses_indicator_dictionary_not_shared_source():
    indicators = ["非石油同比", "非石油金额", "金融同比"]
    df = pd.DataFrame(columns=indicators)
    industry_map = {
        "非石油同比": "非石油",
        "非石油金额": "非石油",
        "金融同比": "金融保险",
    }
    type_map = {
        "非石油同比": "同比增速",
        "非石油金额": "金额",
        "金融同比": "同比增速",
    }

    industry_indicators = _get_industry_indicators("非石油", df, industry_map)
    filtered = _filter_by_type(industry_indicators, "同比增速", type_map)

    assert industry_indicators == ["非石油同比", "非石油金额"]
    assert filtered == ["非石油同比"]


def test_all_industries_returns_all_columns():
    df = pd.DataFrame(columns=["非石油同比", "金融同比"])

    assert _get_industry_indicators("全部", df, {}) == ["非石油同比", "金融同比"]
