# -*- coding: utf-8 -*-
"""
数据处理辅助函数模块
将data_loader.py中的巨型函数拆分为可复用的小函数
"""
import pandas as pd
import numpy as np
import warnings
import io
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def read_indicator_mapping(
    excel_file_handler,
    sheet_name: str = '指标字典',
    file_buffer=None
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]]:
    """
    读取指标字典映射（行业、单位、类型、频率）

    Args:
        excel_file_handler: pandas ExcelFile对象
        sheet_name: 指标字典sheet名称
        file_buffer: 文件缓冲区（用于BytesIO seek操作）

    Returns:
        Tuple[Dict, Dict, Dict, Dict]: (行业映射, 单位映射, 类型映射, 频率映射)
    """
    from dashboard.preview.modules.industrial.loader import normalize_string
    from dashboard.preview.modules.industrial.config import FREQ_CHAR_TO_ENGLISH

    industry_map = {}
    unit_map = {}
    type_map = {}
    freq_map = {}

    try:
        if file_buffer and isinstance(file_buffer, io.BytesIO):
            file_buffer.seek(0)

        # 检查列名
        temp_df = pd.read_excel(excel_file_handler, sheet_name=sheet_name, nrows=0)
        available_cols = temp_df.columns.tolist()

        # 准备要读取的列
        cols_to_read = []
        col_mapping = {
            '指标名称': ['指标名称'],
            '行业': ['行业'],
            '单位': ['单位'],
            '类型': ['类型'],
            '频率': ['频率']
        }

        actual_col_names = {}
        for target_col, possible_names in col_mapping.items():
            for name in possible_names:
                if name in available_cols:
                    cols_to_read.append(name)
                    actual_col_names[target_col] = name
                    break

        if not actual_col_names.get('指标名称'):
            warnings.warn(f"Sheet '{sheet_name}' found, but no indicator name column found.")
            return industry_map, unit_map, type_map, freq_map

        df_mapping = pd.read_excel(
            excel_file_handler,
            sheet_name=sheet_name,
            usecols=cols_to_read
        )

        # 统一列名
        rename_dict = {v: k for k, v in actual_col_names.items()}
        df_mapping.rename(columns=rename_dict, inplace=True)

        # 标准化指标名称
        df_mapping['指标名称'] = df_mapping['指标名称'].apply(normalize_string)

        # 创建行业映射
        if '行业' in df_mapping.columns:
            df_industry = df_mapping.dropna(subset=['指标名称', '行业'])
            industry_map = pd.Series(
                df_industry['行业'].values,
                index=df_industry['指标名称']
            ).to_dict()
            logger.debug(f"成功读取 {len(industry_map)} 个行业映射")

        # 创建单位映射
        if '单位' in df_mapping.columns:
            df_unit = df_mapping.dropna(subset=['指标名称', '单位'])
            df_unit = df_unit[df_unit['单位'].str.strip() != '']
            unit_map = pd.Series(
                df_unit['单位'].values,
                index=df_unit['指标名称']
            ).to_dict()
            logger.debug(f"成功读取 {len(unit_map)} 个单位映射")

        # 创建类型映射
        if '类型' in df_mapping.columns:
            df_type = df_mapping.dropna(subset=['指标名称', '类型'])
            df_type = df_type[df_type['类型'].str.strip() != '']
            type_map = pd.Series(
                df_type['类型'].values,
                index=df_type['指标名称']
            ).to_dict()
            logger.debug(f"成功读取 {len(type_map)} 个类型映射")

        # 创建频率映射
        if '频率' in df_mapping.columns:
            df_freq = df_mapping.dropna(subset=['指标名称', '频率'])
            for _, row in df_freq.iterrows():
                name = row['指标名称']
                freq_char = str(row['频率']).strip()
                if freq_char in FREQ_CHAR_TO_ENGLISH:
                    freq_map[name] = FREQ_CHAR_TO_ENGLISH[freq_char]
            logger.debug(f"成功读取 {len(freq_map)} 个频率映射")

    except KeyError as ke:
        warnings.warn(f"Sheet '{sheet_name}' columns not found: {ke}")
    except Exception as e:
        warnings.warn(f"Error reading mapping sheet '{sheet_name}': {e}")

    return industry_map, unit_map, type_map, freq_map


def determine_data_type(sheet_name: str) -> Optional[str]:
    """
    根据sheet名称判断数据类型（从配置导入，避免硬编码）

    Args:
        sheet_name: Excel sheet名称

    Returns:
        Optional[str]: 数据类型 ('weekly'/'monthly'/'daily'/'ten_day'/'yearly' 或 None)
    """
    from dashboard.preview.modules.industrial.config import CHINESE_TO_ENGLISH_FREQ

    # 使用配置字典，避免硬编码
    for chinese_name, english_name in CHINESE_TO_ENGLISH_FREQ.items():
        if chinese_name in sheet_name:
            return english_name

    return None


def process_date_column(
    df: pd.DataFrame,
    sheet_name: str
) -> Optional[pd.DataFrame]:
    """
    处理日期列：转换为DatetimeIndex，去重，排序

    Args:
        df: 输入DataFrame
        sheet_name: Sheet名称（用于日志）

    Returns:
        Optional[pd.DataFrame]: 处理后的DataFrame，失败返回None
    """
    date_col_name = df.columns[0]
    logger.debug(f"使用 '{date_col_name}' 作为日期列")

    try:
        df[date_col_name] = pd.to_datetime(df[date_col_name], errors='coerce')
        original_rows = len(df)
        df = df.dropna(subset=[date_col_name])

        if len(df) < original_rows:
            warnings.warn(
                f"Sheet '{sheet_name}': Removed {original_rows - len(df)} rows with invalid dates."
            )

        if df.empty:
            warnings.warn(f"Sheet '{sheet_name}' became empty after removing invalid dates.")
            return None

        df.set_index(date_col_name, inplace=True)
        df.sort_index(inplace=True)

        if not df.index.is_unique:
            warnings.warn(f"Sheet '{sheet_name}': Found duplicate dates, keeping last.")
            df = df[~df.index.duplicated(keep='last')]

        return df

    except Exception as e:
        warnings.warn(f"Error processing date column for sheet '{sheet_name}': {e}")
        return None


def convert_to_numeric_and_clean(
    df: pd.DataFrame,
    sheet_name: str,
    threshold: float = 1e-9
) -> Optional[pd.DataFrame]:
    """
    转换为数值类型并清理零值和近零值（向量化优化版）

    Args:
        df: 输入DataFrame
        sheet_name: Sheet名称（用于日志）
        threshold: 近零值阈值

    Returns:
        Optional[pd.DataFrame]: 处理后的DataFrame，失败返回None
    """
    logger.debug(f"尝试对 {len(df.columns)} 列进行数值转换")

    # 向量化转换：一次性转换所有列
    df = df.apply(pd.to_numeric, errors='coerce')
    logger.debug("数值转换完成")

    numeric_cols = df.select_dtypes(include=np.number).columns

    if not numeric_cols.empty:
        logger.debug(f"对数值列应用近零阈值 ({threshold}) 并替换零值: {list(numeric_cols)}")

        # 向量化操作：一次性对所有数值列进行mask操作
        # 创建条件掩码（所有列的绝对值小于阈值或等于0）
        mask = (df[numeric_cols].abs() < threshold) | (df[numeric_cols] == 0)

        # 一次性应用mask到所有数值列
        df.loc[:, numeric_cols] = df[numeric_cols].where(~mask, np.nan)

        # 检查是否所有数据都变成NaN
        if df[numeric_cols].isnull().all().all():
            warnings.warn(f"Sheet '{sheet_name}' is all NaN after conversion and cleaning.")
            return None
    else:
        logger.warning("数值转换后未找到数值列")
        return None

    return df


def _process_periodic_frequency(
    df: pd.DataFrame,
    data_type: str,
    freq_param: str
) -> pd.DataFrame:
    """处理周期性频率数据的通用函数（周度、旬度）

    消除周度和旬度处理的重复代码

    Args:
        df: 输入DataFrame
        data_type: 数据类型 ('weekly' 或 'ten_day')
        freq_param: 借调逻辑参数 ('W-FRI' 或 'ten_day')

    Returns:
        pd.DataFrame: 处理后的DataFrame
    """
    from dashboard.preview.modules.industrial.loader import standardize_timestamps, apply_borrowing_logic

    freq_name = '周度' if data_type == 'weekly' else '旬度'
    logger.debug(f"处理{freq_name}数据")

    # 去重
    if not df.index.is_unique:
        original_count = len(df)
        df = df[~df.index.duplicated(keep='first')]
        logger.debug(f"移除 {original_count - len(df)} 个重复时间戳")

    # 时间戳标准化
    df = standardize_timestamps(df, data_type)

    # 借调逻辑
    df = apply_borrowing_logic(df, freq_param)
    logger.debug(f"已应用{freq_name}数据借调逻辑")

    return df


def process_frequency_specific(
    df: pd.DataFrame,
    data_type: str,
    source_prefix: str,
    indicator_source_map: Dict[str, str]
) -> pd.DataFrame:
    """
    按频率进行特定处理（周度、旬度的时间戳标准化和借调）

    Args:
        df: 输入DataFrame
        data_type: 数据类型
        source_prefix: 数据源前缀
        indicator_source_map: 指标来源映射字典（会被修改）

    Returns:
        pd.DataFrame: 处理后的DataFrame
    """
    from dashboard.preview.modules.industrial.loader import normalize_string

    # 月度数据特殊处理：工业增加值日期调整
    if data_type == "monthly":
        cols_to_adjust = [col for col in df.columns if "工业增加值" in col]
        if cols_to_adjust:
            logger.debug(f"调整'工业增加值'指标的日期索引 (找到 {len(cols_to_adjust)} 个)")
            if pd.api.types.is_datetime64_any_dtype(df.index):
                try:
                    df.index = df.index - pd.offsets.MonthEnd(1)
                    logger.debug(f"调整后的索引范围: {df.index.min()} 至 {df.index.max()}")
                except Exception as e:
                    warnings.warn(f"Failed to apply MonthEnd offset: {e}")

    # 周度数据处理（使用通用函数）
    elif data_type == "weekly":
        df = _process_periodic_frequency(df, "weekly", 'W-FRI')

    # 旬度数据处理（使用通用函数）
    elif data_type == "ten_day":
        df = _process_periodic_frequency(df, "ten_day", 'ten_day')

    # 更新指标来源映射并标准化列名
    for col in df.columns:
        map_key = normalize_string(col)
        if map_key not in indicator_source_map:
            indicator_source_map[map_key] = source_prefix

    df.columns = [normalize_string(col) for col in df.columns]

    return df


def process_single_sheet(
    excel_file_handler,
    sheet_name: str,
    file_name: str,
    source_name_base: str,
    indicator_source_map: Dict[str, str],
    indicator_freq_map: Dict[str, str],
    file_buffer=None
) -> Optional[Dict[str, List[pd.DataFrame]]]:
    """处理单个Excel sheet（按变量分配频率）

    Args:
        excel_file_handler: pandas ExcelFile对象
        sheet_name: sheet名称
        file_name: 文件名
        source_name_base: 源文件基础名称
        indicator_source_map: 指标来源映射字典
        indicator_freq_map: 指标频率映射字典
        file_buffer: 文件缓冲区

    Returns:
        Optional[Dict[str, List[pd.DataFrame]]]: {频率: [DataFrame列表]}，失败返回None
    """
    from dashboard.preview.modules.industrial.loader import normalize_string

    logger.debug(f"分析sheet: '{sheet_name}'")

    # 跳过指标字典sheet
    if sheet_name == '指标字典':
        return None

    try:
        # Reset buffer position if reading from BytesIO
        if file_buffer and isinstance(file_buffer, io.BytesIO):
            file_buffer.seek(0)

        logger.debug(f"从sheet '{sheet_name}' 读取数据")

        # 使用统一格式读取
        read_params = {
            'sheet_name': sheet_name,
            'header': 0,
            'dtype': object,
            'keep_default_na': False,
            'na_values': []
        }

        df_sheet = pd.read_excel(excel_file_handler, **read_params)

        if df_sheet.empty:
            warnings.warn(f"     Sheet '{sheet_name}' in '{file_name}' is empty. Skipping.")
            return None

        # 验证格式
        if len(df_sheet.columns) < 2:
            warnings.warn(f"     Sheet '{sheet_name}': 列数不足（需要至少2列：时间列+数据列）. Skipping.")
            return None

        logger.debug(f"成功读取 {len(df_sheet.columns)} 列: 第一列为时间列，其余{len(df_sheet.columns)-1}列为数据变量")

        # 处理日期列
        df_sheet = process_date_column(df_sheet, sheet_name)
        if df_sheet is None:
            return None

        # 数值转换和清理
        df_sheet = convert_to_numeric_and_clean(df_sheet, sheet_name)
        if df_sheet is None:
            return None

        # 验证所有变量都在指标字典中定义了频率
        data_columns = list(df_sheet.columns)
        unknown_vars = []
        for col in data_columns:
            normalized_col = normalize_string(col)
            if normalized_col not in indicator_freq_map:
                unknown_vars.append(col)

        if unknown_vars:
            error_msg = (
                f"Sheet '{sheet_name}' 包含 {len(unknown_vars)} 个未在指标字典中定义频率的变量:\n"
                + "\n".join(f"  - {v}" for v in unknown_vars[:10])
                + (f"\n  ... 等共 {len(unknown_vars)} 个" if len(unknown_vars) > 10 else "")
            )
            raise ValueError(error_msg)

        # 按变量分配到不同频率
        result = {
            'weekly': [],
            'monthly': [],
            'daily': [],
            'ten_day': [],
            'quarterly': [],
            'yearly': []
        }

        source_identifier_prefix = f"{source_name_base}|{sheet_name}"

        for col in data_columns:
            normalized_col = normalize_string(col)
            freq = indicator_freq_map.get(normalized_col)

            if freq and freq in result:
                # 提取单列数据
                col_df = df_sheet[[col]].copy()
                col_df.columns = [normalized_col]

                # 更新指标来源映射
                if normalized_col not in indicator_source_map:
                    indicator_source_map[normalized_col] = source_identifier_prefix

                # 应用频率特定处理
                col_df = _apply_frequency_processing(col_df, freq, normalized_col)

                result[freq].append(col_df)
                logger.debug(f"变量 '{normalized_col}' 分配到 '{freq}' 频率")

        return result

    except ValueError:
        # 重新抛出验证错误
        raise
    except Exception as e:
        warnings.warn(f"     Error processing sheet '{sheet_name}' in '{file_name}': {e}. Skipping sheet.")
        return None


def _apply_frequency_processing(
    df: pd.DataFrame,
    freq: str,
    col_name: str
) -> pd.DataFrame:
    """对单列数据应用频率特定处理

    Args:
        df: 单列DataFrame
        freq: 频率类型
        col_name: 列名（用于日志）

    Returns:
        pd.DataFrame: 处理后的DataFrame
    """
    # 月度数据特殊处理：工业增加值日期调整
    if freq == "monthly" and "工业增加值" in col_name:
        if pd.api.types.is_datetime64_any_dtype(df.index):
            try:
                df = df.copy()
                df.index = df.index - pd.offsets.MonthEnd(1)
                logger.debug(f"调整'{col_name}'的日期索引")
            except Exception as e:
                warnings.warn(f"Failed to apply MonthEnd offset for '{col_name}': {e}")

    # 周度数据处理
    elif freq == "weekly":
        df = _process_periodic_frequency(df, "weekly", 'W-FRI')

    # 旬度数据处理
    elif freq == "ten_day":
        df = _process_periodic_frequency(df, "ten_day", 'ten_day')

    return df


def process_single_excel_file(
    file_input,
    indicator_industry_map: Dict[str, str],
    indicator_unit_map: Dict[str, str],
    indicator_type_map: Dict[str, str],
    indicator_freq_map: Dict[str, str],
    read_mapping_sheet: bool = False
) -> Tuple[Dict[str, List[pd.DataFrame]], Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]]:
    """处理单个Excel文件

    Args:
        file_input: 上传的文件对象
        indicator_industry_map: 行业映射字典（会被更新）
        indicator_unit_map: 单位映射字典（会被更新）
        indicator_type_map: 类型映射字典（会被更新）
        indicator_freq_map: 频率映射字典（会被更新）
        read_mapping_sheet: 是否读取指标字典映射

    Returns:
        Tuple: (数据框字典, 指标来源映射, 行业映射, 单位映射, 类型映射, 频率映射)
    """
    # 初始化结果容器
    all_dfs_by_type = {
        'weekly': [],
        'monthly': [],
        'daily': [],
        'ten_day': [],
        'quarterly': [],
        'yearly': []
    }
    indicator_source_map = {}

    # 处理Streamlit上传的文件对象
    try:
        file_buffer = io.BytesIO(file_input.getvalue())
        file_name_for_display = file_input.name
    except Exception as e:
        logger.error(f"文件读取失败: {e}")
        warnings.warn(f"Failed to read file: {e}")
        return all_dfs_by_type, indicator_source_map, indicator_industry_map, indicator_unit_map, indicator_type_map, indicator_freq_map
    source_name_base = file_name_for_display.rsplit('.', 1)[0] if '.' in file_name_for_display else file_name_for_display

    try:
        excel_file_handler = pd.ExcelFile(file_buffer)
        logger.info(f"处理文件: {file_name_for_display}")
        sheet_names = excel_file_handler.sheet_names
        logger.debug(f"找到sheets: {', '.join(sheet_names)}")

        # 读取指标字典（如果需要）
        if read_mapping_sheet and '指标字典' in sheet_names:
            logger.debug("尝试从'指标字典'sheet读取映射")
            industry_map_temp, unit_map_temp, type_map_temp, freq_map_temp = read_indicator_mapping(
                excel_file_handler,
                '指标字典',
                file_buffer
            )
            if industry_map_temp:
                indicator_industry_map.update(industry_map_temp)
            if unit_map_temp:
                indicator_unit_map.update(unit_map_temp)
            if type_map_temp:
                indicator_type_map.update(type_map_temp)
            if freq_map_temp:
                indicator_freq_map.update(freq_map_temp)
                logger.info(f"成功读取 {len(freq_map_temp)} 个频率映射")

        # 验证是否有频率映射（必须在处理数据sheet之前完成）
        if not indicator_freq_map:
            raise ValueError("指标字典中未找到频率映射，无法处理数据。请确保'指标字典'sheet包含'频率'列。")

        # 处理每个sheet
        processed_sheets = 0
        for sheet_name in sheet_names:
            result = process_single_sheet(
                excel_file_handler,
                sheet_name,
                file_name_for_display,
                source_name_base,
                indicator_source_map,
                indicator_freq_map,
                file_buffer
            )

            if result:
                # result是Dict[str, List[pd.DataFrame]]
                for freq, dfs in result.items():
                    all_dfs_by_type[freq].extend(dfs)
                processed_sheets += 1

        if processed_sheets > 0:
            logger.info(f"文件 {file_name_for_display}: 已处理 {processed_sheets} 个sheets")
        else:
            warnings.warn(f"--- No valid data sheets found in file: {file_name_for_display} ---")

    except ValueError:
        # 重新抛出验证错误
        raise
    except Exception as e:
        warnings.warn(f"General error processing file {file_name_for_display}: {e}")
    finally:
        if 'excel_file_handler' in locals():
            try:
                excel_file_handler.close()
            except Exception:
                pass

    return all_dfs_by_type, indicator_source_map, indicator_industry_map, indicator_unit_map, indicator_type_map, indicator_freq_map


def merge_dataframes_by_type(
    all_dfs_dict: Dict[str, List[pd.DataFrame]]
) -> Dict[str, pd.DataFrame]:
    """
    按数据类型合并DataFrame列表（从配置导入，避免硬编码）

    Args:
        all_dfs_dict: 数据类型到DataFrame列表的字典

    Returns:
        Dict[str, pd.DataFrame]: 数据类型到合并后DataFrame的字典
    """
    from dashboard.preview.modules.industrial.config import ENGLISH_TO_CHINESE_FREQ

    result = {}

    # 使用配置字典，避免硬编码
    for data_type, df_list in all_dfs_dict.items():
        type_name = ENGLISH_TO_CHINESE_FREQ.get(data_type, data_type)
        logger.debug(f"合并{type_name}数据")

        if df_list:
            merged_df = pd.concat(df_list, axis=1)
            merged_df = merged_df.loc[:, ~merged_df.columns.duplicated(keep='first')]
            merged_df.sort_index(inplace=True)
            result[data_type] = merged_df
            logger.info(f"最终{type_name}数据形状: {merged_df.shape}")
        else:
            result[data_type] = pd.DataFrame()
            logger.debug(f"未找到{type_name}数据")

    return result
