"""经济工作簿完整性与覆盖统计。"""
import pandas as pd

def _calculate_indicator_detail(indicator, frequency, series, industry, ind_type):
    """计算单个指标在某频率下的详细信息

    Args:
        indicator: 指标名称
        frequency: 频率名称（中文）
        series: 数据序列（已dropna）
        industry: 行业名称
        ind_type: 指标类型

    Returns:
        dict: 包含指标名称、行业、类型、频率、时间范围、有效值、缺失率
    """
    start_date = series.index.min()
    end_date = series.index.max()

    # 计算期望数据点数
    expected_points = calculate_expected_data_points(
        start_date, end_date, frequency
    )

    # 计算有效值和缺失率
    effective_values = len(series)
    missing_rate = (
        (expected_points - effective_values) / expected_points * 100
        if expected_points > 0 else 0
    )

    return {
        "指标名称": indicator,
        "行业": industry,
        "类型": ind_type,
        "频率": frequency,
        "时间范围": f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}",
        "有效值": effective_values,
        "缺失率": f"{missing_rate:.1f}%"
    }


def calculate_indicator_statistics(all_data_dict, indicator_maps):
    """优化版统计计算：反转循环顺序，降低复杂度

    优化前：O(indicators × frequencies²) - 先遍历指标，内部再调用get_indicator_frequencies遍历所有频率
    优化后：O(frequencies × indicators) - 先遍历频率，再遍历该频率的指标

    Args:
        all_data_dict: {频率名: DataFrame}字典
        indicator_maps: 包含industry、type、clean_industry的映射字典

    Returns:
        dict: {
            'all_indicators': set,
            'industry_stats': {行业名: 指标数量},
            'type_stats': {类型名: 指标数量},
            'frequency_stats': {频率名: 指标数量},
            'indicator_details': [{指标详情字典}]
        }
    """
    # 初始化统计字典
    stats = {
        'all_indicators': set(),
        'industry_stats': {},
        'type_stats': {},
        'frequency_stats': {},
        'indicator_details': []
    }

    # 已处理的指标集合（用于行业/类型统计去重）
    processed_for_industry_type = set()

    # 优化：先遍历频率，再遍历指标（降低复杂度）
    for freq_name, df in all_data_dict.items():
        if df is None or df.empty:
            continue

        # 统计该频率的指标数量
        freq_indicators = set(df.columns)
        stats['frequency_stats'][freq_name] = len(freq_indicators)

        # 遍历该频率的指标
        for indicator in freq_indicators:
            # 收集所有指标
            stats['all_indicators'].add(indicator)

            # 行业和类型统计（每个指标只统计一次）
            if indicator not in processed_for_industry_type:
                industry = indicator_maps['industry'].get(indicator, "未分类")
                stats['industry_stats'][industry] = stats['industry_stats'].get(industry, 0) + 1

                ind_type = indicator_maps['type'].get(indicator, "未分类")
                stats['type_stats'][ind_type] = stats['type_stats'].get(ind_type, 0) + 1

                processed_for_industry_type.add(indicator)
            else:
                # 已处理，直接获取
                industry = indicator_maps['industry'].get(indicator, "未分类")
                ind_type = indicator_maps['type'].get(indicator, "未分类")

            # 生成该频率的详细信息
            series = df[indicator].dropna()
            if not series.empty:
                detail = _calculate_indicator_detail(
                    indicator, freq_name, series, industry, ind_type
                )
                stats['indicator_details'].append(detail)

    return stats


def calculate_expected_data_points(start_date, end_date, frequency):
    """计算期望的数据点数

    用于计算缺失率时,应该相对于有效值在其时间范围内的理论数据点数

    Args:
        start_date: 开始日期
        end_date: 结束日期
        frequency: 数据频率(周度、月度、日度、旬度、年度)

    Returns:
        int: 应该存在的数据点数
    """
    if frequency == "周度":
        days_diff = (end_date - start_date).days
        theoretical_weeks = days_diff // 7 + 1
        return theoretical_weeks

    elif frequency == "月度":
        months_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
        return months_diff

    elif frequency == "日度":
        days_diff = (end_date - start_date).days + 1
        return days_diff

    elif frequency == "旬度":
        start_year, start_month, start_day = start_date.year, start_date.month, start_date.day
        end_year, end_month, end_day = end_date.year, end_date.month, end_date.day

        start_ten = 1 if start_day <= 10 else (2 if start_day <= 20 else 3)
        end_ten = 1 if end_day <= 10 else (2 if end_day <= 20 else 3)

        if start_year == end_year and start_month == end_month:
            return end_ten - start_ten + 1

        start_month_tens = 3 - start_ten + 1
        end_month_tens = end_ten
        total_months = (end_year - start_year) * 12 + (end_month - start_month)
        middle_months = total_months - 1
        middle_tens = middle_months * 3 if middle_months > 0 else 0

        return start_month_tens + middle_tens + end_month_tens

    elif frequency == "年度":
        years_diff = end_date.year - start_date.year + 1
        return years_diff

    elif frequency == "季度":
        # 计算季度数
        start_quarter = (start_date.month - 1) // 3 + 1
        end_quarter = (end_date.month - 1) // 3 + 1
        quarters = (end_date.year - start_date.year) * 4 + (end_quarter - start_quarter) + 1
        return quarters

    else:
        return 0
