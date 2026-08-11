# HTFA Python and Ts runtime

HTFA has separate development and Windows distribution environments. Neither one is portable as a conventional virtual environment.

## Development environment

The repository `.venv/` is machine-local. Do not copy or synchronize it to another computer. Recreate it with Python 3.13.4 whenever the checkout moves:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\install_ts.py
```

The pinned bootstrap repository, branch and commit are stored in `scripts/ts_runtime.json`. The development environment and its installed Ts package remain ignored by Git.

The current bootstrap commit is `bec57a2610b38be3a8f78071d7e03850b53ca25e`.

## Build the Windows x64 portable release

Run from a working development environment:

```powershell
.venv\Scripts\python.exe scripts\build_portable.py
```

The builder downloads the official CPython 3.13.4 Windows embeddable archive, verifies its pinned SHA-256, installs the exact binary dependencies from `requirements-win-py313.lock`, installs the pinned bootstrap Ts, and writes:

```text
dist/HTFA-win-x64/
|-- runtime/                 Python 3.13.4, dependencies, and current Ts
|-- dashboard/
|-- scripts/
|-- data/
|-- .streamlit/
|-- app.py
|-- start.bat
|-- requirements-win-py313.lock
`-- runtime-manifest.json
```

Copy the whole `HTFA-win-x64` directory. The target Windows x64 computer needs no installed Python, pip, Git or compiler. It starts HTFA through `start.bat`; never copy the development `.venv/` as part of a release.

`requirements.txt` expresses supported dependency ranges for development. `requirements-win-py313.lock` records the exact versions used by the portable release. `runtime-manifest.json` records the Python archive, dependency-lock hash, bootstrap Ts commit and build timestamp.

## Ts update behavior

Every `start.bat` run performs one short HTTPS request to the public `BichengNiu/Ts` repository:

1. Read the `main` HEAD commit through the GitHub API.
2. If it matches the installed metadata, launch with the current Ts.
3. If it differs, download the immutable commit ZIP, safely extract the allowlisted Ts files, atomically replace the current package, and launch with it.
4. If the network check, download, extraction or replacement fails, leave the current Ts untouched and launch with it.

The updater does not use system Git, credentials, pip, background tasks or version caches. It retains HTTPS, fixed-repository and fixed-commit URLs, archive size limits, ZIP path traversal protection and atomic replacement.

By explicit project decision, a successfully downloaded `main` commit receives no interface validation, import validation or isolated smoke test before installation. A broken `main` commit can therefore break HTFA after download. Recovery is to fix `main` and start again, or replace the directory with a clean portable release.

## Docker

Docker remains an independent deployment target and currently uses the Python version declared in `Dockerfile`. The Windows portable build does not change the container runtime.
