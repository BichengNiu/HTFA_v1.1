"""
UI后端服务模块

为UI层提供所有必需的业务逻辑接口，UI层不应包含任何业务逻辑，只负责显示
"""

import logging
from typing import Dict, Any, Optional, List
import pandas as pd

from dashboard.models.DFM.prep.modules.variable_transformer import VariableTransformer
from dashboard.models.DFM.utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


class UIBackendService:
    """UI后端服务 - 提供UI需要的所有业务逻辑"""

    @staticmethod
    def transform_variables(
        data: pd.DataFrame,
        transform_config: List[Dict[str, Any]],
        target_freq: str = 'W-FRI',
        var_frequency_map: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        执行变量转换

        这是UI层应该调用的唯一业务逻辑接口

        Args:
            data: 原始数据DataFrame
            transform_config: 转换配置列表，每项为：
                {
                    'variable': str,          # 变量名
                    'operations': List[str],  # 操作序列: ['log', 'diff_yoy'] 或 ['diff_1']
                }
            target_freq: 目标频率
            var_frequency_map: 变量频率映射（用于同比差分）

        Returns:
            {
                'status': 'success' | 'error',
                'message': str,
                'data': pd.DataFrame,                          # 转换后的数据
                'transform_details': Dict,                     # 转换详情
                'errors': List[str]                           # 转换过程中的错误
            }
        """
        try:
            logger.info("UI后端: 开始变量转换")
            logger.info(f"  输入数据形状: {data.shape}")
            logger.info(f"  转换配置数量: {len(transform_config)}")

            # 初始化转换器
            transformer = VariableTransformer(freq=target_freq)
            errors = []

            # 执行转换
            transformed_data = data.copy()
            transform_details = {}

            for config in transform_config:
                var_name = config.get('variable', '')
                operations = config.get('operations', [])

                if not var_name or var_name not in transformed_data.columns:
                    logger.warning(f"变量 '{var_name}' 不在数据中，跳过")
                    errors.append(f"变量 '{var_name}' 不在数据中")
                    continue

                try:
                    ops_str = ' -> '.join(operations) if operations else '不处理'
                    logger.debug(f"  转换: {var_name} <- {ops_str}")

                    # 提取单个变量的 Series
                    series = transformed_data[var_name].copy()

                    # 获取变量的原始频率（用于智能同比差分）
                    var_name_normalized = normalize_text(var_name)
                    original_freq = var_frequency_map.get(var_name_normalized) if var_frequency_map else None

                    # 执行转换
                    transformed_series = transformer.transform_variable(
                        series=series,
                        operations=operations,
                        original_freq=original_freq
                    )

                    # 更新 DataFrame
                    transformed_data[var_name] = transformed_series

                    # 记录转换详情（从 transformer 的公共方法获取）
                    transform_details_map = transformer.get_transform_details()
                    if var_name in transform_details_map:
                        detail = transform_details_map[var_name]
                        transform_details[var_name] = {
                            'operations': detail.get('operations', []),
                            'status': 'success'
                        }

                except Exception as e:
                    logger.error(f"变换变量 '{var_name}' 失败: {e}")
                    errors.append(f"变量 '{var_name}': {str(e)}")

            logger.info(f"转换完成: {len(transform_details)}个变量成功")

            return {
                'status': 'success',
                'message': f'成功转换 {len(transform_details)} 个变量',
                'data': transformed_data,
                'transform_details': transform_details,
                'errors': errors
            }

        except Exception as e:
            logger.error(f"UI后端服务失败: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': f'处理失败: {str(e)}',
                'data': None,
                'transform_details': {},
                'errors': [str(e)]
            }


__all__ = ['UIBackendService']
