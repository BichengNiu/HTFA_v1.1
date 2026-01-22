import pandas as pd
import numpy as np
import warnings
from datetime import datetime
import io
from typing import List, Tuple, Dict, Any, Optional
import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LoadedIndustrialData:
    """工业数据加载结果封装

    使用dataclass提供类型安全和清晰的数据结构
    """
    # DataFrame数据
    weekly_df: pd.DataFrame
    monthly_df: pd.DataFrame
    daily_df: pd.DataFrame
    ten_day_df: pd.DataFrame
    quarterly_df: pd.DataFrame
    yearly_df: pd.DataFrame

    # 映射关系
    source_map: Dict[str, str]
    indicator_industry_map: Dict[str, str]
    indicator_unit_map: Dict[str, str]
    indicator_type_map: Dict[str, str]
    indicator_freq_map: Dict[str, str]


    def get_all_dataframes(self) -> Dict[str, pd.DataFrame]:
        """获取所有DataFrame的字典

        Returns:
            {频率名: DataFrame}字典
        """
        return {
            'weekly': self.weekly_df,
            'monthly': self.monthly_df,
            'daily': self.daily_df,
            'ten_day': self.ten_day_df,
            'quarterly': self.quarterly_df,
            'yearly': self.yearly_df
        }

    def get_all_maps(self) -> Dict[str, Dict[str, str]]:
        """获取所有映射字典

        Returns:
            包含所有映射的字典
        """
        return {
            'source': self.source_map,
            'industry': self.indicator_industry_map,
            'unit': self.indicator_unit_map,
            'type': self.indicator_type_map,
            'freq': self.indicator_freq_map
        } 

def normalize_string(s: str) -> str:
    """将字符串转换为标准化形式：半角，去除首尾空格，合并中间空格。"""
    if not isinstance(s, str):
        return s # Return original if not a string
    # 转换全角为半角 (常见标点和空格)
    full_width = "（）：　"
    half_width = "(): "
    translation_table = str.maketrans(full_width, half_width)
    s = s.translate(translation_table)
    # 特殊处理：确保冒号后面有空格
    s = re.sub(r':(?!\s)', ': ', s)
    # 去除首尾空格
    s = s.strip()
    # 合并中间多余空格
    s = re.sub(r'\s+', ' ', s)
    return s

def standardize_timestamps(df_input: pd.DataFrame, data_type: str) -> pd.DataFrame:
    """
    将时间戳统一到标准时间点（向量化优化版 + 条件性copy）

    性能优化：只在需要修改时才copy，节省内存

    Args:
        df_input: 输入DataFrame，必须有DatetimeIndex
        data_type: 数据类型 ('weekly' for 周度, 'ten_day' for 旬度)

    Returns:
        时间戳统一后的DataFrame
    """
    if df_input.empty or not isinstance(df_input.index, pd.DatetimeIndex):
        return df_input

    # 仅对周度数据进行时间戳标准化，旬度数据保留原始时间戳
    if data_type != "weekly":
        return df_input

    # 周度数据：将所有时间戳统一到当周的周五（向量化操作）
    logger.debug("统一周度数据时间戳到周五")
    dates = df_input.index

    # 使用向量化操作计算周五日期
    weekdays = dates.weekday  # 0=Monday, ..., 6=Sunday

    # 计算到周五的天数（向量化）
    # 修正逻辑：周六、周日应该回到上周五，而不是下周五
    days_to_friday = np.where(
        weekdays <= 4,  # Monday to Friday
        4 - weekdays,   # 到当周周五的天数
        -(weekdays - 4)  # 周六、周日向前偏移到上周五
    )

    # 使用向量化操作计算新索引
    new_index = dates + pd.to_timedelta(days_to_friday, unit='D')

    df_result = df_input.copy()
    df_result.index = new_index

    logger.debug(f"周度数据时间戳统一完成，数据范围: {df_result.index.min().strftime('%Y-%m-%d')} 至 {df_result.index.max().strftime('%Y-%m-%d')}")
    if not df_result.index.is_unique:
        logger.debug(f"时间戳统一后存在 {df_result.index.duplicated().sum()} 个重复时间戳，将在借调后处理")

    # 重新排序
    df_result.sort_index(inplace=True)

    return df_result

def _generate_weekly_boundaries(min_date, max_date) -> pd.DatetimeIndex:
    """生成周度时间窗口边界

    Args:
        min_date: 最小日期
        max_date: 最大日期

    Returns:
        pd.DatetimeIndex: 周度边界时间点
    """
    start_of_first_week = min_date - pd.Timedelta(days=min_date.weekday() + 2)
    end_extended = max_date + pd.Timedelta(days=14)
    boundary_times = pd.date_range(start=start_of_first_week, end=end_extended, freq='W-FRI')
    # 过滤出与数据范围相关的边界
    boundary_times = boundary_times[(boundary_times >= min_date - pd.Timedelta(days=7)) &
                                   (boundary_times <= max_date + pd.Timedelta(days=7))]
    return boundary_times


def _generate_tenday_boundaries(min_date, max_date) -> pd.DatetimeIndex:
    """生成旬度时间窗口边界

    Args:
        min_date: 最小日期
        max_date: 最大日期

    Returns:
        pd.DatetimeIndex: 旬度边界时间点
    """
    from calendar import monthrange
    boundary_times = []

    # 从数据最小日期的前一个月开始，到最大日期的后一个月结束
    start_month = min_date.replace(day=1)
    if start_month.month == 1:
        start_month = start_month.replace(year=start_month.year - 1, month=12)
    else:
        start_month = start_month.replace(month=start_month.month - 1)

    end_month = max_date.replace(day=1)
    if end_month.month == 12:
        end_month = end_month.replace(year=end_month.year + 1, month=1)
    else:
        end_month = end_month.replace(month=end_month.month + 1)

    current_date = start_month
    while current_date <= end_month:
        for day in [10, 20]:
            try:
                boundary_date = current_date.replace(day=day)
                boundary_times.append(boundary_date)
            except ValueError:
                pass

        # 月末
        try:
            last_day = monthrange(current_date.year, current_date.month)[1]
            month_end = current_date.replace(day=last_day)
            boundary_times.append(month_end)
        except ValueError:
            pass

        # 移动到下个月
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return pd.DatetimeIndex(boundary_times).sort_values()


def _get_window_bounds(i, boundary_times, target_freq, min_date):
    """获取时间窗口的开始和结束时间

    Args:
        i: 边界索引
        boundary_times: 边界时间序列
        target_freq: 频率类型
        min_date: 最小日期

    Returns:
        tuple: (current_start, current_end, next_start, next_end)
    """
    current_boundary = boundary_times[i]
    next_boundary = boundary_times[i+1]

    if target_freq == 'W-FRI':
        current_window_start = current_boundary - pd.Timedelta(days=6)
        current_window_end = current_boundary
        next_window_start = next_boundary - pd.Timedelta(days=6)
        next_window_end = next_boundary
    elif target_freq == 'ten_day':
        if i == 0:
            current_window_start = min_date
        else:
            current_window_start = boundary_times[i-1] + pd.Timedelta(days=1)
        current_window_end = current_boundary
        next_window_start = current_boundary + pd.Timedelta(days=1)
        next_window_end = next_boundary
    else:
        return None, None, None, None

    return current_window_start, current_window_end, next_window_start, next_window_end


def _handle_duplicate_indices(df: pd.DataFrame) -> pd.DataFrame:
    """处理重复的时间索引

    Args:
        df: 输入DataFrame

    Returns:
        pd.DataFrame: 去重后的DataFrame
    """
    if not df.index.is_unique:
        duplicate_count = df.index.duplicated().sum()
        logger.info(f"[最终去重] 借调后仍存在 {duplicate_count} 个重复时间戳，使用平均值合并")
        df = df.groupby(df.index).mean()
        logger.info(f"[最终去重] 去重完成，最终数据形状: {df.shape}")
    return df


def _precompute_windows(boundary_times, target_freq, min_date):
    """预计算所有窗口边界，避免循环内重复计算

    Args:
        boundary_times: 边界时间序列
        target_freq: 频率类型
        min_date: 最小日期

    Returns:
        list: 窗口边界字典列表
    """
    windows = []
    for i in range(len(boundary_times) - 1):
        window = _get_window_bounds(i, boundary_times, target_freq, min_date)
        if window[0] is not None:
            windows.append({
                'current_start': window[0],
                'current_end': window[1],
                'next_start': window[2],
                'next_end': window[3]
            })
    return windows


def _is_valid_borrow_target(series_data, target_time):
    """检查目标位置是否为有效的借调目标

    Args:
        series_data: 数据序列
        target_time: 目标时间

    Returns:
        bool: 是否可以借调到该位置
    """
    if target_time not in series_data.index:
        return False

    target_values = series_data.loc[target_time]
    if isinstance(target_values, pd.Series):
        # 如果是Series（重复索引），检查是否所有值都是NaN
        return target_values.isna().all()
    else:
        # 如果是标量
        return pd.isna(target_values)


def _precompute_window_data(series_data, windows):
    """预计算所有窗口的数据，避免重复切片（性能优化）

    Args:
        series_data: 列数据序列
        windows: 预计算的窗口边界列表

    Returns:
        list: 窗口数据列表，每项包含current、next、target_time、window_bounds
    """
    window_data_list = []

    for window in windows:
        current_mask = (series_data.index >= window['current_start']) & \
                      (series_data.index <= window['current_end'])
        next_mask = (series_data.index >= window['next_start']) & \
                   (series_data.index <= window['next_end'])

        window_data_list.append({
            'current': series_data[current_mask].dropna(),
            'next': series_data[next_mask].dropna(),
            'target_time': window['current_end'],
            'current_start': window['current_start'],  # 保留边界信息
            'current_end': window['current_end']
        })

    return window_data_list


def _apply_borrowing_batch(series_data, window_data_list):
    """批量应用借调操作，减少索引操作（性能优化）

    Args:
        series_data: 列数据序列
        window_data_list: 预计算的窗口数据列表

    Returns:
        tuple: (更新后的序列, 借调次数)
    """
    updates = {}  # {时间: 新值}
    removes = []  # [要删除的时间]
    borrowing_count = 0

    for wd in window_data_list:
        current_data = wd['current']
        next_data = wd['next']
        target_time = wd['target_time']

        # 借调条件：当前窗口无值 AND 下个窗口有2个或更多数据点
        if len(current_data) == 0 and len(next_data) >= 2:
            borrowed_value = next_data.iloc[0]
            borrowed_time = next_data.index[0]

            # 如果目标时间不在索引中，找最接近的时间点
            if target_time not in series_data.index:
                # 在当前窗口范围内查找最接近的时间
                current_mask = (series_data.index >= wd['current_start']) & \
                              (series_data.index <= wd['current_end'])
                current_window_times = series_data.index[current_mask]

                if len(current_window_times) > 0:
                    # 找到最接近target_time的时间点
                    target_time = current_window_times[
                        np.argmin(np.abs((current_window_times - target_time).total_seconds()))
                    ]
                else:
                    continue

            # 检查是否可以借调到该位置
            if _is_valid_borrow_target(series_data, target_time) and borrowed_time in series_data.index:
                updates[target_time] = borrowed_value
                removes.append(borrowed_time)
                borrowing_count += 1

    # 批量应用更新（一次性操作）
    if updates:
        series_data.update(pd.Series(updates))
    if removes:
        series_data.loc[removes] = np.nan

    return series_data, borrowing_count


def _apply_borrowing_to_column(series_data, windows, target_freq, col_name=""):
    """对单列应用借调逻辑（优化版：使用预计算和批量操作）

    Args:
        series_data: 列数据序列
        windows: 预计算的窗口边界列表
        target_freq: 频率类型
        col_name: 列名（用于日志）

    Returns:
        pd.Series: 应用借调后的序列
    """
    series_data = series_data.copy()

    # 子任务1：预计算窗口数据（避免重复切片）
    window_data_list = _precompute_window_data(series_data, windows)

    # 子任务2：批量借调（减少索引操作）
    series_data, borrowing_count = _apply_borrowing_batch(series_data, window_data_list)

    if borrowing_count > 0 and col_name:
        logger.info(f"[借调汇总] {col_name}: 完成 {borrowing_count} 次借调操作")

    return series_data


def apply_borrowing_logic(df_input: pd.DataFrame, target_freq: str) -> pd.DataFrame:
    """对时间序列数据应用"借调"逻辑（优化版）

    优化要点：
    1. 边界时间只生成一次（移到循环外）
    2. 预计算所有窗口边界
    3. 提取单列处理逻辑为独立函数

    借调逻辑：在原始数据的基础上，当某个时间窗口完全没有数据，但下一个时间窗口
    有2个或更多数据点时，将下一个窗口的第一个值复制到前一个窗口的合适位置。

    核心原则：
    1. 不进行频率转换，保持原始数据结构
    2. 总有效观测值数量严格不变（只是重新分布）
    3. 在原始时间序列中进行数据填充

    Args:
        df_input: 输入DataFrame，必须有DatetimeIndex
        target_freq: 目标频率标识 ('W-FRI' for weekly, 'ten_day' for ten-day)

    Returns:
        应用借调逻辑后的DataFrame，结构和原始数据完全相同
    """
    if df_input.empty or not isinstance(df_input.index, pd.DatetimeIndex):
        return df_input

    df_result = df_input.copy()

    # 优化点1：边界时间生成移到外层，只计算一次
    min_date = df_result.index.min()
    max_date = df_result.index.max()

    try:
        if target_freq == 'W-FRI':
            boundary_times = _generate_weekly_boundaries(min_date, max_date)
        elif target_freq == 'ten_day':
            boundary_times = _generate_tenday_boundaries(min_date, max_date)
        else:
            return df_result
    except Exception as e:
        logger.error(f"创建边界时间失败: {e}")
        return df_result

    if len(boundary_times) < 2:
        return df_result

    # 优化点2：预计算窗口边界，避免循环内重复计算
    windows = _precompute_windows(boundary_times, target_freq, min_date)

    # 优化点3：对每列应用借调逻辑（使用独立函数）
    for col in df_result.columns:
        series_data = df_result[col]
        if series_data.dropna().empty:
            continue

        df_result[col] = _apply_borrowing_to_column(
            series_data, windows, target_freq, col_name=col
        )

    # 处理重复索引
    df_result = _handle_duplicate_indices(df_result)

    return df_result

def load_and_process_data(excel_files_input: List[Any]) -> LoadedIndustrialData:
    """
    读取并处理Excel文件，返回封装的工业数据对象

    此函数已重构为简洁版本，复杂逻辑已提取到辅助函数中

    Args:
        excel_files_input: 上传的文件对象列表

    Returns:
        LoadedIndustrialData: 包含所有数据和映射的封装对象
    """
    import streamlit as st
    from dashboard.preview.modules.industrial.processor import (
        process_single_excel_file,
        merge_dataframes_by_type
    )

    # 初始化映射字典
    indicator_industry_map = {}
    indicator_unit_map = {}
    indicator_type_map = {}
    indicator_freq_map = {}

    # 初始化数据容器
    all_dfs_by_freq = {
        'weekly': [],
        'monthly': [],
        'daily': [],
        'ten_day': [],
        'quarterly': [],
        'yearly': []
    }
    all_indicator_source_maps = []

    logger.info(f"开始处理 {len(excel_files_input)} 个文件")

    # 处理每个文件
    for idx, file_input in enumerate(excel_files_input):
        # 只有第一个文件读取指标字典映射
        read_mapping = (idx == 0)

        file_dfs, source_map, ind_map, unit_map, type_map, freq_map = process_single_excel_file(
            file_input,
            indicator_industry_map,
            indicator_unit_map,
            indicator_type_map,
            indicator_freq_map,
            read_mapping_sheet=read_mapping
        )

        # 使用返回的映射字典更新
        indicator_industry_map = ind_map
        indicator_unit_map = unit_map
        indicator_type_map = type_map
        indicator_freq_map = freq_map

        # 合并各频率数据
        for freq, dfs in file_dfs.items():
            all_dfs_by_freq[freq].extend(dfs)

        # 收集指标来源映射
        all_indicator_source_maps.append(source_map)

    # 检查是否有数据被处理
    total_dfs = sum(len(dfs) for dfs in all_dfs_by_freq.values())

    if total_dfs == 0:
        warnings.warn("No files were successfully processed.")
        return LoadedIndustrialData(
            weekly_df=pd.DataFrame(),
            monthly_df=pd.DataFrame(),
            daily_df=pd.DataFrame(),
            ten_day_df=pd.DataFrame(),
            quarterly_df=pd.DataFrame(),
            yearly_df=pd.DataFrame(),
            source_map={},
            indicator_industry_map={},
            indicator_unit_map={},
            indicator_type_map={},
            indicator_freq_map={}
        )

    # 合并所有指标来源映射
    merged_source_map = {}
    for source_map in all_indicator_source_maps:
        merged_source_map.update(source_map)

    # 合并各频率的DataFrame
    merged_dfs = merge_dataframes_by_type(all_dfs_by_freq)

    # 月度数据特殊处理提示（已禁用对齐）
    if not merged_dfs.get('monthly', pd.DataFrame()).empty:
        logger.info("月度数据已加载（已禁用月末对齐以保持数据完整性）")

    logger.info("数据处理完成")

    return LoadedIndustrialData(
        weekly_df=merged_dfs.get('weekly', pd.DataFrame()),
        monthly_df=merged_dfs.get('monthly', pd.DataFrame()),
        daily_df=merged_dfs.get('daily', pd.DataFrame()),
        ten_day_df=merged_dfs.get('ten_day', pd.DataFrame()),
        quarterly_df=merged_dfs.get('quarterly', pd.DataFrame()),
        yearly_df=merged_dfs.get('yearly', pd.DataFrame()),
        source_map=merged_source_map,
        indicator_industry_map=indicator_industry_map,
        indicator_unit_map=indicator_unit_map,
        indicator_type_map=indicator_type_map,
        indicator_freq_map=indicator_freq_map
    )

# === 行业工具函数 ===

def extract_industry_name(source_string: str) -> str:
    """
    从 '文件名|工作表名' 格式的字符串中提取核心行业名称。
    规则：优先返回工作表名中第一个既不是频度/来源关键字、也不是空的 token。
    允许英文缩写（如 PMI/CPI/PPI）作为行业名。
    """
    try:
        # 分割文件名与sheet名
        parts = str(source_string).split('|')
        sheet_name = parts[1] if len(parts) >= 2 else parts[0]

        # 规范化：去空格、统一分隔符
        sheet_name_clean = str(sheet_name).strip()
        # 以 _ - 空格 分词
        import re
        tokens = [t.strip() for t in re.split(r'[_\-\s]+', sheet_name_clean) if t and t.strip()]

        if not tokens:
            return sheet_name_clean or "未知"

        # 需要过滤掉的"频度/来源/噪音"词
        drop_words = set([
            "日度", "周度", "月度", "季度", "年度",
            "Wind", "wind", "同花顺", "TongHuaShun", "tonghuashun",
            "Mysteel", "mysteel", "Myteel", "myteel"
        ])

        # 允许英文缩写：只要不是 drop_words 就认为是候选行业
        for tok in tokens:
            if tok not in drop_words:
                return tok  # 首个有效 token 直接作为行业名（例如 "PMI"）

        # 兜底：如果都被过滤了，就返回第一个 token
        return tokens[0]

    except Exception:
        # 出错时尽量返回原始 sheet 名，避免 None
        return str(source_string).split('|')[-1] or "未知"


# === IndustrialLoader类（继承BaseDataLoader） ===

from dashboard.preview.core.base_loader import BaseDataLoader
from dashboard.preview.core.base_config import BasePreviewConfig
from dashboard.preview.domain.models import LoadedPreviewData


class IndustrialLoader(BaseDataLoader):
    """工业数据加载器

    继承BaseDataLoader，封装工业数据加载逻辑
    """

    def __init__(self, config: BasePreviewConfig):
        """初始化工业数据加载器

        Args:
            config: 配置对象
        """
        super().__init__(config)

    def load_and_process_data(self, files: List[Any]) -> LoadedPreviewData:
        """加载并处理数据

        Args:
            files: 文件对象列表

        Returns:
            LoadedPreviewData: 标准化的数据对象
        """
        # 调用原有的load_and_process_data函数
        industrial_data = load_and_process_data(files)

        # 转换为LoadedPreviewData
        return self._convert_to_preview_data(industrial_data)

    def extract_industry_name(self, source: str) -> str:
        """从数据源提取行业名称

        Args:
            source: 数据源字符串

        Returns:
            str: 行业名称
        """
        return extract_industry_name(source)

    def get_state_namespace(self) -> str:
        """获取状态命名空间

        Returns:
            str: 状态命名空间前缀
        """
        return 'preview.industrial'

    def _convert_to_preview_data(self, industrial_data: 'LoadedIndustrialData') -> LoadedPreviewData:
        """将LoadedIndustrialData转换为LoadedPreviewData

        Args:
            industrial_data: 工业数据对象

        Returns:
            LoadedPreviewData: 通用预览数据对象
        """
        return LoadedPreviewData(
            dataframes={
                'weekly': industrial_data.weekly_df,
                'monthly': industrial_data.monthly_df,
                'daily': industrial_data.daily_df,
                'ten_day': industrial_data.ten_day_df,
                'quarterly': industrial_data.quarterly_df,
                'yearly': industrial_data.yearly_df
            },
            source_map=industrial_data.source_map,
            indicator_industry_map=industrial_data.indicator_industry_map,
            indicator_unit_map=industrial_data.indicator_unit_map,
            indicator_type_map=industrial_data.indicator_type_map,
            indicator_freq_map=industrial_data.indicator_freq_map,
            module_name='industrial'
        )


# 导出的公共接口
__all__ = [
    'IndustrialLoader',
    'load_and_process_data',
    'normalize_string',
    'extract_industry_name'
]

