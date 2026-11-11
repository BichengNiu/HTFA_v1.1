"""Read an exact public GitHub LFS object back and verify its committed bytes."""

import argparse
import hashlib
import json
import subprocess

import requests


def verify(commit, repository="BichengNiu/HTFA_v1.1"):
    pointer = subprocess.check_output(
        ["git", "show", f"{commit}:htfa/monitoring/uae/assets/uae.duckdb"], text=True,
    )
    fields = dict(line.split(" ", 1) for line in pointer.splitlines())
    expected = fields["oid"].removeprefix("sha256:")
    size = int(fields["size"])
    digest, received = hashlib.sha256(), 0
    url = f"https://media.githubusercontent.com/media/{repository}/{commit}/htfa/monitoring/uae/assets/uae.duckdb"
    with requests.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        for block in response.iter_content(1024 * 1024):
            digest.update(block)
            received += len(block)
    if received != size or digest.hexdigest() != expected:
        raise RuntimeError("Remote LFS size/SHA256 does not match committed pointer")
    return {"status": "verified", "commit": commit, "bytes": received, "sha256": expected}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    args = parser.parse_args()
    print(json.dumps(verify(args.commit)))
