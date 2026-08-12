# Repository Guidelines

## Project layout

`app.py` is the Streamlit entry point. Application code lives under `dashboard/`, maintenance and data-source scripts under `scripts/`, deployment configuration under `tooling/`, and reusable documentation under `docs/`. Local data belongs in `data/`; local binary references belong in `references-local/`. Do not commit credentials, databases, raw data, binary research files, logs, caches, or temporary exports.

## Run and test

- Run HTFA with `scripts\windows\start.bat`.
- Rebuild the project-local runtime with `scripts\windows\setup_runtime.bat` only when dependencies or the runtime are damaged.
- After a code change, run only the tests relevant to the changed behavior. Run the complete suite only for broad cross-module changes.

## Code changes

Use four-space indentation and PEP 8 naming. Keep UI rendering separate from data transformation, reuse existing module utilities, and keep diffs focused. Preserve user files and unrelated worktree changes. Runtime input validation, statistical assumptions, workbook schemas, authentication, download safety, and failure rollback are product behavior and must not be removed merely to shorten the code.
