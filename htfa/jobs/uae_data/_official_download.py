"""Small, conservative helpers for downloading official source files.

The UAE jobs deliberately keep downloaded files under ``data/UAE/raw``.  This
module only supplies a common user-agent, atomic writes, and a minimum-size
check; source-specific discovery and parsing stay in their own modules.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
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
    timeout: int = 90,
) -> bytes:
    """Fetch an official URL with a browser-like request header."""

    headers = {"User-Agent": user_agent, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
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
) -> str:
    """Download ``url`` to ``destination`` atomically.

    Returns ``existing`` when a valid local file is reused and ``downloaded``
    when a new response is written.  A failed/empty response never replaces a
    good cache.
    """

    if not force and destination.is_file() and destination.stat().st_size >= min_bytes:
        return "existing"
    payload = fetch_bytes(url, referer=referer, user_agent=user_agent)
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


__all__ = ["USER_AGENT", "download_file", "fetch_bytes"]
