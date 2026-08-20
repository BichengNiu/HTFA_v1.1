import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from scripts.htfa import (
    RuntimeUpdateError,
    build_streamlit_argv,
    extract_runtime_archive,
    fetch_head_commit,
    install_ts_runtime,
    load_pinned_metadata,
    load_portable_spec,
    prepare_ts_runtime,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_COMMIT = "1" * 40
REMOTE_COMMIT = "2" * 40
RUNTIME_PACKAGES = (
    "TsMetrics", "TsModels", "TsPlots", "TsSims", "TsTests", "TsUtils",
)


def _write_runtime(root: Path, *, broken_init: bool = False) -> None:
    package_root = root / "Ts"
    package_root.mkdir(parents=True)
    source = "raise RuntimeError('broken main')\n" if broken_init else "VALUE = 1\n"
    (package_root / "__init__.py").write_text(source, encoding="utf-8")
    for package in RUNTIME_PACKAGES:
        child = package_root / package
        child.mkdir()
        (child / "__init__.py").write_text("\n", encoding="utf-8")


def _seed_installed(install_root: Path, commit: str = CURRENT_COMMIT) -> None:
    _write_runtime(install_root)
    metadata = {
        "repository": "https://github.com/BichengNiu/Ts",
        "branch": "main",
        "commit": commit,
    }
    (install_root / "Ts" / "HTFA_RUNTIME.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )


def _materializer(*, broken_init: bool = False, error: Exception | None = None):
    def materialize(commit: str, destination: Path) -> str:
        if error is not None:
            raise error
        assert commit == REMOTE_COMMIT
        _write_runtime(destination, broken_init=broken_init)
        return "a" * 64
    return materialize


def _runtime_zip(commit: str) -> bytes:
    output = io.BytesIO()
    prefix = f"Ts-{commit}"
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(f"{prefix}/__init__.py", "VALUE = 1\n")
        for package in RUNTIME_PACKAGES:
            archive.writestr(f"{prefix}/{package}/__init__.py", "\n")
    return output.getvalue()


def test_offline_uses_current_installed_version(tmp_path):
    install_root = tmp_path / "site-packages"
    _seed_installed(install_root)

    def offline():
        raise OSError("offline")

    selection = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        install_root=install_root,
        head_fetcher=offline,
    )

    assert selection.commit == CURRENT_COMMIT
    assert selection.root == install_root.resolve()
    assert selection.source == "installed"
    assert "offline" in selection.detail


def test_matching_main_head_skips_download(tmp_path):
    install_root = tmp_path / "site-packages"
    _seed_installed(install_root)

    selection = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        install_root=install_root,
        head_fetcher=lambda: CURRENT_COMMIT,
        candidate_materializer=lambda *_: pytest.fail("downloaded matching commit"),
    )

    assert selection.commit == CURRENT_COMMIT
    assert selection.source == "installed"
    assert "matches main HEAD" in selection.detail


def test_new_main_head_replaces_current_ts_without_smoke_test(tmp_path):
    install_root = tmp_path / "site-packages"
    _seed_installed(install_root)

    selection = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        install_root=install_root,
        head_fetcher=lambda: REMOTE_COMMIT,
        candidate_materializer=_materializer(broken_init=True),
    )

    assert selection.commit == REMOTE_COMMIT
    assert selection.source == "downloaded"
    assert "broken main" in (install_root / "Ts" / "__init__.py").read_text(
        encoding="utf-8"
    )


def test_download_failure_keeps_current_ts(tmp_path):
    install_root = tmp_path / "site-packages"
    _seed_installed(install_root)

    selection = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        install_root=install_root,
        head_fetcher=lambda: REMOTE_COMMIT,
        candidate_materializer=_materializer(error=OSError("download failed")),
    )

    assert selection.commit == CURRENT_COMMIT
    assert selection.source == "installed"
    assert "download failed" in selection.detail


def test_head_response_requires_full_commit_sha():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"sha":"short"}'

    with pytest.raises(RuntimeUpdateError, match="invalid commit"):
        fetch_head_commit(opener=lambda *args, **kwargs: Response())


def test_extract_rejects_zip_path_traversal(tmp_path):
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Ts-bad/__init__.py", b"")
        archive.writestr("Ts-bad/../outside.py", b"bad")

    with pytest.raises(RuntimeUpdateError, match="unsafe ZIP path"):
        extract_runtime_archive(archive_path, tmp_path / "candidate")


def test_extract_accepts_allowlisted_ts_files(tmp_path):
    archive_path = tmp_path / "runtime.zip"
    archive_path.write_bytes(_runtime_zip(REMOTE_COMMIT))

    root = extract_runtime_archive(archive_path, tmp_path / "candidate")

    assert (root / "Ts" / "TsUtils" / "__init__.py").exists()


def test_install_failure_restores_previous_ts(tmp_path, monkeypatch):
    install_root = tmp_path / "site-packages"
    candidate_root = tmp_path / "candidate"
    _seed_installed(install_root)
    _write_runtime(candidate_root, broken_init=True)
    real_replace = os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(destination) == install_root / "Ts" and not failed:
            failed = True
            raise OSError("replace failed")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_once)

    with pytest.raises(OSError, match="replace failed"):
        install_ts_runtime(
            candidate_root,
            commit=REMOTE_COMMIT,
            install_root=install_root,
        )

    metadata = json.loads(
        (install_root / "Ts" / "HTFA_RUNTIME.json").read_text(encoding="utf-8")
    )
    assert metadata["commit"] == CURRENT_COMMIT


def test_embedded_runtime_specs_are_valid():
    pinned = load_pinned_metadata(PROJECT_ROOT)
    portable = load_portable_spec(PROJECT_ROOT)

    assert pinned["repository"] == "https://github.com/BichengNiu/Ts"
    assert pinned["branch"] == "main"
    assert len(pinned["commit"]) == 40
    assert portable["python_version"] == "3.13.4"
    assert portable["platform"] == "win_amd64"
    assert portable["pip_version"] == "26.1.2"
    assert portable["pip_wheel_url"].endswith(
        "/pip-26.1.2-py3-none-any.whl"
    )
    assert len(portable["archive_sha256"]) == 64
    assert len(portable["pip_wheel_sha256"]) == 64


def test_streamlit_arguments_are_preserved():
    assert build_streamlit_argv(
        PROJECT_ROOT,
        ["--server.port=8501", "--server.headless", "true"],
    ) == [
        "streamlit",
        "run",
        str(PROJECT_ROOT / "app.py"),
        "--server.headless",
        "false",
        "--server.port=8501",
        "--server.headless",
        "true",
    ]
