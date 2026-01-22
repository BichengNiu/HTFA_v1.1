"""
文本处理工具模块（共享）

提供统一的文本标准化功能，用于处理中文变量名、列名等
供prep和train模块共同使用
"""

import re
import unicodedata
import pandas as pd
from typing import Union, Optional


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


__all__ = [
    'normalize_text',
    'normalize_column_name'
]
