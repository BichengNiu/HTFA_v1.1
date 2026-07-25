import pandas as pd

from dashboard.preview.core.calculation_rules import (
    group_indicators_by_calculation,
    uses_difference_calculation,
)


def test_uses_difference_calculation_matches_summary_rule():
    assert uses_difference_calculation('%', '同比增速') is True
    assert uses_difference_calculation('%', '环比增速') is True
    assert uses_difference_calculation('%', '开工率') is False
    assert uses_difference_calculation('百万阿联酋迪拉姆', '金额') is False


def test_group_indicators_by_calculation_uses_current_summary_rows():
    summary = pd.DataFrame(
        [
            {
                '季度指标名称': '阿联酋GDP现价',
                '单位': '百万阿联酋迪拉姆',
                '类型': '金额',
            },
            {
                '季度指标名称': '阿联酋GDP不变价：当季同比',
                '单位': '%',
                '类型': '同比增速',
            },
            {
                '季度指标名称': '阿联酋GDP不变价：当季环比',
                '单位': '%',
                '类型': '环比增速',
            },
        ]
    )

    growth, difference = group_indicators_by_calculation(summary)

    assert growth == ['阿联酋GDP现价']
    assert difference == [
        '阿联酋GDP不变价：当季同比',
        '阿联酋GDP不变价：当季环比',
    ]


def test_group_indicators_by_calculation_handles_missing_metadata():
    summary = pd.DataFrame([{'季度指标名称': '阿联酋GDP现价'}])

    assert group_indicators_by_calculation(summary) == ([], [])
