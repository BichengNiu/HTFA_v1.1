# Ts runtime

HTFA installs the `Ts` time-series toolkit into the active Python environment
instead of tracking its source under the project root.

- Upstream: <https://github.com/BichengNiu/Ts>
- Bootstrap commit: `bec57a2610b38be3a8f78071d7e03850b53ca25e`
- Import namespace: `Ts`
- Local location: `.venv/Lib/site-packages/Ts` on Windows

Run `.venv\Scripts\python.exe scripts\install_ts.py` after installing the root
requirements in a new environment. `start.bat` performs this bootstrap
automatically when `Ts` is absent. The launcher checks the allowlisted upstream
branch and keeps verified updates under the active environment's site-packages
directory. Neither the installed package nor its update cache is committed,
because `.venv/` is ignored.

The pinned repository, branch, and commit are recorded in
`scripts/ts_runtime.json`. Review and update that file when changing the
bootstrap version.

The upstream snapshot did not contain a `LICENSE` file. Installation therefore
relies on authorization from the upstream owner rather than on a declared
open-source license.
