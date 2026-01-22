"""
DFM数据准备模块 - 简化API接口

这个模块提供简化后的前后端分离接口，遵循7步流程设计。

重构说明（2025-11-13）：
- 消除Pipeline和Core层，直接调用Processor
- 映射表只加载一次（带简化的缓存机制）
- 删除工作表自动推断功能（UI层必须明确指定）
- 新增时间范围统计功能（步骤2）
- 智能缺失值检测（根据频率关系选择检测时机）
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Union, Tuple
from pathlib import Path
import logging
import tempfile
import os
import threading
import atexit
from datetime import datetime

from dashboard.models.DFM.prep.processor import DataPreparationProcessor
from dashboard.models.DFM.prep.config import PrepParallelConfig, create_default_prep_config
from dashboard.models.DFM.utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


# 线程安全的缓存机制
_MAPPING_CACHE = {}
_CACHE_LOCK = threading.Lock()

# 临时文件跟踪（用于清理）
_TEMP_FILES = set()
_TEMP_FILES_LOCK = threading.Lock()


def _cleanup_temp_files():
    """清理所有临时文件（在程序退出时调用）"""
    while True:
        with _TEMP_FILES_LOCK:
            if not _TEMP_FILES:
                break
            tmp_path = _TEMP_FILES.pop()
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError as e:
            logger.debug("清理临时文件失败 %s: %s", tmp_path, e)


# 注册退出时清理
atexit.register(_cleanup_temp_files)


def load_mappings_once(
    excel_path: Union[str, Any],
    reference_sheet_name: str = "指标字典",
    reference_column_name: str = "指标名称",
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    步骤1: 加载映射表（带简化的缓存机制）

    从Excel文件的"指标字典"工作表加载7种映射关系。
    使用文件修改时间作为缓存键，避免重复加载。

    Args:
        excel_path: Excel文件路径或文件对象
        reference_sheet_name: 映射表的工作表名称，默认"指标字典"
        reference_column_name: 映射表的参考列名，默认"指标名称"
        use_cache: 是否使用缓存，默认True

    Returns:
        dict: {
            'status': str,              # 'success' 或 'error'
            'message': str,             # 处理结果消息
            'mappings': {               # 映射字典（仅成功时）
                'var_type_map': Dict[str, str],           # 变量类型映射
                'var_industry_map': Dict[str, str],       # 变量-行业映射 ★核心★
                'var_frequency_map': Dict[str, str],      # 变量-频率映射
                'single_stage_map': Dict[str, str],       # 预测变量映射
                'second_stage_target_map': Dict[str, str] # 目标变量映射
            }
        }
    """
    try:
        logger.info("步骤1/7: 加载映射表...")

        # 处理文件输入
        file_path = _handle_file_input(excel_path)

        # 检查缓存（线程安全）
        if use_cache:
            cache_key = _get_cache_key(file_path)
            with _CACHE_LOCK:
                if cache_key in _MAPPING_CACHE:
                    logger.info("  从缓存加载映射表（命中）")
                    return {
                        'status': 'success',
                        'message': '从缓存加载映射表',
                        'mappings': _MAPPING_CACHE[cache_key]
                    }

        # 加载映射表
        logger.info("  从Excel文件加载映射表...")
        df = pd.read_excel(file_path, sheet_name=reference_sheet_name)

        # 标准化列名
        df.columns = df.columns.str.strip()

        # 验证必需列
        required_columns = [reference_column_name, '类型', '行业', '频率', '单位']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"映射表缺少必需列: {missing_columns}")

        # 提取映射关系
        mappings = {}

        # 1. 变量类型映射（变量名 → 类型）
        mappings['var_type_map'] = _extract_mapping(
            df, reference_column_name, '类型'
        )

        # 2. 变量-行业映射（变量名 → 行业）★核心★
        mappings['var_industry_map'] = _extract_mapping(
            df, reference_column_name, '行业'
        )

        # 3. 变量-频率映射（变量名 → 频率）★新增★
        mappings['var_frequency_map'] = _extract_mapping(
            df, reference_column_name, '频率'
        )

        # 4. 变量-单位映射（变量名 → 单位）★核心★
        mappings['var_unit_map'] = _extract_mapping(
            df, reference_column_name, '单位'
        )

        # 5. 变量-性质映射（变量名 → 性质）
        if '性质' not in df.columns:
            raise ValueError("映射表缺少必需列: '性质'")
        mappings['var_nature_map'] = _extract_mapping(
            df, reference_column_name, '性质'
        )

        # 6. 预测变量映射
        if '预测变量' not in df.columns:
            raise ValueError("映射表缺少必需列: '预测变量'")
        mappings['single_stage_map'] = _extract_mapping(
            df, reference_column_name, '预测变量', value_filter='是'
        )

        # 7. 目标变量映射
        if '目标变量' not in df.columns:
            raise ValueError("映射表缺少必需列: '目标变量'")
        mappings['second_stage_target_map'] = _extract_mapping(
            df, reference_column_name, '目标变量', value_filter='是'
        )

        # 8. 变量-发布日期滞后映射
        if '发布日期' not in df.columns:
            raise ValueError("映射表缺少必需列: '发布日期'")
        mappings['var_publication_lag_map'] = _extract_numeric_mapping(
            df, reference_column_name, '发布日期'
        )

        # 统计信息
        logger.info(f"  映射加载完成:")
        logger.info(f"    变量类型: {len(mappings['var_type_map'])}个")
        logger.info(f"    变量-行业: {len(mappings['var_industry_map'])}个")
        logger.info(f"    变量-频率: {len(mappings['var_frequency_map'])}个")
        logger.info(f"    变量-单位: {len(mappings['var_unit_map'])}个")
        logger.info(f"    变量-性质: {len(mappings['var_nature_map'])}个")
        logger.info(f"    发布日期滞后: {len(mappings['var_publication_lag_map'])}个")
        logger.info(f"    预测变量: {len(mappings['single_stage_map'])}个")
        logger.info(f"    目标变量: {len(mappings['second_stage_target_map'])}个")

        # 更新缓存（线程安全）
        if use_cache:
            cache_key = _get_cache_key(file_path)
            with _CACHE_LOCK:
                _MAPPING_CACHE[cache_key] = mappings
            logger.info("  映射表已缓存")

        return {
            'status': 'success',
            'message': f'成功加载 {len(mappings["var_industry_map"])} 个变量映射',
            'mappings': mappings
        }

    except FileNotFoundError as e:
        logger.error(f"文件未找到: {e}")
        return {
            'status': 'error',
            'message': f'文件未找到: {str(e)}',
            'mappings': None
        }

    except (ValueError, KeyError) as e:
        logger.error(f"映射表数据验证失败: {e}")
        raise
    except pd.errors.EmptyDataError as e:
        logger.error(f"映射表为空: {e}")
        raise ValueError(f"映射表为空: {e}") from e


def collect_time_ranges(
    excel_path: Union[str, Any]
) -> Dict[str, Any]:
    """
    步骤2: 统计所有数据的时间范围（新增功能）

    遍历Excel文件中的所有工作表，统计每个工作表的时间范围，
    并返回所有数据的并集时间范围。

    Args:
        excel_path: Excel文件路径或文件对象

    Returns:
        dict: {
            'status': str,              # 'success' 或 'error'
            'message': str,             # 处理结果消息
            'time_range': {             # 时间范围信息（仅成功时）
                'overall_start': str,   # 所有数据的最早日期
                'overall_end': str,     # 所有数据的最晚日期
                'sheet_ranges': {       # 每个工作表的时间范围
                    '工业_日度': {'start': '2020-01-01', 'end': '2024-12-31'},
                    ...
                }
            }
        }
    """
    try:
        logger.info("步骤2/7: 统计数据时间范围...")

        # 处理文件输入
        file_path = _handle_file_input(excel_path)

        # 加载Excel文件（使用context manager确保资源释放）
        sheet_ranges = {}
        all_dates = []

        with pd.ExcelFile(file_path) as excel_file:
            for sheet_name in excel_file.sheet_names:
                # 跳过映射表
                if sheet_name == '指标字典':
                    continue

                # 读取第一列作为日期列
                df = pd.read_excel(excel_file, sheet_name=sheet_name, usecols=[0])
                if df.empty:
                    continue

                # 尝试解析为日期
                dates = pd.to_datetime(df.iloc[:, 0], errors='coerce')
                valid_dates = dates.dropna()

                if not valid_dates.empty:
                    sheet_start = valid_dates.min()
                    sheet_end = valid_dates.max()

                    sheet_ranges[sheet_name] = {
                        'start': sheet_start.strftime('%Y-%m-%d'),
                        'end': sheet_end.strftime('%Y-%m-%d'),
                        'data_points': len(valid_dates)
                    }

                    all_dates.extend(valid_dates.tolist())

                    logger.info("  %s: %s 至 %s", sheet_name, sheet_ranges[sheet_name]['start'], sheet_ranges[sheet_name]['end'])

        if not all_dates:
            raise ValueError("未能从任何工作表中提取有效日期")

        # 计算并集时间范围
        overall_start = min(all_dates)
        overall_end = max(all_dates)

        time_range = {
            'overall_start': overall_start.strftime('%Y-%m-%d'),
            'overall_end': overall_end.strftime('%Y-%m-%d'),
            'total_sheets': len(sheet_ranges),
            'sheet_ranges': sheet_ranges
        }

        logger.info(f"  所有数据时间范围: {time_range['overall_start']} 至 {time_range['overall_end']}")
        logger.info(f"  共 {time_range['total_sheets']} 个工作表")

        return {
            'status': 'success',
            'message': f'成功统计 {len(sheet_ranges)} 个工作表的时间范围',
            'time_range': time_range
        }

    except Exception as e:
        logger.error(f"统计时间范围失败: {e}", exc_info=True)
        return {
            'status': 'error',
            'message': f'统计时间范围失败: {str(e)}',
            'time_range': None
        }


def prepare_dfm_data_simple(
    uploaded_file: Union[str, Any],
    target_variable_name: str = None,
    data_start_date: str = None,
    data_end_date: str = None,
    target_freq: str = "W-FRI",
    consecutive_nan_threshold: int = 10,
    reference_sheet_name: str = "指标字典",
    reference_column_name: str = "指标名称",
    enable_borrowing: bool = True,
    enable_freq_alignment: bool = True,
    zero_handling: str = "missing",
    negative_handling: str = "none",
    enable_publication_calibration: bool = False,
    parallel_config: Optional[PrepParallelConfig] = None
) -> Dict[str, Any]:
    """
    DFM数据准备主API - 简化版（7步流程）

    步骤1: 加载映射表（一次性）
    步骤2: 统计时间范围（已在UI层完成）
    步骤3: 应用UI配置的时间范围
    步骤4: 加载数据并按频率分类
    步骤5: 智能缺失值检测与频率对齐
    步骤6: 合并数据形成最终表
    步骤7: 生成输出

    Args:
        uploaded_file: Excel文件路径（str）或文件对象
        target_variable_name: 目标变量名称（可选，用于将其放在第一列）
        data_start_date: 数据起始日期，格式："YYYY-MM-DD"（None表示使用数据实际起始日期）
        data_end_date: 数据结束日期，格式："YYYY-MM-DD"（None表示使用数据实际结束日期）
        target_freq: 目标频率，默认"W-FRI"（周五结尾的周度数据）
        consecutive_nan_threshold: 允许的最大连续NaN值数量
        reference_sheet_name: 指标映射表的工作表名称
        reference_column_name: 映射表中的参考列名
        enable_borrowing: 是否启用数据借调，默认True
        enable_freq_alignment: 是否启用频率对齐，默认True。选择False时保留原始日期
        zero_handling: 零值处理方式，'none'不处理，'missing'转为缺失值，'adjust'调正为1，默认'missing'
        negative_handling: 负值处理方式，'none'不处理，'missing'转为缺失值，'adjust'调正为1，默认'none'
        enable_publication_calibration: 是否启用发布日期校准，默认False。启用时按指标实际发布日期对齐
        parallel_config: 并行配置（可选）

    Returns:
        dict: {
            'status': str,              # 'success' 或 'error'
            'message': str,             # 处理结果消息
            'data': pd.DataFrame,       # 处理后的周度数据（仅成功时）
            'metadata': {               # 元数据（仅成功时）
                'variable_mapping': Dict,      # 变量到行业的映射
                'transform_log': Dict,         # 转换操作日志（包含去趋势信息）
                'removal_log': List[Dict],     # 移除变量日志
                'data_shape': tuple,           # 数据形状 (rows, cols)
                'time_range': tuple,           # 时间范围 (start, end)
                'processing_time': str         # 处理耗时
            }
        }
    """
    start_time = datetime.now()

    try:
        logger.info("\n" + "="*60)
        logger.info("DFM数据准备流程启动（简化版 7步流程）")
        logger.info("="*60)
        logger.info(f"参数: 目标变量={target_variable_name}")
        logger.info(f"      起始日期={data_start_date}, 结束日期={data_end_date}, 目标频率={target_freq}")

        # 步骤1: 处理文件输入
        excel_input = _handle_file_input(uploaded_file)

        # 步骤1: 加载映射表（带缓存）
        mapping_result = load_mappings_once(
            excel_input,
            reference_sheet_name,
            reference_column_name
        )

        if mapping_result['status'] != 'success':
            raise ValueError(mapping_result['message'])

        mappings = mapping_result['mappings']
        var_industry_map = mappings['var_industry_map']
        var_frequency_map = mappings['var_frequency_map']
        var_publication_lag_map = mappings.get('var_publication_lag_map', {})

        # 步骤3-7: 创建Processor并执行
        logger.info("\n开始执行数据处理流程...")
        logger.info(f"频率对齐模式: {'启用' if enable_freq_alignment else '禁用（保留原始日期）'}")
        logger.info(f"零值处理: {zero_handling}")
        logger.info(f"负值处理: {negative_handling}")
        logger.info(f"发布日期校准: {'启用' if enable_publication_calibration else '禁用'}")
        processor = DataPreparationProcessor(
            excel_path=excel_input,
            target_variable_name=target_variable_name,
            var_industry_map=var_industry_map,
            var_frequency_map=var_frequency_map,
            target_freq=target_freq,
            consecutive_nan_threshold=consecutive_nan_threshold,
            data_start_date=data_start_date,
            data_end_date=data_end_date,
            enable_borrowing=enable_borrowing,
            enable_freq_alignment=enable_freq_alignment,
            zero_handling=zero_handling,
            negative_handling=negative_handling,
            var_publication_lag_map=var_publication_lag_map,
            enable_publication_calibration=enable_publication_calibration,
            parallel_config=parallel_config
        )

        processed_data, variable_mapping, transform_log, removal_log = processor.execute()

        # 步骤8: 执行平稳性检验
        logger.info("\n" + "="*60)
        logger.info("步骤8/8: 执行平稳性检验...")
        logger.info("="*60)
        from dashboard.models.DFM.prep.utils.stationarity_checker import StationarityChecker

        stationarity_check_results = {}
        try:
            if processed_data.empty:
                logger.warning("prepared_data为空，跳过平稳性检验")
            elif len(processed_data.columns) == 0:
                logger.warning("prepared_data没有列，跳过平稳性检验")
            else:
                raw_results = StationarityChecker.batch_check_variables(
                    processed_data,
                    variables=list(processed_data.columns),
                    alpha=0.05,
                    parallel=False
                )
                # 标准化键名，确保与export_service查询时使用的normalize_text一致
                stationarity_check_results = {
                    normalize_text(k): v for k, v in raw_results.items()
                }
                logger.info(f"平稳性检验完成: {len(stationarity_check_results)}个变量")
        except (ValueError, np.linalg.LinAlgError) as e:
            logger.error(f"平稳性检验执行失败: {e}")
            raise RuntimeError(f"平稳性检验失败: {e}") from e

        # 构建元数据
        processing_time = (datetime.now() - start_time).total_seconds()

        metadata = {
            'variable_mapping': variable_mapping,
            'transform_log': transform_log,
            'removal_log': removal_log,
            'stationarity_check_results': stationarity_check_results,
            'data_shape': processed_data.shape,
            'time_range': (
                str(processed_data.index.min()) if not processed_data.empty else None,
                str(processed_data.index.max()) if not processed_data.empty else None
            ),
            'processing_time': f"{processing_time:.2f}秒",
            'parameters': {
                'reference_sheet_name': reference_sheet_name,
                'target_variable_name': target_variable_name,
                'data_start_date': data_start_date,
                'data_end_date': data_end_date,
                'target_freq': target_freq,
                'nan_threshold': consecutive_nan_threshold
            }
        }

        logger.info("="*60)
        logger.info(f"数据准备成功！形状: {processed_data.shape}, 耗时: {processing_time:.2f}秒")
        logger.info("="*60 + "\n")

        return {
            'status': 'success',
            'message': f'数据准备成功！处理了 {processed_data.shape[0]} 行 × {processed_data.shape[1]} 列数据',
            'data': processed_data,
            'metadata': metadata
        }

    except FileNotFoundError as e:
        logger.error(f"文件未找到: {e}")
        return {
            'status': 'error',
            'message': f'文件未找到: {str(e)}',
            'data': None,
            'metadata': None
        }

    except ValueError as e:
        logger.error(f"参数错误: {e}")
        return {
            'status': 'error',
            'message': f'参数错误: {str(e)}',
            'data': None,
            'metadata': None
        }

    except Exception as e:
        logger.error(f"数据准备过程中发生错误: {e}", exc_info=True)
        return {
            'status': 'error',
            'message': f'数据准备失败: {str(e)}',
            'data': None,
            'metadata': None
        }


def validate_preparation_parameters(
    target_sheet_name: str,
    target_variable_name: str,
    data_start_date: str,
    data_end_date: str,
    target_freq: str
) -> Dict[str, Any]:
    """
    验证数据准备参数

    Args:
        target_sheet_name: 目标工作表名称
        target_variable_name: 目标变量名称
        data_start_date: 起始日期
        data_end_date: 结束日期
        target_freq: 目标频率

    Returns:
        dict: {
            'status': str,
            'message': str,
            'is_valid': bool,
            'errors': List[str]
        }
    """
    errors = []

    try:
        # 验证必填参数
        if not target_sheet_name:
            errors.append("目标工作表名称不能为空")

        if not target_variable_name:
            errors.append("目标变量名称不能为空")

        # 验证日期格式
        if data_start_date:
            pd.to_datetime(data_start_date)  # Validate format
        if data_end_date:
            pd.to_datetime(data_end_date)  # Validate format

        # 验证日期逻辑
        if data_start_date and data_end_date:
            start_dt = pd.to_datetime(data_start_date)
            end_dt = pd.to_datetime(data_end_date)
            if start_dt >= end_dt:
                errors.append(f"起始日期 ({data_start_date}) 必须早于结束日期 ({data_end_date})")

        # 验证频率
        valid_freqs = ['W-FRI', 'W', 'D', 'M', 'Q', 'Y']
        if target_freq not in valid_freqs:
            errors.append(f"不支持的频率 '{target_freq}'，支持的频率: {', '.join(valid_freqs)}")

        if errors:
            return {
                'status': 'error',
                'message': '参数验证失败',
                'is_valid': False,
                'errors': errors
            }

        return {
            'status': 'success',
            'message': '参数验证通过',
            'is_valid': True,
            'errors': []
        }

    except Exception as e:
        return {
            'status': 'error',
            'message': f'参数验证异常: {str(e)}',
            'is_valid': False,
            'errors': [str(e)]
        }


# 私有辅助函数

def _handle_file_input(file_input: Union[str, Any]) -> str:
    """
    处理文件输入，统一转换为文件路径

    Args:
        file_input: 文件路径（str）或文件对象

    Returns:
        str: 文件路径
    """
    if isinstance(file_input, str):
        # 已经是路径
        return file_input

    elif hasattr(file_input, 'read'):
        # 是文件对象，保存到临时文件
        file_input.seek(0)  # 重置文件指针
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_file.write(file_input.read())
            tmp_path = tmp_file.name
            # 跟踪临时文件以便清理
            with _TEMP_FILES_LOCK:
                _TEMP_FILES.add(tmp_path)
            logger.debug(f"文件对象已保存到临时文件: {tmp_path}")
            return tmp_path

    elif isinstance(file_input, Path):
        # Path对象
        return str(file_input)

    else:
        raise TypeError(f"不支持的文件输入类型: {type(file_input)}")


def _get_cache_key(file_path: str) -> str:
    """
    生成缓存键（基于文件修改时间）

    Args:
        file_path: 文件路径

    Returns:
        str: 缓存键

    Raises:
        FileNotFoundError: 文件不存在
    """
    # 路径验证：规范化路径防止路径遍历
    real_path = os.path.realpath(file_path)
    if not os.path.exists(real_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    mtime = os.path.getmtime(real_path)
    return f"{real_path}_{mtime}"


def _extract_mapping(
    df: pd.DataFrame,
    key_column: str,
    value_column: str,
    value_filter: Optional[str] = None
) -> Dict[str, str]:
    """
    从DataFrame中提取映射关系

    Args:
        df: 映射表DataFrame
        key_column: 键列名（变量名列）
        value_column: 值列名（映射目标列）
        value_filter: 值过滤条件（可选，如'是'）

    Returns:
        Dict[str, str]: 标准化后的映射字典
    """
    mapping = {}

    for _, row in df.iterrows():
        key = str(row[key_column]).strip()
        value = str(row[value_column]).strip()

        # 跳过空值
        if not key or key == 'nan' or not value or value == 'nan':
            continue

        # 应用值过滤
        if value_filter and value != value_filter:
            continue

        # 标准化键名
        key_norm = normalize_text(key)
        if key_norm:
            mapping[key_norm] = value

    return mapping


def _extract_numeric_mapping(
    df: pd.DataFrame,
    key_column: str,
    value_column: str
) -> Dict[str, int]:
    """
    从DataFrame中提取数值映射关系

    Args:
        df: 映射表DataFrame
        key_column: 键列名（变量名列）
        value_column: 值列名（数值列）

    Returns:
        Dict[str, int]: 标准化后的映射字典（值为整数）
    """
    mapping = {}

    for _, row in df.iterrows():
        key = str(row[key_column]).strip()
        value = row[value_column]

        # 跳过空值
        if not key or key == 'nan':
            continue

        # 尝试转换为整数
        try:
            if pd.notna(value):
                int_value = int(float(value))
                key_norm = normalize_text(key)
                if key_norm:
                    mapping[key_norm] = int_value
        except (ValueError, TypeError):
            continue

    return mapping


def clear_mapping_cache():
    """清除映射表缓存（线程安全）"""
    with _CACHE_LOCK:
        _MAPPING_CACHE.clear()
    logger.info("映射表缓存已清除")


def detect_file_info(
    file_content: bytes
) -> Dict[str, Any]:
    """
    检测Excel文件信息（日期范围和变量统计）

    整合日期检测和变量统计功能，供UI层调用

    Args:
        file_content: Excel文件字节内容

    Returns:
        dict: {
            'status': str,
            'message': str,
            'date_range': {
                'start': date,
                'end': date
            },
            'variable_count': int,
            'freq_counts': Dict[str, int],
            'variable_stats': pd.DataFrame
        }
    """
    from dashboard.models.DFM.prep.services.stats_service import StatsService

    try:
        # 检测日期范围
        start_date, end_date, var_count, freq_counts = StatsService.detect_date_range(file_content)

        # 计算变量统计
        var_stats = StatsService.compute_raw_stats(file_content)

        return {
            'status': 'success',
            'message': f'检测到 {var_count} 个变量',
            'date_range': {
                'start': start_date,
                'end': end_date
            },
            'variable_count': var_count,
            'freq_counts': freq_counts,
            'variable_stats': var_stats
        }

    except Exception as e:
        logger.error(f"文件信息检测失败: {e}", exc_info=True)
        return {
            'status': 'error',
            'message': f'文件信息检测失败: {str(e)}',
            'date_range': None,
            'variable_count': 0,
            'freq_counts': {},
            'variable_stats': None
        }


def generate_export_excel(
    prepared_data: pd.DataFrame,
    industry_map: Dict[str, str],
    mappings: Dict[str, Any],
    removed_vars_log: Optional[list] = None,
    transform_details: Optional[Dict] = None
) -> bytes:
    """
    生成导出Excel文件

    Args:
        prepared_data: 处理后的数据
        industry_map: 行业映射
        mappings: 完整映射字典
        removed_vars_log: 被删除变量日志
        transform_details: 变量转换详情

    Returns:
        bytes: Excel文件字节内容
    """
    from dashboard.models.DFM.prep.services.export_service import ExportService

    return ExportService.generate_excel(
        prepared_data=prepared_data,
        industry_map=industry_map,
        mappings=mappings,
        removed_vars_log=removed_vars_log,
        transform_details=transform_details
    )


def compute_variable_stats(
    prepared_data: pd.DataFrame,
    var_frequency_map: Optional[Dict[str, str]] = None
) -> pd.DataFrame:
    """
    计算处理后数据的变量统计

    Args:
        prepared_data: 处理后的DataFrame
        var_frequency_map: 变量频率映射

    Returns:
        DataFrame: 变量统计信息
    """
    from dashboard.models.DFM.prep.services.stats_service import StatsService

    return StatsService.compute_processed_stats(prepared_data, var_frequency_map)


# 导出的API函数
__all__ = [
    'load_mappings_once',
    'collect_time_ranges',
    'prepare_dfm_data_simple',
    'validate_preparation_parameters',
    'clear_mapping_cache',
    'detect_file_info',
    'generate_export_excel',
    'compute_variable_stats'
]
