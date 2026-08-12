# HTFA unified Python runtime

HTFA uses one project-local CPython 3.13.4 environment for development,
testing, local startup, and Windows release:

```text
runtime/
|-- python.exe
|-- python313._pth
|-- runtime-manifest.json
`-- Lib/site-packages/       application packages, pip, pytest, and Ts
```

The project does not create or use a separate virtual environment. All normal
commands call `runtime\python.exe` and therefore import the same physical
dependencies.

## Create or rebuild runtime

Run from the project root:

```powershell
scripts\windows\setup_runtime.bat
```

PowerShell downloads the pinned official CPython 3.13.4 embeddable archive and
pip 26.1.2 wheel, verifies both SHA-256 values, and builds
`build/runtime-candidate`. The candidate installs every exact entry from
`tooling/requirements/requirements-py313.lock`, including pip and pytest, then installs the pinned
Ts baseline.

The candidate must pass imports, `pip check`, pytest, compileall, and a final
smoke test before it replaces `runtime`. The existing runtime is renamed to a
backup during the swap and restored if the final check fails. A failure before
the swap leaves the active runtime unchanged.

`tooling/requirements/requirements.txt` documents supported version ranges. It is not an install
input. Windows runtime construction and Docker both install the exact versions
from `tooling/requirements/requirements-py313.lock`.

## Daily commands

```powershell
runtime\python.exe -m pip check
runtime\python.exe -m pytest -q -c tooling\pytest.ini
runtime\python.exe -m compileall app.py dashboard scripts
runtime\python.exe scripts\run_htfa.py --server.port=8501
```

`scripts\windows\start.bat` uses the same runtime, clears project caches, frees port 8501,
checks Ts, and starts Streamlit. If runtime is missing, it directs the user to
run `scripts\windows\setup_runtime.bat`.

## Portable delivery

Copy the project folder with `runtime/` to another Windows x64 location and run
`scripts\windows\start.bat`. The target computer needs no installed Python, pip, Git, or
compiler. Do not include `.git/`, `build/`, test caches, credentials, or local
exports in a release copy.

`runtime/runtime-manifest.json` records the Python archive, pip wheel,
dependency-lock hash, Ts baseline commit, and build timestamp. The pinned Ts
baseline is `bec57a2610b38be3a8f78071d7e03850b53ca25e`.

## Ts update behavior

Every `scripts\windows\start.bat` run performs one bounded HTTPS check against the public
`BichengNiu/Ts` repository. A different `main` commit is downloaded by immutable
commit URL and atomically replaces only the Ts package. Network or replacement
failure leaves the installed Ts unchanged and starts HTFA with it.

The updater does not use system Git, credentials, pip, background tasks, or
version caches. By explicit project decision, a downloaded `main` commit is not
interface-validated or smoke-tested before installation.

## Docker

Docker uses Python 3.13.4 and installs the same exact
`tooling/requirements/requirements-py313.lock`. Platform-specific wheel files remain separate, but
the Python and package versions match the Windows runtime.
