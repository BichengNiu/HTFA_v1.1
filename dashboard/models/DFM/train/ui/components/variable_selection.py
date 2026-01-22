# -*- coding: utf-8 -*-
"""
DFM变量选择组件

提供目标变量选择、行业分组、预测指标选择等功能
"""

import streamlit as st
import pandas as pd
import unicodedata
import logging
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict

from dashboard.models.DFM.ui import DFMComponent
from dashboard.models.DFM.utils.text_utils import normalize_text


logger = logging.getLogger(__name__)


class VariableSelectionComponent(DFMComponent):
    """DFM变量选择组件"""

    def __init__(self):
        """初始化变量选择组件"""
        super().__init__()
        self._default_num_cols = 3  # 默认行业选择列数

    def get_component_id(self) -> str:
        """获取组件ID"""
        return "variable_selection"

    def get_state_keys(self) -> list:
        """
        获取组件相关的状态键

        Returns:
            List[str]: 状态键列表
        """
        return [
            'dfm_target_variable',
            'dfm_selected_industries',
            'dfm_industry_checkbox_states',
            'dfm_selected_indicators_per_industry',
            'dfm_selected_indicators',
            'dfm_variable_selection_method'
        ]

    def validate_input(self, data: Dict) -> bool:
        """
        验证输入数据

        Args:
            data: 输入数据字典，包含training_data, industry_mapping, type_mapping

        Returns:
            bool: 验证是否通过
        """
        try:
            training_data = data.get('training_data')
            if training_data is None:
                logger.warning("缺少训练数据")
                return False

            if not isinstance(training_data, pd.DataFrame):
                logger.warning("训练数据不是DataFrame格式")
                return False

            if training_data.empty:
                logger.warning("训练数据为空")
                return False

            available_vars = self._extract_available_variables(training_data)
            if len(available_vars) == 0:
                logger.warning("没有可用的变量")
                return False

            return True

        except Exception as e:
            logger.error(f"输入验证失败: {e}")
            return False

    def handle_service_error(self, error: Exception) -> None:
        """
        处理服务错误

        Args:
            error: 异常对象
        """
        error_msg = f"变量选择服务错误: {str(error)}"
        logger.error(error_msg)
        st.error(error_msg)

    def render(self, st_obj, training_data: pd.DataFrame,
               industry_mapping: Dict[str, str] = None,
               type_mapping: Dict[str, str] = None) -> Optional[Dict[str, Any]]:
        """
        渲染变量选择组件 - 与老代码UI完全一致

        Args:
            st_obj: Streamlit对象
            training_data: 训练数据
            industry_mapping: 行业映射字典
            type_mapping: 类型映射字典

        Returns:
            变量选择结果字典或None
        """
        try:
            available_target_vars = self._get_available_target_variables(training_data)
            selected_target_var = self._render_target_variable_selection(
                st_obj, available_target_vars
            )

            industry_to_vars = self._get_industry_mapping_from_state()
            all_industries = list(industry_to_vars.keys()) if industry_to_vars else []

            selected_industries_from_ui = self._render_industry_selection(
                st_obj, all_industries, industry_to_vars
            )

            dfm_default_map = self._get_state('dfm_default_variables_map', {})

            selected_indicators = self._render_indicator_selection(
                st_obj, selected_industries_from_ui, industry_to_vars, dfm_default_map
            )

            var_industry_map = self._get_state('dfm_industry_map_obj', {})

            actual_industries_set = set()
            # normalize_text 已在顶部导入
            for indicator in selected_indicators:
                indicator_norm = normalize_text(indicator)
                if indicator_norm in var_industry_map:
                    industry = var_industry_map[indicator_norm]
                    actual_industries_set.add(industry)

            selected_industries = sorted(list(actual_industries_set))

            self._render_selection_summary(st_obj, selected_target_var,
                                                selected_industries, selected_indicators)

            return {
                'target_variable': selected_target_var,
                'selected_industries': selected_industries,
                'selected_indicators': selected_indicators,
                'industry_to_vars': industry_to_vars
            }

        except Exception as e:
            self.handle_service_error(e)
            return None

    def _extract_available_variables(self, data: pd.DataFrame) -> List[str]:
        """
        提取可用变量（排除日期列和非数值列）

        Args:
            data: 训练数据

        Returns:
            可用变量列表
        """
        try:
            numeric_cols = data.select_dtypes(include=['number']).columns.tolist()

            date_keywords = ['date', 'time', 'datetime', '日期', '时间']
            available_vars = []

            for col in numeric_cols:
                col_lower = col.lower()
                is_date_col = any(keyword in col_lower for keyword in date_keywords)
                if not is_date_col:
                    available_vars.append(col)

            return available_vars

        except Exception as e:
            logger.error(f"提取可用变量失败: {e}")
            return []

    def _group_variables_by_industry(self, variables: List[str],
                                   industry_mapping: Dict[str, str]) -> Dict[str, List[str]]:
        """
        按行业分组变量

        Args:
            variables: 变量列表
            industry_mapping: 行业映射字典

        Returns:
            按行业分组的变量字典
        """
        try:
            normalized_industry_map = {}
            for k, v in industry_mapping.items():
                if pd.notna(k) and pd.notna(v):
                    normalized_key = unicodedata.normalize('NFKC', str(k)).strip().lower()
                    normalized_industry_map[normalized_key] = str(v).strip()

            industry_to_vars = defaultdict(list)
            unmapped_vars = []

            for var in variables:
                lookup_key = unicodedata.normalize('NFKC', str(var)).strip().lower()
                industry = normalized_industry_map.get(lookup_key)
                if industry:
                    industry_to_vars[industry].append(var)
                else:
                    unmapped_vars.append(var)

            if unmapped_vars:
                logger.warning(f"以下变量未找到行业映射: {unmapped_vars[:5]}{'...' if len(unmapped_vars) > 5 else ''}")

            return dict(industry_to_vars)

        except Exception as e:
            logger.error(f"按行业分组变量失败: {e}")
            raise ValueError(f"按行业分组变量失败: {e}") from e

    def _initialize_target_variable(self, available_vars: List[str]) -> str:
        """
        初始化目标变量

        Args:
            available_vars: 可用变量列表

        Returns:
            初始化的目标变量
        """
        current_target = self._get_state('dfm_target_variable')

        if current_target is None or current_target not in available_vars:
            default_target = available_vars[0] if available_vars else None
            self._set_state('dfm_target_variable', default_target)
            return default_target

        return current_target

    def _initialize_industry_selection(self, industries: List[str]) -> None:
        """
        初始化行业选择状态

        Args:
            industries: 行业列表
        """
        current_states = self._get_state('dfm_industry_checkbox_states', {})

        if not current_states and industries:
            default_states = {industry: True for industry in industries}
            self._set_state('dfm_industry_checkbox_states', default_states)

    def _get_available_target_variables(self, training_data: pd.DataFrame) -> List[str]:
        """获取可用的目标变量"""
        available_target_vars = []

        if training_data is not None:
            available_target_vars = [
                col for col in training_data.columns
                if 'date' not in col.lower() and 'time' not in col.lower()
            ]

            default_target = '规模以上工业增加值:当月同比'

            if default_target and default_target in training_data.columns and default_target not in available_target_vars:
                available_target_vars.insert(0, default_target)

            if not available_target_vars and default_target and default_target in training_data.columns:
                available_target_vars = [default_target]

            if not available_target_vars:
                if default_target:
                    available_target_vars = [default_target]
        else:
            default_target = '规模以上工业增加值:当月同比'
            if default_target:
                available_target_vars = [default_target]

        return available_target_vars

    def _get_industry_mapping_from_state(self) -> Dict[str, List[str]]:
        """从状态管理器获取行业映射"""
        try:
            var_industry_map = self._get_state('dfm_industry_map_filtered', None)
            if var_industry_map is None:
                var_industry_map = self._get_state('dfm_industry_map_obj', {})

            if not var_industry_map:
                return {}

            from collections import defaultdict
            industry_to_indicators_temp = defaultdict(list)
            for indicator, industry in var_industry_map.items():
                if indicator and industry:
                    industry_to_indicators_temp[str(industry).strip()].append(str(indicator).strip())

            industry_to_indicators_map = {k: sorted(v) for k, v in industry_to_indicators_temp.items()}
            return industry_to_indicators_map

        except Exception as e:
            logger.error(f"获取行业映射失败: {e}")
            return {}

    def _render_target_variable_selection(self, st_obj, available_target_vars: List[str]) -> str:
        """渲染目标变量选择"""
        if available_target_vars:
            if self._get_state('dfm_target_variable') is None:
                self._set_state('dfm_target_variable', available_target_vars[0])

            current_target_var = self._get_state('dfm_target_variable')

            if current_target_var not in available_target_vars:
                current_target_var = available_target_vars[0]
                self._set_state('dfm_target_variable', current_target_var)

            selected_target_var = st_obj.selectbox(
                "**选择目标变量**",
                options=available_target_vars,
                index=available_target_vars.index(current_target_var),
                key="new_ss_dfm_target_variable",
                help="选择您希望模型预测的目标序列。"
            )
            self._set_state('dfm_target_variable', selected_target_var)
            return selected_target_var
        else:
            st_obj.error("[ERROR] 无法找到任何可用的目标变量")
            self._set_state('dfm_target_variable', None)
            return None

    def _render_industry_selection(self, st_obj, unique_industries: List[str],
                                        industry_to_vars: Dict[str, List[str]]) -> List[str]:
        """渲染行业选择"""
        current_checkbox_states = self._get_state('dfm_industry_checkbox_states', None)

        needs_initialization = (
            current_checkbox_states is None or
            not current_checkbox_states or
            (unique_industries and set(current_checkbox_states.keys()) != set(unique_industries))
        )

        if needs_initialization and unique_industries:
            initial_states = {industry: True for industry in unique_industries}
            self._set_state('dfm_industry_checkbox_states', initial_states)
        elif not unique_industries:
            self._set_state('dfm_industry_checkbox_states', {})

        if not unique_industries:
            st_obj.info("没有可用的行业数据。")
            return []
        else:
            num_cols_industry = 3

            industry_cols = st_obj.columns(num_cols_industry)
            col_idx = 0
            current_checkbox_states = self._get_state('dfm_industry_checkbox_states', {})

            current_target_var = self._get_state('dfm_target_variable', None)
            filtered_industries = []

            for industry_name in unique_industries:
                industry_indicators = industry_to_vars.get(industry_name, [])
                if current_target_var and current_target_var in industry_indicators:
                    non_target_indicators = [ind for ind in industry_indicators if ind != current_target_var]
                    if non_target_indicators:
                        filtered_industries.append(industry_name)
                else:
                    filtered_industries.append(industry_name)

            for industry_name in filtered_industries:
                with industry_cols[col_idx % num_cols_industry]:
                    current_value = current_checkbox_states.get(industry_name, True)

                    new_state = st_obj.checkbox(
                        industry_name,
                        value=current_value,
                        key=f"dfm_industry_checkbox_{industry_name}"
                    )
                    current_checkbox_states[industry_name] = new_state
                col_idx += 1

            self._set_state('dfm_industry_checkbox_states', current_checkbox_states)

            col_deselect, col_select, col_reset = st_obj.columns(3)
            with col_deselect:
                if st_obj.button("取消全行业",
                                key='btn_dfm_deselect_all_industries',
                                help="点击取消所有已选中的行业",
                                width='stretch'):
                    old_states = self._get_state('dfm_industry_checkbox_states', {})
                    new_states = {industry: False for industry in filtered_industries}

                    self._set_state('dfm_industry_checkbox_states', new_states)

                    logger.info(f"取消全行业按钮点击 - 旧状态: {sum(old_states.values())} 个行业已选")
                    logger.info(f"取消全行业按钮点击 - 新状态: 0 个行业已选")
                    logger.info(f"行业复选框状态已更新: {len(filtered_industries)} 个行业全部设为 False")
                    logger.info(f"过滤后的行业列表: {filtered_industries}")
                    logger.info(f"industry_to_vars内容: {list(industry_to_vars.keys())}")

                    st_obj.rerun()

            with col_select:
                if st_obj.button("选择全行业",
                                key='btn_dfm_select_all_industries',
                                help="点击选择所有行业",
                                width='stretch'):
                    old_states = self._get_state('dfm_industry_checkbox_states', {})
                    new_states = {industry: True for industry in filtered_industries}

                    self._set_state('dfm_industry_checkbox_states', new_states)

                    logger.info(f"选择全行业按钮点击 - 旧状态: {sum(old_states.values())} 个行业已选")
                    logger.info(f"选择全行业按钮点击 - 新状态: {len(filtered_industries)} 个行业已选")
                    logger.info(f"行业复选框状态已更新: {len(filtered_industries)} 个行业全部设为 True")

                    st_obj.rerun()

            with col_reset:
                if st_obj.button("[LOADING] 重置",
                                key='btn_dfm_reset_industries',
                                help="重置为默认状态（全选）",
                                width='stretch'):
                    old_states = self._get_state('dfm_industry_checkbox_states', {})
                    reset_states = {industry: True for industry in filtered_industries}

                    self._set_state('dfm_industry_checkbox_states', reset_states)

                    logger.info(f"重置行业按钮点击 - 旧状态: {sum(old_states.values())} 个行业已选")
                    logger.info(f"重置行业按钮点击 - 新状态: {len(filtered_industries)} 个行业已选")
                    logger.info(f"行业复选框状态已重置: {len(filtered_industries)} 个行业全部设为 True")

                    st_obj.rerun()

            selected_count = sum(1 for industry, checked in current_checkbox_states.items() if checked and industry in filtered_industries)
            st_obj.info(f"[DATA] 当前状态：已选择 {selected_count} 个行业（共 {len(filtered_industries)} 个可选）")

            if len(filtered_industries) < len(unique_industries):
                excluded_count = len(unique_industries) - len(filtered_industries)
                st_obj.text(f"已自动排除 {excluded_count} 个仅包含目标变量的行业")

        current_checkbox_states = self._get_state('dfm_industry_checkbox_states', {})

        current_target_var = self._get_state('dfm_target_variable', None)
        filtered_industries_for_state = []
        for industry_name in unique_industries:
            industry_indicators = industry_to_vars.get(industry_name, [])
            if current_target_var and current_target_var in industry_indicators:
                non_target_indicators = [ind for ind in industry_indicators if ind != current_target_var]
                if non_target_indicators:
                    filtered_industries_for_state.append(industry_name)
            else:
                filtered_industries_for_state.append(industry_name)

        if not current_checkbox_states and filtered_industries_for_state:
            current_checkbox_states = {industry: True for industry in filtered_industries_for_state}
            self._set_state('dfm_industry_checkbox_states', current_checkbox_states)

        selected_industries = [
            industry for industry, checked in current_checkbox_states.items() if checked
        ]

        self._set_state('dfm_selected_industries', selected_industries)
        return selected_industries

    def _render_indicator_selection(self, st_obj, selected_industries: List[str],
                                         industry_to_vars: Dict[str, List[str]],
                                         dfm_default_map: Dict[str, str] = None) -> List[str]:
        """渲染预测指标选择"""
        if dfm_default_map is None:
            dfm_default_map = {}
        st_obj.markdown("**选择预测指标**")

        if self._get_state('dfm_selected_indicators_per_industry', None) is None:
            self._set_state('dfm_selected_indicators_per_industry', {})

        final_selected_indicators_flat = []
        current_selected_industries = self._get_state('dfm_selected_industries', [])

        if not current_selected_industries:
            st_obj.info("请先在上方选择至少一个行业。")
        else:
            num_cols_indicator = 4
            indicator_cols = st_obj.columns(num_cols_indicator)
            col_idx = 0

            for industry_name in current_selected_industries:
                all_indicators_for_industry = industry_to_vars.get(industry_name, [])

                current_target_var = self._get_state('dfm_target_variable', None)
                if current_target_var:
                    indicators_for_this_industry = [
                        indicator for indicator in all_indicators_for_industry
                        if indicator != current_target_var
                    ]
                else:
                    indicators_for_this_industry = all_indicators_for_industry

                if not indicators_for_this_industry:
                    current_selection = self._get_state('dfm_selected_indicators_per_industry', {})
                    current_selection[industry_name] = []
                    self._set_state('dfm_selected_indicators_per_industry', current_selection)
                    col_idx += 1
                    continue

                with indicator_cols[col_idx % num_cols_indicator]:
                    st_obj.markdown(f"**{industry_name}**")

                    excluded_count = len(all_indicators_for_industry) - len(indicators_for_this_industry)
                    if excluded_count > 0:
                        st_obj.caption(f"排除目标变量: {excluded_count}个")

                    current_selection = self._get_state('dfm_selected_indicators_per_industry', {})
                    default_selection_for_industry = current_selection.get(industry_name, None)

                    if default_selection_for_industry is None:
                        if dfm_default_map:
                            dfm_selected_indicators = [
                                indicator for indicator in indicators_for_this_industry
                                if normalize_text(indicator) in dfm_default_map
                            ]
                            default_selection_for_industry = dfm_selected_indicators
                        else:
                            default_selection_for_industry = []

                    valid_default = [item for item in default_selection_for_industry if item in indicators_for_this_industry]

                    deselect_all_checked = st_obj.checkbox(
                        "取消全选",
                        key=f"dfm_deselect_all_{industry_name}",
                        help=f"取消所有 '{industry_name}' 的指标"
                    )

                    if deselect_all_checked:
                        valid_default = []

                    selected_in_widget = st_obj.multiselect(
                        "选择指标",
                        options=indicators_for_this_industry,
                        default=valid_default,
                        help=f"从 {industry_name} 中选择指标",
                        key=f"dfm_indicator_multiselect_{industry_name}"
                    )

                    current_selection = self._get_state('dfm_selected_indicators_per_industry', {})
                    current_selection[industry_name] = selected_in_widget
                    self._set_state('dfm_selected_indicators_per_industry', current_selection)

                    final_selected_indicators_flat.extend(selected_in_widget)

                col_idx += 1

            current_selection = self._get_state('dfm_selected_indicators_per_industry', {})
            industries_to_remove_from_state = [
                ind for ind in current_selection
                if ind not in current_selected_industries
            ]
            for ind_to_remove in industries_to_remove_from_state:
                del current_selection[ind_to_remove]
            self._set_state('dfm_selected_indicators_per_industry', current_selection)

        final_indicators = sorted(list(set(final_selected_indicators_flat)))
        self._set_state('dfm_selected_indicators', final_indicators)
        return final_indicators

    def _render_selection_summary(self, st_obj, selected_target_var: str,
                                       selected_industries: List[str], selected_indicators: List[str]):
        """渲染选择摘要"""
        st_obj.markdown("---")
        current_target_var = self._get_state('dfm_target_variable', None)
        current_selected_indicators = self._get_state('dfm_selected_indicators', [])
        st_obj.text(f" - 目标变量: {current_target_var if current_target_var else '未选择'}")
        st_obj.text(f" - 选定行业数: {len(selected_industries)}")
        st_obj.text(f" - 选定预测指标总数: {len(current_selected_indicators)}")

    def _update_selection_states(self, selected_industries: List[str],
                               selected_indicators: List[str]) -> None:
        """
        更新选择状态

        Args:
            selected_industries: 选择的行业列表
            selected_indicators: 选择的指标列表
        """
        try:
            self._set_state('dfm_selected_industries', selected_industries)

            self._set_state('dfm_selected_indicators', selected_indicators)

        except Exception as e:
            logger.error(f"更新选择状态失败: {e}")

    def _clean_unused_industry_states(self, current_industries: List[str]) -> None:
        """
        清理不再被选中的行业状态

        Args:
            current_industries: 当前选择的行业列表
        """
        try:
            current_selection = self._get_state('dfm_selected_indicators_per_industry', {})

            industries_to_remove = [
                industry for industry in current_selection
                if industry not in current_industries
            ]

            for industry_to_remove in industries_to_remove:
                del current_selection[industry_to_remove]

            self._set_state('dfm_selected_indicators_per_industry', current_selection)

        except Exception as e:
            logger.error(f"清理未使用的行业状态失败: {e}")

    def _get_state(self, key: str, default: Any = None) -> Any:
        """获取状态值"""
        try:
            value = self.get_state(key, default)
            logger.debug(f"获取DFM状态成功: {key} = {type(value).__name__}")
            return value
        except Exception as e:
            logger.error(f"获取状态失败: {key} - {str(e)}")
            return default

    def _set_state(self, key: str, value: Any) -> bool:
        """设置状态值"""
        try:
            success = self.set_state(key, value)
            if success:
                logger.debug(f"设置DFM状态成功: {key}")
                return True
            else:
                logger.error(f"设置DFM状态失败: {key}")
                return False
        except Exception as e:
            logger.error(f"设置状态失败: {key} - {str(e)}")
            return False
