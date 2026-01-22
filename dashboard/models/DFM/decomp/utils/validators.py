# -*- coding: utf-8 -*-
"""
数据验证器

提供各种数据验证功能，确保影响分析计算的数据质量和格式正确性。
"""

import numpy as np
import pandas as pd
from typing import Any, Optional, Tuple, List, Union
from datetime import datetime

from .exceptions import ValidationError, DataFormatError


def validate_model_data(model: Any, metadata: Any) -> Tuple[bool, List[str]]:
    """
    验证模型数据的完整性和兼容性

    Args:
        model: DFM模型对象
        metadata: 模型元数据字典

    Returns:
        Tuple[bool, List[str]]: (是否有效, 错误信息列表)
    """
    errors = []

    try:
        # 验证模型对象
        if model is None:
            errors.append("模型对象为空")
        elif not hasattr(model, '__dict__'):
            errors.append("模型对象格式无效")
        else:
            # 检查必要的属性
            required_attrs = ['factors', 'H', 'A', 'Q', 'R']
            for attr in required_attrs:
                if not hasattr(model, attr):
                    errors.append(f"模型缺少必要属性: {attr}")
                else:
                    value = getattr(model, attr)
                    if not isinstance(value, np.ndarray):
                        errors.append(f"属性 {attr} 不是numpy数组")
                    elif value.size == 0:
                        errors.append(f"属性 {attr} 为空数组")

        # 验证元数据
        if metadata is None:
            errors.append("元数据为空")
        elif not isinstance(metadata, dict):
            errors.append("元数据不是字典格式")
        else:
            # 检查必要的元数据键
            required_keys = ['complete_aligned_table', 'factor_loadings_df', 'target_variable']
            for key in required_keys:
                if key not in metadata:
                    errors.append(f"元数据缺少必要键: {key}")

        # 检查nowcast数据
        if 'complete_aligned_table' in metadata:
            nowcast_data = metadata['complete_aligned_table']
            if not isinstance(nowcast_data, (pd.DataFrame, pd.Series)):
                errors.append("nowcast数据格式无效")
            elif isinstance(nowcast_data, pd.DataFrame):
                if 'Nowcast (Original Scale)' not in nowcast_data.columns:
                    errors.append("nowcast数据中缺少目标列")
                elif nowcast_data.empty:
                    errors.append("nowcast数据为空")

        return len(errors) == 0, errors

    except Exception as e:
        return False, [f"验证过程发生异常: {str(e)}"]