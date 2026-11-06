"""Stable oil and gas classification labels."""

ASSET_LEVEL_LABELS = {
    "field": "单一油气田",
    "field_group": "油田群／综合体",
    "block": "区块",
    "concession": "特许区",
    "project": "开发项目",
    "development_area": "开发区",
}

COMMODITY_LABELS = {
    "crude_oil": "原油",
    "natural_gas": "天然气",
    "condensate": "凝析油",
    "oil_and_gas": "油气／凝析油",
}

OUTPUT_METRIC_TYPES = {
    "actual_output",
    "estimated_output",
    "estimated_daily_average",
    "actual_output_boe",
    "derived_daily_average",
    "historical_condensate_output",
    "historical_peak",
}

OPERATING_STATUS_LABELS = {
    "restoration_unconfirmed": "恢复未完成／当前产量待核（带时点）",
    "partially_operating": "部分运行／恢复未完成（带时点）",
    "producing": "在产",
    "temporarily_suspended": "暂停生产",
    "ceased": "停产／终止",
    "non_producing": "未生产",
    "development": "开发／建设中",
    "planned": "规划／评价中",
    "discovered": "已发现／待商业化",
    "storage": "转储存用途",
    "historical_unverified": "历史生产／当前待核",
    "unknown": "待核实",
}
