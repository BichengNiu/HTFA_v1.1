"""Re-read named clues from the preserved 590-row checkpoint.

GEM is evidence of its own public catalogue, not a current operator output feed.
Only confirmed names enter the live catalogue. Unread clues remain in the ledger.
"""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from htfa.monitoring.energy_supply.data_store import read_json

GEM_ROWS = read_json("GEM_RECONCILIATION_2026-09-30.json")
TURKEY_URL = "https://enerji.gov.tr/haber-detay?id=31903"
DANA_URL = "https://www.danagas.com/wp-content/uploads/2026/02/20260204-Dana-Gas-FY-2025-Press-Release-En.pdf"
DANA_STATUS_URL = "https://www.danagas.com/media/press-releases/?cat=2026"
UMM_SHAIF_URL = "https://adnoc.ae/en/news-and-media/press-releases/2026/adnoc-accelerates-gas-growth-strategy-with-62-billion-fid-for-umm-shaif-gas-cap"
DENISE_URL = "https://www.eni.com/en-IT/media/press-release/2026/04/eni-unveils-2-tcf-gas-discovery-offshore-egypt-unlocking-fast-track-development-potential.html"


def estimated_mean(total, share, days, divisor, places):
    result = Decimal(str(total)) * Decimal(str(share)) / Decimal(days) / Decimal(divisor)
    return result.quantize(Decimal(places), rounding=ROUND_HALF_UP)

# Same referent or a source grouping already represented by multiple records.
# No nearest-neighbour matching. Reasons are exported by reconcile_checkpoint.py.
MERGES = {
    ("伊拉克", "Tel Gazal"): ("Tal Ghazal",),
    ("伊拉克", "Mansuriyah"): ("Mansuriya",),
    ("伊拉克", "Merjan"): ("Marjan (Iraq)",),
    ("伊拉克", "Nau Doman"): ("Nao Doman",),
    ("伊拉克", "Eridu"): ("Eridu (Block 10)",),
    ("伊拉克", "Khanah"): ("Naft Khana",),
    ("伊朗", "Dey"): ("Day",),
    ("阿曼", "Ghazeer (Khazzan Phase 2)"): ("Ghazeer",),
    ("阿曼", "Bahja (North and South)"): ("Bahja",),
    ("阿曼", "Safah/Wadi Latham"): ("Safah", "Wadi Latham"),
    ("埃及", "Taurus and Libra"): ("Taurus", "Libra"),
    ("埃及", "Denise W"): ("Denise West",),
    ("卡塔尔", "Al-Karkara/A-Structure"): ("Karkara", "A-Structures (A-North / A-South)"),
}

PARENTS = {
    ("埃及", "Belayim Land"): "Belayim",
    ("埃及", "Belayim Marine"): "Belayim",
    ("沙特阿拉伯", "South Ghawar"): "Ghawar",
    ("沙特阿拉伯", "Haradh"): "Ghawar",
    ("沙特阿拉伯", "Hawiyah"): "Ghawar",
    ("土耳其", "Sehit Esma Cevik"): "Gabar",
    ("土耳其", "Sehit Aybuke Yalcin"): "Gabar",
    ("卡塔尔", "Idd El Shargi North Dome (ISND)"): "Idd El-Sharqi",
    ("卡塔尔", "Idd El Shargi South Dome (ISSD)"): "Idd El-Sharqi",
    ("阿联酋", "Qusahwira (Phase 1)"): "Qusahwira",
    ("阿联酋", "Qusahwira (Phase 2)"): "Qusahwira",
    ("阿联酋", "Umm Shaif Gas Cap"): "Umm Shaif",
}
for name in ("Qatargas 1", "Qatargas 2", "Qatargas 3", "Qatargas 4", "Dolphin",
             "RasGas Alpha", "RasGas 2", "RasGas 3", "Al-Khaleej Gas Project 1 Gas Phase",
             "Al-Khaleej Gas Project 2 Gas Phase"):
    PARENTS[("卡塔尔", name)] = "North Field"

PROJECTS = {key for key in PARENTS if key[0] == "卡塔尔" and PARENTS[key] == "North Field"}
PROJECTS |= {("阿联酋", "Qusahwira (Phase 1)"), ("阿联酋", "Qusahwira (Phase 2)"),
             ("阿联酋", "Umm Shaif Gas Cap"), ("埃及", "WDDM Phase 11 Gas Phase"),
             ("埃及", "Amal Redevelop (A and B)")}
AREAS = {("沙特阿拉伯", n) for n in ("South Ghawar", "Haradh", "Hawiyah")}
AREAS |= {("卡塔尔", "Idd El Shargi North Dome (ISND)"), ("卡塔尔", "Idd El Shargi South Dome (ISSD)")}


def additions(record):
    output = []
    for row in GEM_ROWS:
        key = (row["country"], row["name"])
        if not row["catalog_name_confirmed"] or key in MERGES:
            continue
        title = row["url"].split("/")[-1]
        kind = "油气田" if "Oil_and_Gas" in title else "气田" if "Gas_Field" in title else "油田"
        if key in PROJECTS:
            kind = "油气开发项目"
        elif key in AREAS:
            kind = "油气开发区"
        elif "/" in row["name"]:
            kind = "油田群／综合体"
        coord = row["coordinates"]
        item = record(row["country"], row["name"], row["name"], kind,
                      coord["lat"] if coord else None, coord["lon"] if coord else None,
                      source="Iraq EITI 2023", note="回查GEM公开名录确认名称；不移植其未逐条核清的产量字段。"
                      "名录状态不证明当前停复产。" + ("暂无重新核实的独立坐标。" if not coord else
                      "坐标是GEM公布的田/项目参考点，exact是源分类，不是本项目独立测绘。"))
        item.update(source="GEM public inventory (re-read 2026-09-30)", source_url=row["url"],
                    catalog_evidence_url=row["url"], catalog_status_note=row["catalog_note"],
                    numeric_audit="只核对名称/位置；不将名录的年量、储量、设计能力当当前日产量")
        if coord:
            item["coordinate_precision"] = f"GEM {coord['accuracy']}；公开参考点，非独立测绘"
        output.append(item)
    for country, name, kind in (("伊拉克", "Khor Mor", "气田"),
                                ("伊拉克", "Chemchemal", "气田"),
                                ("土耳其", "Sakarya", "气田"),
                                ("阿联酋", "Umm Shaif Gas Cap", "天然气开发项目")):
        item = record(country, name, name, kind, None, None, source="Iraq EITI 2023")
        if name == "Khor Mor":
            item.update(value=">700", unit="百万标准立方英尺/日", metric_type="actual_output",
                        data_date="2026年1月高需求时段产量水平（非月均）", source="Dana Gas FY2025 release",
                        source_url=DANA_URL, note="原PDF第1—2页确认1月超过700 MMscf/d；"
                        "750为处理能力，70千boe/d为公司净合计，均不替换本字段。原文公告年份有笔误，观察期以明确的2026年1月为准。",
                        numeric_audit="运营商原文下限已核；历史峰时产量水平，不是当前或全年均值")
        elif name == "Sakarya":
            item.update(value=estimated_mean(1641, .92, 181, 1, ".01"),
                        value_qualifier="约", unit="百万立方米/日", metric_type="estimated_daily_average",
                        data_date="2026上半年估算日均；181日", source="Turkey Ministry of Energy 2026-08-16",
                        source_url=TURKEY_URL, note="政府报全国上半年天然气超过1,641百万m³，Sakarya占92%。"
                        "以公布的约数基准1,641×92%÷181≈8.34百万m³/日；"
                        "份额及总量有舍入，不能解释为精确实测均值或9月日产量。",
                        estimate_total_million_m3=1641, estimate_share=0.92, calendar_days=181,
                        numeric_audit="基于政府总量和份额的可复算近似估计；不是原文直报单田日量")
        elif name == "Umm Shaif Gas Cap":
            item.update(value=">600", unit="百万标准立方英尺/日", metric_type="target_capacity",
                        data_date="2026-07-21 FID；预计2030产气", source="ADNOC Umm Shaif Gas Cap FID",
                        source_url=UMM_SHAIF_URL, note="ADNOC规划天然气及相关气液开发；尚未将计划值当实产。",
                        numeric_audit="原FID公告已核；未来开发目标，不是当前产量")
        else:
            item.update(source="Dana Gas H1 2026 release", source_url=DANA_STATUS_URL,
                        note="运营商2026-08-07公告确认评估及早期开发计划；142 MMscf/d是销售协议上限，不填作已实现产量。")
        output.append(item)
    return output


def apply_existing(assets):
    index = {(a["country"], a["name"]): a for a in assets}
    for key, targets in MERGES.items():
        if len(targets) == 1:
            item = index[(key[0], targets[0])]
            item.setdefault("aliases", []).append(key[1])
    denise = index[("埃及", "Denise West")]
    denise.update(source="Eni Denise W discovery 2026-04-07", source_url=DENISE_URL,
                  note="Eni 2026-04-07原公告确认Denise W气及凝析油发现；2 Tcf为原地资源量，非产量；未填井测试或推算坐标。")
    gabar = index[("土耳其", "Gabar")]
    gabar.update(value=estimated_mean(23100000, .60, 181, 1000, ".1"),
                 value_qualifier="约", unit="千桶/日", metric_type="estimated_daily_average",
                 data_date="2026上半年估算日均；181日", source="Turkey Ministry of Energy 2026-08-16",
                 source_url=TURKEY_URL, estimate_total_barrels=23100000, estimate_share=0.60,
                 calendar_days=181, numeric_audit="政府全国量×公布份额÷181日；近似估计，非独立实测",
                 note="23.1百万桶×60%÷181÷1000≈76.6千桶/日；总量与份额均有舍入，仅作上半年Gabar区域估算，不能拆到组成田。")


def coordinates():
    output = {}
    for row in GEM_ROWS:
        key = (row["country"], row["name"])
        coord = row["coordinates"]
        # Multi-field composite locations cannot be assigned to their members.
        if not row["catalog_name_confirmed"] or not coord or key in MERGES:
            continue
        output[key] = dict(lat=coord["lat"], lon=coord["lon"],
                           precision=f"GEM {coord['accuracy']}；源参考点，非独立测绘",
                           source="GEM public field location table", url=row["url"], proxy=False)
    return output


def register_statuses(assign):
    for row in GEM_ROWS:
        key = (row["country"], row["name"])
        if row["catalog_name_confirmed"] and key not in MERGES:
            assign(*key, "historical_unverified", "GEM名录回查2026-09-30；逐田观察期不统一", "低",
                   "名称/公开坐标已核；目录状态可能来自旧材料，当前商业生产待核。", row["url"])
    assign("伊拉克", "Khor Mor", "producing", "2026-08-07公告", "高",
           "Dana H1公告明确7月短暂停产后已恢复；1月产量不能代表复产后流量。", DANA_STATUS_URL)
    assign("伊拉克", "Chemchemal", "development", "2026-08-07公告", "高",
           "Dana H1原公告确认评估及早期开发项目；销售合同不是生产证据。", DANA_STATUS_URL)
    assign("土耳其", "Sakarya", "producing", "2026上半年；08-16发布", "高",
           "政府统计确认上半年贡献国内天然气生产的92%；不证明9月具体流量。", TURKEY_URL)
    assign("阿联酋", "Umm Shaif Gas Cap", "development", "2026-07-21 FID", "高",
           "开发最终投资决定；预计2030产气，目标不是当前产量。", UMM_SHAIF_URL)
