# -*- coding: utf-8 -*-
"""
值替换器模块

提供数据值替换功能，支持按月份、周次、日期范围、条件等多种规则进行值替换。
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union, Literal, Any
from datetime import date
import pandas as pd
import numpy as np


@dataclass
class ReplacementRule:
    """替换规则数据类"""
    variable: str  # 目标变量名（空字符串表示应用于任意变量）
    rule_type: Literal['months', 'weeks_yearly', 'weeks_monthly', 'date_range', 'condition']

    # 按月份筛选
    months: Optional[List[int]] = None  # [1, 2, 12] 表示1月、2月、12月

    # 按周次筛选
    weeks: Optional[List[int]] = None  # 周次列表
    # weeks_yearly: [1,2,3,4] 表示每年第1-4周
    # weeks_monthly: [1,5] 表示每月第1周和最后一周

    # 按日期范围
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # 按条件表达式
    condition_type: Optional[Literal['eq', 'gt', 'lt', 'gte', 'lte', 'between', 'isnull']] = None
    condition_value: Optional[float] = None
    condition_value2: Optional[float] = None  # 用于 between

    # 替换目标
    replace_with: Union[float, Literal['nan']] = 'nan'

    # 规则元数据（用于保存/复用）
    rule_name: Optional[str] = None  # 规则名称
    rule_description: Optional[str] = None  # 规则描述
    created_at: Optional[str] = None  # 创建时间
    last_used: Optional[str] = None  # 最后使用时间

    def to_dict(self) -> dict:
        """转换为可序列化的字典"""
        d = asdict(self)
        # 处理date类型
        if self.start_date:
            d['start_date'] = self.start_date.isoformat()
        if self.end_date:
            d['end_date'] = self.end_date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'ReplacementRule':
        """从字典创建规则"""
        d = d.copy()  # 避免修改原字典
        if d.get('start_date') and isinstance(d['start_date'], str):
            d['start_date'] = date.fromisoformat(d['start_date'])
        if d.get('end_date') and isinstance(d['end_date'], str):
            d['end_date'] = date.fromisoformat(d['end_date'])
        # 过滤掉不属于dataclass字段的键
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_d = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered_d)


@dataclass
class ReplacementResult:
    """替换结果数据类"""
    variable: str
    rule_description: str  # 人类可读的规则描述
    affected_count: int  # 影响的行数
    affected_indices: List  # 受影响的索引列表
    original_values: List  # 原始值（用于撤销）
    new_value: Union[float, str]  # 替换后的值


class ValueReplacer:
    """值替换器"""

    def __init__(self, data: pd.DataFrame):
        """
        初始化值替换器

        Args:
            data: 要处理的DataFrame，索引应为DatetimeIndex
        """
        self.data = data

    def build_mask(self, rule: ReplacementRule) -> pd.Series:
        """
        根据规则构建布尔掩码

        Args:
            rule: 替换规则

        Returns:
            布尔Series，True表示该行需要被替换
        """
        if rule.variable not in self.data.columns:
            raise ValueError(f"变量 '{rule.variable}' 不存在")

        mask = pd.Series(False, index=self.data.index)

        if rule.rule_type == 'months':
            # 按月份筛选
            if not isinstance(self.data.index, pd.DatetimeIndex):
                raise ValueError("数据索引必须是DatetimeIndex才能按月份筛选")
            if rule.months:
                mask = self.data.index.month.isin(rule.months)

        elif rule.rule_type == 'weeks_yearly':
            # 按每年第N周筛选（ISO周数）
            if not isinstance(self.data.index, pd.DatetimeIndex):
                raise ValueError("数据索引必须是DatetimeIndex才能按周次筛选")
            if rule.weeks:
                iso_weeks = self.data.index.isocalendar().week
                mask = pd.Series(iso_weeks.isin(rule.weeks).values, index=self.data.index)

        elif rule.rule_type == 'weeks_monthly':
            # 按每月第N周筛选
            if not isinstance(self.data.index, pd.DatetimeIndex):
                raise ValueError("数据索引必须是DatetimeIndex才能按周次筛选")
            if rule.weeks:
                # 计算每个日期是当月的第几周（基于日期，1-7日为���1周，8-14日为第2周...）
                week_of_month = ((self.data.index.day - 1) // 7) + 1
                mask = pd.Series(week_of_month.isin(rule.weeks), index=self.data.index)

        elif rule.rule_type == 'date_range':
            # 按日期范围
            if not isinstance(self.data.index, pd.DatetimeIndex):
                raise ValueError("数据索引必须是DatetimeIndex才能按日期范围筛选")
            start_ts = pd.Timestamp(rule.start_date) if rule.start_date else self.data.index.min()
            end_ts = pd.Timestamp(rule.end_date) if rule.end_date else self.data.index.max()
            mask = (self.data.index >= start_ts) & (self.data.index <= end_ts)

        elif rule.rule_type == 'condition':
            # 按条件表达式
            col = self.data[rule.variable]
            if rule.condition_type == 'eq':
                mask = col == rule.condition_value
            elif rule.condition_type == 'gt':
                mask = col > rule.condition_value
            elif rule.condition_type == 'lt':
                mask = col < rule.condition_value
            elif rule.condition_type == 'gte':
                mask = col >= rule.condition_value
            elif rule.condition_type == 'lte':
                mask = col <= rule.condition_value
            elif rule.condition_type == 'between':
                mask = (col >= rule.condition_value) & (col <= rule.condition_value2)
            elif rule.condition_type == 'isnull':
                mask = col.isnull()

        return mask

    def preview(self, rule: ReplacementRule) -> ReplacementResult:
        """
        预览替换效果，不实际修改数据

        Args:
            rule: 替换规则

        Returns:
            ReplacementResult对象，包含受影响的行信息
        """
        mask = self.build_mask(rule)
        affected_indices = self.data.index[mask].tolist()
        original_values = self.data.loc[mask, rule.variable].tolist()

        return ReplacementResult(
            variable=rule.variable,
            rule_description=self._format_rule_description(rule),
            affected_count=len(affected_indices),
            affected_indices=affected_indices,
            original_values=original_values,
            new_value='NaN' if rule.replace_with == 'nan' else rule.replace_with
        )

    def apply(self, rule: ReplacementRule) -> ReplacementResult:
        """
        执行替换操作

        Args:
            rule: 替换规则

        Returns:
            ReplacementResult对象，包含替换结果信息（可用于撤销）
        """
        # 先预览获取原始值
        result = self.preview(rule)

        # 执行替换
        mask = self.build_mask(rule)
        if rule.replace_with == 'nan':
            self.data.loc[mask, rule.variable] = np.nan
        else:
            self.data.loc[mask, rule.variable] = rule.replace_with

        return result

    def undo(self, result: ReplacementResult) -> None:
        """
        撤销替换操作

        Args:
            result: 之前apply返回的ReplacementResult对象
        """
        for idx, orig_val in zip(result.affected_indices, result.original_values):
            self.data.loc[idx, result.variable] = orig_val

    def _format_rule_description(self, rule: ReplacementRule) -> str:
        """
        生成人类可读的规则描述

        Args:
            rule: 替换规则

        Returns:
            规则的中文描述
        """
        if rule.rule_type == 'months':
            if rule.months:
                months_str = '、'.join([f"{m}月" for m in sorted(rule.months)])
                return f"每年{months_str}"
            return "未选择月份"

        elif rule.rule_type == 'weeks_yearly':
            if rule.weeks:
                if len(rule.weeks) <= 3:
                    weeks_str = '、'.join([f"第{w}周" for w in sorted(rule.weeks)])
                else:
                    min_w, max_w = min(rule.weeks), max(rule.weeks)
                    weeks_str = f"第{min_w}-{max_w}周"
                return f"每年{weeks_str}"
            return "未选择周次"

        elif rule.rule_type == 'weeks_monthly':
            if rule.weeks:
                weeks_str = '、'.join([f"第{w}周" for w in sorted(rule.weeks)])
                return f"每月{weeks_str}"
            return "未选择周次"

        elif rule.rule_type == 'date_range':
            start_str = rule.start_date.isoformat() if rule.start_date else "起始"
            end_str = rule.end_date.isoformat() if rule.end_date else "结束"
            return f"{start_str} 至 {end_str}"

        elif rule.rule_type == 'condition':
            type_map = {
                'eq': '等于',
                'gt': '大于',
                'lt': '小于',
                'gte': '大于等于',
                'lte': '小于等于',
                'between': '介于',
                'isnull': '为空'
            }
            if rule.condition_type == 'between':
                return f"{type_map[rule.condition_type]} {rule.condition_value} 和 {rule.condition_value2}"
            elif rule.condition_type == 'isnull':
                return type_map[rule.condition_type]
            else:
                return f"{type_map.get(rule.condition_type, '未知')} {rule.condition_value}"

        return "未知规则"
