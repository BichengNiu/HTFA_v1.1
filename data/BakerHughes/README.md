# Baker Hughes 月度钻机数据更新

本目录只存放 Baker Hughes `WorldWide Rig Count Report.xlsx` 原始数据库。处理脚本位于 `scripts/data_sources/baker_hughes/`。

`update_baker_hughes_monthly.py` 会自动选择观测期最新的有效数据库，仅汇总 `DrillFor = Oil` 的阿布扎比、迪拜和沙迦月度活跃钻机数，并更新 `data/阿联酋.xlsx` 的 `月度_贝克休斯` sheet。Gas 和 Miscellaneous 不计入该指标；重复运行时，如果数据未变化则不会重写工作簿。

手动运行：

```powershell
runtime\python.exe scripts\data_sources\baker_hughes\update_baker_hughes_monthly.py
```

正常使用 `scripts\windows\start.bat` 启动 HTFA 时也会自动执行更新。以后只需把新的数据库文件放入本目录；脚本会按源表中的最新观测月份选择文件，不依赖文件名。写入使用本机 Excel，以保留 `阿联酋.xlsx` 的其他 sheet、外部链接和批注，因此运行更新时请关闭正在打开的 `阿联酋.xlsx`。
