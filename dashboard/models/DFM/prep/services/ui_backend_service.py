"""数据准备页面使用的变量转换入口。"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from dashboard.models.DFM.prep.modules.variable_transformer import VariableTransformer
from dashboard.models.DFM.utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


def transform_variables(
    data: pd.DataFrame,
    transform_config: list[dict[str, Any]],
    target_freq: str = "W-FRI",
    var_frequency_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """按配置转换变量，并返回页面可直接处理的结构化结果。"""

    try:
        transformer = VariableTransformer(freq=target_freq)
        transformed_data = data.copy()
        transform_details: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        for config in transform_config:
            variable = config.get("variable", "")
            operations = config.get("operations", [])
            if not variable or variable not in transformed_data.columns:
                logger.warning("变量 '%s' 不在数据中，跳过", variable)
                errors.append(f"变量 '{variable}' 不在数据中")
                continue

            try:
                normalized = normalize_text(variable)
                original_freq = (
                    var_frequency_map.get(normalized)
                    if var_frequency_map
                    else None
                )
                transformed_data[variable] = transformer.transform_variable(
                    series=transformed_data[variable].copy(),
                    operations=operations,
                    original_freq=original_freq,
                )
                detail = transformer.get_transform_details().get(variable)
                if detail is not None:
                    transform_details[variable] = {
                        "operations": detail.get("operations", []),
                        "status": "success",
                    }
            except Exception as exc:  # noqa: BLE001 - isolate one variable
                logger.error("变换变量 '%s' 失败: %s", variable, exc)
                errors.append(f"变量 '{variable}': {exc}")

        return {
            "status": "success",
            "message": f"成功转换 {len(transform_details)} 个变量",
            "data": transformed_data,
            "transform_details": transform_details,
            "errors": errors,
        }
    except Exception as exc:  # noqa: BLE001 - public UI boundary
        logger.error("变量转换失败: %s", exc, exc_info=True)
        return {
            "status": "error",
            "message": f"处理失败: {exc}",
            "data": None,
            "transform_details": {},
            "errors": [str(exc)],
        }


__all__ = ["transform_variables"]
