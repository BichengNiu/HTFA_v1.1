"""
文本处理工具模块（共享）

提供统一的文本标准化功能，用于处理中文变量名、列名等
供prep和train模块共同使用
"""

import re
import unicodedata
import pandas as pd
from typing import Union


def normalize_text(text: Union[str, float, None], to_lower: bool = True) -> str:
    """
    标准化文本，移除特殊字符和空格

    此函数适用于中文和英文混合文本的标准化处理，
    主要用于变量名、列名的规范化以确保匹配一致性。

    处理内容：
    - Unicode NFKC规范化（统一全角/半角字符）
    - 去除前后空格
    - 去除冒号、逗号、括号等标点符号前后的空格
    - 压缩连续多个空格为单个空格
    - 可选的小写转换

    Args:
        text: 待标准化的文本，可以是字符串、浮点数或None
        to_lower: 是否转换为小写，默认True

    Returns:
        str: 标准化后的文本，如果输入为空则返回空字符串

    Examples:
        >>> normalize_text('  工业增加值  ')
        '工业增加值'
        >>> normalize_text('用电量: 电气机械  ')
        '用电量:电气机械'
        >>> normalize_text('GDP  Growth  Rate', to_lower=True)
        'gdp growth rate'
        >>> normalize_text(None)
        ''
    """
    if pd.isna(text) or text == '':
        return ''

    # 转换为字符串并标准化Unicode（NFKC规范化）
    # NFKC会将全角字符转换为半角，统一Unicode变体
    text = str(text)
    text = unicodedata.normalize('NFKC', text)

    # 移除前后空格
    text = text.strip()

    # 移除标点符号前后的空格
    # 处理常见的中文和英文标点符号
    punctuation_list = [':', '：', ',', '，', '(', ')', '（', '）', '[', ']',
                        '【', '】', '{', '}', '-', '—', '·', '.', '。']

    for punct in punctuation_list:
        # 移除标点前后的空格
        text = text.replace(f' {punct}', punct)
        text = text.replace(f'{punct} ', punct)

    # 压缩连续多个空格为单个空格
    text = re.sub(r'\s+', ' ', text)

    # 再次去除前后空格（防止标点处理后产生的空格）
    text = text.strip()

    # 根据参数决定是否转换为小写
    # 对于包含ASCII字符的文本进行小写转换
    if to_lower:
        if any(ord(char) < 128 for char in text):
            # 包含ASCII字符，可能有英文，进行小写转换
            text = text.lower()

    return text


def normalize_column_name(column_name: Union[str, float, None]) -> str:
    """
    标准化列名

    这是 normalize_text 的便利包装函数，专门用于列名标准化。
    默认转换为小写并去除空格。

    Args:
        column_name: 列名

    Returns:
        str: 标准化后的列名

    Examples:
        >>> normalize_column_name('  规模以上工业增加值  ')
        '规模以上工业增加值'
        >>> normalize_column_name('Total_Revenue')
        'total_revenue'
    """
    return normalize_text(column_name, to_lower=True)


def normalize_variable_name(variable_name: Union[str, float, None]) -> str:
    """
    标准化变量名以匹配var_industry_map中的键

    简化版标准化：NFKC规范化 + 去除首尾空格 + 英文转小写。
    供 decomp、train 等模块统一使用。

    Args:
        variable_name: 原始变量名

    Returns:
        str: 标准化后的变量名

    Examples:
        >>> normalize_variable_name('  GDP增速  ')
        'gdp增速'
        >>> normalize_variable_name('全角空格　test')
        '全角空格 test'
    """
    if pd.isna(variable_name) or variable_name == '':
        return ''

    text = str(variable_name)
    text = unicodedata.normalize('NFKC', text)
    text = text.strip()

    if any(ord(char) < 128 for char in text):
        text = text.lower()

    return text


def match_columns_case_insensitive(
    columns,
    candidates: list[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """按 NFKC+去空格+小写 规则匹配候选列名（大小写不敏感）。

    Args:
        columns: DataFrame 的实际列名集合
        candidates: 候选指标名列表

    Returns:
        (匹配到的实际列名列表, (候选名, 实际列名) 修正对列表)
    """
    column_mapping = {
        normalize_variable_name(col): col
        for col in columns
    }

    matched: list[str] = []
    mismatches: list[tuple[str, str]] = []
    for candidate in candidates:
        if candidate in columns:
            matched.append(candidate)
            continue
        actual = column_mapping.get(normalize_variable_name(candidate))
        if actual is not None:
            matched.append(actual)
            mismatches.append((candidate, actual))

    return matched, mismatches


__all__ = [
    'match_columns_case_insensitive',
    'normalize_text',
    'normalize_column_name',
    'normalize_variable_name',
]
