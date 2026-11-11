"""经济工作簿摘要导出用例。"""
import pandas as pd
from htfa.processing.economic_workbook.calculation_rules import group_indicators_by_calculation
from htfa.data.economic_workbook.export import serialize_summary_workbook

def build_summary_workbook(summary_table: pd.DataFrame) -> bytes:
    """构建口径说明，并交由数据层序列化工作簿。"""
    growth_indicators, difference_indicators = group_indicators_by_calculation(
        summary_table
    )
    note_table = pd.DataFrame(
        [
            {
                '计算方式': '按增速计算',
                '公式': '（本期值 - 对比期值）/ 对比期值',
                '适用指标': '\n'.join(growth_indicators) if growth_indicators else '无',
                '说明': '计算结果按百分比理解。',
            },
            {
                '计算方式': '按减差形式计算',
                '公式': '本期值 - 对比期值',
                '适用指标': (
                    '\n'.join(difference_indicators)
                    if difference_indicators else '无'
                ),
                '说明': '单位为“%”的指标，计算结果按百分点理解。',
            },
        ]
    )

    return serialize_summary_workbook(summary_table, note_table)
