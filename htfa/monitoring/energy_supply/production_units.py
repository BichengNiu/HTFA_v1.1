"""Read-only production views. Scope selection never allocates a group to fields.

Dates describe observations, not publication dates. Unknown scope/period stays
unknown. The source catalog and its historical measurements are not rewritten.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from htfa.monitoring.energy_supply.asset_values import display_value
from htfa.monitoring.energy_supply.entity_names import display_name

PRODUCTION = {"actual_output", "estimated_output", "estimated_daily_average",
              "derived_daily_average", "actual_output_boe", "historical_condensate_output"}
ESTIMATES = {"estimated_output", "estimated_daily_average"}
PRODUCTS = {"crude_oil": "原油", "natural_gas": "天然气", "condensate": "凝析油",
            "boe": "油当量", "liquids": "液体（组分未拆）", "unknown": "商品待核"}
STATISTICAL_PRODUCTS = {"crude_oil": "原油", "natural_gas": "天然气"}
MILLION_FT3_TO_MILLION_M3 = Decimal("0.028316846592")
SOURCE_RECHECK_UPDATES = {
    "https://genelenergy.com/wp-content/uploads/Genel-2024-Q1-trading-update.pdf":
        "https://genelenergy.com/wp-content/uploads/2020/09/Genel-Trading-and-operations-update-FINAL-PR.pdf",
}

# Reviewed against the existing source notes. These are measurement products,
# independent of whether the asset itself produces both oil and gas.
CRUDE_MEASUREMENTS = {"Shah", "Faihaa", "Tuba", "Dukhan", "Block 5 (Daleel)",
                      "Block 5 (Jannah)", "Block S2 (Uqlah)", "Block 9 (Malik)",
                      "Ramadan", "Idd El Shargi North Dome (ISND)",
                      "Idd El Shargi South Dome (ISSD)", "Zeloi", "Siah Makan"}

# A reference's `members` may mean recipients of a reference, NOT its complete
# production footprint. Never infer completeness from the length of that list.
REFERENCE_MEMBERS = {
    "kirkuk-two-domes-2021": ["Baba Dome", "Avana Dome"],
    "hawler-forza-2022": ["Banan", "Demir Dagh", "Zey Gawra"],
    "egypt-taurus-libra-2017": ["Taurus", "Libra"],
    "syria-ward-ahmer-akash-ratka-2015": ["Al-Ward", "Ahmer", "Akash", "Ratka"],
    "syria-tayyani-maleh-sijan-azraq-2015": ["Tayyani", "Maleh", "Sijan", "Azraq"],
    "syria-wahab-habbari-deilla-fadeh-2015": ["Wahab", "Habbari", "Deilla", "Fadeh"],
    "syria-jazal-heil-2015": ["Jazal-Heil"],
}
COMPLETE_PARENTS = {"Sarsang", "Missan Fields", "Idd El-Sharqi", "Belayim"}
INCOMPLETE_REFERENCES = {"basra-national-2023", "noc-licensed-2023", "noc-national-2023",
                         "midland-licensed-2023", "missan-national-2023", "egypt-karma-fields-2017"}


def observation_period(text):
    """Only explicitly stated calendar averages can enter a period total."""
    text = str(text or "")
    m = re.match(r"^(\d{4})年?(?:第)?([一二三四1-4])季度平均", text)
    if m:
        year = int(m[1]); q = "一二三四".find(m[2]) + 1 if m[2] in "一二三四" else int(m[2])
        return f"{year}-Q{q}", date(year, q * 3, monthrange(year, q * 3)[1])
    m = re.match(r"^(\d{4})年?(上半年|下半年)", text)
    if m and ("平均" in text or "日均" in text):
        year = int(m[1]); first = m[2] == "上半年"
        return f"{year}-H{1 if first else 2}", date(year, 6, 30) if first else date(year, 12, 31)
    m = re.match(r"^(\d{4})年(\d{1,2})月平均", text)
    if m:
        year, month = int(m[1]), int(m[2])
        return f"{year}-{month:02}", date(year, month, monthrange(year, month)[1])
    m = re.match(r"^(\d{4})(?:年历史日均|年平均|全年平均|全年.*日均)", text)
    if m:
        return m[1], date(int(m[1]), 12, 31)
    # A reported instant can order observations, but is not an annual average.
    m = re.match(r"^(\d{4})-(\d\d)-(\d\d)", text)
    if m:
        return None, date(*map(int, m.groups()))
    return None, None


def _amount(m):
    """Return only unqualified numbers; ranges and bounds remain display-only."""
    if m.get("value_qualifier"):
        return None
    raw = str(m.get("value") if m.get("value") is not None else "").replace(",", "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    unit = m.get("unit")
    if unit in {"千桶/日", "千桶油当量/日"}:
        return value / 10
    if unit == "桶/日":
        return value / 10000
    if unit in {"百万标准立方英尺/日", "百万立方米/日"}:
        return value
    return None


def _product(m, name):
    unit = str(m.get("unit") or "")
    if "油当量" in unit:
        return "boe"
    if "立方" in unit:
        return "natural_gas"
    if m.get("metric_type") == "historical_condensate_output":
        return "condensate"
    product = m.get("commodity")
    if product in {"crude_oil", "natural_gas", "condensate"}:
        return product
    if name in CRUDE_MEASUREMENTS:
        return "crude_oil"
    return "liquids" if "桶/日" in unit else "unknown"


def _basis(m):
    text = str(m.get("ownership_basis") or m.get("basis") or "")
    if "获分配" in text or "分配份额" in text or "巴林份额" in text:
        return "分配份额"
    if any(word in text for word in ("65%工作权益", "Tethys权益", "30%工作权益")):
        return "企业权益"
    if any(word in text for word in ("许可证南区", "伊朗侧", "主平台", "年度田级报送")):
        return "具名部分范围"
    if "毛口径" in text or "毛产量" in text or "全口径" in text or "全资产口径" in text or "非公司权益缩减" in text:
        return "全资产"
    return "口径待核"


def operating_state(asset):
    """Latest sourced operating state, independent of production measurement."""
    state = asset.get("operating_status", "unknown")
    date = asset.get("operating_status_as_of")
    if (not date or not asset.get("operating_status_evidence_url")
            or asset.get("operating_status_confidence") not in {"高", "中"}):
        return {"state": "unknown", "label": "待确认"}
    label = asset.get("operating_status_label") or "待确认"
    return {"state": state, "label": f"{label}（截至：{date}）",
            "evidence_url": asset.get("operating_status_evidence_url"),
            "as_of": date, "basis": asset.get("operating_status_basis"),
            "confidence": asset.get("operating_status_confidence")}


def producing_count(observations):
    return len({o["scope_id"] for o in observations
                if o.get("operating_state", {}).get("state") == "producing"})


def build_observations(assets):
    index = {(a["country"], a["name"]): a for a in assets}
    children = {}
    for a in assets:
        if a.get("parent_asset"):
            children.setdefault((a["country"], a["parent_asset"]), set()).add((a["country"], a["name"]))

    def footprint(key, seen=frozenset()):
        if key in seen:
            raise ValueError(f"资产归属循环：{key}")
        result = {key}
        declared = {(key[0], name) for name in index.get(key, {}).get('constituent_assets', [])}
        for child in children.get(key, set()) | declared:
            result |= footprint(child, seen | {key})
        return result

    observations = []

    def add(asset, measurement, scope_id, members=None, complete=False, virtual=False, forced_reason=""):
        m = dict(measurement)
        if m.get("source_url") in SOURCE_RECHECK_UPDATES:
            m["original_source_url"] = m["source_url"]
            m["source_url"] = SOURCE_RECHECK_UPDATES[m["source_url"]]
        if m.get("value_numeric") is not None:
            try:
                m["value_numeric"] = Decimal(str(m["value_numeric"]))
                if not m["value_numeric"].is_finite():
                    m["value_numeric"] = None
            except InvalidOperation:
                m["value_numeric"] = None
        country, name = asset["country"], asset["name"]
        # Additional measurements inherit ownership only when they do not
        # supply their own basis. Keep explicit contrary evidence intact.
        if not m.get("ownership_basis") and not m.get("basis"):
            m["ownership_basis"] = asset.get("ownership_basis")
        product = _product(m, name)
        period, end = observation_period(m.get("data_date"))
        keys = {(country, member) for member in members} if members is not None else footprint((country, name))
        if complete and members:
            keys = set().union(*(footprint((country, member)) for member in members))
        if not keys:
            keys = {(country, name)}
        metric = m.get("metric_type")
        reason = forced_reason
        if metric not in PRODUCTION:
            reason = "非产量指标" if m.get("value") is not None else "缺产量"
        elif m.get("value") is None:
            reason = "缺产量"
        if not m.get("source_url") and metric in PRODUCTION:
            reason = "缺来源链接"
        if name == "Qayyarah" and not virtual and metric in PRODUCTION:
            reason = "同年NOC与PCLD来源冲突待核"
        def member_label(member):
            return display_name(index.get((country, member),
                {"name": member, "name_cn": asset.get('constituent_asset_labels', {}).get(member,
                    "泽伊高拉" if member == "Zey Gawra" else "待核名称")}))

        observations.append({
            "scope_id": scope_id, "country": country, "name": m.get("scope") if virtual else name,
            "countries": list(asset.get("countries") or [country]),
            "label": ("、".join(member_label(member) for member in (members or []))
                       + "合计（" + str(m.get("scope")) + "）") if virtual else display_name(asset),
            "type": "具名合计" if virtual else asset.get("asset_level_label", "未分类"),
            "members": members if members is not None else list(asset.get("constituent_assets", [])),
            "member_labels": [member_label(member)
                              for member in (members if members is not None else asset.get("constituent_assets", []))],
            "coverage": frozenset(keys), "complete": complete, "virtual": virtual,
            "measurement": m, "product": product, "period": period,
            "end": end, "basis": _basis(m), "amount": _amount(m),
            "estimated": metric in ESTIMATES, "reason": reason, "status": "待选择",
        })
        observation = observations[-1]
        if virtual:
            states = [operating_state(index.get((country, member), {})) for member in (members or [])]
            if complete and states and len({s["state"] for s in states}) == 1 and states[0]["state"] != "unknown":
                observation["operating_state"] = {
                    "state": states[0]["state"],
                    "label": "；".join(dict.fromkeys(s["label"] for s in states)),
                }
            else:
                observation["operating_state"] = {"state": "unknown", "label": "待确认（合计成员状态未一致核实）"}
        else:
            observation["operating_state"] = operating_state(asset)
        basis_text = str(m.get("ownership_basis") or "")
        if not virtual and "许可证南区" in basis_text:
            observation["label"] += "南区"
            observation["type"] = "开发区"
        elif not virtual and "伊朗侧" in basis_text:
            observation["label"] += "（伊朗侧）"
            observation["countries"] = [country]
        if name == "North Arabia" and product == "natural_gas":
            observation["label"] = "北阿拉伯非常规气项目（North Arabia unconventional gas project）"
            observation["type"] = "开发项目"
            if asset.get('operating_status_scope') != 'development_project':
                observation["operating_state"] = {"state": "unknown", "label": "待确认（项目与资产状态范围不同）"}
        if name == "South Ghawar" and product == "natural_gas":
            observation["label"] = "南加瓦尔非常规气项目（South Ghawar）"

    for a in assets:
        scope_id = f'{a["country"]}/{a["name"]}'
        members = a.get("constituent_assets") if a["name"] in COMPLETE_PARENTS else None
        add(a, a, scope_id, members=members, complete=bool(members))
        for m in a.get("additional_measurements", []):
            if m.get("metric_type") in PRODUCTION:
                add(a, m, scope_id, members=members, complete=bool(members))

    refs = {}
    for a in assets:
        for m in a.get("aggregate_references", []):
            rid = m.get("id")
            if not rid:
                continue
            # Parent references are copies of the parent's production record.
            if rid in {f'{country}/{name}' for country, name in index}:
                continue
            refs.setdefault((a["country"], rid), (a, m))
    for (country, rid), (a, m) in sorted(refs.items()):
        members = REFERENCE_MEMBERS.get(rid, m.get("members", []))
        measurement = dict(m)
        # Reviewed source tables identify the following reference products.
        measurement["commodity"] = "natural_gas" if rid == "egypt-taurus-libra-2017" else "crude_oil"
        if rid == "kirkuk-two-domes-2021":
            measurement["ownership_basis"] = "Baba、Avana两圆顶全范围毛口径；不含Khurmala"
        reason = "合计成员范围未完整核实" if rid in INCOMPLETE_REFERENCES or rid not in REFERENCE_MEMBERS else ""
        add(a, measurement, f"reference:{country}/{rid}", members=members,
            complete=not reason, virtual=True, forced_reason=reason)
    return observations


def select_units(observations, *, period=None, product="crude_oil", estimates=True, prefer_actual=False,
                 require_reliable=False):
    """Select a non-overlapping scope cover, separately by product and basis.

    A parent can split only into a complete, same-period, same-basis cover.
    Partial intersections exclude both scopes rather than inventing a residual.
    """
    rows = [dict(o) for o in observations]
    candidates = []
    for o in rows:
        reason = o["reason"] or (quality_issue(o) if require_reliable else "")
        if reason:
            o["status"] = reason
        elif o["product"] != product:
            o["status"] = "其他商品"
        elif period and o["period"] != period:
            o["status"] = "非所选平均期间"
        elif not estimates and o["estimated"]:
            o["status"] = "估算未纳入"
        elif o["basis"] in {"企业权益", "分配份额"}:
            o["status"] = "权益／分配量，仅作明细"
        else:
            candidates.append(o)

    # Same-scope alternate disclosures must not turn into competing map areas.
    # Prefer an explicitly whole-asset scope to an unqualified older reference.
    groups = {}
    for o in candidates:
        groups.setdefault(o["scope_id"], []).append(o)
    candidates = []
    for group in groups.values():
        def rank(o):
            year = measurement_year(o["measurement"])
            when = o["end"] or (date(int(year), 12, 31) if year else date.min)
            actual = not daily_is_estimated(o)
            basis = {"全资产": 2, "具名部分范围": 1}.get(o["basis"], 0)
            return (basis, actual, when) if prefer_actual else (basis, when, not o["estimated"])
        ordered = sorted(group, key=rank, reverse=True)
        winner = ordered[0]
        # Distinct values for the same scope/period are unresolved, not summed.
        conflicts = [o for o in ordered[1:] if o["period"] and o["period"] == winner["period"]
                     and o["basis"] == winner["basis"]
                     and (not prefer_actual or daily_is_estimated(o) == daily_is_estimated(winner))
                     and o["measurement"].get("value") != winner["measurement"].get("value")]
        if conflicts:
            for o in ordered:
                o["status"] = "同范围同期间来源冲突待核"
        else:
            candidates.append(winner)
            for o in ordered[1:]:
                o["status"] = "同单元其他披露"

    bad = set()
    for i, a in enumerate(candidates):
        for j, b in enumerate(candidates[i + 1:], i + 1):
            overlap = a["coverage"] & b["coverage"]
            if overlap and (a["coverage"] == b["coverage"] or
                            not (a["coverage"] < b["coverage"] or b["coverage"] < a["coverage"])):
                bad.update((i, j))
    for i in bad:
        candidates[i]["status"] = "范围交叉或重复待核"
    available = [o for i, o in enumerate(candidates) if i not in bad]
    chosen = []
    for o in sorted(available, key=lambda o: (-len(o["coverage"]), o["scope_id"])):
        parent = next((p for p in chosen if o["coverage"] <= p["coverage"]), None)
        if parent:
            o["status"] = f'已包含在：{parent["label"]}'
            continue
        smaller = [s for s in available if s["basis"] == o["basis"] and s["coverage"] < o["coverage"]
                   and s["period"] is not None and s["period"] == o["period"]
                   and (not prefer_actual or daily_is_estimated(o) or not daily_is_estimated(s))]
        covered = set().union(*(s["coverage"] for s in smaller)) if smaller else set()
        if o["complete"] and covered == set(o["coverage"]):
            o["status"] = "已拆为同期间完整组成单元"
        else:
            o["status"] = "选用"
            chosen.append(o)
    for o in rows:
        if o["status"] == "缺产量" and o["product"] == product:
            parent = next((p for p in chosen if o["country"] == p["country"]
                           and o["coverage"] <= p["coverage"]), None)
            if parent:
                o["status"] = f'已包含在：{parent["label"]}'
    return chosen, rows


def total_units(chosen, period):
    """Conservative total: full-asset, calendar mean, unqualified numeric data."""
    eligible = [o for o in chosen if period and o["period"] == period and o["basis"] == "全资产"
                and o["amount"] is not None and o["product"] != "unknown"]
    units = {o["measurement"].get("unit") for o in eligible}
    # Never combine gas volumes in different units or standard conditions.
    if any("立方" in str(u) for u in units) and len(units) > 1:
        return None, []
    if not eligible:
        return None, []
    for i, a in enumerate(eligible):
        for b in eligible[i + 1:]:
            if a["coverage"] & b["coverage"]:
                raise ValueError("统计单元范围重叠，禁止汇总")
    return sum((o["amount"] for o in eligible), Decimal(0)), eligible


def unit_rows(observations):
    return [{"统计单元": o["label"], "国家": o["country"], "共享国家": "、".join(o["countries"]), "单元类型": o["type"],
             "包含资产": "、".join(o["member_labels"]) or o["label"],
             "产量": display_value(o["measurement"]) if o["measurement"].get("metric_type") in PRODUCTION else "未披露",
             "统计期间": o["measurement"].get("data_date") or "未披露",
             "平均期间": o["period"] or "时点／期间未明确",
             "商品": PRODUCTS[o["product"]], "口径": o["basis"],
             "权益及范围说明": o["measurement"].get("ownership_basis") or o["measurement"].get("basis") or "未披露",
             "产量性质": "非产量／缺产量" if o["measurement"].get("metric_type") not in PRODUCTION else "估算" if o["estimated"] else "历史日均换算" if o["measurement"].get("metric_type") == "derived_daily_average" else "来源直报",
             "统计状态": o["status"], "来源": o["measurement"].get("source_url"),
             "汇总状态": o.get("sum_status", "未计入合计"),
             "说明": o["measurement"].get("note") or o["measurement"].get("basis") or "",
             "单元ID": o["scope_id"]} for o in observations]


def daily_is_estimated(observation):
    return observation["estimated"] or observation["measurement"].get("metric_type") == "derived_daily_average"


def quality_issue(observation):
    """Evidence-backed exclusions from the 2026-10-25 source recheck.

    Preserve excluded evidence in the catalog; absence from statistics is not
    a claim of zero output. Source access failure alone is not a rejection.
    """
    m = observation["measurement"]
    url = str(m.get("source_url") or "")
    if m.get("metric_type") == "estimated_output":
        if "303325221_Oil_in_Syria" in url or "2076-0760/5/2/20" in url:
            return "战时访谈历史估计，缺可复算逐田量测；仅归档"
        if measurement_year(m) is None:
            return "估算依据时间未明确；仅归档"
        if "alanba.com.kw/1177600" in url:
            return "匿名消息估计，缺独立产量证据；仅归档"
    if m.get("metric_type") == "derived_daily_average" and m.get("annual_barrels") is not None:
        try:
            barrels, days = Decimal(str(m["annual_barrels"])), Decimal(str(m.get("calendar_days")))
            value = Decimal(str(m.get("value")))
            if days not in {Decimal(365), Decimal(366)} or barrels < 0:
                return "年度量换算参数异常；待核"
            precision = Decimal(1).scaleb(value.as_tuple().exponent)
            if abs(barrels / days / 1000 - value) > precision / 2:
                return "年度量与日均值换算不一致；待核"
        except (InvalidOperation, TypeError, ZeroDivisionError):
            return "年度量换算参数缺失；待核"
    return ""


def measurement_year(measurement):
    """Observation basis only: never turn a publication/review year into data."""
    text = str(measurement.get("data_date") or "")
    if any(word in text for word in ("观测期未注明", "未注明观察期", "未注明供气数值基准日",
                                     "底层观察期未明", "底层观察日未注明", "具体统计期未注明")):
        return None
    match = re.match(r"^(?:截至)?((?:19|20)\d{2})", text)
    if match:
        return match[1]
    if text.startswith("伊朗历"):
        match = re.search(r"（((?:19|20)\d{2})-\d{2}-\d{2}）", text)
        return match[1] if match else None
    return None


def daily_display(measurement):
    unit = str(measurement.get("unit") or "")
    raw = str(measurement.get("value") if measurement.get("value") is not None else "未披露")
    if unit in {"千桶/日", "桶/日", "千桶油当量/日"}:
        divisor = Decimal(10000 if unit == "桶/日" else 10)
        def convert(match):
            value = Decimal(match[0].replace(",", "")) / divisor
            return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
        value = re.sub(r"\d[\d,]*(?:\.\d+)?", convert, raw)
        qualifier = str(measurement.get("value_qualifier") or "")
        if qualifier and not value.startswith(qualifier):
            value = qualifier + value
        return value + ("万桶油当量/天" if "油当量" in unit else "万桶/天")
    return display_value(measurement).replace("/日", "/天")


def compact_rows(observations):
    return [{"名称": o["label"], "国家": "、".join(o["countries"]), "类型": o["type"],
             "包含资产": "、".join(o["member_labels"]) or o["label"],
             "日产量": daily_display(o["measurement"]), "商品": PRODUCTS[o["product"]],
             "备注": "估算产量" if daily_is_estimated(o) else "真实产量",
             "数据时间": measurement_year(o["measurement"]) or "未明确",
             "数据来源": o["measurement"].get("source_url")} for o in observations]


def numeric_daily(measurement):
    """Numeric daily rate; closed ranges use midpoint, open bounds stay null."""
    raw = str(measurement.get("value") if measurement.get("value") is not None else "").replace(",", "").strip()
    qualifier = str(measurement.get("value_qualifier") or "")
    if any(mark in raw + qualifier for mark in (">", "<", "以上", "以下", "超过", "至少", "不低于", "不超过")):
        return None, False
    raw = re.sub(r"^(?:约|大约|近|≈|~)\s*", "", raw)
    raw = re.sub(r"(?<![\d.])\.(?=\d)", "0.", raw)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:[–—−~至-]\s*(\d+(?:\.\d+)?))?", raw)
    if not match:
        return None, False
    amount = Decimal(match[1])
    midpoint = match[2] is not None
    if midpoint:
        high = Decimal(match[2])
        if high < amount:
            return None, False
        amount = (amount + high) / 2
    unit = measurement.get("unit")
    if unit in {"千桶/日", "千桶油当量/日"}:
        amount /= 10
    elif unit == "桶/日":
        amount /= 10000
    elif unit not in {"百万立方米/日", "百万标准立方英尺/日"}:
        return None, midpoint
    return float(amount), midpoint


def approximated_point(measurement, midpoint):
    raw = str(measurement.get("value") or "")
    qualifier = str(measurement.get("value_qualifier") or "")
    return midpoint or qualifier in {"约", "≈", "~", "近", "about", "approx"} or bool(re.match(r"^(?:约|大约|近|≈|~)", raw))


def numeric_rows(observations, product=None):
    rows = compact_rows(observations)
    # Keep gas in its reported unit; incompatible volume bases remain null in
    # the shared numeric column instead of becoming fictitious oil barrels.
    units = {o["measurement"].get("unit") for o in observations}
    product = product or (observations[0]["product"] if observations else "crude_oil")
    if product == "natural_gas":
        unit = next(iter(units)) if len(units) == 1 else "百万标准立方英尺/日"
        column = f"日产量（{unit}）"
    elif product == "boe":
        unit = "万桶油当量/日"
        column = f"日产量（{unit}）"
    else:
        unit = "万桶/日"
        column = "日产量（万桶/日）"
    for row, observation in zip(rows, observations):
        number, midpoint = numeric_daily(observation["measurement"])
        if product == "natural_gas" and observation["measurement"].get("unit") != unit:
            number = None
        row.pop("日产量")
        row[column] = number
        if approximated_point(observation["measurement"], midpoint):
            row["备注"] = "估算产量"
    columns = ["名称", "国家", "类型", "包含资产", column, "商品", "备注", "数据时间", "数据来源"]
    return [{k: row[k] for k in columns} for row in rows], column, unit


def numeric_metrics(observations, rows, column):
    values = [r[column] for r in rows if r[column] is not None]
    return (len(rows), len({c for o in observations for c in o["countries"]}),
            len({r["类型"] for r in rows}), sum(values) / len(values) if values else None,
            len({r["商品"] for r in rows}))


def combined_rows(observations, products):
    """Two product dimensions, never an oil/gas-equivalent conversion."""
    products = set(products) & set(STATISTICAL_PRODUCTS)
    if products == {"crude_oil"}:
        column = "日产量（万桶/日）"
    elif products == {"natural_gas"}:
        column = "日产量（百万立方米/日）"
    else:
        column = "日产量（原油：万桶/日；天然气：百万立方米/日）"
    filtered = [o for o in observations if o["product"] in products]
    rows = compact_rows(filtered)
    for row, observation in zip(rows, filtered):
        value, midpoint = numeric_daily(observation["measurement"])
        if value is not None and observation["product"] == "natural_gas":
            if observation["measurement"].get("unit") == "百万标准立方英尺/日":
                value = float(Decimal(str(value)) * MILLION_FT3_TO_MILLION_M3)
            elif observation["measurement"].get("unit") != "百万立方米/日":
                value = None
        row.pop("日产量")
        row["状态"] = observation.get("operating_state", {}).get("label", "待确认")
        row[column] = value
        if approximated_point(observation["measurement"], midpoint):
            row["备注"] = "估算产量"
    columns = ["名称", "国家", "类型", "包含资产", column, "商品", "状态", "备注", "数据时间", "数据来源"]
    means = {}
    for product in products:
        values = [row[column] for row, observation in zip(rows, filtered)
                  if observation["product"] == product and row[column] is not None]
        means[product] = sum(values) / len(values) if values else None
    return [{key: row[key] for key in columns} for row in rows], column, means


def statistical_view(assets, countries=(), products=None):
    """Single population and row binding for the table, map and download."""
    products = list(STATISTICAL_PRODUCTS) if products is None else products
    observations = build_observations([a for a in assets if a['country'] != '土耳其'])
    observations = [o for o in observations if not countries or set(countries) & set(o['countries'])]
    chosen = []
    for product in products:
        if product in STATISTICAL_PRODUCTS:
            chosen.extend(select_units(observations, product=product, prefer_actual=True,
                                       require_reliable=True)[0])
    rows, column, means = combined_rows(chosen, products)
    return chosen, rows, column, means


def map_units(assets, chosen, rows):
    """One map identity per selected scope, with product rows in its popup.

    Unknown/aggregate locations remain unmapped; never inherit the attaching
    member's location or invent a centroid for a reference aggregate.
    """
    index = {(a['country'], a['name']): a for a in assets}
    result = {}
    for observation, row in zip(chosen, rows):
        key = observation['scope_id']
        if key not in result:
            source = {} if observation['virtual'] else index.get((observation['country'], observation['name']), {})
            drawable = bool(source.get('map_drawable') and not source.get('map_is_proxy')
                            and source.get('map_lat') is not None and source.get('map_lon') is not None)
            result[key] = {'name': observation['name'], 'country': observation['country'],
                           'display_name': observation['label'], 'scope_id': key,
                           'map_drawable': drawable, 'map_is_proxy': False,
                           'map_lat': source.get('map_lat') if drawable else None,
                           'map_lon': source.get('map_lon') if drawable else None,
                           'production_rows': [], 'operating_states': []}
        result[key]['production_rows'].append(row)
        result[key]['operating_states'].append(observation.get('operating_state', {}).get('state', 'unknown'))
    return list(result.values())
