# UAE来源撤下与T-100复核（2026-11-03）

按用户明确要求：

- 钢材只保留新Emsteel公开钢筋报价，撤下旧MEsteel进口报价的15个指标、
  `月度_MEsteel`、`mesteel_monthly` 和活动刷新/合并入口。物价图和报价卡
  改为读取 `月度_EMSTEEL`，单位AED/吨，保留“汇编含推算”名称及逐月批注。
- 重新在线下载TDRA九份官方工作簿，九个指标均截止2026年6月，没有后续
  观测。因此撤下 `月度_TDRA`、`tdra_telecom_monthly` 及对应指标和活动入口。
- 原始下载和历史运行日志作为本地审计资料保留，不再发布旧序列。

## T-100重新核实的证据

1. [BTS表说明页](https://www.transtats.bts.gov/TableInfo.asp?gnoyr_VQ=FJE)
   `Latest Available Data` 为 July, 2026。
2. [BTS官方筛选下载页](https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FJE&QO_fu146_anzr=)
   同样标明 Latest Available Data: July 2026。
3. 按2026年、United Arab Emirates、All Months重新下载，过滤保留US↔AE，
   共261条航段记录，仅包含2026年1—7月。最新月份在原ZIP中就是7月，
   不是Excel合并或月末截断丢失8月。

T-100刷新包括重取已有月份和历史修订，不保证每次出现新的观察月。下载器
现同时记录官方公布的最新期、实际过滤后月份、记录数、来源URL和文件哈希，
保存在被忽略的 `data/UAE/raw/t100/csv/uae_<year>.source.json`。
更新日志明确报告这两个截止期。近期重抓继续保留早年数据库历史，并拒绝
删除刷新年份内已有的观察键；旅客航段人次、货运及邮件磅数口径不变。

## 发布保护

停用来源在注册表中明确列出，普通 `all` 更新不会重新采集。标准入口先移除
数据库表及对应指标元数据，再原子移除Excel受管表并由数据库同步指标字典，
最后通过既有完整发布事务重建经济快照。未涉及的指标和Emsteel来源批注保留。

本次只切换物价图的数据来源及真实名称、单位；复用Ts现有 `plot_series`
标题、单位和单序列绘图接口，不改绘图引擎或参数契约。Ts源码实际位于
`D:/programs/Ts`，已先核对 `TsPlots/ts_plot.py` 的公共接口。

发布结果：44张表、632,250条观测、647个指标。撤下两类来源以外的所有
既有非空观测与撤下前快照逐项一致；Emsteel保留34个月及34条来源批注。
工作簿SHA-256与 `report.release` 一致。最终来源停用、BTS下载溯源及
实际经济快照上的页面测试13项通过；此前相关管线、元数据和交通测试亦已验证。
