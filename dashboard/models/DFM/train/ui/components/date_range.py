# -*- coding: utf-8 -*-
"""
DFM日期范围组件

提供训练期和验证期日期选择、验证和自动计算功能
"""

import streamlit as st
import pandas as pd
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import date, datetime, timedelta

from dashboard.models.DFM.ui import DFMComponent


logger = logging.getLogger(__name__)


class DateRangeComponent(DFMComponent):
    """DFM日期范围组件"""
    
    def __init__(self):
        """初始化日期范围组件"""
        super().__init__()
        self._default_training_years = 5  # 默认训练期年数
        self._default_validation_months = 6  # 默认验证期月数
    
    def get_component_id(self) -> str:
        """获取组件ID"""
        return "date_range"
    
    def get_state_keys(self) -> list:
        """
        获取组件相关的状态键
        
        Returns:
            List[str]: 状态键列表
        """
        return [
            'dfm_training_start_date',
            'dfm_validation_start_date',
            'dfm_validation_end_date'
        ]
    
    def validate_input(self, data: Dict) -> bool:
        """
        验证输入数据
        
        Args:
            data: 输入数据字典，包含training_data, data_prep_dates
            
        Returns:
            bool: 验证是否通过
        """
        try:
            # 检查训练数据
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
            
            # 检查是否有时间索引
            if not isinstance(training_data.index, pd.DatetimeIndex):
                logger.warning("训练数据没有时间索引")
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
        error_msg = f"日期范围服务错误: {str(error)}"
        logger.error(error_msg)
        st.error(error_msg)
    
    def render(self, st_obj, training_data: pd.DataFrame, 
               data_prep_dates: Dict[str, date] = None) -> Optional[Dict[str, Any]]:
        """
        渲染日期范围组件
        
        Args:
            st_obj: Streamlit对象
            training_data: 训练数据
            data_prep_dates: 数据准备页面的日期设置
            
        Returns:
            日期范围设置结果字典或None
        """
        try:
            # 验证输入
            input_data = {
                'training_data': training_data,
                'data_prep_dates': data_prep_dates or {}
            }
            
            if not self.validate_input(input_data):
                st_obj.error("[ERROR] 输入数据验证失败，请检查训练数据是否有效。")
                return None
            
            # === 与老代码第1126-1292行完全一致的日期设置逻辑 ===

            # 计算基于数据的智能默认值 - 与老代码第1131-1214行一致
            date_defaults = self._get_data_based_date_defaults(training_data, data_prep_dates)

            # 使用统一状态管理器检查是否有数据并获取数据 - 与老代码第1219-1257行一致
            self._update_date_states_from_data(training_data, date_defaults)

            # 执行日期参数一致性验证 - 与老代码第1262-1265行一致
            self._validate_date_consistency()

            # 渲染日期输入控件 - 与老代码第1267-1292行完全一致
            date_result = self._render_date_inputs(st_obj, date_defaults)

            return date_result

        except Exception as e:
            self.handle_service_error(e)
            return None

    # === 与老代码完全一致的辅助方法 ===

    def _get_data_based_date_defaults(self, training_data: pd.DataFrame,
                                           data_prep_dates: Dict[str, Any]) -> Dict[str, Any]:
        """计算基于数据的智能默认值 - 与老代码第1131-1214行一致"""
        try:
            # 从统一状态管理器获取数据准备阶段的日期
            data_start_date = self._get_state('dfm_param_data_start_date')
            data_end_date = self._get_state('dfm_param_data_end_date')

            # 如果没有从状态管理器获取到日期，尝试从参数获取
            if not data_start_date and data_prep_dates:
                data_start_date = data_prep_dates.get('start_date')
            if not data_end_date and data_prep_dates:
                data_end_date = data_prep_dates.get('end_date')

            # 如果仍然没有日期，尝试从数据中推断
            if not data_start_date or not data_end_date:
                if training_data is not None and not training_data.empty:
                    # 查找日期列
                    date_columns = [col for col in training_data.columns if 'date' in col.lower()]
                    if date_columns:
                        date_col = date_columns[0]
                        try:
                            training_data[date_col] = pd.to_datetime(training_data[date_col])
                            if not data_start_date:
                                data_start_date = training_data[date_col].min().date()
                            if not data_end_date:
                                data_end_date = training_data[date_col].max().date()
                        except Exception as e:
                            logger.warning(f"无法解析日期列 {date_col}: {e}")

            # 设置默认值
            if data_start_date and data_end_date:
                # 计算训练期和验证期的默认分割点
                total_days = (data_end_date - data_start_date).days
                training_days = int(total_days * 0.8)  # 80%用于训练

                training_start_date = data_start_date
                validation_start_date = data_start_date + timedelta(days=training_days)
                validation_end_date = data_end_date
            else:
                raise ValueError("无法获取数据日期范围，请确保训练数据包含有效的日期索引")

            return {
                'training_start_date': training_start_date,
                'validation_start_date': validation_start_date,
                'validation_end_date': validation_end_date,
                'data_start_date': data_start_date,
                'data_end_date': data_end_date
            }

        except Exception as e:
            logger.error(f"计算默认日期失败: {e}")
            raise ValueError(f"计算默认日期失败: {e}") from e

    def _update_date_states_from_data(self, training_data: pd.DataFrame,
                                           date_defaults: Dict[str, Any]):
        """使用统一状态管理器检查是否有数据并获取数据 - 与老代码第1219-1257行一致"""
        try:
            # 检查是否有训练数据
            if training_data is not None and not training_data.empty:
                # 初始化日期状态（如果尚未设置）
                if self._get_state('dfm_training_start_date') is None:
                    self._set_state('dfm_training_start_date', date_defaults['training_start_date'])

                if self._get_state('dfm_validation_start_date') is None:
                    self._set_state('dfm_validation_start_date', date_defaults['validation_start_date'])

                if self._get_state('dfm_validation_end_date') is None:
                    self._set_state('dfm_validation_end_date', date_defaults['validation_end_date'])

        except Exception as e:
            logger.error(f"更新日期状态失败: {e}")

    def _validate_date_consistency(self):
        """执行日期参数一致性验证 - 与老代码第1262-1265行一致"""
        try:
            training_start = self._get_state('dfm_training_start_date')
            validation_start = self._get_state('dfm_validation_start_date')
            validation_end = self._get_state('dfm_validation_end_date')

            # 基本验证逻辑
            if training_start and validation_start and training_start >= validation_start:
                logger.warning("训练开始日期应早于验证开始日期")

            if validation_start and validation_end and validation_start >= validation_end:
                logger.warning("验证开始日期应早于验证结束日期")

        except Exception as e:
            logger.error(f"日期一致性验证失败: {e}")

    def _render_date_inputs(self, st_obj, date_defaults: Dict[str, Any]) -> Dict[str, Any]:
        """渲染日期输入控件 - 与老代码第1267-1292行完全一致"""
        try:
            # 获取当前状态
            current_training_start = self._get_state('dfm_training_start_date', date_defaults['training_start_date'])
            current_validation_start = self._get_state('dfm_validation_start_date', date_defaults['validation_start_date'])
            current_validation_end = self._get_state('dfm_validation_end_date', date_defaults['validation_end_date'])

            # 渲染训练开始日期
            training_start_date = st_obj.date_input(
                "训练开始日期",
                value=current_training_start,
                key="new_ss_dfm_training_start_date",
                help="选择模型训练的开始日期"
            )
            self._set_state('dfm_training_start_date', training_start_date)

            # 渲染验证期日期
            validation_start_date = st_obj.date_input(
                "验证开始日期",
                value=current_validation_start,
                key="new_ss_dfm_validation_start_date",
                help="选择模型验证的开始日期"
            )
            self._set_state('dfm_validation_start_date', validation_start_date)

            validation_end_date = st_obj.date_input(
                "验证结束日期",
                value=current_validation_end,
                key="new_ss_dfm_validation_end_date",
                help="选择模型验证的结束日期"
            )
            self._set_state('dfm_validation_end_date', validation_end_date)

            return {
                'training_start_date': training_start_date,
                'validation_start_date': validation_start_date,
                'validation_end_date': validation_end_date
            }

        except Exception as e:
            logger.error(f"渲染日期输入控件失败: {e}")
            return {}

    def _auto_correct_dates(self, dates: Dict[str, date]) -> Dict[str, date]:
        """
        自动修正日期设置

        Args:
            dates: 当前日期设置

        Returns:
            修正后的日期设置
        """
        try:
            corrected = dates.copy()

            # 确保训练开始日期早于验证开始日期
            if corrected['training_start'] >= corrected['validation_start']:
                # 将验证开始日期设置为训练开始日期后6个月
                corrected['validation_start'] = corrected['training_start'] + timedelta(days=180)

            # 确保验证开始日期早于验证结束日期
            if corrected['validation_start'] >= corrected['validation_end']:
                # 将验证结束日期设置为验证开始日期后3个月
                corrected['validation_end'] = corrected['validation_start'] + timedelta(days=90)

            # 更新状态
            for key, value in corrected.items():
                self._set_state(f'dfm_{key}', value)

            logger.info(f"日期已自动修正: {corrected}")
            return corrected

        except Exception as e:
            logger.error(f"自动修正日期失败: {e}")
            return dates

    def _calculate_training_period_length(self, dates: Dict[str, date]) -> int:
        """
        计算训练期长度（天数）

        Args:
            dates: 日期设置

        Returns:
            训练期天数
        """
        try:
            return (dates['validation_start'] - dates['training_start']).days
        except Exception as e:
            logger.error(f"计算训练期长度失败: {e}")
            return 0

    def _calculate_validation_period_length(self, dates: Dict[str, date]) -> int:
        """
        计算验证期长度（天数）

        Args:
            dates: 日期设置

        Returns:
            验证期天数
        """
        try:
            return (dates['validation_end'] - dates['validation_start']).days
        except Exception as e:
            logger.error(f"计算验证期长度失败: {e}")
            return 0

    def _set_state(self, key: str, value: Any) -> None:
        """设置状态值"""
        try:
            success = self.set_state(key, value)
            if not success:
                logger.error(f"设置DFM状态失败: {key}")
        except Exception as e:
            logger.error(f"设置状态失败: {e}")
