"""Apply dated asset evidence in order, retaining each review's scope and dates."""

from __future__ import annotations

from dataclasses import dataclass

from htfa.monitoring.energy_supply.processing.evidence import read_json


def _key(row: dict) -> tuple[str, str]:
    return row["country"], row["name"]


@dataclass(frozen=True)
class AssetReview:
    date: str
    evidence: dict

    def additions(self, record) -> list[dict]:
        output = []
        for row in self.evidence["additions"]:
            item = record(
                row["country"],
                row["name"],
                row.get("name_cn", row["name"]),
                row["asset_type"],
                None,
                None,
                source=row["source"],
                source_url=row["source_url"],
                note=row["note"],
            )
            item["catalog_evidence_url"] = row["source_url"]
            output.append(item)
        return output

    def apply_measurements(self, assets: list[dict]) -> None:
        index = {_key(asset): asset for asset in assets}
        for row in self.evidence["measurements"]:
            item = index[_key(row)]
            item.setdefault("catalog_evidence_url", item["source_url"])
            item.update(
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"country", "name"}
                }
            )

    def levels(self) -> dict:
        return {_key(row): row["asset_level"] for row in self.evidence["additions"]}

    def parents(self) -> dict:
        return {_key(row): row["parent"] for row in self.evidence.get("parents", [])}

    def register_statuses(self, assign) -> None:
        self._apply_statuses(assign, self.evidence["additions"])

    def revise_statuses(self, revise) -> None:
        self._apply_statuses(revise, self.evidence["statuses"])

    @staticmethod
    def _apply_statuses(assign, rows: list[dict]) -> None:
        for row in rows:
            assign(
                row["country"],
                row["name"],
                row["state"],
                row["as_of"],
                row["confidence"],
                row["status_basis"],
                row["status_url"],
            )

    @property
    def status_keys(self) -> set:
        return {
            _key(row)
            for kind in ("additions", "statuses")
            for row in self.evidence[kind]
        }

    @property
    def reviewed_keys(self) -> set:
        return self.status_keys | {_key(row) for row in self.evidence["measurements"]}


def _load(date: str, filename: str) -> AssetReview:
    return AssetReview(date, read_json(filename))


def public_reference_coordinates() -> dict:
    """Only reviewed missing points; mirror accuracy is unknown, so use proxies."""
    evidence = _evidence()
    return {
        _key(row): {
            "lat": row["record"]["latitude"],
            "lon": row["record"]["longitude"],
            "precision": "GEM 2026-03目录参考点；原始精度未保留，非核验油田中心或井位",
            "source": "Global Energy Monitor（2026-03公开镜像；CC BY 4.0）",
            "url": evidence["PUBLIC_METADATA"]["source"]["mirror_url"],
            "proxy": True,
        }
        for row in evidence["PUBLIC_METADATA"]["records"]
        if row["use_reference_coordinates"]
    }


def apply_public_metadata(assets: list[dict]) -> None:
    """Keep directory facts separate from measurements and current status."""
    evidence = _evidence()
    index = {_key(asset): asset for asset in assets}
    for row in evidence["PUBLIC_METADATA"]["records"]:
        index[_key(row)]["public_metadata"] = {
            **row["record"],
            "release": evidence["PUBLIC_METADATA"]["source"]["release"],
            "review_date": evidence["PUBLIC_METADATA"]["review_date"],
            "source_url": evidence["PUBLIC_METADATA"]["source"]["mirror_url"],
            "confidence": evidence["PUBLIC_METADATA"]["source"]["confidence"],
            "limitations": evidence["PUBLIC_METADATA"]["source"]["limitations"],
        }


def attach_gem_production_candidates(assets: list[dict]) -> None:
    """Keep secondary transcriptions as leads until their original units are checked."""
    evidence = _evidence()
    index = {_key(asset): asset for asset in assets}
    for row in evidence["GEM_HISTORICAL_PRODUCTION"]["rows"]:
        index[_key(row)].setdefault("gem_production_candidates", []).append(row)


def apply_production_recheck(assets: list[dict]) -> None:
    """Apply reviewed source values before hierarchy and commodity classification."""
    evidence = _evidence()
    index = {_key(asset): asset for asset in assets}
    for row in evidence["PRODUCTION_RECHECK"]["measurements"]:
        asset = index[_key(row)]
        asset["production_evidence"] = row
        if asset["value"] is not None:
            asset.setdefault("previous_measurements", []).append(
                {
                    key: asset.get(key)
                    for key in (
                        "value",
                        "metric_type",
                        "unit",
                        "data_date",
                        "source",
                        "source_url",
                        "note",
                    )
                }
            )
        asset.setdefault("catalog_evidence_url", asset["source_url"])
        for key in (
            "value",
            "metric_type",
            "unit",
            "data_date",
            "source",
            "source_url",
            "note",
            "numeric_audit",
            "annual_barrels",
            "calendar_days",
        ):
            if key in row:
                asset[key] = row[key]


def finish_production_recheck(assets: list[dict], output_types: set[str]) -> None:
    """Attach named aggregate references without copying totals into field values."""
    evidence = _evidence()
    index = {_key(asset): asset for asset in assets}
    for row in evidence["PRODUCTION_RECHECK"].get("scope_adjustments", []):
        asset = index[_key(row)]
        asset["ownership_basis"] = row["ownership_basis"]
        asset["data_audit_date"] = evidence["PRODUCTION_RECHECK"]["review_date"]
    for asset in assets:
        row = asset.get("production_evidence")
        if row:
            asset["ownership_basis"] = row["ownership_basis"]
            asset["data_audit_date"] = evidence["PRODUCTION_RECHECK"]["review_date"]
            asset["freshness_note"] = (
                "数值只对应标注期间；单田、合计和权益范围见备注，复核日不是观测日"
            )
            for previous in asset.get("previous_measurements", []):
                asset["additional_measurements"].append(
                    {
                        **previous,
                        "commodity": "crude_oil"
                        if str(previous.get("unit") or "").startswith("千桶/日")
                        else asset["commodity"],
                        "basis": previous.get("note")
                        or "保留此前来源指标；不同日期与口径分别列示",
                    }
                )
        asset["aggregate_references"] = []
        parent_name = asset["parent_asset"]
        seen = {_key(asset)}
        while parent_name:
            parent_key = asset["country"], parent_name
            if parent_key in seen:
                raise ValueError(f"Cyclic aggregate reference: {parent_key}")
            seen.add(parent_key)
            parent = index[parent_key]
            compatible_product = not (
                asset["commodity"] == "natural_gas" and parent["unit"] == "千桶/日"
            )
            if (
                parent["value"] is not None
                and parent["metric_type"] in output_types
                and compatible_product
            ):
                asset["aggregate_references"].append(
                    {
                        **{
                            key: parent.get(key)
                            for key in (
                                "value",
                                "metric_type",
                                "unit",
                                "data_date",
                                "source",
                                "source_url",
                                "ownership_basis",
                                "commodity",
                                "note",
                            )
                        },
                        "id": f"{parent['country']}/{parent['name']}",
                        "scope": parent["name"],
                        "members": parent["constituent_assets"],
                        "basis": "已登记上级资产合计；没有分配为组成田产量，不重复汇总",
                    }
                )
                break
            parent_name = parent["parent_asset"]
    for row in evidence["PRODUCTION_RECHECK"]["aggregate_measurements"]:
        for name in row["members"]:
            index[row["country"], name]["aggregate_references"].append(row)
    for row in evidence["PRODUCTION_RECHECK"].get("historical_measurements", []):
        index[_key(row)]["additional_measurements"].append(
            {
                **row,
                "commodity": "crude_oil",
                "basis": row["note"],
            }
        )
    for row in evidence["PRODUCTION_RECHECK"]["asset_reviews"]:
        index[_key(row)]["production_review"] = row


def finish_reviews(assets: list[dict]) -> None:
    """Preserve the distinct country, freshness, and note rules of both reviews."""
    evidence = _evidence()
    index = {_key(asset): asset for asset in assets}
    for asset in assets:
        asset["countries"] = [asset["country"]]
    for review in evidence["REVIEWS"]:
        for row in review.evidence["shared_countries"]:
            index[_key(row)].update(
                countries=row["countries"],
                shared_country_evidence_url=row["evidence_url"],
            )
    for row in evidence["GULF"].evidence["measurements"]:
        if "ownership_basis" in row:
            index[_key(row)]["ownership_basis"] = row["ownership_basis"]
    rechecked = {
        (row["country"], name)
        for row in evidence["GULF"].evidence["rechecked"]
        for name in row["names"]
    }
    gulf_status_keys = evidence["GULF"].status_keys | rechecked
    for key in evidence["GULF"].reviewed_keys | rechecked:
        item = index[key]
        item["data_audit_date"] = evidence["GULF"].date
        item["freshness_note"] = (
            "仅适用于标注的证据/观测期；复核日不是实绩日；缺失不等于零"
        )
        if key in gulf_status_keys:
            item["status_audit_date"] = evidence["GULF"].date
    for review in evidence["REVIEWS"]:
        for row in review.evidence["additional_measurements"]:
            item = index[_key(row)]
            item["data_audit_date"] = review.date
            item["additional_measurements"].append(
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"country", "name"}
                }
            )
    reviewed = evidence["FOLLOWUP"].reviewed_keys
    followup_status_keys = evidence["FOLLOWUP"].status_keys
    for row in evidence["FOLLOWUP"].evidence["notes"]:
        reviewed.add(_key(row))
        item = index[_key(row)]
        item["note"] += " " + row["note"]
        item.setdefault("followup_evidence", []).append(row)
    index["科威特", "Homah"]["aliases"].append("Houma")
    for key in reviewed:
        item = index[key]
        item["data_audit_date"] = evidence["FOLLOWUP"].date
        item["freshness_note"] = "仅适用于标注的证据期；复核日不是产量或停复产观测日"
        if key in followup_status_keys:
            item["status_audit_date"] = evidence["FOLLOWUP"].date


def _evidence():
    GULF = _load("2026-10-03", "GULF_REVIEW_2026-10-03.json")
    FOLLOWUP = _load("2026-10-04", "FINAL_REVIEW_2026-10-04.json")
    REVIEWS = (GULF, FOLLOWUP)
    PUBLIC_METADATA = read_json("data/asset_public_metadata.json")
    GEM_HISTORICAL_PRODUCTION = read_json("data/gem_historical_production.json")
    PRODUCTION_RECHECK = read_json("data/production_recheck.json")
    return {
        "FOLLOWUP": FOLLOWUP,
        "GEM_HISTORICAL_PRODUCTION": GEM_HISTORICAL_PRODUCTION,
        "GULF": GULF,
        "PRODUCTION_RECHECK": PRODUCTION_RECHECK,
        "PUBLIC_METADATA": PUBLIC_METADATA,
        "REVIEWS": REVIEWS,
    }
