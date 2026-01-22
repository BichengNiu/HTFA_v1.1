"""
数据验证模块
Data Validation Module

提供数据格式验证和数据质量检查功能
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """
    数据验证结果

    使用dataclass替代三元组返回值，提供更清晰的API和类型安全
    """
    is_valid: bool
    error_message: str = ""
    matched_indicators_count: int = 0
    matched_indicators: List[str] = field(default_factory=list)
    available_columns_count: int = 0
    available_columns: List[str] = field(default_factory=list)
    macro_shape: tuple = field(default_factory=tuple)
    weights_shape: tuple = field(default_factory=tuple)

    @property
    def is_warning_only(self) -> bool:
        """是否仅警告（有部分匹配但不完全）"""
        return self.matched_indicators_count > 0 and not self.is_valid

    @property
    def has_matches(self) -> bool:
        """是否有匹配的指标"""
        return self.matched_indicators_count > 0


def validate_data_format(
    df_macro: pd.DataFrame,
    df_weights: pd.DataFrame,
    target_columns: List[str]
) -> ValidationResult:
    """
    验证数据格式并返回详细的诊断信息

    Args:
        df_macro: 分行业工业增加值同比增速数据
        df_weights: 权重数据
        target_columns: 目标列列表

    Returns:
        ValidationResult: 验证结果对象
    """
    # 检查基本数据
    if df_macro.empty:
        return ValidationResult(
            is_valid=False,
            error_message="分行业工业增加值同比增速数据为空"
        )

    if df_weights.empty:
        return ValidationResult(
            is_valid=False,
            error_message="权重数据为空"
        )

    # 记录数据形状
    macro_shape = df_macro.shape
    weights_shape = df_weights.shape

    # 检查权重数据必要列
    required_weight_columns = ['指标名称', '出口依赖', '上中下游']
    weight_year_columns = ['权重_2012', '权重_2018', '权重_2020']

    missing_columns = [col for col in required_weight_columns if col not in df_weights.columns]
    if missing_columns:
        return ValidationResult(
            is_valid=False,
            error_message=f"权重数据缺少必要列: {missing_columns}",
            macro_shape=macro_shape,
            weights_shape=weights_shape
        )

    # 检查是否至少有一个权重年份列
    available_weight_columns = [col for col in weight_year_columns if col in df_weights.columns]
    if not available_weight_columns:
        return ValidationResult(
            is_valid=False,
            error_message=f"权重数据缺少权重列，需要以下任一列: {weight_year_columns}",
            macro_shape=macro_shape,
            weights_shape=weights_shape
        )

    # 检查目标列匹配情况
    available_columns = [col for col in target_columns if col in df_macro.columns]
    if not available_columns:
        return ValidationResult(
            is_valid=False,
            error_message="目标列在分行业工业增加值同比增速数据中未找到匹配项",
            macro_shape=macro_shape,
            weights_shape=weights_shape,
            available_columns_count=0
        )

    # 检查权重数据中的指标名称匹配
    weight_indicators = df_weights['指标名称'].dropna().tolist()
    matched_indicators = [ind for ind in weight_indicators if ind in available_columns]

    if not matched_indicators:
        return ValidationResult(
            is_valid=False,
            error_message="权重数据中的指标名称与分行业工业增加值同比增速数据列名无匹配项",
            macro_shape=macro_shape,
            weights_shape=weights_shape,
            available_columns_count=len(available_columns),
            available_columns=available_columns[:5]
        )

    # 验证通过
    return ValidationResult(
        is_valid=True,
        error_message="数据格式验证通过",
        matched_indicators_count=len(matched_indicators),
        matched_indicators=matched_indicators[:5],
        available_columns_count=len(available_columns),
        available_columns=available_columns[:5],
        macro_shape=macro_shape,
        weights_shape=weights_shape
    )


def display_validation_result(st_obj, result: ValidationResult, debug_mode: bool = False):
    """
    在Streamlit界面上显示验证结果

    Args:
        st_obj: Streamlit对象
        result: 验证结果
        debug_mode: 是否显示详细调试信息
    """
    if result.is_valid:
        return

    # 显示错误信息
    st_obj.error(f"加权分组计算失败: {result.error_message}")

    if debug_mode:
        # 调试模式：显示详细信息
        with st_obj.expander("详细诊断信息（调试模式）"):
            st_obj.json(result.get_summary())
    else:
        # 正常模式：只显示关键信息
        with st_obj.expander("快速诊断"):
            if result.has_matches:
                st_obj.info(f"匹配的指标数: {result.matched_indicators_count}")
                if result.matched_indicators:
                    st_obj.text(f"示例: {result.matched_indicators}")

            if result.available_columns_count > 0:
                st_obj.info(f"可用目标列数: {result.available_columns_count}")

            st_obj.markdown("**数据格式要求：**")
            st_obj.markdown("""
            - 权重数据需包含：`指标名称`、`出口依赖`、`上中下游`、权重列
            - 指标名称需与宏观数据列名完全匹配
            - 设置环境变量 `INDUSTRIAL_DEBUG_MODE=true` 查看详细诊断
            """)
