# -*- coding: utf-8 -*-
"""
训练结果导出器（合并版）

负责将TrainingResult导出为文件：
- 模型文件（.joblib）
- 元数据文件（.pkl）

整合了原metadata_builder和utils的功能
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
            prepared_data: 预处理后的完整观测数据矩阵（用于影响分解）

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

        # 导出模型文件（不捕获异常，失败时直接抛出）
        model_path = os.path.join(output_dir, f'final_dfm_model_{timestamp}.joblib')
        self._export_model(result, model_path)
        file_paths['final_model_joblib'] = model_path
        logger.info(f"模型文件已导出: {os.path.basename(model_path)}")

        # 导出元数据文件（不捕获异常，失败时直接抛出）
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
        """构建元数据字典（与results模块格式一致）"""
        logger.debug("开始构建元数据")

        # 计算目标变量统计参数
        target_mean, target_std = self._calculate_target_statistics(config)

        metadata = {
            # 基本信息
            'timestamp': timestamp,
            'target_variable': config.target_variable,
            'best_variables': result.selected_variables,
            'N_variables': len(result.selected_variables),  # 显式保存变量数N
            'initial_selected_indicators': getattr(config, 'selected_indicators', []),  # 保存原始选择的指标列表

            # 模型参数
            'best_params': {
                'k_factors': int(result.k_factors),  # 转换为Python int，避免numpy类型问题
                'variable_selection_method': config.variable_selection_method if config.enable_variable_selection else '全选',
                'tuning_objective': 'RMSE' if config.enable_variable_selection else 'N/A',
                'algorithm': config.algorithm,  # 算法类型: 'classical' 或 'deep_learning'
            },

            # 日期（不使用默认值，字段缺失时抛出AttributeError）
            'training_start_date': self._calculate_training_start(config),
            'train_end_date': config.train_end,
            'validation_start_date': self._calculate_validation_start(config),
            'validation_end_date': config.validation_end,

            # 标准化参数
            'target_mean_original': target_mean,
            'target_std_original': target_std,

            # 训练统计
            'total_runtime_seconds': float(result.training_time),
            'var_industry_map': config.industry_map,
        }

        # 评估指标（使用results模块需要的字段名）
        # 不使用if检查，直接访问，字段缺失时抛出异常
        if result.metrics is None:
            raise ValueError("训练结果缺少评估指标(metrics)，无法导出元数据")

        metadata.update({
            'is_win_rate': float(result.metrics.is_win_rate),
            'oos_win_rate': float(result.metrics.oos_win_rate),
            'is_rmse': float(result.metrics.is_rmse),
            'oos_rmse': float(result.metrics.oos_rmse),
            'is_mae': float(result.metrics.is_mae),
            'oos_mae': float(result.metrics.oos_mae),
        })

        # 观察期指标（如果存在）
        if result.metrics.obs_rmse != np.inf:
            metadata.update({
                'obs_win_rate': float(result.metrics.obs_win_rate),
                'obs_rmse': float(result.metrics.obs_rmse),
                'obs_mae': float(result.metrics.obs_mae),
            })
            logger.info("观察期指标已添加到元数据")

        # 因子载荷DataFrame（预测变量）
        metadata['factor_loadings_df'] = self._extract_factor_loadings(result, config)

        # 目标变量的因子载荷（用于新闻分解分析）
        if not result.model_result or not hasattr(result.model_result, 'target_factor_loading'):
            raise ValueError("模型结果缺少target_factor_loading属性")
        target_loading = result.model_result.target_factor_loading
        if target_loading is None:
            raise ValueError("目标变量因子载荷为None，无法导出元数据")
        metadata['target_factor_loading'] = target_loading
        logger.info(f"保存目标变量因子载荷: 形状={target_loading.shape}")

        # 因子序列DataFrame (需要转置：因子应该是列，时间是行)
        if result.model_result and hasattr(result.model_result, 'factors'):
            factors_data = result.model_result.factors
            if isinstance(factors_data, np.ndarray):
                # factors_data 的形状是 (n_factors, n_timesteps)
                # 需要转置为 (n_timesteps, n_factors) 以便 DataFrame 中时间是行，因子是列
                if factors_data.ndim == 2:
                    factors_transposed = factors_data.T
                    factor_names = [f'Factor_{i+1}' for i in range(factors_transposed.shape[1])]

                    # 尝试从数据文件获取日期索引
                    date_index = None
                    if not config.data_path:
                        raise ValueError("配置中缺少data_path字段")
                    try:
                        data = self._read_data_file(config.data_path)
                        if data is None:
                            raise ValueError(f"无法读取数据文件: {config.data_path}")
                        if isinstance(data.index, pd.DatetimeIndex):
                            date_index = data.index
                        else:
                            date_index = pd.to_datetime(data.index)

                        # 确保长度匹配
                        if len(date_index) != factors_transposed.shape[0]:
                            raise ValueError(
                                f"日期索引长度({len(date_index)})与因子数据长度({factors_transposed.shape[0]})不匹配，"
                                "请检查训练数据和模型是否一致"
                            )
                    except ValueError:
                        raise  # 重新抛出长度不匹配错误
                    except Exception as e:
                        raise ValueError(f"获取因子序列日期索引失败: {e}") from e

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

        # 保存卡尔曼增益历史（用于新闻分解分析）
        # 注意：早期验证已在kalman.py的filter()方法中完成
        if not result.model_result or not hasattr(result.model_result, 'kalman_gains_history'):
            raise ValueError("内部错误：model_result缺少kalman_gains_history属性")
        kalman_gains = result.model_result.kalman_gains_history
        if kalman_gains is None:
            raise ValueError("内部错误：kalman_gains_history为None（应在滤波阶段验证）")
        metadata['kalman_gains_history'] = kalman_gains
        logger.info(f"保存卡尔曼增益历史: {len(kalman_gains)} 个时间步")

        # 保存先验因子状态（用于新闻分解的expected_value计算）
        # 此字段为影响分解必需，与kalman_gains_history一样使用严格验证
        if not result.model_result or not hasattr(result.model_result, 'factor_states_predicted'):
            raise ValueError("内部错误：model_result缺少factor_states_predicted属性")
        factor_states_pred = result.model_result.factor_states_predicted
        if factor_states_pred is None:
            raise ValueError("内部错误：factor_states_predicted为None（应在训练阶段生成）")
        if not isinstance(factor_states_pred, np.ndarray):
            raise TypeError(f"内部错误：factor_states_predicted类型错误，应为ndarray，实际为{type(factor_states_pred)}")
        if len(factor_states_pred.shape) != 2:
            raise ValueError(f"内部错误：factor_states_predicted应为2维数组，实际为{len(factor_states_pred.shape)}维")
        if factor_states_pred.shape[1] != result.k_factors:
            raise ValueError(f"内部错误：factor_states_predicted因子数({factor_states_pred.shape[1]})与k_factors({result.k_factors})不一致")
        metadata['factor_states_predicted'] = factor_states_pred
        logger.info(f"保存先验因子状态: 形状={factor_states_pred.shape}")

        # PCA结果DataFrame
        if result.pca_analysis:
            metadata['pca_results_df'] = self._convert_pca_to_dataframe(result.pca_analysis, result.k_factors)
        else:
            metadata['pca_results_df'] = None

        # 对齐表格（核心数据）
        metadata['complete_aligned_table'] = self._generate_aligned_table(result, config, metadata)

        # 观察期日期
        # DDFM模型：validation_start~validation_end就是观察期（无验证期）
        # 经典DFM：观察期是validation_end之后的数据
        is_ddfm = (getattr(config, 'algorithm', 'classical') == 'deep_learning')

        if is_ddfm:
            # DDFM模型使用observation_start和observation_end作为观察期
            metadata['observation_period_start'] = config.observation_start
            metadata['observation_period_end'] = config.observation_end
            logger.info(f"[DDFM] 观察期时间段: {config.observation_start} 至 {config.observation_end}")
        else:
            # 经典DFM：基于对齐表格计算观察期
            observation_period_start, observation_period_end = self._calculate_observation_period(
                config.validation_end,
                metadata['complete_aligned_table']
            )
            if observation_period_start and observation_period_end:
                metadata['observation_period_start'] = observation_period_start
                metadata['observation_period_end'] = observation_period_end
                logger.info(f"观察期时间段: {observation_period_start} 至 {observation_period_end}")

        # 保存完整观测数据矩阵（用于影响分解的数据发布提取）
        if prepared_data is not None:
            metadata['prepared_data'] = prepared_data
            logger.info(f"保存完整观测数据: 形状={prepared_data.shape}, 时间范围={prepared_data.index[0]}至{prepared_data.index[-1]}")
        else:
            metadata['prepared_data'] = None
            logger.debug("未提供prepared_data，影响分解功能可能受限")

        logger.info(f"元数据构建完成,包含 {len(metadata)} 个字段")
        return metadata

    def _calculate_target_statistics(self, config) -> tuple[float, float]:
        """计算目标变量的均值和标准差"""
        try:
            if not hasattr(config, 'data_path') or not config.data_path:
                return 0.0, 1.0

            # 读取数据文件
            data = self._read_data_file(config.data_path)

            if config.target_variable not in data.columns:
                logger.warning(f"目标变量 {config.target_variable} 不在数据中")
                return 0.0, 1.0

            target_series = data[config.target_variable].dropna()
            if len(target_series) == 0:
                return 0.0, 1.0

            target_mean = float(target_series.mean())
            target_std = float(target_series.std())

            logger.debug(f"目标变量统计: mean={target_mean:.4f}, std={target_std:.4f}")
            return target_mean, target_std

        except Exception as e:
            logger.error(f"计算目标变量统计参数失败: {e}")
            raise ValueError(f"无法计算目标变量统计参数: {e}") from e

    def _calculate_training_start(self, config) -> str:
        """计算训练开始日期（不使用默认值，字段缺失时抛出异常）"""
        # 直接访问属性，不使用has attr检查
        if not config.training_start:
            raise ValueError("配置中缺少training_start字段")
        return config.training_start

    def _calculate_validation_start(self, config) -> str:
        """计算验证开始日期（不使用默认值，字段缺失时抛出异常）"""
        # 直接访问属性，不使用hasattr检查
        if not config.validation_start:
            raise ValueError("配置中缺少validation_start字段")
        return config.validation_start

    def _calculate_observation_period(
        self,
        validation_end: str,
        aligned_table: Optional[pd.DataFrame]
    ) -> tuple[Optional[str], Optional[str]]:
        """
        计算观察期起止日期

        Args:
            validation_end: 验证期结束日期
            aligned_table: 对齐表格（包含完整时间序列）

        Returns:
            (observation_start, observation_end) 或 (None, None)
        """
        try:
            if aligned_table is None or aligned_table.empty:
                logger.warning("aligned_table为空，无法计算观察期")
                return None, None

            val_end_dt = pd.to_datetime(validation_end)
            data_end_dt = aligned_table.index.max()

            # 观察期起始 = 验证期结束后的下一周
            obs_start_dt = val_end_dt + pd.DateOffset(weeks=1)

            # 检查是否有观察期数据
            if data_end_dt <= val_end_dt:
                logger.info("数据结束日期不晚于验证期，无观察期")
                return None, None

            if obs_start_dt > data_end_dt:
                logger.warning("观察期起始日期晚于数据结束日期，无观察期")
                return None, None

            # 返回字符串格式
            return obs_start_dt.strftime('%Y-%m-%d'), data_end_dt.strftime('%Y-%m-%d')

        except Exception as e:
            logger.error(f"计算观察期失败: {e}")
            return None, None

    def _validate_metadata(self, metadata: Dict) -> None:
        """验证元数据包含所有必需字段"""
        required_fields = [
            'timestamp', 'target_variable', 'best_variables',
            'best_params', 'train_end_date', 'validation_end_date',
        ]

        missing_fields = [f for f in required_fields if f not in metadata]

        if missing_fields:
            raise ValueError(f"元数据缺少必需字段: {missing_fields}")

        logger.debug(f"元数据验证通过,包含 {len(metadata)} 个字段")

    # ========== 工具方法 ==========

    def _read_data_file(self, file_path: str) -> pd.DataFrame:
        """
        根据文件扩展名读取数据文件

        Args:
            file_path: 数据文件路径

        Returns:
            pd.DataFrame: 读取的数据
        """
        return read_data_file(file_path, parse_dates=False, check_exists=False)

    def _extract_factor_loadings(self, result, config=None) -> pd.DataFrame:
        """提取因子载荷矩阵（H矩阵）

        对于factor_order=2的模型（如DDFM），H矩阵包含滞后因子的零列，
        实际只有前k_factors列有效，因此只提取前k_factors列。
        """
        try:
            if not result.model_result:
                return pd.DataFrame()

            H = result.model_result.H

            if H is None:
                return pd.DataFrame()

            # H必须是np.ndarray类型（根据DFMModelResult定义）
            if not isinstance(H, np.ndarray):
                raise TypeError(f"H矩阵类型错误: 期望np.ndarray，实际{type(H).__name__}")

            # 验证k_factors存在且有效（不使用回退逻辑）
            if not hasattr(result, 'k_factors') or result.k_factors is None:
                raise ValueError("result对象缺少k_factors属性，无法确定因子数量")
            if result.k_factors <= 0:
                raise ValueError(f"k_factors值无效: {result.k_factors}，必须为正整数")

            k_factors = result.k_factors

            # 验证k_factors与H矩阵列数的关系
            # 正常情况：k_factors <= H.shape[1]（factor_order=1时相等，factor_order=2时H有滞后列）
            # 异常情况：k_factors > H.shape[1]，说明数据不一致
            if k_factors > H.shape[1]:
                raise ValueError(
                    f"k_factors({k_factors})大于H矩阵列数({H.shape[1]})，数据不一致"
                )

            # 只取前k_factors列（排除factor_order=2时的滞后项零列）
            H_trimmed = H[:, :k_factors]

            factor_names = [f'Factor_{i+1}' for i in range(k_factors)]

            # 使用model_result中保存的variable_names（必须存在）
            if not (hasattr(result, 'model_result') and
                result.model_result is not None and
                hasattr(result.model_result, 'variable_names') and
                result.model_result.variable_names is not None):
                raise ValueError(
                    "model_result.variable_names不存在，无法提取因子载荷矩阵。"
                    "请使用最新版本重新训练模型。"
                )
            var_names = result.model_result.variable_names

            # 严格检查变量名列表长度与H的行数是否匹配
            if len(var_names) != H_trimmed.shape[0]:
                raise ValueError(
                    f"变量名数量({len(var_names)})与H矩阵行数({H_trimmed.shape[0]})不匹配。"
                    f"selected_variables: {result.selected_variables}, "
                    f"target_variable: {config.target_variable if config else 'N/A'}"
                )

            return pd.DataFrame(H_trimmed, columns=factor_names, index=var_names)

        except Exception as e:
            logger.error(f"提取因子载荷失败: {e}")
            raise ValueError(f"无法提取因子载荷矩阵: {e}") from e

    def _convert_pca_to_dataframe(self, pca_analysis: Dict, n_components: int) -> pd.DataFrame:
        """
        将PCA分析结果转换为DataFrame格式

        Args:
            pca_analysis: PCA分析结果字典，包含:
                - explained_variance: 各主成分解释方差值
                - cumsum_variance: 累计解释方差（百分比）
                - eigenvalues: 特征值
            n_components: 主成分数量

        Returns:
            DataFrame包含列: 主成分(PC), 解释方差(%), 累计解释方差(%), 特征值
        """
        try:
            if not pca_analysis:
                return pd.DataFrame()

            # 从pca_analysis中提取数据（适配pca_utils.py的返回格式）
            explained_variance = pca_analysis.get('explained_variance', [])
            cumsum_variance = pca_analysis.get('cumsum_variance', [])
            eigenvalues = pca_analysis.get('eigenvalues', [])

            # Fix: 正确检查数组/列表是否为空
            if explained_variance is None or (hasattr(explained_variance, '__len__') and len(explained_variance) == 0):
                logger.warning("PCA分析结果缺少explained_variance数据")
                return pd.DataFrame()

            # explained_variance 已经是比率（来自pca.explained_variance_ratio_），直接转换为百分比
            explained_variance_ratio_pct = [v * 100 for v in explained_variance[:n_components]]

            # 使用cumsum_variance（如果可用），否则重新计算
            # cumsum_variance也是比率，需要转换为百分比
            if cumsum_variance is not None and len(cumsum_variance) >= n_components:
                cumulative_explained_variance_pct = [v * 100 for v in cumsum_variance[:n_components]]
            else:
                cumulative_explained_variance_pct = np.cumsum(explained_variance_ratio_pct).tolist()

            # 使用eigenvalues（如果可用）
            if eigenvalues is not None and len(eigenvalues) >= n_components:
                eigenvalues_list = list(eigenvalues[:n_components])
            else:
                eigenvalues_list = [0.0] * n_components

            # 构建DataFrame
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

    def _collect_nowcast_data(self, result, config) -> Optional[pd.Series]:
        """
        收集并合并训练期、验证期/观察期的Nowcast数据

        术语说明：
        - 经典DFM: forecast_is(训练期), forecast_oos(验证期), forecast_obs(观察期)
        - DDFM: forecast_is(训练期), forecast_obs(观察期), forecast_oos=None

        Args:
            result: 训练结果
            config: 训练配置

        Returns:
            合并后的Nowcast序列，如果失败则返回None
        """
        # 判断是否为DDFM模式（深度学习算法）
        is_ddfm = (getattr(config, 'algorithm', 'classical') == 'deep_learning')

        forecast_is = None
        forecast_oos = None
        forecast_obs = None

        if result.model_result:
            forecast_is = result.model_result.forecast_is
            logger.info(f"forecast_is类型: {type(forecast_is)}, 长度: {len(forecast_is) if forecast_is is not None else None}")

            forecast_oos = result.model_result.forecast_oos
            logger.info(f"forecast_oos类型: {type(forecast_oos)}, 长度: {len(forecast_oos) if forecast_oos is not None else None}")

            forecast_obs = result.model_result.forecast_obs
            logger.info(f"forecast_obs类型: {type(forecast_obs)}, 长度: {len(forecast_obs) if forecast_obs is not None else None}")

        is_index = self._get_date_index(config, 'training_start', 'train_end', '训练期')

        nowcast_series_list = []

        # 训练期数据
        if forecast_is is not None and is_index is not None and len(is_index) == len(forecast_is):
            is_series = pd.Series(forecast_is, index=is_index, name='Nowcast')
            nowcast_series_list.append(is_series)
            logger.info(f"训练期数据: {len(is_series)} 个点，时间范围 {is_index.min()} 到 {is_index.max()}")
        else:
            logger.warning("无法生成训练期Nowcast序列")

        if is_ddfm:
            # DDFM模式：validation_start~validation_end是观察期，使用forecast_obs
            obs_index = self._get_date_index(config, 'validation_start', 'validation_end', '观察期')
            if forecast_obs is not None and obs_index is not None and len(obs_index) == len(forecast_obs):
                obs_series = pd.Series(forecast_obs, index=obs_index, name='Nowcast')
                nowcast_series_list.append(obs_series)
                logger.info(f"[DDFM] 观察期数据: {len(obs_series)} 个点，时间范围 {obs_index.min()} 到 {obs_index.max()}")
            else:
                logger.warning("[DDFM] 无法生成观察期Nowcast序列")
        else:
            # 经典DFM模式：validation是验证期，之后是观察期
            oos_index = self._get_date_index(config, 'validation_start', 'validation_end', '验证期')

            # 验证期数据
            if forecast_oos is not None and oos_index is not None and len(oos_index) == len(forecast_oos):
                oos_series = pd.Series(forecast_oos, index=oos_index, name='Nowcast')
                nowcast_series_list.append(oos_series)
                logger.info(f"验证期数据: {len(oos_series)} 个点，时间范围 {oos_index.min()} 到 {oos_index.max()}")
            else:
                logger.warning("无法生成验证期Nowcast序列")

            # 观察期数据（验证期之后）
            if forecast_obs is not None:
                obs_index = self._get_observation_index(config)
                if obs_index is not None and len(obs_index) == len(forecast_obs):
                    obs_series = pd.Series(forecast_obs, index=obs_index, name='Nowcast')
                    nowcast_series_list.append(obs_series)
                    logger.info(f"观察期数据: {len(obs_series)} 个点，时间范围 {obs_index.min()} 到 {obs_index.max()}")
                else:
                    logger.warning("无法生成观察期Nowcast序列")

        if len(nowcast_series_list) == 0:
            logger.warning("无法获取Nowcast数据")
            return None

        nowcast_data = pd.concat(nowcast_series_list).sort_index()
        logger.info(f"完整Nowcast数据: {len(nowcast_data)} 个点，时间范围 {nowcast_data.index.min()} 到 {nowcast_data.index.max()}")
        logger.info(f"nowcast_data索引类型: {type(nowcast_data.index)}, 前5个: {list(nowcast_data.index[:5])}")

        return nowcast_data

    def _load_target_data(self, config) -> Optional[pd.Series]:
        """
        从数据文件加载目标变量数据

        Args:
            config: 训练配置

        Returns:
            目标变量序列，如果失败则返回None
        """
        if not hasattr(config, 'data_path') or not config.data_path:
            return None

        try:
            logger.info(f"尝试从数据文件读取目标变量: {config.data_path}")
            data = self._read_data_file(config.data_path)
            logger.info(f"数据文件读取成功，形状: {data.shape}, 列数: {len(data.columns)}")

            if config.target_variable in data.columns:
                target_data = data[config.target_variable].dropna()
                logger.info(f"目标变量'{config.target_variable}'读取成功，长度: {len(target_data)}")
                return target_data
            else:
                logger.warning(f"数据文件中未找到目标变量'{config.target_variable}'")
                return None
        except Exception as e:
            logger.warning(f"从数据文件读取目标变量失败: {e}", exc_info=True)
            return None

    def _generate_aligned_table(self, result, config, metadata: Dict) -> Optional[pd.DataFrame]:
        """
        生成complete_aligned_table

        对齐规则：
        1. 每个月最后一个周五的Nowcast值
        2. 对应下一个月的实际值

        Args:
            result: 训练结果
            config: 训练配置
            metadata: 元数据字典

        Returns:
            DataFrame包含两列: 'Nowcast (Original Scale)' 和目标变量名
        """
        try:
            logger.info("=" * 60)
            logger.info("开始生成complete_aligned_table，合并训练期和验证期数据...")
            logger.info("=" * 60)

            nowcast_data = self._collect_nowcast_data(result, config)
            if nowcast_data is None:
                logger.warning("无法获取Nowcast数据，complete_aligned_table将为空")
                return pd.DataFrame(columns=['Nowcast (Original Scale)', config.target_variable])

            target_data = self._load_target_data(config)
            if target_data is None or len(target_data) == 0:
                logger.warning("无法获取目标变量实际值")
                return pd.DataFrame({
                    'Nowcast (Original Scale)': nowcast_data,
                    config.target_variable: np.nan
                })

            aligned_table = self._align_nowcast_target(
                nowcast_data,
                target_data,
                config.target_variable
            )

            logger.info(f"complete_aligned_table生成完成，包含 {len(aligned_table)} 行数据")
            return aligned_table

        except Exception as e:
            logger.error(f"生成complete_aligned_table失败: {e}", exc_info=True)
            raise ValueError(f"无法生成对齐表格: {e}") from e

    def _align_nowcast_target(
        self,
        nowcast_weekly: pd.Series,
        target_orig: pd.Series,
        target_variable_name: str
    ) -> pd.DataFrame:
        """
        对齐周度Nowcast和月度Target

        对齐规则：
        1. 选取每个月最后一个周五的Nowcast值
        2. 将该Nowcast值与下一个月的Target值进行匹配

        Args:
            nowcast_weekly: 周度Nowcast序列
            target_orig: 目标变量序列
            target_variable_name: 目标变量名称

        Returns:
            对齐后的DataFrame
        """
        try:
            # 确保索引是DatetimeIndex
            if not isinstance(nowcast_weekly.index, pd.DatetimeIndex):
                nowcast_weekly.index = pd.to_datetime(nowcast_weekly.index)
            if not isinstance(target_orig.index, pd.DatetimeIndex):
                target_orig.index = pd.to_datetime(target_orig.index)

            # 筛选出所有周五
            fridays_index = nowcast_weekly[nowcast_weekly.index.dayofweek == 4].index
            if fridays_index.empty:
                logger.warning("Nowcast序列中未找到任何周五")
                return pd.DataFrame(columns=['Nowcast (Original Scale)', target_variable_name])

            # 使用所有周五的Nowcast值
            nowcast_all_fridays = nowcast_weekly.loc[fridays_index].copy()
            nowcast_all_fridays.name = 'Nowcast (Original Scale)'

            # 计算每月最后一个周五
            last_fridays = fridays_index.to_series().groupby(fridays_index.to_period('M')).max()

            # 准备Target数据
            target_df = target_orig.dropna().to_frame(target_variable_name)
            target_df['TargetPeriod'] = target_df.index.to_period('M')

            # 创建完整的对齐DataFrame
            final_aligned_table = nowcast_all_fridays.to_frame()
            final_aligned_table[target_variable_name] = np.nan

            # 对齐逻辑：每个月最后一个周五对应下个月的真实值
            aligned_count = 0
            for target_date, target_value in target_df[target_variable_name].items():
                target_period = target_df.loc[target_date, 'TargetPeriod']

                # 找到上个月的最后一个周五
                prev_month = target_period - 1

                if prev_month in last_fridays.index:
                    last_friday_date = last_fridays.loc[prev_month]

                    # 将真实值分配到对应的周五行
                    if last_friday_date in final_aligned_table.index:
                        final_aligned_table.loc[last_friday_date, target_variable_name] = target_value
                        aligned_count += 1

            logger.debug(f"成功对齐 {aligned_count} 个数据点")
            return final_aligned_table

        except Exception as e:
            logger.error(f"对齐Nowcast和Target失败: {e}")
            return pd.DataFrame(columns=['Nowcast (Original Scale)', target_variable_name])

    def _get_date_index(
        self,
        config,
        start_field: str,
        end_field: str,
        period_name: str
    ) -> Optional[pd.DatetimeIndex]:
        """
        从数据文件中获取指定时间段的日期索引

        Args:
            config: 训练配置
            start_field: 开始日期字段名（如'training_start'或'validation_start'）
            end_field: 结束日期字段名（如'train_end'或'validation_end'）
            period_name: 时间段名称，用于日志（如'训练期'或'验证期'）

        Returns:
            指定时间段的日期索引，如果无法获取则返回None
        """
        try:
            if not hasattr(config, 'data_path') or not config.data_path:
                return None

            if not hasattr(config, start_field) or not getattr(config, start_field):
                logger.warning(f"config缺少{start_field}字段")
                return None

            if not hasattr(config, end_field) or not getattr(config, end_field):
                logger.warning(f"config缺少{end_field}字段")
                return None

            data = self._read_data_file(config.data_path)

            if not isinstance(data.index, pd.DatetimeIndex):
                try:
                    data.index = pd.to_datetime(data.index)
                except Exception as e:
                    raise ValueError(f"无法将数据索引转换为DatetimeIndex: {e}") from e

            start_date = pd.to_datetime(getattr(config, start_field))
            end_date = pd.to_datetime(getattr(config, end_field))

            date_index = data.index[(data.index >= start_date) & (data.index <= end_date)]

            if len(date_index) == 0:
                logger.warning(f"{period_name} {start_date} 到 {end_date} 没有数据")
                return None

            logger.debug(f"获取{period_name}日期索引成功: {len(date_index)} 个日期，范围 {date_index.min()} 到 {date_index.max()}")
            return date_index

        except Exception as e:
            logger.error(f"获取{period_name}日期索引失败: {e}")
            return None

    def _get_observation_index(self, config) -> Optional[pd.DatetimeIndex]:
        """
        获取观察期的日期索引

        Args:
            config: 训练配置

        Returns:
            观察期的日期索引，如果无法获取则返回None
        """
        try:
            if not hasattr(config, 'data_path') or not config.data_path:
                return None

            if not hasattr(config, 'validation_end') or not config.validation_end:
                logger.warning("config缺少validation_end字段")
                return None

            # 读取数据文件
            data = self._read_data_file(config.data_path)

            if not isinstance(data.index, pd.DatetimeIndex):
                try:
                    data.index = pd.to_datetime(data.index)
                except Exception as e:
                    raise ValueError(f"无法将数据索引转换为DatetimeIndex: {e}") from e

            # 计算观察期起始和结束日期
            val_end_dt = pd.to_datetime(config.validation_end)
            obs_start_dt = val_end_dt + pd.DateOffset(weeks=1)
            data_end_dt = data.index.max()

            # 检查是否有观察期
            if data_end_dt <= val_end_dt:
                logger.info("数据结束日期不晚于验证期，无观察期")
                return None

            if obs_start_dt > data_end_dt:
                logger.warning("观察期起始日期晚于数据结束日期，无观察期")
                return None

            # 获取观察期日期索引
            obs_index = data.index[(data.index >= obs_start_dt) & (data.index <= data_end_dt)]

            if len(obs_index) == 0:
                logger.warning(f"观察期 {obs_start_dt} 到 {data_end_dt} 没有数据")
                return None

            logger.debug(f"获取观察期日期索引成功: {len(obs_index)} 个日期，范围 {obs_index.min()} 到 {obs_index.max()}")
            return obs_index

        except Exception as e:
            logger.error(f"获取观察期日期索引失败: {e}")
            return None


__all__ = ['TrainingResultExporter']
