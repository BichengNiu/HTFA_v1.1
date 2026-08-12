# Repository Guidelines

## Project Structure & Module Organization

`app.py` is the Streamlit entry point and top-level router. Application code lives under `dashboard/`: `core/` provides initialization, navigation, and resource loading; `auth/` handles users and permissions; `analysis/industrial/` contains industrial dashboards; `models/DFM/` covers data preparation, training, and results; `explore/` contains time-series analysis; and `preview/` renders uploaded data. Versioned project documents are in `docs/`; local Excel, CSV, PDF, and SQLite inputs stay in the ignored `data/` tree, with only its `README.md` files committed. Reproducible source-update code belongs in `scripts/data_sources/`, and local binary research material belongs in `references-local/`. Developer and deployment configuration is grouped under `tooling/`; executable maintenance and Windows entry scripts live under `scripts/`. Keep domain logic close to its module and reusable UI or calculations in that module's `utils/`, `core/`, or `shared/` package.

## Build, Test, and Development Commands

- `scripts\windows\setup_runtime.bat` creates or safely rebuilds the single project-local CPython 3.13.4 runtime; no system Python or virtual environment is required.
- `runtime\python.exe -m pip check` verifies the exact dependencies installed from `tooling\requirements\requirements-py313.lock`.
- `runtime\python.exe scripts\install_ts.py` reinstalls the pinned `Ts` baseline into the unified runtime; do not restore or commit a root-level `Ts/` copy.
- `runtime\python.exe -m pytest -q -c tooling\pytest.ini` runs the committed automated test suite.
- `runtime\python.exe scripts\run_htfa.py --server.port=8501` starts the dashboard directly.
- `scripts\windows\start.bat` clears Python caches, frees port 8501, checks Ts, and starts HTFA with the same runtime.
- `docker compose -f tooling\docker\docker-compose.yml up --build -d` builds and runs the containerized application.
- `runtime\python.exe -m compileall app.py dashboard scripts` performs a quick syntax/import-layout check before review.

## Coding Style & Naming Conventions

Use four-space indentation and follow PEP 8. Name modules, functions, and variables with `snake_case`; classes with `PascalCase`; constants with `UPPER_SNAKE_CASE`. Add type hints to public functions and concise docstrings where behavior, inputs, or statistical assumptions are not obvious. Prefer absolute imports beginning with `dashboard`. Keep Streamlit state keys centralized and avoid mixing UI rendering with data transformation. No formatter or linter is configured, so match surrounding code and keep diffs focused.

## Testing Guidelines

The repository has a committed `pytest` suite but no coverage threshold. For new logic, add tests under `tests/`, mirroring package paths and naming files `test_<module>.py`. Test calculations and validation independently from Streamlit UI. Before submitting, run the complete suite, the compile check, and smoke-test affected pages with representative files from `data/`; document manual scenarios and results in the pull request.

## Commit & Pull Request Guidelines

Recent commits use short Chinese summaries such as `优化` and `优化-可用`. Preserve the concise style but describe the affected behavior, for example `修复 DFM 训练日期校验`. Keep each commit focused. Pull requests should include the problem, implementation summary, validation evidence, and any data or configuration impact. Add screenshots for visible UI changes and link the relevant issue or task when available.

### Mandatory Pre-Push Cleanup

Before every commit intended for a remote branch, and again immediately before pushing, remove all reproducible test artifacts and caches from the repository working tree. This includes `__pycache__/`, `*.pyc`, `*.pyo`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, coverage outputs, pytest temporary directories, test logs, smoke-test outputs, and other files created only by local validation. Inspect and resolve each target before deletion; never use a broad recursive cleanup against the repository root. Do not delete `runtime/`, `.git/`, files under `data/`, user-created logs or exports, or unrelated untracked/modified files. After cleanup, run `git status --short` and confirm that no generated test or cache artifacts remain before committing or pushing. Report what was cleaned and preserve every user change not explicitly in scope.

## Security & Data Handling

Do not commit credentials, tokens, `.env` files, production user databases, raw source data, binary reference documents, or temporary spreadsheet exports. Keep local datasets under `data/` and binary research material under `references-local/`; commit only their documentation and reproducible acquisition or transformation code. Keep `HTFA_DEBUG_MODE=true` limited to local development; verify authentication with debug mode disabled before deployment.
