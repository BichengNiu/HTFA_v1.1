"""Excel COM 写表脚本共享的 PowerShell 调用基础设施。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

_POWERSHELL_BASE = (
    "powershell.exe",
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
)
_EXCEL_WRITER_TIMEOUT_SECONDS = 180.0
_EXCEL_SHUTDOWN_TIMEOUT_SECONDS = 15.0
_AUTOMATION_EXCEL_QUERY = (
    "Get-CimInstance Win32_Process -Filter \"Name='EXCEL.EXE'\" | "
    "Where-Object { $_.CommandLine -match "
    "'(?i)\\s/automation\\s+-Embedding(?:\\s|$)' } | "
    "Select-Object -ExpandProperty ProcessId"
)


def records_latest_first(observations: Iterable) -> list[dict[str, object]]:
    """按 period 倒序序列化观测记录。"""

    return [
        {
            "period": observation.period,
            "values": [
                None if value is None else float(value)
                for value in observation.values
            ],
        }
        for observation in sorted(
            observations,
            key=lambda item: item.period,
            reverse=True,
        )
    ]


@contextmanager
def payload_json_file(
    payload: dict[str, Any],
    *,
    prefix: str,
    directory: Path,
) -> Iterator[Path]:
    """创建临时 payload JSON 并在退出时删除。"""

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix=prefix,
            suffix=".json",
            dir=directory,
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=True)
        yield temporary_path
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _automation_excel_pids() -> set[int]:
    """返回隐藏 Excel COM 自动化进程，不包含用户可见的 Excel。"""

    if os.name != "nt":
        return set()
    try:
        completed = subprocess.run(
            (
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _AUTOMATION_EXCEL_QUERY,
            ),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        try:
            pids.add(int(line.strip()))
        except ValueError:
            continue
    return pids


def _wait_for_automation_excel(pids: set[int], timeout: float) -> set[int]:
    """等待指定的隐藏 Excel 进程退出，并返回仍存活的 PID。"""

    deadline = time.monotonic() + timeout
    while pids:
        remaining = pids & _automation_excel_pids()
        if not remaining or time.monotonic() >= deadline:
            return remaining
        time.sleep(0.5)
    return set()


def _terminate_automation_excel(pids: set[int]) -> None:
    """只强制结束已确认带 COM 自动化参数的隐藏 Excel 进程。"""

    for pid in sorted(pids & _automation_excel_pids()):
        try:
            subprocess.run(
                ("taskkill.exe", "/PID", str(pid), "/F"),
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue


def cleanup_excel_automation() -> None:
    """等待并清理残留的隐藏 Excel COM 进程，不触碰可见 Excel。"""

    pids = _automation_excel_pids()
    if not pids:
        return
    remaining = _wait_for_automation_excel(
        pids,
        _EXCEL_SHUTDOWN_TIMEOUT_SECONDS,
    )
    if remaining:
        _terminate_automation_excel(remaining)
        _wait_for_automation_excel(remaining, 2.0)


def run_powershell_command(
    arguments: Sequence[str],
    *,
    timeout_seconds: float = _EXCEL_WRITER_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """运行一个 Excel PowerShell 助手并管理其隐藏 COM 进程。

    ``arguments`` 必须包含完整的 PowerShell 命令及参数；
    ``timeout_seconds`` 是助手允许运行的最长秒数。
    """

    cleanup_excel_automation()
    before = _automation_excel_pids()
    process = subprocess.Popen(
        tuple(arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout, stderr = process.communicate()
        cleanup_excel_automation()
        detail = (stderr or stdout or "").strip()
        message = (
            f"Excel PowerShell helper timed out after {timeout_seconds:.0f}s"
        )
        if detail:
            message += f": {detail}"
        raise TimeoutError(message) from exc
    finally:
        # PowerShell may exit before Excel's COM server has finished shutting
        # down.  Wait for the processes visible after launch, then reap only
        # hidden automation instances that failed to quit.
        launched = _automation_excel_pids() - before
        remaining = _wait_for_automation_excel(
            launched,
            _EXCEL_SHUTDOWN_TIMEOUT_SECONDS,
        )
        if remaining:
            _terminate_automation_excel(remaining)
            _wait_for_automation_excel(remaining, 2.0)
        # Also reap an automation instance that predated this helper call.
        # This matters when a non-COM source (for example GFS) is next in the
        # merge sequence and would otherwise encounter the stale workbook lock.
        cleanup_excel_automation()
    return subprocess.CompletedProcess(
        tuple(arguments),
        process.returncode,
        stdout,
        stderr,
    )


def run_powershell_sheet_writer(
    helper_path: Path,
    workbook_path: Path,
    payload_path: Path,
    sheet_name: str,
) -> None:
    """调用 PowerShell 写表助手并统一处理失败消息。"""

    completed = run_powershell_command(
        _POWERSHELL_BASE
        + (
            str(helper_path),
            "-WorkbookPath",
            str(workbook_path),
            "-DataPath",
            str(payload_path),
            "-SheetName",
            sheet_name,
        )
    )
    if completed.returncode:
        message = (completed.stderr or "").strip() or (
            completed.stdout or ""
        ).strip()
        raise RuntimeError(f"Excel sheet update failed: {message}")
