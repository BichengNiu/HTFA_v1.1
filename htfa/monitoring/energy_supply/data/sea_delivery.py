"""Bounded, authenticated historical delivery downloads."""

from pathlib import Path
from urllib.parse import urlparse


def download_bundle(config, max_bytes):
    """Read an authorized delivery bundle, not an invented vendor API endpoint."""
    local = config.get("SEA_HISTORY_BUNDLE_PATH")
    url = config.get("SEA_HISTORY_BUNDLE_URL")
    if local and url:
        raise ValueError("只配置一种历史交付来源：本地ZIP或HTTPS ZIP")
    if not local and not url:
        return None
    if local:
        with Path(local).expanduser().open("rb") as handle:
            data = handle.read(max_bytes + 1)
    else:
        import requests

        if urlparse(url).scheme != "https":
            raise ValueError("历史交付地址必须使用HTTPS")
        token = config.get("SEA_HISTORY_BEARER_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            # Do not forward secret tokens via redirects or print signed URLs.
            with requests.get(
                url,
                headers=headers,
                timeout=(10, 60),
                stream=True,
                allow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise ValueError(f"历史交付源返回HTTP {response.status_code}")
                parts, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("历史ZIP超过50MB")
                    parts.append(chunk)
                data = b"".join(parts)
        except requests.RequestException:
            raise ValueError("历史交付源连接失败，请检查地址、授权与网络") from None
    return data
