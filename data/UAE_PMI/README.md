# UAE headline PMI 月度数据

本目录保存阿联酋非油私营部门总体 PMI（月度、经季节调整）的本地下载结果、标准化 CSV 和质量检查报告。工作簿中的目标 sheet 按约定命名为 `月度_LSEG`，但单元格“来源”会如实写为 `S&P Global / Trading Economics（公开样本）`，不会把公开网页数据标成 LSEG 专有数据。

数据由 S&P Global 编制。抓取入口是 Trading Economics 的[公开展示页](https://tradingeconomics.com/united-arab-emirates/manufacturing-pmi)，该页明确说明其仅展示经 S&P Global 授权的有限 headline 样本；完整 headline 历史和分项历史需要订阅。因此，本地质量报告会同时检查历史月份、月度连续性和最新月份，也会明确标记“不是完整调查历史”。

运行顺序：

```powershell
runtime\python.exe data\UAE_PMI\download_uae_pmi.py
runtime\python.exe data\UAE_PMI\process_uae_pmi.py
```

生成文件：

- `raw/tradingeconomics_chart.json`：公开图表原始响应解码后的 JSON。
- `raw/source_metadata.json`：下载时间、来源链接、覆盖期和最新值。
- `uae_pmi_monthly.csv`：标准化月度序列。
- `quality_report.json`：历史覆盖、连续性、重复值、数值范围和最新性检查。
- `../阿联酋.xlsx` 的 `月度_LSEG`：最新月份在上，日期按月末写入。

处理脚本通过本机 Excel 写入，保留工作簿的其他 sheet、外部链接和批注。运行前请关闭正在打开的 `阿联酋.xlsx`；写入失败或写后验证失败时会从临时备份回滚。
