"""Bilingual display labels without changing source identities or historical keys."""
import re


def display_name(row):
    if row.get("display_name"):
        return row["display_name"]
    english = str(row.get("name_en") or row.get("name") or row.get("portname") or row.get("英文名称") or "").strip()
    chinese = str(row.get("name_cn") or row.get("中文名称") or "").strip()
    if chinese and english and chinese != english:
        return f"{chinese}（{english}）"
    return chinese or english or str(row.get("portid") or "")


def enrich_catalog(kind, rows, translations):
    result = []
    for original in rows:
        row = dict(original)
        english = row.get("name_en") or row.get("name") or row.get("portname")
        if not english:
            result.append(row)
            continue
        chinese = translations.get("assets", {}).get(english, row.get("name_cn")) if kind == "assets" else row.get("name_cn")
        if not chinese:
            # Keep source-only/unresolved records intact; the publisher separately
            # requires bilingual labels for every production catalog entity.
            result.append(row)
            continue
        row["name_en"] = english
        if kind == "assets":
            row["name_cn"] = translations.get("assets", {}).get(english, row.get("name_cn"))
        row.pop("display_name", None)
        row["display_name"] = display_name(row)
        result.append(row)
    return result


def validate_catalogs(catalogs):
    for kind, rows in catalogs.items():
        for row in rows:
            if not re.search(r"[\u3400-\u9fff]", row.get("name_cn") or ""):
                raise ValueError(f"Missing Chinese {kind} name: {row.get('name') or row.get('portid')}")
            if not row.get("name_en") or row.get("display_name") != f"{row['name_cn']}（{str(row['name_en']).strip()}）":
                raise ValueError(f"Invalid bilingual {kind} name: {row.get('portid') or row.get('name')}")
