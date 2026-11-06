"""Supplement PortWatch coverage without inventing PortWatch observations."""
import json
from pathlib import Path
from htfa.monitoring.energy_supply.data_store import read_json

WPI_SOURCE = "https://msi.nga.mil/api/publications/download?key=16694622%2FSFH00000%2FUpdatedPub150.csv"
WPI_ROWS = read_json("port_inventory_wpi_2026-09-30.json")
NGA_SAILING = "https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf"


# Chinese labels used in the country and port selectors. Source catalog values
# remain unchanged for filtering and API requests.
PORT_REVIEW = read_json("PORT_REVIEW_2026-10-03.json")

PORT_FOLLOWUP = read_json("PORT_REVIEW_2026-10-04.json")

_COUNTRY_NAMES_ZH = {
    "bahrain": "巴林",
    "djibouti": "吉布提",
    "egypt": "埃及",
    "eritrea": "厄立特里亚",
    "iran": "伊朗",
    "iraq": "伊拉克",
    "kuwait": "科威特",
    "oman": "阿曼",
    "qatar": "卡塔尔",
    "saudi arabia": "沙特阿拉伯",
    "united arab emirates": "阿联酋",
    "yemen": "也门",
    "uae": "阿联酋",
    "united arab emirates (uae)": "阿联酋",
    "islamic republic of iran": "伊朗",
    "republic of yemen": "也门",
    "state of kuwait": "科威特",
}

def country_label(country: object) -> str:
    raw = str(country or "").strip()
    if not raw:
        return "国家未知"
    if any("\u4e00" <= character <= "\u9fff" for character in raw):
        return raw
    return _COUNTRY_NAMES_ZH.get(raw.casefold(), "其他国家")


def _port_name_key(value: object) -> str:
    raw = str(value or "").strip().casefold().replace("’", "'")
    raw = raw.replace("-", " ").replace("/", " ")
    return " ".join(raw.split())


_PORT_NAMES_ZH = {
    _port_name_key('Duqm'): '杜库姆港',
    _port_name_key('Salalah'): '塞拉莱港',
    _port_name_key('Duba (Port of Neom)'): '杜巴港（NEOM）',
    _port_name_key('Duba Bulk Plant Tanker Terminal'): '杜巴油轮码头',
    _port_name_key('Al Ruwais'): '鲁韦斯港（卡塔尔）',
    _port_name_key('Jeddah'): '吉达港',
    _port_name_key('Shoaiba'): '舒艾拜港（沙特）',
    _port_name_key('Yanbu (King Fahd Port)'): '延布法赫德国王工业港',
    _port_name_key('Yanbu (Yanbu city)'): '延布商业港',
    _port_name_key('Rabigh'): '拉比格港',
    _port_name_key('King Abdullah Port'): '阿卜杜拉国王港',
    _port_name_key('Jazan'): '吉赞港',
    _port_name_key('Shuqaiq'): '舒盖格港',
    _port_name_key('Nowshahr Port'): '诺沙赫尔港',
    _port_name_key('Amirabad Port'): '阿米拉巴德港',
    _port_name_key('Bandar-e Anzali'): '安扎利港',
    _port_name_key('Oman - Offshore Oil Terminal 1'): '阿曼海上石油终端1（源库名称）',
    _port_name_key("Ras Al Ghar"): "拉斯盖尔港",
    _port_name_key("Kharg Island Oil Terminal"): "哈尔克岛石油码头",
    _port_name_key("Bandar-E Mahshahr"): "马赫沙赫尔港",
    _port_name_key("Ras Sudr"): "拉斯苏德尔港",
    _port_name_key("Khorramshahr"): "霍拉姆沙赫尔港",
    _port_name_key("Umm Qasr"): "乌姆盖斯尔港",
    _port_name_key("Bandar Khomeyni"): "霍梅尼港",
    _port_name_key("Mina Ash Shuaybah"): "舒艾拜港",
    _port_name_key("Al Kuwayt"): "科威特港",
    _port_name_key("Al Jubayl"): "朱拜勒港",
    _port_name_key("Mina Az Zawr"): "祖尔港",
    _port_name_key("Ras Al Khafji"): "哈夫吉港",
    _port_name_key("Ras  Tannurah"): "拉斯坦努拉港",
    _port_name_key("Mina Salman"): "萨勒曼港",
    _port_name_key("Al-Basra Oil Terminal"): "巴士拉石油码头",
    _port_name_key("Al Rayyan Terminal"): "阿尔赖扬码头",
    _port_name_key("As Suways"): "苏伊士港",
    _port_name_key("Al Basrah"): "巴士拉港",
    _port_name_key("Khawr Al Zubair"): "祖拜尔港",
    _port_name_key("Abadan"): "阿巴丹港",
    _port_name_key("Khosrowabad"): "霍斯罗阿巴德港",
    _port_name_key("El Ismailiya"): "伊斯梅利亚港",
    _port_name_key("Damietta"): "达米埃塔港",
    _port_name_key("Khawr Al Amaya"): "阿迈耶港",
    _port_name_key("Mina Abd Allah"): "阿卜杜拉港",
    _port_name_key("Mina Al Ahmadi"): "艾哈迈迪港",
    _port_name_key("Jask"): "贾斯克港",
    _port_name_key("Khawr Al Zubair Lng Terminal"): "祖拜尔液化石油气码头",
    _port_name_key("Jazireh-Ye Hormoz"): "霍尔木兹岛港",
    _port_name_key("Jazireh-Ye Sirri"): "锡里岛港",
    _port_name_key("Khawr Fakkan"): "豪尔费坎港",
    _port_name_key("Mina Qabus"): "卡布斯港",
    _port_name_key("Mina Al Fahl"): "法赫勒港",
    _port_name_key("Dammam"): "达曼港",
    _port_name_key("Ju Aymah Oil Terminal"): "朱艾玛石油码头",
    _port_name_key("Al Manamah"): "麦纳麦港",
    _port_name_key("Ju Aymah Lpg Terminal"): "朱艾玛液化石油气码头",
    _port_name_key("Doha Harbor"): "多哈港",
    _port_name_key("Al Mukha"): "穆哈港",
    _port_name_key("Qalhat Lng Terminal"): "卡尔哈特液化天然气码头",
    _port_name_key("Ras Isa Marine Terminal"): "拉斯伊萨海洋码头",
    _port_name_key("Zirkuh Oil Field"): "吉尔库油田终端",
    _port_name_key("Sitrah"): "西特拉港",
    _port_name_key("Sokhna Port Gas Tanker Terminal"): "苏赫纳港气体船码头",
    _port_name_key("Port Of Sohar"): "苏哈尔港",
    _port_name_key("Bur Sa'id"): "塞得港",
    _port_name_key("North Ain Sukhna Port"): "苏赫纳北港",
    _port_name_key("Assab"): "阿萨布港",
    _port_name_key("El-Adabiya"): "阿达比亚港",
    _port_name_key("Ain Sukhna Terminal"): "艾因苏赫纳码头",
    _port_name_key("Al Ahmadi"): "艾哈迈迪港",
    _port_name_key("Aden"): "亚丁港",
    _port_name_key("Khawr Khasab"): "哈萨卜港",
    _port_name_key("Bandar Abbas"): "阿巴斯港",
    _port_name_key("Hulaylah Oil Terminal"): "哈莱拉石油码头",
    _port_name_key("Mina Saqr"): "萨克尔港",
    _port_name_key("Jazireh-Ye Lavan Oil Terminal"): "拉万岛石油码头",
    _port_name_key("Sharjah Offshore Terminal"): "沙迦海上码头",
    _port_name_key("Umm Al Qaywayn"): "乌姆盖万港",
    _port_name_key("Al Jazeera Port"): "贾齐拉港",
    _port_name_key("Mina Jabal Ali"): "杰贝阿里港",
    _port_name_key("Ash Shariqah"): "沙迦港",
    _port_name_key("Dubayy"): "迪拜港",
    _port_name_key("Ajman"): "阿治曼港",
    _port_name_key("Al Hamriyah Lpg Terminal"): "哈姆里亚液化石油气码头",
    _port_name_key("Doraleh"): "多哈雷港",
    _port_name_key("Ras Al Mishab"): "米沙卜港",
    _port_name_key("Salif"): "萨利夫港",
    _port_name_key("Mubarraz Oil Terminal"): "穆巴拉兹石油码头",
    _port_name_key("Doha"): "多哈港",
    _port_name_key("Zirkuh"): "吉尔库岛港",
    _port_name_key("Fateh Oil Terminal"): "法特赫石油码头",
    _port_name_key("Al Shaheen Terminal"): "阿尔沙欣码头",
    _port_name_key("Jabal Az Zannah/ruways"): "杰贝勒宰纳／鲁韦斯港",
    _port_name_key("Jazirat Halul"): "哈卢尔岛港",
    _port_name_key("Umm An Nar"): "乌姆纳尔港",
    _port_name_key("Umm Said"): "乌姆赛义德港",
    _port_name_key("Ras Laffan"): "拉斯拉凡港",
    _port_name_key("Abu Zaby"): "阿布扎比港",
    _port_name_key("Jazirat Das"): "达斯岛港",
    _port_name_key("Bushehr"): "布什尔港",
    _port_name_key("Bandar Taheri Offshore Terminal"): "塔赫里海上码头",
    _port_name_key("Chah Bahar"): "恰巴哈尔港",
    _port_name_key("Barkan Oil-loading Terminal"): "巴尔干石油装船码头",
    _port_name_key("Bandar-E Pars Terminal"): "帕尔斯港码头",
    _port_name_key("Sirus Oil Terminal"): "锡里斯石油码头",
    _port_name_key("Bandar-E Shahid Rejaie"): "沙希德拉贾伊港",
    _port_name_key("Hamad"): "哈马德港",
    _port_name_key("Al Fujayrah"): "富查伊拉港",
    _port_name_key("Khalifa Bin Salman"): "哈利法·本·萨勒曼港",
    _port_name_key("Djibouti"): "吉布提港",
    _port_name_key("Ras Tanura"): "拉斯坦努拉港",
    _port_name_key("Khor Fakkan"): "豪尔费坎港",
    _port_name_key("Port Said"): "塞得港",
    _port_name_key("Abu Dhabi"): "阿布扎比港",
    _port_name_key("Dubai"): "迪拜港",
    _port_name_key("Jebel Ali"): "杰贝阿里港",
    _port_name_key("Fujairah"): "富查伊拉港",
    _port_name_key("Sharjah"): "沙迦港",
    _port_name_key("Ras Al Khaimah"): "哈伊马角港",
    _port_name_key("Sohar"): "苏哈尔港",
    _port_name_key("Mina Qaboos"): "卡布斯港",
    _port_name_key("Mesaieed"): "乌姆赛义德港",
    _port_name_key("Imam Khomeini Port"): "霍梅尼港",
    _port_name_key("Khor Al Zubair"): "祖拜尔港",
    _port_name_key("Khalifa Port"): "哈利法港",
    _port_name_key("Jebel Dhanna"): "杰贝尔丹那港",
    # Raw catalog variants audited in PORT_ACTIVITY_AUDIT_2026-09-25.csv.
    _port_name_key("Hudaydah (Hodeidah)"): "荷台达港",
    _port_name_key("Mokha"): "穆哈港",
    _port_name_key("Ras Isa Terminal"): "拉斯伊萨海洋码头",
    _port_name_key("Bahregan"): "巴里根角港",
    _port_name_key("Bandar Khomeini"): "霍梅尼港",
    _port_name_key("Kharg Island"): "哈尔克岛石油码头",
    _port_name_key("Lavan"): "拉万岛石油码头",
    _port_name_key("Basrah Oil Terminal"): "巴士拉石油码头",
    _port_name_key("Mina Al Zour"): "祖尔港",
    _port_name_key("Shuaiba"): "舒艾拜港",
    _port_name_key("Shuwaikh"): "舒韦赫港",
    _port_name_key("Al Ruwais"): "鲁韦斯港（卡塔尔）",
    _port_name_key("Doha-Umm Said"): "多哈—乌姆赛义德港",
    _port_name_key("Hamad Port"): "哈马德港",
    _port_name_key("Juaymah"): "朱艾玛石油码头",
    _port_name_key("Jubail"): "朱拜勒港",
    _port_name_key("Ras Al-Khair"): "拉斯海尔港",
    _port_name_key("Saudi Arabia - Offshore Oil Terminal 1"): "海上石油终端1",
    _port_name_key("Das Island"): "达斯岛港",
    _port_name_key("Umm al Qaiwain"): "乌姆盖万港",
    _port_name_key("Zirku Island"): "吉尔库岛港",
    _port_name_key("Al Adabiyah"): "阿达比亚港",
    _port_name_key("El Sokhna"): "苏赫纳港",
    _port_name_key("Chabahar"): "恰巴哈尔港",
    _port_name_key("Port Sultan Qaboos"): "卡布斯港",
    _port_name_key("Shinas"): "希纳斯港",
    _port_name_key("Suwaiq"): "苏瓦伊克港",
    _port_name_key("Bandar Shahid Rajaee"): "沙希德拉贾伊港",
}


_PORT_ID_NAMES_ZH = {
    "port2025": "哈利法港",
    "port2236": "杰贝尔丹那港",
    "fso158": "海上石油终端1",
}


def port_label(port: dict) -> str:
    port_id = str(port.get("portid") or "")
    if port_id in _PORT_ID_NAMES_ZH:
        return _PORT_ID_NAMES_ZH[port_id]
    candidates = [port.get("name_cn"), port.get("name"), port.get("portname"),
                  port.get("node_name"), *port.get("wpi_names", [])]
    for candidate in candidates:
        raw = str(candidate or "").strip()
        if not raw:
            continue
        if any("\u4e00" <= character <= "\u9fff" for character in raw):
            return raw
        label = _PORT_NAMES_ZH.get(_port_name_key(raw))
        if label:
            return label
    port_id = str(port.get("portid") or "未知")
    return f"港口（编号{port_id}）"


def enrich(ports: list[dict]) -> list[dict]:
    output = [dict(p, statistics_available=True, activity_source="IMF PortWatch", source_url="https://portwatch.imf.org/pages/data-and-methodology",
                   coverage_note="AIS识别进港及模型估算货量；不是港务局实测吞吐量", wpi_ids=[], wpi_names=[])
              for p in ports]
    index = {p["portid"]: p for p in output}
    for row in WPI_ROWS:
        pid = row["portwatch_id"]
        if pid:
            if pid not in index:
                raise ValueError(f"WPI对应PortWatch点位已缺失/改变：{pid}，需重审跨库映射")
            if index[pid]["country"] != row["country"]:
                raise ValueError(f"WPI与PortWatch映射国家不符：{pid}")
            index[pid]["wpi_ids"].append(row["wpi"])
            index[pid]["wpi_names"].append(row["name"])
            index[pid]["inventory_source_url"] = WPI_SOURCE
            continue
        output.append(dict(portid=f"wpi{row['wpi']}", name=row["name"], country=row["country"],
                           lat=row["lat"], lon=row["lon"], region=row["region"],
                           wpi_ids=[row["wpi"]], source_url=WPI_SOURCE,
                           statistics_available=False, activity_source="无独立PortWatch统计", inventory_source_url=WPI_SOURCE,
                           coordinate_precision="NGA港口代表点；非泊位边界",
                           coverage_note="NGA名录补充，观察量未知；邻近综合港可能范围重叠，不借用邻港统计；名录日期未注明"))
    # Nautical positions represent the named coastal locality, not a surveyed berth.
    for pid, name, lat, lon, section in (
        ("facility_shinas", "Shinas", 24 + 46 / 60, 56 + 29 / 60, "11.22"),
        ("facility_suwaiq", "Suwaiq", 23 + 51 / 60, 57 + 27 / 60, "11.18"),
    ):
        output.append(dict(portid=pid, name=name, country="Oman", lat=lat, lon=lon, region="阿曼湾",
                           wpi_ids=[], statistics_available=False,
                           source_url="https://www.asyad.com/ports",
                           inventory_source_url=NGA_SAILING, activity_source="无独立PortWatch统计",
                           coordinate_precision=f"NGA Pub172 §{section}港口所在地代表点；分钟精度",
                           coverage_note="Asyad港口名录补充；坐标是所在地近似点，进港与货量未知"))
    output.extend(dict(row) for row in PORT_REVIEW["additions"] + PORT_FOLLOWUP["additions"])
    from htfa.monitoring.energy_supply.port_additions import extend_inventory
    output = extend_inventory(output)
    if len({p["portid"] for p in output}) != len(output):
        raise ValueError("合并港口目录出现重复编号")
    for port in output:
        if len(port["wpi_ids"]) > 1:
            port["coverage_note"] += "；跨库对应多个名录条目，PortWatch统计保持一个节点，不拆分：" + " / ".join(port["wpi_names"])
    for port in output:
        port["name_cn"] = port_label(port)
    return sorted(output, key=lambda p: (p["region"], p["country"], p["name"]))


SUPPLEMENTAL_IDS = {f"wpi{r['wpi']}" for r in WPI_ROWS if not r["portwatch_id"]} | {
    "facility_shinas", "facility_suwaiq"} | {r["portid"] for r in PORT_REVIEW["additions"] + PORT_FOLLOWUP["additions"]}
from htfa.monitoring.energy_supply.port_additions import SUPPLEMENTAL_IDS as ADDED_SUPPLEMENTAL_IDS
SUPPLEMENTAL_IDS |= ADDED_SUPPLEMENTAL_IDS
