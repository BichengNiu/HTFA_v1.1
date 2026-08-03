# Vendored Ts package

This directory contains the runtime Python source of the `Ts` time-series
toolkit used by HTFA.

- Upstream: <https://github.com/BichengNiu/Ts>
- Commit: `bec57a2610b38be3a8f78071d7e03850b53ca25e`
- Vendored on: 2026-08-03
- Import namespace: `Ts`

## Included scope

The root package initializer and runtime `.py` files from `TsMetrics`,
`TsModels`, `TsPlots`, `TsSims`, `TsTests`, and `TsUtils` are included without
source changes. Upstream tests, notebooks, READMEs, caches, repository metadata,
and development configuration are excluded.

Third-party runtime dependencies are declared by HTFA's root
`requirements.txt`; this directory is imported directly and is not installed as
a separate distribution.

## Updating

Choose and review an exact upstream commit, rerun HTFA's vendored-package and
Explore regression tests, then update both the commit above and the vendored
sources in the same change. Do not track a moving branch.

Local Windows startup is separate from updating this immutable fallback.
`start.bat` uses `scripts/run_htfa.py` to check the private upstream `main`
branch through the current user's Git Credential Manager credentials. A new
commit is stored under `%LOCALAPPDATA%\HTFA\ts-runtime`, validated, and
preloaded for that process. Network, Git, credential, dependency, or validation
failures keep the most recent verified runtime active and ultimately fall back
to this directory. The updater never runs `pip install` and never overwrites
these vendored files.

## License notice

The upstream snapshot did not contain a `LICENSE` file. Its inclusion in HTFA
therefore relies on authorization from the upstream owner rather than on a
declared open-source license. Add the upstream license here if one is published
later.
