# -*- coding: utf-8 -*-
"""
配置管理模块

提供统一的训练配置类和验证
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dashboard.models.DFM.train.utils.parallel_config import ParallelConfig


@dataclass
class TrainingConfig:
    """完整训练配置

    包含DFM模型训练所需的全部配置参数,与trainer.py配合使用
    """
    # ========== 必填字段（无默认值） ==========
    # 核心配置
    data_path: str
    target_variable: str

    # 训练/验证期配置
    training_start: str  # 训练期开始日期
    train_end: str  # 训练期结束日期
    validation_start: str  # 验证期开始日期
    validation_end: str  # 验证期结束日期

    # 观察期配置（DDFM专用）
    observation_start: Optional[str] = None  # 观察期开始日期
    observation_end: Optional[str] = None    # 观察期结束日期

    # ========== 可选字段（有默认值） ==========
    # 核心配置
    selected_indicators: List[str] = field(default_factory=list)
    target_freq: str = 'W-FRI'

    # 模型参数
    k_factors: int = 4
    max_iterations: int = 30
    max_lags: int = 1
    tolerance: float = 1e-6

    # 变量选择配置
    enable_variable_selection: bool = False
    variable_selection_method: str = 'backward'
    min_variables_after_selection: int = 1

    # 因子数选择配置
    factor_selection_method: str = 'fixed'  # fixed, cumulative, kaiser
    pca_threshold: float = 0.9  # cumulative方法的阈值
    kaiser_threshold: float = 1.0  # kaiser方法的特征值阈值

    # 并行计算配置（2025-11-08重构后默认启用）
    enable_parallel: bool = True  # 是否启用并行计算（重构后已解决序列化问题）
    n_jobs: int = -1  # 并行任务数（-1=所有核心，1=串行）
    parallel_backend: str = 'loky'  # 并行后端（loky, multiprocessing, threading）
    min_variables_for_parallel: int = 5  # 启用并行的最小变量数

    # 输出配置
    output_dir: Optional[str] = None

    # 目标变量配对模式（2025-12新增）
    target_alignment_mode: str = 'next_month'  # 'current_month'(本月) 或 'next_month'(下月)

    # Win Rate优化配置（2025-12-19新增）
    rmse_tolerance_percent: float = 1.0  # RMSE相近的容忍度（百分比）
    win_rate_tolerance_percent: float = 5.0  # Win Rate相近的容忍度（百分比），用于胜率优先策略

    # 筛选策略配置（2025-12-20新增）
    selection_criterion: str = 'hybrid'  # 筛选标准: 'rmse', 'win_rate', 'hybrid'
    prioritize_win_rate: Optional[bool] = True  # 混合策略时的优先级，仅hybrid模式有效

    # 训练期权重配置（2025-12-20新增）
    training_weight: float = 0.5  # 训练期权重 (0.0-1.0)，验证期权重自动为 1-training_weight

    # ========== 算法选择配置（2025-12-21新增）==========
    algorithm: str = 'classical'  # 算法类型: 'classical'(经典EM算法) 或 'deep_learning'(深度学习)

    # ========== DDFM专用参数（仅当algorithm='deep_learning'时生效）==========
    # 自编码器结构
    encoder_structure: Tuple[int, ...] = (16, 4)  # 编码器层结构，最后一个数为因子数
    decoder_structure: Optional[Tuple[int, ...]] = None  # 解码器层结构(None=对称单层线性)
    use_bias: bool = True  # 解码器最后一层是否使用偏置
    batch_norm: bool = True  # 是否使用批量归一化
    activation: str = 'relu'  # 激活函数: 'relu', 'tanh', 'sigmoid'

    # 因子动态
    factor_order: int = 2  # 因子AR阶数(1或2)
    lags_input: int = 0  # 输入滞后期数

    # 训练参数
    learning_rate: float = 0.005  # 学习率
    ddfm_optimizer: str = 'Adam'  # 优化器: 'Adam', 'SGD'
    decay_learning_rate: bool = True  # 是否使用学习率衰减
    epochs_per_mcmc: int = 100  # 每次MCMC迭代的epoch数
    batch_size: int = 100  # 批量大小
    mcmc_max_iter: int = 200  # MCMC最大迭代次数
    mcmc_tolerance: float = 0.0005  # MCMC收敛阈值
    display_interval: int = 10  # 显示间隔

    # 随机种子
    ddfm_seed: int = 3  # DDFM随机种子
    dfm_random_seed: int = 42  # 经典DFM随机种子

    # 行业映射（用于R²分析）
    industry_map: Optional[Dict[str, str]] = None

    def __post_init__(self):
        """后初始化验证"""
        # 设置默认输出目录
        if self.output_dir is None:
            self.output_dir = str(Path.cwd() / "dfm_output")

        # 验证必填字段
        if not self.data_path:
            raise ValueError("data_path不能为空")
        if not self.target_variable:
            raise ValueError("target_variable不能为空")

        # 验证数据文件存在
        data_file = Path(self.data_path)
        if not data_file.exists():
            raise FileNotFoundError(f"数据文件不存在: {self.data_path}")

        # 验证模型参数
        if self.k_factors <= 0:
            raise ValueError(f"k_factors必须为正数,当前值: {self.k_factors}")
        if self.max_iterations <= 0:
            raise ValueError(f"max_iterations必须为正数,当前值: {self.max_iterations}")
        if self.max_lags < 1:
            raise ValueError(f"max_lags必须>=1,当前值: {self.max_lags}")

        # 验证因子选择方法
        valid_methods = ['fixed', 'cumulative', 'kaiser']
        if self.factor_selection_method not in valid_methods:
            raise ValueError(
                f"factor_selection_method必须是{valid_methods}之一,"
                f"当前值: {self.factor_selection_method}"
            )

        # 验证变量选择方法
        if self.enable_variable_selection:
            valid_selection_methods = ['backward', 'forward', 'stepwise', 'none']
            if self.variable_selection_method not in valid_selection_methods:
                raise ValueError(
                    f"variable_selection_method必须是{valid_selection_methods}之一,"
                    f"当前值: {self.variable_selection_method}"
                )

        # 验证并行配置
        if self.n_jobs == 0:
            raise ValueError("n_jobs不能为0，使用-1表示所有核心，1表示串行")
        valid_backends = ['loky', 'multiprocessing', 'threading']
        if self.parallel_backend not in valid_backends:
            raise ValueError(
                f"parallel_backend必须是{valid_backends}之一,"
                f"当前值: {self.parallel_backend}"
            )

        # 验证目标配对模式（2025-12）
        valid_alignment_modes = ['current_month', 'next_month']
        if self.target_alignment_mode not in valid_alignment_modes:
            raise ValueError(
                f"target_alignment_mode必须是{valid_alignment_modes}之一,"
                f"当前值: {self.target_alignment_mode}"
            )

        # 验证Win Rate配置（2025-12-19）
        if self.rmse_tolerance_percent < 0 or self.rmse_tolerance_percent > 100:
            raise ValueError(
                f"rmse_tolerance_percent必须在0-100之间，"
                f"当前值: {self.rmse_tolerance_percent}"
            )
        if self.win_rate_tolerance_percent < 0 or self.win_rate_tolerance_percent > 100:
            raise ValueError(
                f"win_rate_tolerance_percent必须在0-100之间，"
                f"当前值: {self.win_rate_tolerance_percent}"
            )

        # 验证筛选策略配置（2025-12-20）
        valid_criteria = ['rmse', 'win_rate', 'hybrid']
        if self.selection_criterion not in valid_criteria:
            raise ValueError(
                f"selection_criterion必须是{valid_criteria}之一，"
                f"当前值: {self.selection_criterion}"
            )

        # 验证训练期权重（2025-12-20）
        if not 0.0 <= self.training_weight <= 1.0:
            raise ValueError(
                f"training_weight必须在0.0到1.0之间，"
                f"当前值: {self.training_weight}"
            )

        # 验证算法选择（2025-12-21）
        valid_algorithms = ['classical', 'deep_learning']
        if self.algorithm not in valid_algorithms:
            raise ValueError(
                f"algorithm必须是{valid_algorithms}之一，"
                f"当前值: {self.algorithm}"
            )

        # 验证DDFM专用参数（仅当algorithm='deep_learning'时）
        if self.algorithm == 'deep_learning':
            # 验证因子阶数
            if self.factor_order not in [1, 2]:
                raise ValueError(
                    f"factor_order必须为1或2，当前值: {self.factor_order}"
                )
            # 验证编码器结构
            if not self.encoder_structure or len(self.encoder_structure) < 1:
                raise ValueError("encoder_structure不能为空")
            # 验证所有层的神经元数都为正整数
            for i, neurons in enumerate(self.encoder_structure):
                if not isinstance(neurons, int) or neurons <= 0:
                    raise ValueError(
                        f"encoder_structure第{i+1}层神经元数必须为正整数，"
                        f"当前值: {neurons}"
                    )
            # 验证激活函数
            valid_activations = ['relu', 'tanh', 'sigmoid']
            if self.activation not in valid_activations:
                raise ValueError(
                    f"activation必须是{valid_activations}之一，"
                    f"当前值: {self.activation}"
                )
            # 验证优化器
            valid_optimizers = ['Adam', 'SGD']
            if self.ddfm_optimizer not in valid_optimizers:
                raise ValueError(
                    f"ddfm_optimizer必须是{valid_optimizers}之一，"
                    f"当前值: {self.ddfm_optimizer}"
                )
            # 验证学习率
            if self.learning_rate <= 0 or self.learning_rate > 1:
                raise ValueError(
                    f"learning_rate必须在(0, 1]范围内，当前值: {self.learning_rate}"
                )
            # 验证输入滞后期
            if self.lags_input < 0:
                raise ValueError(
                    f"lags_input必须>=0，当前值: {self.lags_input}"
                )
            # 验证批量大小
            if self.batch_size <= 0:
                raise ValueError(
                    f"batch_size必须>0，当前值: {self.batch_size}"
                )
            # 验证MCMC迭代次数
            if self.mcmc_max_iter <= 0:
                raise ValueError(
                    f"mcmc_max_iter必须>0，当前值: {self.mcmc_max_iter}"
                )
            # 验证每次MCMC的epoch数
            if self.epochs_per_mcmc <= 0:
                raise ValueError(
                    f"epochs_per_mcmc必须>0，当前值: {self.epochs_per_mcmc}"
                )
            # DDFM不支持变量选择
            if self.enable_variable_selection:
                raise ValueError(
                    "深度学习算法(DDFM)不支持变量选择，"
                    "请设置enable_variable_selection=False"
                )

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'TrainingConfig':
        """从字典创建配置

        Args:
            config_dict: 配置字典

        Returns:
            TrainingConfig对象
        """
        # 直接使用字典的键值对创建配置对象
        # dataclass会自动处理字段映射
        return cls(**config_dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            配置字典
        """
        from dataclasses import asdict
        return asdict(self)

    def validate(self) -> List[str]:
        """验证配置完整性

        Returns:
            错误信息列表,空列表表示验证通过
        """
        errors = []

        try:
            # 调用__post_init__进行验证
            self.__post_init__()
        except Exception as e:
            errors.append(str(e))

        return errors

    def get_parallel_config(self) -> ParallelConfig:
        """获取并行配置对象

        Returns:
            ParallelConfig对象
        """
        return ParallelConfig(
            enabled=self.enable_parallel,
            n_jobs=self.n_jobs,
            backend=self.parallel_backend,
            verbose=0,
            min_variables_for_parallel=self.min_variables_for_parallel
        )

    def __repr__(self) -> str:
        """字符串表示"""
        base_repr = (
            f"TrainingConfig(\n"
            f"  data_path={self.data_path},\n"
            f"  target_variable={self.target_variable},\n"
            f"  indicators={len(self.selected_indicators)},\n"
            f"  algorithm={self.algorithm},\n"
        )
        if self.algorithm == 'deep_learning':
            base_repr += (
                f"  encoder_structure={self.encoder_structure},\n"
                f"  factor_order={self.factor_order},\n"
            )
        else:
            base_repr += (
                f"  k_factors={self.k_factors},\n"
                f"  factor_selection={self.factor_selection_method},\n"
                f"  variable_selection={self.enable_variable_selection},\n"
            )
        base_repr += ")"
        return base_repr
