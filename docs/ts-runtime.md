# HTFA portable project runtime

The project folder contains two Python environments with different purposes:

- `.venv/` is only for development and can remain machine-local.
- `runtime/` is the self-contained CPython 3.13.4 runtime used by `start.bat`.

## Make the project folder portable

Run once from the development computer:

```powershell
.venv\Scripts\python.exe scripts\build_portable.py
```

The builder downloads the official CPython 3.13.4 Windows embeddable archive, verifies its pinned SHA-256, installs the exact binary dependencies from `requirements-win-py313.lock`, installs the pinned bootstrap Ts, and writes directly into the current project:

```text
HTFA_v1.1/
|-- runtime/                 Python 3.13.4, dependencies, Ts, and manifest
|-- dashboard/
|-- scripts/
|-- data/
|-- .streamlit/
|-- app.py
`-- start.bat
```

Copy the whole `HTFA_v1.1` folder to any Windows x64 path and double-click its root `start.bat`. The target computer needs no installed Python, pip, Git or compiler. The copied `.venv/` and `.git/` directories are not used by startup and may be omitted to reduce copy size.

The builder safely replaces only the root `runtime/` directory. `requirements-win-py313.lock` records exact dependency versions; `runtime/runtime-manifest.json` records the Python archive, dependency-lock hash, bootstrap Ts commit and build timestamp.

The pinned bootstrap Ts commit is `bec57a2610b38be3a8f78071d7e03850b53ca25e`.

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
