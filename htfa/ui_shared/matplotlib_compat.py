"""Matplotlib compatibility helpers shared by dashboard features."""

from __future__ import annotations

import warnings
from contextlib import contextmanager


@contextmanager
def matplotlib_date_compatibility():
    """隔离 Matplotlib 与 NumPy 日期转换的第三方弃用警告。"""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"The 'generic' unit for NumPy timedelta is deprecated",
            category=DeprecationWarning,
            module=r"matplotlib\.dates",
        )
        yield


__all__ = ["matplotlib_date_compatibility"]
