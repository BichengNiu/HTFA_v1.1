# -*- coding: utf-8 -*-
"""
训练结果导出器（合并版）

负责将TrainingResult导出为文件：
- 模型文件（.joblib）
- 元数据文件（.pkl）

经典DFM模型：所有变量平等参与因子提取，无目标变量概念
"""

import os
import tempfile
import pickle
from datetime import datetime
from typing import Dict, Optional, Any, Tuple
import numpy as np
import pandas as pd
import joblib
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.utils.file_io import read_data_file

logger = get_logger(__name__)


class TrainingResultExporter:
    """训练结果文件导出器（合并版）"""

    def export_all(
        self,
        result,  # TrainingResult
        config,  # TrainingConfig
        output_dir: Optional[str] = None,
        prepared_data: Optional[pd.DataFrame] = None
    ) -> Dict[str, str]:
        """
        导出所有结果文件

        Args:
            result: 训练结果
            config: 训练配置
            output_dir: 输出目录（None=创建临时目录）
            prepared_data: 预处理后的完整观测数据矩阵

        Returns:
            文件路径字典 {
                'final_model_joblib': 模型文件路径,
                'metadata': 元数据文件路径,
                'training_summary': 训练摘要文本文件路径
            }
        """
        logger.info("开始导出训练结果文件")

        # 创建输出目录
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix='dfm_results_')
            logger.info(f"使用临时目录: {output_dir}")
        else:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"使用指定目录: {output_dir}")

        # 生成时间戳
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 导出各个文件
        file_paths = {}

        # 导出模型文件
        model_path = os.path.join(output_dir, f'final_dfm_model_{timestamp}.joblib')
        self._export_model(result, model_path)
        file_paths['final_model_joblib'] = model_path
        logger.info(f"模型文件已导出: {os.path.basename(model_path)}")

        # 导出元数据文件
        metadata_path = os.path.join(output_dir, f'final_dfm_metadata_{timestamp}.pkl')
        self._export_metadata(result, config, metadata_path, timestamp, prepared_data)
        file_paths['metadata'] = metadata_path
        logger.info(f"元数据文件已导出: {os.path.basename(metadata_path)}")

        # 导出训练摘要文本文件
        summary_path = os.path.join(output_dir, f'training_summary_{timestamp}.txt')
        self._export_training_summary(result, config, summary_path, timestamp)
        file_paths['training_summary'] = summary_path
        logger.info(f"训练摘要已导出: {os.path.basename(summary_path)}")

        # 验证文件
        for file_type, path in file_paths.items():
            if path and os.path.exists(path):
                size = os.path.getsize(path)
                logger.debug(f"{file_type}: {path} ({size} bytes)")
            else:
                logger.warning(f"{file_type}: 文件不存在或导出失败")

        logger.info(f"文件导出完成,共 {len([p for p in file_paths.values() if p])} 个文件")
        return file_paths

    def _export_model(self, result, path: str) -> None:
        """导出模型文件"""
        if result.model_result is None:
            raise ValueError("训练结果中没有模型对象")

        joblib.dump(result.model_result, path, compress=3)

        if not os.path.exists(path):
            raise IOError(f"模型文件保存失败: {path}")

        file_size = os.path.getsize(path) / (1024 * 1024)
        logger.debug(f"模型文件大小: {file_size:.2f} MB")

    def _export_metadata(self, result, config, path: str, timestamp: str, prepared_data: Optional[pd.DataFrame] = None) -> None:
        """导出元数据文件"""
        metadata = self._build_metadata(result, config, timestamp, prepared_data)
        self._validate_metadata(metadata)

        with open(path, 'wb') as f:
            pickle.dump(metadata, f, protocol=pickle.HIGHEST_PROTOCOL)

        if not os.path.exists(path):
            raise IOError(f"元数据文件保存失败: {path}")

        file_size = os.path.getsize(path) / (1024 * 1024)
        logger.debug(f"元数据文件大小: {file_size:.2f} MB")

    def _export_training_summary(self, result, config, path: str, timestamp: str) -> None:
        """导出训练摘要文本文件"""
        from dashboard.models.DFM.train.export.training_summary import generate_training_summary

        try:
            summary_text = generate_training_summary(result, config, timestamp)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(summary_text)

            if not os.path.exists(path):
                raise IOError(f"训练摘要文件保存失败: {path}")

            file_size = os.path.getsize(path) / 1024
            logger.debug(f"训练摘要文件大小: {file_size:.2f} KB")

        except Exception as e:
            logger.error(f"导出训练摘要失败: {e}")
            raise IOError(f"无法导出训练摘要: {e}") from e

    # ========== 元数据构建方法 ==========

    def _build_metadata(self, result, config, timestamp: str, prepared_data: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """构建元数据字典（经典DFM版，无目标变量）"""
        logger.debug("开始构建元数据")

        metadata = {
            # 基本信息
            'timestamp': timestamp,
            'selected_variables': result.selected_variables,
            'best_variables': result.selected_variables,  # 兼容模型分析模块
            'N_variables': len(result.selected_variables),
            'initial_selected_indicators': getattr(config, 'selected_indicators', []),

            # 模型参数（兼容模型分析模块的best_params格式）
            'model_params': {
                'k_factors': int(result.k_factors),
                'variable_selection_method': config.variable_selection_method if config.enable_variable_selection else '全选',
                'algorithm': config.algorithm,
            },
            'best_params': {
                'k_factors': int(result.k_factors),
                'algorithm': config.algorithm,
            },

            # 日期
            'training_start_date': config.training_start,
            'train_end_date': config.train_end,
            'validation_start_date': config.validation_start,
            'validation_end_date': config.validation_end,
            # 观察期日期
            'observation_period_start': config.observation_start,
            'observation_period_end': config.observation_end,

            # 训练统计
            'total_runtime_seconds': float(result.training_time),
            'var_industry_map': config.industry_map,
        }

        # 评估指标（分期计算重构RMSE和MAE）
        if result.metrics is None:
            raise ValueError("训练结果缺少评估指标(metrics)，无法导出元数据")

        # 计算训练期指标
        is_rmse, is_mae = self._calculate_period_metrics(
            result, prepared_data, config.training_start, config.train_end
        )
        # 计算验证期指标
        oos_rmse, oos_mae = self._calculate_period_metrics(
            result, prepared_data, config.validation_start, config.validation_end
        )

        metadata.update({
            # 训练期指标 (in-sample)
            'is_rmse': is_rmse,
            'is_mae': is_mae,
            # 验证期指标 (out-of-sample)
            'oos_rmse': oos_rmse,
            'oos_mae': oos_mae,
            # 收敛信息
            'converged': result.metrics.converged,
            'iterations': result.metrics.iterations,
        })

        # 因子载荷DataFrame
        metadata['factor_loadings_df'] = self._extract_factor_loadings(result, config)

        # 因子序列DataFrame
        if result.model_result and hasattr(result.model_result, 'factors'):
            factors_data = result.model_result.factors
            if isinstance(factors_data, np.ndarray):
                if factors_data.ndim == 2:
                    factors_transposed = factors_data.T
                    factor_names = [f'Factor_{i+1}' for i in range(factors_transposed.shape[1])]

                    # 尝试从数据文件获取日期索引
                    date_index = None
                    if config.data_path:
                        try:
                            data = self._read_data_file(config.data_path)
                            if data is not None:
                                if isinstance(data.index, pd.DatetimeIndex):
                                    date_index = data.index
                                else:
                                    date_index = pd.to_datetime(data.index)

                                # 确保日期索引按升序排列（与训练时数据顺序一致）
                                if not date_index.is_monotonic_increasing:
                                    date_index = date_index.sort_values()

                                # 确保长度匹配（严格校验）
                                if len(date_index) != factors_transposed.shape[0]:
                                    raise ValueError(
                                        f"日期索引长度({len(date_index)})与因子数据长度({factors_transposed.shape[0]})不匹配。"
                                        f"因子必须覆盖完整时间范围。"
                                    )
                        except ValueError:
                            # 长度不匹配是严重错误，必须重新抛出
                            raise
                        except Exception as e:
                            logger.warning(f"获取因子序列日期索引失败: {e}")

                    metadata['factor_series'] = pd.DataFrame(
                        factors_transposed,
                        columns=factor_names,
                        index=date_index
                    )
                    if date_index is not None:
                        logger.info(f"因子序列保存成功，日期范围: {date_index.min()} 到 {date_index.max()}")
                else:
                    metadata['factor_series'] = None
            else:
                metadata['factor_series'] = factors_data.copy() if isinstance(factors_data, pd.DataFrame) else None
        else:
            metadata['factor_series'] = None

        # 保存卡尔曼增益历史
        if result.model_result and hasattr(result.model_result, 'kalman_gains_history'):
            kalman_gains = result.model_result.kalman_gains_history
            if kalman_gains is not None:
                metadata['kalman_gains_history'] = kalman_gains
                logger.info(f"保存卡尔曼增益历史: {len(kalman_gains)} 个时间步")
            else:
                metadata['kalman_gains_history'] = None
        else:
            metadata['kalman_gains_history'] = None

        # 保存先验因子状态
        if result.model_result and hasattr(result.model_result, 'factor_states_predicted'):
            factor_states_pred = result.model_result.factor_states_predicted
            if factor_states_pred is not None:
                metadata['factor_states_predicted'] = factor_states_pred
                logger.info(f"保存先验因子状态: 形状={factor_states_pred.shape}")
            else:
                metadata['factor_states_predicted'] = None
        else:
            metadata['factor_states_predicted'] = None

        # PCA结果DataFrame
        if result.pca_analysis:
            metadata['pca_results_df'] = self._convert_pca_to_dataframe(result.pca_analysis, result.k_factors)
        else:
            metadata['pca_results_df'] = None

        # 保存完整观测数据矩阵
        if prepared_data is not None:
            # 确保 prepared_data 按时间升序排列
            if not prepared_data.index.is_monotonic_increasing:
                prepared_data = prepared_data.sort_index()
            metadata['prepared_data'] = prepared_data
            logger.info(f"保存完整观测数据: 形状={prepared_data.shape}")

            # 计算并保存训练期均值（用于重构效果图还原原始尺度）
            try:
                train_start_dt = pd.to_datetime(config.training_start)
                train_end_dt = pd.to_datetime(config.train_end)
                train_mask = (prepared_data.index >= train_start_dt) & (prepared_data.index <= train_end_dt)
                train_data = prepared_data[train_mask]

                if len(train_data) > 0:
                    # 获取模型使用的变量列表
                    if (hasattr(result, 'model_result') and
                        result.model_result is not None and
                        hasattr(result.model_result, 'variable_names') and
                        result.model_result.variable_names is not None):
                        var_names = list(result.model_result.variable_names)
                    else:
                        var_names = list(result.selected_variables)

                    # 筛选出在 prepared_data 中存在的变量
                    available_vars = [v for v in var_names if v in train_data.columns]
                    training_means = train_data[available_vars].mean().values

                    metadata['training_means'] = training_means
                    metadata['training_variable_names'] = available_vars
                    logger.info(f"保存训练期均值: {len(available_vars)} 个变量")
                else:
                    metadata['training_means'] = None
                    metadata['training_variable_names'] = None
                    logger.warning("训练期数据为空，无法计算训练期均值")
            except Exception as e:
                logger.warning(f"计算训练期均值失败: {e}")
                metadata['training_means'] = None
                metadata['training_variable_names'] = None
        else:
            metadata['prepared_data'] = None
            metadata['training_means'] = None
            metadata['training_variable_names'] = None

        # 计算并保存重构对比表（原始尺度）
        if prepared_data is not None and result.model_result is not None:
            try:
                H = result.model_result.H  # (n_vars, k_factors)
                factors = result.model_result.factors_smooth.T  # (n_time, k_factors)

                # 关键修复：使用模型的变量名列表（与H矩阵行顺序一致）
                if (hasattr(result.model_result, 'variable_names') and
                    result.model_result.variable_names is not None):
                    model_var_names = list(result.model_result.variable_names)
                else:
                    model_var_names = list(result.selected_variables)

                # 筛选出在 prepared_data 中存在的变量，保持原始顺序
                available_vars = [v for v in model_var_names if v in prepared_data.columns]
                # 获取这些变量在模型变量列表中的索引（用于从H矩阵中提取对应行）
                var_indices = [model_var_names.index(v) for v in available_vars]

                if len(available_vars) > 0 and H is not None and factors is not None:
                    # 只提取可用变量对应的H矩阵行
                    H_subset = H[var_indices, :]  # (n_available_vars, k_factors)

                    # 计算重构值（去均值尺度）
                    reconstructed_centered = factors @ H_subset.T  # (n_time, n_available_vars)

                    # 获取原始值
                    original_data = prepared_data[available_vars]

                    # 使用训练期均值还原（与training_means保持一致）
                    training_means = metadata.get('training_means')
                    training_var_names = metadata.get('training_variable_names')

                    if training_means is not None and training_var_names is not None:
                        # 为每个可用变量获取对应的训练期均值
                        var_means = []
                        for var in available_vars:
                            if var in training_var_names:
                                idx = list(training_var_names).index(var)
                                var_means.append(training_means[idx])
                            else:
                                # 如果变量不在训练期均值中，使用全期均值
                                var_means.append(original_data[var].mean())
                        var_means = np.array(var_means)
                    else:
                        # 回退到全期均值
                        var_means = original_data.mean().values

                    # 还原到原始尺度
                    reconstructed_original = reconstructed_centered + var_means

                    # 构建重构对比表
                    reconstruction_comparison = pd.DataFrame(
                        index=prepared_data.index,
                        columns=pd.MultiIndex.from_product([available_vars, ['原始值', '重构值']])
                    )
                    for i, var in enumerate(available_vars):
                        reconstruction_comparison[(var, '原始值')] = original_data[var].values
                        reconstruction_comparison[(var, '重构值')] = reconstructed_original[:, i]

                    metadata['reconstruction_comparison'] = reconstruction_comparison
                    logger.info(f"保存重构对比表: {len(available_vars)} 个变量")
                else:
                    metadata['reconstruction_comparison'] = None
                    logger.warning("无法计算重构对比表：缺少必要数据")
            except Exception as e:
                logger.warning(f"计算重构对比表失败: {e}")
                metadata['reconstruction_comparison'] = None
        else:
            metadata['reconstruction_comparison'] = None

        logger.info(f"元数据构建完成,包含 {len(metadata)} 个字段")
        return metadata

    def _validate_metadata(self, metadata: Dict) -> None:
        """验证元数据包含所有必需字段"""
        required_fields = [
            'timestamp', 'selected_variables',
            'model_params', 'train_end_date', 'validation_end_date',
        ]

        missing_fields = [f for f in required_fields if f not in metadata]

        if missing_fields:
            raise ValueError(f"元数据缺少必需字段: {missing_fields}")

        logger.debug(f"元数据验证通过,包含 {len(metadata)} 个字段")

    def _calculate_period_metrics(
        self,
        result,
        prepared_data: Optional[pd.DataFrame],
        period_start: str,
        period_end: str
    ) -> Tuple[float, float]:
        """计算指定时期的重构 RMSE 和 MAE"""
        if prepared_data is None or result.model_result is None:
            return np.inf, np.inf
        if result.model_result.H is None or result.model_result.factors_smooth is None:
            return np.inf, np.inf

        try:
            # 获取模型使用的变量列表
            if hasattr(result.model_result, 'variable_names') and result.model_result.variable_names is not None:
                selected_vars = result.model_result.variable_names
            else:
                selected_vars = result.selected_variables

            # 筛选出模型使用的变量
            available_vars = [v for v in selected_vars if v in prepared_data.columns]
            if len(available_vars) == 0:
                logger.warning("prepared_data 中没有模型使用的变量")
                return np.inf, np.inf

            filtered_data = prepared_data[available_vars]

            start_dt = pd.to_datetime(period_start)
            end_dt = pd.to_datetime(period_end)
            period_mask = (filtered_data.index >= start_dt) & (filtered_data.index <= end_dt)
            period_data = filtered_data[period_mask]

            if len(period_data) == 0:
                logger.warning(f"时期 {period_start} ~ {period_end} 无数据")
                return np.inf, np.inf

            full_index = filtered_data.index
            period_indices = [i for i, idx in enumerate(full_index) if start_dt <= idx <= end_dt]

            H = result.model_result.H
            factors = result.model_result.factors_smooth.T
            period_factors = factors[period_indices, :]
            reconstructed = period_factors @ H.T

            obs_values = period_data.values
            obs_mean = np.nanmean(obs_values, axis=0)
            obs_centered = obs_values - obs_mean

            min_time = min(obs_centered.shape[0], reconstructed.shape[0])
            obs_centered = obs_centered[:min_time, :]
            reconstructed = reconstructed[:min_time, :]

            residuals = obs_centered - reconstructed
            rmse = float(np.sqrt(np.nanmean(residuals ** 2)))
            mae = float(np.nanmean(np.abs(residuals)))
            return rmse, mae

        except Exception as e:
            logger.warning(f"计算时期 {period_start}~{period_end} 指标失败: {e}")
            return np.inf, np.inf

    # ========== 工具方法 ==========

    def _read_data_file(self, file_path: str) -> pd.DataFrame:
        """根据文件扩展名读取数据文件"""
        return read_data_file(file_path, parse_dates=False, check_exists=False)

    def _extract_factor_loadings(self, result, config=None) -> pd.DataFrame:
        """提取因子载荷矩阵（H矩阵）"""
        try:
            if not result.model_result:
                return pd.DataFrame()

            H = result.model_result.H

            if H is None:
                return pd.DataFrame()

            if not isinstance(H, np.ndarray):
                raise TypeError(f"H矩阵类型错误: 期望np.ndarray，实际{type(H).__name__}")

            if not hasattr(result, 'k_factors') or result.k_factors is None:
                raise ValueError("result对象缺少k_factors属性")
            if result.k_factors <= 0:
                raise ValueError(f"k_factors值无效: {result.k_factors}")

            k_factors = result.k_factors

            if k_factors > H.shape[1]:
                raise ValueError(
                    f"k_factors({k_factors})大于H矩阵列数({H.shape[1]})"
                )

            # 只取前k_factors列
            H_trimmed = H[:, :k_factors]

            factor_names = [f'Factor_{i+1}' for i in range(k_factors)]

            # 使用model_result中保存的variable_names
            if (hasattr(result, 'model_result') and
                result.model_result is not None and
                hasattr(result.model_result, 'variable_names') and
                result.model_result.variable_names is not None):
                var_names = result.model_result.variable_names
            else:
                var_names = result.selected_variables

            # 检查变量名列表长度与H的行数是否匹配
            if len(var_names) != H_trimmed.shape[0]:
                logger.warning(
                    f"变量名数量({len(var_names)})与H矩阵行数({H_trimmed.shape[0]})不匹配"
                )
                var_names = [f'Var_{i+1}' for i in range(H_trimmed.shape[0])]

            return pd.DataFrame(H_trimmed, columns=factor_names, index=var_names)

        except Exception as e:
            logger.error(f"提取因子载荷失败: {e}")
            return pd.DataFrame()

    def _convert_pca_to_dataframe(self, pca_analysis: Dict, n_components: int) -> pd.DataFrame:
        """将PCA分析结果转换为DataFrame格式"""
        try:
            if not pca_analysis:
                return pd.DataFrame()

            explained_variance = pca_analysis.get('explained_variance', [])
            cumsum_variance = pca_analysis.get('cumsum_variance', [])
            eigenvalues = pca_analysis.get('eigenvalues', [])

            if explained_variance is None or (hasattr(explained_variance, '__len__') and len(explained_variance) == 0):
                logger.warning("PCA分析结果缺少explained_variance数据")
                return pd.DataFrame()

            explained_variance_ratio_pct = [v * 100 for v in explained_variance[:n_components]]

            if cumsum_variance is not None and len(cumsum_variance) >= n_components:
                cumulative_explained_variance_pct = [v * 100 for v in cumsum_variance[:n_components]]
            else:
                cumulative_explained_variance_pct = np.cumsum(explained_variance_ratio_pct).tolist()

            if eigenvalues is not None and len(eigenvalues) >= n_components:
                eigenvalues_list = list(eigenvalues[:n_components])
            else:
                eigenvalues_list = [0.0] * n_components

            pca_results_df = pd.DataFrame({
                '主成分 (PC)': [f'PC{i+1}' for i in range(n_components)],
                '解释方差 (%)': explained_variance_ratio_pct,
                '累计解释方差 (%)': cumulative_explained_variance_pct,
                '特征值 (Eigenvalue)': eigenvalues_list
            })

            logger.debug(f"PCA结果转换完成，包含 {len(pca_results_df)} 个主成分")
            return pca_results_df

        except Exception as e:
            logger.error(f"转换PCA结果为DataFrame失败: {e}")
            return pd.DataFrame()


__all__ = ['TrainingResultExporter']
