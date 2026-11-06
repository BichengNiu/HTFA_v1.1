"""Dashboard page renderers with explicit current-view inputs."""

from __future__ import annotations

import streamlit as st

import htfa.monitoring.energy_supply.processing.ais as AIS
import htfa.monitoring.energy_supply.processing.portwatch as PORTWATCH


def render_method_panel(assets: list[dict]) -> None:
    st.subheader("范围、口径与数据限制")
    st.markdown(
        "**更新方式。** 展示端只读GitHub发布快照，不联网采集或写库；数据由既有采集发布脚本统一更新。"
    )
    st.dataframe(
        [
            {
                "数据": "港口 / 咽喉点日度记录",
                "当前更新": "采集端更新成功后发布日度记录，同一节点同一天去重更新",
                "进一步自动化": "源站发布时间决定最新观测日；缺失仍保持未知",
            },
            {
                "数据": "实时船位",
                "当前更新": "展示已发布船位快照；选择日期时读取当天归档",
                "进一步自动化": "覆盖与采集频率决定实时性，展示端不启动采集服务",
            },
            {
                "数据": "港口 / 咽喉点官方目录",
                "当前更新": "读取已发布的版本化目录",
                "进一步自动化": "补充 WPI / 运营商名录仍需版本核验",
            },
            {
                "数据": "港口风险运力",
                "当前更新": "既有采集任务尝试更新并归档；港口页不再展示该模型",
                "进一步自动化": "源为历史航线模型；重新抓取不代表实时风险",
            },
            {
                "数据": "油气产量、产能、状态和坐标",
                "当前更新": "带来源的静态披露；公开目录参考点另标版本和精度限制",
                "进一步自动化": "接运营商 / 监管机构 API 或公告抓取，校验资产、日期、单位、产量 / 产能后更新",
            },
            {
                "数据": "油气运营商、权益、发现年和投产年",
                "当前更新": "Global Energy Monitor 2026-03公开镜像参考（CC BY 4.0）；不代表当前在产",
                "进一步自动化": "新版本需核对名称和层级；原字段缺失保持为空，不填补日产量",
            },
            {
                "数据": "船位归档",
                "当前更新": "归档有明确观测时间的上游快照；接收时间另存，地图与船舶页展示已存最新快照",
                "进一步自动化": "统一DuckDB由Git LFS发布；保留真实观测，不以稀疏船位推断完整流量",
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "**地图与截图。** 港口和咽喉点分别使用源站最新观测日，船舶图层显示当前AIS快照；油气保留披露日期。地图下方的“保存图片”按钮可导出当前视野、图例、日期、弹窗及底图署名。"
    )
    st.markdown(
        "**港口覆盖。** 地图读取 IMF 当前维护的 PortWatch 港口点位数据库，"
        "覆盖下表五个水域框及沙特、阿联酋、伊拉克、伊朗、科威特、卡塔尔、阿曼、巴林全境的源库港口。"
        "另补港务局、运营商及NGA具名设施；无独立统计的设施保留未知，无可靠坐标时仅列目录。"
    )
    st.dataframe(
        [
            {"水域": name, "南界": b[0], "北界": b[1], "西界": b[2], "东界": b[3]}
            for name, b in PORTWATCH.REGIONS.items()
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        f"[IMF PortWatch 方法说明]({PORTWATCH.SOURCE}) · "
        "[当前港口点位 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0) · "
        "[每日港口活动 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0) · "
        "[每日咽喉点 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0) · "
        "[风险运力网络 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/spillovers_port_level_impact/FeatureServer/0)"
    )
    st.markdown(
        "**港口指标。** 港口页与地图弹窗的本周累计为所显示数据日所在周周一至当天；船型占比为分类累计艘次除以本周总艘次。缺报保留未知，下载中的滚动窗口指标按对应字段口径计算。"
    )
    st.dataframe(
        [
            {
                "指标": "港口活动指数",
                "计算": "当前窗口日均有效进港艘次 ÷ 前一等长窗口日均值 × 100",
                "解释": "100持平；高于100表示进港活动增加",
            },
            {
                "指标": "船型结构",
                "计算": "窗口内各船型进港艘次 ÷ 全部进港艘次",
                "解释": "集装箱、干散货、普通货物、滚装、油轮/液货船",
            },
            {
                "指标": "活跃天数率",
                "计算": "窗口内有效进港艘次大于0的天数 ÷ 窗口天数",
                "解释": "反映港口活动连续性",
            },
            {
                "指标": "单船平均货量",
                "计算": "窗口内估算进口量与出口量之和 ÷ 有效进港艘次",
                "解释": "单位万吨/艘次；属于AIS载荷估算",
            },
            {
                "指标": "进出口平衡指数",
                "计算": "(出口量−进口量) ÷ (出口量+进口量) × 100",
                "解释": "−100进口导向；+100出口导向",
            },
            {
                "指标": "风险运力",
                "计算": "该港所有出港航线 daily_capacity_at_risk 之和",
                "解释": "2019—2024历史航线网络冲击暴露，非实时值",
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "PortWatch 的 portcalls 是进入港界并通过贸易挂靠筛选的有效进港艘次，不是在港船舶存量；"
        "货量根据 AIS、载重和吃水估算。单日 0 只表示源表当日为 0；窗口不完整或比较基期为 0 时，"
        "派生指标保持为空，不以 0 替代。tanker 可能包含原油、成品油及其他液体货物。"
    )
    st.markdown(
        f"**船舶数据。** 免费快照来自[Open Waters开放AIS网络]({AIS.OPENWATERS_SOURCE})，"
        f"可选[AISStream WebSocket API]({AIS.SOURCE})在服务器端接收五个监测水域及红海北、南段的船级广播；"
        "船位快照用于地图、船舶页和后台打印报告；每次运行自动获取并保存最新船位，保留实际观测时间，获取失败时沿用已存快照。"
        "浏览器只接收标准化的每船最新位置，不接收API Key。"
        "多源位置按MMSI合并，航行阈值为0.5节；"
        "上游来源署名随船舶表及弹窗显示。"
    )
    st.markdown(
        "AIS 基础船型只能可靠区分油轮／液货船、货船、客船等大类，不能直接识别集装箱船、干散货船、"
        "原油油轮或成品油轮。AIS 是事件驱动广播，覆盖中断、设备关闭、错误 MMSI、延迟或位置欺骗都会造成缺失；"
        "未收到报文不等于水域内船舶数为 0。实时船位不能替代 PortWatch 按港界和贸易规则处理的日度挂靠指标。"
    )
    st.markdown(
        "**咽喉点。** 打印地图的空心紫色圆点标示全部监测咽喉点。"
        "popup列示总通过船数、估算承载货量及五类船型分解；港口和咽喉点默认分别使用最新观测日；选择历史日期时，各来源采用最近有效记录日，缺报不补零。"
    )
    st.markdown(
        f"**资产覆盖与战略层级（公开目录，非全量保证）。** 目录保留全部{len(assets)}项公开命名的生产、开发、发现或历史资产；"
        f"地图显示其中{sum(a['map_drawable'] for a in assets)}个具备可绘制坐标的资产。"
        "上级油田群、区块或特许区有"
        "直接披露值时，地图和目录按资产层级分别列示；上级缺坐标时可使用已定位组成"
        "资产的几何中心，并在弹窗中明确标注。"
    )
    st.markdown(
        "**坐标质量。** 地图优先使用资产级公开WGS84点位；区块缺少直接点位时，可使用组成油田"
        "或公开设施的代表点／几何中心；组成单田仍缺点位时，可使用最近上级资产代表点。此类坐标"
        "明确标为“近似”，只用于地图定位，不代表区块边界、储层范围或精确井位。坐标证据链接可在"
        "popup和资产表中追溯。"
    )
    st.markdown(
        "**产量与产能。** 油气统一使用橙色叉号；指标性质、数据日期和披露情况在弹窗及表格中列明。"
        "实际产量、历史产量、产能、目标和规划增量分别标注；未披露数值不视为零。不同日期、商品和权益口径"
        "不得相加。来源为千桶/日的油品数值在界面统一换算为万桶/日；生产状态带证据时点，"
        "不等于实时遥测。"
    )
