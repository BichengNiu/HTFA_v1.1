"""Open Waters raw GeoJSON transport; no vessel or UI rules."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import storage as data_store

OPENWATERS_API = "https://ais.openwaters.io/v1/vessels"


def fetch_group(
    boxes: tuple[tuple[float, float, float, float], ...],
    max_age_minutes: int,
    *,
    split_depth: int = 0,
) -> dict[str, Any]:
    if data_store.read_only():
        raise RuntimeError("只读展示端不允许采集船位")
    params = [
        ("bbox", f"{south},{west},{north},{east}") for south, north, west, east in boxes
    ]
    params.append(("max_age", f"{max_age_minutes}m"))
    request = Request(
        f"{OPENWATERS_API}?{urlencode(params)}",
        headers={
            "User-Agent": "oil-field-map-demo/1.0",
            "Accept": "application/geo+json, application/json",
        },
    )
    with urlopen(request, timeout=8) as response:
        result = json.load(response)
    data_store.save_query(OPENWATERS_API, {"query_parameters": params}, result)
    if not isinstance(result, dict) or result.get("type") != "FeatureCollection":
        raise ValueError("Open Waters返回了无法识别的船位快照")
    if result.get("error"):
        raise ValueError(f"Open Waters API：{result['error']}")
    if result.get("truncated") and split_depth < 3:
        # Dense areas may hit the provider's response cap even below its area
        # limit. Retry smaller areas; never relabel the partial parent as full.
        if len(boxes) > 1:
            parts = [(box,) for box in boxes]
        else:
            south, north, west, east = boxes[0]
            if east - west >= north - south:
                middle = (west + east) / 2
                parts = [
                    ((south, north, west, middle),),
                    ((south, north, middle, east),),
                ]
            else:
                middle = (south + north) / 2
                parts = [((south, middle, west, east),), ((middle, north, west, east),)]
        children = [
            fetch_group(part, max_age_minutes, split_depth=split_depth + 1)
            for part in parts
        ]
        result = {
            "type": "FeatureCollection",
            "features": [
                feature for child in children for feature in child.get("features", [])
            ],
            "attribution": {
                key: value
                for child in children
                for key, value in (child.get("attribution") or {}).items()
            },
            "truncated": any(bool(child.get("truncated")) for child in children),
        }
    return result


def fetch_track(mmsi, start, end):
    params = urlencode(
        {"from": start.isoformat(), "to": end.isoformat(), "limit": 1000}
    )
    request = Request(
        f"{OPENWATERS_API}/{mmsi}/track?{params}",
        headers={
            "Accept": "application/geo+json",
            "User-Agent": "oil-field-map-demo/1.0",
        },
    )
    with urlopen(request, timeout=8) as response:
        return json.load(response)
