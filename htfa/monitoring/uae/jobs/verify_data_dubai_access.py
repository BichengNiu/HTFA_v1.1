"""Verify official Data Dubai dataset grants without logging tokens or records."""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests


TOKEN_URL = "https://apis.data.dubai/oauth/client_credential/accesstoken"
DATASET_URLS = {
    "ded": "https://apis.data.dubai/open/ded/ded_commerce_registry-open-api",
    "dld": "https://apis.data.dubai/open/dld/dld_transactions-open-api",
    "dubai_customs_air": "https://apis.data.dubai/open/customs/customs_airway_bill_detail-open-api",
}


def verify_access(session, api_key: str, api_secret: str) -> dict:
    """Check OAuth and each dataset grant; return status and schema names only."""
    if not api_key.strip() or not api_secret.strip():
        raise ValueError("Missing DATA_DUBAI_API_KEY / DATA_DUBAI_API_SECRET")
    try:
        response = session.post(
            TOKEN_URL, params={"grant_type": "client_credentials"},
            data={"client_id": api_key, "client_secret": api_secret}, timeout=60,
        )
    except requests.RequestException:
        raise RuntimeError("Data Dubai OAuth connection failed; credentials were not logged") from None
    if response.status_code != 200:
        raise RuntimeError(f"Data Dubai OAuth HTTP {response.status_code}; credentials were not logged")
    payload = response.json()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Data Dubai OAuth returned no access_token")
    results = {}
    for name, url in DATASET_URLS.items():
        try:
            response = session.get(
                url, params={"limit": 1}, headers={"Authorization": f"Bearer {token}",
                                               "Accept": "application/json"}, timeout=60,
            )
            result = {"http_status": response.status_code, "status": "error"}
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and any(
                    key in data for key in ("records", "result", "response", "data")
                ) and not any(
                    data.get(key) for key in ("Exception", "exception", "fault", "error")
                ) and data.get("success") is not False:
                    result.update(status="ok", response_keys=sorted(data))
            results[name] = result
        except (requests.RequestException, ValueError):
            # Never serialize upstream bodies or exceptions: either may contain
            # authorization headers, request parameters or personal records.
            results[name] = {"status": "error", "error": "Request or JSON validation failed"}
    return {"status": "ok" if all(r["status"] == "ok" for r in results.values()) else "error",
            "sources": results}


def main() -> None:
    with requests.Session() as session:
        result = verify_access(session, os.environ.get("DATA_DUBAI_API_KEY", ""),
                               os.environ.get("DATA_DUBAI_API_SECRET", ""))
    output = Path(os.environ["RUNNER_TEMP"]) / "data-dubai-api-access.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
