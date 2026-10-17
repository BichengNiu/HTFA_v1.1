"""Download Dubai Customs "Airway Bill Details" open dataset.

Source of truth: Data Dubai (Dubai Pulse) portal, dataset id 459114
  page:  https://data.dubai/en/l/459114  ("Airway Bill Details")
  api:   GET /o/dda/data-services/dataset-download?datasetId=459114&page=1&pageSize=30&sortDir=desc

The download API returns a manifest of gz shards on cdn.data.dubai (AWS S3
pre-signed URLs, valid ~10 minutes).  This script fetches the manifest, then
downloads the ``.csv.gz`` shards with resume support and re-fetches the
manifest whenever a signed URL expires (HTTP 403).

Usage::

    runtime\\python.exe -m htfa.jobs.uae_data.download_dubai_customs_air
        [--dataset 459114] [--limit 1] [--page-size 30] [--out DIR]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import certifi


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


DATASET_ID_DEFAULT = 459114
API_BASE = "https://data.dubai/o/dda/data-services/dataset-download"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_OUT = Path(__file__).resolve().parents[3] / "data" / "UAE" / "raw" / "dubai_customs_air" / "csv"


def fetch_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=120, context=_ssl_context()) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} while fetching {url}")
        return json.loads(resp.read().decode("utf-8"))


def fetch_manifest_pages(dataset_id: int, page_size: int = 30) -> list[dict]:
    """Fetch every metadata page and return the flattened file list (all shards).

    The API returns at most ``page_size`` folders per page; pages are walked
    until a page comes back shorter than ``page_size`` (or empty).
    """
    files: list[dict] = []
    page = 1
    while True:
        url = f"{API_BASE}?datasetId={dataset_id}&page={page}&pageSize={page_size}&sortDir=desc"
        payload = fetch_json(url)
        if not payload.get("success"):
            raise RuntimeError(f"manifest failed: {payload.get('message')}")
        folders = payload.get("data", {}).get("metadata", [])
        for folder in folders:
            files.extend(folder.get("files", []))
        if len(folders) < page_size:
            break
        page += 1
    return files


def csv_files_of(files: list[dict]) -> list[dict]:
    return [f for f in files if f.get("file_extension") == "csv"]


def _gzip_ok(path: Path) -> bool:
    """CRC check: fully stream the gzip; gzip module raises on bad CRC."""
    import gzip
    try:
        with gzip.open(path, "rb") as fh:
            while fh.read(1 << 20):
                pass
        return True
    except Exception:  # noqa: BLE001 - truncated/corrupt gzip
        return False


def download_file(
    url: str,
    target: Path,
    *,
    force: bool = False,
) -> str:
    """Resume one shard and atomically replace it after gzip CRC verification.

    NOTE: the manifest ``file_size`` reports the *decompressed* size while the
    CDN serves the compressed gzip (about 56 MB per shard in July-2026 data),
    so completeness is verified with the HTTP content-length followed by a
    gzip CRC pass instead of comparing compressed bytes to the manifest size.
    """
    if target.exists() and not force:
        if _gzip_ok(target):
            return "skipped"
    tmp = target.with_suffix(target.suffix + ".part")
    offset = tmp.stat().st_size if tmp.exists() and not force else 0
    headers = {"User-Agent": UA}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    req = Request(url, headers=headers)
    # CDN 签名 URL 只有约 10 分钟有效；短一些的 socket 超时可以让
    # 过期/无响应的链接尽快触发 manifest 刷新，而不是把整批任务挂住。
    try:
        response = urlopen(req, timeout=180, context=_ssl_context())
    except HTTPError as exc:
        if exc.code == 416 and offset and _gzip_ok(tmp):
            tmp.replace(target)
            return "ok"
        if exc.code == 416:
            tmp.unlink(missing_ok=True)
        raise
    with response as resp:
        append = resp.status == 206 and offset > 0
        if append and not resp.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise ValueError("CDN resumed at an unexpected byte offset")
        received = 0
        expected = int(resp.headers.get("Content-Length") or 0)
        with open(tmp, "ab" if append else "wb") as out:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                received += len(chunk)
        if expected and received != expected:
            raise OSError(f"Incomplete HTTP response: {received}/{expected} bytes")
    if not _gzip_ok(tmp):
        tmp.unlink()
        raise ValueError("Downloaded gzip failed its CRC integrity check")
    tmp.replace(target)
    return "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=int, default=DATASET_ID_DEFAULT)
    parser.add_argument("--limit", type=int, default=0,
                        help="Only download the first N csv shards (0 = all)")
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--workers", type=int, default=8,
                        help="Concurrent download threads (default 8)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true",
                        help="Redownload existing shards after refreshing the manifest")
    args = parser.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    # 1) manifest (all pages)
    all_files = fetch_manifest_pages(args.dataset, args.page_size)
    manifest_path = out / "manifest.json"
    manifest_path.write_text(
        json.dumps(all_files, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    files = csv_files_of(all_files)
    print(f"[manifest] dataset={args.dataset} files_in_manifest={len(all_files)} "
          f"csv_shards={len(files)} "
          f"total_bytes={sum(f['file_size'] for f in files)}", flush=True)
    if args.limit > 0:
        files = files[: args.limit]

    # 2) concurrent download with manifest re-fetch on expiry
    manifest_lock = threading.Lock()
    state = {"all_files": all_files, "fetched_at": time.monotonic()}
    done = {"ok": 0, "skipped": 0, "failed": 0}
    done_lock = threading.Lock()
    total = len(files)

    def refresh_manifest() -> None:
        with manifest_lock:
            latest = fetch_manifest_pages(args.dataset, args.page_size)
            state["all_files"] = latest
            state["fetched_at"] = time.monotonic()
            manifest_path.write_text(
                json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def ensure_fresh_manifest() -> None:
        # 预留约三分钟给正在传输的文件，避免四个线程同时拿到刚好过期的 URL。
        with manifest_lock:
            stale = time.monotonic() - state["fetched_at"] > 420
        if stale:
            refresh_manifest()

    def work(f: dict) -> tuple[str, str, int]:
        name = f["file_name"]
        target = out / name
        for attempt in range(4):
            ensure_fresh_manifest()
            with manifest_lock:
                fresh = next(
                    (x for x in csv_files_of(state["all_files"])
                     if x["file_name"] == name),
                    None,
                )
            if fresh is not None:
                f = fresh
            try:
                if fresh is None:
                    raise ValueError(f"Official snapshot no longer lists {name}")
                status = download_file(f["file_url"], target, force=args.force)
                size = target.stat().st_size if target.exists() else 0
                with done_lock:
                    bucket = status if status in ("ok", "skipped") else "failed"
                    done[bucket] += 1
                print(f"[{done['ok'] + done['skipped'] + done['failed']}/{total}] "
                      f"{name} -> {status} ({size / 1048576:.1f} MB)", flush=True)
                return name, status, size
            except Exception as exc:  # noqa: BLE001 - retry with fresh manifest
                if attempt == 3:
                    with done_lock:
                        done["failed"] += 1
                    print(f"[{total}] {name} ERROR {exc}", flush=True)
                    return name, f"error: {exc}", 0
                print(f"  {name} retry {attempt + 1} ({exc})", flush=True)
                time.sleep(2)
                refresh_manifest()
                fresh = next(
                    (x for x in csv_files_of(state["all_files"]) if x["file_name"] == name),
                    None,
                )
                if fresh is not None:
                    f = fresh

    summary = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, f) for f in files]
        for fut in concurrent.futures.as_completed(futures):
            summary.append(fut.result())
    summary.sort()
    report = {
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": args.dataset,
        "output_dir": str(out),
        "files": [
            {"file": name, "status": status, "size": size}
            for name, status, size in summary
        ],
    }
    (out / "download_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ok = sum(1 for _n, status, _s in summary if status in ("ok", "skipped"))
    print(f"[done] {ok}/{len(summary)} shards ok; report: {out / 'download_report.json'}")
    return 0 if ok == len(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
