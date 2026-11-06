"""经过口径审计的中东公开命名油气资产目录（DEMO）。

设计原则：一个记录对应一个可公开识别的油田、气田、油田群、区块、特许区或项目；
每条记录均给出资产层级、上级资产、统计范围、商品和权益口径。
未公开的逐田数值保留为空，不以国家、区块或油田群数据填充。
有坐标记录为公开地图资料的近似中心点；无核验坐标的记录只列目录。
"""

from __future__ import annotations

import json
from htfa.monitoring.energy_supply import data_store
import re
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Any


SOURCES = {
    "ADNOC Onshore": "https://www.adnoc.ae/en/adnoc-onshore/about-us/what-we-do",
    "ADNOC Offshore": "https://www.adnoc.ae/en/adnoc-offshore",
    "ADNOC Al Yasat": "https://adnoc.ae/en/al-yasat-petroleum/about-us/what-we-do",
    "ADNOC Ghasha": "https://adnoc.ae/en/news-and-media/press-releases/2025/uae-president-chairs-adnoc-board-of-directors-meeting-at-habshan-complex",
    "Dubai Petroleum": "https://www.dubaipetroleum.ae/about-us/oil-and-gas-assets/",
    "Saudi Aramco / EIA": "https://www.eia.gov/international/analysis/country/SAU",
    "EIA Iran": "https://www.eia.gov/international/content/analysis/countries_long/Iran/pdf/Iran%20CAB%202024.pdf",
    "EIA Iraq": "https://www.eia.gov/international/analysis/country/irq",
    "KOC / KPC": "https://www.kockw.com/sites/EN/Pages/Profile/whoAreWe/KOC-History.aspx",
    "QatarEnergy": "https://www.qatarenergy.qa/en/MediaCenter/Publications/QatarEnergy_Investors_Presentation_November_2025.pdf",
    "PDO": "https://www.pdo.co.om/en/Pages/WhoWeAre/OurJourney.aspx",
    "Bapco": "https://www.bapco.net/en/page/history/",
    "Yemen Ministry of Oil": "https://mom-ye.com/site-en/",
    "Syria public reporting": "https://www.reuters.com/business/energy/shell-seeks-exit-syrias-al-omar-oilfield-official-says-2026-01-19/",
    "Le Monde Al-Omar 2026": "https://www.lemonde.fr/en/economy/article/2026/02/22/the-syrian-oil-sector-s-year-zero_6750756_19.html",
    "Israel Ministry of Energy": "https://prime.energy.gov.il/en/prime.html",
    "UNFCCC Bahrain BTR": "https://unfccc.int/sites/default/files/resource/30112025_Bahrain%27s_BTR1_2024_to_the_UNFCCC_vSubmitted.pdf",
    "KOC Annual Report 2023-24": "https://www.kockw.com/sites/EN/Annual%20Reports/2023%20-%202024%20English.pdf",
    "Masirah Oil Yumna": "https://www.masirahoil.om/post/production-update-march-2026",
    "GEM Yibal": "https://www.gem.wiki/Yibal_Oil_and_Gas_Field_(Oman)",
    "OQ / GEM Bisat": "https://oq.com/en/news-and-media/newsroom/20230126-oq-celebrates-inauguration-of-bisat-oil-field",
    "Shafaq News Faihaa": "https://shafaq.com/en/Economy/Iraq-expands-oil-production-starts-drilling-in-border-region",
    "Iraqi News West Qurna-1": "https://www.iraqinews.com/iraq/iraq-to-raise-west-qurna-1s-output-to-670000-bpd-in-2026/",
    "GEM Fakkah": "https://www.gem.wiki/Fakkah_Oil_Field_(Iraq)",
    "GEM Bazerkan": "https://www.gem.wiki/Bazerkan_Oil_Field_(Iraq)",
    "GEM Abu Gharb": "https://www.gem.wiki/Abu_Gharb_Oil_Field_(Iraq)",
    "GEM Luhais": "https://www.gem.wiki/Luhais_Oil_Field_(Iraq)",
    "GEM Subba": "https://www.gem.wiki/Subba_Oil_Field_(Iraq)",
    "GEM Tuba": "https://www.gem.wiki/Tuba_Oil_and_Gas_Field_(Iraq)",
    "GEM Bibi Hakimeh": "https://www.gem.wiki/Bibi_Hakimeh_Oil_Field_(Iran)",
    "GEM Karanj": "https://www.gem.wiki/Karanj_Oil_Field_(Iran)",
    "GEM Abuzar": "https://www.gem.wiki/Abuzar_Oil_Field_(Iran)",
    "GEM Mansouri": "https://www.gem.wiki/Mansouri_Oil_Field_(Iran)",
    "GEM Sepehr-Jufair": "https://www.gem.wiki/Sepehr-Jufair_Oil_Field_(Iran)",
    "GEM Parsi": "https://www.gem.wiki/Parsi_Oil_Field_(Iran)",
    "GEM Bahregansar": "https://www.gem.wiki/Bahregansar_Oil_Field_(Iran)",
    "GEM Sirri E": "https://www.gem.wiki/Sirri_E_Oil_and_Gas_Field_(Iran)",
    "GEM Masjed Soleyman": "https://www.gem.wiki/Masjed_Soleyman_Oil_Field_(Iran)",
    "GEM Marun": "https://www.gem.wiki/Marun_Oil_Field_(Iran)",
    "GEM Aghajari": "https://www.gem.wiki/Aghajari_Oil_Field_(Iran)",
    "GEM Gachsaran": "https://www.gem.wiki/Gachsaran_Oil_and_Gas_Field_(Iran)",
    "GEM South Azadegan": "https://www.gem.wiki/Azadegan_South_Oil_Field_(Iran)",
    "Trend North Azadegan": "https://www.trend.az/iran/business/3153217.html",
    "TPAO": "https://www.tpao.gov.tr/",
    "Rumaila Operating Organisation": "https://rumaila.iq/english/about-us/history-2/",
    "DNO 2025 Results": "https://www.dno.no/media/t14pl1zl/2025-interim-results-report.pdf",
    "Gulf Keystone H1 2026": "https://www.gulfkeystone.com/2026-half-year-results-announcement/",
    "ShaMaran Q2 2026": "https://shamaranpetroleum.com/news/shamaran-reports-second-quarter-2026-results-122891/",
    "PETRONAS Gharraf": "https://www.petronas.com/partner-us/pcihbv-contract-plan",
    "KOC Annual Report 2024-25": "https://www.kockw.com/sites/EN/Annual%20Reports/2024-2025%20English.pdf",
    "Saudi Press Agency 2025": "https://www.spa.gov.sa/en/N2295070",
    "Saudi Press Agency 2024": "https://www.spa.gov.sa/N2131725",
    "Daleel Petroleum": "https://daleelpetroleum.com/operational-excellence/production",
    "Occidental Oman": "https://www.oxy.com/operations/performance-production/",
    "GEM Pazanan": "https://www.gem.wiki/Pazanan_Oil_Field_(Iran)",
    "GEM Kupal": "https://www.gem.wiki/Kupal_Oil_Field_(Iran)",
    "GEM Dehloran": "https://www.gem.wiki/Dehloran_Oil_Field_(Iran)",
    "GEM Paranj": "https://www.gem.wiki/Paranj_Oil_Field_(Iran)",
    "GEM Nargesi": "https://www.gem.wiki/Nargesi_Oil_Field_(Iran)",
    "Aramco 2019 Prospectus": "https://www.aramco.com/-/media/images/investors/saudi-aramco-prospectus-en-051219.pdf",
    "Iraq EITI 2021": "https://eiti.org/sites/default/files/2024-01/Iraq%202021%20EITI%20Report.pdf",
    "Iraq EITI 2016": "https://eiti.org/sites/default/files/attachments/iraq_2016_eiti_report.pdf",
    "QatarEnergy E&P": "https://www.qatarenergy.qa/en/Whatwedo/Pages/ExplorationandProduction.aspx",
    "ADOC Fields": "https://www.cts-co.net/adocauh/product/",
    "Aramco FY2025 Results": "https://china.aramco.com/zh-cn/news-media/global-news/2026/aramco-announces-fourth-quarter-and-full-year-2025-results",
    "Aramco 2019 Increments": "https://www.aramco.com/en/news-media/news/2019/aramco-contracts-marjan-berri-oilfields",
    "Aramco 2019 GMTN": "https://www.aramco.com/-/media/publications/corporate-reports/bonds/2019-gmtn-prospectus.pdf",
    "Iraq EITI 2019-20": "https://eiti.org/sites/default/files/2023-01/doc-1232-2022_12_15_11_48_01.pdf",
    "SHANA Hengam 2010": "https://www.shana.ir/news/156860/",
    "KOC Mutriba": "https://www.kockw.com/sites/EN/EMagazine/Pages/Events/1032.aspx",
    "OQEP Operations": "https://www.oqep.om/operation",
    "SNOC Upstream": "https://www.snoc.ae/our-business/upstream/",
    "SNOC GHG 2021": "https://www.snoc.ae/wp-content/uploads/SNOC-2021-GHG-Report.pdf",
    "RAKGAS History": "https://www.rakgas.ae/en/who-we-are/our-story",
    "Bapco Abu Safah": "https://www.bapco.net/en/page/crude-and-petroleum-products",
    "Aramco 2017 Review": "https://www.aramco.com/en/news-media/news/2018/2017-annual-review",
    "Aramco 2025 Highlights": "https://www.aramco.com/en/investors/annual-report/highlights",
    "Aramco Gas 2026": "https://www.aramco.com/en/news-media/news/2026/aramcos-gas-strategy-builds-momentum-with-major-progress-towards-growth-target",
    "ADNOC Bab 2019": "https://adnoc.ae/en/news-and-media/press-releases/2019/adnoc-invests-aed-1-8-billion-to-upgrade-its-giant-bab-onshore-field",
    "ADNOC Bu Hasa 2021": "https://www.adnoc.ae/news-and-media/press-releases/2021/adnoc-invests-usd318-million-to-connect-smart-wells-at-bu-hasa",
    "ADNOC Shah 2025": "https://adnoc.ae/en/news-and-media/press-releases/2025/adnoc-achieves-industryleading-carbon-intensity-at-shah",
    "ADNOC Lower Zakum 2022": "https://adnoc.ae/en/news-and-media/press-releases/2022/adnoc-announces-%24548-million-contract-for-a-new-main-gas-line-at-its-lower-zakum-field",
    "INPEX Upper Zakum 2017": "https://www.inpex.com/english/news/english/news/assets/pdf/e20171114.pdf",
    "ADNOC Umm Shaif 2022": "https://www.adnoc.ae/en/news-and-media/press-releases/2022/adnoc-invests-close-to-usd1-billion-in-the-long-term-development-of-umm-shaif-field",
    "INPEX Nasr 2015": "https://www.inpex.com/english/news/english/news/assets/pdf/e20150205.pdf",
    "INPEX Umm Lulu 2014": "https://www.inpex.com/english/news/english/news/assets/pdf/e20141017.pdf",
    "ADNOC SARB 2024": "https://adnoc.ae/en/news-and-media/press-releases/2023/adnocs-offshore-sarb-field-commences-ai-enabled-digital-operations",
    "ADNOC Belbazem 2024": "https://adnoc.ae/en/news-and-media/press-releases/2023/adnoc-announces-first-production-from-belbazem-offshore-block/",
    "ADNOC Haliba": "https://www.adnoc.ae/en/al-dhafra-petroleum/about-us/what-we-do",
    "Iraq EITI 2023": "https://eiti.org/documents/iraq-2023-eiti-report",
    "HKN Sarsang": "https://www.hknenergy.com/",
    "Kurdistan Presidency 2025": "https://presidency.gov.krd/en/statement-from-the-presidency-of-the-kurdistan-region-5/",
    "Genel Q1 2024": "https://genelenergy.com/wp-content/uploads/Genel-2024-Q1-trading-update.pdf",
    "DNO Kurdistan 2025": "https://www.dno.no/en/operations/kurdistan-region-of-iraq/",
    "Daleel 2023": "https://daleelpetroleum.com/media/news/2023/daleel-petroleum-a-journey-of-excellence",
    "PDO Sustainability 2024": "https://www.pdo.co.om/en/PDOSERVICES/Sustainability%20Report%202024%20English.pdf",
    "GEM Darquain": "https://www.gem.wiki/Darquain_Oil_Field_%28Iran%29",
    "Qatar News Agency A-Structures": "https://qna.org.qa/en/news/news-details?date=23%2F12%2F2022&id=0056-qatarenergy-signs-agreement-with-qpd-to-continue-al-karkara%2C-a-structures-offshore-fields-development-and-production",
    "Yemen EIA": "https://www.eia.gov/international/content/analysis/countries_long/Yemen/yemen.pdf",
    "Yemen PEPA Production Plan": "https://pepaye.com/production/plan",
    "Rudaw Rmeilan Sector One": "https://www.rudaw.net/english/categories/syria/933427",
    "Egypt EGPC Brownfields 2023": "https://eug.petroleum.gov.eg/dp/jsp/assets/docs/EGPC/2023%20EGPC%20Brownfields%20Overview.pdf",
    "Eni Egypt Factbook 2013": "https://report.eni.com/factbook-2013/en/business-segments/exploration-production/activity-areas/north-africa.html",
    "Yemen PEPA Block 5": "https://www.pepaye.com/page/67",
}


def record(
    country: str,
    name: str,
    name_cn: str,
    asset_type: str,
    lat: float | None,
    lon: float | None,
    *,
    value: str | None = None,
    metric_type: str = "undisclosed",
    unit: str | None = None,
    data_date: str | None = None,
    status: str = "公开命名资产",
    source: str,
    source_url: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    return {
        "country": country,
        "name": name,
        "name_cn": name_cn,
        "asset_type": asset_type,
        "lat": lat,
        "lon": lon,
        "value": value,
        "metric_type": metric_type,
        "unit": unit,
        "data_date": data_date,
        "status": status,
        "coordinate_precision": "近似中心点" if lat is not None and lon is not None else "待核验；仅列目录",
        "source": source,
        "source_url": source_url or SOURCES[source],
        "note": note,
    }


# 仅在来源给出明确的单一资产口径时填写 value；区块／项目数值不可归给组成油田。
ASSETS = [
    # Saudi Arabia
    record("沙特阿拉伯", "Ghawar", "加瓦尔", "油田", 25.42, 49.57, value="3,800", metric_type="maximum_sustainable_capacity", unit="千桶/日", data_date="2018-12-31", source="Aramco 2019 Prospectus", note="阿美招股书表14最大可持续产能，不是当期实际产量。"),
    record("沙特阿拉伯", "Safaniya", "萨法尼亚", "海上油田", 28.18, 48.78, value="1,300", metric_type="maximum_sustainable_capacity", unit="千桶/日", data_date="2018-12-31", source="Aramco 2019 Prospectus", note="阿美招股书截至2018年末最大可持续产能；非实际日产量。"),
    record("沙特阿拉伯", "Khurais", "库赖斯", "油田／综合体", 25.03, 48.24, value="1,450", metric_type="maximum_sustainable_capacity", unit="千桶/日", data_date="2018-12-31", source="Aramco 2019 Prospectus", note="阿美公布的Khurais综合体最大可持续产能，含Abu Jifan、Mazalij等，不能分配给Khurais单田；非实际产量。"),
    record("沙特阿拉伯", "Shaybah", "谢拜", "油田", 22.48, 53.78, value="1,000", metric_type="maximum_sustainable_capacity", unit="千桶/日", data_date="2018-12-31", source="Aramco 2019 Prospectus", note="阿美招股书表14最大可持续产能，非当前实际日产量。"),
    record("沙特阿拉伯", "Manifa", "马尼法", "海上油田", 27.62, 49.87, value="900", metric_type="capacity", unit="千桶/日", data_date="2019年招股书披露", source="Aramco 2019 Prospectus", note="阿美招股书列马尼法原油生产能力90万桶/日；披露时点的历史产能，非当前实产。"),
    record("沙特阿拉伯", "Marjan", "马尔詹", "海上油田", 27.47, 49.86, value="300", metric_type="incremental_capacity", unit="千桶/日", data_date="2025年项目投产", source="Aramco FY2025 Results", note="2025年投产项目的新增产能，并非油田总产能或实际日产量。"),
    record("沙特阿拉伯", "Berri", "贝里", "海上油田", 27.83, 49.93, value="250", metric_type="planned_incremental_capacity", unit="千桶/日", data_date="2019-07-09规划；截至2025年末注水启动", source="Aramco 2019 Increments", note="项目规划新增原油产能；阿美2025全年业绩仅称注水作业已启动，未证实该增量已投产，不能作实际日产量。"),
    record("沙特阿拉伯", "Zuluf", "祖卢夫", "海上油田", 27.67, 49.12, value="825", metric_type="maximum_sustainable_capacity", unit="千桶/日", data_date="2018-12-31", source="Aramco 2019 Prospectus", note="阿美招股书截至2018年末最大可持续产能；不能与后续项目新增/处理能力混同，非实际日产量。"),
    record("沙特阿拉伯", "Qatif", "卡提夫", "油田", 26.55, 50.01, source="Saudi Aramco / EIA"),
    record("沙特阿拉伯", "Abqaiq", "阿布盖格", "油田", 25.94, 49.68, source="Saudi Aramco / EIA"),
    record("沙特阿拉伯", "Khursaniyah", "胡尔萨尼亚", "油田", 27.72, 48.91, source="Saudi Aramco / EIA"),
    record("沙特阿拉伯", "Dammam", "达曼", "油田", 26.36, 49.99, value="25", metric_type="incremental_capacity", unit="千桶/日", data_date="2025年第二季度投产", source="Aramco 2025 Highlights", note="达曼开发一期新增原油产能，不是整个油田实际日产量。"),
    record("沙特阿拉伯", "Jafurah", "贾富拉", "非常规气田", 25.43, 48.82, status="2026年宣布开始产气", source="Aramco Gas 2026", note="阿美2026年确认气田开始生产；天然气或油当量数据不作为原油逐田日产量。"),
    # 2025 年公布的新发现：井测试流量不是油田持续日产量；未核验点位不绘地图标。
    record("沙特阿拉伯", "Jabu", "贾布", "发现油田", None, None, status="已发现；商业生产未证实", source="Saudi Press Agency 2025", note="官方公布的新发现油田；试井流量不填作油田日产量。"),
    record("沙特阿拉伯", "Sayahid", "萨亚希德", "发现油田", None, None, status="已发现；商业生产未证实", source="Saudi Press Agency 2025", note="官方公布的新发现油田；逐田实产未披露。"),
    record("沙特阿拉伯", "Ayfan", "艾凡", "发现油田", None, None, status="已发现；商业生产未证实", source="Saudi Press Agency 2025", note="官方公布的新发现油田；逐田实产未披露。"),
    record("沙特阿拉伯", "Nuwayr", "努韦尔", "发现油田", None, None, status="已发现；商业生产未证实", source="Saudi Press Agency 2025", note="官方公布的新发现油田；逐田实产未披露。"),
    record("沙特阿拉伯", "Damda", "达姆达", "发现油田", None, None, status="已发现；商业生产未证实", source="Saudi Press Agency 2025", note="官方公布的新发现油田；逐田实产未披露。"),
    record("沙特阿拉伯", "Qurqas", "古尔加斯", "发现油田", None, None, status="已发现；商业生产未证实", source="Saudi Press Agency 2025", note="官方公布的新发现油田；逐田实产未披露。"),
    record("沙特阿拉伯", "Ladam", "拉达姆", "非常规发现油田", None, None, status="2024年发现；商业生产未证实", source="Saudi Press Agency 2024", note="官方公布的非常规油田；5,100桶/日是Ladam-2井测试流量，不是全田持续日产量。"),
    record("沙特阿拉伯", "Faruq", "法鲁克", "非常规发现油田", None, None, status="2024年发现；商业生产未证实", source="Saudi Press Agency 2024", note="官方公布的非常规油田；4,557桶/日是Faruq-4井测试流量，不是全田持续日产量。"),

    # Aramco prospectus identifies these as separate fields within the Khurais complex; no field-level production split.
    record("沙特阿拉伯", "Abu Jifan", "阿布吉凡", "油田（Khurais综合体）", None, None, source="Aramco 2019 Prospectus", note="阿美列为Khurais综合体组成油田；综合体1,450千桶/日产能不可拆给单田。"),
    record("沙特阿拉伯", "Mazalij", "马扎利吉", "油田（Khurais综合体）", None, None, source="Aramco 2019 Prospectus", note="阿美列为Khurais综合体组成油田；单田产量未披露。"),
    record("沙特阿拉伯", "Qirdi", "吉尔迪", "油田", None, None, source="Aramco 2019 Prospectus", note="阿美招股书将Qirdi与Khurais、Abu Jifan、Mazalij共同列为Khurais综合体的四个油田；单田产量未披露。"),
    record("沙特阿拉伯", "Abu Hadriya", "阿布哈德里亚", "油田", None, None, source="Aramco 2019 Prospectus", note="阿美储量认证附件列为油田；生产状态及逐田日产量待核。"),
    record("沙特阿拉伯", "Fadhili", "法迪利", "油田", None, None, source="Aramco 2019 Prospectus", note="阿美储量认证附件列为油田；与同名气体处理设施区分，逐田原油日产量待核。"),
    record("沙特阿拉伯", "Harmaliyah", "哈马利亚", "油田", None, None, source="Aramco 2019 Prospectus", note="阿美储量认证附件列为油田；逐田产量未披露。"),
    record("沙特阿拉伯", "Hawtah", "豪塔", "油田", None, None, source="Aramco 2019 GMTN", note="阿美2019年债券招股书第100页原油基础设施图列名；逐田产量及坐标未核验。"),
    record("沙特阿拉伯", "Sakab", "萨卡布", "发现油田", None, None, status="2017年发现；商业生产未核", source="Aramco 2017 Review", note="阿美2017年度回顾列为新发现油田；无可核验单田持续日产量。"),
    record("沙特阿拉伯", "Zumul", "祖穆尔", "发现油田", None, None, status="2017年发现；商业生产未核", source="Aramco 2017 Review", note="阿美2017年度回顾列为鲁卜哈利新发现油田；无可核验单田持续日产量。"),

    # United Arab Emirates — ADNOC Onshore
    record("阿联酋", "Bab", "巴布", "油田", 23.93, 53.79, value="450", metric_type="target_capacity", unit="千桶/日", data_date="2019-11-13公告；此前合同目标2020年", source="ADNOC Bab 2019", note="ADNOC回顾此前将产能从420提高至450千桶/日的2020年目标，另提出485千桶/日长期维持项目；均非已核实实产。"),
    record("阿联酋", "Bu Hasa", "布哈萨", "油田", 23.52, 53.24, value="650", metric_type="capacity", unit="千桶/日", data_date="2021-05-10公告", source="ADNOC Bu Hasa 2021", note="ADNOC称投资维持该田650千桶/日产能；不是逐日实际产量。"),
    record("阿联酋", "Huwaila", "胡韦拉", "油田", 23.70, 53.45, source="ADNOC Onshore"),
    record("阿联酋", "Bida Al-Qemzan", "比达·盖姆赞", "油田", 23.66, 53.66, source="ADNOC Onshore"),
    record("阿联酋", "Al Dabb'iya", "达比亚", "油田", 24.36, 54.15, source="ADNOC Onshore"),
    record("阿联酋", "Rumaitha", "鲁迈萨", "油田", 24.30, 54.22, source="ADNOC Onshore"),
    record("阿联酋", "Shanayel", "沙奈耶勒", "油田", 24.18, 54.27, source="ADNOC Onshore"),
    record("阿联酋", "Asab", "阿萨布", "油田", 23.45, 53.77, source="ADNOC Onshore"),
    record("阿联酋", "Sahil", "萨希勒", "油田", 23.55, 53.90, source="ADNOC Onshore"),
    record("阿联酋", "Shah", "沙阿", "油气田", 22.99, 53.95, value="70", metric_type="oil_capacity", unit="千桶/日", data_date="2025-01-23公告", source="ADNOC Shah 2025", note="原油产能约70千桶/日；与同名气体处理能力分开，非实产。"),
    record("阿联酋", "Qusahwira", "古萨赫维拉", "油田", 23.23, 54.18, source="ADNOC Onshore"),
    record("阿联酋", "Mender", "门德尔", "油田", 23.08, 54.00, source="ADNOC Onshore"),
    record("阿联酋", "Jumaylah", "朱迈拉", "油田", 24.05, 53.70, status="公开命名；生产状态待确认", source="ADNOC Onshore"),
    record("阿联酋", "Al Nouf", "努夫", "油田", 24.11, 53.82, status="公开命名；生产状态待确认", source="ADNOC Onshore"),

    # United Arab Emirates — ADNOC Offshore
    record("阿联酋", "Upper Zakum", "上扎库姆", "海上油田", 24.85, 53.66, value="1,000", metric_type="target_capacity", unit="千桶/日", data_date="2017-11-14协议；目标2024年", source="INPEX Upper Zakum 2017", note="合作伙伴2017年提出的产能提升目标；未据此认定2024年已达产，更不是实际日产量。"),
    record("阿联酋", "Lower Zakum", "下扎库姆", "海上油田", 24.74, 53.51, value="450", metric_type="target_capacity", unit="千桶/日", data_date="2022-09-05公告；目标2025年", source="ADNOC Lower Zakum 2022", note="ADNOC称产能计划在2025年提高到450千桶/日；未找到已实现的逐田产能或实产确认。"),
    record("阿联酋", "Umm Shaif", "乌姆沙伊夫", "海上油田", 25.26, 53.28, value="275", metric_type="capacity", unit="千桶/日", data_date="2022-01-05公告", source="ADNOC Umm Shaif 2022", note="ADNOC公布维持现有275千桶/日产能的项目；非实际日产量。"),
    record("阿联酋", "Satah", "萨塔赫", "海上油田", 25.10, 52.74, source="ADNOC Offshore"),
    record("阿联酋", "Nasr", "纳斯尔", "海上油田", 25.54, 53.52, value="65", metric_type="target_capacity", unit="千桶/日", data_date="2015-02-05公告；全田开发预期峰值", source="INPEX Nasr 2015", note="INPEX在初期投产公告中预期全田开发完成后峰值65千桶/日；未核实实际达到或当前实产。"),
    record("阿联酋", "Umm Al Dalkh", "乌姆阿尔达尔赫", "海上油田", 24.63, 54.10, source="ADNOC Offshore"),
    record("阿联酋", "Satah Al Razboot (SARB)", "萨塔赫·阿尔拉兹布特", "海上油气田", 25.19, 53.18, value="140", metric_type="capacity", unit="千桶/日", data_date="2024-07-30公告", source="ADNOC SARB 2024", note="ADNOC宣布该田达到140千桶/日产能；非实际日产量，深层气项目单列。"),
    record("阿联酋", "Umm Lulu", "乌姆卢卢", "海上油田", 24.70, 54.06, value="105", metric_type="target_capacity", unit="千桶/日", data_date="2014-10-17公告；全田开发预期峰值", source="INPEX Umm Lulu 2014", note="INPEX初期投产公告称全田开发完成后预期峰值105千桶/日；不能认定已经达到。"),
    record("阿联酋", "Abu Al Bukhoosh", "阿布阿尔布胡什", "海上油田", 25.50, 53.15, source="ADNOC Offshore"),

    # United Arab Emirates — Al Yasat / Ghasha / other concessions
    record("阿联酋", "Bu Haseer", "布哈塞尔", "海上油田", 24.93, 53.17, value="8", metric_type="actual_output", unit="千桶/日", data_date="2018年3月初期投产口径", source="ADNOC Al Yasat", note="ADNOC称初期生产方案日产8千桶；全田15千桶/日仅是目标，未用目标代替实产；本值并非当前产量。"),
    record("阿联酋", "Belbazem", "贝尔巴泽姆", "海上油田", 25.13, 53.59, source="ADNOC Belbazem 2024", note="2024年投产的Belbazem区块组成油田之一；45千桶/日属于三区块合计目标，单田实产未披露。"),
    record("阿联酋", "Belbazem Offshore Block", "贝尔巴泽姆海上区块", "海上区块（三油田）", None, None, value="45", metric_type="target_capacity", unit="千桶/日", data_date="2024-03-27公告；逐步达产目标", source="ADNOC Belbazem 2024", note="目标为Belbazem、Umm Al Salsal、Umm Al Dholou三田合计产能，非任一单田或已核实实产；区块无单点坐标。"),
    record("阿联酋", "Umm Al Salsal", "乌姆阿尔萨尔萨勒", "海上油田", 25.07, 53.53, source="ADNOC Al Yasat"),
    record("阿联酋", "Umm Al Dholou", "乌姆阿尔祖卢", "海上油田", 25.01, 53.64, source="ADNOC Al Yasat"),
    record("阿联酋", "Arzanah", "阿尔扎纳", "海上油田", 24.79, 52.56, source="ADNOC Al Yasat"),
    record("阿联酋", "Nahaidiin", "纳海迪因", "油田", 23.82, 52.20, source="ADNOC Al Yasat"),
    record("阿联酋", "Bin Hadi", "本哈迪", "油田", 23.72, 52.43, source="ADNOC Al Yasat"),
    record("阿联酋", "Gezira", "盖济拉", "油田", 23.89, 52.61, source="ADNOC Al Yasat"),
    record("阿联酋", "Muhaymat", "穆海马特", "浅海油田", 24.10, 52.10, source="ADNOC Al Yasat"),
    record("阿联酋", "Sila", "锡拉", "浅海油田", 24.08, 51.76, source="ADNOC Al Yasat"),
    record("阿联酋", "Ghasha", "加沙", "超酸性气田", 24.95, 52.77, source="ADNOC Ghasha"),
    record("阿联酋", "Dalma", "达尔马", "超酸性气田", 24.78, 52.83, source="ADNOC Ghasha"),
    record("阿联酋", "Shuweihat", "舒韦哈特", "超酸性气田", 24.20, 52.55, source="ADNOC Ghasha"),
    record("阿联酋", "Ghasha Concession", "Ghasha特许区", "海上油气特许区", None, None, value="150", metric_type="target_capacity", unit="千桶/日（原油及凝析油）", data_date="2025-11-24公告；预期口径", status="建设推进中；特许区目标", source="ADNOC Ghasha", note="ADNOC称Ghasha特许区包括Hail、Ghasha、Dalma、SARB和Nasr，预期日产15万桶原油及凝析油；这是特许区目标／预期，不是单田或已核实实产。"),
    record("阿联酋", "SARB Deep Gas", "SARB 深层气项目", "天然气项目", 25.19, 53.18, value="200", metric_type="target_capacity", unit="百万标准立方英尺/日", data_date="2026-01-07", source="ADNOC Ghasha", note="天然气项目，不能与原油日产量相加。"),
    record("阿联酋", "Hail (ADOC)", "海尔（ADOC）", "海上油田", 24.37, 53.41, status="2017年投产", source="ADOC Fields", note="ADOC确认Hail与Mubarraz等田的原油混合外运；原列21千桶/日未在该单田来源中核实，撤回。"),
    record("阿联酋", "Hail (ADNOC Ghasha)", "海尔（ADNOC Ghasha）", "含酸气海上油气田", None, None, status="ADNOC列为Ghasha开发项目组成资产；单田投产状态待核", source="ADNOC Ghasha", note="与上方Hail (ADOC)是不同资产。ADNOC将Hail列入Ghasha项目；项目层级的气量／液体目标不分摊为该田产量，单田坐标和产量未核实。"),
    record("阿联酋", "Mubarraz", "穆巴拉兹", "海上油田", 24.40, 53.52, source="ADOC Fields"),
    record("阿联酋", "Umm Al-Anbar", "乌姆阿尔安巴尔", "海上油田", 24.30, 53.45, source="ADOC Fields"),
    record("阿联酋", "Neewat Al-Ghalan", "尼瓦特阿尔加兰", "海上油田", 24.22, 53.55, source="ADOC Fields"),
    record("阿联酋", "Bunduq", "本杜克", "跨境海上油田", 25.22, 52.72, value="9.2", metric_type="actual_output", unit="千桶/日", data_date="2024年平均", source="QatarEnergy", note="QatarEnergy投资者材料第13页列El Bunduq全田2024年平均原油产量；跨境资产仅列一次，不是阿联酋权益量。"),
    record("阿联酋", "Haliba", "哈利巴", "油田", 23.00, 53.80, value="10", metric_type="actual_output", unit="千桶/日", data_date="2019年6月初期投产口径", source="ADNOC Haliba", note="ADNOC Al Dhafra称2019年6月开始以10千桶/日生产；40千桶/日仅为目标产能，本值非当前实产。"),
    record("阿联酋", "Fateh", "法泰赫", "海上油田", 25.54, 54.29, source="Dubai Petroleum"),
    record("阿联酋", "South-West Fateh", "西南法泰赫", "海上油田", 25.45, 54.19, source="Dubai Petroleum"),
    record("阿联酋", "Falah", "法拉赫", "海上油田", 25.63, 54.21, source="Dubai Petroleum"),
    record("阿联酋", "Rashid", "拉希德", "海上油田", 25.45, 54.40, source="Dubai Petroleum"),
    record("阿联酋", "Jalilah", "贾利拉", "海上油田", 25.38, 54.34, source="Dubai Petroleum"),
    record("阿联酋", "Margham", "马尔格姆", "凝析油气田", 24.98, 55.61, source="Dubai Petroleum", note="撤回25千桶/日历史凝析油值：所引Dubai Petroleum资产页未提供该数字。"),
    record("阿联酋", "Bab Gas Cap", "巴布气顶项目", "天然气项目", 23.93, 53.79, value="1,500", metric_type="target_capacity", unit="百万标准立方英尺/日", data_date="2026-01-01", source="ADNOC Onshore", note="天然气项目。"),
    record("阿联酋", "Ruwais Diyab", "鲁韦斯迪亚布", "非常规气特许权", 24.15, 52.70, source="ADNOC Ghasha", note="特许权，不是单一油田。"),
    record("阿联酋", "Sajaa", "萨贾", "气／凝析油田", None, None, source="SNOC Upstream", note="沙迦SNOC列为既有油气资产；原油逐田日产量未披露。"),
    record("阿联酋", "Kahaif", "卡海夫", "气／凝析油田", None, None, source="SNOC Upstream", note="沙迦SNOC列为既有油气资产；原油逐田日产量未披露。"),
    record("阿联酋", "Moveyeid", "穆韦耶德", "气田／储气设施", None, None, status="成熟气田转为储气用途", source="SNOC Upstream", note="SNOC称其已从成熟生产田转型为储气设施；不填当期原油日产量。"),
    record("阿联酋", "Mahani", "马哈尼", "气／凝析油田", None, None, status="2020年发现；2021年运营中，当期待核", source="SNOC GHG 2021", note="SNOC的2021年温室气体报告列为其四座运营气田之一；不将井测试流量填为全田持续产量。"),
    record("阿联酋", "Hedebah", "赫德巴", "气／凝析油田", None, None, status="2024年发现；开发中", source="SNOC Upstream", note="SNOC将其列为新发现田；持续逐田产量未披露。"),
    record("阿联酋", "Saleh", "萨利赫", "海上气田", None, None, status="历史生产；当期状态待核", source="RAKGAS History", note="RAKGAS历史页面记载从哈伊马角近海Saleh田开采和处理，未披露当前逐田流量。"),
    record("阿联酋", "Umm Al Quwain", "乌姆盖万", "海上气田", None, None, status="历史生产；当期状态待核", source="RAKGAS History", note="RAKGAS历史页面记载2006—2008年处理该田来气；当前生产状态和逐田数值待核。"),

    # Iraq
    record("伊拉克", "Rumaila", "鲁迈拉", "油田", 30.08, 47.43, value="1,370", metric_type="actual_output", unit="千桶/日", data_date="2025年平均", source="Rumaila Operating Organisation", note="运营组织直报2025全年日均137万桶；不是当前瞬时日产量。"),
    record("伊拉克", "West Qurna-1", "西古尔纳一期", "油田", 30.77, 47.25, value="600", metric_type="actual_output", unit="千桶/日", data_date="2025-11-20", source="Iraqi News West Qurna-1", note="报道引用油田管理方称当日产量为600千桶/日；旧750千桶/日记录是产能，2026年实际日产量未核实。"),
    record("伊拉克", "West Qurna-2", "西古尔纳二期", "油田", 30.96, 47.31, value="400.1", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表58（PCLD）年产146,022,515桶÷365日=400.1千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Zubair", "祖拜尔", "油田", 30.20, 47.82, value="470.6", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表58（PCLD）年产171,760,022桶÷365日=470.6千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Majnoon", "马季努恩", "油田", 31.05, 47.72, value="176.0", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表58（PCLD）年产64,240,000桶÷365日=176.0千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Halfaya", "哈法亚", "油田", 31.58, 47.30, value="389.6", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表58（PCLD）年产142,213,694桶÷365日=389.6千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Gharraf", "加拉夫", "油田", 31.45, 46.78, value="130", metric_type="actual_output", unit="千桶/日", data_date="截至2022-04-20的运营资料", source="PETRONAS Gharraf", note="PETRONAS资料称该田平均约13万桶/日；网页给出2022-04-20累计出口基准日，属于历史资料。"),
    record("伊拉克", "Badra", "巴德拉", "油田", 33.03, 45.03, value="35.2", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表58（PCLD）年产12,857,981桶÷365日=35.2千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Ahdab", "阿赫达卜", "油田", 32.99, 44.63, value="49.2", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表58（PCLD）年产17,956,867桶÷365日=49.2千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "East Baghdad", "东巴格达", "油田", 33.45, 44.60, value="18.2", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表58（PCLD）年产6,630,000桶÷365日=18.2千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Nahr Umar", "纳赫尔乌马尔", "油田", 30.40, 47.72, source="Iraq EITI 2021", note="2026-09-30撤回原目录无原表支持的2021日产量；EITI 2021表58没有该田报送行。当前逐田实产未知。"),
    record("伊拉克", "Artawi", "阿尔塔维", "油田", 30.42, 47.91, value="16.7", metric_type="derived_daily_average", unit="千桶/日", data_date="2016年推算日均", status="EITI 2023列为非生产田；后续待核", source="Iraq EITI 2016", note="EITI 2016报告第75页Basra Oil Company逐田年产6,123,726桶÷366日=16.7千桶/日（四舍五入）；EITI 2023表17列非生产田，不能据历史值认定当前产量。"),
    record("伊拉克", "Nassiriya", "纳西里耶", "油田", 31.12, 46.27, source="Iraq EITI 2021", note="2026-09-30撤回原目录无原表支持的2021日产量；EITI 2021表58没有该田报送行。当前逐田实产未知。"),
    record("伊拉克", "Kirkuk", "基尔库克", "油田", 35.47, 44.39, source="EIA Iraq"),
    record("伊拉克", "Bai Hassan", "拜哈桑", "油田", 35.61, 44.40, value="133.3", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表57（North Oil Company）；年产48,672,087桶÷365日=133.3千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Jambur", "詹布尔", "油田", 35.31, 44.48, value="38.4", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表57（North Oil Company）；年产14,008,692桶÷365日=38.4千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Khabbaz", "哈巴兹", "油田", 35.52, 44.21, value="25.0", metric_type="derived_daily_average", unit="千桶/日", data_date="2021年推算日均", source="Iraq EITI 2021", note="EITI 2021 表57（North Oil Company）；年产9,139,429桶÷365日=25.0千桶/日（四舍五入）；历史均值，非当前日产量。"),
    record("伊拉克", "Qayyarah", "盖亚拉", "油田", 35.80, 43.31, source="EIA Iraq"),
    record("伊拉克", "Najma", "纳杰马", "油田", 35.91, 43.20, status="EITI 2023列为非生产田", source="Iraq EITI 2021", note="2026-09-30撤回原目录无原表支持的2021日产量；EITI 2021表58没有该田报送行。当前逐田实产未知。"),
    record("伊拉克", "Tawke", "陶凯", "油田（库区）", 37.02, 43.27, value="29.095", metric_type="actual_output", unit="千桶/日", data_date="2025年第四季度平均", source="DNO 2025 Results", note="DNO直报全田总产量；不是DNO的75%权益产量。"),
    record("伊拉克", "Peshkabir", "佩什卡比尔", "油田（库区）", 37.13, 43.47, value="48.173", metric_type="actual_output", unit="千桶/日", data_date="2025年第四季度平均", source="DNO 2025 Results", note="DNO直报全田总产量；不是DNO的75%权益产量。"),
    record("伊拉克", "Taq Taq", "塔克塔克", "油田（库区）", 35.91, 44.62, value="1.36", metric_type="actual_output", unit="千桶/日", data_date="2023年平均", status="Genel称2023-05-20起停产；后续待核", source="Genel Q1 2024", note="运营方直报2023年全田总产量1,360桶/日（含停产期的年度平均）；不是Genel权益产量，更非当前日产量。"),
    record("伊拉克", "Sarta", "萨尔塔", "油田（库区）", None, None, value="0.79", metric_type="actual_output", unit="千桶/日", data_date="2023年平均", status="Sarta PSC于2023-12-01终止", source="Genel Q1 2024", note="Genel直报2023年全资产总产量790桶/日；合同随后终止，不能当作现时生产。未核验单田点位。"),
    record("伊拉克", "Shaikan", "沙伊坎", "油田（库区）", 36.70, 43.33, value="14.6", metric_type="actual_output", unit="千桶/日", data_date="2026年上半年平均", source="Gulf Keystone H1 2026", note="GKP直报全田半年日均；期间有停产，8月恢复后流量与半年均值不同。"),
    record("伊拉克", "Atrush", "阿特鲁什", "油田（库区）", 37.08, 44.29, value="1.2", metric_type="actual_output", unit="千桶/日", data_date="2026年第二季度平均", source="ShaMaran Q2 2026", note="全田100%口径；季度多数时间停产，7月再次停产，不能视作当前日产量。"),
    record("伊拉克", "Sarsang", "萨尔桑格", "区块（两油田）", 37.12, 44.41, value="0.7", metric_type="actual_output", unit="千桶/日", data_date="2026年第二季度平均", source="ShaMaran Q2 2026", note="Sarsang区块全额口径，包含Swara Tika与East Swara Tika两田；季度多数时间停产，不能拆为单田或视作当前日产量。坐标为区块近似点。"),
    record("伊拉克", "Swara Tika", "斯瓦拉蒂卡", "油田（Sarsang区块）", None, None, status="运营方列为生产田；当期待核", source="HKN Sarsang", note="HKN称为Sarsang区块两座生产田之一；区块0.7千桶/日的历史季度均值不可拆分。"),
    record("伊拉克", "East Swara Tika", "东斯瓦拉蒂卡", "油田（Sarsang区块）", None, None, status="运营方列为生产田；当期待核", source="HKN Sarsang", note="HKN称为Sarsang区块两座生产田之一；区块0.7千桶/日的历史季度均值不可拆分。"),
    record("伊拉克", "Khurmala", "胡尔马拉", "油田（库区）", None, None, status="2025年官方列名；当期待核", source="Kurdistan Presidency 2025", note="库区政府2025年通告明确称其为油田；未找到同田公开日均实产，坐标不臆定。"),
    record("伊拉克", "Baeshiqa", "拜什卡", "区块（试井项目）", None, None, status="DNO称2025年未生产；2024年只有试井", source="DNO Kurdistan 2025", note="DNO称2024年约5桶油当量/日来自井测试，2025年未生产；试井油当量不能填作持续区块原油日产量。"),
    record("伊拉克", "Eridu (Block 10)", "埃里杜／第十区块", "发现油田／区块", None, None, status="EITI 2023列为非生产田；后续待核", source="Iraq EITI 2023", note="EITI 2023报告表16将Eridu（Block 10）列在Dhi Qar非生产油田栏；未披露可核验商业持续日产量。"),

    record("伊拉克", "Faihaa", "费哈", "油气田", 30.7253, 47.7629, value=">100", metric_type="actual_output", unit="千桶/日", data_date="2025-09-25（报告下限）", status="运营", source="Shafaq News Faihaa", note="伊拉克石油部长称该田当日产量超过10万桶；该数为公开下限，不是精确值，也不代表当前日产量。"),
    record("伊拉克", "Fakkah", "法卡（福基）", "油田", 32.135, 47.52, metric_type="undisclosed", status="运营", source="GEM Fakkah", note="GEM列为运营油田，亦称Fauqi；未找到可核验的单田日产量。"),
    record("伊拉克", "Bazerkan", "巴泽尔坎", "油田", 31.936, 47.372, metric_type="undisclosed", status="运营", source="GEM Bazerkan", note="GEM列为运营油田，亦称Buzurgan；未找到可核验的单田日产量。"),
    record("伊拉克", "Abu Gharb", "阿布加尔卜", "油田", 32.365, 47.306, status="运营", source="GEM Abu Gharb", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊拉克", "Luhais", "卢海斯", "油田", 29.904, 46.952, value="89.2", metric_type="derived_daily_average", unit="千桶/日", data_date="2016年推算日均", status="EITI 2023列为生产田；当期数值待核", source="Iraq EITI 2016", note="EITI 2016报告第75页Basra Oil Company逐田年产32,631,608桶÷366日=89.2千桶/日（四舍五入）；EITI 2023表17列为生产田，但未给该田2023实产。"),
    record("伊拉克", "Subba", "苏巴", "油田", 30.258, 46.829, status="运营", source="Iraq EITI 2021", note="2026-09-30撤回原目录无原表支持的2021日产量；EITI 2021表58没有该田报送行。当前逐田实产未知。"),
    record("伊拉克", "Tuba", "图巴", "油气田", 30.4036, 47.4977, value="36.2", metric_type="derived_daily_average", unit="千桶/日", data_date="2016年推算日均", status="EITI 2023列为生产田；当期数值待核", source="Iraq EITI 2016", note="EITI 2016报告第75页Basra Oil Company逐田年产13,262,897桶÷366日=36.2千桶/日（四舍五入）；EITI 2023表17列为生产田但未给该田实产。"),

    record("伊拉克", "Ajil", "阿吉勒", "油田", None, None, source="Iraq EITI 2021", note="EITI 2021表57 NOC年产2,167,278桶；表58没有Ajil行，不存在该田两表冲突。"),
    record("伊拉克", "Ain Zalah", "艾因扎拉", "油田", None, None, source="Iraq EITI 2021", note="EITI 2021表57列为产油田；无近期可核验逐田日产量。"),
    record("伊拉克", "Batmah", "巴特马", "油田", None, None, source="Iraq EITI 2021", note="EITI 2021表57列为产油田；无近期可核验逐田日产量。"),
    record("伊拉克", "Hamrin", "哈姆林", "油田", None, None, source="Iraq EITI 2021", note="EITI 2021表58列为产油田；逐田当期日产量未披露。"),
    record("伊拉克", "Naft Khana", "纳夫特哈纳", "油田", None, None, status="EITI 2023列为生产田；当期数值待核", source="Iraq EITI 2023", note="EITI 2023报告表14列为Midland Oil Company生产田；报告的公司产量不可分配到该田。"),
    record("伊拉克", "Amara", "阿马拉", "油田", None, None, status="EITI 2023列为生产田；当期数值待核", source="Iraq EITI 2023", note="EITI 2023报告表15列为Maysan Oil Company生产田；公司合计量不可分配到该田。"),
    record("伊拉克", "Noor", "努尔", "油田", None, None, status="EITI 2023列为生产田；当期数值待核", source="Iraq EITI 2023", note="EITI 2023报告表15列为Maysan Oil Company生产田；公司合计量不可分配到该田。"),
    record("伊拉克", "Safiya", "萨菲亚", "油田", None, None, status="EITI 2023列为生产田；当期数值待核", source="Iraq EITI 2023", note="EITI 2023报告表13列为North Oil Company生产田；无可核验逐田日产量。"),

    # Iran
    record("伊朗", "Ahvaz", "阿瓦士", "油田", 31.32, 48.68, source="EIA Iran"),
    record("伊朗", "Marun", "马伦", "油田", 31.19, 49.08, source="GEM Marun", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Aghajari", "阿加贾里", "油田", 30.70, 49.83, source="GEM Aghajari", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Gachsaran", "加奇萨兰", "油田", 30.36, 50.80, source="GEM Gachsaran", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Reg-e-Safid", "雷格萨菲德", "油田", 31.03, 49.31, source="EIA Iran"),
    record("伊朗", "South Azadegan", "南阿扎德甘", "油田", 30.06, 48.23, source="GEM South Azadegan", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "North Azadegan", "北阿扎德甘", "油田", 30.27, 48.25, value="75", metric_type="actual_output", unit="千桶/日", data_date="2019-11-25", source="Trend North Azadegan", note="Trend报道引用伊朗方面消息称日产量75千桶；这是2019年现场产量快照，不代表当前产量。"),
    record("伊朗", "Yadavaran", "雅达瓦兰", "油田", 31.03, 48.16, source="EIA Iran"),
    record("伊朗", "North Yaran", "北亚兰", "油田", 30.81, 48.14, source="EIA Iran"),
    record("伊朗", "South Yaran", "南亚兰", "油田", 30.68, 48.13, source="EIA Iran"),
    record("伊朗", "Azar", "阿扎尔", "油田", 33.08, 46.29, source="EIA Iran"),
    record("伊朗", "Darkhovin", "达尔霍温", "油田", 30.70, 48.48, source="EIA Iran"),
    record("伊朗", "Hendijan", "亨迪詹", "海上油田", 30.24, 49.70, source="EIA Iran"),
    record("伊朗", "Doroud", "多鲁德", "海上油田", 26.06, 53.04, source="EIA Iran"),
    record("伊朗", "Foroozan", "福鲁赞", "海上油田", 26.02, 52.45, source="EIA Iran"),
    record("伊朗", "Soroush", "苏鲁什", "海上油田", 29.70, 50.12, source="EIA Iran"),
    record("伊朗", "Nowruz", "诺鲁兹", "海上油田", 29.35, 50.20, source="EIA Iran"),
    record("伊朗", "Salman", "萨尔曼", "海上油气田", 25.52, 53.39, source="EIA Iran"),

    record("伊朗", "Bibi Hakimeh", "比比哈基梅", "油田", 29.91, 50.46, status="运营", source="GEM Bibi Hakimeh", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Karanj", "卡兰吉", "油田", 30.9902, 49.8602, status="运营", source="GEM Karanj", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Abuzar", "阿布扎尔", "海上油田", 29.292, 49.532, status="运营", source="GEM Abuzar", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Mansouri", "曼苏里", "油田", 30.9289, 48.828, status="运营", source="GEM Mansouri", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Sepehr-Jufair", "塞佩赫尔—朱费尔", "油田项目群", 31.298, 48.059, status="运营", source="GEM Sepehr-Jufair", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Parsi", "帕西", "油田", 31.0718, 49.9237, metric_type="undisclosed", status="运营", source="GEM Parsi", note="GEM列为运营油田，属于Parsi-Paranj开发项目；项目合计量未分配给单一油田，故单田日产量留空。"),
    record("伊朗", "Bahregansar", "巴赫雷甘萨尔", "海上油田", 29.916667, 49.7, metric_type="undisclosed", status="运营", source="GEM Bahregansar", note="GEM列为运营海上油田但未给坐标；地图点位取NGA地名数据库油田点（29.916667, 49.7）作近似位置。未找到可核验的单田日产量。"),
    record("伊朗", "Sirri E", "锡里E", "海上油气田", 25.751, 54.632, status="运营", source="GEM Sirri E", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("伊朗", "Masjed Soleyman", "马斯杰德苏莱曼", "油田", 31.9325, 49.3105, status="运营", source="GEM Masjed Soleyman", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),

    # 公开地图中的位置为近似中心点，二手名录仅用于确认名称和位置，不据此填写未经核实的实产。
    record("伊朗", "Pazanan", "帕扎南", "油田", 30.4532, 50.1354, source="GEM Pazanan", note="公开资产名录；逐田持续日产量未核验。"),
    record("伊朗", "Kupal", "库帕尔", "油田", 31.3118, 49.3203, source="GEM Kupal", note="公开资产名录；逐田持续日产量未核验。"),
    record("伊朗", "Dehloran", "德赫洛兰", "油田", 32.5516, 47.1077, source="GEM Dehloran", note="公开资产名录；逐田持续日产量未核验。"),
    record("伊朗", "Paranj", "帕兰吉", "油田", 30.95, 49.85, source="GEM Paranj", note="与Parsi同属开发项目；不拆分项目合计产量。"),
    record("伊朗", "Nargesi", "纳尔格西", "油田", 29.4742, 51.2602, source="GEM Nargesi", note="公开资产名录；逐田持续日产量未核验。"),

    record("伊朗", "Hengam", "亨加姆", "跨境海上油田（伊朗侧）", None, None, value="7", metric_type="actual_output", unit="千桶/日", data_date="2010-08-24", source="SHANA Hengam 2010", note="伊朗石油部新闻报道称该日伊朗侧产量达到7,000桶/日；极旧历史快照，非2026年或伊朗—阿曼全田产量。阿曼侧与West Bukha相关。"),
    # EIA 2024列名作为伴生气收集项目的供气油田，不据项目处理能力反推油田原油量。
    record("伊朗", "Band-e-Karkheh", "班德卡尔赫", "油田", None, None, status="EIA 2024具名；当期生产状态待核", source="EIA Iran", note="EIA报告表2将其列为NGL 3200拟收集伴生气的油田；未披露该田原油日产量。"),
    record("伊朗", "West Paydar", "西帕伊达尔", "油田", None, None, status="EIA 2024具名；当期生产状态待核", source="EIA Iran", note="EIA报告表2列为NGL 3100拟接收伴生气的油田；非逐田原油数据。"),
    record("伊朗", "Chehsmeh-Khosh", "切什梅霍什", "油田", None, None, status="EIA 2024具名；当期生产状态待核", source="EIA Iran", note="按EIA报告表2英文拼法登记；伴生气处理计划不是该田原油日产量。"),
    record("伊朗", "Danan", "达南", "油田", None, None, status="EIA 2024具名；当期生产状态待核", source="EIA Iran", note="EIA报告表2列名；未披露该田原油日产量。"),
    record("伊朗", "Paydar", "帕伊达尔", "油田", None, None, status="EIA 2024具名；当期生产状态待核", source="EIA Iran", note="EIA报告表2与West Paydar分别列名；无可靠逐田日产量。"),
    record("伊朗", "Changuleh", "昌古莱", "油田", None, None, status="EIA 2024具名；当期生产状态待核", source="EIA Iran", note="EIA报告表2列名；不把伴生气收集设施容量当作原油产量。"),
    record("伊朗", "Dalpari", "达尔帕里", "油田", None, None, status="EIA 2024具名；当期生产状态待核", source="EIA Iran", note="EIA报告表2列名；逐田原油日产量未核实。"),
    record("伊朗", "South Pars", "南帕尔斯", "海上气／凝析油田", None, None, status="已开发；原油逐田值不适用", source="EIA Iran", note="EIA称为伊朗最大非伴生气田；与卡塔尔North Field同一跨境地质构造的伊朗侧，天然气和凝析油数据不作为原油实产。"),

    # Kuwait
    record("科威特", "Burgan", "布尔干", "油田", 29.05, 47.91, source="KOC / KPC"),
    record("科威特", "Magwa", "马格瓦", "油田", 29.17, 47.92, source="KOC / KPC"),
    record("科威特", "Ahmadi", "艾哈迈迪", "油田", 28.99, 48.08, source="KOC / KPC"),
    record("科威特", "Raudhatain", "劳达泰因", "油田", 30.20, 47.66, source="KOC / KPC"),
    record("科威特", "Sabriya", "萨布里亚", "油田", 30.28, 47.74, source="KOC / KPC"),
    record("科威特", "Bahra", "巴赫拉", "油田", 29.95, 47.46, source="KOC / KPC"),
    record("科威特", "Ratqa", "拉特卡", "油田", 30.13, 47.59, source="KOC / KPC"),
    record("科威特", "Umm Niqa", "乌姆尼卡", "重油田", 30.10, 47.68, value="22.14", metric_type="actual_output", unit="千桶/日", data_date="FY2023/24（日点未注明）", source="KOC Annual Report 2023-24", note="KOC年报称FY2023/24在Umm Niqa实现22,140桶/日；报告未将其定义为全年平均。"),
    record("科威特", "South Ratqa", "南拉特卡", "重油田", 30.02, 47.70, source="KOC / KPC"),
    record("科威特", "Minagish", "米纳吉什", "油田", 29.00, 46.38, source="KOC / KPC"),
    record("科威特", "Umm Gudair", "乌姆古代尔", "油田", 28.70, 46.52, source="KOC / KPC"),
    record("科威特", "Abdali", "阿卜达利", "油田", 30.03, 47.93, source="KOC / KPC"),
    record("科威特", "Wafra", "瓦夫拉", "跨境油田", 28.72, 47.90, source="KOC / KPC", note="沙特—科威特中立区共享资产。"),
    record("科威特", "Khafji", "哈夫吉", "跨境海上油田", 28.52, 48.42, source="KOC / KPC", note="沙特—科威特中立区共享资产。"),
    record("科威特", "Nokhetha", "诺赫萨", "发现海上油田", None, None, status="2024年发现；商业生产未证实", source="KOC Annual Report 2024-25", note="KOC年报的2,800桶/日是Nokhetha-1勘探井测试流量，不能填作全田持续日产量。"),
    record("科威特", "Julaiah", "朱莱亚", "发现海上油田", None, None, status="2025年发现；商业生产未证实", source="KOC Annual Report 2024-25", note="KOC年报仅披露勘探井测试与资源量，未披露全田持续日产量。"),
    record("科威特", "Mutriba", "穆特里巴", "油田", None, None, status="2025-06-15商业投产", source="KOC Mutriba", note="KOC确认轻质油商业生产；公开报道未给可核验的全田持续日产量，井测试量不作替代。"),
    record("科威特", "Shaham", "沙哈姆", "勘探油田", None, None, status="FY2024/25勘探发现；商业产量未核", source="KOC Annual Report 2024-25", note="KOC年报第30—31页称北科威特Shaham勘探田发现Zubair砂岩油藏；未给商业持续产量。"),
    record("科威特", "Kra-al-Maru", "克拉马鲁", "油田", None, None, status="FY2024/25加深井发现新储层", source="KOC Annual Report 2024-25", note="KOC年报第30—31页称在既有Kra-al-Maru油田发现Marrat储层；该发现不是全田日产量。"),

    # Qatar
    record("卡塔尔", "Al Shaheen", "阿尔沙欣", "海上油田", 26.51, 51.92, value="280.1", metric_type="actual_output", unit="千桶/日", data_date="2024年平均", source="QatarEnergy", note="QatarEnergy官方投资者演示文稿列示的2024年平均原油产量；来源直报。"),
    record("卡塔尔", "Dukhan", "杜汉", "油气田", 25.42, 50.79, value="176.4", metric_type="actual_output", unit="千桶/日", data_date="2024年平均", source="QatarEnergy", note="QatarEnergy官方投资者演示文稿列示的2024年平均原油产量；来源直报。"),
    record("卡塔尔", "Al-Rayyan", "阿尔拉扬", "海上油田", 25.98, 51.33, value="3.6", metric_type="actual_output", unit="千桶/日", data_date="2024年平均", source="QatarEnergy", note="QatarEnergy官方投资者演示文稿列示的2024年平均原油产量；来源直报。"),
    record("卡塔尔", "Al-Khaleej", "阿尔哈利杰", "海上油田", 25.70, 51.48, value="23.4", metric_type="actual_output", unit="千桶/日", data_date="2024年平均", source="QatarEnergy", note="QatarEnergy官方投资者演示文稿列示的2024年平均原油产量；来源直报。"),
    record("卡塔尔", "Idd El-Sharqi", "伊德谢尔基", "海上油田", 25.59, 51.31, value="54.4", metric_type="actual_output", unit="千桶/日", data_date="2024年平均", source="QatarEnergy", note="QatarEnergy官方投资者演示文稿列示的2024年平均原油产量；来源直报。"),
    record("卡塔尔", "Karkara", "卡尔卡拉", "海上油田", 25.46, 51.33, source="QatarEnergy"),
    record("卡塔尔", "Maydan Mahzam", "迈丹马赫赞", "海上油田", 25.20, 51.20, value="16.2", metric_type="actual_output", unit="千桶/日", data_date="2024年平均", source="QatarEnergy", note="QatarEnergy官方投资者演示文稿列示的2024年平均原油产量；来源直报。"),
    record("卡塔尔", "Bul Hanine", "布尔哈宁", "海上油田", 25.06, 51.14, value="35.1", metric_type="actual_output", unit="千桶/日", data_date="2024年平均", source="QatarEnergy", note="QatarEnergy官方投资者演示文稿列示的2024年平均原油产量；来源直报。"),
    record("卡塔尔", "Al-Murjan", "阿尔穆尔詹", "海上油田", None, None, source="QatarEnergy E&P", note="卡塔尔能源称该田通过Al-Rayyan平台生产；没有单田产量，不把Al-Rayyan平台数值分摊。"),
    record("卡塔尔", "North Field", "北方气田", "气田", 26.62, 51.45, source="QatarEnergy", note="气田，不与原油日产量比较。"),
    record("卡塔尔", "A-Structures (A-North / A-South)", "A构造（A北／A南）", "海上油田群（两个小油田）", None, None, status="2022年续签五年开发生产协议（至2027年）", source="Qatar News Agency A-Structures", note="QNA称A-North和A-South于1971年发现，A-Structures与Al-Karkara自2006年3月投产；报道的3,350万桶是三田合计累计原油，不能分配给A-Structures。单田产量及坐标未披露。"),
    record("卡塔尔", "A-North", "A北", "海上油田", None, None, status="A-Structures组成油田；单田状态随油田群协议", source="Qatar News Agency A-Structures", note="QNA明确列为A-Structures两座小油田之一；油田群与Al-Karkara的累计产量不能分配给该田。"),
    record("卡塔尔", "A-South", "A南", "海上油田", None, None, status="A-Structures组成油田；单田状态随油田群协议", source="Qatar News Agency A-Structures", note="QNA明确列为A-Structures两座小油田之一；油田群与Al-Karkara的累计产量不能分配给该田。"),

    # Oman
    record("阿曼", "Mukhaizna", "穆凯兹奈", "油田", 19.34, 56.47, source="Occidental Oman", note="运营商确认油田运营及累计产量，但未找到可核验的2023年单田8万桶/日实产；撤回该值。"),
    record("阿曼", "Yibal", "伊巴尔", "油田", 22.26, 56.15, source="GEM Yibal", note="原列年度数值的原始引文未证实是该年度实际产油总量；撤回据此换算的推算日均。逐田实产待核。"),
    record("阿曼", "Natih", "纳蒂赫", "油田", 22.48, 56.33, source="PDO"),
    record("阿曼", "Fahud", "法胡德", "油田", 22.35, 56.50, source="PDO"),
    record("阿曼", "Qarn Alam", "卡恩阿拉姆", "油田", 22.55, 57.07, source="PDO"),
    record("阿曼", "Marmul", "马尔穆勒", "油田", 18.12, 55.22, source="PDO"),
    record("阿曼", "Nimr", "尼姆尔", "油田", 18.76, 55.74, source="PDO"),
    record("阿曼", "Lekhwair", "莱赫韦尔", "油田", 20.59, 57.14, source="PDO"),
    record("阿曼", "Bahja", "巴赫贾", "油田", 20.96, 56.80, source="PDO"),
    record("阿曼", "Harweel", "哈维尔", "油田群", 18.08, 55.62, source="PDO"),
    record("阿曼", "Amal", "阿迈勒", "油田", 18.48, 55.72, source="PDO"),
    record("阿曼", "Zalzala", "扎尔扎拉", "油田（Harweel资产）", None, None, source="PDO Sustainability 2024", note="PDO报告第60页列Harweel 2AB项目位于Zalzala田；注气与增采累计量不是全田日均原油。"),
    record("阿曼", "Haima West", "海马西", "油田（Marmul集群）", None, None, source="PDO Sustainability 2024", note="PDO报告第60页列名；聚合物驱项目预期增采量不能转换为现时单田日产量。"),
    record("阿曼", "Al Noor", "努尔", "油田（Nimr资产）", None, None, source="PDO Sustainability 2024", note="PDO报告列Al Noor三期项目；项目增采资源量不是单田实产。"),
    record("阿曼", "Nimr-A", "尼姆尔A", "油田（Nimr资产）", None, None, source="PDO Sustainability 2024", note="PDO明确称Nimr-A油田；2024年聚合物驱投资决定的预期增采量不是已实现日产量。"),
    record("阿曼", "Nimr-E", "尼姆尔E", "油田（Nimr资产）", None, None, source="PDO Sustainability 2024", note="PDO明确称Nimr-E油田；不把Nimr资产合计量分配给该田。"),

    record("阿曼", "Budour Northeast", "布杜尔东北", "发现油田", None, None, status="发现／开发状态待核", source="PDO", note="PDO历史页面确认发现，尚无可核验的持续逐田日产量。"),

    record("阿曼", "Block 50 (Masirah)", "50区块（马西拉）", "海上油气区块", None, None, status="区块内Yumna田生产中", source="Masirah Oil Yumna", note="区块层级日产量未单独披露；Yumna单田数据不反推为整个区块产量。"),
    record("阿曼", "Yumna", "尤姆纳", "海上油田", 19.9841, 58.546, value="742", metric_type="actual_output", unit="桶/日", data_date="2026年3月平均（31天生产期）", status="生产中", source="Masirah Oil Yumna", note="运营方公告称31天生产期内全田总产量日均742桶；Block 50运营方持有100%权益。"),
    record("阿曼", "Bisat", "比萨特", "油田", 21.178, 55.8542, metric_type="undisclosed", status="运营", source="OQ / GEM Bisat", note="OQ于2023年公告比萨特油田原油处理设施投产；GEM列为运营油田，逐田日产量未披露。坐标为公开地图资料的近似点。"),
    record("阿曼", "Block 5 (Daleel)", "5区块（Daleel）", "油气区块", None, None, value="50", metric_type="actual_output", unit="千桶/日", data_date="运营商网页未注明观察期（2026-09-28核对）", status="运营", source="Daleel Petroleum", note="运营商称Block 5日均产量已从2002年的约5千桶/日提高至50千桶/日；这是区块多田合计，不能分配给Daleel、Shadi、Bushra、Mazoon、Furat或Thahab。"),
    record("阿曼", "Daleel", "达利勒", "油田", 22.7241, 55.976, status="运营", source="Daleel Petroleum", note="运营商披露Block 5共有五个主要油田；区块约5万桶/日不能分配给单田。"),
    record("阿曼", "Shadi", "沙迪", "油田", None, None, status="运营", source="Daleel Petroleum", note="Block 5油田；仅有区块合计产量，单田和坐标未核验。"),
    record("阿曼", "Bushra", "布什拉", "油田", None, None, status="运营", source="Daleel Petroleum", note="Block 5油田；仅有区块合计产量，单田和坐标未核验。"),
    record("阿曼", "Mazoon", "马祖恩", "油田", None, None, status="运营", source="Daleel Petroleum", note="Block 5油田；仅有区块合计产量，单田和坐标未核验。"),
    record("阿曼", "Furat", "富拉特", "油田", None, None, status="运营", source="Daleel Petroleum", note="Block 5油田；仅有区块合计产量，单田和坐标未核验。"),
    record("阿曼", "Thahab", "扎哈卜", "油田（Block 5）", None, None, status="2023年运营商列为开采田", source="Daleel 2023", note="Daleel称近年开采Thahab；其约5万桶/日为Block 5多田总量，不分摊。"),
    record("阿曼", "Block 9 (Oman)", "9区块（阿曼）", "油气区块", None, None, status="运营商公开命名区块；区块日产量未核", source="Occidental Oman", note="包含Safah和Wadi Latham等资产；没有用公司或区块组合数据估算单田产量。"),
    record("阿曼", "Block 27 (Oman)", "27区块（阿曼）", "油气区块", None, None, status="运营商公开命名区块；区块日产量未核", source="Occidental Oman", note="Khamilah所属区块；未披露可核验区块或单田日产量。"),
    record("阿曼", "Safah", "萨法", "油田", None, None, status="运营", source="Occidental Oman", note="Occidental披露Block 9的主要油田；未披露可核验单田日产量。"),
    record("阿曼", "Wadi Latham", "瓦迪拉萨姆", "油田", None, None, status="运营", source="Occidental Oman", note="Occidental披露Block 9的主要油田；未披露可核验单田日产量。"),
    record("阿曼", "Khamilah", "哈米拉", "油田", None, None, status="运营", source="Occidental Oman", note="Occidental披露Block 27油田；未披露可核验单田日产量。"),
    record("阿曼", "Wadi Aswad North", "瓦迪阿斯瓦德北", "发现油田", None, None, status="运营商列为发现；当期生产未核", source="Occidental Oman", note="Occidental列为阿曼北部发现油田；未披露可核验持续逐田日产量。"),
    record("阿曼", "Safah North B", "萨法北B", "发现油田", None, None, status="运营商列为发现；当期生产未核", source="Occidental Oman", note="Occidental列为阿曼北部发现油田；不同于Safah，未披露单田日产量。"),
    record("阿曼", "Block 8 (Oman)", "8区块（阿曼）", "海上油气区块", None, None, status="运营", source="OQEP Operations", note="包含West Bukha与Bukha；公开区块合计不拆给单田。"),
    record("阿曼", "Block 7 (Oman)", "7区块（阿曼）", "油气区块", None, None, status="公开资料列名；区块状态待核", source="OQEP Operations", note="Sahma所属区块；未披露可核验区块日产量。"),
    record("阿曼", "Block 60 (Oman)", "60区块（阿曼）", "油气区块", None, None, status="运营", source="OQEP Operations", note="Abu Butabul所属区块；油当量或区块合计不分配给单田。"),
    record("阿曼", "Block 61 (Oman)", "61区块（阿曼）", "气区块", None, None, status="运营", source="OQEP Operations", note="包含Khazzan与Ghazeer阶段；天然气或油当量指标不作为原油日产量。"),
    record("阿曼", "West Bukha", "西布哈", "跨境海上油田", None, None, status="运营", source="OQEP Operations", note="OQEP列为Block 8两座生产田之一；与伊朗Hengam同属跨境地质结构，未将区块合计拆为单田产量。"),
    record("阿曼", "Bukha", "布哈", "海上气田", None, None, status="运营", source="OQEP Operations", note="OQEP列为Block 8两座生产田之一；不将区块或天然气量充作单田原油日产量。"),
    record("阿曼", "Sahma", "萨赫马", "油田", None, None, status="公开列为生产田", source="OQEP Operations", note="OQEP Block 48说明列为相邻Block 7生产油田；未披露单田产量。"),
    record("阿曼", "Abu Butabul", "阿布布塔布尔", "气／凝析油田", None, None, source="OQEP Operations", note="OQEP确认Block 60油气田名称；不把Block 60油当量合计归给该田。"),
    record("阿曼", "Khazzan", "哈赞", "气田", None, None, source="OQEP Operations", note="OQEP称为Block 61阶段之一；逐田原油日产量不适用。"),
    record("阿曼", "Ghazeer", "加泽尔", "气田", None, None, source="OQEP Operations", note="OQEP称为Block 61阶段之一；逐田原油日产量不适用。"),

    # Bahrain and Yemen
    record("巴林", "Bahrain Field (Awali)", "巴林／阿瓦利油田", "油田", 26.07, 50.55, value="39.5", metric_type="actual_output", unit="千桶/日", data_date="2022年平均", source="UNFCCC Bahrain BTR", note="UNFCCC BTR列示2022年原油与凝析油年均产量39.5千桶/日。"),
    record("巴林", "Abu Safah", "阿布萨法", "跨境海上油田", 26.02, 50.61, value="300", metric_type="capacity", unit="千桶/日", data_date="网页未注明基准日（2026-09-27核对）", source="Bapco Abu Safah", note="Bapco明确为全油田30万桶/日产能，非实产；巴林与沙特权益各50%，不可按权益数推断实际日产量。"),
    record("也门", "Block 14 (Masila)", "14区块（马西拉）", "油气区块", 14.47, 49.54, source="Yemen Ministry of Oil", note="按生产区块记录；冲突环境下缺少可靠连续区块日产量，不能作为单一油田统计。"),
    record("也门", "Block 10 (East Shabwa)", "10区块（东舍卜瓦）", "油气区块", 14.55, 47.54, source="Yemen Ministry of Oil", note="按生产区块记录；不是单一油田。"),
    record("也门", "Block 32 (Hawareem)", "32区块（哈瓦里姆）", "油气区块", 14.32, 48.96, source="Yemen Ministry of Oil", note="按生产区块记录；PEPA计划列Tasour与Godah为区块内油田。"),
    record("也门", "Tasour", "塔苏尔", "油田", None, None, status="PEPA 2012计划列为Block 32油田；当前状态未核", source="Yemen PEPA Production Plan", note="PEPA计划提及该田生产优化；没有可核验单田日产量。"),
    record("也门", "Godah", "戈达", "油田", None, None, status="PEPA 2012计划列为Block 32油田；当前状态未核", source="Yemen PEPA Production Plan", note="PEPA计划提及该田生产优化；没有可核验单田日产量。"),
    record("也门", "Block 18 (Marib)", "18区块（马里卜）", "油气区块", None, None, status="EIA记载2018年恢复生产；当前状态未核", source="Yemen EIA", note="区块层级状态；不能下推为区块内每一油田的当期产量。"),
    record("也门", "Alif", "阿利夫", "油田", 15.35, 45.05, source="Yemen Ministry of Oil", note="Block 18组成油田；区块层级数据不分配给该田。"),
    record("也门", "Block 5 (Jannah)", "5区块（詹纳）", "油气区块", 15.24, 45.16, value="50", metric_type="actual_output", unit="千桶/日", data_date="截至2007-01的历史平均", status="历史生产区块；当前状态未核", source="Yemen PEPA Block 5", note="PEPA称该区块含5个油田，历史平均产量50千桶/日；这是旧区块合计，不能视为当前产量或分配给区块内单田。"),
    record("也门", "Block S2 (Uqlah)", "S2区块（乌克拉）", "油气区块", None, None, status="PEPA列为生产计划区块；当前状态未核", source="Yemen PEPA Production Plan", note="Habban所属区块；未取得可靠的当前区块日产量。"),
    record("也门", "Habban", "哈班", "油田", None, None, status="2018年有原油出口记录；当前生产状态未核", source="Yemen EIA", note="EIA记载OMV在2018年从S2区块Habban田出口原油；PEPA计划提及Habban CPF。历史出口记录不代表当前持续日产量。"),
    record("也门", "Block 9 (Malik)", "9区块（马利克）", "油气区块", None, None, status="EIA记载Medco于2019年恢复区块作业；当前状态未核", source="Yemen EIA", note="区块级生产恢复信息；不能据此认定区块内每一田当期均在产或将区块产量分配给单田。"),
    record("也门", "Hiswah (Haswa)", "希斯瓦（Haswa）", "油田／Block 9", None, None, status="PEPA 2012计划列名；现行生产状态未核", source="Yemen PEPA Production Plan", note="PEPA 2012计划提到Hiswah田CPU建设，评估清单又作Haswa；按同一田名变体合并登记。区块重启不等于该田有已核实的单田产量。"),
    record("也门", "Alroidhat (Al-Rowedhat)", "阿尔罗伊达特", "油田／Block 9", None, None, status="PEPA 2012计划列名；现行生产状态未核", source="Yemen PEPA Production Plan", note="PEPA 2012计划提到Alroidhat输油管线建设，评估清单作AL-rowedhat；保留原拼法变体，未取得单田产量。"),
    record("也门", "Qarn Qeamah", "卡恩·基阿马", "油田／Block 9", None, None, status="PEPA 2012列为评估对象；商业生产未核", source="Yemen PEPA Production Plan", note="PEPA计划列入Block 9地质评估研究；名称已公开，但这不足以证明当前商业生产或单田产量。"),

    # Syria, Israel and Turkey
    record("叙利亚", "Rmeilan Sector One", "鲁迈兰第一作业区", "油田群／作业区", None, None, value="70–80", metric_type="actual_output", unit="千桶/日", data_date="2026-02-11采访时点", status="采访时点生产；之后控制与产量可能变化", source="Rudaw Rmeilan Sector One", note="负责人称Sector One含Rmeilan、Suwaydiya、Qarachok、Hamza、Alyan、Sazabeh、Ode和Tigris八田；70–80千桶/日为作业区合计，不能分配给单田。另称产能110千桶/日。"),
    record("叙利亚", "Al-Omar", "奥马尔", "油田", 35.07, 40.60, value="15", metric_type="actual_output", unit="千桶/日", data_date="2026-02-22", source="Le Monde Al-Omar 2026", note="记者实地采访运营主任称日产1.5万桶；2026-01-19较早报道约5千桶/日，修复期波动很大。"),
    record("叙利亚", "Al-Tanak", "塔纳克", "油田", 35.10, 40.34, source="Syria public reporting"),
    record("叙利亚", "Al-Jafra", "贾夫拉", "油田", 35.05, 40.47, source="Syria public reporting"),
    record("叙利亚", "Al-Ward", "瓦尔德", "油田", 35.20, 40.55, source="Syria public reporting"),
    record("叙利亚", "Al-Taym", "泰姆", "油田", 35.23, 40.26, source="Syria public reporting"),
    record("叙利亚", "Rmeilan", "鲁迈兰", "油田", 37.04, 42.03, source="Syria public reporting"),
    record("叙利亚", "Suwaydiya", "苏韦迪耶", "油田", 37.07, 41.93, source="Syria public reporting"),
    record("叙利亚", "Qarachok", "卡拉乔克", "油田（Rmeilan Sector One）", None, None, status="2026年Rudaw列为Sector One油田；单田状态待核", source="Rudaw Rmeilan Sector One", note="Rudaw列为鲁迈兰Sector One八个油田之一；报道中的区域日产量与产能是全区合计，不拆给单田。"),
    record("叙利亚", "Hamza", "哈姆扎", "油田（Rmeilan Sector One）", None, None, status="2026年Rudaw列为Sector One油田；单田状态待核", source="Rudaw Rmeilan Sector One", note="Rudaw列为鲁迈兰Sector One油田；报道中的区域总产能及当期产量不能分配给单田。"),
    record("叙利亚", "Alyan", "阿利扬", "油田（Rmeilan Sector One）", None, None, status="2026年Rudaw列为Sector One油田；单田状态待核", source="Rudaw Rmeilan Sector One", note="Rudaw列为鲁迈兰Sector One油田；报道中的区域总产能及当期产量不能分配给单田。"),
    record("叙利亚", "Sazabeh", "萨扎贝", "油田（Rmeilan Sector One）", None, None, status="2026年Rudaw列为Sector One油田；单田状态待核", source="Rudaw Rmeilan Sector One", note="Rudaw列为鲁迈兰Sector One油田；报道中的区域总产能及当期产量不能分配给单田。"),
    record("叙利亚", "Ode", "奥德", "油田（Rmeilan Sector One）", None, None, status="2026年Rudaw列为Sector One油田；单田状态待核", source="Rudaw Rmeilan Sector One", note="Rudaw列为鲁迈兰Sector One油田；报道中的区域总产能及当期产量不能分配给单田。"),
    record("叙利亚", "Tigris", "底格里斯", "油田（Rmeilan Sector One）", None, None, status="2026年Rudaw列为Sector One油田；单田状态待核", source="Rudaw Rmeilan Sector One", note="Rudaw列为鲁迈兰Sector One油田；报道中的区域总产能及当期产量不能分配给单田。"),
    record("以色列", "Heletz", "赫莱兹", "油田", 31.57, 34.62, source="Israel Ministry of Energy", note="当前实际产量和停产状态未获可靠公开确认。"),
    record("以色列", "Meged", "梅格德", "油田", 32.28, 35.03, source="Israel Ministry of Energy"),
    record("以色列", "Leviathan", "利维坦", "气田", 32.58, 34.78, source="Israel Ministry of Energy", note="气田。"),
    record("以色列", "Tamar", "塔马尔", "气田", 31.99, 34.33, source="Israel Ministry of Energy", note="气田。"),
    record("以色列", "Karish", "卡里什", "气田", 32.62, 33.94, source="Israel Ministry of Energy", note="气田。"),
    record("以色列", "Tanin", "塔宁", "气田", 32.73, 34.10, source="Israel Ministry of Energy", note="气田。"),
    record("土耳其", "Raman", "拉曼", "油田", 37.86, 41.16, source="TPAO"),
    record("土耳其", "Batı Raman", "西拉曼", "油田", 37.88, 41.05, source="TPAO"),
    record("土耳其", "Garzan", "加尔赞", "油田", 37.75, 41.45, source="TPAO"),
    record("土耳其", "Şelmo", "谢尔莫", "油田", 37.77, 41.69, source="TPAO"),
    record("土耳其", "Gabar", "加巴尔", "油田群", 37.40, 42.45, source="TPAO"),

    # Egypt: named assets from a 2013 operator report and EGPC's 2023 brownfields package.
    record("埃及", "Belayim", "贝莱伊姆", "油田", None, None, value="105", metric_type="actual_output", unit="千桶/日", data_date="2013年", status="2013年运营商报告产量；当前值未核", source="Eni Egypt Factbook 2013", note="Eni报告2013年Belayim约105千桶/日，并列其净额56千桶/日；这是历史数据，不代表当前田级实产。"),
    record("埃及", "Shukheir Offshore (Shukheir Bay)", "舒凯尔海上（舒凯尔湾）", "油田／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；当前逐田实产未核", source="Egypt EGPC Brownfields 2023", note="EGPC图示资产面积5平方公里；面积不是储量或产量。"),
    record("埃及", "Shukheir Offshore (Gamma)", "舒凯尔海上（伽马）", "油田／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；当前逐田实产未核", source="Egypt EGPC Brownfields 2023", note="EGPC图示资产面积23.7平方公里；面积不是储量或产量。"),
    record("埃及", "Gazwarina", "加兹瓦里纳", "油田／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；当前逐田实产未核", source="Egypt EGPC Brownfields 2023", note="EGPC图示资产面积2.5平方公里；面积不是储量或产量。"),
    record("埃及", "Ras El Ush", "拉斯埃尔乌什", "油田／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；当前逐田实产未核", source="Egypt EGPC Brownfields 2023", note="EGPC图示资产面积9平方公里；面积不是储量或产量。"),
    record("埃及", "Zeit Bay", "宰特湾", "油田／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；当前逐田实产未核", source="Egypt EGPC Brownfields 2023", note="EGPC图示资产面积38平方公里；面积不是储量或产量。"),
    record("埃及", "Ras Budran", "拉斯布德兰", "油田／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；当前逐田实产未核", source="Egypt EGPC Brownfields 2023", note="EGPC图示资产面积15平方公里；面积不是储量或产量。"),
    record("埃及", "East Zeit (E. Zeit)", "东宰特（E. Zeit）", "油田／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；当前逐田实产未核", source="Egypt EGPC Brownfields 2023", note="EGPC图示资产面积27平方公里；面积不是储量或产量。"),
    record("埃及", "Ashrafi", "阿什拉菲", "油田／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；当前逐田实产未核", source="Egypt EGPC Brownfields 2023", note="EGPC图示资产面积35平方公里；面积不是储量或产量。"),
    record("埃及", "Wadi El Sahl Development Area", "瓦迪埃尔萨赫勒开发区", "油田开发区／EGPC棕地招标资产", None, None, status="EGPC 2023棕地资料列名；田级产量待核", source="Egypt EGPC Brownfields 2023", note="原资料称Development Area并列面积31平方公里，目录按开发区记录，不将其强行当作单一油田；EGPC包件的剩余储量／增产潜力不拆给单个资产。"),
]


# 本轮原始报告复核；补充目录与数字在元数据生成之前应用。
from htfa.monitoring.energy_supply import supplemental_assets as SUPPLEMENT
from htfa.monitoring.energy_supply import reconciled_assets as RECONCILED
from htfa.monitoring.energy_supply import continuation_assets as CONTINUATION
from htfa.monitoring.energy_supply.asset_reviews import (
    REVIEWS, apply_production_recheck, attach_gem_production_candidates, apply_public_metadata,
    finish_production_recheck, finish_reviews, public_reference_coordinates,
)
from htfa.monitoring.energy_supply.audited_measurements import apply_annual_volumes, additional_measurements
ASSETS.extend(SUPPLEMENT.additions(record))
ASSETS.extend(RECONCILED.additions(record))
RECONCILED.apply_existing(ASSETS)
ASSETS.extend(CONTINUATION.additions(record))
CONTINUATION.apply_measurements(ASSETS)
for review in REVIEWS:
    ASSETS.extend(review.additions(record))
    review.apply_measurements(ASSETS)
apply_annual_volumes(ASSETS)
for asset in ASSETS:
    if asset["country"] == "伊朗" and asset["name"] == "Darkhovin":
        asset.update(aliases=["Darquain", "Darkhoveyn"], lat=30.7289, lon=48.2934,
                     coordinate_precision="GEM所列近似田中心；非边界",
                     note="Darkhovin / Darquain为同田异名，已合并；不重复计数。")
    if asset["country"] == "伊拉克" and asset["name"] in {"Tawke", "Peshkabir"}:
        asset.update(value="0.363" if asset["name"] == "Tawke" else "0",
                     metric_type="actual_output_boe", unit="千桶油当量/日",
                     data_date="2026年第二季度平均",
                     source="DNO Q2 2026", source_url="https://www.dno.no/media/ezuglbal/q2-2026-interim-results-report.pdf",
                     numeric_audit="运营商Q2表原值已复核；BOE不转换为原油桶",
                     note="DNO Q2 2026第4页：Tawke 363 boe/d、Peshkabir 0 boe/d，100%毛口径。两田分别6月28日、7月11日恢复；季度零不等于当前停产。")
    if asset["name"] == "Marjan":
        asset.update(source="Aramco Annual Report 2025", source_url="https://www.aramco.com/-/media/publications/corporate-reports/reports-and-presentations/2025/fy/saudi-aramco-ara-2025-english.pdf",
                     numeric_audit="2025年报原文300 mbpd已复核；新增产能，非实产")
    if asset["name"] == "SARB Deep Gas":
        asset.update(source="ADNOC SARB Deep Gas FID", source_url="https://www.adnoc.ae/en/news-and-media/press-releases/2026/adnoc-announces-final-investment-decision-for-the-sarb-deep-gas-development/",
                     note="2026-01-07 FID公告：目标最高200百万标准立方英尺/日，非已投产实绩。")
    if asset["name"] == "Bab Gas Cap":
        asset.update(source="TotalEnergies Bab Gas Cap 2026", source_url="https://www.sec.gov/Archives/edgar/data/879764/000110465926079516/tm2619405d1_ex99-6.htm",
                     data_date="2026-06-24特许区公告", note="开发目标1.5十亿立方英尺/日，非当前实产；已更换不能支撑数字的通用资产页。")
    if asset["name"] == "Upper Zakum":
        asset.update(value="1,500", metric_type="target_capacity", data_date="2026-02-04承包商业绩会规划口径",
                     source="NMDC Energy FY25 Results Call", source_url="https://www.nmdc-energy.com/assets/files/earnings-results/NMDC%20Energy%20FY25%20Results%20Conference%20Call%20020426%20final.pdf",
                     numeric_audit="承包商原始会议稿已核；目标，不是运营商实产",
                     note="NMDC Energy CEO原始会议稿披露Upper Zakum计划由100万桶/日增至150万桶/日；替换2017年100万目标。该值是扩产规划，未据承包商口述填当前实产。")
    if asset["name"] == "Bahrain Field (Awali)":
        asset["asset_type"] = "油田"
    if asset["name"] == "Margham":
        asset.update(source="DUSUP Margham", source_url="https://www.dusup.ae/supply-operations/margham-gas-plant/")
    if asset["name"] == "Hedebah":
        asset.update(source="SNOC Hedebah 2025", source_url="https://www.snoc.ae/news/snoc-strengthens-sharjahs-energy-security-with-second-well-success-in-hedebah-field/")
    if asset["name"] == "Umm Niqa":
        asset.update(value=None, metric_type="undisclosed", unit=None, data_date=None,
                     numeric_audit="历史22.14值的引用PDF失效；暂撤回待恢复原表",
                     note=asset["note"] + " 2026-09-30原引用2023/24年报HTTP404，未恢复原表前不展示22.14千桶/日。")

apply_production_recheck(ASSETS)

# 分层审计：层级字段独立于资产类型，防止区块／油田群合计与单田重复计算。
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

LEVEL_OVERRIDES = {
    ("伊拉克", "Baba Dome"): "development_area",
    ("伊拉克", "Avana Dome"): "development_area",
    ("埃及", "Meleiha"): "development_area",
    ("埃及", "Belayim"): "field_group",
    ("沙特阿拉伯", "Ghawar"): "field_group",
    ("沙特阿拉伯", "Khurais"): "field_group",
    ("沙特阿拉伯", "Abu Jifan"): "field",
    ("沙特阿拉伯", "Mazalij"): "field",
    ("沙特阿拉伯", "Qirdi"): "field",
    ("阿联酋", "Ghasha Concession"): "concession",
    ("伊拉克", "Eridu (Block 10)"): "field",
    ("卡塔尔", "A-Structures (A-North / A-South)"): "field_group",
    ("阿曼", "Harweel"): "field_group",
    ("叙利亚", "Rmeilan Sector One"): "field_group",
    ("土耳其", "Gabar"): "field_group",
    ("埃及", "Wadi El Sahl Development Area"): "development_area",
}

PARENT_RELATIONSHIPS = {
    ("伊拉克", "Baba Dome"): "Kirkuk",
    ("伊拉克", "Avana Dome"): "Kirkuk",
    ("伊拉克", "Fakkah"): "Missan Fields",
    ("伊拉克", "Bazerkan"): "Missan Fields",
    ("伊拉克", "Abu Gharb"): "Missan Fields",
    ("沙特阿拉伯", "Abu Jifan"): "Khurais",
    ("沙特阿拉伯", "Mazalij"): "Khurais",
    ("沙特阿拉伯", "Qirdi"): "Khurais",
    ("阿联酋", "Belbazem"): "Belbazem Offshore Block",
    ("阿联酋", "Umm Al Salsal"): "Belbazem Offshore Block",
    ("阿联酋", "Umm Al Dholou"): "Belbazem Offshore Block",
    ("阿联酋", "Hail (ADNOC Ghasha)"): "Ghasha Concession",
    ("阿联酋", "Ghasha"): "Ghasha Concession",
    ("阿联酋", "Dalma"): "Ghasha Concession",
    ("阿联酋", "Nasr"): "Ghasha Concession",
    ("阿联酋", "Satah Al Razboot (SARB)"): "Ghasha Concession",
    ("阿联酋", "SARB Deep Gas"): "Satah Al Razboot (SARB)",
    ("阿联酋", "Bab Gas Cap"): "Bab",
    ("伊拉克", "Swara Tika"): "Sarsang",
    ("伊拉克", "East Swara Tika"): "Sarsang",
    ("卡塔尔", "A-North"): "A-Structures (A-North / A-South)",
    ("卡塔尔", "A-South"): "A-Structures (A-North / A-South)",
    ("阿曼", "Zalzala"): "Harweel",
    ("阿曼", "Haima West"): "Marmul",
    ("阿曼", "Al Noor"): "Nimr",
    ("阿曼", "Nimr-A"): "Nimr",
    ("阿曼", "Nimr-E"): "Nimr",
    ("阿曼", "Yumna"): "Block 50 (Masirah)",
    ("阿曼", "Daleel"): "Block 5 (Daleel)",
    ("阿曼", "Shadi"): "Block 5 (Daleel)",
    ("阿曼", "Bushra"): "Block 5 (Daleel)",
    ("阿曼", "Mazoon"): "Block 5 (Daleel)",
    ("阿曼", "Furat"): "Block 5 (Daleel)",
    ("阿曼", "Thahab"): "Block 5 (Daleel)",
    ("阿曼", "Safah"): "Block 9 (Oman)",
    ("阿曼", "Wadi Latham"): "Block 9 (Oman)",
    ("阿曼", "Khamilah"): "Block 27 (Oman)",
    ("阿曼", "West Bukha"): "Block 8 (Oman)",
    ("阿曼", "Bukha"): "Block 8 (Oman)",
    ("阿曼", "Sahma"): "Block 7 (Oman)",
    ("阿曼", "Abu Butabul"): "Block 60 (Oman)",
    ("阿曼", "Bisat"): "Block 60 (Oman)",
    ("阿曼", "Khazzan"): "Block 61 (Oman)",
    ("阿曼", "Ghazeer"): "Block 61 (Oman)",
    ("也门", "Alif"): "Block 18 (Marib)",
    ("也门", "Habban"): "Block S2 (Uqlah)",
    ("也门", "Tasour"): "Block 32 (Hawareem)",
    ("也门", "Godah"): "Block 32 (Hawareem)",
    ("也门", "Hiswah (Haswa)"): "Block 9 (Malik)",
    ("也门", "Alroidhat (Al-Rowedhat)"): "Block 9 (Malik)",
    ("也门", "Qarn Qeamah"): "Block 9 (Malik)",
    ("叙利亚", "Rmeilan"): "Rmeilan Sector One",
    ("叙利亚", "Suwaydiya"): "Rmeilan Sector One",
    ("叙利亚", "Qarachok"): "Rmeilan Sector One",
    ("叙利亚", "Hamza"): "Rmeilan Sector One",
    ("叙利亚", "Alyan"): "Rmeilan Sector One",
    ("叙利亚", "Sazabeh"): "Rmeilan Sector One",
    ("叙利亚", "Ode"): "Rmeilan Sector One",
    ("叙利亚", "Tigris"): "Rmeilan Sector One",
}

# 官方资料直接给出组成区域、但目录不需要为每个细分区另建地图节点的情形。
NAMED_CONSTITUENTS = {
    ("沙特阿拉伯", "Ghawar"): (
        "Fazran", "Ain Dar", "Shedgum", "Uthmaniyah", "Hawiyah", "Haradh",
    ),
}

# 没有公开田级数值、但对区域供给具有代表性的独立资产，用于战略层级分类。
STRATEGIC_STANDALONE_ASSETS = {
    ("沙特阿拉伯", name) for name in ("Qatif", "Abqaiq", "Khursaniyah", "Jafurah")
} | {
    ("伊拉克", name) for name in ("Kirkuk", "Qayyarah")
} | {
    ("伊朗", name) for name in (
        "Ahvaz", "Marun", "Aghajari", "Gachsaran", "Reg-e-Safid",
        "South Azadegan", "Yadavaran", "South Pars",
    )
} | {
    ("科威特", name) for name in (
        "Burgan", "Raudhatain", "Sabriya", "Minagish", "Umm Gudair", "Wafra", "Khafji",
    )
} | {
    ("阿曼", name) for name in ("Mukhaizna", "Yibal", "Fahud", "Qarn Alam", "Marmul")
} | {
    ("卡塔尔", "North Field"),
    ("以色列", "Leviathan"), ("以色列", "Tamar"), ("以色列", "Karish"),
    ("阿联酋", "Fateh"),
}

# 地图补点单独记录证据和精度，不改写原始目录来源。优先采用公开WGS84资产点位；
# 区块只有组成田或设施点时，明确标为近似代表点，不能理解为区块边界中心。
COORDINATE_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("沙特阿拉伯", "Abu Jifan"): {
        "lat": 25.0631, "lon": 48.0304, "precision": "Khurais综合体内公开近似点（WGS84）",
        "source": "Global Energy Monitor — Abu Jifan",
        "url": "https://www.gem.wiki/Abu_Jifan_Oil_and_Gas_Field_%28Saudi_Arabia%29",
    },
    ("沙特阿拉伯", "Mazalij"): {
        "lat": 25.0631, "lon": 48.0304, "precision": "Khurais综合体内公开近似点（WGS84）",
        "source": "Global Energy Monitor — Mazalij",
        "url": "https://www.gem.wiki/Mazalij_Oil_and_Gas_Field_%28Saudi_Arabia%29",
    },
    ("沙特阿拉伯", "Abu Hadriya"): {
        "lat": 27.312, "lon": 49.0051, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Abu Hadriya",
        "url": "https://www.gem.wiki/Abu_Hadriya_Oil_Field_%28Saudi_Arabia%29",
    },
    ("沙特阿拉伯", "Fadhili"): {
        "lat": 26.9807, "lon": 49.1735, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Fadhili",
        "url": "https://www.gem.wiki/Fadhili_Oil_Field_%28Saudi_Arabia%29",
    },
    ("沙特阿拉伯", "Harmaliyah"): {
        "lat": 24.6291, "lon": 49.4985, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Harmaliyah",
        "url": "https://www.gem.wiki/Harmaliyah_Oil_and_Gas_Field_%28Saudi_Arabia%29",
    },
    ("沙特阿拉伯", "Hawtah"): {
        "lat": 22.9678, "lon": 46.8995,
        "precision": "Hawtah油田机场设施代表点（近似，非油田中心）",
        "source": "OpenStreetMap/GeoNames — Hawtah Airport",
        "url": "https://mapcarta.com/36033010", "proxy": True,
    },
    ("沙特阿拉伯", "Sakab"): {
        "lat": 23.92, "lon": 49.08,
        "precision": "Haradh油田区域代表点（Sakab位于其东南；非井位）",
        "source": "Saudi Aramco discovery release / Haradh public coordinate",
        "url": "https://www.aramco.com/en/news-media/news/2020/saudi-aramco-announces-new-oil-and-gas-discoveries", "proxy": True,
    },
    ("沙特阿拉伯", "Zumul"): {
        "lat": 22.48, "lon": 53.78,
        "precision": "鲁卜哈利新发现区域代表点（借用Shaybah区域；非井位）",
        "source": "Saudi Aramco discovery release / Shaybah regional anchor",
        "url": "https://www.aramco.com/en/news-media/news/2020/saudi-aramco-announces-new-oil-and-gas-discoveries", "proxy": True,
    },
    **{
        ("沙特阿拉伯", name): {
            "lat": 25.43, "lon": 48.82,
            "precision": "沙特东部省新发现区域代表点（非油田中心或井位）",
            "source": "Saudi Press Agency announcement — Eastern Region (reported by Reuters)",
            "url": "https://www.reuters.com/business/energy/saudi-arabia-discovers-14-oil-natural-gas-fields-state-news-agency-says-2025-04-09/",
            "proxy": True,
        }
        for name in ("Jabu", "Sayahid", "Ayfan")
    },
    **{
        ("沙特阿拉伯", name): {
            "lat": 25.43, "lon": 48.82,
            "precision": "沙特东部省新发现区域代表点（非油田中心或井位）",
            "source": "Saudi Press Agency announcement — Eastern Province (reported by Reuters)",
            "url": "https://www.reuters.com/world/middle-east/saudi-energy-minister-announces-discovery-multiple-oil-gas-fields-2024-07-01/",
            "proxy": True,
        }
        for name in ("Ladam", "Faruq")
    },
    **{
        ("沙特阿拉伯", name): {
            "lat": 22.48, "lon": 53.78,
            "precision": "鲁卜哈利新发现区域代表点（非油田中心或井位）",
            "source": "Saudi Press Agency announcement — Empty Quarter (reported by Reuters)",
            "url": "https://www.reuters.com/business/energy/saudi-arabia-discovers-14-oil-natural-gas-fields-state-news-agency-says-2025-04-09/",
            "proxy": True,
        }
        for name in ("Nuwayr", "Damda", "Qurqas")
    },
    ("阿联酋", "Hail (ADNOC Ghasha)"): {
        "lat": 24.368, "lon": 53.413, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Hail",
        "url": "https://www.gem.wiki/Hail_Oil_Field_%28United_Arab_Emirates%29",
    },
    ("阿联酋", "Sajaa"): {
        "lat": 25.3778, "lon": 55.6826, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Sajaa",
        "url": "https://www.gem.wiki/Sajaa_Oil_and_Gas_Field_%28United_Arab_Emirates%29",
    },
    ("阿联酋", "Kahaif"): {
        "lat": 25.1941, "lon": 55.7993, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Kahaif",
        "url": "https://www.gem.wiki/Kahaif_Oil_and_Gas_Field_%28United_Arab_Emirates%29",
    },
    ("阿联酋", "Umm Al Quwain"): {
        "lat": 25.5639, "lon": 55.4466, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Umm Al Qaiwain",
        "url": "https://www.gem.wiki/Umm_Al_Qaiwain_%28UAQ%29_Gas_Field_%28United_Arab_Emirates%29",
    },
    ("阿联酋", "Moveyeid"): {
        "lat": 25.3778, "lon": 55.6826,
        "precision": "Sajaa—Moveyeid—Kahaif资产群代表点（非Moveyeid井位）",
        "source": "SNOC asset grouping / Sajaa public coordinate",
        "url": "https://www.snoc.ae/operations/", "proxy": True,
    },
    ("阿联酋", "Mahani"): {
        "lat": 25.15, "lon": 55.78,
        "precision": "Area B公开位置图估读（近似，非井位）",
        "source": "ENI / GEO ExPro — Mahani-1 location map",
        "url": "https://geoexpro.com/uae-sharjah-gas-discovery/", "proxy": True,
    },
    ("阿联酋", "Hedebah"): {
        "lat": 25.442, "lon": 55.754,
        "precision": "按Sajaa处理厂东北约10公里推算（区域代表点）",
        "source": "SNOC Hedebah project description / Sajaa public coordinate",
        "url": "https://www.snoc.ae/operations/", "proxy": True,
    },
    ("阿联酋", "Saleh"): {
        "lat": 26.14, "lon": 55.71,
        "precision": "Saleh—Ras al-Khaimah输气管线海上起点（近似）",
        "source": "Global Energy Monitor — Saleh–Ras al-Khaimah gas pipeline",
        "url": "https://www.gem.wiki/Saleh%E2%80%93Ras_al-Khaimah_gas_pipeline", "proxy": True,
    },
    ("伊拉克", "Khurmala"): {
        "lat": 35.97778, "lon": 43.76306,
        "precision": "公开地图油田设施点位（OpenStreetMap；近似）",
        "source": "OpenStreetMap/GeoNames — Khurmala Oilfield",
        "url": "https://mapcarta.com/30858796",
    },
    ("伊拉克", "Naft Khana"): {
        "lat": 34.1814, "lon": 45.4085, "precision": "跨境油田项目公开近似点（WGS84）",
        "source": "Global Energy Monitor — Khanah / Naft Khana",
        "url": "https://www.gem.wiki/Khanah_Oil_Field_%28Iraq%29",
    },
    ("伊拉克", "Sarta"): {
        "lat": 36.377, "lon": 44.0002, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Sarta",
        "url": "https://www.gem.wiki/Sarta_Oil_and_Gas_Field_%28Iraq%29",
    },
    ("伊拉克", "Baeshiqa"): {
        "lat": 36.45046, "lon": 43.34977,
        "precision": "Baeshiqa许可证区同名城镇代表点（非油田中心）",
        "source": "DNO license description / GeoNames — Bashiqa",
        "url": "https://www.dno.no/en/operations/kurdistan-region-of-iraq/", "proxy": True,
    },
    ("伊拉克", "Eridu (Block 10)"): {
        "lat": 30.73, "lon": 45.99, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Eridu",
        "url": "https://www.gem.wiki/Eridu_Oil_Field_%28Iraq%29",
    },
    ("伊拉克", "Ajil"): {
        "lat": 35.019, "lon": 43.744, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Ajeel",
        "url": "https://www.gem.wiki/Ajeel_Oil_and_Gas_Field_%28Iraq%29",
    },
    ("伊拉克", "Ain Zalah"): {
        "lat": 36.71667, "lon": 42.6, "precision": "公开地名数据库油田点位（WGS84）",
        "source": "GeoNames/Mapcarta — Ain Zalah Oil Field", "url": "https://mapcarta.com/12542254",
    },
    ("伊拉克", "Batmah"): {
        "lat": 36.66667, "lon": 42.78333, "precision": "公开地名数据库油田点位（WGS84）",
        "source": "GeoNames/Mapcarta — Butmah Oil Field", "url": "https://mapcarta.com/12540670",
    },
    ("伊拉克", "Hamrin"): {
        "lat": 34.93545, "lon": 43.84327, "precision": "公开地名数据库油田点位（WGS84）",
        "source": "GeoNames/Mapcarta — Hamrin Oil Field", "url": "https://mapcarta.com/26089772",
    },
    ("伊拉克", "Amara"): {
        "lat": 31.7468, "lon": 47.0614, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Amara",
        "url": "https://www.gem.wiki/Amara_Oil_and_Gas_Field_%28Iraq%29",
    },
    ("伊拉克", "Noor"): {
        "lat": 31.796, "lon": 47.287, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Noor",
        "url": "https://www.gem.wiki/Noor_Oil_and_Gas_Field_%28Iraq%29",
    },
    ("伊拉克", "Safiya"): {
        "lat": 36.9216, "lon": 42.24094,
        "precision": "同名油田设施公开点（近似，非油田中心）",
        "source": "OpenStreetMap/Mapcarta — Safiya oil-field facility",
        "url": "https://mapcarta.com/N8571647117", "proxy": True,
    },
    ("伊朗", "Hengam"): {
        "lat": 26.4214, "lon": 55.9659, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Hengam",
        "url": "https://www.gem.wiki/Hengam_Oil_and_Gas_Field_%28Iran%29",
    },
    ("伊朗", "South Pars"): {
        "lat": 26.619125, "lon": 52.067964,
        "precision": "南帕尔斯／北方气田整体公开中心点（WGS84；近似）",
        "source": "South Pars / North Dome public coordinate",
        "url": "https://en.wikipedia.org/wiki/South_Pars/North_Dome_Gas-Condensate_field",
    },
    ("伊朗", "West Paydar"): {
        "lat": 32.1693, "lon": 47.5814, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Paydar West",
        "url": "https://www.gem.wiki/Paydar_West_Oil_and_Gas_Field_%28Iran%29",
    },
    ("伊朗", "Chehsmeh-Khosh"): {
        "lat": 32.2969, "lon": 47.7746, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Cheshmeh-Khosh",
        "url": "https://www.gem.wiki/Cheshmeh-Khosh_Oil_Field_%28Iran%29",
    },
    ("伊朗", "Danan"): {
        "lat": 32.614, "lon": 47.5312, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Danan",
        "url": "https://www.gem.wiki/Danan_Oil_Field_%28Iran%29",
    },
    ("伊朗", "Changuleh"): {
        "lat": 32.98, "lon": 46.47, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Changuleh",
        "url": "https://www.gem.wiki/Changuleh_Oil_Field_%28Iran%29",
    },
    ("伊朗", "Dalpari"): {
        "lat": 32.5293, "lon": 47.8673, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Dalpari",
        "url": "https://www.gem.wiki/Dalpari_Oil_Field_%28Iran%29",
    },
    ("伊朗", "Band-e-Karkheh"): {
        "lat": 31.44, "lon": 48.52,
        "precision": "公开区域图估读／Ahvaz西北约20公里（近似）",
        "source": "IranOilGas field map / published location description",
        "url": "https://www.iranoilgas.com/fields/details.aspx?id=1063", "proxy": True,
    },
    ("伊朗", "Paydar"): {
        "lat": 32.02, "lon": 47.72,
        "precision": "East Paydar公开区域图估读（近似，非井位）",
        "source": "IranOilGas — East Paydar field map",
        "url": "https://www.iranoilgas.com/fields/details.aspx?id=1089", "proxy": True,
    },
    ("科威特", "Nokhetha"): {
        "lat": 29.4162, "lon": 48.7026, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Nokhetha",
        "url": "https://www.gem.wiki/Nokhetha_Oil_and_Gas_Field_%28Kuwait%29",
    },
    ("科威特", "Julaiah"): {
        "lat": 28.824, "lon": 48.6894, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Julaiah",
        "url": "https://www.gem.wiki/Julaiah_Oil_and_Gas_Field_%28Kuwait%29",
    },
    ("科威特", "Mutriba"): {
        "lat": 29.763444, "lon": 47.224222,
        "precision": "官方地震勘探区中心坐标（WGS84；区域代表点）",
        "source": "Kuwait official seismic-survey tender coordinate",
        "url": "https://www.kockw.com/sites/EN/Pages/Profile/WhatWeDo/OilFields.aspx", "proxy": True,
    },
    ("科威特", "Shaham"): {
        "lat": 29.916667, "lon": 47.666667,
        "precision": "北科威特同名地理要素代表点（非油田中心）",
        "source": "GeoNames — Shaib Abu-Shaham / field-region description",
        "url": "https://www.geonames.org/387923/shaib-abu-shaham.html", "proxy": True,
    },
    ("科威特", "Kra-al-Maru"): {
        "lat": 29.435833, "lon": 47.327778,
        "precision": "西科威特同名地理要素代表点（近似）",
        "source": "GeoNames / MEES field-region description",
        "url": "https://www.geonames.org/285913/kra-al-maru.html", "proxy": True,
    },
    ("卡塔尔", "Al-Rayyan"): {
        "lat": 26.6591, "lon": 51.5725, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Al Rayyan",
        "url": "https://www.gem.wiki/Al_Rayyan_Oil_and_Gas_Field_%28Qatar%29",
    },
    ("卡塔尔", "Al-Murjan"): {
        "lat": 26.6591, "lon": 51.5725,
        "precision": "Al-Rayyan生产平台代表点（Al-Murjan经该平台生产）",
        "source": "QatarEnergy project description / Global Energy Monitor — Al Rayyan",
        "url": "https://www.qatarenergy.qa/en/WhatWeDo/Pages/ExplorationandProduction.aspx", "proxy": True,
    },
    ("卡塔尔", "A-Structures (A-North / A-South)"): {
        "lat": 25.0811, "lon": 52.4847,
        "precision": "Al-Karkara／A-Structures项目公开近似点（WGS84）",
        "source": "MarineLink — Al-Karkara/A-Structure",
        "url": "https://ports.marinelink.com/oilrigs/rig/alkarkaraastructure",
    },
    ("阿曼", "Block 9 (Oman)"): {
        "lat": 23.1614, "lon": 55.4485,
        "precision": "Safah／Wadi Latham组成田公开近似点（WGS84）",
        "source": "Global Energy Monitor — Safah/Wadi Latham",
        "url": "https://www.gem.wiki/Safah/Wadi_Latham_Oil_and_Gas_Field_%28Oman%29",
    },
    ("阿曼", "Safah"): {
        "lat": 23.1614, "lon": 55.4485,
        "precision": "Safah／Wadi Latham联合公开近似点（WGS84）",
        "source": "Global Energy Monitor — Safah/Wadi Latham",
        "url": "https://www.gem.wiki/Safah/Wadi_Latham_Oil_and_Gas_Field_%28Oman%29",
    },
    ("阿曼", "Wadi Latham"): {
        "lat": 23.1614, "lon": 55.4485,
        "precision": "Safah／Wadi Latham联合公开近似点（WGS84）",
        "source": "Global Energy Monitor — Safah/Wadi Latham",
        "url": "https://www.gem.wiki/Safah/Wadi_Latham_Oil_and_Gas_Field_%28Oman%29",
    },
    ("阿曼", "Block 27 (Oman)"): {
        "lat": 22.7117, "lon": 56.5162, "precision": "Khamilah组成田公开近似点（WGS84）",
        "source": "Global Energy Monitor — Khamilah",
        "url": "https://www.gem.wiki/Khamilah_Oil_Field_%28Oman%29",
    },
    ("阿曼", "Khamilah"): {
        "lat": 22.7117, "lon": 56.5162, "precision": "公开资产数据库近似点（WGS84）",
        "source": "Global Energy Monitor — Khamilah",
        "url": "https://www.gem.wiki/Khamilah_Oil_Field_%28Oman%29",
    },
    ("阿曼", "Block 8 (Oman)"): {
        "lat": 26.4214, "lon": 55.9659,
        "precision": "跨境West Bukha／Hengam油田代表点（WGS84；近似）",
        "source": "Global Energy Monitor — Hengam / West Bukha cross-border field",
        "url": "https://www.gem.wiki/Hengam_Oil_and_Gas_Field_%28Iran%29",
    },
    ("阿曼", "West Bukha"): {
        "lat": 26.4214, "lon": 55.9659,
        "precision": "跨境West Bukha／Hengam油田代表点（WGS84；近似）",
        "source": "Global Energy Monitor — Hengam / West Bukha cross-border field",
        "url": "https://www.gem.wiki/Hengam_Oil_and_Gas_Field_%28Iran%29",
    },
    ("阿曼", "Block 7 (Oman)"): {
        "lat": 20.40786, "lon": 56.24374,
        "precision": "Sahma组成油田公开点位（WGS84；区块代表点）",
        "source": "OpenStreetMap/GeoNames — As Sahmah", "url": "https://mapcarta.com/36266762",
    },
    ("阿曼", "Sahma"): {
        "lat": 20.40786, "lon": 56.24374, "precision": "公开地名数据库油田点位（WGS84）",
        "source": "OpenStreetMap/GeoNames — As Sahmah", "url": "https://mapcarta.com/36266762",
    },
    ("阿曼", "Block 60 (Oman)"): {
        "lat": 21.178, "lon": 55.8542,
        "precision": "Bisat／Abu Butabul区块公开近似点（WGS84）",
        "source": "Global Energy Monitor — Bisat / Abu Butabul",
        "url": "https://www.gem.wiki/Bisat_Oil_Field_%28Oman%29",
    },
    ("阿曼", "Abu Butabul"): {
        "lat": 21.178, "lon": 55.8542, "precision": "Block 60公开近似点（WGS84）",
        "source": "Global Energy Monitor — Abu Butabul",
        "url": "https://www.gem.wiki/Abu_Butabul_Oil_and_Gas_Field_%28Oman%29",
    },
    ("阿曼", "Block 61 (Oman)"): {
        "lat": 21.705, "lon": 56.4643,
        "precision": "Khazzan／Ghazeer项目公开近似点（WGS84）",
        "source": "Global Energy Monitor — Khazzan/Ghazeer",
        "url": "https://www.gem.wiki/Khazzan_Oil_and_Gas_Complex_%28Oman%29",
    },
    ("阿曼", "Khazzan"): {
        "lat": 21.705, "lon": 56.4643,
        "precision": "Khazzan／Ghazeer项目公开近似点（WGS84）",
        "source": "Global Energy Monitor — Khazzan Phase 1",
        "url": "https://www.gem.wiki/Khazzan_Phase_1_Oil_and_Gas_Field_%28Oman%29",
    },
    ("阿曼", "Ghazeer"): {
        "lat": 21.705, "lon": 56.4643,
        "precision": "Khazzan／Ghazeer项目公开近似点（WGS84）",
        "source": "Global Energy Monitor — Ghazeer",
        "url": "https://www.gem.wiki/Ghazeer_%28Khazzan_Phase_2%29_Oil_and_Gas_Field_%28Oman%29",
    },
    ("阿曼", "Budour Northeast"): {
        "lat": 18.31856, "lon": 55.10261,
        "precision": "Birba作业区公开油田点（Budour Northeast区域代表点）",
        "source": "PDO discovery description / GeoNames — Birba Oil Field",
        "url": "https://mapcarta.com/35907568", "proxy": True,
    },
    ("阿曼", "Wadi Aswad North"): {
        "lat": 21.93501, "lon": 55.74842,
        "precision": "Wadi Aswad同名地理区域代表点（非发现井坐标）",
        "source": "GeoNames/Mapcarta — Wadi Aswad",
        "url": "https://mapcarta.com/12444616", "proxy": True,
    },
    ("阿曼", "Safah North B"): {
        "lat": 23.196323, "lon": 55.471184,
        "precision": "Safah油田公开点（北部发现区域代表点；非井位）",
        "source": "GeoNames — Safah Oil Field / Occidental discovery announcement",
        "url": "https://www.geonames.org/11864188/safah-oil-field.html", "proxy": True,
    },
    ("也门", "Block S2 (Uqlah)"): {
        "lat": 15.3053, "lon": 46.77715,
        "precision": "Habban组成油田设施公开点位（OpenStreetMap；近似）",
        "source": "OpenStreetMap — Habban field facilities",
        "url": "https://mapcarta.com/W498389053",
    },
    ("也门", "Habban"): {
        "lat": 15.3053, "lon": 46.77715,
        "precision": "公开油田设施点位（OpenStreetMap；近似）",
        "source": "OpenStreetMap — Habban field facilities",
        "url": "https://mapcarta.com/W498389053",
    },
    ("也门", "Hiswah (Haswa)"): {
        "lat": 15.70337, "lon": 47.96781,
        "precision": "公开油田设施点位（OpenStreetMap；近似）",
        "source": "OpenStreetMap — Hiswah field facilities",
        "url": "https://mapcarta.com/W498389042",
    },
    ("也门", "Alroidhat (Al-Rowedhat)"): {
        "lat": 15.58213, "lon": 48.09317,
        "precision": "公开油田设施点位（OpenStreetMap；近似）",
        "source": "OpenStreetMap — Al Rhoidat field facilities",
        "url": "https://mapcarta.com/W498389044",
    },
    ("埃及", "Belayim"): {
        "lat": 28.6197, "lon": 33.2076, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Belayim Marine",
        "url": "https://www.gem.wiki/Belayim_Marine_Oil_and_Gas_Field_%28Egypt%29",
    },
    ("埃及", "Wadi El Sahl Development Area"): {
        "lat": 27.17584, "lon": 33.77484,
        "precision": "开发区同名地理要素近似点（WGS84；非边界中心）",
        "source": "GeoNames/OpenStreetMap — Wadi Faliq as Sahl",
        "url": "https://mapcarta.com/13059698",
    },
    ("埃及", "Shukheir Offshore (Shukheir Bay)"): {
        "lat": 28.12, "lon": 33.31,
        "precision": "埃及官方特许权地图估读（Shukheir代表点）",
        "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
        "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf", "proxy": True,
    },
    ("埃及", "Shukheir Offshore (Gamma)"): {
        "lat": 28.12, "lon": 33.31,
        "precision": "埃及官方特许权地图估读（Shukheir特许区代表点）",
        "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
        "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf", "proxy": True,
    },
    ("埃及", "Gazwarina"): {
        "lat": 27.63, "lon": 33.64,
        "precision": "埃及官方特许权地图估读（近似）",
        "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
        "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf", "proxy": True,
    },
    ("埃及", "Ras El Ush"): {
        "lat": 27.866667, "lon": 33.516667,
        "precision": "公开地学论文所列Ras El Ush井区坐标（近似）",
        "source": "Published Ras El Ush field study",
        "url": "https://www.researchgate.net/publication/342262683", "proxy": True,
    },
    ("埃及", "Zeit Bay"): {
        "lat": 27.7182, "lon": 33.2409, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Zeit Bay",
        "url": "https://www.gem.wiki/Zeit_Bay_Oil_and_Gas_Field_%28Egypt%29",
    },
    ("埃及", "Ras Budran"): {
        "lat": 28.934, "lon": 33.2409, "precision": "公开资产数据库精确点位（WGS84）",
        "source": "Global Energy Monitor — Ras Budran",
        "url": "https://www.gem.wiki/Ras_Budran_Oil_and_Gas_Field_%28Egypt%29",
    },
    ("埃及", "East Zeit (E. Zeit)"): {
        "lat": 27.84, "lon": 33.62,
        "precision": "埃及官方特许权地图估读（近似）",
        "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
        "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf", "proxy": True,
    },
    ("埃及", "Ashrafi"): {
        "lat": 27.78, "lon": 33.59,
        "precision": "埃及官方特许权地图估读（近似）",
        "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
        "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf", "proxy": True,
    },
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

PARENT_RELATIONSHIPS.update(RECONCILED.PARENTS)
COORDINATE_OVERRIDES.update(RECONCILED.coordinates())
COORDINATE_OVERRIDES.update(CONTINUATION.coordinates())
for key, coordinate in public_reference_coordinates().items():
    COORDINATE_OVERRIDES.setdefault(key, coordinate)
LEVEL_OVERRIDES.update(CONTINUATION.levels())
for review in REVIEWS:
    LEVEL_OVERRIDES.update(review.levels())
    PARENT_RELATIONSHIPS.update(review.parents())
LEVEL_OVERRIDES.update({key: "project" for key in RECONCILED.PROJECTS})
LEVEL_OVERRIDES.update({key: "development_area" for key in RECONCILED.AREAS})


def infer_asset_level(asset_type: str) -> str:
    if "开发区" in asset_type:
        return "development_area"
    if "特许" in asset_type:
        return "concession"
    if "区块" in asset_type and not asset_type.startswith("油田（"):
        return "block"
    if "项目" in asset_type:
        return "project"
    if "油田群" in asset_type or "综合体" in asset_type or "作业区" in asset_type:
        return "field_group"
    return "field"


def infer_commodity(asset_type: str) -> str:
    if "气" in asset_type and ("油" in asset_type or "凝析" in asset_type):
        return "oil_and_gas"
    if "气" in asset_type:
        return "natural_gas"
    return "crude_oil"


for asset in ASSETS:
    key = (asset["country"], asset["name"])
    asset_level = LEVEL_OVERRIDES.get(key, infer_asset_level(asset["asset_type"]))
    commodity = ("oil_and_gas" if asset["metric_type"] == "actual_output_boe"
                 else infer_commodity(asset["asset_type"]))
    asset["asset_level"] = asset_level
    asset["asset_level_label"] = ASSET_LEVEL_LABELS[asset_level]
    asset["parent_asset"] = PARENT_RELATIONSHIPS.get(key)
    asset["parent_level"] = None
    asset["aggregation_scope"] = (
        "单一资产"
        if asset_level == "field"
        else "多资产合计"
        if asset_level in {"field_group", "block", "concession"}
        else "项目范围"
        if asset_level == "project"
        else "开发区域"
    )
    asset["commodity"] = commodity
    asset["commodity_label"] = COMMODITY_LABELS[commodity]
    asset["ownership_basis"] = "全资产毛口径（若来源披露数值）"
    asset["is_daily_output"] = (
        asset["value"] is not None and asset["metric_type"] in OUTPUT_METRIC_TYPES
    )

_asset_index = {(asset["country"], asset["name"]): asset for asset in ASSETS}
if len(_asset_index) != len(ASSETS):
    raise ValueError("资产目录出现重复国家/名称")
for asset in ASSETS:
    parent_name = asset["parent_asset"]
    if parent_name:
        parent = _asset_index.get((asset["country"], parent_name))
        if parent is None:
            raise ValueError(f"缺少上级资产记录：{asset['country']} / {asset['name']} -> {parent_name}")
        asset["parent_level"] = parent["asset_level"]


# 战略生产节点：有直接披露指标的上级资产负责汇总，组成资产保留在目录中但默认不重复上图。
# 上级缺坐标时，可使用已有组成资产地图坐标的均值，并显式标记为推算中心点。
_children: dict[tuple[str, str], list[dict[str, Any]]] = {}
for asset in ASSETS:
    if asset["parent_asset"]:
        parent_key = (asset["country"], asset["parent_asset"])
        _children.setdefault(parent_key, []).append(asset)

for asset in ASSETS:
    key = (asset["country"], asset["name"])
    direct_children = _children.get(key, [])
    named_children = list(NAMED_CONSTITUENTS.get(key, ()))
    asset["constituent_assets"] = list(dict.fromkeys([child["name"] for child in direct_children] + named_children))
    asset["constituent_count"] = len(asset["constituent_assets"])
    asset["aggregate_children_on_map"] = bool(direct_children) and asset["value"] is not None
    coordinate = COORDINATE_OVERRIDES.get(key)
    asset["map_lat"] = coordinate["lat"] if coordinate else asset["lat"]
    asset["map_lon"] = coordinate["lon"] if coordinate else asset["lon"]
    asset["map_coordinate_precision"] = (
        coordinate["precision"] if coordinate else asset["coordinate_precision"]
    )
    asset["map_is_proxy"] = bool(coordinate.get("proxy", False)) if coordinate else False
    if coordinate:
        asset["coordinate_source"] = coordinate["source"]
        asset["coordinate_source_url"] = coordinate["url"]
    elif asset["map_lat"] is not None and asset["map_lon"] is not None:
        asset["coordinate_source"] = "继承目录近似坐标；独立坐标出处待核"
        asset["coordinate_source_url"] = None
    else:
        asset["coordinate_source"] = "暂无可核验坐标"
        asset["coordinate_source_url"] = None

for asset in ASSETS:
    key = (asset["country"], asset["name"])
    direct_children = _children.get(key, [])
    if direct_children and (asset["map_lat"] is None or asset["map_lon"] is None):
        located_children = [
            child for child in direct_children
            if child["map_lat"] is not None and child["map_lon"] is not None
        ]
        if located_children:
            asset["map_lat"] = sum(child["map_lat"] for child in located_children) / len(located_children)
            asset["map_lon"] = sum(child["map_lon"] for child in located_children) / len(located_children)
            asset["map_coordinate_precision"] = (
                f"组成资产近似中心（{len(located_children)}/{len(direct_children)}个有坐标）"
            )
            asset["coordinate_source"] = "组成资产地图坐标的几何中心"
            asset["coordinate_source_url"] = None
            asset["map_is_proxy"] = True

# 完整目录中的组成单田若仍无独立点位，可退回到最近一个有坐标的上级资产代表点。
# 这只解决地图可见性，并不声称子资产与上级资产中心重合；popup 必须保留“近似”标记。
for asset in ASSETS:
    if asset["map_lat"] is not None and asset["map_lon"] is not None:
        continue
    parent_name = asset["parent_asset"]
    seen = {(asset["country"], asset["name"])}
    while parent_name:
        parent_key = (asset["country"], parent_name)
        if parent_key in seen:
            break
        seen.add(parent_key)
        parent = _asset_index[parent_key]
        if parent["map_lat"] is not None and parent["map_lon"] is not None:
            asset["map_lat"] = parent["map_lat"]
            asset["map_lon"] = parent["map_lon"]
            asset["map_coordinate_precision"] = (
                f"上级资产代表点（{parent['name']}；近似，非本资产中心）"
            )
            asset["coordinate_source"] = f"上级资产 {parent['name']} 的地图坐标"
            asset["coordinate_source_url"] = parent["coordinate_source_url"]
            asset["map_is_proxy"] = True
            break
        parent_name = parent["parent_asset"]

for asset in ASSETS:
    strategic_parent = None
    seen = {(asset["country"], asset["name"])}
    parent_name = asset["parent_asset"]
    while parent_name:
        parent_key = (asset["country"], parent_name)
        if parent_key in seen:
            raise ValueError(f"资产层级出现循环：{asset['country']} / {asset['name']}")
        seen.add(parent_key)
        parent = _asset_index[parent_key]
        if parent["aggregate_children_on_map"] and parent["map_lat"] is not None:
            strategic_parent = parent
            break
        parent_name = parent["parent_asset"]

    asset["map_default"] = strategic_parent is None
    asset["strategic_parent"] = strategic_parent["name"] if strategic_parent else None
    asset["map_drawable"] = asset["map_lat"] is not None and asset["map_lon"] is not None
    if strategic_parent:
        asset["map_role"] = "component"
        asset["map_role_label"] = f"组成资产（上级节点：{strategic_parent['name']}）"
        asset["rollup_policy"] = "上级直接披露值优先；本资产不重复计入地图汇总"
    elif asset["constituent_count"]:
        asset["map_role"] = "strategic_group"
        asset["map_role_label"] = "战略生产节点（油田群／区块）"
        asset["rollup_policy"] = (
            "采用本层级直接披露值；组成资产不相加"
            if asset["value"] is not None
            else "本层级未披露数值；不自动汇总不同日期或口径的组成资产"
        )
    else:
        asset["map_role"] = "strategic_standalone"
        asset["map_role_label"] = "战略生产节点（独立资产）"
        asset["rollup_policy"] = "独立资产；仅使用本资产直接披露值"


# 逐资产生产状态审计（2026-09-28）。
# 注意：状态是“截至证据日期”的公开资料结论，不是实时遥测；冲突地区尤其可能快速变化。
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

_STATUS_AUDIT: dict[tuple[str, str], dict[str, str]] = {}


def _assign_status(
    country: str,
    names: str,
    operating_status: str,
    status_as_of: str,
    confidence: str,
    basis: str,
    evidence_url: str | None = None,
) -> None:
    for name in [item.strip() for item in names.split("|") if item.strip()]:
        key = (country, name)
        if key not in _asset_index:
            raise ValueError(f"状态审计引用不存在的资产：{country} / {name}")
        if key in _STATUS_AUDIT:
            raise ValueError(f"状态审计重复赋值：{country} / {name}")
        _STATUS_AUDIT[key] = {
            "operating_status": operating_status,
            "operating_status_label": OPERATING_STATUS_LABELS[operating_status],
            "operating_status_as_of": status_as_of,
            "operating_status_confidence": confidence,
            "operating_status_basis": basis,
            "operating_status_evidence_url": evidence_url or _asset_index[key]["source_url"],
        }


# 沙特阿拉伯：近期官方公司材料可确认主力田持续开发／投产；发现田不把试井流量当商业生产。
_assign_status("沙特阿拉伯", "Ghawar | Safaniya | Khurais | Shaybah | Manifa | Berri | Zuluf | Qatif | Abqaiq | Khursaniyah", "producing", "2025-12-31／2026年公开材料", "中", "官方资料确认主力生产资产；逐田当日产量并未全部公开，且不把公司总产量下推到单田。")
_assign_status("沙特阿拉伯", "Marjan | Dammam | Jafurah", "producing", "2025-12-31", "高", "Aramco 2025年报逐项确认Marjan原油增量、Dammam一期及Jafurah已投产；这里仅据此判定状态，不把新增产能或公司总量当作逐田实产。", "https://www.aramco.com/-/media/publications/corporate-reports/reports-and-presentations/2025/fy/saudi-aramco-ara-2025-english.pdf")
_assign_status("沙特阿拉伯", "Jabu | Sayahid | Ayfan | Nuwayr | Damda | Qurqas | Ladam | Faruq | Sakab | Zumul", "discovered", "2017—2025年发现公告", "高", "官方资料仅确认发现或试井，未确认商业生产。")
_assign_status("沙特阿拉伯", "Abu Jifan | Mazalij", "producing", "2020年官方运营资料／网页复核2026-09-28", "中", "Aramco说明Khurais设施从Khurais、Abu Jifan和Mazalij三田生产；未披露两田各自日产量。", "https://www.aramco.com/en/news-media/elements-magazine/2020/why-intelligence-is-important")
_assign_status("沙特阿拉伯", "Qirdi", "ceased", "1980年代／报告更新至2026年", "中", "Wood Mackenzie当前资产报告明确Qirdi在1980年代停止生产，未见复产资料。", "https://www.woodmac.com/reports/upstream-oil-and-gas-khurais-3186632/")
_assign_status("沙特阿拉伯", "Abu Hadriya", "producing", "2025年资产报告／复核2026-09-28", "中", "Abu Hadriya属于仍有生产与2025—2029运营支出记录的AFK资产组合。", "https://www.woodmac.com/reports/upstream-oil-and-gas-khursaniyah-area-4215754/")
_assign_status("沙特阿拉伯", "Fadhili", "producing", "2026-09-28", "中", "当前油气资产跟踪器将Fadhili油田列为运营中；注意不要与同名Fadhili天然气处理厂混淆。", "https://www.gem.wiki/Fadhili_Oil_Field_(Saudi_Arabia)")
_assign_status("沙特阿拉伯", "Harmaliyah", "producing", "2026-09-28", "中", "当前油气资产跟踪器将Harmaliyah列为运营中，最近可见田级产量年份为2020。", "https://www.gem.wiki/Harmaliyah_Oil_and_Gas_Field_(Saudi_Arabia)")
_assign_status("沙特阿拉伯", "Hawtah", "producing", "2024年资产资料／复核2026-09-28", "中", "当前资产资料将Hawtah Trend列为生产油田，配套原油管线亦列为运营中。", "https://www.offshore-technology.com/marketdata/oil-gas-field-profile-hawtah-trend-fields-conventional-oil-field-saudi-arabia/")

# 阿联酋：运营商当前资产页与近年投产公告为主；Ghasha相关开发项目不提前标作在产。
_assign_status("阿联酋", "Huwaila | Al Dabb'iya | Sahil | Shah | Upper Zakum | Lower Zakum | Umm Shaif | Satah | Nasr | Umm Al Dalkh | Satah Al Razboot (SARB) | Umm Lulu | Abu Al Bukhoosh | Bu Haseer | Belbazem | Umm Al Salsal | Umm Al Dholou | Arzanah | Nahaidiin | Bin Hadi | Gezira | Muhaymat | Sila | Hail (ADOC) | Mubarraz | Umm Al-Anbar | Neewat Al-Ghalan | Bunduq | Haliba | Fateh | South-West Fateh | Falah | Rashid | Jalilah | Margham | Sajaa | Kahaif | Mahani", "producing", "运营商资料截至2025年／再次复核2026-09-28", "中", "逐资产重查后，运营商仍把该资产列入当前上游运营或近年已投产；但缺少同一观察日的逐田实时遥测，故维持中置信度。")
_assign_status("阿联酋", "Bab | Bu Hasa | Bida Al-Qemzan | Rumaitha | Shanayel | Asab | Qusahwira | Mender | Al Nouf | Jumaylah", "producing", "2025年", "高", "ADNOC 2025可持续发展报告把这十个具名油田列入Onshore特许区，并明确该特许区的作业类型为开采与生产；报告不披露逐田日产量。", "https://reports.adnoc.ae/e/sustainability-report-2025-mobile")
_assign_status("阿联酋", "Belbazem Offshore Block", "producing", "2024-03-27", "高", "ADNOC公告明确Belbazem海上区块已实现首产；45千桶/日为三区块目标产能，不能作为当期实产或分配给三个组成田。", "https://adnoc.ae/en/news-and-media/press-releases/2023/adnoc-announces-first-production-from-belbazem-offshore-block/")
_assign_status("阿联酋", "Ghasha | Dalma | Shuweihat | Ghasha Concession | SARB Deep Gas | Hail (ADNOC Ghasha) | Bab Gas Cap | Ruwais Diyab | Hedebah", "development", "2025—2026年项目资料", "高", "公开资料将其列为开发、建设或扩建项目；目标产量不等于当前实产。")
_assign_status("阿联酋", "Moveyeid", "storage", "2026-09-28审计", "高", "SNOC明确其成熟气田已转为储气用途。")
_assign_status("阿联酋", "Saleh", "ceased", "2024-11-05／复核2026-09-28", "高", "RAK Petroleum Authority披露对Saleh田六个平台九口井开展封堵弃置（P&A），不再按历史产量视为在产。", "https://www.linkedin.com/posts/rakpa_collaboration-adipec2024-rakpa-activity-7259475442305286144-qSf6")
_assign_status("阿联酋", "Umm Al Quwain", "ceased", "2025年资产报告／复核2026-09-28", "中", "当前已停产资产报告把Umm Al Qaiwain列入ceased fields，公开资产资料亦称已停产并弃置。", "https://www.woodmac.com/reports/upstream-oil-and-gas-united-arab-emirates-ceased-fields-75021668/")

# 伊拉克：把2025—2026运营商／新闻与EITI参考年分开；历史表不伪装成实时状态。
_assign_status("伊拉克", "Rumaila | West Qurna-1 | West Qurna-2 | Zubair | Majnoon | Halfaya | Gharraf | Badra | Ahdab | East Baghdad | Nahr Umar | Nassiriya | Kirkuk | Bai Hassan | Jambur | Khabbaz | Qayyarah | Shaikan | Atrush | Sarsang | Swara Tika | East Swara Tika | Khurmala | Faihaa | Fakkah | Bazerkan | Abu Gharb | Luhais | Subba | Tuba | Ajil | Hamrin | Naft Khana | Amara | Noor | Safiya", "producing", "2023—2026年最后可核实公开时点／再次复核2026-09-28", "中", "逐资产重查后，运营商、EITI或近期报道仍支持生产属性；2026年冲突造成的国家或区域减产不下推为每个油田停产。")
_assign_status("伊拉克", "Tawke | Peshkabir", "producing", "2025年", "高", "DNO当前生产与储量页面及年度资料明确Tawke许可证的Tawke、Peshkabir两田在2025年贡献生产；披露的是许可证合计，不能拆成两田日产量。", "https://www.dno.no/en/operations/production-and-reserves/")
_assign_status("伊拉克", "Taq Taq | Sarta", "ceased", "2023-12-01", "高", "运营商披露停产或PSC终止；未找到后续复产的直接证据。")
_assign_status("伊拉克", "Artawi | Najma | Baeshiqa | Eridu (Block 10)", "non_producing", "2023—2025年最后可核实公开时点", "高", "EITI或运营商明确列为非生产／仅试井；开发活动不等于商业生产。")
_assign_status("伊拉克", "Ain Zalah | Batmah", "producing", "2022-03-30", "中", "摩苏尔大学石油与采矿工程学院对两田的现场记录逐名说明，从油井、处理和湿油分离直至外输管线观察了产油流程；证据为2022年现场时点，未外推为2026年实时状态。", "https://uomosul.edu.iq/petroleumengineering/%D8%B2%D9%8A%D8%A7%D8%B1%D8%A9-%D8%B9%D9%84%D9%85%D9%8A%D8%A9-5/")

# 伊朗：来源页可确认运营资产，但2026年战争和出口封锁使“当前运行强度”不确定。
_assign_status("伊朗", "Ahvaz | Marun | Aghajari | Gachsaran | Reg-e-Safid | South Azadegan | North Azadegan | Yadavaran | North Yaran | South Yaran | Azar | Darkhovin | Hendijan | Doroud | Foroozan | Soroush | Nowruz | Salman | Bibi Hakimeh | Karanj | Abuzar | Mansouri | Sepehr-Jufair | Parsi | Bahregansar | Sirri E | Masjed Soleyman | Pazanan | Kupal | Dehloran | Paranj | Nargesi | South Pars", "producing", "2024—2026年最后可核实公开时点", "中", "EIA、SHANA或资产资料列为开发／运营资产；2026年地区冲突下不把出口量变化下推成单田停复产。")
_assign_status("伊朗", "Hengam", "producing", "2025年资产状态／复核2026-09-28", "中", "当前油气资产跟踪器将Hengam列为Operating；逐田最新公开产量仍较旧。", "https://www.gem.wiki/Hengam_Oil_and_Gas_Field_(Iran)")
_assign_status("伊朗", "Band-e-Karkheh", "development", "2026-02-21", "高", "MAPNA宣布开发合同完成审批并进入实施阶段；目标增产不当作当前实产。", "https://mapnagroup.com/63236/mapna-officially-notified-of-ipc-contract-for-development-of-bande-karkheh-oil-field/?lang=en")
_assign_status("伊朗", "West Paydar", "producing", "2026年资产报告", "高", "当前资产报告明确该田已生产多年并进入2025—2030加速开发阶段。", "https://www.woodmac.com/reports/upstream-oil-and-gas-aban-and-west-paydar-ipc-54481312/")
_assign_status("伊朗", "Chehsmeh-Khosh", "producing", "2026-07-18", "高", "PEDEC信息显示CK-26井投产；2025年资料亦披露该田在产并增产。", "https://www.iranoilgas.com/trackers/?view=fieldstrackers")
_assign_status("伊朗", "Danan", "producing", "2025-03-04", "中", "MAPNA项目公司披露Danan开发项目的新脱盐装置已接入生产并提升处理能力。", "https://www.linkedin.com/posts/mapna-ogdc_%D9%85%D9%BE%D9%86%D8%A7-%D8%B5%D9%86%D8%B9%D8%AA%D9%86%D9%81%D8%AA-%D8%AA%D9%88%D8%B3%D8%B9%D9%87%D9%86%D8%AA%D9%88%DA%AF%D8%A7%D8%B2-activity-7303067532536500224-s-7Y")
_assign_status("伊朗", "Changuleh", "development", "2026-09-28", "高", "2025年成立的项目公司负责Changuleh全周期开发，目标产能尚不能作为当前产量。", "https://www.linkedin.com/company/mogdc")
_assign_status("伊朗", "Dalpari", "producing", "2026-07-18", "高", "PEDEC信息将Dalpari与Cheshmeh Khosh、East Paydar列入正在开发生产的项目组合并披露新井投产。", "https://www.iranoilgas.com/trackers/?view=fieldstrackers")
_assign_status("伊朗", "Paydar", "unknown", "2024-10-10／再次复核2026-09-28", "中", "EIA将Paydar与West Paydar分别列为NGL 3100拟收集伴生气的油田，确认它是独立资产；但该表描述的是拟建处理项目，不能单独证明Paydar当前正在产油，故保留待核实。", "https://www.eia.gov/international/content/analysis/countries_long/Iran/pdf/Iran%20CAB%202024.pdf")

# 科威特：KOC年报和商业投产公告；新发现不按在产处理。
_assign_status("科威特", "Burgan | Magwa | Ahmadi | Raudhatain | Sabriya | Bahra | Ratqa | Umm Niqa | South Ratqa | Minagish | Umm Gudair | Abdali | Wafra | Khafji | Mutriba | Kra-al-Maru", "producing", "FY2024/25—2026年最后可核实公开时点", "中", "KOC年报、分区运营资料或商业投产公告支持；2026年出口受扰不等于各田停产。")
_assign_status("科威特", "Nokhetha | Julaiah | Shaham", "discovered", "FY2024/25", "高", "KOC将其列为发现；试井流量不等于持续商业生产。")

# 卡塔尔：2024逐田平均、当前E&P页及延长至2027年的开发生产协议。
_assign_status("卡塔尔", "Al Shaheen | Dukhan | Al-Rayyan | Al-Khaleej | Idd El-Sharqi | Karkara | Maydan Mahzam | Bul Hanine | Al-Murjan | North Field | A-Structures (A-North / A-South) | A-North | A-South", "producing", "2024年平均／协议期至2027年", "高", "QatarEnergy逐田产量、当前E&P资料或有效开发生产协议支持。")

# 阿曼：运营商2024—2025资料确认绝大多数生产资产；发现田单列。
_assign_status("阿曼", "Mukhaizna | Yibal | Natih | Fahud | Qarn Alam | Marmul | Nimr | Lekhwair | Bahja | Harweel | Amal | Zalzala | Haima West | Al Noor | Nimr-A | Nimr-E | Block 5 (Daleel) | Daleel | Shadi | Bushra | Mazoon | Furat | Thahab | Block 9 (Oman) | Block 27 (Oman) | Safah | Wadi Latham | Khamilah | Block 8 (Oman) | Block 7 (Oman) | Block 61 (Oman) | West Bukha | Bukha | Sahma | Abu Butabul | Khazzan | Ghazeer", "producing", "2024—2026年最后可核实公开时点／再次复核2026-09-28", "中", "逐资产重查后，PDO、OQEP、Oxy或Daleel资料仍支持生产资产／生产区块属性；区块合计不拆给单田。")
_assign_status("阿曼", "Block 50 (Masirah) | Yumna", "producing", "2026年3月", "高", "Masirah Oil逐月公告明确Yumna在2026年3月31天生产期平均742桶/日，并说明其为Block 50运营商且持有100%权益；该值属于Yumna单田，不反推区块内其他资产。", "https://www.masirahoil.om/post/production-update-march-2026")
_assign_status("阿曼", "Bisat | Block 60 (Oman)", "producing", "2025-12-31", "高", "OQEP 2025年报确认Bisat C扩建投运，Block 60年末总产量超过70千桶油当量/日；区块合计与处理能力均不拆给Bisat单田。", "https://oqep.om/UploadsAll/IRFiles/1781008603725OQEP_2025_Annual_Report.pdf")
_assign_status("阿曼", "Budour Northeast | Wadi Aswad North | Safah North B", "discovered", "2024—2026年最后可核实公开时点", "中", "运营商列为发现或待开发，未取得商业生产直接证据。")

# 巴林。
_assign_status("巴林", "Bahrain Field (Awali) | Abu Safah", "producing", "2025年运营资料／2026-09-28审计", "中", "Bapco当前上游资料和跨境田资料支持生产属性；产能不等于实际日产量。")

# 也门：有历史生产和设施证据，但安全局势下不把旧区块计划写成当前在产。
_assign_status("也门", "Block 14 (Masila) | Block 10 (East Shabwa)", "temporarily_suspended", "2025-12-01／复核至2026-09-28", "中", "PetroMasila声明因安全局势全面停止Block 14生产炼制，并同时停止Block 10生产；未找到其后复产的直接公告。", "https://en.ypagency.net/377792")
_assign_status("也门", "Block 32 (Hawareem) | Tasour | Godah", "non_producing", "2015-03-31／复核至2026-09-28", "中", "DNO官方公告因安全恶化暂停Block 32生产；其后未找到复产证据，故按当前非生产处理而非沿用历史产量。", "https://www.dno.no/en/investors/announcements/dno-asa-yemen-operations-update/")
_assign_status("也门", "Block 18 (Marib) | Alif", "producing", "运营商网页复核2026-09-28", "高", "SEPOC称其为也门第二大产油商，Block 18生产设施页明确Alif等16田原油流入处理系统。", "https://sepocye.com/en/DefaultDET.aspx?SUB_ID=81")
_assign_status("也门", "Block 5 (Jannah)", "producing", "运营商网页复核2026-09-28", "高", "JHOC当前运营页明确Block 5原油在Halewah中央处理设施稳定并达到管输规格。", "https://www.jhocyemen.com/our-operations/")
_assign_status("也门", "Block S2 (Uqlah) | Habban", "temporarily_suspended", "2023年中／报告更新至2025-11", "高", "当前资产报告明确Block S2生产在2023年中再次暂停；Habban是该区块唯一油田。", "https://www.woodmac.com/reports/upstream-oil-and-gas-al-uqlah-block-s2-1303840")
_assign_status("也门", "Block 9 (Malik) | Hiswah (Haswa) | Alroidhat (Al-Rowedhat)", "producing", "运营商网页复核2026-09-28", "中", "当前运营资料称Block 9约产6500桶/日，并明确Hiswah与Al Roidhat为生产体系组成田。", "https://www.petsec.com.au/operations/yemen-leases/")
_assign_status("也门", "Qarn Qeamah", "discovered", "运营商网页复核2026-09-28", "中", "运营商将Qarn Qaymah列为气、凝析油和原油的contingent discovery，而非当前生产田。", "https://www.calvalleypetroleum.com/current-production/")

# 叙利亚：2026年可确认作业区和Al-Omar；作业区合计不能证明八个组成田逐一在产。
_assign_status("叙利亚", "Rmeilan Sector One | Al-Omar", "producing", "2026-02-11／2026-02-22", "高", "近期现场采访给出作业区或单田实际产量。")
_assign_status("叙利亚", "Al-Tanak", "producing", "2026-01-25", "高", "SANA确认来自Al-Omar与Al-Tanak的原油已运抵Baniyas炼厂。", "https://sana.sy/en/economic/2292355/")
_assign_status("叙利亚", "Al-Jafra", "development", "2026-01-21", "中", "SPC技术团队现场检查Al-Jafra并评估恢复、改造和潜在合作，当前更适合标为再开发而非直接推定稳定在产。", "https://en.zamanalwsl.net/news/article/70852/")
_assign_status("叙利亚", "Al-Ward", "producing", "2026年资产状态", "中", "当前油气资产跟踪器将Al-Ward列为operating；缺少可靠逐田日产量。", "https://www.gem.wiki/Ward_Oil_Field_(Syria)")
_assign_status("叙利亚", "Al-Taym", "producing", "2026-01-26", "高", "SANA称技术团队正在Al-Taym等田监督开采、装运和运输作业。", "https://sana.sy/en/economic/2292574/")
_assign_status("叙利亚", "Rmeilan | Suwaydiya", "producing", "2026-03-04", "高", "SANA确认SPC已在Rmeilan、Suwaydiya及Hasakeh其他点位开始原油开采。", "https://sana.sy/es/economy/2298482/")
_assign_status("叙利亚", "Qarachok | Hamza | Alyan | Sazabeh | Ode", "development", "2026-08-04／复核2026-09-28", "中", "HKN Syria列明已接手并运营八个田；现场工作以修井、新钻井和设施修复为主，因此按开发／复产阶段处理，不把作业区总量下推。", "https://hknsyria.com/")
_assign_status("叙利亚", "Tigris", "producing", "2026-04-09", "中", "叙利亚官方通讯社称哈塞克省Dejla（Tigris）油田群产量提高30%，并说明其属于Rmeilan综合体；因报道使用复数油田群而目录记录为单一具名资产，保留中置信度。", "https://sana.sy/es/economy/2304911/")

# 以色列：2026年停产后复产信息逐田处理；Tanin尚无商业生产证据。
_assign_status("以色列", "Heletz", "producing", "2022年研究／2026-09-28审计", "中", "公开研究称该田仍被开采，但没有实时产量。")
_assign_status("以色列", "Meged", "producing", "运营商网页审计2026-09-28", "中", "运营商网页说明自2010年起生产并列累计产量；没有逐日实时值。", "https://www.givot.co.il/en/")
_assign_status("以色列", "Leviathan | Tamar", "producing", "2026-07-06", "高", "以色列能源部门近期信息确认Tamar供应国内、Leviathan承担出口；Leviathan在4月已从临时停产中复产。", "https://www.reuters.com/world/middle-east/israel-launches-tender-search-more-natural-gas-mediterranean-2026-07-06/")
_assign_status("以色列", "Karish", "producing", "2026-09-09", "高", "Energean在4月恢复生产，9月半年报称以色列产量已强劲恢复。", "https://www.reuters.com/business/energy/uks-energean-posts-higher-half-year-profit-maintains-output-forecast-after-2026-09-09/")
_assign_status("以色列", "Tanin", "development", "2026-09-28审计", "中", "资产属于Energean开发组合，但未找到Tanin商业生产的直接证据。", "https://www.reuters.com/business/energy/energean-invest-12-bln-develop-israel-katlan-gas-project-2024-07-23/")

# 土耳其：TPAO公开资产及Gabar增产资料。
_assign_status("土耳其", "Raman | Batı Raman | Garzan | Şelmo | Gabar", "producing", "2025—2026年最后可核实公开时点", "中", "TPAO／政府资料列为生产资产；未把全国或Gabar油田群合计拆给其他单田。")

# 埃及：棕地包件是资产名录而非当前生产快照。
_assign_status("埃及", "Belayim", "producing", "2026年资产状态", "高", "当前油气资产跟踪器将Belayim Marine与Belayim Land均列为operating。", "https://www.gem.wiki/Belayim_Marine_%26_Belayim_Land_Oil_Project_(Egypt)")
_assign_status("埃及", "Shukheir Offshore (Shukheir Bay) | Shukheir Offshore (Gamma) | Gazwarina | Ras El Ush | East Zeit (E. Zeit) | Ashrafi", "producing", "FY2025/26／复核2026-09-28", "中", "EGPC棕地轮次将其列为OSOCO生产棕地；OSOCO FY2025/26仍有7100桶油当量/日合计产量，但不得拆成各田日产量。", "https://egyptoil-gas.com/news/osoco-raises-output-to-1-7-mmboe-in-fy-2025-26/")
_assign_status("埃及", "Zeit Bay | Ras Budran", "producing", "FY2025/26", "高", "SOCO FY2025/26披露持续生产和在Ras Budran增加生产井；设施同时服务Zeit Bay。", "https://egyptoil-gas.com/news/suez-oil-company-increased-proven-reserves-by-3-9-mmbbl/")
_assign_status("埃及", "Wadi El Sahl Development Area", "development", "2025-11-25", "高", "埃及批准法律授权与Lukoil签署该开发区勘探、开发和生产合同，尚不以目标或发现量当作当前商业产量。", "https://www.egypttoday.com/Article/3/143692/El-Sisi-ratifies-law-on-oil-exploration-and-development-in")

SUPPLEMENT.register_statuses(_assign_status)
RECONCILED.register_statuses(_assign_status)
CONTINUATION.register_statuses(_assign_status)
for review in REVIEWS:
    review.register_statuses(_assign_status)
# 纠正旧状态，明确每个证据时点；覆盖更新而不是重复登记。
def _revise_status(country, names, state, as_of, confidence, basis, url):
    for name in names.split(" | "):
        _STATUS_AUDIT.pop((country, name))
    _assign_status(country, names, state, as_of, confidence, basis, url)

CONTINUATION.revise_statuses(_revise_status)
_revise_status("阿联酋", "Hedebah", "producing", "2025-11-04", "高",
               "SNOC披露首井已在发现后十个月投产；第二井当时计划接入，不填产量。",
               "https://www.snoc.ae/news/snoc-strengthens-sharjahs-energy-security-with-second-well-success-in-hedebah-field/")
_revise_status("伊拉克", "Atrush | Sarsang | Swara Tika | East Swara Tika", "temporarily_suspended", "2026-08-05公告；停产自07-20", "高",
               "ShaMaran Q2公告明确两资产7月20日起再次停产；Sarsang组成田按区块停产证据。9月材料的预计复产流量并非实际复产证明。",
               SOURCES["ShaMaran Q2 2026"])
_revise_status("伊拉克", "Tawke | Peshkabir", "producing", "2026-08 Q2报告", "高",
               "DNO Q2报告分别披露Tawke于06-28、Peshkabir于07-11复产；不以Q2均值代替当前值。",
               "https://www.dno.no/media/ezuglbal/q2-2026-interim-results-report.pdf")
_revise_status("伊拉克", "Taq Taq | Sarta", "historical_unverified", "2025参考年；2026-03年报", "中",
               "Genel 2025年报确认已退出Taq Taq和Sarta许可证；运营商退出不证明资产永久停产，2026逐田实绩待核。",
               "https://genelenergy.com/wp-content/uploads/190326_Genel-AR_web-1.pdf")
_revise_status("伊拉克", "Artawi", "development", "2025-09-15", "高",
               "TotalEnergies披露Artawi再开发项目施工，未来120/210千桶日为分期目标，不是当期实产。",
               "https://totalenergies.com/newsroom/iraq-totalenergies-launches-construction-final-two-major-projects-ggip/?lang=eng")

_catalog_keys = set(_asset_index)
for review in REVIEWS:
    review.revise_statuses(_revise_status)
_audited_keys = set(_STATUS_AUDIT)
if _catalog_keys != _audited_keys:
    missing = sorted(_catalog_keys - _audited_keys)
    extra = sorted(_audited_keys - _catalog_keys)
    raise ValueError(f"状态审计覆盖不完整：missing={missing}; extra={extra}")

for asset in ASSETS:
    audit = _STATUS_AUDIT[(asset["country"], asset["name"])]
    asset.update(audit)
    asset["status_audit_date"] = "2026-09-28"
    asset["status_audit_result"] = (
        "已核实（带时点）"
        if audit["operating_status_confidence"] == "高"
        else "再次核实（证据存在时点或层级限制）"
        if audit["operating_status_confidence"] == "中"
        else "需持续核实"
    )


# 标记适合区域供给研判的战略资产层级；地图和目录仍完整展示所有公开资产记录。
# 此标记不要求资产具备坐标，以便单独说明战略节点的定位状态。
_STRATEGIC_STATUSES = {
    "producing", "restoration_unconfirmed", "partially_operating", "temporarily_suspended", "development",
    "historical_unverified", "unknown",
}
for asset in ASSETS:
    key = (asset["country"], asset["name"])
    asset["strategic_default"] = bool(
        asset["map_default"]
        and asset["operating_status"] in _STRATEGIC_STATUSES
        and (
            asset["value"] is not None
            or asset["asset_level"] != "field"
            or key in STRATEGIC_STANDALONE_ASSETS
        )
    )
    if asset["map_role"] == "strategic_standalone" and not asset["strategic_default"]:
        asset["map_role"] = "catalog_detail"
        asset["map_role_label"] = "目录补充资产（战略层级外）"

# 下载成功不等于数值已核验；审计日期不等于观测日期。
for asset in ASSETS:
    if asset["name"] == "Belayim" and asset["country"] == "埃及":
        asset["map_is_proxy"] = True
        asset["map_coordinate_precision"] = "Belayim Marine代表点；105千桶/日是Belayim历史整体口径"
    asset.setdefault("aliases", [])
    if asset["source"] == "QatarEnergy" and asset["value"] is not None:
        asset["numeric_audit"] = "原始2025-11演示第12页2024均值已核；不是2026实绩"
    if asset["name"] in {"Taq Taq", "Sarta"}:
        asset["numeric_audit"] = "Genel 2024-01原表2023毛产量已核；非权益产量或当前值"
    asset.setdefault("numeric_audit", "数值缺失；不可估计当前产量" if asset["value"] is None
                     else "保留来源期数据；详见2026-09-30逐行审计，非实时实绩")
    asset["data_audit_date"] = "2026-09-30"
    asset["freshness_note"] = ("没有当前逐资产实绩；缺失不等于零" if asset["value"] is None else
                              "数值仅对应数据日期；复核日不是观测日，不能视作2026-09-30实绩")

additional_measurements(ASSETS)
CONTINUATION.finish_review(ASSETS)
finish_reviews(ASSETS)
attach_gem_production_candidates(ASSETS)
apply_public_metadata(ASSETS)
finish_production_recheck(ASSETS, OUTPUT_METRIC_TYPES)

# Resolve the former dashed markers only from independently reviewed field/well
# locations. Keep rejected proxy evidence in the dated audit, not in map exports.
_coordinate_review = data_store.read_json("data/coordinate_recheck.json")
for _row in _coordinate_review["records"]:
    _asset = _asset_index[(_row["country"], _row["name"])]
    _coordinate = _row["coordinate"]
    _asset["coordinate_review_date"] = _coordinate_review["review_date"]
    _asset["coordinate_review_reason"] = _row["reason"]
    _asset["map_is_proxy"] = False
    _asset["map_drawable"] = _coordinate is not None
    if _coordinate:
        _asset["map_lat"] = _coordinate["lat"]
        _asset["map_lon"] = _coordinate["lon"]
        _asset["map_coordinate_precision"] = _coordinate["precision"]
        _asset["coordinate_source"] = _coordinate["source"]
        _asset["coordinate_source_url"] = _coordinate["url"]
    else:
        _asset["map_lat"] = _asset["map_lon"] = None
        _asset["map_coordinate_precision"] = "独立田级坐标待核；仅列目录"
        _asset["coordinate_source"] = "2026-10-06再次检索未确认独立位置；原代理点已撤回"
        _asset["coordinate_source_url"] = None


def _numeric_value(value: Any) -> tuple[Decimal | None, str]:
    """Separate a numeric amount from an approximate/bound qualifier."""
    if value is None:
        return None, ""
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return Decimal(str(value)), ""
    match = re.fullmatch(
        r"\s*(约|~|≥|≤|>|<)?\s*([+-]?[\d,]+(?:\.\d+)?)\s*", str(value))
    if not match:
        return None, ""
    try:
        amount = Decimal(match.group(2).replace(",", ""))
    except InvalidOperation:
        return None, ""
    qualifier = "约" if match.group(1) == "~" else (match.group(1) or "")
    return amount, qualifier


from htfa.monitoring.energy_supply.asset_table_recheck import apply as apply_asset_table_recheck
apply_asset_table_recheck(ASSETS)

for asset in ASSETS:
    raw_value = asset.get("value")
    amount, qualifier = _numeric_value(raw_value)
    asset["value_raw"] = raw_value
    asset["value_numeric"] = amount
    asset["value_qualifier"] = asset.get("value_qualifier") or qualifier
    for measurement in asset.get("additional_measurements", []) + asset.get("aggregate_references", []):
        raw_measurement = measurement.get("value")
        measurement_amount, measurement_qualifier = _numeric_value(raw_measurement)
        measurement["value_raw"] = raw_measurement
        measurement["value_numeric"] = measurement_amount
        measurement["value_qualifier"] = (
            measurement.get("value_qualifier") or measurement_qualifier)

# Versioned Python rules build the seed; the app and report consume the same
# persisted catalog, including source dates and exact decimal measurements.
if not data_store.read_only():
    data_store.save_catalog("assets", ASSETS)
ASSETS = data_store.load_catalog("assets")
