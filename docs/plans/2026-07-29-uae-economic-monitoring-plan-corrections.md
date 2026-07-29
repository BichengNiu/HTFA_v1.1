# UAE Economic Monitoring Phase 1 Plan Corrections

This appendix is part of
`docs/plans/2026-07-29-uae-economic-monitoring.md` and overrides the two snippets below.

## Correct workbook inventory command

```powershell
$env:PYTHONUTF8='1'
python -c "from dashboard.preview.core.workbook_parser import parse_preview_workbook; d=parse_preview_workbook(r'data/阿联酋.xlsx', module_name='uae_monitoring'); print('\n'.join(sorted(d.indicator_metadata_map)))"
```

## Correct parser adapter fields

`parse_preview_workbook` must be called with `module_name="uae_monitoring"`. Metadata is read from
`LoadedPreviewData.indicator_metadata_map`, then remapped from workbook names to semantic indicator
IDs before constructing `UAEDataBundle`.

The current workbook names required by Phase 1 are:

```python
BASE_INDICATOR_NAMES = {
    "growth.real_gdp": "阿联酋: GDP: 不变价",
    "growth.nominal_gdp": "阿联酋: GDP: 现价",
    "growth.nonoil_real_gdp": "阿联酋: GDP: 不变价: 非石油",
    "growth.nonoil_nominal_gdp": "阿联酋: GDP: 现价: 非石油",
    "oil.crude_production": "阿联酋: 产量: 原油",
    "market.dfm_index": "阿联酋DFM综合股票指数",
}

INDUSTRY_NAMES = {
    "mining": "采矿和采石(包括原油和天然气)",
    "manufacturing": "制造业",
    "construction": "建筑业",
    "real_estate": "房地产业",
    "wholesale_retail": "批发零售业、汽车及摩托车修理",
    "transport_storage": "运输和仓储",
    "accommodation_food": "住宿和餐饮服务业",
    "information_communication": "信息和通信",
    "finance_insurance": "金融保险业",
    "professional_scientific": "专业、科技活动",
    "household_employers": "家庭作为雇主的活动",
}
```

Do not use fuzzy matching. A verified future rename may be added as an explicit alias.
