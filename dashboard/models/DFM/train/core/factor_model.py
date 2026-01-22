# -*- coding: utf-8 -*-
"""
动态因子模型核心实现

实现基于EM算法的DFM估计
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, Callable
from sklearn.decomposition import PCA
from dashboard.models.DFM.train.core.kalman import KalmanFilter
from dashboard.models.DFM.train.core.estimator import (
    estimate_loadings,
    estimate_transition_matrix,
    estimate_covariance_matrices,
    _ensure_positive_definite
)
from dashboard.models.DFM.train.core.models import DFMModelResult
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.constants import (
    ZERO_STD_REPLACEMENT,
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

        Z_orig = data.copy()

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

        self.results_ = self._em_algorithm(
            obs_centered,  # 使用中心化数据进行EM算法
            initial_factors,
            initial_loadings,
            V,  # V矩阵用于R矩阵计算
            stds,
            data.index,
            Z_train.index,
            progress_callback
        )

        return self.results_

    def _preprocess_data(
        self,
        train_data: pd.DataFrame,
        full_data: pd.DataFrame = None
    ) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
        """数据预处理：中心化和标准化（匹配老代码实现）

        Args:
            train_data: 训练期数据（用于计算均值和标准差）
            full_data: 完整数据（需要处理的数据），如果为None则使用train_data

        Returns:
            Tuple: (中心化数据DataFrame, 标准化数据ndarray, 均值, 标准差)
        """
        if full_data is None:
            full_data = train_data

        # 使用训练期数据计算均值和标准差
        means = train_data.mean(skipna=True).values
        stds = train_data.std(skipna=True).values

        # 处理零标准差
        stds = np.where(stds > 0, stds, ZERO_STD_REPLACEMENT)

        # 中心化数据（匹配老代码obs_centered）
        obs_centered = full_data - means

        # 标准化数据并填充NaN为0（匹配老代码的z）
        Z_standardized = (obs_centered / stds).fillna(0).values

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
        from dashboard.models.DFM.train.core.estimator import estimate_loadings

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

    def _em_algorithm(
        self,
        obs_centered: pd.DataFrame,
        initial_factors: pd.DataFrame,
        initial_loadings: np.ndarray,
        V: np.ndarray,
        stds: np.ndarray,
        index: pd.DatetimeIndex,
        train_index: pd.DatetimeIndex,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> DFMModelResult:
        """EM算法估计DFM参数（匹配老代码）

        Args:
            obs_centered: 中心化观测数据（DataFrame）
            initial_factors: 初始因子估计
            initial_loadings: 初始载荷矩阵
            V: SVD分解得到的V矩阵（用于R矩阵计算）
            stds: 标准差向量（用于计算R矩阵）
            index: 完整数据时间索引
            train_index: 训练期时间索引
            progress_callback: 进度回调函数

        Returns:
            DFMModelResult: 估计结果
        """
        n_time, n_obs = obs_centered.shape
        Z = obs_centered.values  # (n_time, n_obs)格式,匹配train_model
        n_states = self.n_factors * self.max_lags

        factors_current = initial_factors.copy()

        # 使用初始载荷矩阵
        Lambda = initial_loadings.copy()

        # 初始化A矩阵和Q矩阵
        # 关键修复：k=1用固定值（匹配老代码），k>=2用VAR估计
        if self.n_factors == 1:
            # 单因子情况：使用固定初始值（匹配老代码line 354-355）
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
            # 多因子情况：使用VAR模型估计（保持原逻辑，已验证成功）
            from statsmodels.tsa.api import VAR
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='.*No frequency information.*')
                var_model = VAR(factors_current.dropna())
                var_results = var_model.fit(self.max_lags)

            # 使用VAR系数初始化A矩阵（完全匹配老代码line 322）
            if self.max_lags == 1:
                A = var_results.coefs[0]
            else:
                # VAR(p): 构造companion form矩阵
                n_factors_orig = factors_current.shape[1]
                A = np.zeros((n_factors_orig * self.max_lags, n_factors_orig * self.max_lags))
                # 填充VAR系数
                for lag in range(self.max_lags):
                    A[:n_factors_orig, lag*n_factors_orig:(lag+1)*n_factors_orig] = var_results.coefs[lag]
                # 构造companion form下半部分
                if self.max_lags > 1:
                    A[n_factors_orig:, :-n_factors_orig] = np.eye(n_factors_orig * (self.max_lags - 1))

            # 使用VAR残差计算初始Q矩阵（匹配老代码）
            Q = np.cov(var_results.resid, rowvar=False)
            Q = np.diag(np.maximum(np.diag(Q), R_MATRIX_MIN_VARIANCE))

        # 计算R矩阵（匹配老代码：psi_diag * obs_std^2）
        # 只使用训练期数据计算R矩阵
        obs_centered_for_R = obs_centered.loc[train_index] if len(train_index) < len(index) else obs_centered
        R = self._compute_R_matrix(initial_factors.values, V, stds, obs_centered_for_R)

        # 调试：打印初始R矩阵
        logger.debug(f"[初始化] R矩阵对角线前5个: {np.diag(R)[:5]}")
        logger.debug(f"[初始化] 初始Q矩阵对角线: {np.diag(Q)}")

        loglik_prev = -np.inf
        converged = False

        # 初始化Kalman滤波的初始状态（匹配老代码）
        x0 = np.zeros(n_states)
        P0 = np.eye(n_states)

        # 初始化B矩阵（匹配老代码line 393: B_current = np.eye(n_factors) * 0.1）
        B = np.eye(n_states) * DEFAULT_B_SCALE

        # 生成外部shock矩阵U（完全匹配老代码默认行为）
        # 老代码有个Python陷阱：if error: 将字符串'False'当作True处理！
        # 所以即使error='False'，也会生成随机U矩阵
        # 为了保持一致性，这里也生成相同的随机U矩阵
        DFM_SEED = 42  # 匹配老代码的种子
        np.random.seed(DFM_SEED)
        # 注意：老代码U shape是(n_time, n_shocks)，这里n_shocks=n_factors=n_states（max_lags=1时）
        U = np.random.randn(n_time, n_states)  # (n_time, n_states)格式,匹配train_model

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
                logger.debug(f"[EM第0次] Kalman滤波前, 当前因子标准差: {factors_current.std().values}")
                logger.debug(f"[EM第0次] obs_centered.shape = {obs_centered.shape}, dtype = {obs_centered.values.dtype}")
                logger.debug(f"[EM第0次] obs_centered[:3, :3] =\n{obs_centered.values[:3, :3]}")
                logger.debug(f"[EM第0次] Lambda.shape = {Lambda.shape}, dtype = {Lambda.dtype}")
                logger.debug(f"[EM第0次] Lambda[:3, :] =\n{Lambda[:3, :]}")
                logger.debug(f"[EM第0次] B.shape = {B.shape}, dtype = {B.dtype}")
                logger.debug(f"[EM第0次] B =\n{B}")
                logger.debug(f"[EM第0次] A.dtype = {A.dtype}, Q.dtype = {Q.dtype}, R.dtype = {R.dtype}")
                logger.debug(f"[EM第0次] A =\n{A}")
                logger.debug(f"[EM第0次] Q_diag = {np.diag(Q)}")
                logger.debug(f"[EM第0次] R_diag[:5] = {np.diag(R)[:5]}")
                logger.debug(f"[EM第0次] x0 = {x0}, dtype = {x0.dtype}")
                logger.debug(f"[EM第0次] P0_diag = {np.diag(P0)}, dtype = {P0.dtype}")

            kf = KalmanFilter(A, B, H, Q, R, x0, P0)
            filter_result = kf.filter(Z, U)  # Z:(n_time, n_obs), U:(n_time, n_states) - 匹配train_model
            smoother_result = kf.smooth(filter_result)

            if iteration == 0:
                factors_after_kf = smoother_result.x_smoothed[:self.n_factors, :].T
                logger.debug(f"[EM第0次] Kalman滤波后, 因子标准差: {np.std(factors_after_kf, axis=0)}")

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
                logger.debug(f"[EM第0次] estimate_loadings返回的Lambda_new[:3, :] =\n{Lambda_new[:3, :]}")
                logger.debug(f"[EM第0次] Lambda_new中NaN数量: {np.isnan(Lambda_new).sum()}")

            # 处理Lambda中的NaN：使用上一次迭代的值
            nan_rows = np.isnan(Lambda_new).any(axis=1)
            if np.any(nan_rows):
                if iteration == 0:
                    logger.debug(f"[EM第0次] 发现{nan_rows.sum()}行包含NaN，用初始Lambda替换")
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

            # 调试信息：打印第1、2、30次迭代的Q和R
            if iteration == 0 or iteration == 1 or iteration == 29:
                logger.debug(f"[EM第{iteration+1}次迭代] Q矩阵对角线: {np.diag(Q)}")
                logger.debug(f"[EM第{iteration+1}次迭代] R矩阵对角线前5个: {np.diag(R)[:5]}")
                logger.debug(f"[EM第{iteration+1}次迭代] Lambda[:3, :] =\n{Lambda[:3, :]}")
                logger.debug(f"[EM第{iteration+1}次迭代] A =\n{A}")
                logger.debug(f"[EM第{iteration+1}次迭代] 因子标准差: {factors_df.std().values}")
                logger.debug(f"[EM第{iteration+1}次迭代] 因子前3行:\n{factors_df.values[:3, :]}")

            # 更新下一次迭代的初始状态（匹配老代码）
            x0 = smoother_result.x_smoothed[:, 0].copy()  # 第一个时间点的平滑状态
            P0 = smoother_result.P_smoothed[:, :, 0].copy()  # 第一个时间点的平滑协方差

            factors_current = factors_df

        # 提取平滑因子（n_factors × n_time格式）
        factors_smoothed_final = smoother_result.x_smoothed[:self.n_factors, :]  # (n_factors, n_time)

        # 添加调试信息
        logger.debug(f"[EM结束] 最终因子标准差: {factors_smoothed_final.std(axis=1)}")
        logger.debug(f"[EM结束] 最终载荷范围: [{Lambda.min():.2f}, {Lambda.max():.2f}]")

        # 提取先验因子状态（用于新闻分解的expected_value计算）
        # x_predicted形状: (n_time, n_states)，n_states = n_factors * max_lags
        # 只取前n_factors列
        factor_states_predicted = filter_result.x_predicted[:, :self.n_factors].copy()
        logger.info(f"[EM结束] 提取先验因子状态: 形状={factor_states_predicted.shape}")

        # 返回统一的DFMModelResult
        return DFMModelResult(
            A=A,
            Q=Q,
            H=Lambda,
            R=R,
            factors=factors_smoothed_final,  # (n_factors, n_time)
            factors_smooth=factors_smoothed_final,  # 同上
            kalman_gains_history=filter_result.kalman_gains_history,  # 保存卡尔曼增益历史
            factor_states_predicted=factor_states_predicted,  # 先验因子状态 (n_time, n_factors)
            variable_names=obs_centered.columns.tolist(),  # 保存训练时使用的变量名列表
            converged=converged,
            iterations=iteration + 1,
            log_likelihood=loglik_current
        )

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
