"""Small, conservative helpers for downloading official source files.

The UAE jobs deliberately keep downloaded files under ``data/UAE/raw``.  This
module supplies explicit HTTP transports, atomic writes, and a minimum-size
check; source-specific discovery and parsing stay in their own modules.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 HTFA/1.1"
)


def fetch_bytes(
    url: str,
    *,
    referer: str | None = None,
    user_agent: str = USER_AGENT,
    headers: Mapping[str, str] | None = None,
    timeout: int = 90,
    browser_transport: bool = False,
) -> bytes:
    """Fetch ``url`` using the explicitly selected HTTP transport.

    ``referer``, ``headers`` and ``timeout`` configure either transport.
    ``user_agent`` is used by urllib; ``browser_transport=True`` selects
    curl_cffi's Chrome headers and TLS directly. Failed requests propagate
    without switching transports or substituting old payloads.
    """

    if browser_transport:
        from curl_cffi import requests

        request_headers = dict(headers or {})
        if referer:
            request_headers.setdefault("Referer", referer)
        response = requests.get(
            url, impersonate="chrome", timeout=timeout, headers=request_headers
        )
        if response.status_code != 200:
            raise HTTPError(url, response.status_code, "Official download failed", None, None)
        return response.content

    request_headers = {"User-Agent": user_agent, "Accept": "*/*"}
    request_headers.update(headers or {})
    if referer:
        request_headers.setdefault("Referer", referer)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def download_file(
    url: str,
    destination: Path,
    *,
    force: bool = False,
    min_bytes: int = 128,
    referer: str | None = None,
    user_agent: str = USER_AGENT,
    headers: Mapping[str, str] | None = None,
    browser_transport: bool = False,
) -> str:
    """Download ``url`` to ``destination`` atomically.

    Returns ``existing`` when a valid local file is reused and ``downloaded``
    when a new response is written. ``headers`` are passed to the selected
    transport. A failed/empty response never replaces a good cache.
    """

    if not force and destination.is_file() and destination.stat().st_size >= min_bytes:
        return "existing"
    fetch_options = {"browser_transport": True} if browser_transport else {}
    payload = fetch_bytes(
        url,
        referer=referer,
        user_agent=user_agent,
        headers=headers,
        **fetch_options,
    )
    if len(payload) < min_bytes:
        raise RuntimeError(
            f"官方地址返回内容过小，疑似错误页: {url} ({len(payload)} bytes)"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return "downloaded"


def write_json_atomic(path: Path, payload: object, *, indent: int | None = 2) -> None:
    """Write UTF-8 JSON via a unique sibling file, preserving old data on failure.

    ``path`` is the destination, ``payload`` must be JSON serializable, and
    ``indent=None`` keeps large raw API responses compact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=f".{path.name}.", suffix=".tmp",
            dir=path.parent, encoding="utf-8", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=indent)
            temporary.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = ["USER_AGENT", "download_file", "fetch_bytes", "write_json_atomic"]
