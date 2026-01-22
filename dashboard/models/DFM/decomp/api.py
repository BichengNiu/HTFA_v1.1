# -*- coding: utf-8 -*-
"""
DFM影响分解API接口

提供与前端UI兼容的execute_news_analysis函数，实现完整的
数据发布影响分析流程。
"""

import os
import tempfile
import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import traceback

from .core.model_loader import ModelLoader, SavedNowcastData
from .core.nowcast_extractor import NowcastExtractor
from .core.impact_analyzer import ImpactAnalyzer, DataRelease
from .core.news_impact_calculator import NewsImpactCalculator, NewsContribution
from .core.prior_predictor import ObservationPriorPredictor
from .utils.industry_aggregator import IndustryAggregator
from .utils.data_flow_formatter import DataFlowFormatter
from .utils.exceptions import DecompError, ModelLoadError, ComputationError, ValidationError
from .utils.constants import NORMALIZATION_ZERO_THRESHOLD
from .utils.helpers import get_month_date_range

logger = logging.getLogger(__name__)


def execute_news_analysis(
    dfm_model_file_content: bytes,
    dfm_metadata_file_content: bytes,
    target_month: str,
    base_workspace_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    执行影响分解的主要入口函数

    核心功能：分析新数据发布对已有nowcast值的影响

    Args:
        dfm_model_file_content: 包含已计算nowcast值的DFM模型文件字节内容
        dfm_metadata_file_content: 模型元数据文件字节内容
        target_month: 目标分析月份 (YYYY-MM格式)
        base_workspace_dir: 工作目录（可选）

    Returns:
        Dict包含:
        - returncode: int (0=成功, 非0=失败)
        - csv_paths: Dict[str, str]
            - 'impacts': 数据发布影响CSV
            - 'contributions': 贡献分解CSV
        - summary: Dict[str, Any]
            - 'total_impact': 总影响值
            - 'total_releases': 数据发布总数
            - 'positive_impact_sum': 正向影响总和
            - 'negative_impact_sum': 负向影响总和
            - 'top_contributors': 主要贡献变量
            - 'industry_breakdown': 按行业分解的统计
        - data_flow: List[Dict] - 数据流结构（按日期分组）
        - error_message: Optional[str]
    """
    try:
        logger.info(f"开始执行影响分解: 目标月份={target_month}")

        # 验证输入参数
        _validate_input_parameters(dfm_model_file_content, dfm_metadata_file_content, target_month)

        # 创建工作目录
        workspace_dir = _create_workspace_directory(base_workspace_dir)

        # 阶段1: 加载模型和数据
        logger.info("阶段1: 加载模型和数据")
        model_loader = ModelLoader()
        model = model_loader.load_model(dfm_model_file_content)
        metadata = model_loader.load_metadata(dfm_metadata_file_content)

        # 验证模型兼容性
        model_loader.validate_model_compatibility(model, metadata)

        # 提取nowcast数据
        saved_nowcast_data = model_loader.extract_saved_nowcast()

        # 阶段2: 初始化分析器
        logger.info("阶段2: 初始化分析器")
        nowcast_extractor = NowcastExtractor(saved_nowcast_data)
        impact_analyzer = ImpactAnalyzer(nowcast_extractor)
        news_calculator = NewsImpactCalculator(impact_analyzer)

        # 阶段2.5: 创建先验预测器
        logger.info("阶段2.5: 创建先验预测器")
        prior_predictor = ObservationPriorPredictor(
            factor_states_predicted=saved_nowcast_data.factor_states_predicted,
            factor_loadings=saved_nowcast_data.factor_loadings,
            variable_index_map=saved_nowcast_data.variable_index_map,
            time_index=saved_nowcast_data.prepared_data.index
        )
        logger.debug("先验预测器创建成功")

        # 阶段3: 提取真实数据发布（仅当月）
        logger.info("阶段3: 提取真实数据发布")
        target_date = pd.to_datetime(target_month)
        data_releases = _extract_real_data_releases(saved_nowcast_data, target_month, prior_predictor)

        # 阶段4: 执行影响分析
        logger.info("阶段4: 执行影响分析")
        contributions = news_calculator.calculate_news_contributions(data_releases, target_date)

        # 阶段4.5: 归一化影响值到实际Nowcast变化
        logger.info("阶段4.5: 归一化影响值")
        contributions, normalization_info = _normalize_impacts_to_actual_change(
            contributions,
            saved_nowcast_data.nowcast_series,
            target_date
        )

        # 阶段5: 生成分析结果（包括行业聚合和数据流）
        logger.info("阶段5: 生成分析结果")
        analysis_results = _generate_analysis_results(
            news_calculator, contributions, target_date, workspace_dir,
            saved_nowcast_data.var_industry_map, saved_nowcast_data.nowcast_series,
            normalization_info
        )

        # 读取CSV内容到内存中（避免下载时的文件访问问题）
        csv_contents = {}
        for csv_key, csv_path in analysis_results['csv_paths'].items():
            if os.path.exists(csv_path):
                with open(csv_path, 'rb') as f:
                    csv_contents[csv_key] = f.read()

        # 构建返回结果
        result = {
            'returncode': 0,
            'csv_paths': analysis_results['csv_paths'],
            'csv_contents': csv_contents,
            'summary': analysis_results['summary'],
            'data_flow': analysis_results['data_flow'],
            'workspace_dir': workspace_dir
        }

        logger.info(f"影响分解执行成功: 总影响={analysis_results['summary']['total_impact']:.4f}")
        return result

    except (DecompError, ModelLoadError, ComputationError, ValidationError) as e:
        error_msg = f"影响分解执行失败: {str(e)}"
        logger.error(error_msg)
        logger.debug(f"详细错误: {traceback.format_exc()}")

        return {
            'returncode': -1,
            'error_message': error_msg,
            'csv_paths': {},
            'summary': {},
            'data_flow': []
        }


def _normalize_impacts_to_actual_change(
    contributions: List,
    nowcast_series: pd.Series,
    target_date: pd.Timestamp
) -> Tuple[List, Dict[str, Any]]:
    """
    将影响值归一化到实际的Nowcast变化

    由于observed_value和expected_value量纲不一致导致的尺度偏差，
    通过事后归一化确保：总影响 = 最新Nowcast - 第一次Nowcast

    Args:
        contributions: 原始贡献列表
        nowcast_series: Nowcast时间序列
        target_date: 目标分析日期

    Returns:
        (归一化后的贡献列表, 归一化信息字典)
    """
    # 计算目标月份的日期范围
    month_start, month_end = get_month_date_range(target_date)

    # 筛选目标月份的nowcast值
    month_nowcast = nowcast_series[(nowcast_series.index >= month_start) &
                                    (nowcast_series.index <= month_end)]

    if len(month_nowcast) < 2:
        raise ComputationError(
            f"目标月份 {target_date.strftime('%Y-%m')} 数据点不足（需要至少2个，实际{len(month_nowcast)}个），"
            "无法计算归一化因子。请检查nowcast_series是否包含该月份的数据。"
        )

    # 获取第一次和最后一次nowcast值
    first_nowcast = float(month_nowcast.iloc[0])
    last_nowcast = float(month_nowcast.iloc[-1])
    actual_change = last_nowcast - first_nowcast

    # 计算原始累加影响
    raw_total_impact = sum(c.impact_value for c in contributions)

    # 计算归一化因子
    if abs(raw_total_impact) < NORMALIZATION_ZERO_THRESHOLD:
        raise ComputationError(
            f"原始累加影响接近0（{raw_total_impact:.2e}），无法计算有意义的归一化因子。"
            "这表明影响计算可能存在问题，请检查数据发布和卡尔曼增益。"
        )

    # 特殊情况：Nowcast无变化
    if abs(actual_change) < NORMALIZATION_ZERO_THRESHOLD:
        raise ComputationError(
            f"目标月份Nowcast无变化（first={first_nowcast:.4f}, last={last_nowcast:.4f}），"
            f"但原始影响累加为{raw_total_impact:.4f}。这是异常情况，请检查数据完整性。"
        )

    scale_factor = actual_change / raw_total_impact

    # 归一化所有影响值
    normalized_contributions = []
    total_abs_normalized = sum(abs(c.impact_value * scale_factor) for c in contributions)

    for contrib in contributions:
        normalized_impact = contrib.impact_value * scale_factor

        # 重新计算贡献百分比（total_abs_normalized必定>0，因为actual_change和raw_total_impact都非零）
        new_pct = abs(normalized_impact) / total_abs_normalized * 100

        normalized_contrib = NewsContribution(
            variable_name=contrib.variable_name,
            impact_value=normalized_impact,
            contribution_pct=new_pct,
            is_positive=normalized_impact > 0,
            release_date=contrib.release_date,
            observed_value=contrib.observed_value,
            expected_value=contrib.expected_value,
            kalman_weight=contrib.kalman_weight,
            confidence_interval=contrib.confidence_interval
        )
        normalized_contributions.append(normalized_contrib)

    normalization_info = {
        'first_nowcast': first_nowcast,
        'last_nowcast': last_nowcast,
        'actual_change': actual_change,
        'raw_total_impact': raw_total_impact,
        'scale_factor': scale_factor
    }

    logger.info(f"影响归一化: first={first_nowcast:.4f}, last={last_nowcast:.4f}, "
          f"actual_change={actual_change:.4f}, raw_total={raw_total_impact:.4f}, "
          f"scale_factor={scale_factor:.6f}")

    return normalized_contributions, normalization_info


def _validate_input_parameters(
    model_content: bytes,
    metadata_content: bytes,
    target_month: str
) -> None:
    """验证输入参数"""
    if not model_content:
        raise ValidationError("模型文件内容为空")
    if not metadata_content:
        raise ValidationError("元数据文件内容为空")
    if not target_month:
        raise ValidationError("目标月份不能为空")

    try:
        pd.to_datetime(target_month, format='%Y-%m')
    except ValueError:
        raise ValidationError("目标月份格式错误，应为YYYY-MM")


def _create_workspace_directory(base_dir: Optional[str]) -> str:
    """创建工作目录"""
    if base_dir is None:
        base_dir = tempfile.gettempdir()

    workspace_dir = os.path.join(
        base_dir,
        f"dfm_news_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    os.makedirs(workspace_dir, exist_ok=True)
    logger.debug(f"创建工作目录: {workspace_dir}")
    return workspace_dir


def _extract_real_data_releases(
    saved_nowcast_data: SavedNowcastData,
    target_month_str: str,
    prior_predictor
) -> List[DataRelease]:
    """
    从真实历史数据中提取目标月份的数据发布事件

    Args:
        saved_nowcast_data: 保存的nowcast数据（包含prepared_data）
        target_month_str: 目标月份字符串（格式: YYYY-MM）
        prior_predictor: 先验预测器，用于计算expected_value

    Returns:
        目标月份内的数据发布列表
    """
    releases = []

    # 验证必需数据
    if saved_nowcast_data.prepared_data is None:
        raise ValidationError("prepared_data不可用，无法提取数据发布")

    if saved_nowcast_data.variable_index_map is None:
        raise ValidationError("variable_index_map不可用")

    prepared_data = saved_nowcast_data.prepared_data
    variable_index_map = saved_nowcast_data.variable_index_map

    # 获取可用变量列表（排除目标变量）
    target_var = saved_nowcast_data.target_variable
    available_variables = [var for var in variable_index_map.keys() if var != target_var]

    if not available_variables:
        raise ValidationError("没有可用的非目标变量")

    # 计算目标月份的日期范围
    target_date = pd.to_datetime(target_month_str)
    month_start, month_end = get_month_date_range(target_date)

    # 筛选目标月份范围内的日期
    selected_dates = prepared_data.index[(prepared_data.index >= month_start) & (prepared_data.index <= month_end)]

    if len(selected_dates) == 0:
        raise ValidationError(f"目标月份 {target_month_str} 没有找到任何数据")

    try:
        logger.info(f"目标月份: {target_month_str} (范围: {month_start.strftime('%Y-%m-%d')} 到 {month_end.strftime('%Y-%m-%d')})")
        logger.info(f"提取数据发布: {len(selected_dates)}个时间点 x {len(available_variables)}个变量")
        logger.debug(f"实际数据日期范围: {selected_dates[0].strftime('%Y-%m-%d')} 到 {selected_dates[-1].strftime('%Y-%m-%d')}")
        logger.debug(f"available_variables前3个={available_variables[:3]}")

        # 为每个时间点和每个变量创建数据发布
        skipped_missing = 0
        skipped_not_in_columns = 0

        for release_date in selected_dates:
            for var_name in available_variables:
                # 检查该变量在该时间点是否有观测值
                if var_name not in prepared_data.columns:
                    skipped_not_in_columns += 1
                    continue

                observed_value = prepared_data.loc[release_date, var_name]

                # 跳过缺失值
                if pd.isna(observed_value):
                    skipped_missing += 1
                    continue

                # 使用卡尔曼滤波的先验预测作为expected_value
                expected_value = prior_predictor.get_prior_prediction(var_name, release_date)

                # 获取变量索引（var_name必然存在于variable_index_map中）
                variable_index = variable_index_map[var_name]

                # 创建数据发布对象
                release = DataRelease(
                    timestamp=release_date,
                    variable_name=var_name,
                    observed_value=float(observed_value),
                    expected_value=float(expected_value),
                    measurement_error=float(abs(observed_value - expected_value) * 0.1) if expected_value != observed_value else 0.01,
                    variable_index=variable_index
                )

                releases.append(release)

        # 按时间排序
        releases.sort(key=lambda x: x.timestamp)

        logger.info(f"成功提取 {len(releases)} 个真实数据发布事件")
        logger.debug(f"跳过统计 - 缺失值={skipped_missing}, 不在列中={skipped_not_in_columns}")
        return releases

    except (ValidationError, ComputationError):
        raise
    except KeyError as e:
        raise ValidationError(f"数据访问错误: 日期或变量不存在 - {str(e)}")
    except (TypeError, ValueError) as e:
        raise ComputationError(f"数据类型转换失败: {str(e)}")


def _generate_analysis_results(
    news_calculator: NewsImpactCalculator,
    contributions: List,
    target_date: pd.Timestamp,
    workspace_dir: str,
    var_industry_map: Optional[Dict[str, str]] = None,
    nowcast_series: Optional[pd.Series] = None,
    normalization_info: Dict[str, Any] = None
) -> Dict[str, Any]:
    """生成分析结果（包括行业聚合和数据流）

    Args:
        normalization_info: 归一化信息字典（必需）
    """
    if normalization_info is None:
        raise ValidationError("normalization_info参数是必需的，不能为None")
    try:
        # 计算各种分析指标
        ranking_df = news_calculator.rank_variables_by_impact(contributions)
        pn_split = news_calculator.calculate_positive_negative_split(contributions)
        key_drivers = news_calculator.identify_key_drivers(contributions, top_n=5)

        # 行业聚合分析
        industry_aggregator = IndustryAggregator(var_industry_map)
        industry_breakdown = industry_aggregator.aggregate_by_industry(contributions)

        # 数据流格式化
        data_flow_formatter = DataFlowFormatter(var_industry_map)
        data_flow = data_flow_formatter.format_data_flow(contributions, nowcast_series)

        # 生成CSV文件
        csv_paths = {}

        # 影响数据CSV
        impacts_data = []
        for contrib in contributions:
            impacts_data.append({
                'variable_name': contrib.variable_name,
                'industry': industry_aggregator.get_industry(contrib.variable_name),
                'observed_value': contrib.observed_value,
                'expected_value': contrib.expected_value,
                'impact_value': contrib.impact_value,
                'contribution_pct': contrib.contribution_pct,
                'is_positive': contrib.is_positive
            })

        impacts_df = pd.DataFrame(impacts_data)
        impacts_csv_path = os.path.join(workspace_dir, 'data_release_impacts.csv')
        impacts_df.to_csv(impacts_csv_path, index=False, encoding='utf-8-sig')
        csv_paths['impacts'] = impacts_csv_path

        # 贡献分解CSV（带说明）
        contributions_data = []
        for _, row in ranking_df.iterrows():
            contributions_data.append({
                'rank': row['rank'],
                'variable_name': row['variable_name'],
                'total_impact': row['total_impact'],
                'avg_impact': row['avg_impact'],
                'contribution_pct': row['total_contribution_pct'],
                'release_count': row['release_count'],
                'positive_count': row['positive_count'],
                'negative_count': row['negative_count']
            })

        contributions_df = pd.DataFrame(contributions_data)
        contributions_csv_path = os.path.join(workspace_dir, 'contributions_decomposition.csv')

        # 创建带说明的CSV
        with open(contributions_csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            # 写入说明头部
            f.write('# 贡献分解CSV说明文档\n')
            f.write('# \n')
            f.write('# 列名含义与计算方法:\n')
            f.write('# \n')
            f.write('# 1. rank - 排名\n')
            f.write('#    说明: 按total_impact的绝对值从大到小排序\n')
            f.write('#    计算: 根据|total_impact|降序排列后的序号\n')
            f.write('# \n')
            f.write('# 2. variable_name - 变量名称\n')
            f.write('#    说明: 经济指标的名称\n')
            f.write('#    示例: 规模以上工业增加值, CPI, 社会消费品零售总额\n')
            f.write('# \n')
            f.write('# 3. total_impact - 总影响值\n')
            f.write('#    说明: 该变量在分析期内所有数据发布对目标变量预测值的累计影响\n')
            f.write('#    计算: sum(各次发布的impact_value)\n')
            f.write('#    公式: Δy_total = Σ([λ_y\' × K_t[:, i] × v_i,t] × σ_y)\n')
            f.write('#    单位: 与目标变量相同（通常为百分点），已反标准化到原始尺度\n')
            f.write('# \n')
            f.write('# 4. avg_impact - 平均影响值\n')
            f.write('#    说明: 该变量每次数据发布的平均影响\n')
            f.write('#    计算: total_impact / release_count\n')
            f.write('#    用途: 衡量单次数据发布的平均贡献强度\n')
            f.write('# \n')
            f.write('# 5. contribution_pct - 贡献百分比\n')
            f.write('#    说明: 该变量对预测变动的相对贡献度\n')
            f.write('#    计算: sum(|该变量各次影响值|) / sum(|所有变量所有影响值|) × 100\n')
            f.write('#    范围: 0-100%, 所有变量的贡献百分比之和为100%\n')
            f.write('#    解释: 该值越大，说明该变量对预测变动的解释力越强\n')
            f.write('# \n')
            f.write('# 6. release_count - 发布次数\n')
            f.write('#    说明: 该变量在分析期内的数据发布次数\n')
            f.write('#    计算: 统计该变量有非缺失观测值的时间点数量\n')
            f.write('# \n')
            f.write('# 7. positive_count - 正向影响次数\n')
            f.write('#    说明: 该变量的数据发布中，使预测值上升的次数\n')
            f.write('#    计算: 统计impact_value > 0的发布次数\n')
            f.write('# \n')
            f.write('# 8. negative_count - 负向影响次数\n')
            f.write('#    说明: 该变量的数据发布中，使预测值下降的次数\n')
            f.write('#    计算: 统计impact_value < 0的发布次数\n')
            f.write('# \n')
            f.write('# 核心公式详解:\n')
            f.write('# 影响值 = [λ_y\' × K_t[:, i] × v_i,t] × σ_y\n')
            f.write('# 三步计算过程:\n')
            f.write('#   1. Δf_t = K_t[:, i] × v_i,t      (因子状态增量)\n')
            f.write('#   2. Δy_标准化 = λ_y\' × Δf_t       (标准化尺度影响)\n')
            f.write('#   3. Δy_原始 = Δy_标准化 × σ_y      (反标准化到原始尺度)\n')
            f.write('# 其中:\n')
            f.write('#   - λ_y: 目标变量的因子载荷向量 (n_factors,)\n')
            f.write('#   - K_t: 第t期卡尔曼增益矩阵 (n_factors, n_variables)\n')
            f.write('#   - v_i,t: 变量i在第t期的新息（观测值 - 先验预测）\n')
            f.write('#   - σ_y: 目标变量的标准差（用于反标准化）\n')
            f.write('#   - Δy: 变量i的数据更新对目标变量的影响（原始尺度，标量）\n')
            f.write('# \n')
            f.write('# 使用示例:\n')
            f.write('# 如果GDP增长率预测从5.0%变为5.2%，某变量的total_impact=+0.15，contribution_pct=75%\n')
            f.write('# 说明: 该变量使预测值提升了0.15个百分点，解释了总变动（0.2个百分点）的75%\n')
            f.write('# \n')
            f.write('# 生成时间: {}\n'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            f.write('# \n')
            f.write('# ========== 数据开始 ==========\n')
            f.write('# \n')

            # 写入实际数据
            contributions_df.to_csv(f, index=False)

        csv_paths['contributions'] = contributions_csv_path

        # 生成摘要信息
        total_impact = sum(c.impact_value for c in contributions)
        month_start, month_end = get_month_date_range(target_date)
        summary = {
            'target_date': target_date.strftime('%Y-%m-%d'),
            'analysis_start': month_start.strftime('%Y-%m-%d'),
            'analysis_end': month_end.strftime('%Y-%m-%d'),
            'total_impact': float(total_impact),
            'total_releases': len(contributions),
            'positive_impact_sum': float(pn_split['positive_impact']),
            'negative_impact_sum': float(pn_split['negative_impact']),
            'top_contributors': ranking_df['variable_name'].head(5).tolist(),
            'key_drivers_count': key_drivers['driver_count'],
            'industry_breakdown': industry_breakdown,
            'analysis_time': datetime.now().isoformat(),
            # 归一化信息（必需字段）
            'first_nowcast': normalization_info['first_nowcast'],
            'last_nowcast': normalization_info['last_nowcast'],
            'actual_nowcast_change': normalization_info['actual_change'],
            'normalization_scale_factor': normalization_info['scale_factor'],
        }

        logger.info(f"分析结果生成完成: CSV文件={len(csv_paths)} 个, 行业数={len(industry_breakdown)}")
        return {
            'csv_paths': csv_paths,
            'summary': summary,
            'data_flow': data_flow
        }

    except (KeyError, TypeError, ValueError) as e:
        raise ComputationError(f"分析结果生成失败: {str(e)}")