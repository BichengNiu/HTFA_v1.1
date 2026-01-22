# -*- coding: utf-8 -*-
"""
数据验证组件
提供数据格式验证、质量检查等功能
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import logging

from dashboard.core.ui.components.data_input.base import DataInputComponent

logger = logging.getLogger(__name__)


class DataValidationComponent(DataInputComponent):
    """数据验证组件"""
    
    def __init__(self):
        super().__init__("validation", "数据验证")
    
    def validate_time_series_format(self, df: pd.DataFrame) -> Tuple[bool, str, Dict[str, Any]]:
        """
        验证时间序列数据格式
        
        Args:
            df: 待验证的DataFrame
            
        Returns:
            Tuple[bool, str, Dict[str, Any]]: (是否有效, 详细消息, 验证详情)
        """
        validation_details = {
            'total_rows': len(df),
            'total_cols': len(df.columns),
            'time_column': None,
            'numeric_columns': [],
            'missing_values': {},
            'data_types': {},
            'time_range': None,
            'issues': []
        }
        
        try:
            # 基本格式检查
            if df.empty:
                return False, "数据为空", validation_details
            
            if df.shape[1] < 2:
                validation_details['issues'].append("数据列数不足（至少需要时间列+1个数据列）")
                return False, "数据列数不足", validation_details
            
            # 时间列检查（假设第一列是时间列）
            time_col = df.columns[0]
            validation_details['time_column'] = time_col
            
            try:
                time_series = pd.to_datetime(df[time_col], errors='raise')
                validation_details['time_range'] = {
                    'start': str(time_series.min()),
                    'end': str(time_series.max()),
                    'frequency': self._detect_frequency(time_series)
                }
            except Exception as e:
                validation_details['issues'].append(f"时间列 '{time_col}' 格式无效: {str(e)}")
                return False, f"时间列格式无效", validation_details
            
            # 数值列检查
            numeric_cols = []
            for col in df.columns[1:]:
                if pd.api.types.is_numeric_dtype(df[col]):
                    numeric_cols.append(col)
                    validation_details['data_types'][col] = 'numeric'
                else:
                    validation_details['data_types'][col] = 'non-numeric'
                    validation_details['issues'].append(f"列 '{col}' 不是数值类型")
            
            validation_details['numeric_columns'] = numeric_cols
            
            if not numeric_cols:
                validation_details['issues'].append("没有找到有效的数值列")
                return False, "没有有效的数值列", validation_details
            
            # 缺失值检查
            for col in df.columns:
                missing_count = df[col].isnull().sum()
                missing_pct = (missing_count / len(df)) * 100
                validation_details['missing_values'][col] = {
                    'count': int(missing_count),
                    'percentage': round(missing_pct, 2)
                }
                
                if missing_pct > 50:
                    validation_details['issues'].append(f"列 '{col}' 缺失值过多 ({missing_pct:.1f}%)")
            
            # 重复时间戳检查
            if time_series.duplicated().any():
                dup_count = time_series.duplicated().sum()
                validation_details['issues'].append(f"发现 {dup_count} 个重复的时间戳")
            
            # 时间序列连续性检查
            if len(time_series) > 1:
                time_diff = time_series.diff().dropna()
                if time_diff.std() > time_diff.mean() * 0.1:  # 时间间隔变异系数 > 10%
                    validation_details['issues'].append("时间序列间隔不规律")
            
            # 生成验证结果
            if validation_details['issues']:
                status = "warning"
                message = f"数据格式基本有效，但存在 {len(validation_details['issues'])} 个问题"
            else:
                status = "success"
                message = "数据格式完全有效"
            
            return status == "success", message, validation_details
            
        except Exception as e:
            logger.error(f"数据验证失败: {e}")
            validation_details['issues'].append(f"验证过程出错: {str(e)}")
            return False, "验证过程出错", validation_details
    
    def _detect_frequency(self, time_series: pd.Series) -> str:
        """检测时间序列频率"""
        try:
            if len(time_series) < 2:
                return "unknown"
            
            # 计算时间差
            time_diff = time_series.diff().dropna()
            mode_diff = time_diff.mode()
            
            if mode_diff.empty:
                return "irregular"
            
            mode_days = mode_diff.iloc[0].days
            
            if mode_days == 1:
                return "daily"
            elif mode_days == 7:
                return "weekly"
            elif 28 <= mode_days <= 31:
                return "monthly"
            elif 90 <= mode_days <= 92:
                return "quarterly"
            elif 365 <= mode_days <= 366:
                return "yearly"
            else:
                return f"custom ({mode_days} days)"
                
        except Exception:
            return "unknown"
    
    def render_validation_report(self, st_obj, validation_details: Dict[str, Any]):
        """渲染详细的验证报告"""
        
        # 基本信息
        col1, col2 = st_obj.columns(2)
        with col1:
            st_obj.metric("总行数", validation_details['total_rows'])
            st_obj.metric("总列数", validation_details['total_cols'])
        
        with col2:
            st_obj.metric("数值列数", len(validation_details['numeric_columns']))
            if validation_details['time_range']:
                st_obj.metric("时间频率", validation_details['time_range']['frequency'])
        
        # 时间范围信息
        if validation_details['time_range']:
            st_obj.markdown("**时间范围：**")
            st_obj.write(f"从 {validation_details['time_range']['start']} 到 {validation_details['time_range']['end']}")
        
        # 数据类型信息
        if validation_details['data_types']:
            st_obj.markdown("**列类型分布：**")
            type_df = pd.DataFrame([
                {'列名': col, '类型': dtype} 
                for col, dtype in validation_details['data_types'].items()
            ])
            st_obj.dataframe(type_df, width='stretch')
        
        # 缺失值信息
        if validation_details['missing_values']:
            st_obj.markdown("**缺失值统计：**")
            missing_df = pd.DataFrame([
                {
                    '列名': col, 
                    '缺失数量': info['count'],
                    '缺失比例(%)': info['percentage']
                }
                for col, info in validation_details['missing_values'].items()
                if info['count'] > 0
            ])
            
            if not missing_df.empty:
                st_obj.dataframe(missing_df, width='stretch')
            else:
                st_obj.success("[SUCCESS] 无缺失值")
        
        # 问题列表
        if validation_details['issues']:
            st_obj.markdown("**发现的问题：**")
            for i, issue in enumerate(validation_details['issues'], 1):
                st_obj.warning(f"{i}. {issue}")
    
    def render_input_section(self, st_obj, **kwargs) -> Optional[pd.DataFrame]:
        """渲染验证输入部分"""
        
        # 获取要验证的数据
        data_to_validate = kwargs.get('data')
        
        if data_to_validate is None:
            st_obj.info("请先提供要验证的数据")
            return None
        
        # 执行验证
        is_valid, message, details = self.validate_time_series_format(data_to_validate)
        
        # 显示验证结果
        if is_valid:
            st_obj.success(f"[SUCCESS] {message}")
        else:
            st_obj.error(f"[ERROR] {message}")
        
        # 显示详细报告
        if kwargs.get('show_detailed_report', True):
            with st_obj.expander("查看详细验证报告", expanded=not is_valid):
                self.render_validation_report(st_obj, details)
        
        # 保存验证结果到状态
        self.set_state('validation_result', {
            'is_valid': is_valid,
            'message': message,
            'details': details
        })
        
        return data_to_validate if is_valid else None


__all__ = ['DataValidationComponent']
