"""Explicit construction of the reviewed oil and gas catalog."""

import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

from htfa.monitoring.energy_supply.processing import asset_spec as spec
from htfa.monitoring.energy_supply.processing.asset_labels import (
    ASSET_LEVEL_LABELS,
    COMMODITY_LABELS,
    OPERATING_STATUS_LABELS,
    OUTPUT_METRIC_TYPES,
)
from htfa.monitoring.energy_supply.processing.evidence import evidence_scope, read_json


def build_catalog():
    """Build fresh records from dated evidence without writing a database."""
    with evidence_scope():
        SOURCES = deepcopy(spec.SOURCES)

        record = spec.record

        # 仅在来源给出明确的单一资产口径时填写 value；区块／项目数值不可归给组成油田。
        ASSETS = spec.base_assets()

        # 本轮原始报告复核；补充目录与数字在元数据生成之前应用。
        import htfa.monitoring.energy_supply.processing.continuation_assets as CONTINUATION
        import htfa.monitoring.energy_supply.processing.reconciled_assets as RECONCILED
        import htfa.monitoring.energy_supply.processing.supplemental_assets as SUPPLEMENT
        from htfa.monitoring.energy_supply.processing.asset_reviews import (
            _evidence,
            apply_production_recheck,
            apply_public_metadata,
            attach_gem_production_candidates,
            finish_production_recheck,
            finish_reviews,
            public_reference_coordinates,
        )
        from htfa.monitoring.energy_supply.processing.audited_measurements import (
            additional_measurements,
            apply_annual_volumes,
        )

        REVIEWS = _evidence()["REVIEWS"]
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
                asset.update(
                    aliases=["Darquain", "Darkhoveyn"],
                    lat=30.7289,
                    lon=48.2934,
                    coordinate_precision="GEM所列近似田中心；非边界",
                    note="Darkhovin / Darquain为同田异名，已合并；不重复计数。",
                )
            if asset["country"] == "伊拉克" and asset["name"] in {"Tawke", "Peshkabir"}:
                asset.update(
                    value="0.363" if asset["name"] == "Tawke" else "0",
                    metric_type="actual_output_boe",
                    unit="千桶油当量/日",
                    data_date="2026年第二季度平均",
                    source="DNO Q2 2026",
                    source_url="https://www.dno.no/media/ezuglbal/q2-2026-interim-results-report.pdf",
                    numeric_audit="运营商Q2表原值已复核；BOE不转换为原油桶",
                    note="DNO Q2 2026第4页：Tawke 363 boe/d、Peshkabir 0 boe/d，100%毛口径。两田分别6月28日、7月11日恢复；季度零不等于当前停产。",
                )
            if asset["name"] == "Marjan":
                asset.update(
                    source="Aramco Annual Report 2025",
                    source_url="https://www.aramco.com/-/media/publications/corporate-reports/reports-and-presentations/2025/fy/saudi-aramco-ara-2025-english.pdf",
                    numeric_audit="2025年报原文300 mbpd已复核；新增产能，非实产",
                )
            if asset["name"] == "SARB Deep Gas":
                asset.update(
                    source="ADNOC SARB Deep Gas FID",
                    source_url="https://www.adnoc.ae/en/news-and-media/press-releases/2026/adnoc-announces-final-investment-decision-for-the-sarb-deep-gas-development/",
                    note="2026-01-07 FID公告：目标最高200百万标准立方英尺/日，非已投产实绩。",
                )
            if asset["name"] == "Bab Gas Cap":
                asset.update(
                    source="TotalEnergies Bab Gas Cap 2026",
                    source_url="https://www.sec.gov/Archives/edgar/data/879764/000110465926079516/tm2619405d1_ex99-6.htm",
                    data_date="2026-06-24特许区公告",
                    note="开发目标1.5十亿立方英尺/日，非当前实产；已更换不能支撑数字的通用资产页。",
                )
            if asset["name"] == "Upper Zakum":
                asset.update(
                    value="1,500",
                    metric_type="target_capacity",
                    data_date="2026-02-04承包商业绩会规划口径",
                    source="NMDC Energy FY25 Results Call",
                    source_url="https://www.nmdc-energy.com/assets/files/earnings-results/NMDC%20Energy%20FY25%20Results%20Conference%20Call%20020426%20final.pdf",
                    numeric_audit="承包商原始会议稿已核；目标，不是运营商实产",
                    note="NMDC Energy CEO原始会议稿披露Upper Zakum计划由100万桶/日增至150万桶/日；替换2017年100万目标。该值是扩产规划，未据承包商口述填当前实产。",
                )
            if asset["name"] == "Bahrain Field (Awali)":
                asset["asset_type"] = "油田"
            if asset["name"] == "Margham":
                asset.update(
                    source="DUSUP Margham",
                    source_url="https://www.dusup.ae/supply-operations/margham-gas-plant/",
                )
            if asset["name"] == "Hedebah":
                asset.update(
                    source="SNOC Hedebah 2025",
                    source_url="https://www.snoc.ae/news/snoc-strengthens-sharjahs-energy-security-with-second-well-success-in-hedebah-field/",
                )
            if asset["name"] == "Umm Niqa":
                asset.update(
                    value=None,
                    metric_type="undisclosed",
                    unit=None,
                    data_date=None,
                    numeric_audit="历史22.14值的引用PDF失效；暂撤回待恢复原表",
                    note=asset["note"]
                    + " 2026-09-30原引用2023/24年报HTTP404，未恢复原表前不展示22.14千桶/日。",
                )

        apply_production_recheck(ASSETS)

        # 分层审计：层级字段独立于资产类型，防止区块／油田群合计与单田重复计算。

        LEVEL_OVERRIDES = deepcopy(spec.LEVEL_OVERRIDES)

        PARENT_RELATIONSHIPS = deepcopy(spec.PARENT_RELATIONSHIPS)

        # 官方资料直接给出组成区域、但目录不需要为每个细分区另建地图节点的情形。
        NAMED_CONSTITUENTS = deepcopy(spec.NAMED_CONSTITUENTS)

        # 没有公开田级数值、但对区域供给具有代表性的独立资产，用于战略层级分类。
        STRATEGIC_STANDALONE_ASSETS = deepcopy(spec.STRATEGIC_STANDALONE_ASSETS)

        # 地图补点单独记录证据和精度，不改写原始目录来源。优先采用公开WGS84资产点位；
        # 区块只有组成田或设施点时，明确标为近似代表点，不能理解为区块边界中心。
        COORDINATE_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
            ("沙特阿拉伯", "Abu Jifan"): {
                "lat": 25.0631,
                "lon": 48.0304,
                "precision": "Khurais综合体内公开近似点（WGS84）",
                "source": "Global Energy Monitor — Abu Jifan",
                "url": "https://www.gem.wiki/Abu_Jifan_Oil_and_Gas_Field_%28Saudi_Arabia%29",
            },
            ("沙特阿拉伯", "Mazalij"): {
                "lat": 25.0631,
                "lon": 48.0304,
                "precision": "Khurais综合体内公开近似点（WGS84）",
                "source": "Global Energy Monitor — Mazalij",
                "url": "https://www.gem.wiki/Mazalij_Oil_and_Gas_Field_%28Saudi_Arabia%29",
            },
            ("沙特阿拉伯", "Abu Hadriya"): {
                "lat": 27.312,
                "lon": 49.0051,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Abu Hadriya",
                "url": "https://www.gem.wiki/Abu_Hadriya_Oil_Field_%28Saudi_Arabia%29",
            },
            ("沙特阿拉伯", "Fadhili"): {
                "lat": 26.9807,
                "lon": 49.1735,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Fadhili",
                "url": "https://www.gem.wiki/Fadhili_Oil_Field_%28Saudi_Arabia%29",
            },
            ("沙特阿拉伯", "Harmaliyah"): {
                "lat": 24.6291,
                "lon": 49.4985,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Harmaliyah",
                "url": "https://www.gem.wiki/Harmaliyah_Oil_and_Gas_Field_%28Saudi_Arabia%29",
            },
            ("沙特阿拉伯", "Hawtah"): {
                "lat": 22.9678,
                "lon": 46.8995,
                "precision": "Hawtah油田机场设施代表点（近似，非油田中心）",
                "source": "OpenStreetMap/GeoNames — Hawtah Airport",
                "url": "https://mapcarta.com/36033010",
                "proxy": True,
            },
            ("沙特阿拉伯", "Sakab"): {
                "lat": 23.92,
                "lon": 49.08,
                "precision": "Haradh油田区域代表点（Sakab位于其东南；非井位）",
                "source": "Saudi Aramco discovery release / Haradh public coordinate",
                "url": "https://www.aramco.com/en/news-media/news/2020/saudi-aramco-announces-new-oil-and-gas-discoveries",
                "proxy": True,
            },
            ("沙特阿拉伯", "Zumul"): {
                "lat": 22.48,
                "lon": 53.78,
                "precision": "鲁卜哈利新发现区域代表点（借用Shaybah区域；非井位）",
                "source": "Saudi Aramco discovery release / Shaybah regional anchor",
                "url": "https://www.aramco.com/en/news-media/news/2020/saudi-aramco-announces-new-oil-and-gas-discoveries",
                "proxy": True,
            },
            **{
                ("沙特阿拉伯", name): {
                    "lat": 25.43,
                    "lon": 48.82,
                    "precision": "沙特东部省新发现区域代表点（非油田中心或井位）",
                    "source": "Saudi Press Agency announcement — Eastern Region (reported by Reuters)",
                    "url": "https://www.reuters.com/business/energy/saudi-arabia-discovers-14-oil-natural-gas-fields-state-news-agency-says-2025-04-09/",
                    "proxy": True,
                }
                for name in ("Jabu", "Sayahid", "Ayfan")
            },
            **{
                ("沙特阿拉伯", name): {
                    "lat": 25.43,
                    "lon": 48.82,
                    "precision": "沙特东部省新发现区域代表点（非油田中心或井位）",
                    "source": "Saudi Press Agency announcement — Eastern Province (reported by Reuters)",
                    "url": "https://www.reuters.com/world/middle-east/saudi-energy-minister-announces-discovery-multiple-oil-gas-fields-2024-07-01/",
                    "proxy": True,
                }
                for name in ("Ladam", "Faruq")
            },
            **{
                ("沙特阿拉伯", name): {
                    "lat": 22.48,
                    "lon": 53.78,
                    "precision": "鲁卜哈利新发现区域代表点（非油田中心或井位）",
                    "source": "Saudi Press Agency announcement — Empty Quarter (reported by Reuters)",
                    "url": "https://www.reuters.com/business/energy/saudi-arabia-discovers-14-oil-natural-gas-fields-state-news-agency-says-2025-04-09/",
                    "proxy": True,
                }
                for name in ("Nuwayr", "Damda", "Qurqas")
            },
            ("阿联酋", "Hail (ADNOC Ghasha)"): {
                "lat": 24.368,
                "lon": 53.413,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Hail",
                "url": "https://www.gem.wiki/Hail_Oil_Field_%28United_Arab_Emirates%29",
            },
            ("阿联酋", "Sajaa"): {
                "lat": 25.3778,
                "lon": 55.6826,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Sajaa",
                "url": "https://www.gem.wiki/Sajaa_Oil_and_Gas_Field_%28United_Arab_Emirates%29",
            },
            ("阿联酋", "Kahaif"): {
                "lat": 25.1941,
                "lon": 55.7993,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Kahaif",
                "url": "https://www.gem.wiki/Kahaif_Oil_and_Gas_Field_%28United_Arab_Emirates%29",
            },
            ("阿联酋", "Umm Al Quwain"): {
                "lat": 25.5639,
                "lon": 55.4466,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Umm Al Qaiwain",
                "url": "https://www.gem.wiki/Umm_Al_Qaiwain_%28UAQ%29_Gas_Field_%28United_Arab_Emirates%29",
            },
            ("阿联酋", "Moveyeid"): {
                "lat": 25.3778,
                "lon": 55.6826,
                "precision": "Sajaa—Moveyeid—Kahaif资产群代表点（非Moveyeid井位）",
                "source": "SNOC asset grouping / Sajaa public coordinate",
                "url": "https://www.snoc.ae/operations/",
                "proxy": True,
            },
            ("阿联酋", "Mahani"): {
                "lat": 25.15,
                "lon": 55.78,
                "precision": "Area B公开位置图估读（近似，非井位）",
                "source": "ENI / GEO ExPro — Mahani-1 location map",
                "url": "https://geoexpro.com/uae-sharjah-gas-discovery/",
                "proxy": True,
            },
            ("阿联酋", "Hedebah"): {
                "lat": 25.442,
                "lon": 55.754,
                "precision": "按Sajaa处理厂东北约10公里推算（区域代表点）",
                "source": "SNOC Hedebah project description / Sajaa public coordinate",
                "url": "https://www.snoc.ae/operations/",
                "proxy": True,
            },
            ("阿联酋", "Saleh"): {
                "lat": 26.14,
                "lon": 55.71,
                "precision": "Saleh—Ras al-Khaimah输气管线海上起点（近似）",
                "source": "Global Energy Monitor — Saleh–Ras al-Khaimah gas pipeline",
                "url": "https://www.gem.wiki/Saleh%E2%80%93Ras_al-Khaimah_gas_pipeline",
                "proxy": True,
            },
            ("伊拉克", "Khurmala"): {
                "lat": 35.97778,
                "lon": 43.76306,
                "precision": "公开地图油田设施点位（OpenStreetMap；近似）",
                "source": "OpenStreetMap/GeoNames — Khurmala Oilfield",
                "url": "https://mapcarta.com/30858796",
            },
            ("伊拉克", "Naft Khana"): {
                "lat": 34.1814,
                "lon": 45.4085,
                "precision": "跨境油田项目公开近似点（WGS84）",
                "source": "Global Energy Monitor — Khanah / Naft Khana",
                "url": "https://www.gem.wiki/Khanah_Oil_Field_%28Iraq%29",
            },
            ("伊拉克", "Sarta"): {
                "lat": 36.377,
                "lon": 44.0002,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Sarta",
                "url": "https://www.gem.wiki/Sarta_Oil_and_Gas_Field_%28Iraq%29",
            },
            ("伊拉克", "Baeshiqa"): {
                "lat": 36.45046,
                "lon": 43.34977,
                "precision": "Baeshiqa许可证区同名城镇代表点（非油田中心）",
                "source": "DNO license description / GeoNames — Bashiqa",
                "url": "https://www.dno.no/en/operations/kurdistan-region-of-iraq/",
                "proxy": True,
            },
            ("伊拉克", "Eridu (Block 10)"): {
                "lat": 30.73,
                "lon": 45.99,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Eridu",
                "url": "https://www.gem.wiki/Eridu_Oil_Field_%28Iraq%29",
            },
            ("伊拉克", "Ajil"): {
                "lat": 35.019,
                "lon": 43.744,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Ajeel",
                "url": "https://www.gem.wiki/Ajeel_Oil_and_Gas_Field_%28Iraq%29",
            },
            ("伊拉克", "Ain Zalah"): {
                "lat": 36.71667,
                "lon": 42.6,
                "precision": "公开地名数据库油田点位（WGS84）",
                "source": "GeoNames/Mapcarta — Ain Zalah Oil Field",
                "url": "https://mapcarta.com/12542254",
            },
            ("伊拉克", "Batmah"): {
                "lat": 36.66667,
                "lon": 42.78333,
                "precision": "公开地名数据库油田点位（WGS84）",
                "source": "GeoNames/Mapcarta — Butmah Oil Field",
                "url": "https://mapcarta.com/12540670",
            },
            ("伊拉克", "Hamrin"): {
                "lat": 34.93545,
                "lon": 43.84327,
                "precision": "公开地名数据库油田点位（WGS84）",
                "source": "GeoNames/Mapcarta — Hamrin Oil Field",
                "url": "https://mapcarta.com/26089772",
            },
            ("伊拉克", "Amara"): {
                "lat": 31.7468,
                "lon": 47.0614,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Amara",
                "url": "https://www.gem.wiki/Amara_Oil_and_Gas_Field_%28Iraq%29",
            },
            ("伊拉克", "Noor"): {
                "lat": 31.796,
                "lon": 47.287,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Noor",
                "url": "https://www.gem.wiki/Noor_Oil_and_Gas_Field_%28Iraq%29",
            },
            ("伊拉克", "Safiya"): {
                "lat": 36.9216,
                "lon": 42.24094,
                "precision": "同名油田设施公开点（近似，非油田中心）",
                "source": "OpenStreetMap/Mapcarta — Safiya oil-field facility",
                "url": "https://mapcarta.com/N8571647117",
                "proxy": True,
            },
            ("伊朗", "Hengam"): {
                "lat": 26.4214,
                "lon": 55.9659,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Hengam",
                "url": "https://www.gem.wiki/Hengam_Oil_and_Gas_Field_%28Iran%29",
            },
            ("伊朗", "South Pars"): {
                "lat": 26.619125,
                "lon": 52.067964,
                "precision": "南帕尔斯／北方气田整体公开中心点（WGS84；近似）",
                "source": "South Pars / North Dome public coordinate",
                "url": "https://en.wikipedia.org/wiki/South_Pars/North_Dome_Gas-Condensate_field",
            },
            ("伊朗", "West Paydar"): {
                "lat": 32.1693,
                "lon": 47.5814,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Paydar West",
                "url": "https://www.gem.wiki/Paydar_West_Oil_and_Gas_Field_%28Iran%29",
            },
            ("伊朗", "Chehsmeh-Khosh"): {
                "lat": 32.2969,
                "lon": 47.7746,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Cheshmeh-Khosh",
                "url": "https://www.gem.wiki/Cheshmeh-Khosh_Oil_Field_%28Iran%29",
            },
            ("伊朗", "Danan"): {
                "lat": 32.614,
                "lon": 47.5312,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Danan",
                "url": "https://www.gem.wiki/Danan_Oil_Field_%28Iran%29",
            },
            ("伊朗", "Changuleh"): {
                "lat": 32.98,
                "lon": 46.47,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Changuleh",
                "url": "https://www.gem.wiki/Changuleh_Oil_Field_%28Iran%29",
            },
            ("伊朗", "Dalpari"): {
                "lat": 32.5293,
                "lon": 47.8673,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Dalpari",
                "url": "https://www.gem.wiki/Dalpari_Oil_Field_%28Iran%29",
            },
            ("伊朗", "Band-e-Karkheh"): {
                "lat": 31.44,
                "lon": 48.52,
                "precision": "公开区域图估读／Ahvaz西北约20公里（近似）",
                "source": "IranOilGas field map / published location description",
                "url": "https://www.iranoilgas.com/fields/details.aspx?id=1063",
                "proxy": True,
            },
            ("伊朗", "Paydar"): {
                "lat": 32.02,
                "lon": 47.72,
                "precision": "East Paydar公开区域图估读（近似，非井位）",
                "source": "IranOilGas — East Paydar field map",
                "url": "https://www.iranoilgas.com/fields/details.aspx?id=1089",
                "proxy": True,
            },
            ("科威特", "Nokhetha"): {
                "lat": 29.4162,
                "lon": 48.7026,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Nokhetha",
                "url": "https://www.gem.wiki/Nokhetha_Oil_and_Gas_Field_%28Kuwait%29",
            },
            ("科威特", "Julaiah"): {
                "lat": 28.824,
                "lon": 48.6894,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Julaiah",
                "url": "https://www.gem.wiki/Julaiah_Oil_and_Gas_Field_%28Kuwait%29",
            },
            ("科威特", "Mutriba"): {
                "lat": 29.763444,
                "lon": 47.224222,
                "precision": "官方地震勘探区中心坐标（WGS84；区域代表点）",
                "source": "Kuwait official seismic-survey tender coordinate",
                "url": "https://www.kockw.com/sites/EN/Pages/Profile/WhatWeDo/OilFields.aspx",
                "proxy": True,
            },
            ("科威特", "Shaham"): {
                "lat": 29.916667,
                "lon": 47.666667,
                "precision": "北科威特同名地理要素代表点（非油田中心）",
                "source": "GeoNames — Shaib Abu-Shaham / field-region description",
                "url": "https://www.geonames.org/387923/shaib-abu-shaham.html",
                "proxy": True,
            },
            ("科威特", "Kra-al-Maru"): {
                "lat": 29.435833,
                "lon": 47.327778,
                "precision": "西科威特同名地理要素代表点（近似）",
                "source": "GeoNames / MEES field-region description",
                "url": "https://www.geonames.org/285913/kra-al-maru.html",
                "proxy": True,
            },
            ("卡塔尔", "Al-Rayyan"): {
                "lat": 26.6591,
                "lon": 51.5725,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Al Rayyan",
                "url": "https://www.gem.wiki/Al_Rayyan_Oil_and_Gas_Field_%28Qatar%29",
            },
            ("卡塔尔", "Al-Murjan"): {
                "lat": 26.6591,
                "lon": 51.5725,
                "precision": "Al-Rayyan生产平台代表点（Al-Murjan经该平台生产）",
                "source": "QatarEnergy project description / Global Energy Monitor — Al Rayyan",
                "url": "https://www.qatarenergy.qa/en/WhatWeDo/Pages/ExplorationandProduction.aspx",
                "proxy": True,
            },
            ("卡塔尔", "A-Structures (A-North / A-South)"): {
                "lat": 25.0811,
                "lon": 52.4847,
                "precision": "Al-Karkara／A-Structures项目公开近似点（WGS84）",
                "source": "MarineLink — Al-Karkara/A-Structure",
                "url": "https://ports.marinelink.com/oilrigs/rig/alkarkaraastructure",
            },
            ("阿曼", "Block 9 (Oman)"): {
                "lat": 23.1614,
                "lon": 55.4485,
                "precision": "Safah／Wadi Latham组成田公开近似点（WGS84）",
                "source": "Global Energy Monitor — Safah/Wadi Latham",
                "url": "https://www.gem.wiki/Safah/Wadi_Latham_Oil_and_Gas_Field_%28Oman%29",
            },
            ("阿曼", "Safah"): {
                "lat": 23.1614,
                "lon": 55.4485,
                "precision": "Safah／Wadi Latham联合公开近似点（WGS84）",
                "source": "Global Energy Monitor — Safah/Wadi Latham",
                "url": "https://www.gem.wiki/Safah/Wadi_Latham_Oil_and_Gas_Field_%28Oman%29",
            },
            ("阿曼", "Wadi Latham"): {
                "lat": 23.1614,
                "lon": 55.4485,
                "precision": "Safah／Wadi Latham联合公开近似点（WGS84）",
                "source": "Global Energy Monitor — Safah/Wadi Latham",
                "url": "https://www.gem.wiki/Safah/Wadi_Latham_Oil_and_Gas_Field_%28Oman%29",
            },
            ("阿曼", "Block 27 (Oman)"): {
                "lat": 22.7117,
                "lon": 56.5162,
                "precision": "Khamilah组成田公开近似点（WGS84）",
                "source": "Global Energy Monitor — Khamilah",
                "url": "https://www.gem.wiki/Khamilah_Oil_Field_%28Oman%29",
            },
            ("阿曼", "Khamilah"): {
                "lat": 22.7117,
                "lon": 56.5162,
                "precision": "公开资产数据库近似点（WGS84）",
                "source": "Global Energy Monitor — Khamilah",
                "url": "https://www.gem.wiki/Khamilah_Oil_Field_%28Oman%29",
            },
            ("阿曼", "Block 8 (Oman)"): {
                "lat": 26.4214,
                "lon": 55.9659,
                "precision": "跨境West Bukha／Hengam油田代表点（WGS84；近似）",
                "source": "Global Energy Monitor — Hengam / West Bukha cross-border field",
                "url": "https://www.gem.wiki/Hengam_Oil_and_Gas_Field_%28Iran%29",
            },
            ("阿曼", "West Bukha"): {
                "lat": 26.4214,
                "lon": 55.9659,
                "precision": "跨境West Bukha／Hengam油田代表点（WGS84；近似）",
                "source": "Global Energy Monitor — Hengam / West Bukha cross-border field",
                "url": "https://www.gem.wiki/Hengam_Oil_and_Gas_Field_%28Iran%29",
            },
            ("阿曼", "Block 7 (Oman)"): {
                "lat": 20.40786,
                "lon": 56.24374,
                "precision": "Sahma组成油田公开点位（WGS84；区块代表点）",
                "source": "OpenStreetMap/GeoNames — As Sahmah",
                "url": "https://mapcarta.com/36266762",
            },
            ("阿曼", "Sahma"): {
                "lat": 20.40786,
                "lon": 56.24374,
                "precision": "公开地名数据库油田点位（WGS84）",
                "source": "OpenStreetMap/GeoNames — As Sahmah",
                "url": "https://mapcarta.com/36266762",
            },
            ("阿曼", "Block 60 (Oman)"): {
                "lat": 21.178,
                "lon": 55.8542,
                "precision": "Bisat／Abu Butabul区块公开近似点（WGS84）",
                "source": "Global Energy Monitor — Bisat / Abu Butabul",
                "url": "https://www.gem.wiki/Bisat_Oil_Field_%28Oman%29",
            },
            ("阿曼", "Abu Butabul"): {
                "lat": 21.178,
                "lon": 55.8542,
                "precision": "Block 60公开近似点（WGS84）",
                "source": "Global Energy Monitor — Abu Butabul",
                "url": "https://www.gem.wiki/Abu_Butabul_Oil_and_Gas_Field_%28Oman%29",
            },
            ("阿曼", "Block 61 (Oman)"): {
                "lat": 21.705,
                "lon": 56.4643,
                "precision": "Khazzan／Ghazeer项目公开近似点（WGS84）",
                "source": "Global Energy Monitor — Khazzan/Ghazeer",
                "url": "https://www.gem.wiki/Khazzan_Oil_and_Gas_Complex_%28Oman%29",
            },
            ("阿曼", "Khazzan"): {
                "lat": 21.705,
                "lon": 56.4643,
                "precision": "Khazzan／Ghazeer项目公开近似点（WGS84）",
                "source": "Global Energy Monitor — Khazzan Phase 1",
                "url": "https://www.gem.wiki/Khazzan_Phase_1_Oil_and_Gas_Field_%28Oman%29",
            },
            ("阿曼", "Ghazeer"): {
                "lat": 21.705,
                "lon": 56.4643,
                "precision": "Khazzan／Ghazeer项目公开近似点（WGS84）",
                "source": "Global Energy Monitor — Ghazeer",
                "url": "https://www.gem.wiki/Ghazeer_%28Khazzan_Phase_2%29_Oil_and_Gas_Field_%28Oman%29",
            },
            ("阿曼", "Budour Northeast"): {
                "lat": 18.31856,
                "lon": 55.10261,
                "precision": "Birba作业区公开油田点（Budour Northeast区域代表点）",
                "source": "PDO discovery description / GeoNames — Birba Oil Field",
                "url": "https://mapcarta.com/35907568",
                "proxy": True,
            },
            ("阿曼", "Wadi Aswad North"): {
                "lat": 21.93501,
                "lon": 55.74842,
                "precision": "Wadi Aswad同名地理区域代表点（非发现井坐标）",
                "source": "GeoNames/Mapcarta — Wadi Aswad",
                "url": "https://mapcarta.com/12444616",
                "proxy": True,
            },
            ("阿曼", "Safah North B"): {
                "lat": 23.196323,
                "lon": 55.471184,
                "precision": "Safah油田公开点（北部发现区域代表点；非井位）",
                "source": "GeoNames — Safah Oil Field / Occidental discovery announcement",
                "url": "https://www.geonames.org/11864188/safah-oil-field.html",
                "proxy": True,
            },
            ("也门", "Block S2 (Uqlah)"): {
                "lat": 15.3053,
                "lon": 46.77715,
                "precision": "Habban组成油田设施公开点位（OpenStreetMap；近似）",
                "source": "OpenStreetMap — Habban field facilities",
                "url": "https://mapcarta.com/W498389053",
            },
            ("也门", "Habban"): {
                "lat": 15.3053,
                "lon": 46.77715,
                "precision": "公开油田设施点位（OpenStreetMap；近似）",
                "source": "OpenStreetMap — Habban field facilities",
                "url": "https://mapcarta.com/W498389053",
            },
            ("也门", "Hiswah (Haswa)"): {
                "lat": 15.70337,
                "lon": 47.96781,
                "precision": "公开油田设施点位（OpenStreetMap；近似）",
                "source": "OpenStreetMap — Hiswah field facilities",
                "url": "https://mapcarta.com/W498389042",
            },
            ("也门", "Alroidhat (Al-Rowedhat)"): {
                "lat": 15.58213,
                "lon": 48.09317,
                "precision": "公开油田设施点位（OpenStreetMap；近似）",
                "source": "OpenStreetMap — Al Rhoidat field facilities",
                "url": "https://mapcarta.com/W498389044",
            },
            ("埃及", "Belayim"): {
                "lat": 28.6197,
                "lon": 33.2076,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Belayim Marine",
                "url": "https://www.gem.wiki/Belayim_Marine_Oil_and_Gas_Field_%28Egypt%29",
            },
            ("埃及", "Wadi El Sahl Development Area"): {
                "lat": 27.17584,
                "lon": 33.77484,
                "precision": "开发区同名地理要素近似点（WGS84；非边界中心）",
                "source": "GeoNames/OpenStreetMap — Wadi Faliq as Sahl",
                "url": "https://mapcarta.com/13059698",
            },
            ("埃及", "Shukheir Offshore (Shukheir Bay)"): {
                "lat": 28.12,
                "lon": 33.31,
                "precision": "埃及官方特许权地图估读（Shukheir代表点）",
                "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
                "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf",
                "proxy": True,
            },
            ("埃及", "Shukheir Offshore (Gamma)"): {
                "lat": 28.12,
                "lon": 33.31,
                "precision": "埃及官方特许权地图估读（Shukheir特许区代表点）",
                "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
                "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf",
                "proxy": True,
            },
            ("埃及", "Gazwarina"): {
                "lat": 27.63,
                "lon": 33.64,
                "precision": "埃及官方特许权地图估读（近似）",
                "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
                "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf",
                "proxy": True,
            },
            ("埃及", "Ras El Ush"): {
                "lat": 27.866667,
                "lon": 33.516667,
                "precision": "公开地学论文所列Ras El Ush井区坐标（近似）",
                "source": "Published Ras El Ush field study",
                "url": "https://www.researchgate.net/publication/342262683",
                "proxy": True,
            },
            ("埃及", "Zeit Bay"): {
                "lat": 27.7182,
                "lon": 33.2409,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Zeit Bay",
                "url": "https://www.gem.wiki/Zeit_Bay_Oil_and_Gas_Field_%28Egypt%29",
            },
            ("埃及", "Ras Budran"): {
                "lat": 28.934,
                "lon": 33.2409,
                "precision": "公开资产数据库精确点位（WGS84）",
                "source": "Global Energy Monitor — Ras Budran",
                "url": "https://www.gem.wiki/Ras_Budran_Oil_and_Gas_Field_%28Egypt%29",
            },
            ("埃及", "East Zeit (E. Zeit)"): {
                "lat": 27.84,
                "lon": 33.62,
                "precision": "埃及官方特许权地图估读（近似）",
                "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
                "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf",
                "proxy": True,
            },
            ("埃及", "Ashrafi"): {
                "lat": 27.78,
                "lon": 33.59,
                "precision": "埃及官方特许权地图估读（近似）",
                "source": "Egypt Upstream Gateway — Egypt Concession Map (Sep 2026)",
                "url": "https://eug.petroleum.gov.eg/dp/pages/customcode/MDS_iTabs/information-img/Egypt_Concession_Map.pdf",
                "proxy": True,
            },
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
            if (
                "油田群" in asset_type
                or "综合体" in asset_type
                or "作业区" in asset_type
            ):
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
            asset_level = LEVEL_OVERRIDES.get(
                key, infer_asset_level(asset["asset_type"])
            )
            commodity = (
                "oil_and_gas"
                if asset["metric_type"] == "actual_output_boe"
                else infer_commodity(asset["asset_type"])
            )
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
                asset["value"] is not None
                and asset["metric_type"] in OUTPUT_METRIC_TYPES
            )

        _asset_index = {(asset["country"], asset["name"]): asset for asset in ASSETS}
        if len(_asset_index) != len(ASSETS):
            raise ValueError("资产目录出现重复国家/名称")
        for asset in ASSETS:
            parent_name = asset["parent_asset"]
            if parent_name:
                parent = _asset_index.get((asset["country"], parent_name))
                if parent is None:
                    raise ValueError(
                        f"缺少上级资产记录：{asset['country']} / {asset['name']} -> {parent_name}"
                    )
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
            asset["constituent_assets"] = list(
                dict.fromkeys(
                    [child["name"] for child in direct_children] + named_children
                )
            )
            asset["constituent_count"] = len(asset["constituent_assets"])
            asset["aggregate_children_on_map"] = (
                bool(direct_children) and asset["value"] is not None
            )
            coordinate = COORDINATE_OVERRIDES.get(key)
            asset["map_lat"] = coordinate["lat"] if coordinate else asset["lat"]
            asset["map_lon"] = coordinate["lon"] if coordinate else asset["lon"]
            asset["map_coordinate_precision"] = (
                coordinate["precision"] if coordinate else asset["coordinate_precision"]
            )
            asset["map_is_proxy"] = (
                bool(coordinate.get("proxy", False)) if coordinate else False
            )
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
            if direct_children and (
                asset["map_lat"] is None or asset["map_lon"] is None
            ):
                located_children = [
                    child
                    for child in direct_children
                    if child["map_lat"] is not None and child["map_lon"] is not None
                ]
                if located_children:
                    asset["map_lat"] = sum(
                        child["map_lat"] for child in located_children
                    ) / len(located_children)
                    asset["map_lon"] = sum(
                        child["map_lon"] for child in located_children
                    ) / len(located_children)
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
                    raise ValueError(
                        f"资产层级出现循环：{asset['country']} / {asset['name']}"
                    )
                seen.add(parent_key)
                parent = _asset_index[parent_key]
                if (
                    parent["aggregate_children_on_map"]
                    and parent["map_lat"] is not None
                ):
                    strategic_parent = parent
                    break
                parent_name = parent["parent_asset"]

            asset["map_default"] = strategic_parent is None
            asset["strategic_parent"] = (
                strategic_parent["name"] if strategic_parent else None
            )
            asset["map_drawable"] = (
                asset["map_lat"] is not None and asset["map_lon"] is not None
            )
            if strategic_parent:
                asset["map_role"] = "component"
                asset["map_role_label"] = (
                    f"组成资产（上级节点：{strategic_parent['name']}）"
                )
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
                    "operating_status_evidence_url": evidence_url
                    or _asset_index[key]["source_url"],
                }

        # 沙特阿拉伯：近期官方公司材料可确认主力田持续开发／投产；发现田不把试井流量当商业生产。
        _assign_status(
            "沙特阿拉伯",
            "Ghawar | Safaniya | Khurais | Shaybah | Manifa | Berri | Zuluf | Qatif | Abqaiq | Khursaniyah",
            "producing",
            "2025-12-31／2026年公开材料",
            "中",
            "官方资料确认主力生产资产；逐田当日产量并未全部公开，且不把公司总产量下推到单田。",
        )
        _assign_status(
            "沙特阿拉伯",
            "Marjan | Dammam | Jafurah",
            "producing",
            "2025-12-31",
            "高",
            "Aramco 2025年报逐项确认Marjan原油增量、Dammam一期及Jafurah已投产；这里仅据此判定状态，不把新增产能或公司总量当作逐田实产。",
            "https://www.aramco.com/-/media/publications/corporate-reports/reports-and-presentations/2025/fy/saudi-aramco-ara-2025-english.pdf",
        )
        _assign_status(
            "沙特阿拉伯",
            "Jabu | Sayahid | Ayfan | Nuwayr | Damda | Qurqas | Ladam | Faruq | Sakab | Zumul",
            "discovered",
            "2017—2025年发现公告",
            "高",
            "官方资料仅确认发现或试井，未确认商业生产。",
        )
        _assign_status(
            "沙特阿拉伯",
            "Abu Jifan | Mazalij",
            "producing",
            "2020年官方运营资料／网页复核2026-09-28",
            "中",
            "Aramco说明Khurais设施从Khurais、Abu Jifan和Mazalij三田生产；未披露两田各自日产量。",
            "https://www.aramco.com/en/news-media/elements-magazine/2020/why-intelligence-is-important",
        )
        _assign_status(
            "沙特阿拉伯",
            "Qirdi",
            "ceased",
            "1980年代／报告更新至2026年",
            "中",
            "Wood Mackenzie当前资产报告明确Qirdi在1980年代停止生产，未见复产资料。",
            "https://www.woodmac.com/reports/upstream-oil-and-gas-khurais-3186632/",
        )
        _assign_status(
            "沙特阿拉伯",
            "Abu Hadriya",
            "producing",
            "2025年资产报告／复核2026-09-28",
            "中",
            "Abu Hadriya属于仍有生产与2025—2029运营支出记录的AFK资产组合。",
            "https://www.woodmac.com/reports/upstream-oil-and-gas-khursaniyah-area-4215754/",
        )
        _assign_status(
            "沙特阿拉伯",
            "Fadhili",
            "producing",
            "2026-09-28",
            "中",
            "当前油气资产跟踪器将Fadhili油田列为运营中；注意不要与同名Fadhili天然气处理厂混淆。",
            "https://www.gem.wiki/Fadhili_Oil_Field_(Saudi_Arabia)",
        )
        _assign_status(
            "沙特阿拉伯",
            "Harmaliyah",
            "producing",
            "2026-09-28",
            "中",
            "当前油气资产跟踪器将Harmaliyah列为运营中，最近可见田级产量年份为2020。",
            "https://www.gem.wiki/Harmaliyah_Oil_and_Gas_Field_(Saudi_Arabia)",
        )
        _assign_status(
            "沙特阿拉伯",
            "Hawtah",
            "producing",
            "2024年资产资料／复核2026-09-28",
            "中",
            "当前资产资料将Hawtah Trend列为生产油田，配套原油管线亦列为运营中。",
            "https://www.offshore-technology.com/marketdata/oil-gas-field-profile-hawtah-trend-fields-conventional-oil-field-saudi-arabia/",
        )

        # 阿联酋：运营商当前资产页与近年投产公告为主；Ghasha相关开发项目不提前标作在产。
        _assign_status(
            "阿联酋",
            "Huwaila | Al Dabb'iya | Sahil | Shah | Upper Zakum | Lower Zakum | Umm Shaif | Satah | Nasr | Umm Al Dalkh | Satah Al Razboot (SARB) | Umm Lulu | Abu Al Bukhoosh | Bu Haseer | Belbazem | Umm Al Salsal | Umm Al Dholou | Arzanah | Nahaidiin | Bin Hadi | Gezira | Muhaymat | Sila | Hail (ADOC) | Mubarraz | Umm Al-Anbar | Neewat Al-Ghalan | Bunduq | Haliba | Fateh | South-West Fateh | Falah | Rashid | Jalilah | Margham | Sajaa | Kahaif | Mahani",
            "producing",
            "运营商资料截至2025年／再次复核2026-09-28",
            "中",
            "逐资产重查后，运营商仍把该资产列入当前上游运营或近年已投产；但缺少同一观察日的逐田实时遥测，故维持中置信度。",
        )
        _assign_status(
            "阿联酋",
            "Bab | Bu Hasa | Bida Al-Qemzan | Rumaitha | Shanayel | Asab | Qusahwira | Mender | Al Nouf | Jumaylah",
            "producing",
            "2025年",
            "高",
            "ADNOC 2025可持续发展报告把这十个具名油田列入Onshore特许区，并明确该特许区的作业类型为开采与生产；报告不披露逐田日产量。",
            "https://reports.adnoc.ae/e/sustainability-report-2025-mobile",
        )
        _assign_status(
            "阿联酋",
            "Belbazem Offshore Block",
            "producing",
            "2024-03-27",
            "高",
            "ADNOC公告明确Belbazem海上区块已实现首产；45千桶/日为三区块目标产能，不能作为当期实产或分配给三个组成田。",
            "https://adnoc.ae/en/news-and-media/press-releases/2023/adnoc-announces-first-production-from-belbazem-offshore-block/",
        )
        _assign_status(
            "阿联酋",
            "Ghasha | Dalma | Shuweihat | Ghasha Concession | SARB Deep Gas | Hail (ADNOC Ghasha) | Bab Gas Cap | Ruwais Diyab | Hedebah",
            "development",
            "2025—2026年项目资料",
            "高",
            "公开资料将其列为开发、建设或扩建项目；目标产量不等于当前实产。",
        )
        _assign_status(
            "阿联酋",
            "Moveyeid",
            "storage",
            "2026-09-28审计",
            "高",
            "SNOC明确其成熟气田已转为储气用途。",
        )
        _assign_status(
            "阿联酋",
            "Saleh",
            "ceased",
            "2024-11-05／复核2026-09-28",
            "高",
            "RAK Petroleum Authority披露对Saleh田六个平台九口井开展封堵弃置（P&A），不再按历史产量视为在产。",
            "https://www.linkedin.com/posts/rakpa_collaboration-adipec2024-rakpa-activity-7259475442305286144-qSf6",
        )
        _assign_status(
            "阿联酋",
            "Umm Al Quwain",
            "ceased",
            "2025年资产报告／复核2026-09-28",
            "中",
            "当前已停产资产报告把Umm Al Qaiwain列入ceased fields，公开资产资料亦称已停产并弃置。",
            "https://www.woodmac.com/reports/upstream-oil-and-gas-united-arab-emirates-ceased-fields-75021668/",
        )

        # 伊拉克：把2025—2026运营商／新闻与EITI参考年分开；历史表不伪装成实时状态。
        _assign_status(
            "伊拉克",
            "Rumaila | West Qurna-1 | West Qurna-2 | Zubair | Majnoon | Halfaya | Gharraf | Badra | Ahdab | East Baghdad | Nahr Umar | Nassiriya | Kirkuk | Bai Hassan | Jambur | Khabbaz | Qayyarah | Shaikan | Atrush | Sarsang | Swara Tika | East Swara Tika | Khurmala | Faihaa | Fakkah | Bazerkan | Abu Gharb | Luhais | Subba | Tuba | Ajil | Hamrin | Naft Khana | Amara | Noor | Safiya",
            "producing",
            "2023—2026年最后可核实公开时点／再次复核2026-09-28",
            "中",
            "逐资产重查后，运营商、EITI或近期报道仍支持生产属性；2026年冲突造成的国家或区域减产不下推为每个油田停产。",
        )
        _assign_status(
            "伊拉克",
            "Tawke | Peshkabir",
            "producing",
            "2025年",
            "高",
            "DNO当前生产与储量页面及年度资料明确Tawke许可证的Tawke、Peshkabir两田在2025年贡献生产；披露的是许可证合计，不能拆成两田日产量。",
            "https://www.dno.no/en/operations/production-and-reserves/",
        )
        _assign_status(
            "伊拉克",
            "Taq Taq | Sarta",
            "ceased",
            "2023-12-01",
            "高",
            "运营商披露停产或PSC终止；未找到后续复产的直接证据。",
        )
        _assign_status(
            "伊拉克",
            "Artawi | Najma | Baeshiqa | Eridu (Block 10)",
            "non_producing",
            "2023—2025年最后可核实公开时点",
            "高",
            "EITI或运营商明确列为非生产／仅试井；开发活动不等于商业生产。",
        )
        _assign_status(
            "伊拉克",
            "Ain Zalah | Batmah",
            "producing",
            "2022-03-30",
            "中",
            "摩苏尔大学石油与采矿工程学院对两田的现场记录逐名说明，从油井、处理和湿油分离直至外输管线观察了产油流程；证据为2022年现场时点，未外推为2026年实时状态。",
            "https://uomosul.edu.iq/petroleumengineering/%D8%B2%D9%8A%D8%A7%D8%B1%D8%A9-%D8%B9%D9%84%D9%85%D9%8A%D8%A9-5/",
        )

        # 伊朗：来源页可确认运营资产，但2026年战争和出口封锁使“当前运行强度”不确定。
        _assign_status(
            "伊朗",
            "Ahvaz | Marun | Aghajari | Gachsaran | Reg-e-Safid | South Azadegan | North Azadegan | Yadavaran | North Yaran | South Yaran | Azar | Darkhovin | Hendijan | Doroud | Foroozan | Soroush | Nowruz | Salman | Bibi Hakimeh | Karanj | Abuzar | Mansouri | Sepehr-Jufair | Parsi | Bahregansar | Sirri E | Masjed Soleyman | Pazanan | Kupal | Dehloran | Paranj | Nargesi | South Pars",
            "producing",
            "2024—2026年最后可核实公开时点",
            "中",
            "EIA、SHANA或资产资料列为开发／运营资产；2026年地区冲突下不把出口量变化下推成单田停复产。",
        )
        _assign_status(
            "伊朗",
            "Hengam",
            "producing",
            "2025年资产状态／复核2026-09-28",
            "中",
            "当前油气资产跟踪器将Hengam列为Operating；逐田最新公开产量仍较旧。",
            "https://www.gem.wiki/Hengam_Oil_and_Gas_Field_(Iran)",
        )
        _assign_status(
            "伊朗",
            "Band-e-Karkheh",
            "development",
            "2026-02-21",
            "高",
            "MAPNA宣布开发合同完成审批并进入实施阶段；目标增产不当作当前实产。",
            "https://mapnagroup.com/63236/mapna-officially-notified-of-ipc-contract-for-development-of-bande-karkheh-oil-field/?lang=en",
        )
        _assign_status(
            "伊朗",
            "West Paydar",
            "producing",
            "2026年资产报告",
            "高",
            "当前资产报告明确该田已生产多年并进入2025—2030加速开发阶段。",
            "https://www.woodmac.com/reports/upstream-oil-and-gas-aban-and-west-paydar-ipc-54481312/",
        )
        _assign_status(
            "伊朗",
            "Chehsmeh-Khosh",
            "producing",
            "2026-07-18",
            "高",
            "PEDEC信息显示CK-26井投产；2025年资料亦披露该田在产并增产。",
            "https://www.iranoilgas.com/trackers/?view=fieldstrackers",
        )
        _assign_status(
            "伊朗",
            "Danan",
            "producing",
            "2025-03-04",
            "中",
            "MAPNA项目公司披露Danan开发项目的新脱盐装置已接入生产并提升处理能力。",
            "https://www.linkedin.com/posts/mapna-ogdc_%D9%85%D9%BE%D9%86%D8%A7-%D8%B5%D9%86%D8%B9%D8%AA%D9%86%D9%81%D8%AA-%D8%AA%D9%88%D8%B3%D8%B9%D9%87%D9%86%D8%AA%D9%88%DA%AF%D8%A7%D8%B2-activity-7303067532536500224-s-7Y",
        )
        _assign_status(
            "伊朗",
            "Changuleh",
            "development",
            "2026-09-28",
            "高",
            "2025年成立的项目公司负责Changuleh全周期开发，目标产能尚不能作为当前产量。",
            "https://www.linkedin.com/company/mogdc",
        )
        _assign_status(
            "伊朗",
            "Dalpari",
            "producing",
            "2026-07-18",
            "高",
            "PEDEC信息将Dalpari与Cheshmeh Khosh、East Paydar列入正在开发生产的项目组合并披露新井投产。",
            "https://www.iranoilgas.com/trackers/?view=fieldstrackers",
        )
        _assign_status(
            "伊朗",
            "Paydar",
            "unknown",
            "2024-10-10／再次复核2026-09-28",
            "中",
            "EIA将Paydar与West Paydar分别列为NGL 3100拟收集伴生气的油田，确认它是独立资产；但该表描述的是拟建处理项目，不能单独证明Paydar当前正在产油，故保留待核实。",
            "https://www.eia.gov/international/content/analysis/countries_long/Iran/pdf/Iran%20CAB%202024.pdf",
        )

        # 科威特：KOC年报和商业投产公告；新发现不按在产处理。
        _assign_status(
            "科威特",
            "Burgan | Magwa | Ahmadi | Raudhatain | Sabriya | Bahra | Ratqa | Umm Niqa | South Ratqa | Minagish | Umm Gudair | Abdali | Wafra | Khafji | Mutriba | Kra-al-Maru",
            "producing",
            "FY2024/25—2026年最后可核实公开时点",
            "中",
            "KOC年报、分区运营资料或商业投产公告支持；2026年出口受扰不等于各田停产。",
        )
        _assign_status(
            "科威特",
            "Nokhetha | Julaiah | Shaham",
            "discovered",
            "FY2024/25",
            "高",
            "KOC将其列为发现；试井流量不等于持续商业生产。",
        )

        # 卡塔尔：2024逐田平均、当前E&P页及延长至2027年的开发生产协议。
        _assign_status(
            "卡塔尔",
            "Al Shaheen | Dukhan | Al-Rayyan | Al-Khaleej | Idd El-Sharqi | Karkara | Maydan Mahzam | Bul Hanine | Al-Murjan | North Field | A-Structures (A-North / A-South) | A-North | A-South",
            "producing",
            "2024年平均／协议期至2027年",
            "高",
            "QatarEnergy逐田产量、当前E&P资料或有效开发生产协议支持。",
        )

        # 阿曼：运营商2024—2025资料确认绝大多数生产资产；发现田单列。
        _assign_status(
            "阿曼",
            "Mukhaizna | Yibal | Natih | Fahud | Qarn Alam | Marmul | Nimr | Lekhwair | Bahja | Harweel | Amal | Zalzala | Haima West | Al Noor | Nimr-A | Nimr-E | Block 5 (Daleel) | Daleel | Shadi | Bushra | Mazoon | Furat | Thahab | Block 9 (Oman) | Block 27 (Oman) | Safah | Wadi Latham | Khamilah | Block 8 (Oman) | Block 7 (Oman) | Block 61 (Oman) | West Bukha | Bukha | Sahma | Abu Butabul | Khazzan | Ghazeer",
            "producing",
            "2024—2026年最后可核实公开时点／再次复核2026-09-28",
            "中",
            "逐资产重查后，PDO、OQEP、Oxy或Daleel资料仍支持生产资产／生产区块属性；区块合计不拆给单田。",
        )
        _assign_status(
            "阿曼",
            "Block 50 (Masirah) | Yumna",
            "producing",
            "2026年3月",
            "高",
            "Masirah Oil逐月公告明确Yumna在2026年3月31天生产期平均742桶/日，并说明其为Block 50运营商且持有100%权益；该值属于Yumna单田，不反推区块内其他资产。",
            "https://www.masirahoil.om/post/production-update-march-2026",
        )
        _assign_status(
            "阿曼",
            "Bisat | Block 60 (Oman)",
            "producing",
            "2025-12-31",
            "高",
            "OQEP 2025年报确认Bisat C扩建投运，Block 60年末总产量超过70千桶油当量/日；区块合计与处理能力均不拆给Bisat单田。",
            "https://oqep.om/UploadsAll/IRFiles/1781008603725OQEP_2025_Annual_Report.pdf",
        )
        _assign_status(
            "阿曼",
            "Budour Northeast | Wadi Aswad North | Safah North B",
            "discovered",
            "2024—2026年最后可核实公开时点",
            "中",
            "运营商列为发现或待开发，未取得商业生产直接证据。",
        )

        # 巴林。
        _assign_status(
            "巴林",
            "Bahrain Field (Awali) | Abu Safah",
            "producing",
            "2025年运营资料／2026-09-28审计",
            "中",
            "Bapco当前上游资料和跨境田资料支持生产属性；产能不等于实际日产量。",
        )

        # 也门：有历史生产和设施证据，但安全局势下不把旧区块计划写成当前在产。
        _assign_status(
            "也门",
            "Block 14 (Masila) | Block 10 (East Shabwa)",
            "temporarily_suspended",
            "2025-12-01／复核至2026-09-28",
            "中",
            "PetroMasila声明因安全局势全面停止Block 14生产炼制，并同时停止Block 10生产；未找到其后复产的直接公告。",
            "https://en.ypagency.net/377792",
        )
        _assign_status(
            "也门",
            "Block 32 (Hawareem) | Tasour | Godah",
            "non_producing",
            "2015-03-31／复核至2026-09-28",
            "中",
            "DNO官方公告因安全恶化暂停Block 32生产；其后未找到复产证据，故按当前非生产处理而非沿用历史产量。",
            "https://www.dno.no/en/investors/announcements/dno-asa-yemen-operations-update/",
        )
        _assign_status(
            "也门",
            "Block 18 (Marib) | Alif",
            "producing",
            "运营商网页复核2026-09-28",
            "高",
            "SEPOC称其为也门第二大产油商，Block 18生产设施页明确Alif等16田原油流入处理系统。",
            "https://sepocye.com/en/DefaultDET.aspx?SUB_ID=81",
        )
        _assign_status(
            "也门",
            "Block 5 (Jannah)",
            "producing",
            "运营商网页复核2026-09-28",
            "高",
            "JHOC当前运营页明确Block 5原油在Halewah中央处理设施稳定并达到管输规格。",
            "https://www.jhocyemen.com/our-operations/",
        )
        _assign_status(
            "也门",
            "Block S2 (Uqlah) | Habban",
            "temporarily_suspended",
            "2023年中／报告更新至2025-11",
            "高",
            "当前资产报告明确Block S2生产在2023年中再次暂停；Habban是该区块唯一油田。",
            "https://www.woodmac.com/reports/upstream-oil-and-gas-al-uqlah-block-s2-1303840",
        )
        _assign_status(
            "也门",
            "Block 9 (Malik) | Hiswah (Haswa) | Alroidhat (Al-Rowedhat)",
            "producing",
            "运营商网页复核2026-09-28",
            "中",
            "当前运营资料称Block 9约产6500桶/日，并明确Hiswah与Al Roidhat为生产体系组成田。",
            "https://www.petsec.com.au/operations/yemen-leases/",
        )
        _assign_status(
            "也门",
            "Qarn Qeamah",
            "discovered",
            "运营商网页复核2026-09-28",
            "中",
            "运营商将Qarn Qaymah列为气、凝析油和原油的contingent discovery，而非当前生产田。",
            "https://www.calvalleypetroleum.com/current-production/",
        )

        # 叙利亚：2026年可确认作业区和Al-Omar；作业区合计不能证明八个组成田逐一在产。
        _assign_status(
            "叙利亚",
            "Rmeilan Sector One | Al-Omar",
            "producing",
            "2026-02-11／2026-02-22",
            "高",
            "近期现场采访给出作业区或单田实际产量。",
        )
        _assign_status(
            "叙利亚",
            "Al-Tanak",
            "producing",
            "2026-01-25",
            "高",
            "SANA确认来自Al-Omar与Al-Tanak的原油已运抵Baniyas炼厂。",
            "https://sana.sy/en/economic/2292355/",
        )
        _assign_status(
            "叙利亚",
            "Al-Jafra",
            "development",
            "2026-01-21",
            "中",
            "SPC技术团队现场检查Al-Jafra并评估恢复、改造和潜在合作，当前更适合标为再开发而非直接推定稳定在产。",
            "https://en.zamanalwsl.net/news/article/70852/",
        )
        _assign_status(
            "叙利亚",
            "Al-Ward",
            "producing",
            "2026年资产状态",
            "中",
            "当前油气资产跟踪器将Al-Ward列为operating；缺少可靠逐田日产量。",
            "https://www.gem.wiki/Ward_Oil_Field_(Syria)",
        )
        _assign_status(
            "叙利亚",
            "Al-Taym",
            "producing",
            "2026-01-26",
            "高",
            "SANA称技术团队正在Al-Taym等田监督开采、装运和运输作业。",
            "https://sana.sy/en/economic/2292574/",
        )
        _assign_status(
            "叙利亚",
            "Rmeilan | Suwaydiya",
            "producing",
            "2026-03-04",
            "高",
            "SANA确认SPC已在Rmeilan、Suwaydiya及Hasakeh其他点位开始原油开采。",
            "https://sana.sy/es/economy/2298482/",
        )
        _assign_status(
            "叙利亚",
            "Qarachok | Hamza | Alyan | Sazabeh | Ode",
            "development",
            "2026-08-04／复核2026-09-28",
            "中",
            "HKN Syria列明已接手并运营八个田；现场工作以修井、新钻井和设施修复为主，因此按开发／复产阶段处理，不把作业区总量下推。",
            "https://hknsyria.com/",
        )
        _assign_status(
            "叙利亚",
            "Tigris",
            "producing",
            "2026-04-09",
            "中",
            "叙利亚官方通讯社称哈塞克省Dejla（Tigris）油田群产量提高30%，并说明其属于Rmeilan综合体；因报道使用复数油田群而目录记录为单一具名资产，保留中置信度。",
            "https://sana.sy/es/economy/2304911/",
        )

        # 以色列：2026年停产后复产信息逐田处理；Tanin尚无商业生产证据。
        _assign_status(
            "以色列",
            "Heletz",
            "producing",
            "2022年研究／2026-09-28审计",
            "中",
            "公开研究称该田仍被开采，但没有实时产量。",
        )
        _assign_status(
            "以色列",
            "Meged",
            "producing",
            "运营商网页审计2026-09-28",
            "中",
            "运营商网页说明自2010年起生产并列累计产量；没有逐日实时值。",
            "https://www.givot.co.il/en/",
        )
        _assign_status(
            "以色列",
            "Leviathan | Tamar",
            "producing",
            "2026-07-06",
            "高",
            "以色列能源部门近期信息确认Tamar供应国内、Leviathan承担出口；Leviathan在4月已从临时停产中复产。",
            "https://www.reuters.com/world/middle-east/israel-launches-tender-search-more-natural-gas-mediterranean-2026-07-06/",
        )
        _assign_status(
            "以色列",
            "Karish",
            "producing",
            "2026-09-09",
            "高",
            "Energean在4月恢复生产，9月半年报称以色列产量已强劲恢复。",
            "https://www.reuters.com/business/energy/uks-energean-posts-higher-half-year-profit-maintains-output-forecast-after-2026-09-09/",
        )
        _assign_status(
            "以色列",
            "Tanin",
            "development",
            "2026-09-28审计",
            "中",
            "资产属于Energean开发组合，但未找到Tanin商业生产的直接证据。",
            "https://www.reuters.com/business/energy/energean-invest-12-bln-develop-israel-katlan-gas-project-2024-07-23/",
        )

        # 土耳其：TPAO公开资产及Gabar增产资料。
        _assign_status(
            "土耳其",
            "Raman | Batı Raman | Garzan | Şelmo | Gabar",
            "producing",
            "2025—2026年最后可核实公开时点",
            "中",
            "TPAO／政府资料列为生产资产；未把全国或Gabar油田群合计拆给其他单田。",
        )

        # 埃及：棕地包件是资产名录而非当前生产快照。
        _assign_status(
            "埃及",
            "Belayim",
            "producing",
            "2026年资产状态",
            "高",
            "当前油气资产跟踪器将Belayim Marine与Belayim Land均列为operating。",
            "https://www.gem.wiki/Belayim_Marine_%26_Belayim_Land_Oil_Project_(Egypt)",
        )
        _assign_status(
            "埃及",
            "Shukheir Offshore (Shukheir Bay) | Shukheir Offshore (Gamma) | Gazwarina | Ras El Ush | East Zeit (E. Zeit) | Ashrafi",
            "producing",
            "FY2025/26／复核2026-09-28",
            "中",
            "EGPC棕地轮次将其列为OSOCO生产棕地；OSOCO FY2025/26仍有7100桶油当量/日合计产量，但不得拆成各田日产量。",
            "https://egyptoil-gas.com/news/osoco-raises-output-to-1-7-mmboe-in-fy-2025-26/",
        )
        _assign_status(
            "埃及",
            "Zeit Bay | Ras Budran",
            "producing",
            "FY2025/26",
            "高",
            "SOCO FY2025/26披露持续生产和在Ras Budran增加生产井；设施同时服务Zeit Bay。",
            "https://egyptoil-gas.com/news/suez-oil-company-increased-proven-reserves-by-3-9-mmbbl/",
        )
        _assign_status(
            "埃及",
            "Wadi El Sahl Development Area",
            "development",
            "2025-11-25",
            "高",
            "埃及批准法律授权与Lukoil签署该开发区勘探、开发和生产合同，尚不以目标或发现量当作当前商业产量。",
            "https://www.egypttoday.com/Article/3/143692/El-Sisi-ratifies-law-on-oil-exploration-and-development-in",
        )

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
        _revise_status(
            "阿联酋",
            "Hedebah",
            "producing",
            "2025-11-04",
            "高",
            "SNOC披露首井已在发现后十个月投产；第二井当时计划接入，不填产量。",
            "https://www.snoc.ae/news/snoc-strengthens-sharjahs-energy-security-with-second-well-success-in-hedebah-field/",
        )
        _revise_status(
            "伊拉克",
            "Atrush | Sarsang | Swara Tika | East Swara Tika",
            "temporarily_suspended",
            "2026-08-05公告；停产自07-20",
            "高",
            "ShaMaran Q2公告明确两资产7月20日起再次停产；Sarsang组成田按区块停产证据。9月材料的预计复产流量并非实际复产证明。",
            SOURCES["ShaMaran Q2 2026"],
        )
        _revise_status(
            "伊拉克",
            "Tawke | Peshkabir",
            "producing",
            "2026-08 Q2报告",
            "高",
            "DNO Q2报告分别披露Tawke于06-28、Peshkabir于07-11复产；不以Q2均值代替当前值。",
            "https://www.dno.no/media/ezuglbal/q2-2026-interim-results-report.pdf",
        )
        _revise_status(
            "伊拉克",
            "Taq Taq | Sarta",
            "historical_unverified",
            "2025参考年；2026-03年报",
            "中",
            "Genel 2025年报确认已退出Taq Taq和Sarta许可证；运营商退出不证明资产永久停产，2026逐田实绩待核。",
            "https://genelenergy.com/wp-content/uploads/190326_Genel-AR_web-1.pdf",
        )
        _revise_status(
            "伊拉克",
            "Artawi",
            "development",
            "2025-09-15",
            "高",
            "TotalEnergies披露Artawi再开发项目施工，未来120/210千桶日为分期目标，不是当期实产。",
            "https://totalenergies.com/newsroom/iraq-totalenergies-launches-construction-final-two-major-projects-ggip/?lang=eng",
        )

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
            "producing",
            "restoration_unconfirmed",
            "partially_operating",
            "temporarily_suspended",
            "development",
            "historical_unverified",
            "unknown",
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
            if (
                asset["map_role"] == "strategic_standalone"
                and not asset["strategic_default"]
            ):
                asset["map_role"] = "catalog_detail"
                asset["map_role_label"] = "目录补充资产（战略层级外）"

        # 下载成功不等于数值已核验；审计日期不等于观测日期。
        for asset in ASSETS:
            if asset["name"] == "Belayim" and asset["country"] == "埃及":
                asset["map_is_proxy"] = True
                asset["map_coordinate_precision"] = (
                    "Belayim Marine代表点；105千桶/日是Belayim历史整体口径"
                )
            asset.setdefault("aliases", [])
            if asset["source"] == "QatarEnergy" and asset["value"] is not None:
                asset["numeric_audit"] = (
                    "原始2025-11演示第12页2024均值已核；不是2026实绩"
                )
            if asset["name"] in {"Taq Taq", "Sarta"}:
                asset["numeric_audit"] = (
                    "Genel 2024-01原表2023毛产量已核；非权益产量或当前值"
                )
            asset.setdefault(
                "numeric_audit",
                "数值缺失；不可估计当前产量"
                if asset["value"] is None
                else "保留来源期数据；详见2026-09-30逐行审计，非实时实绩",
            )
            asset["data_audit_date"] = "2026-09-30"
            asset["freshness_note"] = (
                "没有当前逐资产实绩；缺失不等于零"
                if asset["value"] is None
                else "数值仅对应数据日期；复核日不是观测日，不能视作2026-09-30实绩"
            )

        additional_measurements(ASSETS)
        CONTINUATION.finish_review(ASSETS)
        finish_reviews(ASSETS)
        attach_gem_production_candidates(ASSETS)
        apply_public_metadata(ASSETS)
        finish_production_recheck(ASSETS, OUTPUT_METRIC_TYPES)

        # Resolve the former dashed markers only from independently reviewed field/well
        # locations. Keep rejected proxy evidence in the dated audit, not in map exports.
        _coordinate_review = read_json("data/coordinate_recheck.json")
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
                _asset["coordinate_source"] = (
                    "2026-10-06再次检索未确认独立位置；原代理点已撤回"
                )
                _asset["coordinate_source_url"] = None

        def _numeric_value(value: Any) -> tuple[Decimal | None, str]:
            """Separate a numeric amount from an approximate/bound qualifier."""
            if value is None:
                return None, ""
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                return Decimal(str(value)), ""
            match = re.fullmatch(
                r"\s*(约|~|≥|≤|>|<)?\s*([+-]?[\d,]+(?:\.\d+)?)\s*", str(value)
            )
            if not match:
                return None, ""
            try:
                amount = Decimal(match.group(2).replace(",", ""))
            except InvalidOperation:
                return None, ""
            qualifier = "约" if match.group(1) == "~" else (match.group(1) or "")
            return amount, qualifier

        from htfa.monitoring.energy_supply.processing.asset_table_recheck import (
            apply as apply_asset_table_recheck,
        )

        apply_asset_table_recheck(ASSETS)

        for asset in ASSETS:
            raw_value = asset.get("value")
            amount, qualifier = _numeric_value(raw_value)
            asset["value_raw"] = raw_value
            asset["value_numeric"] = amount
            asset["value_qualifier"] = asset.get("value_qualifier") or qualifier
            for measurement in asset.get("additional_measurements", []) + asset.get(
                "aggregate_references", []
            ):
                raw_measurement = measurement.get("value")
                measurement_amount, measurement_qualifier = _numeric_value(
                    raw_measurement
                )
                measurement["value_raw"] = raw_measurement
                measurement["value_numeric"] = measurement_amount
                measurement["value_qualifier"] = (
                    measurement.get("value_qualifier") or measurement_qualifier
                )

        return ASSETS
