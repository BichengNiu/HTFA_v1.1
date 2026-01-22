# -*- coding: utf-8 -*-
"""
DFM影响分解模块专用异常类

定义了模块中使用的各种异常类型，便于错误处理和调试。
"""

from typing import Optional, Any


class DecompError(Exception):
    """Decomp模块基础异常类"""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | 详情: {self.details}"
        return self.message


class ModelLoadError(DecompError):
    """模型加载异常"""

    def __init__(self, message: str, file_path: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.file_path = file_path
        self.original_error = original_error

    def __str__(self) -> str:
        parts = [self.message]
        if self.file_path:
            parts.append(f"文件路径: {self.file_path}")
        if self.original_error:
            parts.append(f"原始错误: {str(self.original_error)}")
        return " | ".join(parts)


class ValidationError(DecompError):
    """数据验证异常"""

    def __init__(self, message: str, field_name: Optional[str] = None, expected_type: Optional[str] = None, actual_value: Optional[Any] = None):
        super().__init__(message)
        self.field_name = field_name
        self.expected_type = expected_type
        self.actual_value = actual_value

    def __str__(self) -> str:
        parts = [self.message]
        if self.field_name:
            parts.append(f"字段: {self.field_name}")
        if self.expected_type:
            parts.append(f"期望类型: {self.expected_type}")
        if self.actual_value is not None:
            parts.append(f"实际值: {self.actual_value}")
        return " | ".join(parts)


class ComputationError(DecompError):
    """计算过程异常"""

    def __init__(self, message: str, computation_step: Optional[str] = None, numerical_issue: Optional[str] = None):
        super().__init__(message)
        self.computation_step = computation_step
        self.numerical_issue = numerical_issue

    def __str__(self) -> str:
        parts = [self.message]
        if self.computation_step:
            parts.append(f"计算步骤: {self.computation_step}")
        if self.numerical_issue:
            parts.append(f"数值问题: {self.numerical_issue}")
        return " | ".join(parts)


class DataFormatError(DecompError):
    """数据格式异常"""

    def __init__(self, message: str, data_shape: Optional[tuple] = None, expected_shape: Optional[tuple] = None):
        super().__init__(message)
        self.data_shape = data_shape
        self.expected_shape = expected_shape

    def __str__(self) -> str:
        parts = [self.message]
        if self.data_shape:
            parts.append(f"数据形状: {self.data_shape}")
        if self.expected_shape:
            parts.append(f"期望形状: {self.expected_shape}")
        return " | ".join(parts)


class VisualizationError(DecompError):
    """可视化生成异常"""

    def __init__(self, message: str, plot_type: Optional[str] = None, data_size: Optional[int] = None):
        super().__init__(message)
        self.plot_type = plot_type
        self.data_size = data_size

    def __str__(self) -> str:
        parts = [self.message]
        if self.plot_type:
            parts.append(f"图表类型: {self.plot_type}")
        if self.data_size:
            parts.append(f"数据大小: {self.data_size}")
        return " | ".join(parts)


class ConfigurationError(DecompError):
    """配置错误异常"""

    def __init__(self, message: str, config_key: Optional[str] = None, config_value: Optional[Any] = None):
        super().__init__(message)
        self.config_key = config_key
        self.config_value = config_value

    def __str__(self) -> str:
        parts = [self.message]
        if self.config_key:
            parts.append(f"配置项: {self.config_key}")
        if self.config_value is not None:
            parts.append(f"配置值: {self.config_value}")
        return " | ".join(parts)