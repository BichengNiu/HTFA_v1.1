"""Reviewed port metadata corrections; raw identities and history are retained.

Per-ID receipts and unresolved coverage are in audits/port_catalog_review_2026-10-16.json.
Corrections apply on read, and the existing snapshot publisher persists them on
its next successful publication. This module never opens or writes a database.
"""
from __future__ import annotations

from htfa.monitoring.energy_supply.processing.entity_names import display_name

REVIEW_VERSION = "2026-10-16"
# User-selected monitoring scope. Archived catalogs and historical facts remain
# intact; this allowlist is applied at the dashboard's shared catalog boundary.
PORT_COUNTRIES = frozenset({
    "Bahrain", "Djibouti", "Egypt", "Iran", "Iraq", "Kuwait", "Oman",
    "Qatar", "Saudi Arabia", "United Arab Emirates", "Yemen",
})


def monitored_ports(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("country") in PORT_COUNTRIES]


EXPECTED_IDENTITIES = {'facility_wpi48104': ('Sharmah', 'Saudi Arabia'),
 'facility_yanbu_north_crude': ('Yanbu North Crude Terminal', 'Saudi Arabia'),
 'facility_yanbu_north_refined': ('Yanbu North Refined Product Terminal', 'Saudi Arabia'),
 'facility_yanbu_south': ('Yanbu South Terminal', 'Saudi Arabia'),
 'port1081': ('Rabigh', 'Saudi Arabia'),
 'port1117': ('Al Ruwais', 'Qatar'),
 'port1408': ('Yanbu (Yanbu city)', 'Saudi Arabia'),
 'port18': ('Hudaydah (Hodeidah)', 'Yemen'),
 'port192': ('Port Said', 'Egypt'),
 'port2031': ('King Abdullah Port', 'Saudi Arabia'),
 'port2074': ('Jazan', 'Saudi Arabia'),
 'port2109': ('Mokha', 'Yemen'),
 'port2218': ('Shuqaiq', 'Saudi Arabia'),
 'port2219': ('Salif', 'Yemen'),
 'port2245': ('Ras Isa Terminal', 'Yemen'),
 'port274': ('Damietta', 'Egypt'),
 'port294': ('Djibouti', 'Djibouti'),
 'port304': ('Duba (Port of Neom)', 'Saudi Arabia'),
 'port305': ('Duba Bulk Plant Tanker Terminal', 'Saudi Arabia'),
 'port321': ('Al Adabiyah', 'Egypt'),
 'port518': ('Jeddah', 'Saudi Arabia'),
 'port519': ('Shoaiba', 'Saudi Arabia'),
 'port570': ('Yanbu (King Fahd Port)', 'Saudi Arabia'),
 'port71': ('As Suways', 'Egypt'),
 'port746': ('Salalah', 'Oman'),
 'port747': ('Mina Saqr', 'United Arab Emirates'),
 'port828': ('El Sokhna', 'Egypt'),
 'port9': ('Aden', 'Yemen'),
 'port984': ('Duqm', 'Oman'),
 'wpi47855': ('Doraleh', 'Djibouti'),
 'wpi47880': ('Assab', 'Eritrea'),
 'wpi48035': ('Sokhna Port Gas Tanker Terminal', 'Egypt'),
 'wpi48053': ('Ras Sudr', 'Egypt'),
 'wpi48055': ('Ain Sukhna Terminal', 'Egypt'),
 'wpi48280': ('Hulaylah Oil Terminal', 'United Arab Emirates'),
 'wpi48406': ('Khawr Al Zubair Lng Terminal', 'Iraq')}

CORRECTIONS = {'facility_wpi48104': {'region': '红海'},
 'facility_yanbu_north_crude': {'region': '红海'},
 'facility_yanbu_north_refined': {'region': '红海'},
 'facility_yanbu_south': {'region': '红海'},
 'port1081': {'region': '红海', 'wpi_ids': [48130], 'wpi_names': ['Rabigh']},
 'port1117': {'name_cn': '鲁韦斯港（卡塔尔）'},
 'port1408': {'region': '红海', 'wpi_ids': [48120], 'wpi_names': ['Yanbu']},
 'port18': {'region': '红海'},
 'port192': {'region': '地中海'},
 'port2031': {'region': '红海'},
 'port2074': {'region': '红海', 'wpi_ids': [48142], 'wpi_names': ['Jizan']},
 'port2109': {'region': '红海'},
 'port2218': {'region': '红海'},
 'port2219': {'region': '红海'},
 'port2245': {'region': '红海'},
 'port274': {'region': '地中海'},
 'port294': {'region': '亚丁湾'},
 'port304': {'region': '红海', 'wpi_ids': [48106], 'wpi_names': ['Duba']},
 'port305': {'region': '红海', 'wpi_ids': [48108], 'wpi_names': ['Duba Bulk Plant Tanker Terminal']},
 'port321': {'region': '苏伊士湾'},
 'port518': {'region': '红海', 'wpi_ids': [48140], 'wpi_names': ['Jiddah']},
 'port519': {'region': '红海'},
 'port570': {'region': '红海', 'wpi_ids': [48121], 'wpi_names': ['King Fahd Port']},
 'port71': {'region': '苏伊士湾'},
 'port746': {'wpi_ids': [48230], 'wpi_names': ['Mina Raysut']},
 'port747': {'region': '波斯湾'},
 'port828': {'region': '苏伊士湾'},
 'port9': {'region': '亚丁湾'},
 'port984': {'wpi_ids': [48235], 'wpi_names': ['Duqm']},
 'wpi47855': {'region': '亚丁湾'},
 'wpi47880': {'region': '红海'},
 'wpi48035': {'region': '苏伊士湾'},
 'wpi48053': {'region': '苏伊士湾'},
 'wpi48055': {'region': '苏伊士湾'},
 'wpi48280': {'region': '波斯湾'},
 'wpi48406': {'name_cn': '祖拜尔液化石油气码头'}}

def apply_port_metadata(rows):
    result = []
    for original in rows:
        # The retired port operating-status field is absent from current
        # catalogs and exports. Original review documents remain archived.
        original = {key: value for key, value in original.items()
                    if not key.startswith(("port_operating_status", "port_status_"))
                    and key not in ("recent_daily_activity_normal", "activity_status_as_of")}
        pid = str(original.get("portid", ""))
        patch = CORRECTIONS.get(pid)
        if patch is None:
            result.append(original)
            continue
        expected_name, expected_country = EXPECTED_IDENTITIES[pid]
        if ((original.get("name") and original["name"] != expected_name)
                or (original.get("country") and original["country"] != expected_country)):
            raise ValueError(f"港口核查映射与来源身份不匹配：{pid}")
        row = dict(original)
        for field, value in patch.items():
            if field in {"wpi_ids", "wpi_names"}:
                row[field] = list(dict.fromkeys([*row.get(field, []), *value]))
            else:
                if row.get(field) != value:
                    row.setdefault(field+"_source", row.get(field))
                row[field] = value
        if "name_cn" in patch:
            row.pop("display_name", None)
            row["display_name"] = display_name(row)
        row["metadata_review_version"] = REVIEW_VERSION
        result.append(row)
    return result
