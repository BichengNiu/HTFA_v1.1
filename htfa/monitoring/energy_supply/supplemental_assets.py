"""Named omissions reconciled against primary inventories, 2026-09-30.

None means neither a field coordinate nor a field output has been verified.
Arabic labels preserve the source spelling when transliteration is ambiguous.
"""
from htfa.monitoring.energy_supply.audited_measurements import EITI_2023_URL

# name, original label, type, EITI 2023 table. No exploration block becomes a field.
IRAQ_ADDITIONS = (
    ("Khanuqah", "خانوكة", "气田", 13),
    ("Khashab", "خشاب", "气田", 13),
    ("Jawan", "جاوان", "油田", 13),
    ("Ismail", "إسماعيل", "油田", 13),
    ("Qasab", "قصب", "油田", 13),
    ("Makhmur", "مخمور", "油田", 13),
    ("Jadida", "جديدة", "油田", 13),
    ("Qara Chogh", "قرة جوق", "油田", 13),
    ("Pulkhana", "بلكانا", "油田", 13),
    ("Ibrahim", "إبراهيم", "油田", 13),
    ("Alan / Sasan", "علان / ساسان", "油田群", 13),
    ("Jaria Pika", "جاريا بيكة", "气田", 14),
    ("Akkas", "عكاس", "气田", 14),
    ("Mansuriya", "المنصورية", "气田", 14),
    ("Nahrawan", "النهروان", "油田", 14),
    ("Tal Ghazal", "تل غزال", "油田", 14),
    ("Nao Doman", "ناو دومان", "油田", 14),
    ("Marjan (Iraq)", "مرجان", "油田", 14),
    ("Kifl", "الكفل", "油田", 14),
    ("West Kifl", "غرب الكفل", "油田", 14),
    ("Block 8 (Iraq)", "الرقعة الثامنة", "勘探区块", 14),
    ("Injana / Khashm Al-Ahmar", "إنجانة / خشم الأحمر", "油气田群", 14),
    ("East Baghdad (Rashidiya)", "شرقي بغداد (الراشدية)", "油田开发区", 14),
    ("Middle Euphrates", "الفرات الأوسط", "油气开发区", 14),
    ("Khalisiya", "خليصية", "勘探区块", 14),
    ("Zurbatiya", "زرباطية", "油气开发区", 14),
    ("Block 7 (Iraq)", "الرقعة الإستكشافية السابعة", "勘探区块", 14),
    ("Dhifriya", "ظفرية", "油田", 14),
    ("Qarnain", "قرنين", "油田", 14),
    ("Missan Fields", "حقول ميسان (بزركان، فكة، أبو غرب)", "油田群", 15),
    ("Kumait", "كميت", "油田", 15),
    ("Dujaila", "دجيلة", "油田", 15),
    ("Rifai", "رفاعي", "油田", 15),
    ("Huwaiza", "الحويزة", "油田", 15),
    ("Dima", "ديما", "油田", 15),
    ("Abu Amood", "أبو عامود", "油田", 16),
    ("Sumer", "سومر", "油田", 16),
    ("Adan", "عدان", "油田", 16),
    ("Abu Khaimah", "أبو خيمة", "油田", 16),
    ("Siba", "السيبة", "气田", 17),
    ("Rachi", "راتشي", "油田", 17),
    ("Jraishan", "جريشان", "油田", 17),
    ("Samawa", "السماوة", "油田", 17),
    ("Block 12 (Iraq)", "الرقعة 12", "勘探区块", 17),
    ("Khudr Al-May", "خضر الماي", "油气开发区", 17),
    ("Fao", "فاو", "油气开发区", 17),
    ("Jabal Sanam", "جبل سنام", "油气开发区", 17),
    ("Sinbad", "السندباد", "油田", 17),
)

IRAN_GAS_ADDITIONS = (
    "Belal", "Farzad A", "Farzad B", "Kish", "North Pars", "Khartang",
    "Gardan", "Day", "Sefid Zakhur", "Sefid Baghun", "Halegan", "Eram",
)


def additions(record) -> list[dict]:
    output = []
    for name, label, kind, table in IRAQ_ADDITIONS:
        item = record("伊拉克", name, label, kind, None, None, source="Iraq EITI 2023",
                      note=f"EITI 2023表{table}具名清单；状态仅代表2023参考年，"
                      "不据此推定2026停复产；逐资产当前产量与坐标未核实。")
        item.update(source_url=EITI_2023_URL, inventory_table=str(table),
                    source_original_name=label)
        output.append(item)
    for name, label in (("Baba Dome", "巴巴穹隆"), ("Avana Dome", "阿瓦纳穹隆")):
        output.append(record("伊拉克", name, label, "油田组成区域", None, None,
                             source="Iraq EITI 2021", note="Kirkuk组成穹隆；不是独立油田。"))
    for name in IRAN_GAS_ADDITIONS:
        output.append(record("伊朗", name, name, "气田", None, None,
                             source="EIA Iran", note="EIA 2024第8—9页计划气田；"
                             "启动年份为当时预测，2026实际进度待核。未将计划能力作为产量。"))
    for name in ("Miran", "Bina Bawi", "Qara Dagh"):
        item = record("伊拉克", name, name, "油气特许区", None, None,
                      source="Iraq EITI 2023", note="Genel 2025年报具名许可证；"
                      "许可证退出/争议不证明油气资产永久停产；逐田现时实绩及独立坐标未核。")
        item.update(source="Genel Annual Report 2025",
                    source_url="https://genelenergy.com/wp-content/uploads/190326_Genel-AR_web-1.pdf")
        output.append(item)
    eni_url = "https://www.eni.com/en-IT/actions/global-activities/egypt.html"
    for name in ("Zohr", "Nooros", "Baltim South West", "Meleiha", "Denise West"):
        item = record("埃及", name, name, "油气田" if name == "Meleiha" else "气田",
                      None, None, source="Eni Egypt Factbook 2013",
                      note="Eni埃及当前资产页列名；Meleiha为资产区域，未分配公司产量。"
                      "Denise West为发现；其他资产的2026逐田产量未取得。")
        item.update(source="Eni Egypt Operations", source_url=eni_url)
        output.append(item)
    bp_url = "https://www.bp.com.cn/zh_cn/china/home/news/press-releases/news-05-17-2017.html"
    for name in ("Taurus", "Libra", "Giza", "Fayoum", "Raven"):
        item = record("埃及", name, name, "气田", None, None,
                      source="Eni Egypt Factbook 2013", note="BP西尼罗河三角洲五田名单；"
                      "项目合计不拆给单田，2017公告不能独立证明2026在产。")
        item.update(source="BP West Nile Delta", source_url=bp_url)
        output.append(item)
    return output


def register_statuses(assign):
    # Conservative status when the current year is not directly evidenced.
    for name, _, _, _ in IRAQ_ADDITIONS:
        assign("伊拉克", name, "historical_unverified", "2023参考年；2025-12发布",
               "低", "原始名录确认存在，当前停复产未证实；历史非生产名单不是当前状态。", EITI_2023_URL)
    assign("伊拉克", "Baba Dome | Avana Dome", "historical_unverified", "2021参考年", "低",
           "EITI 2021分别报送两个Kirkuk组成穹隆；未取得当前逐穹隆实绩。")
    assign("伊拉克", "Miran | Bina Bawi | Qara Dagh", "historical_unverified", "2025参考年；2026-03发布",
           "低", "原年报确认命名及许可证退出/争议；当前资产作业状态待核。")
    for name in IRAN_GAS_ADDITIONS:
        assign("伊朗", name, "historical_unverified", "2024-10报告", "低",
               "EIA拟建项目表确认命名；预计启动时间不能证明实际投产。")
    assign("埃及", "Zohr | Nooros | Baltim South West | Meleiha", "unknown", "网页复核2026-09-30",
           "低", "运营商资产页确认存在；不单凭名录推定当日生产。")
    assign("埃及", "Denise West", "discovered", "网页复核2026-09-30", "中",
           "Eni当前埃及资产页明确称Denise W为天然气发现。")
    assign("埃及", "Taurus | Libra | Giza | Fayoum | Raven", "historical_unverified", "2017-05-17名单",
           "低", "原始公告确认五个具名气田；当前逐田生产待核。")
