# CBUAE 月度数据更新

本目录集中存放阿联酋央行月度数据的原始报告和更新脚本：

- `reports/`：按 `YYYY-MM.xlsx` / `YYYY-MM.pdf` 命名的 CBUAE Statistical Bulletin。
- `update_cbuae_monthly.py`：提取、合并并按正式六行元数据协议更新
  `data/阿联酋.xlsx` 中的 `CBUAE_月度` sheet，同时维护指标字典。
- `write_cbuae_sheet.ps1`：通过本机 Excel 后台写入目标 sheet，避免重写或损坏工作簿中的其他 sheet、外部链接和批注。

运行：

```powershell
.\.venv\Scripts\python.exe data\CBUAE\update_cbuae_monthly.py
```

脚本采用央行数据优先规则；央行序列缺少的月份才使用目标工作簿
`月度_Wind` 中的对应序列补充。重复运行会更新同一个 sheet，不会生成新的 CSV，
也不会改动其他数据 sheet。

运行环境需要安装 Microsoft Excel；脚本写入期间请关闭正在打开的 `阿联酋.xlsx`。

新增指标时，在 `update_cbuae_monthly.py` 中扩展指标列及相应的工作表行标签提取规则；新增月报放入 `reports/` 后再次运行脚本即可。
