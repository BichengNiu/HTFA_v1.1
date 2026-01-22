"""
去趋势处理器模块

实现简单线性回归去趋势功能，用于DFM数据预处理流程。
通过对每个变量进行线性回归（y_t = α + β*t + ε），提取残差作为去趋势后的值。

作者: Claude Code
创建时间: 2025-11-13
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
import logging


class DetrendError(Exception):
    """去趋势处理基础异常类"""
    pass


class InsufficientDataError(DetrendError):
    """数据不足异常"""
    pass


class RegressionFailedError(DetrendError):
    """回归失败异常"""
    pass


class DetrendProcessor:
    """
    去趋势处理器

    使用简单线性回归方法对时间序列数据进行去趋势处理。
    对每个变量拟合线性趋势 y_t = α + β*t + ε，提取残差ε作为去趋势后的值。

    特性:
    - 对所有变量统一应用线性去趋势
    - 保留原始数据中的NaN值位置
    - 去趋势后产生的NaN值（如果有）也会保留
    - 数据不足或回归失败时抛出异常

    参数:
        min_valid_points: 进行回归所需的最小有效数据点数（默认3）
        logger: 日志记录器（可选）
    """

    def __init__(
        self,
        min_valid_points: int = 3,
        logger: Optional[logging.Logger] = None
    ):
        self.min_valid_points = min_valid_points
        self.logger = logger or logging.getLogger(__name__)

    def linear_detrend(
        self,
        series: pd.Series,
        return_stats: bool = False
    ) -> pd.Series:
        """
        对单个时间序列进行线性去趋势

        使用numpy.polyfit进行一阶多项式拟合，计算残差。

        参数:
            series: 输入时间序列
            return_stats: 是否返回统计信息（R²等）

        返回:
            pd.Series: 去趋势后的残差序列（保留原始索引和NaN位置）

        异常:
            InsufficientDataError: 有效数据点少于min_valid_points
            RegressionFailedError: 回归计算失败
        """
        variable_name = series.name if series.name else "未命名变量"

        # 检查有效数据点数量
        valid_mask = ~series.isna()
        n_valid = valid_mask.sum()

        if n_valid < self.min_valid_points:
            raise InsufficientDataError(
                f"变量 '{variable_name}' 有效数据点不足: "
                f"需要至少 {self.min_valid_points} 个，实际 {n_valid} 个"
            )

        try:
            # 创建时间索引（0, 1, 2, ...）
            time_index = np.arange(len(series))

            # 提取有效数据点
            valid_time = time_index[valid_mask]
            valid_values = series[valid_mask].values

            # 执行一阶多项式拟合（线性回归）
            # coeffs[0] = β (斜率), coeffs[1] = α (截距)
            coeffs = np.polyfit(valid_time, valid_values, deg=1)

            # 计算整个时间序列的拟合值（趋势）
            trend = np.polyval(coeffs, time_index)

            # 计算残差（去趋势后的值）
            residuals = series.values - trend

            # 创建结果Series，保留原始索引和NaN位置
            result = pd.Series(residuals, index=series.index, name=series.name)

            # 确保原始NaN位置保持为NaN
            result[~valid_mask] = np.nan

            self.logger.debug(
                f"变量 '{variable_name}' 去趋势完成: "
                f"斜率={coeffs[0]:.6f}, 截距={coeffs[1]:.6f}"
            )

            return result

        except np.linalg.LinAlgError as e:
            raise RegressionFailedError(
                f"变量 '{variable_name}' 线性回归失败: {str(e)}"
            )
        except Exception as e:
            raise RegressionFailedError(
                f"变量 '{variable_name}' 去趋势处理异常: {str(e)}"
            )

    def detrend_dataframe(
        self,
        df: pd.DataFrame,
        exclude_columns: Optional[list] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        对DataFrame的所有列进行线性去趋势

        参数:
            df: 输入DataFrame（索引为时间，列为变量）
            exclude_columns: 需要排除的列名列表（可选）

        返回:
            Tuple[pd.DataFrame, Dict]:
                - 去趋势后的DataFrame
                - 统计信息字典，包含：
                    - total_variables: 总变量数
                    - processed_variables: 成功处理的变量数
                    - excluded_variables: 排除的变量数
                    - failed_variables: 失败的变量列表（如果有）

        异常:
            DetrendError: 任何变量去趋势失败时抛出
        """
        if df.empty:
            self.logger.warning("输入DataFrame为空，跳过去趋势处理")
            return df.copy(), {
                'total_variables': 0,
                'processed_variables': 0,
                'excluded_variables': 0,
                'failed_variables': []
            }

        exclude_columns = exclude_columns or []
        total_variables = len(df.columns)
        excluded_variables = len(exclude_columns)

        self.logger.info(
            f"开始去趋势处理: 总变量数={total_variables}, "
            f"排除变量数={excluded_variables}"
        )

        # 创建结果DataFrame
        result_df = pd.DataFrame(index=df.index)
        processed_count = 0
        failed_variables = []

        # 逐列处理
        for col in df.columns:
            if col in exclude_columns:
                # 排除的列直接复制
                result_df[col] = df[col].copy()
                self.logger.debug(f"变量 '{col}' 已排除，保持原始值")
                continue

            try:
                # 执行去趋势
                detrended_series = self.linear_detrend(df[col])
                result_df[col] = detrended_series
                processed_count += 1

            except DetrendError as e:
                # 去趋势失败，记录错误并抛出异常
                error_msg = f"变量 '{col}' 去趋势失败: {str(e)}"
                self.logger.error(error_msg)
                failed_variables.append({'variable': col, 'error': str(e)})
                raise DetrendError(error_msg) from e

        # 生成统计信息
        stats = {
            'total_variables': total_variables,
            'processed_variables': processed_count,
            'excluded_variables': excluded_variables,
            'failed_variables': failed_variables
        }

        self.logger.info(
            f"去趋势处理完成: 成功处理 {processed_count} 个变量"
        )

        return result_df, stats

    def detrend_dict_of_dataframes(
        self,
        data_dict: Dict[str, pd.DataFrame],
        exclude_columns: Optional[list] = None
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any]]:
        """
        对字典中的多个DataFrame进行去趋势处理

        用于处理按频率分类的数据字典（如 {'daily': df1, 'weekly': df2, ...}）

        参数:
            data_dict: 数据字典，键为频率名称，值为DataFrame
            exclude_columns: 需要排除的列名列表（可选）

        返回:
            Tuple[Dict[str, pd.DataFrame], Dict]:
                - 去趋势后的数据字典
                - 汇总统计信息

        异常:
            DetrendError: 任何DataFrame去趋势失败时抛出
        """
        result_dict = {}
        total_stats = {
            'total_variables': 0,
            'processed_variables': 0,
            'excluded_variables': 0,
            'failed_variables': [],
            'by_frequency': {}
        }

        for freq_name, df in data_dict.items():
            if df is None or df.empty:
                self.logger.debug(f"频率 '{freq_name}' 的数据为空，跳过")
                result_dict[freq_name] = df
                continue

            self.logger.info(f"处理频率 '{freq_name}' 的数据...")

            try:
                detrended_df, stats = self.detrend_dataframe(df, exclude_columns)
                result_dict[freq_name] = detrended_df

                # 累加统计信息
                total_stats['total_variables'] += stats['total_variables']
                total_stats['processed_variables'] += stats['processed_variables']
                total_stats['excluded_variables'] += stats['excluded_variables']
                total_stats['failed_variables'].extend(stats['failed_variables'])
                total_stats['by_frequency'][freq_name] = stats

            except DetrendError as e:
                error_msg = f"频率 '{freq_name}' 的数据去趋势失败: {str(e)}"
                self.logger.error(error_msg)
                raise DetrendError(error_msg) from e

        return result_dict, total_stats
