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
from typing import Dict, Any, Optional, Union
from pathlib import Path
from io import BytesIO
import hashlib
import logging
import threading
from datetime import datetime

from dashboard.models.DFM.prep.processor import DataPreparationProcessor
from dashboard.models.DFM.prep.config import PrepParallelConfig
from dashboard.models.DFM.utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


# 线程安全的缓存机制
_MAPPING_CACHE = {}
_CACHE_LOCK = threading.Lock()

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
            }
        }
    """
    try:
        logger.info("步骤1/7: 加载映射表...")

        # 处理文件输入
        excel_input = _handle_file_input(excel_path)

        # 检查缓存（线程安全）
        if use_cache:
            cache_key = (
                _get_cache_key(excel_input),
                reference_sheet_name,
                reference_column_name,
            )
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
        df = pd.read_excel(excel_input, sheet_name=reference_sheet_name)

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

        # 7. 变量-发布日期滞后映射
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

        # 更新缓存（线程安全）
        if use_cache:
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



def prepare_dfm_data_simple(
    uploaded_file: Union[str, Any],
    target_variable_name: str = None,
    data_start_date: str = None,
    data_end_date: str = None,
    target_freq: str = "W-FRI",
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
            var_industry_map=var_industry_map,
            var_frequency_map=var_frequency_map,
            target_freq=target_freq,
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

        # 构建元数据
        processing_time = (datetime.now() - start_time).total_seconds()

        metadata = {
            'variable_mapping': variable_mapping,
            'transform_log': transform_log,
            'removal_log': removal_log,
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
                'target_freq': target_freq
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



# 私有辅助函数

def _handle_file_input(file_input: Union[str, Path, Any]) -> str | BytesIO:
    """
    处理文件输入；上传内容保留在内存中，路径输入保持为路径。

    Args:
        file_input: 文件路径（str）或文件对象

    Returns:
        文件路径或独立的内存字节流
    """
    if isinstance(file_input, str):
        return file_input
    if isinstance(file_input, Path):
        return str(file_input)
    if hasattr(file_input, "getvalue"):
        return BytesIO(file_input.getvalue())
    if hasattr(file_input, "read"):
        original_position = file_input.tell() if hasattr(file_input, "tell") else None
        if hasattr(file_input, "seek"):
            file_input.seek(0)
        content = file_input.read()
        if original_position is not None:
            file_input.seek(original_position)
        return BytesIO(content)
    raise TypeError(f"不支持的文件输入类型: {type(file_input)}")


def _get_cache_key(excel_input: str | BytesIO) -> str:
    """以文件内容生成稳定缓存键。"""
    digest = hashlib.sha256()
    if isinstance(excel_input, str):
        path = Path(excel_input).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {excel_input}")
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
                digest.update(chunk)
    else:
        digest.update(excel_input.getvalue())
    return digest.hexdigest()


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


__all__ = [
    'load_mappings_once',
    'prepare_dfm_data_simple',
]
