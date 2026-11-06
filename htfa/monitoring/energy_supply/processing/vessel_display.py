"""Shared vessel labels; source text and precise timestamps remain archived."""
import re
from functools import lru_cache
from zoneinfo import ZoneInfo

import htfa.monitoring.energy_supply.data.storage as data_store
import htfa.monitoring.energy_supply.processing.ais as ais


def _key(value):
    return re.sub(r"[^A-Z0-9\u3400-\u9fff]+", " ", str(value).upper()).strip()


@lru_cache(maxsize=1)
def _translations(snapshot_identity):
    document = data_store.read_json("data/vessel_destinations_zh.json")
    return {_key(alias): chinese for chinese, aliases in document.items() for alias in aliases}


@lru_cache(maxsize=1)
def _translation_pattern(snapshot_identity):
    aliases = sorted(_translations(snapshot_identity), key=len, reverse=True)
    return re.compile(r"(?<![A-Z0-9])(?:" + "|".join(map(re.escape, aliases)) + r")(?![A-Z0-9])")


@lru_cache(maxsize=4096)
def _destination_text(value, snapshot_identity):
    raw = str(value or "").strip()
    if ">" in raw and all(part.strip() for part in raw.split(">")):
        return " → ".join(_destination_text(part.strip(), snapshot_identity) for part in raw.split(">"))
    key = _key(raw)
    if not key or key in {"0", "NA", "N A", "NONE", "NULL", "UNKNOWN", "NOT DEFINED", "XXX"}:
        return "未知目的地"
    translations = _translations(snapshot_identity)
    if key in translations:
        return translations[key]
    # Translate only explicit place names/terms; never guess a port from a
    # fuzzy spelling, a vessel position, or an unverified platform identifier.
    text = _translation_pattern(snapshot_identity).sub(lambda match: translations[match.group()], key)
    text = re.sub(r"(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff])", "", text)
    if re.search(r"[A-Z]", text):
        return f"{text}（原文待核：{raw}）" if re.search(r"[\u3400-\u9fff]", text) else f"目的地待核（{raw}）"
    if not re.search(r"[\u3400-\u9fff]", text):
        return f"目的地待核（{raw}）"
    return text


def destination_text(value):
    return _destination_text(value, data_store.database_identity())


def destination_label(row):
    return destination_text(row.get("destination"))


def reception_time(value):
    stamp = ais.parse_utc(value)
    if stamp is None:
        return "—"
    local = stamp.astimezone(ZoneInfo("Asia/Dubai"))
    return f"{local.year}年{local.month:02}月{local.day:02}日{local.hour}时"


def source_label(row):
    source = str(row.get("data_source") or row.get("source") or "").strip()
    return "openwaters" if "openwaters" in re.sub(r"\s+", "", source).lower() else source or "—"
