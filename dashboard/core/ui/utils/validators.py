# -*- coding: utf-8 -*-
"""
UI验证工具
提供UI组件的验证功能
"""

import pandas as pd
from typing import Any, List, Dict, Optional, Tuple
import re

class UIValidator:
    """UI验证器"""
    
    @staticmethod
    def validate_file_upload(uploaded_file) -> Tuple[bool, str]:
        """
        验证上传的文件
        
        Returns:
            (is_valid, error_message)
        """
        if uploaded_file is None:
            return False, "请选择要上传的文件"
        
        # 检查文件大小 (最大50MB)
        file_size = len(uploaded_file.getvalue()) / 1024 / 1024
        if file_size > 50:
            return False, f"文件过大 ({file_size:.1f}MB)，请选择小于50MB的文件"
        
        # 检查文件类型
        allowed_extensions = ['.xlsx', '.xls', '.csv']
        file_extension = '.' + uploaded_file.name.split('.')[-1].lower()
        
        if file_extension not in allowed_extensions:
            return False, f"不支持的文件格式 ({file_extension})，请上传Excel或CSV文件"
        
        return True, ""
    
    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> Tuple[bool, str]:
        """
        验证DataFrame的格式
        
        Returns:
            (is_valid, error_message)
        """
        if df is None or df.empty:
            return False, "数据为空"
        
        # 检查最小行数
        if len(df) < 3:
            return False, f"数据行数过少 ({len(df)}行)，建议至少3行数据"
        
        # 检查是否有时间列
        time_columns = []
        for col in df.columns:
            if any(keyword in col.lower() for keyword in ['时间', 'time', '日期', 'date']):
                time_columns.append(col)
        
        if not time_columns:
            # 检查第一列是否可能是时间
            first_col = df.iloc[:, 0]
            try:
                pd.to_datetime(first_col.head())
                time_columns.append(df.columns[0])
            except (ValueError, TypeError):
                # 第一列不是时间格式
                pass
        
        if not time_columns:
            return False, "未找到时间列，请确保数据包含时间信息（建议第一列为时间）"
        
        # 检查数值列
        numeric_columns = df.select_dtypes(include=['number']).columns.tolist()
        if len(numeric_columns) < 1:
            return False, "未找到数值列，请确保数据包含数值型变量"
        
        return True, ""
    
    @staticmethod
    def validate_parameter(param_name: str, param_value: Any, 
                          param_type: str, constraints: Dict[str, Any] = None) -> Tuple[bool, str]:
        """
        验证参数值
        
        Args:
            param_name: 参数名称
            param_value: 参数值
            param_type: 参数类型 ('int', 'float', 'str', 'bool')
            constraints: 约束条件字典
            
        Returns:
            (is_valid, error_message)
        """
        constraints = constraints or {}
        
        # 类型验证
        if param_type == 'int':
            try:
                value = int(param_value)
            except (ValueError, TypeError):
                return False, f"{param_name}必须是整数"
        elif param_type == 'float':
            try:
                value = float(param_value)
            except (ValueError, TypeError):
                return False, f"{param_name}必须是数字"
        elif param_type == 'str':
            if not isinstance(param_value, str):
                return False, f"{param_name}必须是字符串"
            value = param_value
        elif param_type == 'bool':
            if not isinstance(param_value, bool):
                return False, f"{param_name}必须是布尔值"
            value = param_value
        else:
            value = param_value
        
        # 约束验证
        if 'min' in constraints and value < constraints['min']:
            return False, f"{param_name}不能小于{constraints['min']}"
        
        if 'max' in constraints and value > constraints['max']:
            return False, f"{param_name}不能大于{constraints['max']}"
        
        if 'choices' in constraints and value not in constraints['choices']:
            return False, f"{param_name}必须是以下值之一: {constraints['choices']}"
        
        if 'pattern' in constraints and param_type == 'str':
            if not re.match(constraints['pattern'], value):
                return False, f"{param_name}格式不正确"
        
        return True, ""
    
    @staticmethod
    def validate_column_selection(df: pd.DataFrame, selected_columns: List[str]) -> Tuple[bool, str]:
        """
        验证列选择
        
        Returns:
            (is_valid, error_message)
        """
        if not selected_columns:
            return False, "请至少选择一列"
        
        # 检查列是否存在
        missing_columns = [col for col in selected_columns if col not in df.columns]
        if missing_columns:
            return False, f"以下列不存在: {missing_columns}"
        
        # 检查是否为数值列
        non_numeric_columns = []
        for col in selected_columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                non_numeric_columns.append(col)
        
        if non_numeric_columns:
            return False, f"以下列不是数值类型: {non_numeric_columns}"
        
        return True, ""
    
    @staticmethod
    def validate_analysis_parameters(analysis_type: str, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证分析参数
        
        Args:
            analysis_type: 分析类型 ('stationarity', 'correlation', 'lead_lag')
            parameters: 参数字典
            
        Returns:
            (is_valid, error_message)
        """
        if analysis_type == 'stationarity':
            # 平稳性分析参数验证
            if 'significance_level' in parameters:
                alpha = parameters['significance_level']
                if not (0 < alpha < 1):
                    return False, "显著性水平必须在0和1之间"
        
        elif analysis_type == 'correlation':
            # 相关性分析参数验证
            if 'max_lags' in parameters:
                max_lags = parameters['max_lags']
                if max_lags < 1:
                    return False, "最大滞后期必须大于0"
                if max_lags > 50:
                    return False, "最大滞后期不建议超过50"
        
        elif analysis_type == 'lead_lag':
            # 领先滞后分析参数验证
            if 'max_lags' in parameters:
                max_lags = parameters['max_lags']
                if max_lags < 1:
                    return False, "最大滞后期必须大于0"
            
            if 'test_type' in parameters:
                valid_tests = ['granger', 'ccf', 'both']
                if parameters['test_type'] not in valid_tests:
                    return False, f"检验类型必须是: {valid_tests}"
        
        return True, ""
    
    @staticmethod
    def get_data_quality_report(df: pd.DataFrame) -> Dict[str, Any]:
        """
        生成数据质量报告
        
        Returns:
            数据质量报告字典
        """
        report = {
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'missing_values': {},
            'data_types': {},
            'numeric_columns': [],
            'categorical_columns': [],
            'datetime_columns': []
        }
        
        # 缺失值统计
        for col in df.columns:
            missing_count = df[col].isnull().sum()
            missing_pct = (missing_count / len(df)) * 100
            report['missing_values'][col] = {
                'count': missing_count,
                'percentage': missing_pct
            }
        
        # 数据类型分析
        for col in df.columns:
            dtype = str(df[col].dtype)
            report['data_types'][col] = dtype
            
            if pd.api.types.is_numeric_dtype(df[col]):
                report['numeric_columns'].append(col)
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                report['datetime_columns'].append(col)
            else:
                report['categorical_columns'].append(col)
        
        return report
