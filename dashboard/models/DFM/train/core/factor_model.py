# -*- coding: utf-8 -*-
"""
动态因子模型核心实现

实现基于EM算法的DFM估计
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, Callable
from dashboard.models.DFM.train.core.kalman import KalmanFilter
from dashboard.models.DFM.train.core.estimator import (
    estimate_loadings,
    estimate_transition_matrix,
    estimate_covariance_matrices,
)
from dashboard.models.DFM.train.core.models import DFMModelResult
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.utils.preprocessing import standardize_data
from dashboard.models.DFM.train.constants import (
    DEFAULT_AR1_COEFFICIENT,
    DEFAULT_Q_VARIANCE,
    DEFAULT_B_SCALE,
    R_MATRIX_MIN_VARIANCE
)


logger = get_logger(__name__)


class DFMModel:
    """动态因子模型

    使用EM算法估计DFM模型参数

    状态空间表示:
        观测方程: Z_t = Lambda * F_t + eps_t
        状态方程: F_t = A * F_{t-1} + eta_t

    Args:
        n_factors: 因子数量
        max_lags: 因子自回归最大滞后阶数
        max_iter: EM算法最大迭代次数
        tolerance: 收敛容忍度
    """

    def __init__(
        self,
        n_factors: int,
        max_lags: int = 1,
        max_iter: int = 30,
        tolerance: float = 1e-6,
        random_seed: int = 42
    ):
        self.n_factors = n_factors
        self.max_lags = max_lags
        self.max_iter = max_iter
        self.tolerance = tolerance
        self.random_seed = random_seed

        self.results_: Optional[DFMModelResult] = None

    def fit(
        self,
        data: pd.DataFrame,
        training_start: str,
        train_end: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> DFMModelResult:
        """拟合DFM模型

        Args:
            data: 观测数据 (时间 × 变量)
            training_start: 训练期开始日期（必填）
            train_end: 训练期结束日期（必填）
            progress_callback: 进度回调函数，用于报告训练进度

        Returns:
            DFMModelResult: 拟合结果

        Raises:
            ValueError: 如果training_start或train_end未提供
        """
        if not training_start or not train_end:
            raise ValueError("training_start和train_end必须提供")
        # 设置确定性随机种子
        np.random.seed(self.random_seed)

        # 根据训练期日期范围切分数据
        Z_train = data.loc[training_start:train_end]

        # 验证训练期数据有效性
        if Z_train.empty:
            raise ValueError(
                f"训练期({training_start}至{train_end})内没有数据。"
                f"请检查日期范围是否正确。数据时间范围：{data.index.min()}至{data.index.max()}"
            )

        # 数据预处理：计算中心化和标准化数据（使用训练期参数）
        obs_centered, Z_standardized_full, means, stds = self._preprocess_data(Z_train, data)

        # 仅用训练期数据进行PCA
        Z_for_pca = Z_standardized_full[:len(Z_train)]
        obs_centered_for_pca = obs_centered.iloc[:len(Z_train)]

        # 报告PCA初始化开始
        if progress_callback:
            progress_callback("[EM|5%] 开始PCA初始化...")

        # PCA初始化：得到因子、载荷和V矩阵（用于R矩阵计算）
        initial_factors, initial_loadings, V = self._initialize_factors_pca(
            Z_for_pca, obs_centered_for_pca, means, stds
        )

        # 报告PCA初始化完成
        if progress_callback:
            progress_callback("[EM|10%] PCA初始化完成")

        # 关键修复：只传递训练期数据给EM算法，避免信息渗漏
        obs_centered_train = obs_centered.loc[Z_train.index]
        self.results_ = self._em_algorithm(
            obs_centered_train,  # 仅训练期数据，避免验证期/观察期信息渗漏
            initial_factors,
            initial_loadings,
            V,  # V矩阵用于R矩阵计算
            stds,
            Z_train.index,  # 训练期索引
            progress_callback
        )

        # === 新增：对完整数据进行卡尔曼滤波 ===
        # 参数估计仅使用训练期数据（避免信息泄漏）
        # 因子估计覆盖完整时间范围（训练期 + 验证期 + 观察期）
        n_time_train = len(Z_train)
        n_time_full = len(data)

        if n_time_full > n_time_train:
            # 有验证期/观察期数据，需要对完整数据进行滤波
            full_factors, full_factor_states_predicted = self._filter_full_data(
                obs_centered,           # 完整数据（已中心化）
                self.results_,          # EM估计的参数
                n_time_train,           # 训练期长度
                progress_callback
            )

            # 更新结果中的因子和先验状态为完整时间范围
            self.results_.factors = full_factors
            self.results_.factors_smooth = full_factors
            self.results_.factor_states_predicted = full_factor_states_predicted
            self.results_.train_start_idx = 0
            self.results_.train_end_idx = n_time_train

            logger.info(f"[fit] 因子已扩展到完整时间范围: {n_time_full} 个时间点 (训练期: {n_time_train})")
        else:
            # 没有验证期/观察期，因子长度等于训练期长度
            self.results_.train_start_idx = 0
            self.results_.train_end_idx = n_time_train
            logger.info(f"[fit] 仅训练期数据，因子长度: {n_time_train}")

        return self.results_

    def _preprocess_data(
        self,
        train_data: pd.DataFrame,
        full_data: pd.DataFrame = None
    ) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
        """数据预处理：中心化和标准化（使用共享函数）

        Args:
            train_data: 训练期数据（用于计算均值和标准差）
            full_data: 完整数据（需要处理的数据），如果为None则使用train_data

        Returns:
            Tuple: (中心化数据DataFrame, 标准化数据ndarray, 均值, 标准差)
        """
        obs_centered, Z_standardized, means, stds = standardize_data(train_data, full_data)
        logger.debug(f"数据预处理完成: centered={obs_centered.shape}, standardized={Z_standardized.shape}")
        return obs_centered, Z_standardized, means, stds

    def _initialize_factors_pca(
        self,
        Z_standardized: np.ndarray,
        obs_centered: pd.DataFrame,
        means: np.ndarray,
        stds: np.ndarray
    ) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        """使用PCA初始化因子（完全匹配老代码的SVD实现）

        Args:
            Z_standardized: 标准化的观测数据 (n_time, n_obs) - 用于PCA
            obs_centered: 中心化的观测数据 (n_time, n_obs) - 用于计算载荷
            means: 均值向量
            stds: 标准差向量

        Returns:
            Tuple: (初始因子DataFrame, 初始载荷矩阵, V矩阵)
        """
        # 使用SVD分解（匹配老代码）
        U, s, Vh = np.linalg.svd(Z_standardized, full_matrices=False)

        # 初始因子 F0 = U_k * S_k （匹配老代码）
        factors_init = U[:, :self.n_factors] * s[:self.n_factors]

        # 关键修复：必须指定index，否则estimate_loadings索引错误！
        factors_df = pd.DataFrame(
            factors_init,
            index=obs_centered.index,  # 使用obs_centered的index（日期）
            columns=[f'Factor{i+1}' for i in range(self.n_factors)]
        )

        # V矩阵（用于R矩阵计算）
        V = Vh.T  # (n_obs, n_obs)

        # 关键修改：使用中心化数据（而非标准化数据）计算载荷
        # 这与老代码完全一致：calculate_factor_loadings(obs_centered, factors_init_df)
        initial_loadings = estimate_loadings(
            obs_centered,  # 使用中心化数据（匹配老代码）
            factors_df
        )

        # 检查Lambda是否有NaN行
        nan_rows = np.isnan(initial_loadings).any(axis=1)
        n_nan_rows = nan_rows.sum()

        if n_nan_rows > 0:
            # 对有NaN的行，使用SVD直接估计载荷
            # Lambda = V[:n_factors].T * sqrt(s[:n_factors])
            V_short = Vh[:self.n_factors, :].T  # (n_obs, n_factors)
            svd_loadings = V_short * np.sqrt(s[:self.n_factors])

            # 填充NaN行
            for i in np.where(nan_rows)[0]:
                logger.debug(f"变量{i}的载荷使用SVD估计")
                initial_loadings[i, :] = svd_loadings[i, :]

        # 最后检查：确保没有NaN或Inf
        if np.any(np.isnan(initial_loadings)) or np.any(np.isinf(initial_loadings)):
            raise ValueError(f"载荷矩阵仍包含NaN或Inf，无法继续。请检查输入数据质量。")

        # PCA初始化完成（静默）

        # 添加调试信息
        logger.debug(f"[PCA] 初始因子标准差: {factors_df.std().values}")
        logger.debug(f"[PCA] 初始载荷范围: [{initial_loadings.min():.2f}, {initial_loadings.max():.2f}]")

        return factors_df, initial_loadings, V

    def _initialize_em_params(
        self,
        obs_centered: pd.DataFrame,
        initial_factors: pd.DataFrame,
        initial_loadings: np.ndarray,
        V: np.ndarray,
        stds: np.ndarray
    ) -> dict:
        """初始化EM算法所需的全部参数

        Args:
            obs_centered: 中心化观测数据（仅训练期）
            initial_factors: 初始因子估计
            initial_loadings: 初始载荷矩阵
            V: SVD分解得到的V矩阵
            stds: 标准差向量

        Returns:
            dict: 包含所有初始化参数的字典
        """
        n_time, n_obs = obs_centered.shape
        n_states = self.n_factors * self.max_lags

        A, Q = self._initialize_transition_matrix(initial_factors)
        R = self._compute_R_matrix(initial_factors.values, V, stds, obs_centered)

        logger.debug(f"[初始化] R矩阵对角线前5个: {np.diag(R)[:5]}")
        logger.debug(f"[初始化] 初始Q矩阵对角线: {np.diag(Q)}")

        x0 = np.zeros(n_states)
        P0 = np.eye(n_states)
        B = np.eye(n_states) * DEFAULT_B_SCALE

        # 重置种子确保U矩阵可复现
        np.random.seed(self.random_seed)
        U = np.random.randn(n_time, n_states)

        return {
            'A': A, 'Q': Q, 'R': R, 'B': B, 'U': U,
            'x0': x0, 'P0': P0,
            'Lambda': initial_loadings.copy(),
            'n_time': n_time, 'n_obs': n_obs, 'n_states': n_states,
        }

    def _em_algorithm(
        self,
        obs_centered: pd.DataFrame,
        initial_factors: pd.DataFrame,
        initial_loadings: np.ndarray,
        V: np.ndarray,
        stds: np.ndarray,
        train_index: pd.DatetimeIndex,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> DFMModelResult:
        """EM算法估计DFM参数

        Args:
            obs_centered: 中心化观测数据（仅训练期，避免信息渗漏）
            initial_factors: 初始因子估计
            initial_loadings: 初始载荷矩阵
            V: SVD分解得到的V矩阵（用于R矩阵计算）
            stds: 标准差向量（用于计算R矩阵）
            train_index: 训练期时间索引
            progress_callback: 进度回调函数

        Returns:
            DFMModelResult: 估计结果
        """
        params = self._initialize_em_params(
            obs_centered, initial_factors, initial_loadings, V, stds
        )
        n_obs = params['n_obs']
        n_states = params['n_states']
        A, Q, R, B, U = params['A'], params['Q'], params['R'], params['B'], params['U']
        x0, P0 = params['x0'], params['P0']
        Lambda = params['Lambda']
        Z = obs_centered.values

        loglik_prev = -np.inf
        converged = False
        factors_current = initial_factors.copy()

        for iteration in range(self.max_iter):
            # 报告EM迭代进度：10% - 90%，共80%分配给max_iter次迭代
            progress_pct = 10 + int(((iteration + 1) / self.max_iter) * 80)
            if progress_callback:
                progress_callback(f"[EM|{progress_pct}%] EM迭代 {iteration + 1}/{self.max_iter}")

            logger.debug(f"EM迭代 {iteration + 1}/{self.max_iter}")

            H = np.zeros((n_obs, n_states))
            H[:, :self.n_factors] = Lambda

            # 注意：B矩阵在循环外初始化，并在M步后更新（匹配老代码）

            if iteration == 0:
                logger.debug(f"[EM初始化] 因子std={factors_current.std().values}, "
                            f"Lambda范围=[{Lambda.min():.2f}, {Lambda.max():.2f}], "
                            f"A={A.flatten()[:4]}, Q_diag={np.diag(Q)}, R_diag[:3]={np.diag(R)[:3]}")

            kf = KalmanFilter(A, B, H, Q, R, x0, P0)
            filter_result = kf.filter(Z, U)  # Z:(n_time, n_obs), U:(n_time, n_states) - 匹配train_model
            smoother_result = kf.smooth(filter_result)

            if iteration == 0:
                factors_after_kf = smoother_result.x_smoothed[:self.n_factors, :].T
                logger.debug(f"[EM初始化] Kalman滤波后因子std={np.std(factors_after_kf, axis=0)}")

            loglik_current = filter_result.loglikelihood

            if iteration > 0:
                loglik_diff = loglik_current - loglik_prev
                logger.debug(f"  LogLik: {loglik_current:.2f} (增量: {loglik_diff:.4f})")

                if abs(loglik_diff) < self.tolerance:
                    logger.info(f"EM算法收敛于迭代{iteration + 1}")
                    converged = True
                    break

            loglik_prev = loglik_current

            factors_smoothed = smoother_result.x_smoothed[:self.n_factors, :].T
            factors_df = pd.DataFrame(
                factors_smoothed,
                index=obs_centered.index,  # 关键修复：必须指定DatetimeIndex！
                columns=[f'Factor{i+1}' for i in range(self.n_factors)]
            )

            # 使用中心化数据（而非标准化数据）估计载荷
            Lambda_new = estimate_loadings(
                obs_centered,  # 使用中心化数据（匹配老代码）
                factors_df
            )

            if iteration == 0:
                logger.debug(f"[EM初始化] Lambda_new NaN数量={np.isnan(Lambda_new).sum()}")

            # 处理Lambda中的NaN：使用上一次迭代的值
            nan_rows = np.isnan(Lambda_new).any(axis=1)
            if np.any(nan_rows):
                logger.debug(f"[EM迭代{iteration}] 发现{nan_rows.sum()}行NaN，用上次Lambda替换")
                Lambda_new[nan_rows, :] = Lambda[nan_rows, :]

            # 最终检查：如果仍有NaN（第一次迭代且初始化失败），抛出错误
            if np.any(np.isnan(Lambda_new)):
                raise ValueError(
                    f"EM迭代{iteration}: Lambda仍包含NaN，无法继续。"
                    f"可能原因：数据质量不足或变量有效数据点太少。"
                )

            Lambda = Lambda_new

            A = estimate_transition_matrix(factors_smoothed, self.max_lags)

            # 估计协方差矩阵和B矩阵（使用中心化数据，匹配老代码）
            B, Q, R = estimate_covariance_matrices(
                smoother_result,
                obs_centered,  # 使用中心化数据
                Lambda,
                self.n_factors,
                A,  # 传入A矩阵用于Q矩阵计算
                n_shocks=self.n_factors  # 传入n_shocks以计算B矩阵
            )

            # 调试信息：仅在关键迭代输出简洁摘要
            if iteration in (0, 1, self.max_iter - 1):
                logger.debug(f"[EM迭代{iteration+1}] Q_diag={np.diag(Q)}, R_diag[:3]={np.diag(R)[:3]}, "
                            f"因子std={factors_df.std().values}")

            # 更新下一次迭代的初始状态（匹配老代码）
            x0 = smoother_result.x_smoothed[:, 0].copy()  # 第一个时间点的平滑状态
            P0 = smoother_result.P_smoothed[:, :, 0].copy()  # 第一个时间点的平滑协方差

            factors_current = factors_df

        return self._build_em_result(
            smoother_result, filter_result, A, Q, Lambda, R, obs_centered, converged, iteration
        )

    def _build_em_result(
        self,
        smoother_result,
        filter_result,
        A: np.ndarray,
        Q: np.ndarray,
        Lambda: np.ndarray,
        R: np.ndarray,
        obs_centered: pd.DataFrame,
        converged: bool,
        iteration: int
    ) -> DFMModelResult:
        """从EM迭代结果构建DFMModelResult

        Args:
            smoother_result: 卡尔曼平滑结果
            filter_result: 卡尔曼滤波结果
            A: 状态转移矩阵
            Q: 过程噪声协方差矩阵
            Lambda: 最终载荷矩阵
            R: 观测噪声协方差矩阵
            obs_centered: 中心化观测数据
            converged: 是否收敛
            iteration: 最终迭代次数（0-based）

        Returns:
            DFMModelResult
        """
        factors_smoothed_final = smoother_result.x_smoothed[:self.n_factors, :]
        logger.debug(f"[EM结束] 因子std={factors_smoothed_final.std(axis=1)}, "
                     f"Lambda范围=[{Lambda.min():.2f}, {Lambda.max():.2f}]")

        factor_states_predicted = filter_result.x_predicted[:, :self.n_factors].copy()
        logger.info(f"[EM结束] 提取先验因子状态: 形状={factor_states_predicted.shape}")

        return DFMModelResult(
            A=A,
            Q=Q,
            H=Lambda,
            R=R,
            factors=factors_smoothed_final,
            factors_smooth=factors_smoothed_final,
            kalman_gains_history=filter_result.kalman_gains_history,
            factor_states_predicted=factor_states_predicted,
            variable_names=obs_centered.columns.tolist(),
            converged=converged,
            iterations=iteration + 1,
            log_likelihood=filter_result.loglikelihood
        )

    def _initialize_transition_matrix(
        self,
        factors: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray]:
        """初始化状态转移矩阵A和过程噪声协方差Q

        k=1用固定值（匹配老代码），k>=2用VAR估计。

        Args:
            factors: 初始因子估计 DataFrame

        Returns:
            Tuple: (A矩阵, Q矩阵)
        """
        if self.n_factors == 1:
            # 单因子情况：使用固定初始值
            # 不使用AutoReg估计，因为初始PCA因子可能不准确，导致算法发散
            if self.max_lags == 1:
                A = np.array([[DEFAULT_AR1_COEFFICIENT]])
                Q = np.array([[DEFAULT_Q_VARIANCE]])
            else:
                # AR(p) companion form
                A = np.zeros((self.max_lags, self.max_lags))
                A[0, :] = DEFAULT_AR1_COEFFICIENT / self.max_lags
                if self.max_lags > 1:
                    A[1:, :-1] = np.eye(self.max_lags - 1)
                Q = np.zeros((self.max_lags, self.max_lags))
                Q[0, 0] = DEFAULT_Q_VARIANCE
        else:
            # 多因子情况：使用VAR模型估计
            from statsmodels.tsa.api import VAR
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='.*No frequency information.*')
                var_model = VAR(factors.dropna())
                var_results = var_model.fit(self.max_lags)

            if self.max_lags == 1:
                A = var_results.coefs[0]
            else:
                # VAR(p): 构造companion form矩阵
                n_factors_orig = factors.shape[1]
                A = np.zeros((n_factors_orig * self.max_lags, n_factors_orig * self.max_lags))
                for lag in range(self.max_lags):
                    A[:n_factors_orig, lag*n_factors_orig:(lag+1)*n_factors_orig] = var_results.coefs[lag]
                if self.max_lags > 1:
                    A[n_factors_orig:, :-n_factors_orig] = np.eye(n_factors_orig * (self.max_lags - 1))

            Q = np.cov(var_results.resid, rowvar=False)
            Q = np.diag(np.maximum(np.diag(Q), R_MATRIX_MIN_VARIANCE))

        return A, Q

    def _compute_R_matrix(
        self,
        factors: np.ndarray,
        V: np.ndarray,
        stds: np.ndarray,
        obs_centered: pd.DataFrame
    ) -> np.ndarray:
        """计算R矩阵（完全匹配老代码DynamicFactorModel.py line 357-382）

        Args:
            factors: 因子矩阵 (n_time, n_factors)
            V: SVD的V矩阵 (n_obs, n_obs)
            stds: 标准差向量 (n_obs,)
            obs_centered: 中心化观测数据 (n_time, n_obs)

        Returns:
            R矩阵 (n_obs, n_obs)
        """
        # 匹配老代码line 357-382的实现
        # 计算标准化数据的重构和残差
        z_standardized = (obs_centered / stds).fillna(0).values  # (n_time, n_obs)

        # 重构标准化数据：factors @ V[:, :n_factors].T
        reconstructed_z = factors @ V[:, :self.n_factors].T  # (n_time, n_obs)
        residuals_z = z_standardized - reconstructed_z

        # R矩阵：标准化残差的方差 * 原始标准差的平方
        psi_diag = np.nanvar(residuals_z, axis=0)  # 标准化残差的方差
        original_std_sq = stds ** 2  # 原始标准差的平方
        R_diag_current = psi_diag * original_std_sq  # 恢复到原始尺度
        R_diag_current = np.maximum(R_diag_current, R_MATRIX_MIN_VARIANCE)  # 确保正定性

        return np.diag(R_diag_current)

    def _filter_full_data(
        self,
        obs_centered_full: pd.DataFrame,
        em_result: DFMModelResult,
        train_length: int,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        使用EM估计的参数对完整数据进行卡尔曼滤波/平滑

        Args:
            obs_centered_full: 完整中心化数据 (n_time_full, n_obs)
            em_result: EM估计结果（包含参数 A, Q, H, R）
            train_length: 训练期长度（用于记录索引）
            progress_callback: 进度回调函数

        Returns:
            Tuple: (完整时间范围的因子, 完整时间范围的先验因子状态)
                   - factors: (n_factors, n_time_full)
                   - factor_states_predicted: (n_time_full, n_factors)
        """
        n_time_full = len(obs_centered_full)
        n_obs = obs_centered_full.shape[1]
        n_states = self.n_factors * self.max_lags

        if progress_callback:
            progress_callback(f"[EM|95%] 对完整数据({n_time_full}个时间点)进行卡尔曼滤波...")

        # 构建观测矩阵H（扩展到状态空间维度）
        H_full = np.zeros((n_obs, n_states))
        H_full[:, :self.n_factors] = em_result.H

        # 初始状态：使用零向量（标准做法）
        x0 = np.zeros(n_states)
        P0 = np.eye(n_states)

        # 外部输入U（与EM算法保持一致）
        np.random.seed(self.random_seed)
        U = np.random.randn(n_time_full, n_states)

        # B矩阵（与EM算法保持一致）
        B = np.eye(n_states) * DEFAULT_B_SCALE

        # 创建卡尔曼滤波器
        kf = KalmanFilter(
            A=em_result.A,
            B=B,
            H=H_full,
            Q=em_result.Q,
            R=em_result.R,
            x0=x0,
            P0=P0
        )

        # 滤波和平滑
        Z = obs_centered_full.values  # (n_time_full, n_obs)
        filter_result = kf.filter(Z, U)
        smoother_result = kf.smooth(filter_result)

        if progress_callback:
            progress_callback(f"[EM|98%] 完整数据滤波完成")

        logger.info(f"[完整数据滤波] 因子形状: ({self.n_factors}, {n_time_full}), 训练期长度: {train_length}")

        # 提取先验因子状态 (n_time_full, n_factors)
        factor_states_predicted = filter_result.x_predicted[:, :self.n_factors].copy()

        # 提取因子 (n_factors, n_time_full)
        factors = smoother_result.x_smoothed[:self.n_factors, :]

        return factors, factor_states_predicted
