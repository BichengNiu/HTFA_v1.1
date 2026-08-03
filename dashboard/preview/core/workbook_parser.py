"""统一的经济数据库工作簿解析器。

正式协议：
- `指标字典` sheet 保存指标分类信息；
- 指标字典是唯一白名单，数据sheet中的未登记指标会被忽略；
- 指标原始数值中的0统一按缺失值处理，不进行插值；
- 其他非空 sheet 的第2至第6行依次保存指标名称、频率、单位、来源、更新时间；
- 第7行开始为日期和指标值。
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import re
from typing import Any, Callable, Dict, Optional

import pandas as pd

from dashboard.preview.domain.models import IndicatorMetadata, LoadedPreviewData


DICTIONARY_SHEET_NAME = "指标字典"
DICTIONARY_COLUMNS = ["指标名称", "类型", "行业", "数据来源", "预测变量"]
METADATA_ROW_LABELS = {
    2: "指标名称",
    3: "频率",
    4: "单位",
    5: "来源",
    6: "更新时间",
}
FREQUENCY_MAP = {
    "日": "daily",
    "日度": "daily",
    "周": "weekly",
    "周度": "weekly",
    "旬": "ten_day",
    "旬度": "ten_day",
    "月": "monthly",
    "月度": "monthly",
    "季": "quarterly",
    "季度": "quarterly",
    "年": "yearly",
    "年度": "yearly",
}
FREQUENCIES = ("daily", "weekly", "ten_day", "monthly", "quarterly", "yearly")

FrequencyProcessor = Callable[[pd.DataFrame, str, str], pd.DataFrame]


def normalize_indicator_name(value: Any) -> Any:
    """统一指标名称中的全角标点、冒号和空白。"""
    if not isinstance(value, str):
        return value
    translation = str.maketrans("（）：　", "(): ")
    normalized = value.translate(translation)
    normalized = re.sub(r":(?!\s)", ": ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _optional_text(value: Any) -> Optional[str]:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any, *, context: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{context}不能为空")
    return text


def _format_updated_at(value: Any) -> str:
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    return _required_text(value, context="更新时间")


def _read_file(file_input: Any) -> tuple[BytesIO, str]:
    if isinstance(file_input, (str, Path)):
        path = Path(file_input)
        return BytesIO(path.read_bytes()), path.name

    if hasattr(file_input, "getvalue"):
        data = file_input.getvalue()
    elif hasattr(file_input, "read"):
        data = file_input.read()
    else:
        raise TypeError("工作簿输入必须是路径或可读取的二进制文件对象")

    file_name = getattr(file_input, "name", "经济数据库.xlsx")
    return BytesIO(data), Path(str(file_name)).name


def _load_dictionary(excel_file: pd.ExcelFile) -> Dict[str, Dict[str, Any]]:
    if DICTIONARY_SHEET_NAME not in excel_file.sheet_names:
        raise ValueError(f"工作簿必须包含名为“{DICTIONARY_SHEET_NAME}”的首个sheet")
    if excel_file.sheet_names[0] != DICTIONARY_SHEET_NAME:
        raise ValueError(f"“{DICTIONARY_SHEET_NAME}”必须是工作簿的首个sheet")

    dictionary = pd.read_excel(excel_file, sheet_name=DICTIONARY_SHEET_NAME)
    missing_columns = [column for column in DICTIONARY_COLUMNS if column not in dictionary.columns]
    if missing_columns:
        raise ValueError(f"指标字典缺少字段: {', '.join(missing_columns)}")

    records: Dict[str, Dict[str, Any]] = {}
    for row_number, row in dictionary.iterrows():
        name = normalize_indicator_name(row["指标名称"])
        if not _optional_text(name):
            raise ValueError(f"指标字典第{row_number + 2}行的指标名称为空")
        if name in records:
            raise ValueError(f"指标字典包含重复指标: {name}")
        records[name] = {
            "indicator_type": _optional_text(row["类型"]),
            "industry": _optional_text(row["行业"]),
            "dictionary_source": _optional_text(row["数据来源"]),
            "forecast_variable": _optional_text(row["预测变量"]),
        }

    if not records:
        raise ValueError("指标字典中没有任何指标")
    return records


def _validate_metadata_labels(raw: pd.DataFrame, sheet_name: str) -> None:
    for row_number, expected_label in METADATA_ROW_LABELS.items():
        actual_label = _optional_text(raw.iloc[row_number - 1, 0])
        if actual_label != expected_label:
            raise ValueError(
                f"sheet“{sheet_name}”第{row_number}行首列必须为“{expected_label}”，"
                f"实际为“{actual_label or '空'}”"
            )


def _parse_data_sheet(
    raw: pd.DataFrame,
    *,
    file_name: str,
    sheet_name: str,
    dictionary: Dict[str, Dict[str, Any]],
    seen_indicators: set[str],
    frequency_processor: Optional[FrequencyProcessor],
) -> tuple[Dict[str, list[pd.DataFrame]], Dict[str, IndicatorMetadata]]:
    _validate_metadata_labels(raw, sheet_name)

    indicator_columns = []
    for column_index in range(1, raw.shape[1]):
        name = normalize_indicator_name(raw.iloc[1, column_index])
        if _optional_text(name):
            indicator_columns.append((column_index, name))

    if not indicator_columns:
        raise ValueError(f"sheet“{sheet_name}”第2行没有指标名称")

    frames = {frequency: [] for frequency in FREQUENCIES}
    metadata_map: Dict[str, IndicatorMetadata] = {}
    indicator_columns = [
        (column_index, indicator_name)
        for column_index, indicator_name in indicator_columns
        if indicator_name in dictionary
    ]
    if not indicator_columns:
        return frames, metadata_map

    data_block = raw.iloc[6:, :].dropna(how="all")
    if data_block.empty:
        raise ValueError(f"sheet“{sheet_name}”第7行起没有数据")

    raw_dates = data_block.iloc[:, 0]
    parsed_dates = pd.to_datetime(raw_dates, errors="coerce")
    invalid_dates = parsed_dates.isna()
    if invalid_dates.any():
        first_bad_row = int(invalid_dates[invalid_dates].index[0]) + 1
        raise ValueError(f"sheet“{sheet_name}”第{first_bad_row}行日期无效")
    if parsed_dates.duplicated().any():
        raise ValueError(f"sheet“{sheet_name}”包含重复日期")

    for column_index, indicator_name in indicator_columns:
        if indicator_name in seen_indicators:
            raise ValueError(f"指标在多个sheet中重复出现: {indicator_name}")

        frequency_label = _required_text(
            raw.iloc[2, column_index],
            context=f"sheet“{sheet_name}”指标“{indicator_name}”的频率",
        )
        frequency = FREQUENCY_MAP.get(frequency_label)
        if frequency is None:
            raise ValueError(
                f"sheet“{sheet_name}”指标“{indicator_name}”使用了不支持的频率: {frequency_label}"
            )

        unit = _required_text(
            raw.iloc[3, column_index],
            context=f"sheet“{sheet_name}”指标“{indicator_name}”的单位",
        )
        sheet_source = _required_text(
            raw.iloc[4, column_index],
            context=f"sheet“{sheet_name}”指标“{indicator_name}”的来源",
        )
        updated_at = _format_updated_at(raw.iloc[5, column_index])

        raw_values = data_block.iloc[:, column_index]
        numeric_values = pd.to_numeric(raw_values, errors="coerce")
        invalid_values = raw_values.notna() & raw_values.astype(str).str.strip().ne("") & numeric_values.isna()
        if invalid_values.any():
            first_bad_row = int(invalid_values[invalid_values].index[0]) + 1
            raise ValueError(
                f"sheet“{sheet_name}”指标“{indicator_name}”第{first_bad_row}行不是数值"
            )
        numeric_values = numeric_values.mask(numeric_values.eq(0))

        frame = pd.DataFrame(
            {indicator_name: numeric_values.to_numpy()},
            index=pd.DatetimeIndex(parsed_dates),
        ).sort_index()
        if frequency_processor is not None:
            frame = frequency_processor(frame, frequency, indicator_name)
        frames[frequency].append(frame)

        dictionary_metadata = dictionary[indicator_name]
        metadata_map[indicator_name] = IndicatorMetadata(
            indicator_name=indicator_name,
            frequency=frequency,
            unit=unit,
            sheet_source=sheet_source,
            updated_at=updated_at,
            indicator_type=dictionary_metadata["indicator_type"],
            industry=dictionary_metadata["industry"],
            dictionary_source=dictionary_metadata["dictionary_source"],
            forecast_variable=dictionary_metadata["forecast_variable"],
            file_name=file_name,
            sheet_name=sheet_name,
        )
        seen_indicators.add(indicator_name)

    return frames, metadata_map


def parse_preview_workbook(
    file_input: Any,
    *,
    module_name: str,
    frequency_processor: Optional[FrequencyProcessor] = None,
) -> LoadedPreviewData:
    """按正式协议解析单个经济数据库工作簿。"""
    file_buffer, file_name = _read_file(file_input)
    excel_file = pd.ExcelFile(file_buffer)

    try:
        dictionary = _load_dictionary(excel_file)
        all_frames = {frequency: [] for frequency in FREQUENCIES}
        metadata_map: Dict[str, IndicatorMetadata] = {}
        seen_indicators: set[str] = set()

        for sheet_name in excel_file.sheet_names[1:]:
            raw = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            if raw.dropna(how="all").empty:
                continue
            if raw.shape[0] < 7 or raw.shape[1] < 2:
                raise ValueError(f"sheet“{sheet_name}”不为空，但不符合第2至第6行元数据协议")

            sheet_frames, sheet_metadata = _parse_data_sheet(
                raw,
                file_name=file_name,
                sheet_name=sheet_name,
                dictionary=dictionary,
                seen_indicators=seen_indicators,
                frequency_processor=frequency_processor,
            )
            for frequency, frames in sheet_frames.items():
                all_frames[frequency].extend(frames)
            metadata_map.update(sheet_metadata)

        missing_indicators = sorted(set(dictionary) - seen_indicators)
        if missing_indicators:
            preview = "、".join(missing_indicators[:5])
            suffix = "……" if len(missing_indicators) > 5 else ""
            raise ValueError(f"指标字典中有指标未出现在数据sheet: {preview}{suffix}")

        dataframes = {}
        for frequency, frames in all_frames.items():
            if frames:
                merged = pd.concat(frames, axis=1)
                merged.sort_index(inplace=True)
                dataframes[frequency] = merged
            else:
                dataframes[frequency] = pd.DataFrame()

        source_map = {
            name: f"{Path(metadata.file_name).stem}|{metadata.sheet_name}"
            for name, metadata in metadata_map.items()
        }
        industry_map = {
            name: metadata.industry
            for name, metadata in metadata_map.items()
            if metadata.industry
        }
        unit_map = {
            name: metadata.unit for name, metadata in metadata_map.items()
        }
        type_map = {
            name: metadata.indicator_type
            for name, metadata in metadata_map.items()
            if metadata.indicator_type
        }
        frequency_map = {
            name: metadata.frequency for name, metadata in metadata_map.items()
        }

        return LoadedPreviewData(
            dataframes=dataframes,
            source_map=source_map,
            indicator_industry_map=industry_map,
            indicator_unit_map=unit_map,
            indicator_type_map=type_map,
            indicator_freq_map=frequency_map,
            indicator_metadata_map=metadata_map,
            module_name=module_name,
            custom_maps={
                "sheet_source": {
                    name: metadata.sheet_source
                    for name, metadata in metadata_map.items()
                },
                "dictionary_source": {
                    name: metadata.dictionary_source
                    for name, metadata in metadata_map.items()
                    if metadata.dictionary_source
                },
                "updated_at": {
                    name: metadata.updated_at
                    for name, metadata in metadata_map.items()
                },
                "forecast_variable": {
                    name: metadata.forecast_variable
                    for name, metadata in metadata_map.items()
                    if metadata.forecast_variable
                },
            },
        )
    finally:
        excel_file.close()


__all__ = [
    "DICTIONARY_SHEET_NAME",
    "FREQUENCIES",
    "IndicatorMetadata",
    "parse_preview_workbook",
]
