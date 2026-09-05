# Remove User Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the HTFA user-management module and its authentication, authorization, session, registration, and user-database code so the application is an unrestricted single-session analytics application.

**Architecture:** Remove `dashboard/auth` as one bounded feature slice instead of retaining disabled adapters. Make navigation and page rendering depend only on the business-module configuration; every visible module and tab is available in the same Streamlit session. Retain the existing `data/users.db` file untouched because it is local user data, not executable code, and deletion was not authorized.

**Tech Stack:** Python 3.11+, Streamlit, pytest, Streamlit `AppTest`.

---

### Task 1: Add removal-contract regression tests

**Files:**
- Modify: `tests/test_core_boundaries.py`
- Modify: `tests/test_app_smoke.py`
- Modify: `tests/core/test_cache_policy.py`
- Modify: `tests/models/test_sarimax_boundaries.py`
- Delete: `tests/auth/test_dependency_wiring.py`

**Step 1: Write the failing tests**

Replace authentication/permission assertions with these behavioral contracts:

```python
def test_authentication_package_is_absent() -> None:
    assert not Path("dashboard/auth").exists()

def test_public_entry_renders_all_business_modules(monkeypatch) -> None:
    monkeypatch.delenv("HTFA_DEBUG_MODE", raising=False)
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not app.exception
    assert [button.label for button in app.sidebar.button] == [
        "数据预览", "模型分析", "监测分析", "数据探索"
    ]
```

Update the SARIMAX boundary test to derive its submodule and tab assertions directly from `MODULE_CONFIG`, without importing the removed permission tree/builder. Limit the cache-policy protected roots to the workspace package.

**Step 2: Run tests to verify they fail**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\test_core_boundaries.py tests\test_app_smoke.py tests\core\test_cache_policy.py tests\models\test_sarimax_boundaries.py -q
```

Expected: FAIL because `dashboard/auth` and the authentication-dependent entry flow still exist.

### Task 2: Remove the authentication and user-management feature slice

**Files:**
- Delete: `dashboard/auth/__init__.py`
- Delete: `dashboard/auth/authentication.py`
- Delete: `dashboard/auth/config.py`
- Delete: `dashboard/auth/database.py`
- Delete: `dashboard/auth/models.py`
- Delete: `dashboard/auth/permission_builder.py`
- Delete: `dashboard/auth/permissions.py`
- Delete: `dashboard/auth/security.py`
- Delete: `dashboard/auth/ui/__init__.py`
- Delete: `dashboard/auth/ui/middleware.py`
- Delete: `dashboard/auth/ui/components/__init__.py`
- Delete: `dashboard/auth/ui/components/user_info_panel.py`
- Delete: `dashboard/auth/ui/pages/__init__.py`
- Delete: `dashboard/auth/ui/pages/_shared.py`
- Delete: `dashboard/auth/ui/pages/login.py`
- Delete: `dashboard/auth/ui/pages/register.py`
- Delete: `dashboard/auth/ui/pages/user_management.py`

**Step 1: Remove the feature package**

Delete every file under `dashboard/auth/`, including the SQLite adapter, security utility, permission tree, middleware, login/registration screens, user information panel, and management page. Do not modify or delete `data/users.db`.

**Step 2: Verify the package is gone**

Run:

```powershell
Test-Path dashboard\auth
```

Expected: `False`.

### Task 3: Make navigation and page rendering unrestricted

**Files:**
- Modify: `app.py`
- Modify: `dashboard/navigation_config.py`
- Modify: `dashboard/core/ui/components/sidebar/renderer.py`
- Modify: `dashboard/core/ui/components/module_selector.py`
- Modify: `dashboard/core/ui/components/content_router.py`

**Step 1: Simplify the entry point**

Remove the auth imports and `_authenticate`, `_set_authorization_state`, and `_render_user_panel`. `main()` must load styles, serve the standalone overview if requested, then render the complete sidebar and content directly.

**Step 2: Remove permission-only navigation metadata**

Replace `GRANULAR_PERMISSION_MAP`/`PERMISSION_MODULE_MAP` with the direct four-module `MODULE_CONFIG`; exclude the `用户管理` module.

**Step 3: Remove permission gates from the UI chain**

Make the sidebar render all configured main and submodules. Remove `用户管理` from the first-column layout set. Remove `check_user_permission`, user-management dispatch, management-specific navigation level logic, and permission-filtered model tabs from the content router. Keep the existing business renderers and a local/public welcome title with no import from the removed feature package.

**Step 4: Run focused navigation tests**

Run the command from Task 1.

Expected: PASS; a default AppTest reaches the four business-module buttons without a login form or exception.

### Task 4: Remove remaining page-level authorization branching

**Files:**
- Modify: `dashboard/analysis/industrial/industrial_analysis.py`
- Modify: `dashboard/explore/ui/bivariate_page.py`
- Modify: `dashboard/core/ui/utils/error_handler.py`
- Modify: `dashboard/core/ui/utils/debug_helpers.py`

**Step 1: Make business tabs unconditional**

Render the industrial analysis and bivariate analysis tab sets directly from their existing ordered tuples; remove all `auth.*` session-state reads and lazy middleware imports.

**Step 2: Decouple diagnostics from identity state**

Show detailed UI errors only when the caller passes `show_details=True`. Retain `HTFA_DEBUG_MODE` exclusively as an ordinary logging switch in `debug_helpers`, with no claim or dependency on authentication.

**Step 3: Re-run focused regression tests**

Run:

```powershell
runtime\python.exe -B -m pytest -c tooling\pytest.ini tests\analysis tests\exploration tests\core tests\models tests\test_app_smoke.py tests\test_core_boundaries.py -q
```

Expected: PASS with no import error or permission-dependent rendering path.

### Task 5: Prove no executable-code remnants and complete validation

**Files:**
- Verify only; do not modify unrelated documentation or local data.

**Step 1: Run the executable-code residual scan**

Run:

```powershell
rg -n -i --glob '*.py' "dashboard\.auth|AuthDatabase|AuthManager|AuthMiddleware|PermissionManager|AuthConfig|UserManagementPage|render_user_management|auth\.current_user|auth\.debug_mode|user_management|用户管理" app.py dashboard tests components tooling
```

Expected: exit code 1 (no matches). The scan intentionally excludes historical documentation and `data/users.db`.

**Step 2: Compile application code**

Run:

```powershell
runtime\python.exe -B -m compileall -q app.py htfa
```

Expected: exit code 0.

**Step 3: Run the full test suite**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini -q
```

Expected: all collected tests pass.

**Step 4: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; retain the pre-existing unrelated modification to `docs/开发任务.txt` untouched.
