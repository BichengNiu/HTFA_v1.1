from dashboard.auth.database import AuthDatabase
from dashboard.auth.ui.middleware import AuthMiddleware
from dashboard.auth.ui.pages.login import LoginPage
from dashboard.auth.ui.pages.register import RegisterPage
from dashboard.auth.ui.pages.user_management import UserManagementPage


def test_auth_ui_reuses_one_database_adapter(tmp_path):
    database = AuthDatabase(str(tmp_path / "users.db"))
    middleware = AuthMiddleware(database=database)

    login_page = LoginPage(middleware.auth_manager)
    register_page = RegisterPage(database)
    user_page = UserManagementPage(database, middleware.permission_manager)

    assert middleware.auth_manager.db is database
    assert login_page.auth_manager is middleware.auth_manager
    assert register_page.db is database
    assert user_page.db is database
    assert user_page.permission_manager is middleware.permission_manager


def test_permission_manager_has_no_database_dependency(tmp_path):
    database = AuthDatabase(str(tmp_path / "users.db"))
    middleware = AuthMiddleware(database=database)

    assert not hasattr(middleware.permission_manager, "db")


def test_auth_page_helpers_require_explicit_dependencies():
    import inspect

    from dashboard.auth.ui.pages.login import render_login_page
    from dashboard.auth.ui.pages.register import render_register_page

    assert inspect.signature(render_login_page).parameters["auth_manager"].default is inspect.Parameter.empty
    assert inspect.signature(render_register_page).parameters["database"].default is inspect.Parameter.empty
