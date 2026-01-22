# -*- coding: utf-8 -*-
"""
模型文件加载器

专注于从joblib和pickle文件中提取已计算的nowcast值和相关数据，
为影响分析提供基础数据。
"""

import pickle
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, Optional, List
import io
import logging
from datetime import datetime

from ..utils.validators import validate_model_data
from ..utils.exceptions import ModelLoadError, ValidationError, DataFormatError

logger = logging.getLogger(__name__)


class SavedNowcastData:
    """保存的nowcast数据结构"""

    def __init__(self):
        self.nowcast_series: Optional[pd.Series] = None
        self.kalman_gains_history: Optional[List[np.ndarray]] = None  # 修改：保存每个时刻的K_t矩阵列表
        self.factor_loadings: Optional[np.ndarray] = None  # H矩阵（观测矩阵/因子载荷）- 预测变量
        self.target_factor_loading: Optional[np.ndarray] = None  # 新增：目标变量的因子载荷向量
        self.factor_series: Optional[pd.DataFrame] = None
        self.target_variable: Optional[str] = None
        self.variable_index_map: Optional[Dict[str, int]] = None  # 变量名到索引的映射
        self.var_industry_map: Optional[Dict[str, str]] = None  # 新增：变量名到行业分类的映射
        self.model_parameters: Optional[Dict[str, Any]] = None
        self.metadata: Optional[Dict[str, Any]] = None
        self.data_period: Optional[Tuple[str, str]] = None
        self.convergence_info: Optional[Dict[str, Any]] = None
        self.prepared_data: Optional[pd.DataFrame] = None  # 新增：complete_aligned_table（包含所有历史观测数据）
        self.model_type: Optional[str] = None  # 新增：模型类型 'classical' 或 'deep_learning'
        self.factor_states_predicted: Optional[np.ndarray] = None  # 先验因子状态 (n_time, n_factors)，用于expected_value计算
        self.target_mean_original: Optional[float] = None  # 新增：目标变量训练期均值（用于反标准化）
        self.target_std_original: Optional[float] = None  # 新增：目标变量训练期标准差（用于反标准化）


class ModelLoader:
    """
    模型文件加载器

    专门用于加载包含已计算nowcast值的DFM模型文件和元数据。
    核心功能是数据提取而非重新计算。
    """

    def __init__(self):
        self._model: Optional[Any] = None
        self._metadata: Optional[Dict[str, Any]] = None
        self._nowcast_data: Optional[SavedNowcastData] = None
        self._load_time: Optional[datetime] = None

    def load_model(self, model_content: bytes) -> Any:
        """
        从字节内容加载DFM模型文件

        Args:
            model_content: joblib模型文件的字节内容

        Returns:
            加载的DFM模型对象

        Raises:
            ModelLoadError: 加载失败时抛出
        """
        try:
            # 使用BytesIO避免写入临时文件
            model_stream = io.BytesIO(model_content)
            self._model = joblib.load(model_stream)
            self._load_time = datetime.now()

            # 验证模型对象
            if not hasattr(self._model, '__dict__'):
                raise ModelLoadError("加载的对象不是有效的模型实例")

            logger.info(f"成功加载DFM模型，类型: {type(self._model)}")
            return self._model

        except Exception as e:
            raise ModelLoadError(
                f"加载DFM模型文件失败: {str(e)}",
                original_error=e
            )

    def load_metadata(self, metadata_content: bytes) -> Dict[str, Any]:
        """
        从字节内容加载模型元数据

        Args:
            metadata_content: pickle元数据文件的字节内容

        Returns:
            元数据字典

        Raises:
            ModelLoadError: 加载失败时抛出
        """
        try:
            # 使用BytesIO避免写入临时文件
            metadata_stream = io.BytesIO(metadata_content)
            self._metadata = pickle.load(metadata_stream)

            # 验证元数据格式
            if not isinstance(self._metadata, dict):
                raise ModelLoadError("元数据文件格式无效，应为字典")

            logger.info(f"成功加载元数据，包含 {len(self._metadata)} 个键")
            return self._metadata

        except Exception as e:
            raise ModelLoadError(
                f"加载元数据文件失败: {str(e)}",
                original_error=e
            )

    def detect_model_type(self) -> str:
        """
        检测模型类型

        Returns:
            模型类型: 'classical' 或 'deep_learning'

        Raises:
            ModelLoadError: 元数据不可用或缺少算法信息时抛出
        """
        if self._metadata is None:
            raise ModelLoadError("元数据不可用，无法检测模型类型")

        # 优先从best_params检测
        if 'best_params' in self._metadata:
            best_params = self._metadata['best_params']
            if 'algorithm' in best_params:
                return best_params['algorithm']

        # 从顶层检测
        if 'algorithm' not in self._metadata:
            raise ModelLoadError(
                "元数据中缺少算法信息。\n"
                "无法确定模型类型（'classical' 或 'deep_learning'）。\n"
                "请使用新版本训练模块重新训练模型。"
            )

        return self._metadata['algorithm']

    def extract_saved_nowcast(self) -> SavedNowcastData:
        """
        从加载的模型和元数据中提取nowcast相关数据

        Returns:
            SavedNowcastData: 提取的nowcast数据结构

        Raises:
            ModelLoadError: 数据提取失败时抛出
            ValidationError: 数据验证失败时抛出
        """
        if self._model is None or self._metadata is None:
            raise ModelLoadError("请先加载模型和元数据文件")

        try:
            nowcast_data = SavedNowcastData()

            # 1. 提取nowcast时间序列
            nowcast_data.nowcast_series = self._extract_nowcast_series()

            # 2. 提取卡尔曼增益历史（修改：使用新字段名）
            nowcast_data.kalman_gains_history = self._extract_kalman_gains()

            # 3. 提取因子载荷矩阵（H矩阵）
            nowcast_data.factor_loadings = self._extract_factor_loadings()

            # 4. 提取因子时间序列
            nowcast_data.factor_series = self._extract_factor_series()

            # 4.5 提取目标变量的因子载荷
            nowcast_data.target_factor_loading = self._extract_target_factor_loading()

            # 5. 提取目标变量信息
            nowcast_data.target_variable = self._extract_target_variable()

            # 6. 提取变量映射
            nowcast_data.variable_index_map = self._extract_variable_mapping()

            # 7. 提取模型参数
            nowcast_data.model_parameters = self._extract_model_parameters()

            # 8. 提取数据时间范围
            nowcast_data.data_period = self._extract_data_period()

            # 9. 提取收敛信息
            nowcast_data.convergence_info = self._extract_convergence_info()

            # 10. 提取历史观测数据表（complete_aligned_table）
            nowcast_data.prepared_data = self._extract_prepared_data()

            # 11. 提取行业分类映射
            nowcast_data.var_industry_map = self._extract_industry_map()

            # 12. 提取先验因子状态（必需字段）
            nowcast_data.factor_states_predicted = self._extract_factor_states_predicted()

            # 13. 提取目标变量标准化参数（用于影响分解反标准化）
            target_mean, target_std = self._extract_target_standardization_params()
            nowcast_data.target_mean_original = target_mean
            nowcast_data.target_std_original = target_std

            # 14. 保存原始元数据
            nowcast_data.metadata = self._metadata.copy()

            # 15. 检测并设置模型类型
            nowcast_data.model_type = self.detect_model_type()
            logger.info(f"模型类型: {nowcast_data.model_type}")

            # 验证提取的数据
            self._validate_extracted_data(nowcast_data)

            self._nowcast_data = nowcast_data
            logger.info("成功提取nowcast数据")
            return nowcast_data

        except Exception as e:
            raise ModelLoadError(f"提取nowcast数据失败: {str(e)}")

    def validate_model_compatibility(self, model: Any, metadata: Dict[str, Any]) -> bool:
        """
        验证模型和元数据的兼容性

        Args:
            model: DFM模型对象
            metadata: 元数据字典

        Returns:
            bool: 是否兼容

        Raises:
            ValidationError: 验证失败时抛出
        """
        try:
            is_valid, errors = validate_model_data(model, metadata)

            if not is_valid:
                error_msg = "模型兼容性验证失败:\n" + "\n".join(f"  - {error}" for error in errors)
                raise ValidationError(error_msg)

            # 额外的兼容性检查
            # 检查因子数量一致性：使用元数据中的k_factors值（而非H矩阵列数，因为H包含特质项）
            if 'factor_loadings_df' not in metadata:
                raise ValidationError("元数据缺少factor_loadings_df字段")
            if 'best_params' not in metadata:
                raise ValidationError("元数据缺少best_params字段")
            if 'k_factors' not in metadata['best_params']:
                raise ValidationError("元数据best_params缺少k_factors字段")

            k_factors = metadata['best_params']['k_factors']
            factor_loadings_cols = metadata['factor_loadings_df'].shape[1]

            if k_factors != factor_loadings_cols:
                raise ValidationError(
                    f"因子数量不匹配: best_params.k_factors={k_factors}, factor_loadings_df.columns={factor_loadings_cols}"
                )

            logger.info("模型兼容性验证通过")
            return True

        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"兼容性验证过程异常: {str(e)}")

    def _extract_nowcast_series(self) -> pd.Series:
        """提取nowcast时间序列"""
        if 'complete_aligned_table' not in self._metadata:
            raise DataFormatError("元数据中缺少complete_aligned_table")

        nowcast_table = self._metadata['complete_aligned_table']

        if not isinstance(nowcast_table, pd.DataFrame):
            raise DataFormatError("nowcast数据格式无效")

        if 'Nowcast (Original Scale)' not in nowcast_table.columns:
            raise DataFormatError("nowcast数据中缺少目标列")

        nowcast_series = nowcast_table['Nowcast (Original Scale)']

        if nowcast_series.empty:
            raise DataFormatError("nowcast时间序列为空")

        logger.info(f"提取nowcast序列: {len(nowcast_series)} 个数据点")
        return nowcast_series

    def _extract_kalman_gains(self) -> List[np.ndarray]:
        """提取卡尔曼增益历史"""
        if 'kalman_gains_history' not in self._metadata:
            raise DataFormatError(
                "元数据中缺少kalman_gains_history字段。\n"
                "影响分解功能需要卡尔曼增益历史数据。\n"
                "请使用新版本训练模块重新训练模型以支持此功能。"
            )

        kalman_gains_history = self._metadata['kalman_gains_history']

        if kalman_gains_history is None or len(kalman_gains_history) == 0:
            raise DataFormatError(
                "kalman_gains_history为空。\n"
                "影响分解功能需要卡尔曼增益历史数据。\n"
                "请使用新版本训练模块重新训练模型以支持此功能。"
            )

        # 验证至少有一个非None的K_t矩阵
        if all(K is None for K in kalman_gains_history):
            raise DataFormatError(
                "kalman_gains_history中所有K_t矩阵均为None。\n"
                "影响分解功能需要至少一个有效的卡尔曼增益矩阵。\n"
                "请检查模型训练过程是否正确保存了卡尔曼增益。"
            )

        logger.info(f"提取卡尔曼增益历史: {len(kalman_gains_history)} 个时间步")

        # 验证格式
        first_non_none = next((k for k in kalman_gains_history if k is not None), None)
        if first_non_none is not None:
            logger.info(f"K_t矩阵形状: {first_non_none.shape}")

        return kalman_gains_history

    def _extract_factor_loadings(self) -> np.ndarray:
        """提取因子载荷矩阵"""
        if 'factor_loadings_df' not in self._metadata:
            raise DataFormatError("元数据中缺少因子载荷数据")

        factor_loadings = self._metadata['factor_loadings_df']

        if not isinstance(factor_loadings, pd.DataFrame):
            raise DataFormatError("因子载荷数据格式无效")

        if factor_loadings.empty:
            raise DataFormatError("因子载荷矩阵为空")

        logger.info(f"提取因子载荷矩阵: {factor_loadings.shape}")
        return factor_loadings.values

    def _extract_target_factor_loading(self) -> np.ndarray:
        """提取目标变量的因子载荷向量"""
        if 'target_factor_loading' not in self._metadata:
            raise DataFormatError(
                "元数据中缺少target_factor_loading字段。\n"
                "影响分解功能需要目标变量的因子载荷向量。\n"
                "请使用新版本训练模块重新训练模型以支持此功能。"
            )

        target_loading = self._metadata['target_factor_loading']

        if target_loading is None:
            raise DataFormatError("target_factor_loading字段存在但值为None")

        if not isinstance(target_loading, np.ndarray):
            raise DataFormatError(
                f"target_factor_loading格式无效，应为ndarray类型，实际为{type(target_loading)}"
            )

        logger.info(f"提取目标变量因子载荷: 形状={target_loading.shape}")
        return target_loading

    def _extract_factor_series(self) -> pd.DataFrame:
        """提取因子时间序列"""
        if 'factor_series' not in self._metadata:
            raise DataFormatError("元数据中缺少因子序列数据")

        factor_series = self._metadata['factor_series']

        if not isinstance(factor_series, pd.DataFrame):
            raise DataFormatError("因子序列数据格式无效")

        if factor_series.empty:
            raise DataFormatError("因子序列为空")

        logger.info(f"提取因子序列: {factor_series.shape}")
        return factor_series

    def _extract_target_variable(self) -> str:
        """提取目标变量信息"""
        if 'target_variable' not in self._metadata:
            raise DataFormatError("元数据中缺少目标变量信息")

        target_variable = self._metadata['target_variable']

        if not isinstance(target_variable, str):
            raise DataFormatError("目标变量信息格式无效")

        logger.info(f"提取目标变量: {target_variable}")
        return target_variable

    def _extract_model_parameters(self) -> Dict[str, Any]:
        """提取模型参数"""
        parameters = {}

        # 从模型中提取参数
        if hasattr(self._model, 'A'):
            parameters['state_transition'] = self._model.A
        if hasattr(self._model, 'Q'):
            parameters['state_noise'] = self._model.Q
        if hasattr(self._model, 'R'):
            parameters['observation_noise'] = self._model.R

        # 从元数据中提取参数
        if 'best_params' in self._metadata:
            parameters.update(self._metadata['best_params'])

        logger.info(f"提取模型参数: {len(parameters)} 个")
        return parameters

    def _extract_data_period(self) -> Tuple[str, str]:
        """提取数据时间范围

        Raises:
            DataFormatError: 时间范围信息缺失时抛出
        """
        # 从元数据中获取
        if 'training_start_date' not in self._metadata:
            raise DataFormatError("元数据中缺少training_start_date字段")

        if 'validation_end_date' not in self._metadata:
            raise DataFormatError("元数据中缺少validation_end_date字段")

        start_date = self._metadata['training_start_date']
        end_date = self._metadata['validation_end_date']

        if not start_date or not end_date:
            raise DataFormatError("数据时间范围为空")

        return start_date, end_date

    def _extract_convergence_info(self) -> Dict[str, Any]:
        """提取收敛信息"""
        convergence_info = {}

        if hasattr(self._model, 'converged'):
            convergence_info['converged'] = bool(self._model.converged)

        if hasattr(self._model, 'iterations'):
            convergence_info['iterations'] = int(self._model.iterations)

        if hasattr(self._model, 'log_likelihood'):
            convergence_info['log_likelihood'] = float(self._model.log_likelihood)

        # 从元数据中获取性能指标
        performance_keys = ['is_rmse', 'oos_rmse', 'is_hit_rate', 'oos_hit_rate']
        for key in performance_keys:
            if key in self._metadata:
                convergence_info[key] = float(self._metadata[key])

        logger.info(f"提取收敛信息: {len(convergence_info)} 项")
        return convergence_info

    def _extract_prepared_data(self) -> pd.DataFrame:
        """提取历史观测数据表（prepared_data）"""
        if 'prepared_data' not in self._metadata:
            raise DataFormatError(
                "元数据中缺少prepared_data字段。\n"
                "影响分解功能需要完整的历史观测数据表。\n"
                "请使用新版本训练模块重新训练模型以支持此功能。"
            )

        prepared_data = self._metadata['prepared_data']

        if prepared_data is None:
            raise DataFormatError("prepared_data字段存在但值为None")

        if not isinstance(prepared_data, pd.DataFrame):
            raise DataFormatError("prepared_data不是DataFrame类型")

        if prepared_data.empty:
            raise DataFormatError("prepared_data为空")

        logger.info(f"提取历史观测数据表: 形状={prepared_data.shape}, 列数={len(prepared_data.columns)}")
        logger.info(f"数据时间范围: {prepared_data.index[0]} 到 {prepared_data.index[-1]}")

        return prepared_data

    def _extract_variable_mapping(self) -> Dict[str, int]:
        """提取变量索引映射

        注意：variable_index_map只包含预测变量（不含目标变量），
        因为K_t矩阵的列数对应预测变量数。

        Returns:
            Dict[str, int]: 变量名到索引的映射
        """
        # 从factor_loadings_df获取变量列表（已排除目标变量，与K_t矩阵对齐）
        if 'factor_loadings_df' not in self._metadata:
            raise DataFormatError(
                "元数据中缺少factor_loadings_df字段。\n"
                "影响分解功能需要因子载荷矩阵信息。\n"
                "请使用新版本训练模块重新训练模型以支持此功能。"
            )

        factor_loadings_df = self._metadata['factor_loadings_df']
        if not hasattr(factor_loadings_df, 'index') or len(factor_loadings_df.index) == 0:
            raise DataFormatError("factor_loadings_df的索引为空，无法提取变量列表")

        variable_list = list(factor_loadings_df.index)
        logger.info(f"从factor_loadings_df提取{len(variable_list)}个预测变量")

        # 构建变量名到索引的映射（索引对应K_t矩阵的列索引）
        variable_index_map = {var_name: idx for idx, var_name in enumerate(variable_list)}

        # 获取目标变量信息（仅用于日志）
        # 注意：target_variable已在_extract_target_variable中验证存在
        target_variable = self._metadata['target_variable']
        if target_variable:
            logger.info(f"目标变量: {target_variable} (不在预测变量映射中)")

        logger.info(f"提取变量映射: {len(variable_index_map)} 个预测变量")
        return variable_index_map

    def _extract_industry_map(self) -> Optional[Dict[str, str]]:
        """
        从元数据中提取行业分类映射（可选字段）

        Returns:
            变量名到行业的映射字典，如果不存在则返回None
        """
        if 'var_industry_map' not in self._metadata:
            logger.debug("元数据中缺少var_industry_map字段（可选）")
            return None

        var_industry_map = self._metadata['var_industry_map']

        if not isinstance(var_industry_map, dict):
            logger.warning("var_industry_map格式无效，应为字典类型")
            return None

        if not var_industry_map:
            logger.debug("var_industry_map为空字典")
            return {}

        logger.info(f"提取行业分类映射: {len(var_industry_map)} 个变量")
        sample_items = list(var_industry_map.items())[:3]
        logger.debug(f"示例映射: {sample_items}")

        return var_industry_map

    def _extract_factor_states_predicted(self) -> np.ndarray:
        """
        提取先验因子状态历史（必需字段）

        Returns:
            先验因子状态数组 (n_time, n_factors)

        Raises:
            DataFormatError: 数据缺失或格式错误时抛出
        """
        if 'factor_states_predicted' not in self._metadata:
            raise DataFormatError(
                "元数据中缺少factor_states_predicted字段。\n"
                "影响分解功能需要先验因子状态数据。\n"
                "请使用新版本训练模块重新训练模型以支持此功能。"
            )

        data = self._metadata['factor_states_predicted']
        if data is None:
            raise DataFormatError("factor_states_predicted字段存在但值为None")

        if not isinstance(data, np.ndarray):
            raise DataFormatError(
                f"factor_states_predicted格式无效，应为ndarray类型，实际为{type(data)}"
            )

        logger.info(f"提取先验因子状态: 形状={data.shape}")
        return data

    def _extract_target_standardization_params(self) -> Tuple[float, float]:
        """
        提取目标变量标准化参数（用于影响分解反标准化）

        Returns:
            (target_mean, target_std) 元组

        Raises:
            DataFormatError: 数据缺失或格式错误时抛出
        """
        # 验证并提取 target_mean_original
        if 'target_mean_original' not in self._metadata:
            raise DataFormatError(
                "元数据中缺少target_mean_original字段。\n"
                "影响分解功能需要目标变量标准化参数。\n"
                "请使用新版本训练模块重新训练模型以支持此功能。"
            )

        target_mean = self._metadata['target_mean_original']
        if not isinstance(target_mean, (int, float)):
            raise DataFormatError(
                f"target_mean_original格式无效，应为数值类型，实际为{type(target_mean)}"
            )

        # 验证并提取 target_std_original
        if 'target_std_original' not in self._metadata:
            raise DataFormatError(
                "元数据中缺少target_std_original字段。\n"
                "影响分解功能需要目标变量标准化参数。\n"
                "请使用新版本训练模块重新训练模型以支持此功能。"
            )

        target_std = self._metadata['target_std_original']
        if not isinstance(target_std, (int, float)):
            raise DataFormatError(
                f"target_std_original格式无效，应为数值类型，实际为{type(target_std)}"
            )

        # 验证标准差为正数
        if target_std <= 0:
            raise DataFormatError(
                f"target_std_original={target_std}不是正数。\n"
                "标准差必须大于0才能进行反标准化。\n"
                "请检查训练数据是否存在问题。"
            )

        logger.info(f"提取标准化参数: mean={target_mean:.4f}, std={target_std:.4f}")
        return float(target_mean), float(target_std)

    def _validate_extracted_data(self, nowcast_data: SavedNowcastData) -> None:
        """验证提取的数据完整性"""
        # 验证必需字段（这些字段如果缺失，extraction方法已经抛出异常）
        if nowcast_data.nowcast_series is None:
            raise ValidationError("nowcast时间序列不可用")
        if nowcast_data.target_variable is None:
            raise ValidationError("目标变量信息不可用")
        if nowcast_data.kalman_gains_history is None:
            raise ValidationError("卡尔曼增益历史不可用")
        if nowcast_data.target_factor_loading is None:
            raise ValidationError("目标变量因子载荷不可用")
        if nowcast_data.factor_loadings is None:
            raise ValidationError("因子载荷矩阵不可用")
        if nowcast_data.variable_index_map is None:
            raise ValidationError("变量索引映射不可用")
        if nowcast_data.prepared_data is None:
            raise ValidationError("历史观测数据表不可用")
        if nowcast_data.factor_states_predicted is None:
            raise ValidationError("先验因子状态数据不可用")
        if nowcast_data.target_mean_original is None:
            raise ValidationError("目标变量均值不可用")
        if nowcast_data.target_std_original is None:
            raise ValidationError("目标变量标准差不可用")
        if nowcast_data.target_std_original <= 0:
            raise ValidationError(
                f"目标变量标准差={nowcast_data.target_std_original}不是正数。"
                "标准差必须大于0才能进行反标准化。"
            )

        # 验证维度一致性
        # 获取因子数和变量数
        n_factors = nowcast_data.factor_loadings.shape[1]
        n_variables = nowcast_data.factor_loadings.shape[0]

        # 验证卡尔曼增益历史维度
        first_non_none = next((k for k in nowcast_data.kalman_gains_history if k is not None), None)
        if first_non_none is not None:
            # K_t存储形状为(n_states, n_variables)，其中n_states = n_factors * max_lags
            # 使用时会截取前n_factors行
            # H形状应为(n_variables, n_factors)

            # K_t第一维应该 >= n_factors（因为n_states = n_factors * max_lags）
            if first_non_none.shape[0] < n_factors:
                raise ValidationError(
                    f"K_t状态维度({first_non_none.shape[0]})小于因子数({n_factors})"
                )
            # K_t第二维应该等于变量数
            if first_non_none.shape[1] != n_variables:
                raise ValidationError(
                    f"K_t变量维度({first_non_none.shape[1]})与H变量维度({n_variables})不一致"
                )

            logger.info(f"K_t维度验证: ({first_non_none.shape[0]}, {first_non_none.shape[1]}), "
                  f"将截取前{n_factors}行用于影响分析")

        # 验证factor_states_predicted维度（独立于K_t验证）
        fsp_shape = nowcast_data.factor_states_predicted.shape
        if len(fsp_shape) != 2:
            raise ValidationError(
                f"factor_states_predicted维度错误，应为2维，实际为{len(fsp_shape)}维"
            )
        if fsp_shape[1] != n_factors:
            raise ValidationError(
                f"factor_states_predicted因子数({fsp_shape[1]})与factor_loadings因子数({n_factors})不一致"
            )
        logger.info(f"factor_states_predicted维度验证: {fsp_shape}")

        logger.info("数据完整性验证通过")

    def get_model_info(self) -> Dict[str, Any]:
        """
        获取加载的模型信息摘要

        Returns:
            模型信息字典
        """
        if self._model is None or self._metadata is None:
            return {"status": "未加载"}

        info = {
            "status": "已加载",
            "load_time": self._load_time.isoformat() if self._load_time else None,
            "model_type": str(type(self._model)),
            "metadata_keys": len(self._metadata) if self._metadata else 0,
        }

        if self._nowcast_data:
            # 从factor_loadings获取因子数和变量数（H矩阵形状为n_variables × n_factors）
            factor_count = None
            variable_count = None
            if self._nowcast_data.factor_loadings is not None:
                variable_count = self._nowcast_data.factor_loadings.shape[0]
                factor_count = self._nowcast_data.factor_loadings.shape[1]

            info.update({
                "nowcast_data_points": len(self._nowcast_data.nowcast_series) if self._nowcast_data.nowcast_series is not None else 0,
                "target_variable": self._nowcast_data.target_variable,
                "data_period": self._nowcast_data.data_period,
                "factor_count": factor_count,
                "variable_count": variable_count,
                "has_kalman_gains": self._nowcast_data.kalman_gains_history is not None,
                "kalman_gains_timesteps": len(self._nowcast_data.kalman_gains_history) if self._nowcast_data.kalman_gains_history else 0,
            })

        return info