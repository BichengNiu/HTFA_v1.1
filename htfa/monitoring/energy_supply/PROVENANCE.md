# 能源保供模块来源

原项目：<https://github.com/BichengNiu/oil-field-map-demo>，迁入提交
`72f3b04ba9205f66ec1b34231ec6ae3d927dfc9c`。

HTFA 原生调用本包，保留地图、港口、船舶、油气页面及下载、地图截图和打印。
Leaflet、MarkerCluster 和 fflate 静态代码保留在 `ui/vendor/`，各自许可文件随代码保留。
不包含原项目内置的 Ts；统一使用 HTFA 安装的 Ts 公共绘图接口。

初始 DuckDB 快照：193212416 字节，SHA256
`1e3c5b8007878a269c0c22f7d40a202065cd87e03cf9a5532dc4c120382e2154`。
已导入 HTFA 唯一数据库 `htfa/monitoring/uae/assets/uae.duckdb` 的 `energy_supply` schema，
并保留来源文件字节、哈希、历史事实、双语名称和稳定主键。额外保留原项目
`audits/port_type_review_2026-10-16.json` 的类型核查证据。原始审计材料不单独提交。

原项目绘图参数已与 HTFA 的 Ts 公共签名核对，Ts 回归 527 项通过；无需扩展 Ts。
能源图表临时字体配置在绘制后恢复，防止影响 HTFA 其他模块。

数据来源及限制延续库内来源记录：GEM 管线遵循 CC BY 4.0 署名；IMF PortWatch
保留其方法与来源链接；AIS 保留返回的来源署名及实际报告时间。
缺失数据不补零，油气实际产量、产能和合计参考不混用。
