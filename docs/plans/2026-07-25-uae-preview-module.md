# UAE Preview Module Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an “阿联酋” data-preview submodule and migrate industrial preview loading to the same metadata-rich Excel contract.

**Architecture:** A shared workbook parser reads `指标字典` plus per-sheet metadata rows 2–6 and produces a normalized `LoadedPreviewData` object. Industrial and UAE modules use the same parser and shared tabs, while module-specific renderers provide the title, default file, and isolated Streamlit state namespace.

**Tech Stack:** Python 3.11+, pandas, openpyxl, Streamlit, pytest

---

### Task 1: Shared workbook contract and metadata model

**Files:**
- Create: `dashboard/preview/core/workbook_parser.py`
- Modify: `dashboard/preview/domain/models.py`
- Modify: `dashboard/preview/modules/industrial/loader.py`
- Test: `tests/preview/test_workbook_parser.py`

**Steps:**
1. Write tests that build a workbook in memory with `指标字典`, rows 2–6 metadata, and data from row 7.
2. Assert that missing/invalid dictionary or metadata labels raise clear `ValueError` messages.
3. Add `IndicatorMetadata` and store normalized metadata by indicator in `LoadedPreviewData`.
4. Parse sheet metadata as authoritative for frequency, unit, source, and update time.
5. Merge dictionary type, industry, data source, and forecast-variable fields without overwriting sheet source.
6. Derive legacy maps and frequency DataFrames from normalized metadata.
7. Run `python -m pytest tests/preview/test_workbook_parser.py -v`; expect all tests to pass.

### Task 2: Namespaced preview state and shared tabs

**Files:**
- Modify: `dashboard/core/ui/utils/state_helpers.py`
- Modify: `dashboard/preview/modules/industrial/renderer.py`
- Modify: `dashboard/preview/shared/tabs.py`
- Test: `tests/preview/test_preview_state.py`

**Steps:**
1. Write a failing test proving `preview.industrial` and `preview.uae` values do not collide.
2. Add optional module namespaces to preview state helpers.
3. Pass the renderer namespace through overview and time-series tab functions.
4. Prefix Streamlit widget keys with the module identifier.
5. Save complete indicator metadata alongside compatibility maps.
6. Run the state and parser tests; expect all tests to pass.

### Task 3: UAE module

**Files:**
- Create: `dashboard/preview/modules/uae/__init__.py`
- Create: `dashboard/preview/modules/uae/config.py`
- Create: `dashboard/preview/modules/uae/loader.py`
- Create: `dashboard/preview/modules/uae/renderer.py`
- Modify: `dashboard/preview/modules/__init__.py`
- Test: `tests/preview/test_uae_module.py`

**Steps:**
1. Reuse the industrial frequency, summary, and plot configuration.
2. Configure title `阿联酋数据预览`, default file `data/阿联酋.xlsx`, module id `uae`, and state namespace `preview.uae`.
3. Register the module as `uae`.
4. Test registry creation, default path, fixed seven-tab order, and module namespace.
5. Run module tests; expect all tests to pass.

### Task 4: Navigation, permissions, and industrial path

**Files:**
- Modify: `app.py`
- Modify: `dashboard/core/ui/constants.py`
- Modify: `dashboard/core/ui/components/content_router.py`
- Modify: `dashboard/auth/permissions.py`
- Modify: `dashboard/preview/modules/industrial/renderer.py`
- Test: `tests/preview/test_uae_navigation.py`

**Steps:**
1. Add `阿联酋` under `数据预览`.
2. Map it to the `uae` registry id and treat it as a function-active preview module.
3. Add permission code `data_preview.uae`.
4. Change the industrial default preview path to `data/工业/经济数据库0202.xlsx`.
5. Test routing and granular permission configuration.

### Task 5: Verification

**Files:**
- Read only: `data/阿联酋.xlsx`
- Read only after user conversion: `data/工业/经济数据库0202.xlsx`

**Steps:**
1. Run the parser against the real UAE workbook.
2. Verify daily `(5766, 1)`, monthly `(307, 1)`, quarterly `(56, 24)`, yearly `(46, 3)`, with empty weekly and ten-day data.
3. Verify all 29 indicators have frequency, unit, sheet source, and update time metadata.
4. Verify dictionary source and sheet source remain separately available.
5. Run `python -m pytest tests/preview -v`.
6. Run `python -m compileall app.py dashboard tests`.
7. Start Streamlit and smoke-test module switching when practical.

No Git commit is included because the user did not request one.
