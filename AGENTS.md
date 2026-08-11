# Repository Guidelines

## Project Structure & Module Organization

`app.py` is the Streamlit entry point and top-level router. Application code lives under `dashboard/`: `core/` provides initialization, navigation, and resource loading; `auth/` handles users and permissions; `analysis/industrial/` contains industrial dashboards; `models/DFM/` covers data preparation, training, and results; `explore/` contains time-series analysis; and `preview/` renders uploaded data. Reference documents are in `docs/`, while Excel, CSV, and SQLite runtime inputs are in `data/`. Keep domain logic close to its module and reusable UI or calculations in that module's `utils/`, `core/`, or `shared/` package.

## Build, Test, and Development Commands

- `python -m venv .venv` creates the machine-local Python 3.13.4 development environment; never copy `.venv/` between computers.
- `.venv\Scripts\python.exe -m pip install -r requirements.txt` installs the development dependencies into that environment.
- `.venv\Scripts\python.exe scripts\install_ts.py` installs the pinned `Ts` runtime into that virtual environment; do not restore or commit a root-level `Ts/` copy.
- `streamlit run app.py --server.port=8501` starts the local dashboard.
- `start.bat` starts the Windows development environment, clears Python caches, and frees port 8501.
- `docker compose up --build -d` builds and runs the containerized application.
- `python -m compileall app.py dashboard` performs a quick syntax/import-layout check before review.

## Coding Style & Naming Conventions

Use four-space indentation and follow PEP 8. Name modules, functions, and variables with `snake_case`; classes with `PascalCase`; constants with `UPPER_SNAKE_CASE`. Add type hints to public functions and concise docstrings where behavior, inputs, or statistical assumptions are not obvious. Prefer absolute imports beginning with `dashboard`. Keep Streamlit state keys centralized and avoid mixing UI rendering with data transformation. No formatter or linter is configured, so match surrounding code and keep diffs focused.

## Testing Guidelines

The repository currently has no committed automated test suite or coverage threshold. For new logic, add `pytest` tests under `tests/`, mirroring package paths and naming files `test_<module>.py`. Test calculations and validation independently from Streamlit UI. Before submitting, run the compile check and smoke-test affected pages with representative files from `data/`; document manual scenarios and results in the pull request.

## Commit & Pull Request Guidelines

Recent commits use short Chinese summaries such as `优化` and `优化-可用`. Preserve the concise style but describe the affected behavior, for example `修复 DFM 训练日期校验`. Keep each commit focused. Pull requests should include the problem, implementation summary, validation evidence, and any data or configuration impact. Add screenshots for visible UI changes and link the relevant issue or task when available.

### Mandatory Pre-Push Cleanup

Before every commit intended for a remote branch, and again immediately before pushing, remove all reproducible test artifacts and caches from the repository working tree. This includes `__pycache__/`, `*.pyc`, `*.pyo`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, coverage outputs, pytest temporary directories, test logs, smoke-test outputs, and other files created only by local validation. Inspect and resolve each target before deletion; never use a broad recursive cleanup against the repository root. Do not delete `.venv/`, `.git/`, files under `data/`, user-created logs or exports, or unrelated untracked/modified files. After cleanup, run `git status --short` and confirm that no generated test or cache artifacts remain before committing or pushing. Report what was cleaned and preserve every user change not explicitly in scope.

## Security & Data Handling

Do not commit credentials, tokens, `.env` files, production user databases, or temporary spreadsheet exports. Keep `HTFA_DEBUG_MODE=true` limited to local development; verify authentication with debug mode disabled before deployment.
