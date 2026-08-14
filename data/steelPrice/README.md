# MEsteel 阿联酋钢材月度价格

本目录下载并处理 MEsteel 公布的阿联酋 CFR/CPT 钢材月度报价，并将
15 类产品的报价区间中值写入 `../阿联酋.xlsx` 的
`月度_MEsteel` 工作表。

## 数据口径

- 数据源：<https://mesteel.com/newsletter/monthly_prices_latest4.php>
- 下载接口：<https://mesteel.com/newsletter/get_monthly_prices.php>
- 市场口径：CFR/CPT UAE
- 币种和单位：美元/公吨
- 月份：接口月初日期转换为对应月末日期
- 工作簿值：报价区间中值 `(下限 + 上限) / 2`
- 长表同时保留原始报价、下限、上限、产地标签和来源月份
- 缺报月份保持空白，不插值、不前向填充

MEsteel 会随着时间改变同一产品的参考产地标签。接口因此把一条产品
历史拆成若干产地段；当前数据中这些段的月份互不重叠，处理脚本按产品
合并。如果未来出现同一产品同月多条报价，脚本会停止并报错，避免静默
覆盖。

## 运行

在项目根目录运行：

```powershell
.\runtime\python.exe data\steelPrice\download_mesteel.py
.\runtime\python.exe data\steelPrice\process_mesteel.py
.\runtime\python.exe data\steelPrice\merge_workbook.py
```

写入前应关闭 Excel。合并脚本会先在 `backups/` 中建立时间戳备份，
使用 Microsoft Excel 原生 COM 写入临时副本，验证后再原位替换工作簿。
这样可保留原工作簿中的批注、外部链接及其他 Excel 专有部件。

## 输出

- `raw/mesteel_monthly_prices.json`：原始 JSON
- `raw/source_manifest.json`：下载时间、来源和 SHA-256
- `processed/mesteel_monthly_long.csv`：完整报价长表
- `processed/mesteel_monthly_midpoint_wide.csv`：供工作簿使用的中值宽表
- `processed/quality_report.json`：覆盖期和产品级质量报告
- `processed/workbook_merge_report.json`：工作簿写入及保真验证报告

原始数据、处理结果、备份工作簿均属于本地数据，不纳入 Git；本目录
只跟踪脚本和说明文件。
