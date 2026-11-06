"""Publisher-only, source-backed port additions; never borrow neighboring facts."""
from copy import deepcopy
import re

REVIEW_FILE = "PORT_ADDITIONS_2026-10-16.json"
REVIEW_VERSION = "2026-10-16"
SUPPLEMENTAL_IDS = frozenset({
    "wpi45163", "wpi45175", "wpi45180", "wpi47960", "wpi47970",
    "wpi47974", "wpi47982", "wpi47987", "wpi47988", "wpi47989",
    "wpi47990", "wpi48025", "wpi48057", "wpi48060", "wpi48065", "wpi48198",
    "facility_tadjourah", "facility_ghoubet", "facility_socotra", "facility_jcpdi",
    "facility_abu_flous", "facility_abu_qir", "facility_arish", "facility_gargoub",
    "facility_berenice", "facility_astara", "facility_fereydunkenar",
    "facility_dibba_uae", "facility_farasan", "facility_bandar_lengeh",
    "facility_dibba_oman", "facility_lima", "facility_shannah",
    "facility_masirah", "facility_taba", "facility_damerjog",
})


def extend_inventory(ports: list[dict]) -> list[dict]:
    # Called only by collection, after the publisher imports versioned evidence.
    # The dashboard reads the resulting immutable catalog from DuckDB.
    from htfa.monitoring.energy_supply import data_store
    from htfa.monitoring.energy_supply.port_metadata import PORT_COUNTRIES, apply_port_metadata
    document = data_store.read_json(REVIEW_FILE)
    if document.get("review_version") != REVIEW_VERSION:
        raise ValueError("港口补充证据版本不匹配")
    output = deepcopy(ports)
    by_id = {str(port["portid"]): port for port in output}
    if len(by_id) != len(output):
        raise ValueError("港口目录编号重复")
    additions = document["ports"]
    if len({p["portid"] for p in additions}) != len(additions):
        raise ValueError("港口补充证据编号重复")
    supplemental = {p["portid"] for p in additions if not p["statistics_available"]}
    if supplemental != SUPPLEMENTAL_IDS:
        raise ValueError("港口补充证据与注册编号不匹配")
    for checked in additions:
        pid = checked["portid"]
        lat, lon = checked["lat"], checked["lon"]
        unlocated = lat is None and lon is None
        valid_point = (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
                       and -90 <= lat <= 90 and -180 <= lon <= 180)
        if checked["country"] not in PORT_COUNTRIES or not (valid_point or (
            unlocated and checked.get("coordinate_status") == "unresolved_no_map_point"
            and not checked["statistics_available"]
        )):
            raise ValueError(f"港口补充范围或坐标无效：{pid}")
        if bool(re.fullmatch(r"(?:port|fso)\d+", pid)) != checked["statistics_available"]:
            raise ValueError(f"港口统计来源身份无效：{pid}")
        existing = by_id.get(pid)
        if existing is None:
            new = deepcopy(checked)
            output.append(new)
            by_id[pid] = new
            continue
        if any(existing.get(key) != checked[key] for key in ("name", "country")):
            raise ValueError(f"港口补充来源身份已改变：{pid}")
        verified_fill = (valid_point and existing.get("lat") is None and existing.get("lon") is None
                         and existing.get("coordinate_status") == "unresolved_no_map_point"
                         and checked.get("coordinate_status") == "verified_representative"
                         and str(checked.get("coordinate_source_url", "")).startswith("https://"))
        if not verified_fill and any((existing.get(key) is None) != (checked[key] is None)
               or (checked[key] is not None and abs(existing[key] - checked[key]) > 0.05)
               for key in ("lat", "lon")):
            raise ValueError(f"港口来源坐标偏移，需重新核对：{pid}")
        if verified_fill:
            existing["lat"], existing["lon"] = lat, lon
        for key, value in checked.items():
            if key in ("wpi_ids", "wpi_names"):
                existing[key] = list(dict.fromkeys([*existing.get(key, []), *value]))
            elif key not in ("lat", "lon"):
                existing[key] = deepcopy(value)
    return apply_port_metadata(output)
