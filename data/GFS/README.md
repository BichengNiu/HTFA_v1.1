# 阿联酋财政部 GFS 数据整理

本目录保存阿联酋财政部（MOF）公布的 2012—2026 年政府财政统计（GFS）原始文件。可重复运行的整理代码位于 `scripts/data_sources/gfs/`。

`update_gfs.py` 从 2012—2023 年 PDF 和 2024—2026 年 Excel 原件中提取数据，并更新 `data/阿联酋.xlsx`：

- `季度_GFS`：2012 年一季度至最新已公布季度；
- `年度_GFS`：2012 年至最新已公布年度；
- `指标字典`：补充 29 个 GFS 指标及来源信息。

年度值直接采用财政部原件中的年度列，不由季度数相加生成。财政部原件明确说明，季度累计值不一定等于独立公布的年度值。

## 运行

请先关闭正在打开的 `阿联酋.xlsx`，然后在项目根目录运行：

```powershell
runtime\python.exe scripts\data_sources\gfs\update_gfs.py
```

仅校验原始文件、不写入目标工作簿：

```powershell
runtime\python.exe scripts\data_sources\gfs\update_gfs.py --validate-only
```

写入时只修改 XLSX 压缩包内的工作簿目录、`指标字典` 和两张 GFS 工作表；其他工作表、外部链接、批注、VBA/绘图等部件按原始字节保留。脚本在保存后会重新读取工作簿，逐单元格核对日期和数值，并检查日期格式、数字格式、指标字典及非 GFS 工作表是否保持不变。校验结果写入 `validation_report.json`。
