# -*- coding: utf-8 -*-
"""
行业映射校验模块

用于检测指标字典定义的行业映射与sheet名称推断的行业映射之间的冲突
"""

import logging
from typing import Dict, List, Any
from dashboard.models.DFM.utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


def validate_industry_mapping(
    reference_map: Dict[str, str],
    sheet_based_map: Dict[str, str],
    variable_list: List[str]
) -> Dict[str, Any]:
    """
    对比指标字典行业映射与sheet名称推断的映射，检测冲突

    Args:
        reference_map: 指标字典定义的行业映射（标准化键）
        sheet_based_map: 从sheet名称推断的行业映射（标准化键）
        variable_list: 最终数据中的变量列表（原始名称）

    Returns:
        Dict包含:
        - conflicts: 冲突变量列表，每项包含变量名和两个来源的行业
        - undefined_in_reference: 在指标字典中未定义的变量列表
        - conflict_count: 冲突数量
        - undefined_count: 未定义数量
        - validation_passed: 是否通过校验（无冲突且无未定义）
    """

    conflicts = []
    undefined_in_reference = []

    for var_original in variable_list:
        var_norm = normalize_text(var_original)

        if not var_norm:
            continue

        reference_industry = reference_map.get(var_norm)
        sheet_industry = sheet_based_map.get(var_norm)

        # 检查是否在指标字典中未定义
        if not reference_industry:
            undefined_in_reference.append(var_original)

        # 检查冲突（两者都有定义但不一致）
        if reference_industry and sheet_industry:
            if reference_industry != sheet_industry:
                conflicts.append({
                    'variable': var_original,
                    'reference_industry': reference_industry,
                    'sheet_industry': sheet_industry
                })

    result = {
        'conflicts': conflicts,
        'undefined_in_reference': undefined_in_reference,
        'conflict_count': len(conflicts),
        'undefined_count': len(undefined_in_reference),
        'validation_passed': len(conflicts) == 0 and len(undefined_in_reference) == 0
    }

    return result


def print_validation_report(validation_result: Dict[str, Any]) -> None:
    """
    打印行业映射校验报告

    Args:
        validation_result: validate_industry_mapping()的返回结果
    """

    logger.info("=== [行业映射校验] 校验报告 ===")

    if validation_result['validation_passed']:
        logger.info("校验通过: 所有变量的行业映射一致且完整定义")
        return

    conflict_count = validation_result['conflict_count']
    undefined_count = validation_result['undefined_count']

    if conflict_count > 0:
        logger.warning("发现 %d 个变量的指标字典行业与Sheet位置不一致", conflict_count)
        logger.info("系统将使用指标字典定义的行业（Sheet名称仅用于数据组织）")

        conflicts = validation_result['conflicts']
        logger.info("冲突详情（显示前10个）:")
        for item in conflicts[:10]:
            logger.info("  变量: %s", item['variable'])
            logger.info("    - 指标字典定义: %s", item['reference_industry'])
            logger.info("    - Sheet名称推断: %s", item['sheet_industry'])

        if conflict_count > 10:
            logger.info("  ... 还有 %d 个冲突变量", conflict_count - 10)

    if undefined_count > 0:
        logger.warning("发现 %d 个变量在指标字典中未定义行业", undefined_count)
        logger.info("这些变量将被标记为\"Unknown\"行业")

        undefined = validation_result['undefined_in_reference']
        logger.info("未定义变量（显示前10个）:")
        for var in undefined[:10]:
            logger.info("  - %s", var)

        if undefined_count > 10:
            logger.info("  ... 还有 %d 个未定义变量", undefined_count - 10)

    logger.info("=== [行业映射校验] 报告结束 ===")


__all__ = [
    'validate_industry_mapping',
    'print_validation_report'
]
