"""Verify immutable GitHub LFS bytes with bounded retries and range resume."""

import argparse
import hashlib
import json
import re
import subprocess
import time

import requests

from htfa.monitoring.uae.contracts.paths import ASSETS_RELATIVE_PATH


def verify_object(url, expected_sha256, expected_size, *, attempts=4):
    """Hash the complete remote object; resume an interrupted response safely."""
    if attempts < 1 or expected_size < 1:
        raise ValueError("Positive size and attempt count required")
    received, digest = 0, hashlib.sha256()
    last_error = None
    for attempt in range(1, attempts + 1):
        headers = {"Range": f"bytes={received}-"} if received else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(30, 180)) as response:
                response.raise_for_status()
                if response.status_code == 206:
                    content_range = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if not content_range or tuple(map(int, (content_range[1], content_range[3]))) != (received, expected_size):
                        received, digest = 0, hashlib.sha256()
                        raise RuntimeError("Invalid Content-Range; refusing to append mismatched bytes")
                elif response.status_code == 200:
                    # A server may ignore Range. Hash its full response afresh.
                    received, digest = 0, hashlib.sha256()
                else:
                    raise RuntimeError(f"Unexpected LFS response status {response.status_code}")
                for block in response.iter_content(1024 * 1024):
                    digest.update(block)
                    received += len(block)
                    if received > expected_size:
                        received, digest = 0, hashlib.sha256()
                        raise RuntimeError("Remote LFS object exceeds committed size")
            if received != expected_size:
                raise RuntimeError(f"Incomplete LFS object: {received}/{expected_size} bytes")
            if digest.hexdigest() != expected_sha256:
                received, digest = 0, hashlib.sha256()
                raise RuntimeError("Remote LFS SHA256 differs from committed pointer")
            return {"status": "verified", "bytes": received,
                    "sha256": digest.hexdigest(), "attempts": attempt}
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(8, 2 ** (attempt - 1)))
    raise RuntimeError(f"LFS verification failed after {attempts} attempts: {last_error}") from last_error


def verify(commit, repository="BichengNiu/HTFA_v1.1", *, attempts=4):
    """Resolve the exact commit and verify the database named by its LFS pointer."""
    revision = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"], text=True,
    ).strip()
    path = (ASSETS_RELATIVE_PATH / "uae.duckdb").as_posix()
    pointer = subprocess.check_output(["git", "show", f"{revision}:{path}"], text=True)
    fields = dict(line.split(" ", 1) for line in pointer.splitlines())
    if fields.get("version") != "https://git-lfs.github.com/spec/v1":
        raise ValueError("Committed database is not a Git LFS pointer")
    expected = fields["oid"].removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Invalid LFS SHA256")
    result = verify_object(
        f"https://media.githubusercontent.com/media/{repository}/{revision}/{path}",
        expected, int(fields["size"]), attempts=attempts,
    )
    return {**result, "commit": revision}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    parser.add_argument("--attempts", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(verify(args.commit, attempts=args.attempts)))
