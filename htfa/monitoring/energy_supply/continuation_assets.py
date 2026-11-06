"""Evidence-led continuation of the preserved September audit.

The dated JSON is an explicit review decision list, never a scraped import.
Source access, name confirmation, flow, capacity and map position stay separate.
"""
import json
from pathlib import Path
from htfa.monitoring.energy_supply.data_store import read_json

REVIEW_DATE = "2026-10-01"
EVIDENCE = read_json("CONTINUATION_EVIDENCE_2026-10-01.json")
RESOLVED = {(r["country"], r["name"]) for r in EVIDENCE["additions"]}
UPDATED = RESOLVED | {(r["country"], r["name"]) for r in EVIDENCE["measurements"]}
UPDATED |= {(r["country"], r["name"]) for r in EVIDENCE["coordinates"]}
REVISED = {(r["country"], r["name"]) for r in EVIDENCE.get("scope_revisions", [])}
UPDATED |= REVISED


def additions(record):
    result = []
    for row in EVIDENCE["additions"]:
        item = record(row["country"], row["name"], row["name"], row["asset_type"],
                      None, None, source="Iraq EITI 2023", note=row["note"])
        item.update(source=row["source"], source_url=row["source_url"],
                    catalog_evidence_url=row["source_url"],
                    numeric_audit="名称/资产层级有证据；未取得本层级商业产量，不填储量或试井流量")
        result.append(item)
    return result


def apply_measurements(assets):
    index = {(a["country"], a["name"]): a for a in assets}
    for row in EVIDENCE.get("scope_revisions", []):
        item = index[(row["country"], row["name"])]
        item.update({k: row[k] for k in ("asset_type", "source", "source_url", "note")})
    for row in EVIDENCE["measurements"]:
        item = index[(row["country"], row["name"])]
        # Preserve the previous directory evidence when a primary metric replaces it.
        item.setdefault("catalog_evidence_url", item["source_url"])
        item.update({k: v for k, v in row.items() if k not in {"country", "name"}})


def coordinates():
    return {(r["country"], r["name"]): {k: v for k, v in r.items() if k not in {"country", "name"}}
            for r in EVIDENCE["coordinates"]}


def levels():
    return {(r["country"], r["name"]): r["asset_level"]
            for r in EVIDENCE["additions"] + EVIDENCE.get("scope_revisions", [])}


def revise_statuses(revise):
    for row in EVIDENCE.get("scope_revisions", []):
        revise(row["country"], row["name"], row["state"], row["as_of"],
               row["confidence"], row["note"], row["source_url"])


def register_statuses(assign):
    for row in EVIDENCE["additions"]:
        assign(row["country"], row["name"], row["state"], row["as_of"],
               row["confidence"], row["status_basis"], row["status_url"])


def finish_review(assets):
    index = {(a["country"], a["name"]): a for a in assets}
    for key in UPDATED:
        item = index[key]
        item["data_audit_date"] = REVIEW_DATE
        item["freshness_note"] = ("名称/位置复核不证明当前产量；缺失不等于零" if item["value"] is None
                                  else "仅适用于所标观测/规划期；2026-10-01是复核日，不是实绩日")
        if key in RESOLVED | REVISED:
            item["status_audit_date"] = REVIEW_DATE
    for row in EVIDENCE["additional_measurements"]:
        index[(row["country"], row["name"])]["additional_measurements"].append(
            {k: v for k, v in row.items() if k not in {"country", "name"}})
